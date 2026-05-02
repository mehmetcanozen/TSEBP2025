use std::{collections::HashMap, sync::Arc};

use realfft::{num_complex::Complex32, ComplexToReal, RealFftPlanner, RealToComplex};
use rubato::{
    Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction,
};

use crate::error::{AppError, AppResult};

#[derive(Clone, Copy, Debug)]
pub struct MaskingOptions {
    pub aggressiveness: f32,
    pub dd_alpha: f32,
    pub mask_floor: f32,
    pub max_suppression_ratio: f32,
    pub speech_dominance_threshold: f32,
}

pub struct WienerMasker {
    plans: HashMap<usize, StftPlan>,
    prev_clean_power: Option<Vec<f32>>,
    prev_noise_power: Option<Vec<f32>>,
}

struct StftPlan {
    n_fft: usize,
    hop_size: usize,
    window: Vec<f32>,
    rfft: Arc<dyn RealToComplex<f32>>,
    irfft: Arc<dyn ComplexToReal<f32>>,
}

pub struct StreamingSincResampler {
    source_rate: u32,
    target_rate: u32,
    max_input_frames: usize,
    resampler: Option<SincFixedIn<f32>>,
}

impl Default for WienerMasker {
    fn default() -> Self {
        Self {
            plans: HashMap::new(),
            prev_clean_power: None,
            prev_noise_power: None,
        }
    }
}

impl WienerMasker {
    pub fn apply(
        &mut self,
        mix: &[f32],
        unwanted: &[f32],
        sample_rate: u32,
        n_fft: usize,
        options: MaskingOptions,
    ) -> AppResult<Vec<f32>> {
        let min_len = mix.len().min(unwanted.len());
        if min_len == 0 {
            return Ok(Vec::new());
        }

        let mix = &mix[..min_len];
        let unwanted = &unwanted[..min_len];
        let (mix_frames, unwanted_frames, freq_bins) = {
            let plan = self.plan_for(n_fft);
            let mix_frames = stft(mix, plan)?;
            let unwanted_frames = stft(unwanted, plan)?;
            let freq_bins = mix_frames[0].len();
            (mix_frames, unwanted_frames, freq_bins)
        };
        let frame_count = mix_frames.len().min(unwanted_frames.len());
        if frame_count == 0 {
            return Ok(vec![0.0; min_len]);
        }

        if self.prev_clean_power.as_ref().map(|value| value.len()) != Some(freq_bins) {
            self.prev_clean_power = Some(vec![0.0; freq_bins]);
            self.prev_noise_power = Some(vec![1.0e-10; freq_bins]);
        }
        let prev_clean = self
            .prev_clean_power
            .as_mut()
            .expect("masker state initialized");
        let prev_noise = self
            .prev_noise_power
            .as_mut()
            .expect("masker state initialized");

        let perceptual_floor = build_perceptual_floor(freq_bins, sample_rate, 0.01, 0.05);
        let mut clean_frames = Vec::with_capacity(frame_count);
        let eps = 1.0e-10f32;

        for frame_index in 0..frame_count {
            let mix_frame = &mix_frames[frame_index];
            let unwanted_frame = &unwanted_frames[frame_index];
            let mut clean_frame = vec![Complex32::new(0.0, 0.0); freq_bins];

            for bin in 0..freq_bins {
                let mix_value = mix_frame[bin];
                let unwanted_value = unwanted_frame[bin];
                let mag_mix = mix_value.norm();
                let limited_unwanted = unwanted_value
                    .norm()
                    .min(options.max_suppression_ratio * (mag_mix + eps));
                let mix_power = mag_mix * mag_mix;
                let noise_power = limited_unwanted * limited_unwanted + eps;

                let gamma = mix_power / noise_power;
                let gamma_minus_one = (gamma - 1.0).max(0.0);
                let snr_prior = prev_clean[bin] / prev_noise[bin].max(eps);
                let xi = options.dd_alpha * snr_prior + (1.0 - options.dd_alpha) * gamma_minus_one;
                let mut gain = xi / (options.aggressiveness + xi);

                let floor = perceptual_floor[bin].max(options.mask_floor);
                let dominance = mix_power / noise_power.max(eps);
                if dominance >= options.speech_dominance_threshold {
                    let preserve_bias = ((dominance - options.speech_dominance_threshold)
                        / options.speech_dominance_threshold.max(eps))
                    .clamp(0.0, 1.0);
                    gain = gain.max((floor + 0.18 * preserve_bias).clamp(floor, 1.0));
                }

                gain = gain.clamp(floor, 1.0);
                prev_clean[bin] = gain * gain * mix_power;
                prev_noise[bin] = noise_power;

                clean_frame[bin] = mix_value * gain;
            }

            // Real FFT inverse requires DC and Nyquist bins to remain purely real.
            clean_frame[0].im = 0.0;
            if freq_bins > 1 {
                clean_frame[freq_bins - 1].im = 0.0;
            }

            clean_frames.push(clean_frame);
        }

        let plan = self.plan_for(n_fft);
        istft(&clean_frames, plan, min_len)
    }

