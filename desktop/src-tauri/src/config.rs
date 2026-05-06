use std::{
    collections::HashMap,
    env, fs,
    path::{Path, PathBuf},
};

use tauri::{path::BaseDirectory, AppHandle, Manager};

use crate::{
    error::{AppError, AppResult},
    models::{Hive15Preset, ModelCategory},
};

const ACTIVE_MODEL_ENV: &str = "TSEBP_ACTIVE_SUPPRESSION_MODEL";
const BUNDLED_MODELS_DIR: &str = "models";
const BUNDLED_RUNTIME_DIR: &str = "runtime";

#[derive(Clone, Debug)]
pub struct AssetCatalog {
    pub model_id: String,
    pub model_family: String,
    pub display_name: String,
    pub suppression_strategy: String,
    pub runtime_kind: String,
    pub model_path: PathBuf,
    pub runtime_metadata_paths: Vec<PathBuf>,
    pub categories: Vec<ModelCategory>,
    pub category_by_id: HashMap<String, ModelCategory>,
    pub presets: Vec<Hive15Preset>,
    pub sample_rate: u32,
    pub segment_seconds: Option<f32>,
    pub overlap_seconds: Option<f32>,
    pub chunk_samples: Option<usize>,
    pub preferred_live_hop_ms: u32,
    pub mix_channels: usize,
    pub state_tensors: HashMap<String, Vec<usize>>,
    pub runtime_dll_path: Option<PathBuf>,
    pub validation_status: String,
}

#[derive(Clone, Debug)]
pub struct TargetSpeakerAssetCatalog {
    pub model_id: String,
    pub display_name: String,
    pub runtime_kind: String,
    pub bundle_manifest_path: PathBuf,
    pub tsextract_onnx_path: PathBuf,
    pub tsextract_manifest_path: PathBuf,
    pub tsextract_validation_path: PathBuf,
    pub clearvoice_bundle_dir: PathBuf,
    pub sample_rate: u32,
    pub mixture_samples: usize,
    pub reference_samples: usize,
    pub validation_status: String,
    pub runtime_dll_path: Option<PathBuf>,
}

#[derive(Debug, serde::Deserialize)]
struct SelectionManifest {
    default_model_id: String,
    models: HashMap<String, String>,
}

#[derive(Debug, serde::Deserialize)]
struct PackageManifest {
    model_id: String,
    family: String,
    display_name: String,
    suppression_strategy: SuppressionStrategy,
    #[serde(default)]
    validation_summary: Option<ValidationSummary>,
    categories: Vec<ModelCategory>,
    #[serde(default)]
    presets: Vec<Hive15Preset>,
    platforms: HashMap<String, PlatformManifest>,
}

#[derive(Debug, serde::Deserialize)]
struct SuppressionStrategy {
    kind: String,
}

#[derive(Debug, serde::Deserialize)]
struct ValidationSummary {
    #[serde(default)]
    status: Option<String>,
}

#[derive(Debug, serde::Deserialize)]
struct PlatformManifest {
    runtime_kind: String,
    artifact: String,
    #[serde(default)]
    metadata_artifacts: Vec<String>,
    sample_rate: u32,
    #[serde(default)]
    segment_seconds: Option<f32>,
    #[serde(default)]
    overlap_seconds: Option<f32>,
    #[serde(default)]
    chunk_samples: Option<usize>,
    #[serde(default)]
    preferred_live_hop_ms: Option<u32>,
    #[serde(default)]
    mix_channels: Option<usize>,
    #[serde(default)]
    state_tensors: HashMap<String, Vec<usize>>,
}

#[derive(Debug, serde::Deserialize)]
struct TargetSpeakerPackageManifest {
    model_id: String,
    display_name: String,
    #[serde(default)]
    validation_summary: Option<TargetSpeakerValidationSummary>,
    platforms: HashMap<String, PlatformManifest>,
}

#[derive(Debug, serde::Deserialize)]
struct TargetSpeakerValidationSummary {
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    validation_artifact: Option<String>,
}

