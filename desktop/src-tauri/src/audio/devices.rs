use cpal::{
    traits::{DeviceTrait, HostTrait},
    Device, SupportedStreamConfig,
};

use crate::{
    error::{AppError, AppResult},
    models::{
        AudioDevice, AudioDeviceDirection, VirtualCableEndpoint, VirtualCableEndpointRole,
        VirtualMicStatus,
    },
};

const VB_CABLE_PROVIDER: &str = "VB-CABLE";
const VB_CABLE_SETUP_URL: &str = "https://vb-audio.com/Cable/";

pub struct ResolvedDevice {
    pub descriptor: AudioDevice,
    pub device: Device,
    pub config: SupportedStreamConfig,
}

pub fn list_audio_devices() -> AppResult<Vec<AudioDevice>> {
    let host = cpal::default_host();
    let default_input_name = host
        .default_input_device()
        .and_then(|device| device.name().ok());
    let default_output_name = host
        .default_output_device()
        .and_then(|device| device.name().ok());

    let mut devices = Vec::new();
    devices.extend(enumerate_direction(
        &host,
        AudioDeviceDirection::Input,
        default_input_name.as_deref(),
    )?);
    devices.extend(enumerate_direction(
        &host,
        AudioDeviceDirection::Output,
        default_output_name.as_deref(),
    )?);
    Ok(devices)
}

pub fn get_virtual_mic_status() -> AppResult<VirtualMicStatus> {
    let devices = list_audio_devices()?;
    Ok(build_virtual_mic_status(&devices))
}

pub fn resolve_virtual_mic_output_device() -> AppResult<(ResolvedDevice, VirtualMicStatus)> {
    let status = get_virtual_mic_status()?;
    if !status.installed {
        return Err(AppError::message(status.message.clone()));
    }

    let playback_device_id = status
        .playback_device_id
        .clone()
        .ok_or_else(|| AppError::message("VB-CABLE playback endpoint was not found"))?;
    let resolved = resolve_output_device(Some(&playback_device_id))?;
    Ok((resolved, status))
}

pub fn resolve_input_device(selected_id: Option<&str>) -> AppResult<ResolvedDevice> {
    resolve_device(AudioDeviceDirection::Input, selected_id)
}

pub fn resolve_output_device(selected_id: Option<&str>) -> AppResult<ResolvedDevice> {
    resolve_device(AudioDeviceDirection::Output, selected_id)
}

fn resolve_device(
    direction: AudioDeviceDirection,
    selected_id: Option<&str>,
) -> AppResult<ResolvedDevice> {
    let host = cpal::default_host();
    let default_device = match direction {
        AudioDeviceDirection::Input => host.default_input_device(),
        AudioDeviceDirection::Output => host.default_output_device(),
    };
    let default_name = default_device
        .as_ref()
        .and_then(|device| device.name().ok());

    if selected_id.is_none() {
        if let Some(device) = default_device {
            let name = device.name()?;
            let descriptor = AudioDevice {
                id: make_default_id(&direction, &name),
                name: name.clone(),
                direction: direction.clone(),
                default: true,
                virtual_cable: virtual_cable_endpoint(&direction, &name),
            };
            let config = pick_default_config(&device, &direction)?;
            return Ok(ResolvedDevice {
                descriptor,
                device,
                config,
            });
        }
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
            virtual_cable: virtual_cable_endpoint(&direction, &name),
        };
        let config = pick_default_config(&device, &direction)?;

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
        if pick_default_config(&device, &direction).is_ok() {
            results.push(AudioDevice {
                id: make_id(&direction, index, &name),
                name: name.clone(),
                direction: direction.clone(),
                default: default_name == Some(name.as_str()),
                virtual_cable: virtual_cable_endpoint(&direction, &name),
            });
        }
    }
    Ok(results)
}

pub(crate) fn build_virtual_mic_status(devices: &[AudioDevice]) -> VirtualMicStatus {
    let playback = devices.iter().find(|device| {
        matches!(
            device.virtual_cable.as_ref().map(|endpoint| &endpoint.role),
            Some(VirtualCableEndpointRole::Playback)
        )
    });
    let recording = devices.iter().find(|device| {
        matches!(
            device.virtual_cable.as_ref().map(|endpoint| &endpoint.role),
            Some(VirtualCableEndpointRole::Recording)
        )
    });
    let installed = playback.is_some() && recording.is_some();
    let recording_name = recording.map(|device| device.name.clone());
    let playback_name = playback.map(|device| device.name.clone());
    let message = if installed {
        format!(
            "Virtual mic ready. Select '{}' as the microphone in your target app.",
            recording_name
                .as_deref()
                .unwrap_or("CABLE Output (VB-Audio Virtual Cable)")
        )
    } else {
        "VB-CABLE was not detected. Install VB-CABLE, reboot if prompted, then refresh devices."
            .to_string()
    };

    VirtualMicStatus {
        provider: VB_CABLE_PROVIDER.to_string(),
        installed,
        playback_device_id: playback.map(|device| device.id.clone()),
        playback_device_name: playback_name,
        recording_device_name: recording_name,
        setup_url: VB_CABLE_SETUP_URL.to_string(),
        message,
    }
}