    fn plan_for(&mut self, n_fft: usize) -> &StftPlan {
        self.plans.entry(n_fft).or_insert_with(|| {
            let mut planner = RealFftPlanner::<f32>::new();
            let rfft = planner.plan_fft_forward(n_fft);
            let irfft = planner.plan_fft_inverse(n_fft);

            let window = (0..n_fft)
                .map(|index| {
                    let angle = 2.0 * std::f32::consts::PI * index as f32 / n_fft as f32;
                    0.5 - 0.5 * angle.cos()
                })
                .collect::<Vec<_>>();

            StftPlan {
                n_fft,
                hop_size: n_fft / 2,
                window,
                rfft,
                irfft,
            }
        })
    }
}

pub fn linear_resample(audio: &[f32], source_rate: u32, target_rate: u32) -> Vec<f32> {
    if audio.is_empty() || source_rate == target_rate {
        return audio.to_vec();
    }

    let scale = target_rate as f64 / source_rate as f64;
    let target_len = ((audio.len() as f64) * scale).round().max(1.0) as usize;
    let mut output = vec![0.0f32; target_len];

    for (index, sample) in output.iter_mut().enumerate() {
        let position = index as f64 / scale;
        let left = position.floor() as usize;
        let right = (left + 1).min(audio.len().saturating_sub(1));
        let frac = (position - left as f64) as f32;
        let left_sample = audio[left];
        let right_sample = audio[right];
        *sample = left_sample + (right_sample - left_sample) * frac;
    }

    output
}

pub fn sinc_resample(audio: &[f32], source_rate: u32, target_rate: u32) -> AppResult<Vec<f32>> {
    let expected_len = expected_resampled_len(audio.len(), source_rate, target_rate);
    sinc_resample_to_len(audio, source_rate, target_rate, expected_len)
}

pub fn sinc_resample_to_len(
    audio: &[f32],
    source_rate: u32,
    target_rate: u32,
    output_len: usize,
) -> AppResult<Vec<f32>> {
    if audio.is_empty() {
        return Ok(vec![0.0; output_len]);
    }
    if source_rate == target_rate {
        let mut copy = audio.to_vec();
        fit_resampled_length(&mut copy, output_len);
        return Ok(copy);
    }

    let mut resampler = StreamingSincResampler::new(source_rate, target_rate, audio.len())?;
    resampler.process_to_len(audio, output_len)
}

impl StreamingSincResampler {
    pub fn new(source_rate: u32, target_rate: u32, max_input_frames: usize) -> AppResult<Self> {
        let mut instance = Self {
            source_rate,
            target_rate,
            max_input_frames: max_input_frames.max(1),
            resampler: None,
        };
        instance.rebuild(instance.max_input_frames)?;
        Ok(instance)
    }

