pub mod dsp;

use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};

use ndarray::{ArrayView1, ArrayView2, ArrayView3, ArrayView4};
use ort::{
    session::{builder::GraphOptimizationLevel, Session},
    value::TensorRef,
};
use parking_lot::Mutex;

use crate::{
    audio::io::DecodedAudio,
    config::AssetCatalog,
    error::{AppError, AppResult},
    models::{Hive15Preset, ModelCategory},
};

use self::dsp::{
    build_overlap_window, linear_resample, project_removed_to_channels, rms, MaskingOptions,
    WienerMasker,
};

const OUTER_CHUNK_SECONDS: f32 = 10.0;

pub struct SharedEngine {
    assets: AssetCatalog,
    runtime: Mutex<Option<Arc<ModelRuntime>>>,
}

pub struct SuppressionProcessor {
    runtime: Arc<ModelRuntime>,
    category_by_id: HashMap<String, ModelCategory>,
    masker: WienerMasker,
    audiosep_live_buffer: Vec<f32>,
    waveformer_live_states: HashMap<usize, WaveformerStreamState>,
}

enum ModelRuntime {
    AudioSep(AudioSepRuntime),
    Waveformer(WaveformerRuntime),
}

struct AudioSepRuntime {
    session: Mutex<Session>,
    category_order: Vec<String>,
    model_path: String,
    sample_rate: u32,
    segment_samples: usize,
    overlap_samples: usize,
}

struct WaveformerRuntime {
    session: Mutex<Session>,
    category_order: Vec<String>,
    model_path: String,
    sample_rate: u32,
    chunk_samples: usize,
    mix_channels: usize,
    state_shapes: WaveformerStateShapes,
}

#[derive(Clone)]
struct WaveformerStateShapes {
    enc_buf: Vec<usize>,
    dec_buf: Vec<usize>,
    out_buf: Vec<usize>,
}

#[derive(Clone)]
struct WaveformerStreamState {
    enc_buf: Vec<f32>,
    dec_buf: Vec<f32>,
    out_buf: Vec<f32>,
}

#[derive(Clone, Debug)]
pub struct EngineRuntimeInfo {
    pub provider: String,
    pub available_providers: Vec<String>,
    pub warmed: bool,
    pub model_id: String,
    pub model_family: String,
    pub display_name: String,
    pub suppression_strategy: String,
    pub runtime_kind: String,
    pub model_path: Option<String>,
    pub runtime_metadata_paths: Vec<String>,
}

impl SharedEngine {
    pub fn new(assets: AssetCatalog) -> AppResult<Self> {
        Ok(Self {
            assets,
            runtime: Mutex::new(None),
        })
    }

    pub fn warm(&self) -> AppResult<()> {
        self.runtime().map(|_| ())
    }

    pub fn categories(&self) -> &[ModelCategory] {
        &self.assets.categories
    }

    pub fn presets(&self) -> &[Hive15Preset] {
        &self.assets.presets
    }

    pub fn preferred_live_hop_ms(&self) -> u32 {
        self.assets.preferred_live_hop_ms
    }

    pub fn is_streaming_live_runtime(&self) -> bool {
        self.assets.runtime_kind == "onnx_streaming_target_extractor"
    }

    pub fn display_name(&self) -> &str {
        &self.assets.display_name
    }

    pub fn validate_selected_categories(&self, categories: &[String]) -> AppResult<()> {
        if categories.is_empty() {
            return Err(AppError::message("at least one model category must be selected"));
        }
        if !categories
            .iter()
            .all(|category| self.assets.category_by_id.contains_key(category))
        {
            return Err(AppError::message(
                "one or more requested categories do not exist in the active model catalog",
            ));
        }
        Ok(())
    }

    pub fn make_processor(&self) -> AppResult<SuppressionProcessor> {
        let runtime = self.runtime()?;
        Ok(SuppressionProcessor {
            runtime,
            category_by_id: self.assets.category_by_id.clone(),
            masker: WienerMasker::default(),
            audiosep_live_buffer: Vec::new(),
            waveformer_live_states: HashMap::new(),
        })
    }

