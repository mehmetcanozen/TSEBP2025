pub mod dsp;

use std::{
    sync::{atomic::{AtomicBool, Ordering}, Arc},
};

use ndarray::{ArrayView1, ArrayView3};
use ort::{
    session::{builder::GraphOptimizationLevel, Session},
    value::TensorRef,
};
use parking_lot::Mutex;

use crate::{
    audio::io::DecodedAudio,
    config::{AssetCatalog, CategoryCatalog},
    error::{AppError, AppResult},
    models::{Hive15Preset, ModelCategory},
};

use self::dsp::{
    build_overlap_window, linear_resample, project_removed_to_channels, rms, MaskingOptions,
    WienerMasker,
};

const TARGET_SAMPLE_RATE: u32 = 32_000;
const SEGMENT_SECONDS: f32 = 5.0;
const OVERLAP_SECONDS: f32 = 1.0;
const OUTER_CHUNK_SECONDS: f32 = 10.0;

pub struct SharedEngine {
    assets: AssetCatalog,
    category_catalog: CategoryCatalog,
    presets: Vec<Hive15Preset>,
    runtime: Mutex<Option<Arc<InferenceRuntime>>>,
}

pub struct SuppressionProcessor {
    runtime: Arc<InferenceRuntime>,
    category_catalog: CategoryCatalog,
    masker: WienerMasker,
}

struct InferenceRuntime {
    session: Mutex<Session>,
    category_order: Vec<String>,
    model_path: String,
}

#[derive(Clone, Debug)]
pub struct EngineRuntimeInfo {
    pub provider: String,
    pub available_providers: Vec<String>,
    pub warmed: bool,
    pub model_path: Option<String>,
}

impl SharedEngine {
    pub fn new(assets: AssetCatalog) -> AppResult<Self> {
        let category_catalog = CategoryCatalog::load(&assets)?;
        let presets = crate::config::load_hive15_presets(&assets, &category_catalog)?;
        Ok(Self {
            assets,
            category_catalog,
            presets,
            runtime: Mutex::new(None),
        })
    }

    pub fn warm(&self) -> AppResult<()> {
        self.runtime().map(|_| ())
    }

    pub fn categories(&self) -> &[ModelCategory] {
        &self.category_catalog.categories
    }

    pub fn presets(&self) -> &[Hive15Preset] {
        &self.presets
    }

    pub fn validate_selected_categories(&self, categories: &[String]) -> AppResult<()> {
        if categories.is_empty() {
            return Err(AppError::message("at least one exact-15 category must be selected"));
        }
        if !self.category_catalog.contains_all(categories) {
            return Err(AppError::message(
                "one or more requested categories do not exist in the exact-15 AudioSep catalog",
            ));
        }
        Ok(())
    }

    pub fn make_processor(&self) -> AppResult<SuppressionProcessor> {
        let runtime = self.runtime()?;
        Ok(SuppressionProcessor {
            runtime,
            category_catalog: self.category_catalog.clone(),
            masker: WienerMasker::default(),
        })
    }

    pub fn runtime_info(&self) -> EngineRuntimeInfo {
        let runtime = self.runtime.lock();
        EngineRuntimeInfo {
            provider: "cpu".to_string(),
            available_providers: vec!["cpu".to_string()],
            warmed: runtime.is_some(),
            model_path: runtime.as_ref().map(|runtime| runtime.model_path.clone()),
        }
    }

    fn runtime(&self) -> AppResult<Arc<InferenceRuntime>> {
        let mut guard = self.runtime.lock();
        if let Some(runtime) = guard.as_ref() {
            return Ok(Arc::clone(runtime));
        }

        let runtime = Arc::new(InferenceRuntime::new(
            &self.assets,
            self.category_catalog
                .categories
                .iter()
                .map(|category| category.id.clone())
                .collect(),
        )?);
        *guard = Some(Arc::clone(&runtime));
        Ok(runtime)
    }
}

