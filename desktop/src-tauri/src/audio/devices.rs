use cpal::{
    traits::{DeviceTrait, HostTrait},
    Device, SampleFormat, SupportedStreamConfig,
};

use crate::{
    error::{AppError, AppResult},
    models::{AudioDevice, AudioDeviceDirection},
};

pub struct ResolvedDevice {
    pub descriptor: AudioDevice,
    pub device: Device,
    pub config: SupportedStreamConfig,
}

pub fn list_audio_devices() -> AppResult<Vec<AudioDevice>> {
    let host = cpal::default_host();
    let default_input_name = host.default_input_device().and_then(|device| device.name().ok());
    let default_output_name = host.default_output_device().and_then(|device| device.name().ok());

    let mut devices = Vec::new();
    devices.extend(enumerate_direction(&host, AudioDeviceDirection::Input, default_input_name.as_deref())?);
    devices.extend(enumerate_direction(
        &host,
        AudioDeviceDirection::Output,
        default_output_name.as_deref(),
    )?);
    Ok(devices)
}

pub fn resolve_input_device(selected_id: Option<&str>) -> AppResult<ResolvedDevice> {
    resolve_device(AudioDeviceDirection::Input, selected_id)
}

pub fn resolve_output_device(selected_id: Option<&str>) -> AppResult<ResolvedDevice> {
    resolve_device(AudioDeviceDirection::Output, selected_id)
}

fn resolve_device(direction: AudioDeviceDirection, selected_id: Option<&str>) -> AppResult<ResolvedDevice> {
    let host = cpal::default_host();
    let default_name = match direction {
        AudioDeviceDirection::Input => host.default_input_device().and_then(|device| device.name().ok()),
        AudioDeviceDirection::Output => host.default_output_device().and_then(|device| device.name().ok()),
    };

    let mut index = 0usize;
    let mut fallback: Option<ResolvedDevice> = None;
    let devices = match direction {
        AudioDeviceDirection::Input => host.input_devices()?,
        AudioDeviceDirection::Output => host.output_devices()?,
    };

    for device in devices {
        let name = device.name()?;
        let descriptor = AudioDevice {
            id: make_id(&direction, index, &name),
            name: name.clone(),
            direction: direction.clone(),
            default: default_name.as_deref() == Some(name.as_str()),
        };
        let config = pick_f32_config(&device, &direction)?;

        let resolved = ResolvedDevice {
            descriptor,
            device,
            config,
        };

        if resolved.descriptor.default && fallback.is_none() {
            fallback = Some(ResolvedDevice {
                descriptor: resolved.descriptor.clone(),
                device: resolved.device.clone(),
                config: resolved.config.clone(),
            });
        } else if fallback.is_none() {
            fallback = Some(ResolvedDevice {
                descriptor: resolved.descriptor.clone(),
                device: resolved.device.clone(),
                config: resolved.config.clone(),
            });
        }

        if selected_id == Some(resolved.descriptor.id.as_str()) {
            return Ok(resolved);
        }

        index += 1;
    }

    fallback.ok_or_else(|| {
        AppError::message(match direction {
            AudioDeviceDirection::Input => "no usable input device was found",
            AudioDeviceDirection::Output => "no usable output device was found",
        })
    })
}

fn enumerate_direction(
    host: &cpal::Host,
    direction: AudioDeviceDirection,
    default_name: Option<&str>,
) -> AppResult<Vec<AudioDevice>> {
    let devices = match direction {
        AudioDeviceDirection::Input => host.input_devices()?,
        AudioDeviceDirection::Output => host.output_devices()?,
    };

    let mut results = Vec::new();
    for (index, device) in devices.enumerate() {
        let name = device.name()?;
        if pick_f32_config(&device, &direction).is_ok() {
            results.push(AudioDevice {
                id: make_id(&direction, index, &name),
                name: name.clone(),
                direction: direction.clone(),
                default: default_name == Some(name.as_str()),
            });
        }
    }
    Ok(results)
}

fn pick_f32_config(device: &Device, direction: &AudioDeviceDirection) -> AppResult<SupportedStreamConfig> {
    let default_config = match direction {
        AudioDeviceDirection::Input => device.default_input_config()?,
        AudioDeviceDirection::Output => device.default_output_config()?,
    };
    if default_config.sample_format() == SampleFormat::F32 {
        return Ok(default_config);
    }

    let maybe_config = match direction {
        AudioDeviceDirection::Input => {
            let mut best = None;
            for config_range in device.supported_input_configs()? {
                if config_range.sample_format() == SampleFormat::F32 {
                    best = Some(config_range.with_max_sample_rate());
                    break;
                }
            }
            best
        }
        AudioDeviceDirection::Output => {
            let mut best = None;
            for config_range in device.supported_output_configs()? {
                if config_range.sample_format() == SampleFormat::F32 {
                    best = Some(config_range.with_max_sample_rate());
                    break;
                }
            }
            best
        }
    };

    maybe_config.ok_or_else(|| {
        AppError::Unsupported(format!(
            "device '{}' does not expose an f32 {} stream configuration",
            device.name().unwrap_or_else(|_| "unknown".to_string()),
            match direction {
                AudioDeviceDirection::Input => "input",
                AudioDeviceDirection::Output => "output",
            }
        ))
    })
}

fn make_id(direction: &AudioDeviceDirection, index: usize, name: &str) -> String {
    let prefix = match direction {
        AudioDeviceDirection::Input => "input",
        AudioDeviceDirection::Output => "output",
    };
    let slug = name
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect::<String>();
    format!("{prefix}::{index}::{slug}")
}