    pub fn runtime_info(&self) -> EngineRuntimeInfo {
        let runtime = self.runtime.lock();
        EngineRuntimeInfo {
            provider: "cpu".to_string(),
            available_providers: vec!["cpu".to_string()],
            warmed: runtime.is_some(),
            model_id: self.assets.model_id.clone(),
            model_family: self.assets.model_family.clone(),
            display_name: self.assets.display_name.clone(),
            suppression_strategy: self.assets.suppression_strategy.clone(),
            runtime_kind: self.assets.runtime_kind.clone(),
            model_path: runtime.as_ref().map(|runtime| runtime.model_path().to_string()),
            runtime_metadata_paths: self
                .assets
                .runtime_metadata_paths
                .iter()
                .map(|path| path.to_string_lossy().to_string())
                .collect(),
        }
    }

    fn runtime(&self) -> AppResult<Arc<ModelRuntime>> {
        let mut guard = self.runtime.lock();
        if let Some(runtime) = guard.as_ref() {
            return Ok(Arc::clone(runtime));
        }

        let runtime = Arc::new(match self.assets.runtime_kind.as_str() {
            "onnx_category_separator" => {
                ModelRuntime::AudioSep(AudioSepRuntime::new(&self.assets)?)
            }
            "onnx_streaming_target_extractor" => {
                ModelRuntime::Waveformer(WaveformerRuntime::new(&self.assets)?)
            }
            other => {
                return Err(AppError::message(format!(
                    "unsupported desktop runtime kind '{other}'"
                )))
            }
        });
        *guard = Some(Arc::clone(&runtime));
        Ok(runtime)
    }
}

impl ModelRuntime {
    fn model_path(&self) -> &str {
        match self {
            ModelRuntime::AudioSep(runtime) => &runtime.model_path,
            ModelRuntime::Waveformer(runtime) => &runtime.model_path,
        }
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
        match self.runtime.as_ref() {
            ModelRuntime::AudioSep(_) => {
                self.process_offline_audiosep(audio, categories, aggressiveness, cancel_flag, progress)
            }
            ModelRuntime::Waveformer(_) => {
                self.process_offline_waveformer(audio, categories, aggressiveness, cancel_flag, progress)
            }
        }
    }

    pub fn suppress_live_chunk(
        &mut self,
        chunk: &[f32],
        sample_rate: u32,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        match self.runtime.as_ref() {
            ModelRuntime::AudioSep(_) => {
                self.suppress_live_chunk_audiosep(chunk, sample_rate, categories, aggressiveness, cancel_flag)
            }
            ModelRuntime::Waveformer(_) => {
                self.suppress_live_chunk_waveformer(chunk, sample_rate, categories, aggressiveness, cancel_flag)
            }
        }
    }