impl AssetCatalog {
    pub fn resolve(app: &AppHandle) -> AppResult<Self> {
        let workspace_root = workspace_root()?;
        let models_root = resolve_models_root(app, &workspace_root);
        let bundled_runtime_dir = resolve_bundled_runtime_dir(app);
        let selection_path = models_root.join("model_selection.json");
        let selection: SelectionManifest =
            serde_json::from_str(&fs::read_to_string(&selection_path)?)?;

        let active_model_id = env::var(ACTIVE_MODEL_ENV)
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or(selection.default_model_id);
        let relative_package = selection.models.get(&active_model_id).ok_or_else(|| {
            AppError::message(format!("unknown desktop model '{active_model_id}'"))
        })?;
        let package_path = models_root.join(relative_package);
        let package_root = package_path
            .parent()
            .ok_or_else(|| AppError::message("invalid packaged model path"))?
            .to_path_buf();
        let package: PackageManifest = serde_json::from_str(&fs::read_to_string(&package_path)?)?;
        let platform = package
            .platforms
            .get("desktop")
            .ok_or_else(|| AppError::message("packaged model has no desktop platform"))?;

        let categories = package.categories;
        let category_by_id = categories
            .iter()
            .cloned()
            .map(|category| (category.id.clone(), category))
            .collect::<HashMap<_, _>>();

        if categories.is_empty() {
            return Err(AppError::message(format!(
                "packaged model '{}' has no categories",
                package.model_id
            )));
        }

        let runtime_metadata_paths = platform
            .metadata_artifacts
            .iter()
            .map(|relative| package_root.join(relative))
            .collect::<Vec<_>>();
        let runtime_dll_path = bundled_runtime_dir
            .and_then(|path| {
                let candidate = path.join("onnxruntime.dll");
                candidate.exists().then_some(candidate)
            })
            .or_else(|| discover_runtime_dll(&workspace_root));

        Ok(Self {
            model_id: package.model_id,
            model_family: package.family,
            display_name: package.display_name,
            suppression_strategy: package.suppression_strategy.kind,
            runtime_kind: platform.runtime_kind.clone(),
            model_path: package_root.join(&platform.artifact),
            runtime_metadata_paths,
            categories,
            category_by_id,
            presets: package.presets,
            sample_rate: platform.sample_rate,
            segment_seconds: platform.segment_seconds,
            overlap_seconds: platform.overlap_seconds,
            chunk_samples: platform.chunk_samples,
            preferred_live_hop_ms: platform.preferred_live_hop_ms.unwrap_or(500),
            mix_channels: platform.mix_channels.unwrap_or(1),
            state_tensors: platform.state_tensors.clone(),
            runtime_dll_path,
            validation_status: package
                .validation_summary
                .and_then(|summary| summary.status)
                .unwrap_or_else(|| "unknown".to_string()),
        })
    }
}