impl SuppressionProcessor {
    pub fn process_offline<F>(
        &mut self,
        audio: &DecodedAudio,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
        progress: &mut F,
    ) -> AppResult<DecodedAudio>
    where
        F: FnMut(f32),
    {
        let frame_count = audio.frame_count();
        let chunk_size = (audio.sample_rate as f32 * OUTER_CHUNK_SECONDS).round().max(1.0) as usize;
        let overlap = (audio.sample_rate as f32 * OVERLAP_SECONDS).round().max(0.0) as usize;
        let step = chunk_size.saturating_sub(overlap).max(1);

        let mut clean_channels = vec![vec![0.0f32; frame_count]; audio.channel_count().max(1)];
        let mut weights = vec![0.0f32; frame_count];
        let mut chunk_starts = Vec::new();
        let mut start = 0usize;
        while start < frame_count.max(1) {
            chunk_starts.push(start);
            if start + chunk_size >= frame_count {
                break;
            }
            start += step;
        }
        if chunk_starts.is_empty() {
            chunk_starts.push(0);
        }

        for (chunk_index, start) in chunk_starts.iter().copied().enumerate() {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }

            let end = (start + chunk_size).min(frame_count);
            let mono_chunk = audio.mono_range(start, end);
            let original_chunk = audio.channel_chunk(start, end);
            let clean_mono = self.suppress_mono(&mono_chunk, audio.sample_rate, categories, aggressiveness, cancel_flag)?;
            let chunk_window = build_overlap_window(clean_mono.len(), overlap.min(clean_mono.len()), start > 0, end < frame_count);

            if audio.channel_count() <= 1 {
                for (index, sample) in clean_mono.iter().enumerate() {
                    clean_channels[0][start + index] += *sample * chunk_window[index];
                    weights[start + index] += chunk_window[index];
                }
            } else {
                let removed_mono = mono_chunk
                    .iter()
                    .zip(clean_mono.iter())
                    .map(|(mix, clean)| mix - clean)
                    .collect::<Vec<_>>();
                let removed = project_removed_to_channels(&original_chunk, &removed_mono);

                for channel_index in 0..audio.channel_count() {
                    for frame_index in 0..clean_mono.len() {
                        let cleaned = original_chunk[channel_index][frame_index] - removed[channel_index][frame_index];
                        clean_channels[channel_index][start + frame_index] += cleaned * chunk_window[frame_index];
                    }
                }
                for frame_index in 0..clean_mono.len() {
                    weights[start + frame_index] += chunk_window[frame_index];
                }
            }

            progress((chunk_index + 1) as f32 / chunk_starts.len() as f32);
        }

        for channel in &mut clean_channels {
            for (sample, weight) in channel.iter_mut().zip(weights.iter()) {
                if *weight > 1.0e-8 {
                    *sample /= *weight;
                }
            }
        }

        Ok(DecodedAudio::from_channels(audio.sample_rate, clean_channels))
    }

    pub fn suppress_live_mono(
        &mut self,
        mono: &[f32],
        sample_rate: u32,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        self.suppress_mono(mono, sample_rate, categories, aggressiveness, cancel_flag)
    }

    fn suppress_mono(
        &mut self,
        mono: &[f32],
        sample_rate: u32,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        if mono.is_empty() {
            return Ok(Vec::new());
        }
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }

        let peak = mono.iter().fold(1.0f32, |current, sample| current.max(sample.abs()));
        let normalized = mono
            .iter()
            .map(|sample| (*sample / peak).clamp(-1.0, 1.0))
            .collect::<Vec<_>>();
        let resampled = linear_resample(&normalized, sample_rate, TARGET_SAMPLE_RATE);
        let unwanted_resampled = self
            .runtime
            .separate_categories(&resampled, categories, cancel_flag)?;
        let mut unwanted = linear_resample(&unwanted_resampled, TARGET_SAMPLE_RATE, sample_rate);
        unwanted.resize(mono.len(), 0.0);
        unwanted.truncate(mono.len());

        let separation_ratio = rms(&unwanted) / (rms(mono) + 1.0e-8);
        if (1.0e-6..0.18).contains(&separation_ratio) {
            let scale = (0.18 / separation_ratio).min(1.15);
            for sample in &mut unwanted {
                *sample *= scale;
            }
        }

        let mut effective_aggressiveness = aggressiveness.max(1.0);
        let mut has_transient_category = false;
        for category_id in categories {
            if let Some(category) = self.category_catalog.by_id.get(category_id) {
                effective_aggressiveness = effective_aggressiveness.max(category.default_aggressiveness);
                has_transient_category |= category.transient;
            }
        }

        let n_fft = if has_transient_category { 1024 } else { 2048 };
        let dd_alpha = if has_transient_category { 0.92 } else { 0.98 };

        let clean = self.masker.apply(
            mono,
            &unwanted,
            sample_rate,
            n_fft,
            MaskingOptions {
                aggressiveness: effective_aggressiveness,
                dd_alpha,
                mask_floor: 0.07,
                max_suppression_ratio: 0.82,
                speech_dominance_threshold: 2.5,
            },
        )?;

        Ok(clean)
    }
}

