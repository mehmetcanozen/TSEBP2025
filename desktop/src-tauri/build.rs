use std::{env, fs, path::{Path, PathBuf}};

fn main() {
    tauri_build::build();

    println!("cargo:rerun-if-changed=tauri.conf.json");
    println!("cargo:rerun-if-changed=../ai/models/model_selection.json");
    println!("cargo:rerun-if-changed=../ai/models/AudioSepHive15Cat/model_package.json");
    println!("cargo:rerun-if-changed=../ai/models/CodecSepDNRv2_15Cat/model_package.json");
    println!("cargo:rerun-if-changed=../ai/models/Waveformer/model_package.json");
    println!("cargo:rerun-if-changed=../ai/models/AudioSepHive15Cat/frozensep_hive_15cat.onnx");
    println!("cargo:rerun-if-changed=../ai/models/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat.onnx");
    println!("cargo:rerun-if-changed=../ai/models/Waveformer/WFExports/windows_desktop_onnx/semantic_hearing_100ms_windows.onnx");

    if let Err(error) = stage_onnx_runtime_dlls() {
        println!("cargo:warning=Unable to pre-stage ONNX Runtime DLLs: {error}");
    }
}

fn stage_onnx_runtime_dlls() -> Result<(), String> {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").map_err(|error| error.to_string())?);
    let runtime_dir = manifest_dir.join("runtime");
    fs::create_dir_all(&runtime_dir).map_err(|error| error.to_string())?;

    let names = ["onnxruntime.dll", "onnxruntime_providers_shared.dll"];
    let search_roots = candidate_roots()?;

    for name in names {
        let destination = runtime_dir.join(name);
        if destination.exists() {
            continue;
        }
        if let Some(source) = find_in_roots(name, &search_roots) {
            fs::copy(&source, &destination).map_err(|error| {
                format!("failed to copy '{}' from '{}' ({error})", name, source.display())
            })?;
        }
    }

    Ok(())
}

fn candidate_roots() -> Result<Vec<PathBuf>, String> {
    let mut roots = Vec::new();

    if let Ok(path) = env::var("ORT_DYLIB_PATH") {
        let path = PathBuf::from(path);
        if let Some(parent) = path.parent() {
            roots.push(parent.to_path_buf());
        }
    }

    if let Ok(path) = env::var("ORT_RUNTIME_DIR") {
        roots.push(PathBuf::from(path));
    }

    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        let python_root = PathBuf::from(local_app_data).join("Programs").join("Python");
        if python_root.exists() {
            for entry in fs::read_dir(python_root).map_err(|error| error.to_string())? {
                let entry = entry.map_err(|error| error.to_string())?;
                let capi_dir = entry.path().join("Lib").join("site-packages").join("onnxruntime").join("capi");
                if capi_dir.exists() {
                    roots.push(capi_dir);
                }
            }
        }
    }

    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").map_err(|error| error.to_string())?);
    let workspace_root = manifest_dir
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| "unable to resolve workspace root".to_string())?;
    roots.push(
        workspace_root
            .join("ai")
            .join(".venv")
            .join("Lib")
            .join("site-packages")
            .join("onnxruntime")
            .join("capi"),
    );
    roots.push(
        workspace_root
            .join("desktop")
            .join("src-tauri")
            .join("runtime"),
    );

    Ok(roots)
}

fn find_in_roots(name: &str, roots: &[PathBuf]) -> Option<PathBuf> {
    roots
        .iter()
        .map(|root| root.join(name))
        .find(|candidate| candidate.exists())
}

