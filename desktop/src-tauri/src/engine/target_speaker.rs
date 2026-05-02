use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicBool, Ordering},
};

use ndarray::{ArrayView1, ArrayView2};
use ort::{
    session::{builder::GraphOptimizationLevel, Session},
    value::TensorRef,
};
use parking_lot::Mutex;
use uuid::Uuid;

use crate::{
    audio::io::{self, DecodedAudio},
    config::TargetSpeakerAssetCatalog,
    error::{AppError, AppResult},
    models::{TargetSpeakerEngine, TargetSpeakerOutputMode, TargetSpeakerRuntimeInfo},
};

use super::dsp::{project_removed_to_channels, sinc_resample};

pub struct TargetSpeakerRuntime {
    assets: TargetSpeakerAssetCatalog,
    tsextract: Mutex<Option<TSExtractOnnxRuntime>>,
    reference_cache: Mutex<HashMap<PathBuf, PreparedTSExtractReference>>,
}

struct TSExtractOnnxRuntime {
    session: Session,
    sample_rate: u32,
    mixture_samples: usize,
    reference_samples: usize,
}

#[derive(Clone)]
struct PreparedTSExtractReference {
    fixed: Vec<f32>,
    length: i64,
}

pub struct TargetSpeakerLiveProcessor {
    reference: PreparedTSExtractReference,
    context_model: Vec<f32>,
    output_mode: TargetSpeakerOutputMode,
    removal_scale: f32,
}

impl TargetSpeakerRuntime {
    pub fn new(assets: TargetSpeakerAssetCatalog) -> Self {
        Self {
            assets,
            tsextract: Mutex::new(None),
            reference_cache: Mutex::new(HashMap::new()),
        }
    }

    pub fn info(&self) -> TargetSpeakerRuntimeInfo {
        TargetSpeakerRuntimeInfo {
            model_id: self.assets.model_id.clone(),
            display_name: self.assets.display_name.clone(),
            runtime_kind: self.assets.runtime_kind.clone(),
            default_engine: TargetSpeakerEngine::TsextractOnnx,
            available_engines: vec![
                TargetSpeakerEngine::TsextractOnnx,
                TargetSpeakerEngine::ClearvoiceBundle,
            ],
            model_sample_rate: self.assets.sample_rate,
            mixture_samples: self.assets.mixture_samples,
            reference_samples: self.assets.reference_samples,
            validation_status: self.assets.validation_status.clone(),
            runtime_metadata_paths: [
                &self.assets.tsextract_manifest_path,
                &self.assets.tsextract_validation_path,
                &self.assets.bundle_manifest_path,
            ]
            .iter()
            .filter(|path| path.exists())
            .map(|path| path.to_string_lossy().to_string())
            .collect(),
            bundle_manifest_path: path_if_exists(&self.assets.bundle_manifest_path),
            tsextract_onnx_path: path_if_exists(&self.assets.tsextract_onnx_path),
            clearvoice_bundle_path: path_if_exists(&self.assets.clearvoice_bundle_dir),
            onnx_sidecar_present: tsextract_sidecar_path(&self.assets.tsextract_onnx_path).exists(),
            clearvoice_ready: self.clearvoice_python().exists(),
        }
    }

    pub fn process<F>(
        &self,
        input_path: &Path,
        reference_path: &Path,
        engine: TargetSpeakerEngine,
        output_mode: TargetSpeakerOutputMode,
        removal_scale: f32,
        cancel_flag: &AtomicBool,
        progress: &mut F,
    ) -> AppResult<DecodedAudio>
    where
        F: FnMut(f32),
    {
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }

        let mixture = io::decode_audio_file(input_path)?;
        if mixture.frame_count() == 0 {
            return Ok(DecodedAudio::from_channels(
                mixture.sample_rate,
                vec![Vec::new(); mixture.channel_count().max(1)],
            ));
        }
        progress(0.08);