impl InferenceRuntime {
    fn new(assets: &AssetCatalog, category_order: Vec<String>) -> AppResult<Self> {
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
        let mut session = builder
            .commit_from_file(&assets.model_path)
            .map_err(|error| AppError::message(error.to_string()))?;

        let warmup_audio = vec![0.0f32; (TARGET_SAMPLE_RATE as f32 * SEGMENT_SECONDS) as usize];
        let _ = Self::run_window_inner(&mut session, &warmup_audio, 0)?;

        Ok(Self {
            session: Mutex::new(session),
            category_order,
            model_path: assets.model_path.display().to_string(),
        })
    }

    fn separate_categories(
        &self,
        audio: &[f32],
        categories: &[String],
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        let mut combined = vec![0.0f32; audio.len()];
        for category in categories {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }

            let category_index = self
                .category_order
                .iter()
                .position(|label| label.eq_ignore_ascii_case(category))
                .ok_or_else(|| AppError::message(format!("unknown model category '{category}'")))?;
            let separated = self.separate_category(audio, category_index, cancel_flag)?;
            for (target, value) in combined.iter_mut().zip(separated.iter()) {
                *target += *value;
            }
        }
        Ok(combined)
    }

    fn separate_category(
        &self,
        audio: &[f32],
        category_index: usize,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        let segment_samples = (TARGET_SAMPLE_RATE as f32 * SEGMENT_SECONDS) as usize;
        let overlap_samples = (TARGET_SAMPLE_RATE as f32 * OVERLAP_SECONDS) as usize;
        if audio.len() <= segment_samples {
            let mut session = self.session.lock();
            return Self::run_window_inner(&mut session, audio, category_index);
        }

        let step = segment_samples.saturating_sub(overlap_samples).max(1);
        let mut separated = vec![0.0f32; audio.len()];
        let mut weights = vec![0.0f32; audio.len()];

        let mut start = 0usize;
        loop {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }

            let end = (start + segment_samples).min(audio.len());
            let window = build_overlap_window(end - start, overlap_samples.min(end - start), start > 0, end < audio.len());
            let chunk_output = {
                let mut session = self.session.lock();
                Self::run_window_inner(&mut session, &audio[start..end], category_index)?
            };

            for index in 0..chunk_output.len() {
                separated[start + index] += chunk_output[index] * window[index];
                weights[start + index] += window[index];
            }

            if end >= audio.len() {
                break;
            }
            start += step;
        }

        for (sample, weight) in separated.iter_mut().zip(weights.iter()) {
            if *weight > 1.0e-8 {
                *sample /= *weight;
            }
        }

        Ok(separated)
    }

    fn run_window_inner(session: &mut Session, chunk: &[f32], category_index: usize) -> AppResult<Vec<f32>> {
        let segment_samples = (TARGET_SAMPLE_RATE as f32 * SEGMENT_SECONDS) as usize;
        let valid_length = chunk.len();
        let mut padded = vec![0.0f32; segment_samples];
        padded[..valid_length.min(segment_samples)].copy_from_slice(&chunk[..valid_length.min(segment_samples)]);

        let mix_view = ArrayView3::from_shape((1, 1, segment_samples), padded.as_slice())
            .map_err(|error| AppError::message(error.to_string()))?;
        let category_value = [category_index as i64];
        let category_view = ArrayView1::from(&category_value[..]);

        let outputs = session.run(ort::inputs![
            "mixture" => TensorRef::from_array_view(mix_view)?,
            "category_idx" => TensorRef::from_array_view(category_view)?,
        ])?;
        let output = outputs[0]
            .try_extract_array::<f32>()
            .map_err(|error| AppError::message(error.to_string()))?;
        let mut separated = output.iter().copied().collect::<Vec<_>>();
        separated.truncate(valid_length);
        Ok(separated)
    }
}

#[cfg(test)]
mod tests {
    use crate::engine::dsp::build_overlap_window;

    #[test]
    fn outer_chunk_overlap_matches_expected_seconds() {
        let sample_rate = 48_000usize;
        let chunk_size = sample_rate * 10;
        let overlap = sample_rate;
        let window = build_overlap_window(chunk_size, overlap, true, true);
        assert_eq!(window.len(), chunk_size);
        assert!(window[0] < 0.001);
        assert!(window[overlap - 1] > 0.9);
    }
}