impl TargetSpeakerAssetCatalog {
    pub fn resolve(app: &AppHandle) -> AppResult<Self> {
        let workspace_root = workspace_root()?;
        let models_root = resolve_models_root(app, &workspace_root);
        let bundled_runtime_dir = resolve_bundled_runtime_dir(app);
        let package_path = models_root
            .join("TargetSpeakerWindows")
            .join("model_package.json");
        let package_root = package_path
            .parent()
            .ok_or_else(|| AppError::message("invalid target speaker package path"))?
            .to_path_buf();
        let package: TargetSpeakerPackageManifest =
            serde_json::from_str(&fs::read_to_string(&package_path)?)?;
        let platform = package
            .platforms
            .get("desktop")
            .ok_or_else(|| AppError::message("target speaker package has no desktop platform"))?;

        let bundle_manifest_path = package_root.join(&platform.artifact);
        let bundle_dir = bundle_manifest_path
            .parent()
            .ok_or_else(|| AppError::message("invalid target speaker bundle path"))?
            .to_path_buf();
        let tsextract_onnx_path = bundle_dir
            .join("tsextract_onnx")
            .join("tsextract_fp32.onnx");
        let tsextract_manifest_path = bundle_dir
            .join("tsextract_onnx")
            .join("tsextract_fp32.manifest.json");
        let clearvoice_bundle_dir = bundle_dir.join("clearvoice_native");
        let tsextract_validation_path = package
            .validation_summary
            .as_ref()
            .and_then(|summary| summary.validation_artifact.as_ref())
            .map(|relative| package_root.join(relative))
            .unwrap_or_else(|| {
                package_root
                    .join("..")
                    .join("Exports")
                    .join("TargetSpeakerWindows")
                    .join("target_speaker_windows_desktop")
                    .join("desktop")
                    .join("tsextract_onnx")
                    .join("tsextract_fp32.validation.json")
            });
        let validation_status = read_validation_status(
            &tsextract_validation_path,
            package
                .validation_summary
                .and_then(|summary| summary.status)
                .unwrap_or_else(|| "unknown".to_string()),
        );

        Ok(Self {
            model_id: package.model_id,
            display_name: package.display_name,
            runtime_kind: platform.runtime_kind.clone(),
            bundle_manifest_path,
            tsextract_onnx_path,
            tsextract_manifest_path,
            tsextract_validation_path,
            clearvoice_bundle_dir,
            sample_rate: platform.sample_rate,
            mixture_samples: platform.chunk_samples.unwrap_or(80_000),
            reference_samples: 24_000,
            validation_status,
            runtime_dll_path: bundled_runtime_dir
                .and_then(|path| {
                    let candidate = path.join("onnxruntime.dll");
                    candidate.exists().then_some(candidate)
                })
                .or_else(|| discover_runtime_dll(&workspace_root)),
        })
    }
}

fn workspace_root() -> AppResult<PathBuf> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| AppError::message("unable to resolve workspace root"))
        .map(Path::to_path_buf)
}

fn resolve_models_root(app: &AppHandle, workspace_root: &Path) -> PathBuf {
    app.path()
        .resolve(BUNDLED_MODELS_DIR, BaseDirectory::Resource)
        .ok()
        .filter(|path| path.exists())
        .unwrap_or_else(|| workspace_root.join("ai").join("models"))
}

fn resolve_bundled_runtime_dir(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .resolve(BUNDLED_RUNTIME_DIR, BaseDirectory::Resource)
        .ok()
}

fn read_validation_status(path: &Path, fallback: String) -> String {
    let Ok(contents) = fs::read_to_string(path) else {
        return fallback;
    };
    let Ok(value) = serde_json::from_str::<serde_json::Value>(&contents) else {
        return fallback;
    };
    match value.get("passed").and_then(|passed| passed.as_bool()) {
        Some(true) => "tsextract_onnx_validation_passed".to_string(),
        Some(false) => "tsextract_onnx_validation_failed".to_string(),
        None => fallback,
    }
}

fn discover_runtime_dll(workspace_root: &Path) -> Option<PathBuf> {
    if let Ok(path) = env::var("ORT_DYLIB_PATH") {
        let candidate = PathBuf::from(path);
        if candidate.exists() {
            return Some(candidate);
        }
    }

    let runtime_dir = workspace_root
        .join("desktop")
        .join("src-tauri")
        .join("runtime");
    let bundled = runtime_dir.join("onnxruntime.dll");
    if bundled.exists() {
        return Some(bundled);
    }

    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        let python_root = PathBuf::from(local_app_data)
            .join("Programs")
            .join("Python");
        if let Ok(entries) = fs::read_dir(python_root) {
            for entry in entries.flatten() {
                let candidate = entry
                    .path()
                    .join("Lib")
                    .join("site-packages")
                    .join("onnxruntime")
                    .join("capi")
                    .join("onnxruntime.dll");
                if candidate.exists() {
                    return Some(candidate);
                }
            }
        }
    }

    None
}