        let target_mono = match engine {
            TargetSpeakerEngine::TsextractOnnx => {
                let reference = self.prepare_tsextract_reference(reference_path)?;
                progress(0.14);
                self.extract_tsextract(&mixture, &reference, cancel_flag, progress)?
            }
            TargetSpeakerEngine::ClearvoiceBundle => {
                progress(0.14);
                self.extract_clearvoice(input_path, reference_path, &mixture, cancel_flag)?
            }
        };
        progress(0.92);

        let output =
            render_target_speaker_output(&mixture, &target_mono, output_mode, removal_scale);
        progress(1.0);
        Ok(output)
    }

    pub fn preferred_live_hop_ms(&self) -> f32 {
        6_000.0
    }

    pub fn preferred_live_hop_samples(&self, input_rate: u32) -> usize {
        ((input_rate as f32 * self.preferred_live_hop_ms() / 1000.0).round() as usize).max(1)
    }

    pub fn make_live_processor(
        &self,
        reference_path: &Path,
        engine: TargetSpeakerEngine,
        output_mode: TargetSpeakerOutputMode,
        removal_scale: f32,
    ) -> AppResult<TargetSpeakerLiveProcessor> {
        if engine != TargetSpeakerEngine::TsextractOnnx {
            return Err(AppError::message(
                "The ClearVoice quality bundle is offline-only. Use Fast ONNX for speaker realtime.",
            ));
        }

        let reference = self.prepare_tsextract_reference(reference_path)?;
        Ok(TargetSpeakerLiveProcessor {
            reference,
            context_model: Vec::with_capacity(self.assets.mixture_samples),
            output_mode,
            removal_scale,
        })
    }

    pub fn suppress_live_chunk(
        &self,
        processor: &mut TargetSpeakerLiveProcessor,
        chunk: &[f32],
        sample_rate: u32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }

        if chunk.is_empty() {
            return Ok(Vec::new());
        }

        let input = sanitize_audio(chunk);
        let model_chunk = if sample_rate == self.assets.sample_rate {
            input.clone()
        } else {
            sinc_resample(&input, sample_rate, self.assets.sample_rate)?
        };
        let model_chunk_len = model_chunk.len().max(1);

        processor.context_model.extend_from_slice(&model_chunk);
        if processor.context_model.len() > self.assets.mixture_samples {
            let overflow = processor.context_model.len() - self.assets.mixture_samples;
            processor.context_model.drain(0..overflow);
        }

        let target_context = {
            let mut guard = self.tsextract.lock();
            if guard.is_none() {
                *guard = Some(TSExtractOnnxRuntime::new(&self.assets)?);
            }
            let runtime = guard
                .as_mut()
                .ok_or_else(|| AppError::message("TSExtract ONNX runtime was not initialized"))?;
            runtime.extract_model_rate_with_reference(
                &processor.context_model,
                &processor.reference,
                cancel_flag,
                &mut || {},
            )?
        };

        let tail_len = target_context.len().min(model_chunk_len);
        let target_tail_model = target_context
            .get(target_context.len().saturating_sub(tail_len)..)
            .unwrap_or(&[])
            .to_vec();
        let mut target_tail = if sample_rate == self.assets.sample_rate {
            target_tail_model
        } else {
            sinc_resample(&target_tail_model, self.assets.sample_rate, sample_rate)?
        };
        target_tail.resize(input.len(), 0.0);
        target_tail.truncate(input.len());

        let scale = processor.removal_scale.clamp(0.0, 2.5);
        let output = match processor.output_mode {
            TargetSpeakerOutputMode::ExtractTarget => target_tail,
            TargetSpeakerOutputMode::RemoveTarget => input
                .iter()
                .zip(target_tail.iter())
                .map(|(mix, target)| sanitize_sample(*mix - scale * *target))
                .collect(),
        };

        Ok(sanitize_audio(&output))
    }

    fn extract_tsextract<F>(
        &self,
        mixture: &DecodedAudio,
        reference: &PreparedTSExtractReference,
        cancel_flag: &AtomicBool,
        progress: &mut F,
    ) -> AppResult<Vec<f32>>
    where
        F: FnMut(f32),
    {
        let mixture_mono = sanitize_audio(&mixture.mono_range(0, mixture.frame_count()));
        let mixture_model =
            sinc_resample(&mixture_mono, mixture.sample_rate, self.assets.sample_rate)?;

        let mut guard = self.tsextract.lock();
        if guard.is_none() {
            *guard = Some(TSExtractOnnxRuntime::new(&self.assets)?);
        }
        let runtime = guard
            .as_mut()
            .ok_or_else(|| AppError::message("TSExtract ONNX runtime was not initialized"))?;
        let chunk_count = mixture_model.len().div_ceil(runtime.mixture_samples).max(1) as f32;
        let mut completed = 0.0f32;
        let target_model = runtime.extract_model_rate_with_reference(
            &mixture_model,
            reference,
            cancel_flag,
            &mut || {
                completed += 1.0;
                progress(0.14 + (completed / chunk_count).clamp(0.0, 1.0) * 0.76);
            },
        )?;
        let mut target = sinc_resample(&target_model, runtime.sample_rate, mixture.sample_rate)?;
        target.resize(mixture.frame_count(), 0.0);
        target.truncate(mixture.frame_count());
        Ok(sanitize_audio(&target))
    }

    fn prepare_tsextract_reference(
        &self,
        reference_path: &Path,
    ) -> AppResult<PreparedTSExtractReference> {
        let cache_key =
            fs::canonicalize(reference_path).unwrap_or_else(|_| reference_path.to_path_buf());
        if let Some(reference) = self.reference_cache.lock().get(&cache_key).cloned() {
            return Ok(reference);
        }

        let reference = io::decode_audio_file(reference_path)?;
        let reference_mono = sanitize_audio(&reference.mono_range(0, reference.frame_count()));
        let reference_model = sinc_resample(
            &reference_mono,
            reference.sample_rate,
            self.assets.sample_rate,
        )?;
        let (fixed, original_samples) =
            pad_or_trim(&reference_model, self.assets.reference_samples);
        let prepared = PreparedTSExtractReference {
            fixed,
            length: original_samples.min(self.assets.reference_samples) as i64,
        };
        self.reference_cache
            .lock()
            .insert(cache_key, prepared.clone());
        Ok(prepared)
    }

    fn extract_clearvoice(
        &self,
        input_path: &Path,
        reference_path: &Path,
        mixture: &DecodedAudio,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }
        if !self.assets.clearvoice_bundle_dir.exists() {
            return Err(AppError::message(format!(
                "ClearVoice bundle was not found at '{}'",
                self.assets.clearvoice_bundle_dir.display()
            )));
        }
        let script = self
            .assets
            .clearvoice_bundle_dir
            .join("run_clearvoice_extract.ps1");
        if !script.exists() {
            return Err(AppError::message(format!(
                "ClearVoice runner script was not found at '{}'",
                script.display()
            )));
        }
        let python = self.clearvoice_python();
        if !python.exists() {
            return Err(AppError::message(format!(
                "ClearVoice bundle runtime is not installed. Run '{}' once, then try the Quality Bundle engine again.",
                self.assets
                    .clearvoice_bundle_dir
                    .join("install_clearvoice_runtime.ps1")
                    .display()
            )));
        }

        let out_dir = std::env::temp_dir().join(format!("tsebp_target_speaker_{}", Uuid::new_v4()));
        fs::create_dir_all(&out_dir)?;

        let completed = Command::new("powershell")
            .arg("-ExecutionPolicy")
            .arg("Bypass")
            .arg("-File")
            .arg(&script)
            .arg("-Mixture")
            .arg(input_path)
            .arg("-Reference")
            .arg(reference_path)
            .arg("-Out")
            .arg(&out_dir)
            .arg("-Device")
            .arg("cpu")
            .current_dir(&self.assets.clearvoice_bundle_dir)
            .output()?;

        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }
        if !completed.status.success() {
            return Err(AppError::message(format!(
                "ClearVoice bundle failed with exit code {:?}. stdout: {} stderr: {}",
                completed.status.code(),
                String::from_utf8_lossy(&completed.stdout).trim(),
                String::from_utf8_lossy(&completed.stderr).trim()
            )));
        }

        let target_path = out_dir.join("target.wav");
        if !target_path.exists() {
            return Err(AppError::message(format!(
                "ClearVoice bundle did not create '{}'",
                target_path.display()
            )));
        }
        let target_audio = io::decode_audio_file(&target_path)?;
        let target_mono = sanitize_audio(&target_audio.mono_range(0, target_audio.frame_count()));
        let mut target =
            sinc_resample(&target_mono, target_audio.sample_rate, mixture.sample_rate)?;
        target.resize(mixture.frame_count(), 0.0);
        target.truncate(mixture.frame_count());
        Ok(sanitize_audio(&target))
    }

    fn clearvoice_python(&self) -> PathBuf {
        self.assets
            .clearvoice_bundle_dir
            .join(".venv")
            .join("Scripts")
            .join("python.exe")
    }
}