    fn process_offline_audiosep<F>(
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
        let overlap_seconds = self
            .runtime
            .as_ref()
            .audiosep_runtime()
            .map(|runtime| runtime.overlap_seconds())
            .unwrap_or(1.0);
        let overlap = (audio.sample_rate as f32 * overlap_seconds).round().max(0.0) as usize;
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
            let clean_mono = self.suppress_audiosep_context(
                &mono_chunk,
                audio.sample_rate,
                categories,
                aggressiveness,
                cancel_flag,
            )?;
            let chunk_window = build_overlap_window(
                clean_mono.len(),
                overlap.min(clean_mono.len()),
                start > 0,
                end < frame_count,
            );

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
                        let cleaned =
                            original_chunk[channel_index][frame_index] - removed[channel_index][frame_index];
                        clean_channels[channel_index][start + frame_index] +=
                            cleaned * chunk_window[frame_index];
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

    fn process_offline_waveformer<F>(
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
        let ModelRuntime::Waveformer(runtime) = self.runtime.as_ref() else {
            return Err(AppError::message("waveformer runtime was not available"));
        };
        let mono = audio.mono_range(0, audio.frame_count());
        let peak = mono
            .iter()
            .fold(1.0f32, |current, sample| current.max(sample.abs()));
        let normalized = mono
            .iter()
            .map(|sample| (*sample / peak).clamp(-1.0, 1.0))
            .collect::<Vec<_>>();
        let mut clean_resampled = linear_resample(&normalized, audio.sample_rate, runtime.sample_rate);
        let chunks_per_pass = clean_resampled.len().div_ceil(runtime.chunk_samples).max(1);
        let total_steps = (chunks_per_pass * categories.len().max(1)) as f32;
        let mut completed_steps = 0.0f32;

        for category_id in categories {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }

            let category_index = runtime.category_index(category_id)?;
            let mut state = runtime.new_state();
            let scale = self.effective_aggressiveness(category_id, aggressiveness)
                .clamp(0.5, 2.0);
            clean_resampled = runtime.suppress_audio_with_state(
                &clean_resampled,
                category_index,
                scale,
                &mut state,
                cancel_flag,
                &mut || {
                    completed_steps += 1.0;
                    progress((completed_steps / total_steps).clamp(0.0, 1.0));
                },
            )?;
        }

        let mut clean = linear_resample(&clean_resampled, runtime.sample_rate, audio.sample_rate);
        clean.resize(mono.len(), 0.0);
        clean.truncate(mono.len());
        for sample in &mut clean {
            *sample *= peak;
        }

        if audio.channel_count() <= 1 {
            return Ok(DecodedAudio::from_channels(audio.sample_rate, vec![clean]));
        }

        let original_chunk = audio.channel_chunk(0, audio.frame_count());
        let removed_mono = mono
            .iter()
            .zip(clean.iter())
            .map(|(mix, clean)| mix - clean)
            .collect::<Vec<_>>();
        let removed = project_removed_to_channels(&original_chunk, &removed_mono);
        let mut clean_channels = original_chunk.clone();
        for channel_index in 0..audio.channel_count() {
            for frame_index in 0..clean_channels[channel_index].len() {
                clean_channels[channel_index][frame_index] -= removed[channel_index][frame_index];
            }
        }

        progress(1.0);
        Ok(DecodedAudio::from_channels(audio.sample_rate, clean_channels))
    }

    fn suppress_live_chunk_audiosep(
        &mut self,
        chunk: &[f32],
        sample_rate: u32,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        let ModelRuntime::AudioSep(runtime) = self.runtime.as_ref() else {
            return Err(AppError::message("audiosep runtime was not available"));
        };
        if chunk.is_empty() {
            return Ok(Vec::new());
        }

        self.audiosep_live_buffer.extend_from_slice(chunk);
        let context_samples = (sample_rate as f32
            * runtime.segment_seconds().max(1.0))
            .round() as usize;
        if self.audiosep_live_buffer.len() > context_samples {
            let overflow = self.audiosep_live_buffer.len() - context_samples;
            self.audiosep_live_buffer.drain(0..overflow);
        }

        let context = latest_context(&self.audiosep_live_buffer, context_samples);
        let clean = self.suppress_audiosep_context(
            &context,
            sample_rate,
            categories,
            aggressiveness,
            cancel_flag,
        )?;
        let keep = chunk.len().min(clean.len());
        Ok(clean[clean.len().saturating_sub(keep)..].to_vec())
    }

    fn suppress_live_chunk_waveformer(
        &mut self,
        chunk: &[f32],
        sample_rate: u32,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        let ModelRuntime::Waveformer(runtime) = self.runtime.as_ref() else {
            return Err(AppError::message("waveformer runtime was not available"));
        };
        if chunk.is_empty() {
            return Ok(Vec::new());
        }
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }

        let peak = chunk
            .iter()
            .fold(1.0f32, |current, sample| current.max(sample.abs()));
        let normalized = chunk
            .iter()
            .map(|sample| (*sample / peak).clamp(-1.0, 1.0))
            .collect::<Vec<_>>();
        let mut clean_resampled = linear_resample(&normalized, sample_rate, runtime.sample_rate);

        for category_id in categories {
            let category_index = runtime.category_index(category_id)?;
            let scale = self.effective_aggressiveness(category_id, aggressiveness)
                .clamp(0.5, 2.0);
            let state = self
                .waveformer_live_states
                .entry(category_index)
                .or_insert_with(|| runtime.new_state());
            clean_resampled = runtime.suppress_audio_with_state(
                &clean_resampled,
                category_index,
                scale,
                state,
                cancel_flag,
                &mut || {},
            )?;
        }