    pub fn matches(&self, source_rate: u32, target_rate: u32, max_input_frames: usize) -> bool {
        self.source_rate == source_rate
            && self.target_rate == target_rate
            && self.max_input_frames >= max_input_frames.max(1)
    }

    pub fn process(&mut self, audio: &[f32]) -> AppResult<Vec<f32>> {
        if audio.is_empty() {
            return Ok(Vec::new());
        }
        if self.source_rate == self.target_rate {
            return Ok(audio.to_vec());
        }
        if audio.len() > self.max_input_frames {
            self.rebuild(audio.len())?;
        }

        let resampler = self
            .resampler
            .as_mut()
            .ok_or_else(|| AppError::message("sinc resampler was not initialized"))?;
        resampler
            .set_chunk_size(audio.len())
            .map_err(|error| AppError::message(error.to_string()))?;
        let input = vec![audio.to_vec()];
        let mut output = resampler
            .process(&input, None)
            .map_err(|error| AppError::message(error.to_string()))?;
        Ok(output.pop().unwrap_or_default())
    }

    pub fn process_to_len(&mut self, audio: &[f32], output_len: usize) -> AppResult<Vec<f32>> {
        let mut output = self.process(audio)?;
        fit_resampled_length(&mut output, output_len);
        Ok(output)
    }

    fn rebuild(&mut self, max_input_frames: usize) -> AppResult<()> {
        self.max_input_frames = max_input_frames.max(1);
        if self.source_rate == self.target_rate {
            self.resampler = None;
            return Ok(());
        }

        let params = SincInterpolationParameters {
            sinc_len: 64,
            f_cutoff: 0.95,
            interpolation: SincInterpolationType::Linear,
            oversampling_factor: 64,
            window: WindowFunction::BlackmanHarris2,
        };
        let ratio = self.target_rate as f64 / self.source_rate as f64;
        let resampler = SincFixedIn::<f32>::new(ratio, 1.0, params, self.max_input_frames, 1)
            .map_err(|error| AppError::message(error.to_string()))?;
        self.resampler = Some(resampler);
        Ok(())
    }
}

pub fn expected_resampled_len(input_len: usize, source_rate: u32, target_rate: u32) -> usize {
    if input_len == 0 {
        return 0;
    }
    if source_rate == target_rate {
        return input_len;
    }
    ((input_len as f64) * target_rate as f64 / source_rate as f64)
        .round()
        .max(1.0) as usize
}

pub fn fit_resampled_length(audio: &mut Vec<f32>, output_len: usize) {
    if audio.len() > output_len {
        audio.truncate(output_len);
    } else if audio.len() < output_len {
        let fill = audio.last().copied().unwrap_or_default();
        audio.resize(output_len, fill);
    }
}

pub fn build_overlap_window(
    length: usize,
    overlap_samples: usize,
    fade_in: bool,
    fade_out: bool,
) -> Vec<f32> {
    let mut window = vec![1.0f32; length];
    let overlap = overlap_samples.min(length);
    if overlap == 0 {
        return window;
    }

    for index in 0..overlap {
        let ramp = index as f32 / overlap as f32;
        if fade_in {
            window[index] = ramp;
        }
        if fade_out {
            let target = length - overlap + index;
            window[target] = window[target].min(1.0 - ramp);
        }
    }

    window
}

pub fn project_removed_to_channels(
    original_channels: &[Vec<f32>],
    removed_mono: &[f32],
) -> Vec<Vec<f32>> {
    if original_channels.is_empty() {
        return Vec::new();
    }
    let channel_count = original_channels.len();
    let frame_count = removed_mono.len();
    let mut projected = vec![vec![0.0f32; frame_count]; channel_count];

    for frame_index in 0..frame_count {
        let mut energy_sum = 0.0f32;
        for channel in original_channels {
            if let Some(sample) = channel.get(frame_index) {
                energy_sum += sample.abs();
            }
        }

        for (channel_index, channel) in original_channels.iter().enumerate() {
            let weight = if energy_sum > 1.0e-8 {
                channel.get(frame_index).copied().unwrap_or(0.0).abs() / energy_sum
            } else {
                1.0 / channel_count as f32
            };
            projected[channel_index][frame_index] =
                removed_mono[frame_index] * weight * channel_count as f32;
        }
    }

    projected
}

