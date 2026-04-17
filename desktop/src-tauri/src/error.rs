use thiserror::Error;

pub type AppResult<T> = Result<T, AppError>;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("{0}")]
    Message(String),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),
    #[error("Audio decode error: {0}")]
    Symphonia(#[from] symphonia::core::errors::Error),
    #[error("ONNX Runtime error: {0}")]
    Ort(#[from] ort::Error),
    #[error("Unsupported operation: {0}")]
    Unsupported(String),
    #[error("Operation cancelled")]
    Cancelled,
}

impl AppError {
    pub fn message(message: impl Into<String>) -> Self {
        Self::Message(message.into())
    }
}

impl From<cpal::DevicesError> for AppError {
    fn from(value: cpal::DevicesError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<cpal::DeviceNameError> for AppError {
    fn from(value: cpal::DeviceNameError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<cpal::DefaultStreamConfigError> for AppError {
    fn from(value: cpal::DefaultStreamConfigError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<cpal::SupportedStreamConfigsError> for AppError {
    fn from(value: cpal::SupportedStreamConfigsError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<cpal::BuildStreamError> for AppError {
    fn from(value: cpal::BuildStreamError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<cpal::PlayStreamError> for AppError {
    fn from(value: cpal::PlayStreamError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<cpal::PauseStreamError> for AppError {
    fn from(value: cpal::PauseStreamError) -> Self {
        Self::Message(value.to_string())
    }
}