        let mut clean = linear_resample(&clean_resampled, runtime.sample_rate, sample_rate);
        clean.resize(chunk.len(), 0.0);
        clean.truncate(chunk.len());
        for sample in &mut clean {
            *sample *= peak;
        }
        Ok(clean)
    }

    fn suppress_audiosep_context(
        &mut self,
        mono: &[f32],
        sample_rate: u32,
        categories: &[String],
        aggressiveness: f32,
        cancel_flag: &AtomicBool,
    ) -> AppResult<Vec<f32>> {
        let ModelRuntime::AudioSep(runtime) = self.runtime.as_ref() else {
            return Err(AppError::message("audiosep runtime was not available"));
        };

        if mono.is_empty() {
            return Ok(Vec::new());
        }
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(AppError::Cancelled);
        }

        let peak = mono
            .iter()
            .fold(1.0f32, |current, sample| current.max(sample.abs()));
        let normalized = mono
            .iter()
            .map(|sample| (*sample / peak).clamp(-1.0, 1.0))
            .collect::<Vec<_>>();
        let resampled = linear_resample(&normalized, sample_rate, runtime.sample_rate);
        let unwanted_resampled = runtime.separate_categories(&resampled, categories, cancel_flag)?;
        let mut unwanted = linear_resample(&unwanted_resampled, runtime.sample_rate, sample_rate);
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
            if let Some(category) = self.category_by_id.get(category_id) {
                effective_aggressiveness =
                    effective_aggressiveness.max(category.default_aggressiveness);
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

    fn effective_aggressiveness(&self, category_id: &str, base_aggressiveness: f32) -> f32 {
        self.category_by_id
            .get(category_id)
            .map(|category| base_aggressiveness.max(category.default_aggressiveness))
            .unwrap_or(base_aggressiveness.max(1.0))
    }
}

