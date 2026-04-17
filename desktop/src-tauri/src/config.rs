use std::{
    collections::{BTreeMap, HashMap},
    env,
    fs,
    path::{Path, PathBuf},
};

use tauri::{path::BaseDirectory, AppHandle, Manager};

use crate::{
    error::{AppError, AppResult},
    models::{Hive15Preset, ModelCategory},
};

const BUNDLED_MODEL_DIR: &str = "audiosep_hive15cat";
const BUNDLED_CONFIG_DIR: &str = "config";
const BUNDLED_RUNTIME_DIR: &str = "runtime";

#[derive(Clone, Debug)]
pub struct AssetCatalog {
    pub model_path: PathBuf,
    pub categories_yaml_path: PathBuf,
    pub categories_txt_path: PathBuf,
    pub default_profiles_path: PathBuf,
    pub runtime_dll_path: Option<PathBuf>,
}

#[derive(Clone, Debug)]
pub struct CategoryCatalog {
    pub categories: Vec<ModelCategory>,
    pub by_id: HashMap<String, ModelCategory>,
}

#[derive(Debug, serde::Deserialize)]
struct CategoryYamlRoot {
    categories: BTreeMap<String, CategoryYamlEntry>,
}

#[derive(Debug, Default, serde::Deserialize)]
struct CategoryYamlEntry {
    transient: Option<bool>,
    aggressiveness_override: Option<f32>,
}

#[derive(Debug, serde::Deserialize)]
struct DefaultProfile {
    id: String,
    name: String,
    description: String,
    #[serde(default)]
    suppressions: BTreeMap<String, bool>,
    #[serde(default)]
    suppression_params: Option<SuppressionParams>,
}

#[derive(Debug, Default, serde::Deserialize)]
struct SuppressionParams {
    separator_backend: Option<String>,
}

impl AssetCatalog {
    pub fn resolve(app: &AppHandle) -> AppResult<Self> {
        let workspace_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .ok_or_else(|| AppError::message("unable to resolve workspace root"))?
            .to_path_buf();

        let bundled_model_dir = app
            .path()
            .resolve(BUNDLED_MODEL_DIR, BaseDirectory::Resource)
            .ok();
        let bundled_config_dir = app
            .path()
            .resolve(BUNDLED_CONFIG_DIR, BaseDirectory::Resource)
            .ok();
        let bundled_runtime_dir = app
            .path()
            .resolve(BUNDLED_RUNTIME_DIR, BaseDirectory::Resource)
            .ok();

        let model_dir = bundled_model_dir
            .filter(|path| path.exists())
            .unwrap_or_else(|| workspace_root.join("ai").join("models").join("AudioSepHive15Cat"));
        let config_dir = bundled_config_dir
            .filter(|path| path.exists())
            .unwrap_or_else(|| workspace_root.join("ai").join("ai_runtime").join("config"));

        let runtime_dll_path = bundled_runtime_dir
            .and_then(|path| {
                let candidate = path.join("onnxruntime.dll");
                candidate.exists().then_some(candidate)
            })
            .or_else(|| discover_runtime_dll(&workspace_root));

        Ok(Self {
            model_path: model_dir.join("frozensep_hive_15cat.onnx"),
            categories_txt_path: model_dir.join("categories_15.txt"),
            categories_yaml_path: config_dir.join("audiosep_hive15cat_categories.yaml"),
            default_profiles_path: config_dir.join("default_profiles.json"),
            runtime_dll_path,
        })
    }
}

impl CategoryCatalog {
    pub fn load(assets: &AssetCatalog) -> AppResult<Self> {
        let yaml: CategoryYamlRoot = serde_yaml::from_str(&fs::read_to_string(&assets.categories_yaml_path)?)?;
        let txt = fs::read_to_string(&assets.categories_txt_path)?;

        let categories = txt
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .map(|label| {
                let metadata = yaml.categories.get(label);
                ModelCategory {
                    id: label.to_string(),
                    label: label.to_string(),
                    transient: metadata.and_then(|entry| entry.transient).unwrap_or(false),
                    default_aggressiveness: metadata
                        .and_then(|entry| entry.aggressiveness_override)
                        .unwrap_or(1.5),
                }
            })
            .collect::<Vec<_>>();

        if categories.is_empty() {
            return Err(AppError::message(format!(
                "no AudioSepHive15Cat categories found in '{}'",
                assets.categories_txt_path.display()
            )));
        }

        let by_id = categories
            .iter()
            .cloned()
            .map(|category| (category.id.clone(), category))
            .collect();

        Ok(Self { categories, by_id })
    }

    pub fn contains_all(&self, categories: &[String]) -> bool {
        categories.iter().all(|category| self.by_id.contains_key(category))
    }
}

pub fn load_hive15_presets(assets: &AssetCatalog, categories: &CategoryCatalog) -> AppResult<Vec<Hive15Preset>> {
    let profiles: Vec<DefaultProfile> = serde_json::from_str(&fs::read_to_string(&assets.default_profiles_path)?)?;

    Ok(profiles
        .into_iter()
        .filter(|profile| {
            profile
                .suppression_params
                .as_ref()
                .and_then(|params| params.separator_backend.as_deref())
                == Some("audiosep_hive15cat")
        })
        .map(|profile| Hive15Preset {
            id: profile.id,
            name: profile.name,
            description: profile.description,
            categories: profile
                .suppressions
                .into_iter()
                .filter_map(|(category, enabled)| {
                    (enabled && categories.by_id.contains_key(&category)).then_some(category)
                })
                .collect(),
        })
        .collect())
}

fn discover_runtime_dll(workspace_root: &Path) -> Option<PathBuf> {
    if let Ok(path) = env::var("ORT_DYLIB_PATH") {
        let candidate = PathBuf::from(path);
        if candidate.exists() {
            return Some(candidate);
        }
    }

    let runtime_dir = workspace_root.join("desktop").join("src-tauri").join("runtime");
    let bundled = runtime_dir.join("onnxruntime.dll");
    if bundled.exists() {
        return Some(bundled);
    }

    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        let python_root = PathBuf::from(local_app_data).join("Programs").join("Python");
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