impl TSExtractOnnxRuntime {
    fn new(assets: &TargetSpeakerAssetCatalog) -> AppResult<Self> {
        if !assets.tsextract_onnx_path.exists() {
            return Err(AppError::message(format!(
                "TSExtract ONNX was not found at '{}'",
                assets.tsextract_onnx_path.display()
            )));
        }
        let sidecar = tsextract_sidecar_path(&assets.tsextract_onnx_path);
        if !sidecar.exists() {
            return Err(AppError::message(format!(
                "TSExtract ONNX external data sidecar was not found at '{}'",
                sidecar.display()
            )));
        }
        let runtime_dll = assets.runtime_dll_path.as_ref().ok_or_else(|| {
            AppError::message(
                "onnxruntime.dll was not found. Set ORT_DYLIB_PATH or place the DLL in desktop/src-tauri/runtime/",
            )
        })?;
        let _ = ort::init_from(runtime_dll)
            .map_err(|error| AppError::message(error.to_string()))?
            .commit();

        let builder = Session::builder().map_err(|error| AppError::message(error.to_string()))?;
        let builder = builder
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|error| AppError::message(error.to_string()))?;
        let builder = builder
            .with_parallel_execution(false)
            .map_err(|error| AppError::message(error.to_string()))?;
        let mut builder = builder
            .with_intra_threads(4)
            .map_err(|error| AppError::message(error.to_string()))?;
        let session = builder
            .commit_from_file(&assets.tsextract_onnx_path)
            .map_err(|error| AppError::message(error.to_string()))?;