pub(crate) fn virtual_cable_endpoint(
    direction: &AudioDeviceDirection,
    name: &str,
) -> Option<VirtualCableEndpoint> {
    let normalized = normalize_device_name(name);
    let looks_like_vb_cable = normalized.contains("vb-audio")
        || normalized.contains("vb-cable")
        || normalized.contains("virtual cable")
        || normalized == "cable input"
        || normalized == "cable output";

    if !looks_like_vb_cable {
        return None;
    }

    let role = match direction {
        AudioDeviceDirection::Output if normalized.contains("cable input") => {
            VirtualCableEndpointRole::Playback
        }
        AudioDeviceDirection::Input if normalized.contains("cable output") => {
            VirtualCableEndpointRole::Recording
        }
        _ => return None,
    };
    let paired_device_name = match role {
        VirtualCableEndpointRole::Playback => {
            Some("CABLE Output (VB-Audio Virtual Cable)".to_string())
        }
        VirtualCableEndpointRole::Recording => {
            Some("CABLE Input (VB-Audio Virtual Cable)".to_string())
        }
    };

    Some(VirtualCableEndpoint {
        provider: VB_CABLE_PROVIDER.to_string(),
        role,
        paired_device_name,
    })
}

pub(crate) fn is_standard_vb_cable_recording_endpoint(device: &AudioDevice) -> bool {
    if !matches!(device.direction, AudioDeviceDirection::Input) {
        return false;
    }

    let normalized = normalize_device_name(&device.name);
    normalized.contains("cable output") && !normalized.contains("vb-audio point")
}

fn normalize_device_name(name: &str) -> String {
    name.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_ascii_lowercase()
}

fn pick_default_config(
    device: &Device,
    direction: &AudioDeviceDirection,
) -> AppResult<SupportedStreamConfig> {
    Ok(match direction {
        AudioDeviceDirection::Input => device.default_input_config()?,
        AudioDeviceDirection::Output => device.default_output_config()?,
    })
}

fn make_id(direction: &AudioDeviceDirection, index: usize, name: &str) -> String {
    let prefix = match direction {
        AudioDeviceDirection::Input => "input",
        AudioDeviceDirection::Output => "output",
    };
    format!("{prefix}::{index}::{}", device_name_slug(name))
}

fn make_default_id(direction: &AudioDeviceDirection, name: &str) -> String {
    let prefix = match direction {
        AudioDeviceDirection::Input => "input",
        AudioDeviceDirection::Output => "output",
    };
    format!("{prefix}::default::{}", device_name_slug(name))
}

fn device_name_slug(name: &str) -> String {
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
    slug
}

#[cfg(test)]
mod tests {
    use super::{
        build_virtual_mic_status, is_standard_vb_cable_recording_endpoint, virtual_cable_endpoint,
    };
    use crate::models::{AudioDevice, AudioDeviceDirection, VirtualCableEndpointRole};

    #[test]
    fn detects_vb_cable_playback_and_recording_endpoints() {
        let playback = virtual_cable_endpoint(
            &AudioDeviceDirection::Output,
            "CABLE Input (VB-Audio Virtual Cable)",
        )
        .expect("playback endpoint should be detected");
        let recording = virtual_cable_endpoint(
            &AudioDeviceDirection::Input,
            "CABLE Output (VB-Audio Virtual Cable)",
        )
        .expect("recording endpoint should be detected");

        assert_eq!(playback.role, VirtualCableEndpointRole::Playback);
        assert_eq!(recording.role, VirtualCableEndpointRole::Recording);
    }

    #[test]
    fn does_not_mark_physical_devices_as_virtual_cable() {
        assert!(
            virtual_cable_endpoint(&AudioDeviceDirection::Input, "Realtek Microphone").is_none()
        );
        assert!(virtual_cable_endpoint(&AudioDeviceDirection::Output, "Headphones").is_none());
    }

    #[test]
    fn detects_standard_cable_recording_endpoint_for_loop_guard() {
        let standard = AudioDevice {
            id: "input::0::cable-output".to_string(),
            name: "CABLE Output (VB-Audio Virtual Cable)".to_string(),
            direction: AudioDeviceDirection::Input,
            default: false,
            virtual_cable: None,
        };
        let point = AudioDevice {
            id: "input::1::cable-output-vb-audio-point".to_string(),
            name: "CABLE Output (VB-Audio Point)".to_string(),
            direction: AudioDeviceDirection::Input,
            default: false,
            virtual_cable: None,
        };

        assert!(is_standard_vb_cable_recording_endpoint(&standard));
        assert!(!is_standard_vb_cable_recording_endpoint(&point));
    }

    #[test]
    fn virtual_mic_status_requires_both_sides_of_the_cable() {
        let devices = vec![
            AudioDevice {
                id: "output::0::cable-input".to_string(),
                name: "CABLE Input (VB-Audio Virtual Cable)".to_string(),
                direction: AudioDeviceDirection::Output,
                default: false,
                virtual_cable: virtual_cable_endpoint(
                    &AudioDeviceDirection::Output,
                    "CABLE Input (VB-Audio Virtual Cable)",
                ),
            },
            AudioDevice {
                id: "input::0::cable-output".to_string(),
                name: "CABLE Output (VB-Audio Virtual Cable)".to_string(),
                direction: AudioDeviceDirection::Input,
                default: false,
                virtual_cable: virtual_cable_endpoint(
                    &AudioDeviceDirection::Input,
                    "CABLE Output (VB-Audio Virtual Cable)",
                ),
            },
        ];

        let status = build_virtual_mic_status(&devices);
        assert!(status.installed);
        assert_eq!(
            status.playback_device_id.as_deref(),
            Some("output::0::cable-input")
        );
        assert_eq!(
            status.recording_device_name.as_deref(),
            Some("CABLE Output (VB-Audio Virtual Cable)")
        );

        let missing_recording = build_virtual_mic_status(&devices[..1]);
        assert!(!missing_recording.installed);
    }
}