pub fn rms(signal: &[f32]) -> f32 {
    if signal.is_empty() {
        return 0.0;
    }
    let energy = signal.iter().map(|sample| sample * sample).sum::<f32>() / signal.len() as f32;
    energy.sqrt()
}

pub fn peak(signal: &[f32]) -> f32 {
    signal
        .iter()
        .fold(0.0f32, |current, sample| current.max(sample.abs()))
}

pub fn waveform_summary(signal: &[f32], bins: usize) -> Vec<f32> {
    if signal.is_empty() || bins == 0 {
        return Vec::new();
    }

    let mut summary = Vec::with_capacity(bins);
    let chunk_size = ((signal.len() as f32) / bins as f32).ceil() as usize;
    for chunk in signal.chunks(chunk_size.max(1)).take(bins) {
        let value = if chunk.is_empty() {
            0.0
        } else {
            chunk.iter().map(|sample| sample.abs()).sum::<f32>() / chunk.len() as f32
        };
        summary.push(value);
    }
    while summary.len() < bins {
        summary.push(0.0);
    }
    summary
}

fn stft(signal: &[f32], plan: &StftPlan) -> AppResult<Vec<Vec<Complex32>>> {
    let starts = frame_starts(signal.len(), plan.n_fft, plan.hop_size);
    let mut frames = Vec::with_capacity(starts.len());

    for start in starts {
        let mut input = vec![0.0f32; plan.n_fft];
        let available = signal.len().saturating_sub(start).min(plan.n_fft);
        if available > 0 {
            input[..available].copy_from_slice(&signal[start..start + available]);
        }
        for (sample, window) in input.iter_mut().zip(plan.window.iter()) {
            *sample *= *window;
        }

        let mut spectrum = plan.rfft.make_output_vec();
        plan.rfft
            .process(&mut input, &mut spectrum)
            .map_err(|error| AppError::message(error.to_string()))?;
        frames.push(spectrum);
    }

    Ok(frames)
}

fn istft(frames: &[Vec<Complex32>], plan: &StftPlan, output_len: usize) -> AppResult<Vec<f32>> {
    if frames.is_empty() {
        return Ok(vec![0.0; output_len]);
    }

    let total_len = plan.hop_size * frames.len().saturating_sub(1) + plan.n_fft;
    let mut output = vec![0.0f32; total_len];
    let mut norm = vec![0.0f32; total_len];

    for (frame_index, frame) in frames.iter().enumerate() {
        let mut spectrum = frame.clone();
        let mut time = plan.irfft.make_output_vec();
        plan.irfft
            .process(&mut spectrum, &mut time)
            .map_err(|error| AppError::message(error.to_string()))?;

        let start = frame_index * plan.hop_size;
        for sample_index in 0..plan.n_fft {
            let value = time[sample_index] / plan.n_fft as f32;
            let weighted = value * plan.window[sample_index];
            output[start + sample_index] += weighted;
            norm[start + sample_index] += plan.window[sample_index] * plan.window[sample_index];
        }
    }

    for (sample, weight) in output.iter_mut().zip(norm.iter()) {
        if *weight > 1.0e-8 {
            *sample /= *weight;
        }
    }

    output.resize(output_len, 0.0);
    output.truncate(output_len);
    Ok(output)
}

fn frame_starts(signal_len: usize, n_fft: usize, hop_size: usize) -> Vec<usize> {
    if signal_len == 0 || signal_len <= n_fft {
        return vec![0];
    }

    let mut starts = Vec::new();
    let mut start = 0usize;
    loop {
        starts.push(start);
        if start + n_fft >= signal_len {
            break;
        }
        start += hop_size.max(1);
    }
    starts
}