        Ok(Self {
            session,
            sample_rate: assets.sample_rate,
            mixture_samples: assets.mixture_samples,
            reference_samples: assets.reference_samples,
        })
    }

    fn extract_model_rate_with_reference<F>(
        &mut self,
        mixture: &[f32],
        reference: &PreparedTSExtractReference,
        cancel_flag: &AtomicBool,
        on_chunk: &mut F,
    ) -> AppResult<Vec<f32>>
    where
        F: FnMut(),
    {
        if mixture.is_empty() {
            on_chunk();
            return Ok(Vec::new());
        }

        let reference_length = [reference.length];
        let reference_view =
            ArrayView2::from_shape((1, self.reference_samples), reference.fixed.as_slice())
                .map_err(|error| AppError::message(error.to_string()))?;
        let reference_length_view = ArrayView1::from(&reference_length[..]);
        let mut target = Vec::with_capacity(mixture.len());

        for chunk in mixture.chunks(self.mixture_samples) {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }
            let valid_length = chunk.len();
            let (mixture_fixed, _) = pad_or_trim(chunk, self.mixture_samples);
            let mixture_view =
                ArrayView2::from_shape((1, self.mixture_samples), mixture_fixed.as_slice())
                    .map_err(|error| AppError::message(error.to_string()))?;

            let outputs = self.session.run(ort::inputs![
                "mixture" => TensorRef::from_array_view(mixture_view)?,
                "reference" => TensorRef::from_array_view(reference_view)?,
                "reference_length" => TensorRef::from_array_view(reference_length_view)?,
            ])?;
            let output = outputs[0]
                .try_extract_array::<f32>()
                .map_err(|error| AppError::message(error.to_string()))?
                .iter()
                .copied()
                .take(valid_length)
                .map(sanitize_sample)
                .collect::<Vec<_>>();
            target.extend(output);
            on_chunk();
        }

        Ok(target)
    }
}

