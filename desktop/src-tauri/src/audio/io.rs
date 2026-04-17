use std::{
    fs::File,
    path::Path,
};

use hound::{SampleFormat, WavSpec, WavWriter};
use symphonia::core::{
    audio::SampleBuffer,
    codecs::{DecoderOptions, CODEC_TYPE_NULL},
    errors::Error as SymphoniaError,
    formats::FormatOptions,
    io::MediaSourceStream,
    meta::MetadataOptions,
    probe::Hint,
};

use crate::error::{AppError, AppResult};

#[derive(Clone, Debug)]
pub struct DecodedAudio {
    pub sample_rate: u32,
    pub channels: Vec<Vec<f32>>,
}

impl DecodedAudio {
    pub fn from_channels(sample_rate: u32, channels: Vec<Vec<f32>>) -> Self {
        Self { sample_rate, channels }
    }

    pub fn frame_count(&self) -> usize {
        self.channels.first().map(|channel| channel.len()).unwrap_or(0)
    }

    pub fn channel_count(&self) -> usize {
        self.channels.len()
    }

    pub fn mono_range(&self, start: usize, end: usize) -> Vec<f32> {
        let end = end.min(self.frame_count());
        let start = start.min(end);
        let length = end.saturating_sub(start);
        if self.channels.is_empty() {
            return vec![0.0; length];
        }

        let mut mono = vec![0.0f32; length];
        for channel in &self.channels {
            for (index, sample) in channel[start..end].iter().enumerate() {
                mono[index] += *sample;
            }
        }
        let scale = 1.0f32 / self.channels.len() as f32;
        for sample in &mut mono {
            *sample *= scale;
        }
        mono
    }

    pub fn channel_chunk(&self, start: usize, end: usize) -> Vec<Vec<f32>> {
        let end = end.min(self.frame_count());
        let start = start.min(end);
        self.channels
            .iter()
            .map(|channel| channel[start..end].to_vec())
            .collect()
    }
}

pub fn decode_audio_file(path: &Path) -> AppResult<DecodedAudio> {
    let file = File::open(path)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());

    let mut hint = Hint::new();
    if let Some(extension) = path.extension().and_then(|value| value.to_str()) {
        hint.with_extension(extension);
    }

    let probed = symphonia::default::get_probe().format(
        &hint,
        mss,
        &FormatOptions::default(),
        &MetadataOptions::default(),
    )?;
    let mut format = probed.format;
    let track = format
        .default_track()
        .or_else(|| format.tracks().iter().find(|track| track.codec_params.codec != CODEC_TYPE_NULL))
        .ok_or_else(|| AppError::message(format!("no decodable audio track found in '{}'", path.display())))?;

    let mut decoder = symphonia::default::get_codecs().make(&track.codec_params, &DecoderOptions::default())?;
    let track_id = track.id;

    let mut sample_rate = track.codec_params.sample_rate.unwrap_or(0);
    let mut channel_count = track.codec_params.channels.map(|channels| channels.count()).unwrap_or(0);
    let mut interleaved = Vec::<f32>::new();

    loop {
        let packet = match format.next_packet() {
            Ok(packet) => packet,
            Err(SymphoniaError::IoError(error)) if error.kind() == std::io::ErrorKind::UnexpectedEof => break,
            Err(error) => return Err(error.into()),
        };

        if packet.track_id() != track_id {
            continue;
        }

        let decoded = match decoder.decode(&packet) {
            Ok(decoded) => decoded,
            Err(SymphoniaError::DecodeError(_)) => continue,
            Err(error) => return Err(error.into()),
        };

        let spec = *decoded.spec();
        sample_rate = sample_rate.max(spec.rate);
        channel_count = channel_count.max(spec.channels.count());

        let mut sample_buffer = SampleBuffer::<f32>::new(decoded.capacity() as u64, spec);
        sample_buffer.copy_interleaved_ref(decoded);
        interleaved.extend_from_slice(sample_buffer.samples());
    }

    if sample_rate == 0 || channel_count == 0 {
        return Err(AppError::message(format!(
            "unable to resolve sample format for '{}'",
            path.display()
        )));
    }

    let frame_count = interleaved.len() / channel_count;
    let mut channels = vec![vec![0.0f32; frame_count]; channel_count];
    for frame_index in 0..frame_count {
        for channel_index in 0..channel_count {
            channels[channel_index][frame_index] = interleaved[frame_index * channel_count + channel_index];
        }
    }

    Ok(DecodedAudio::from_channels(sample_rate, channels))
}

pub fn write_wav_float(path: &Path, audio: &DecodedAudio) -> AppResult<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let spec = WavSpec {
        channels: audio.channel_count() as u16,
        sample_rate: audio.sample_rate,
        bits_per_sample: 32,
        sample_format: SampleFormat::Float,
    };
    let mut writer = WavWriter::create(path, spec).map_err(|error| AppError::message(error.to_string()))?;
    let frames = audio.frame_count();
    let channels = audio.channel_count();

    for frame_index in 0..frames {
        for channel_index in 0..channels {
            writer
                .write_sample(audio.channels[channel_index][frame_index])
                .map_err(|error| AppError::message(error.to_string()))?;
        }
    }

    writer.finalize().map_err(|error| AppError::message(error.to_string()))?;
    Ok(())
}