fn build_perceptual_floor(
    freq_bins: usize,
    sample_rate: u32,
    floor_min: f32,
    floor_max: f32,
) -> Vec<f32> {
    let mut floor = vec![floor_min; freq_bins];
    let f_low = 200.0f32;
    let f_peak = 2500.0f32;
    let f_high = 10_000.0f32;
    let nyquist = sample_rate as f32 / 2.0;

    for (index, value) in floor.iter_mut().enumerate() {
        let frequency = index as f32 / (freq_bins.saturating_sub(1).max(1)) as f32 * nyquist;
        if frequency < f_low || frequency > f_high {
            *value = floor_min;
        } else if frequency <= f_peak {
            let t = (frequency - f_low) / (f_peak - f_low);
            *value = floor_min + t * (floor_max - floor_min);
        } else {
            let t = (frequency - f_peak) / (f_high - f_peak);
            *value = floor_max - t * (floor_max - floor_min);
        }
    }

    floor
}

#[cfg(test)]
mod tests {
    use super::{
        build_overlap_window, linear_resample, peak, project_removed_to_channels, rms,
        sinc_resample_to_len, MaskingOptions, StreamingSincResampler, WienerMasker,
    };

    #[test]
    fn overlap_window_fades_cleanly() {
        let window = build_overlap_window(8, 4, true, true);
        assert_eq!(window.len(), 8);
        assert!(window[0] < 0.01);
        assert!(window[3] > window[1]);
        assert!(window[7] < 0.26);
    }

    #[test]
    fn linear_resample_preserves_edges() {
        let input = vec![0.0f32, 1.0, 0.0, -1.0];
        let output = linear_resample(&input, 4, 8);
        assert_eq!(output.first().copied().unwrap_or_default(), 0.0);
        assert!(output.len() >= 7);
    }

    #[test]
    fn sinc_resample_to_len_returns_requested_shape() {
        let input = (0..4807)
            .map(|index| ((index as f32) * 0.01).sin())
            .collect::<Vec<_>>();
        let output =
            sinc_resample_to_len(&input, 48_000, 44_100, 4416).expect("sinc resample should run");
        assert_eq!(output.len(), 4416);
        assert!(output.iter().all(|sample| sample.is_finite()));
    }

    #[test]
    fn streaming_sinc_resampler_reuses_state_for_live_chunks() {
        let mut resampler =
            StreamingSincResampler::new(48_000, 44_100, 4807).expect("resampler should construct");
        let input = vec![0.0f32; 4807];
        let output = resampler
            .process_to_len(&input, 4416)
            .expect("resampler should process");
        assert_eq!(output.len(), 4416);
        assert!(resampler.matches(48_000, 44_100, 4807));
    }

    #[test]
    fn projected_removed_audio_keeps_shape() {
        let original = vec![vec![0.5, 0.2], vec![0.5, 0.8]];
        let removed = vec![0.4f32, 0.4];
        let projected = project_removed_to_channels(&original, &removed);
        assert_eq!(projected.len(), 2);
        assert_eq!(projected[0].len(), 2);
        assert!((rms(&projected[0]) + rms(&projected[1])) > 0.0);
        assert!(peak(&projected[1]) > 0.0);
    }

    #[test]
    fn masking_output_remains_valid_for_real_istft() {
        let signal = (0..4096)
            .map(|i| ((i as f32) * 0.01).sin() * 0.4)
            .collect::<Vec<_>>();
        let unwanted = signal.iter().map(|sample| sample * 0.3).collect::<Vec<_>>();
        let mut masker = WienerMasker::default();
        let clean = masker
            .apply(
                &signal,
                &unwanted,
                32_000,
                1024,
                MaskingOptions {
                    aggressiveness: 1.5,
                    dd_alpha: 0.98,
                    mask_floor: 0.07,
                    max_suppression_ratio: 0.82,
                    speech_dominance_threshold: 2.5,
                },
            )
            .expect("masking should produce a valid real-valued signal");
        assert_eq!(clean.len(), signal.len());
        assert!(peak(&clean) > 0.0);
    }
}