fn render_target_speaker_output(
    mixture: &DecodedAudio,
    target_mono: &[f32],
    output_mode: TargetSpeakerOutputMode,
    removal_scale: f32,
) -> DecodedAudio {
    let frame_count = mixture.frame_count();
    let mut target = sanitize_audio(target_mono);
    target.resize(frame_count, 0.0);
    target.truncate(frame_count);

    let channels = match output_mode {
        TargetSpeakerOutputMode::ExtractTarget => {
            duplicate_mono_to_channels(&target, mixture.channel_count().max(1))
        }
        TargetSpeakerOutputMode::RemoveTarget => {
            let original = mixture.channel_chunk(0, frame_count);
            let removed = project_removed_to_channels(&original, &target);
            let scale = removal_scale.clamp(0.0, 2.5);
            let mut clean = original.clone();
            for channel_index in 0..clean.len() {
                for frame_index in 0..clean[channel_index].len() {
                    let removed_sample = removed
                        .get(channel_index)
                        .and_then(|channel| channel.get(frame_index))
                        .copied()
                        .unwrap_or(0.0);
                    clean[channel_index][frame_index] =
                        sanitize_sample(clean[channel_index][frame_index] - scale * removed_sample);
                }
            }
            clean
        }
    };

    DecodedAudio::from_channels(mixture.sample_rate, channels)
}

fn duplicate_mono_to_channels(mono: &[f32], channel_count: usize) -> Vec<Vec<f32>> {
    let channel_count = channel_count.max(1);
    (0..channel_count).map(|_| mono.to_vec()).collect()
}

fn pad_or_trim(audio: &[f32], target_samples: usize) -> (Vec<f32>, usize) {
    let original_samples = audio.len();
    let mut fixed = vec![0.0f32; target_samples];
    let copy_len = original_samples.min(target_samples);
    fixed[..copy_len].copy_from_slice(&audio[..copy_len]);
    (fixed, original_samples)
}

fn sanitize_audio(audio: &[f32]) -> Vec<f32> {
    audio.iter().copied().map(sanitize_sample).collect()
}

fn sanitize_sample(sample: f32) -> f32 {
    if sample.is_finite() {
        sample.clamp(-0.999, 0.999)
    } else {
        0.0
    }
}

fn tsextract_sidecar_path(model_path: &Path) -> PathBuf {
    model_path.with_extension("onnx.data")
}

fn path_if_exists(path: &Path) -> Option<String> {
    path.exists().then(|| path.to_string_lossy().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn target_speaker_remove_mode_is_finite_and_preserves_layout() {
        let mixture =
            DecodedAudio::from_channels(48_000, vec![vec![0.25, -0.5, 0.75], vec![0.2, -0.4, 0.6]]);
        let output = render_target_speaker_output(
            &mixture,
            &[0.1, f32::NAN, 0.2],
            TargetSpeakerOutputMode::RemoveTarget,
            1.0,
        );
        assert_eq!(output.sample_rate, 48_000);
        assert_eq!(output.channel_count(), 2);
        assert_eq!(output.frame_count(), 3);
        assert!(output
            .channels
            .iter()
            .flatten()
            .all(|sample| sample.is_finite() && sample.abs() <= 0.999));
    }

    #[test]
    fn target_speaker_extract_mode_duplicates_mono_target() {
        let mixture = DecodedAudio::from_channels(44_100, vec![vec![0.0; 2], vec![0.0; 2]]);
        let output = render_target_speaker_output(
            &mixture,
            &[0.3, -0.2],
            TargetSpeakerOutputMode::ExtractTarget,
            1.0,
        );
        assert_eq!(output.channel_count(), 2);
        assert_eq!(output.channels[0], vec![0.3, -0.2]);
        assert_eq!(output.channels[1], vec![0.3, -0.2]);
    }

    #[test]
    fn tsextract_sidecar_keeps_onnx_filename() {
        let sidecar = tsextract_sidecar_path(Path::new("tsextract_fp32.onnx"));
        assert_eq!(sidecar, PathBuf::from("tsextract_fp32.onnx.data"));
    }
}