impl AudioSepRuntime {
    fn new(assets: &AssetCatalog) -> AppResult<Self> {
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

        let segment_seconds = assets.segment_seconds.unwrap_or(5.0);
        let sample_rate = assets.sample_rate;
        let warmup_audio = vec![0.0f32; (sample_rate as f32 * segment_seconds) as usize];
        let _ = Self::run_window_inner(
            &mut session,
            &warmup_audio,
            0,
            sample_rate,
            segment_seconds,
        )?;

        Ok(Self {
            session: Mutex::new(session),
            category_order: assets.categories.iter().map(|category| category.id.clone()).collect(),
            model_path: assets.model_path.display().to_string(),
            sample_rate,
            segment_samples: (sample_rate as f32 * segment_seconds) as usize,
            overlap_samples: (sample_rate as f32 * assets.overlap_seconds.unwrap_or(1.0)) as usize,
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

            let category_index = self.category_index(category)?;
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
        if audio.len() <= self.segment_samples {
            let mut session = self.session.lock();
            return Self::run_window_inner(
                &mut session,
                audio,
                category_index,
                self.sample_rate,
                self.segment_seconds(),
            );
        }

        let step = self.segment_samples.saturating_sub(self.overlap_samples).max(1);
        let mut separated = vec![0.0f32; audio.len()];
        let mut weights = vec![0.0f32; audio.len()];

        let mut start = 0usize;
        loop {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }

            let end = (start + self.segment_samples).min(audio.len());
            let window = build_overlap_window(
                end - start,
                self.overlap_samples.min(end - start),
                start > 0,
                end < audio.len(),
            );
            let chunk_output = {
                let mut session = self.session.lock();
                Self::run_window_inner(
                    &mut session,
                    &audio[start..end],
                    category_index,
                    self.sample_rate,
                    self.segment_seconds(),
                )?
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

    fn category_index(&self, category: &str) -> AppResult<usize> {
        self.category_order
            .iter()
            .position(|label| label.eq_ignore_ascii_case(category))
            .ok_or_else(|| AppError::message(format!("unknown model category '{category}'")))
    }

    fn overlap_seconds(&self) -> f32 {
        self.overlap_samples as f32 / self.sample_rate as f32
    }

    fn segment_seconds(&self) -> f32 {
        self.segment_samples as f32 / self.sample_rate as f32
    }

    fn run_window_inner(
        session: &mut Session,
        chunk: &[f32],
        category_index: usize,
        sample_rate: u32,
        segment_seconds: f32,
    ) -> AppResult<Vec<f32>> {
        let segment_samples = (sample_rate as f32 * segment_seconds) as usize;
        let valid_length = chunk.len();
        let mut padded = vec![0.0f32; segment_samples];
        padded[..valid_length.min(segment_samples)]
            .copy_from_slice(&chunk[..valid_length.min(segment_samples)]);

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

impl WaveformerRuntime {
    fn new(assets: &AssetCatalog) -> AppResult<Self> {
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
            .commit_from_file(&assets.model_path)
            .map_err(|error| AppError::message(error.to_string()))?;

        let state_shapes = WaveformerStateShapes::from_assets(assets)?;
        let runtime = Self {
            session: Mutex::new(session),
            category_order: assets.categories.iter().map(|category| category.id.clone()).collect(),
            model_path: assets.model_path.display().to_string(),
            sample_rate: assets.sample_rate,
            chunk_samples: assets.chunk_samples.unwrap_or(0),
            mix_channels: assets.mix_channels.max(1),
            state_shapes,
        };

        let mut state = runtime.new_state();
        let warmup_audio = vec![0.0f32; runtime.chunk_samples];
        {
            let mut locked = runtime.session.lock();
            let _ = runtime.run_chunk_inner(&mut locked, &warmup_audio, 0, &mut state)?;
        }

        Ok(runtime)
    }

    fn category_index(&self, category: &str) -> AppResult<usize> {
        self.category_order
            .iter()
            .position(|label| label.eq_ignore_ascii_case(category))
            .ok_or_else(|| AppError::message(format!("unknown model category '{category}'")))
    }

    fn new_state(&self) -> WaveformerStreamState {
        self.state_shapes.zero_state()
    }

    fn suppress_audio_with_state<F>(
        &self,
        audio: &[f32],
        category_index: usize,
        scale: f32,
        state: &mut WaveformerStreamState,
        cancel_flag: &AtomicBool,
        on_chunk: &mut F,
    ) -> AppResult<Vec<f32>>
    where
        F: FnMut(),
    {
        let mut clean = Vec::with_capacity(audio.len());
        let mut session = self.session.lock();
        let mut start = 0usize;
        while start < audio.len().max(1) {
            if cancel_flag.load(Ordering::Relaxed) {
                return Err(AppError::Cancelled);
            }
            let end = (start + self.chunk_samples).min(audio.len());
            let chunk = &audio[start..end];
            let target = self.run_chunk_inner(&mut session, chunk, category_index, state)?;
            for (mix, extracted) in chunk.iter().zip(target.iter()) {
                clean.push((mix - scale * extracted).clamp(-1.0, 1.0));
            }
            on_chunk();
            if end >= audio.len() {
                break;
            }
            start = end;
        }

        if audio.is_empty() {
            on_chunk();
        }

        Ok(clean)
    }

    fn run_chunk_inner(
        &self,
        session: &mut Session,
        chunk: &[f32],
        category_index: usize,
        state: &mut WaveformerStreamState,
    ) -> AppResult<Vec<f32>> {
        let valid_length = chunk.len();
        let mut mono = vec![0.0f32; self.chunk_samples];
        mono[..valid_length.min(self.chunk_samples)]
            .copy_from_slice(&chunk[..valid_length.min(self.chunk_samples)]);

        let mut stereo = vec![0.0f32; self.mix_channels * self.chunk_samples];
        for channel in 0..self.mix_channels {
            let offset = channel * self.chunk_samples;
            stereo[offset..offset + self.chunk_samples].copy_from_slice(&mono);
        }

        let mut label = vec![0.0f32; self.category_order.len()];
        if let Some(value) = label.get_mut(category_index) {
            *value = 1.0;
        }

        let mixture_view = ArrayView3::from_shape(
            (1, self.mix_channels, self.chunk_samples),
            stereo.as_slice(),
        )
        .map_err(|error| AppError::message(error.to_string()))?;
        let label_view = ArrayView2::from_shape((1, self.category_order.len()), label.as_slice())
            .map_err(|error| AppError::message(error.to_string()))?;
        let enc_view = ArrayView3::from_shape(
            (
                self.state_shapes.enc_buf[0],
                self.state_shapes.enc_buf[1],
                self.state_shapes.enc_buf[2],
            ),
            state.enc_buf.as_slice(),
        )
        .map_err(|error| AppError::message(error.to_string()))?;
        let dec_view = ArrayView4::from_shape(
            (
                self.state_shapes.dec_buf[0],
                self.state_shapes.dec_buf[1],
                self.state_shapes.dec_buf[2],
                self.state_shapes.dec_buf[3],
            ),
            state.dec_buf.as_slice(),
        )
        .map_err(|error| AppError::message(error.to_string()))?;
        let out_view = ArrayView3::from_shape(
            (
                self.state_shapes.out_buf[0],
                self.state_shapes.out_buf[1],
                self.state_shapes.out_buf[2],
            ),
            state.out_buf.as_slice(),
        )
        .map_err(|error| AppError::message(error.to_string()))?;

        let outputs = session.run(ort::inputs![
            "mixture" => TensorRef::from_array_view(mixture_view)?,
            "label_vector" => TensorRef::from_array_view(label_view)?,
            "enc_buf" => TensorRef::from_array_view(enc_view)?,
            "dec_buf" => TensorRef::from_array_view(dec_view)?,
            "out_buf" => TensorRef::from_array_view(out_view)?,
        ])?;

        let target = outputs[0]
            .try_extract_array::<f32>()
            .map_err(|error| AppError::message(error.to_string()))?
            .iter()
            .copied()
            .collect::<Vec<_>>();
        let enc_buf = outputs[1]
            .try_extract_array::<f32>()
            .map_err(|error| AppError::message(error.to_string()))?
            .iter()
            .copied()
            .collect::<Vec<_>>();
        let dec_buf = outputs[2]
            .try_extract_array::<f32>()
            .map_err(|error| AppError::message(error.to_string()))?
            .iter()
            .copied()
            .collect::<Vec<_>>();
        let out_buf = outputs[3]
            .try_extract_array::<f32>()
            .map_err(|error| AppError::message(error.to_string()))?
            .iter()
            .copied()
            .collect::<Vec<_>>();

        state.enc_buf = enc_buf;
        state.dec_buf = dec_buf;
        state.out_buf = out_buf;

        let mut target_mono = vec![0.0f32; valid_length];
        for sample_index in 0..valid_length {
            let mut sum = 0.0f32;
            for channel in 0..self.mix_channels {
                let offset = channel * self.chunk_samples;
                sum += target[offset + sample_index];
            }
            target_mono[sample_index] = sum / self.mix_channels as f32;
        }
        Ok(target_mono)
    }
}

impl WaveformerStateShapes {
    fn from_assets(assets: &AssetCatalog) -> AppResult<Self> {
        let enc_buf = assets
            .state_tensors
            .get("enc_buf")
            .cloned()
            .ok_or_else(|| AppError::message("waveformer desktop config is missing enc_buf shape"))?;
        let dec_buf = assets
            .state_tensors
            .get("dec_buf")
            .cloned()
            .ok_or_else(|| AppError::message("waveformer desktop config is missing dec_buf shape"))?;
        let out_buf = assets
            .state_tensors
            .get("out_buf")
            .cloned()
            .ok_or_else(|| AppError::message("waveformer desktop config is missing out_buf shape"))?;

        if enc_buf.len() != 3 || dec_buf.len() != 4 || out_buf.len() != 3 {
            return Err(AppError::message("waveformer state tensor ranks are invalid"));
        }

        Ok(Self {
            enc_buf,
            dec_buf,
            out_buf,
        })
    }

    fn zero_state(&self) -> WaveformerStreamState {
        WaveformerStreamState {
            enc_buf: vec![0.0; self.enc_buf.iter().product()],
            dec_buf: vec![0.0; self.dec_buf.iter().product()],
            out_buf: vec![0.0; self.out_buf.iter().product()],
        }
    }
}

impl ModelRuntime {
    fn audiosep_runtime(&self) -> Option<&AudioSepRuntime> {
        match self {
            ModelRuntime::AudioSep(runtime) => Some(runtime),
            ModelRuntime::Waveformer(_) => None,
        }
    }
}

fn latest_context(rolling_input: &[f32], context_samples: usize) -> Vec<f32> {
    if rolling_input.len() >= context_samples {
        return rolling_input[rolling_input.len() - context_samples..].to_vec();
    }

    let mut context = vec![0.0f32; context_samples];
    let offset = context_samples - rolling_input.len();
    context[offset..].copy_from_slice(rolling_input);
    context
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
