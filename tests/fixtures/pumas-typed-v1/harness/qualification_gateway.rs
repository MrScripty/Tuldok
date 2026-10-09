//! Authored qualification composition only; all included Pumas modules are pinned.
//! This is a non-test binary: no cfg(test) Torch process-observation bypass.
#[path = "../catalog_projection.rs"] mod catalog_projection;
#[path = "../contract.rs"] mod contract;
#[path = "../handlers/mod.rs"] mod handlers;
#[path = "../http_admission.rs"] mod http_admission;
#[path = "../http_transport.rs"] mod http_transport;
#[path = "../provider_clients.rs"] mod provider_clients;
#[path = "../server.rs"] mod server;
#[path = "../wrapper.rs"] mod wrapper;

use pumas_library::{PumasApi, PluginLoader, index::ModelRecord, models::*};
use pumas_app_manager::SizeCalculator;
use serde_json::json;
use std::{collections::HashMap, path::PathBuf, time::Duration};

async fn record(api: &PumasApi, id: &str, alias: &str, task: &str, provider: RuntimeProviderId, profile: &str, endpoint: &str) -> anyhow::Result<()> {
    let model_root = api.model_library().library_root().join(id);
    std::fs::create_dir_all(&model_root)?;
    api.model_library().index().upsert(&ModelRecord {
        id: id.into(), path: model_root.display().to_string(), cleaned_name: alias.into(), official_name: alias.into(), model_type: if provider == RuntimeProviderId::Torch {"diffusion"} else {"llm"}.into(), tags: vec![], hashes: HashMap::new(), metadata: json!({"task_type_primary":task,"controlled_backend_no_model":true}), updated_at: "authored-control".into(),
    })?;
    api.record_served_model(ServedModelStatus {
        model_id: id.into(), model_alias: Some(alias.into()), provider, profile_id: RuntimeProfileId::parse(profile).map_err(anyhow::Error::msg)?, load_state: ServedModelLoadState::Loaded, device_mode: RuntimeDeviceMode::Cpu, device_id: None, gpu_layers: None, tensor_split: None, context_size: None, keep_loaded: true, endpoint_url: Some(RuntimeEndpointUrl::parse(endpoint).map_err(anyhow::Error::msg)?), memory_bytes: None, loaded_at: None, last_error: None,
    }).await?;
    Ok(())
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    anyhow::ensure!(args.len() == 3, "arguments: fixture-root text-backend-url image-port");
    let root = PathBuf::from(&args[0]);
    std::fs::create_dir_all(&root)?;
    std::env::set_var("PUMAS_REGISTRY_DB_PATH", root.join("registry.db"));
    let api = PumasApi::builder(&root).auto_create_dirs(true).with_hf_client(false).with_process_manager(true).build().await?;
    let mut text = RuntimeProfileConfig::default_ollama();
    text.profile_id = RuntimeProfileId::parse("controlled-text-cpu").map_err(anyhow::Error::msg)?;
    text.name = "Controlled external text; no model".into();
    text.provider = RuntimeProviderId::LlamaCpp;
    text.provider_mode = RuntimeProviderMode::LlamaCppDedicated;
    text.management_mode = RuntimeManagementMode::External;
    text.endpoint_url = Some(RuntimeEndpointUrl::parse(&args[1]).map_err(anyhow::Error::msg)?);
    text.port = None;
    api.upsert_runtime_profile(text).await?;
    record(&api, "models/controlled-text", "controlled-text", "text-generation", RuntimeProviderId::LlamaCpp, "controlled-text-cpu", &args[1]).await?;

    let image_profile = RuntimeProfileId::parse("controlled-image-cpu").map_err(anyhow::Error::msg)?;
    let image_url = format!("http://127.0.0.1:{}", args[2]);
    let mut image = RuntimeProfileConfig::default_ollama();
    image.profile_id = image_profile.clone();
    image.name = "Controlled managed literal PNG worker; no Torch/model".into();
    image.provider = RuntimeProviderId::Torch;
    image.provider_mode = RuntimeProviderMode::TorchServe;
    image.management_mode = RuntimeManagementMode::Managed;
    image.endpoint_url = Some(RuntimeEndpointUrl::parse(&image_url).map_err(anyhow::Error::msg)?);
    image.port = Some(RuntimePort::parse(args[2].parse()?).map_err(anyhow::Error::msg)?);
    image.device.mode = RuntimeDeviceMode::Cpu;
    api.upsert_runtime_profile(image).await?;
    let launch = api.launch_runtime_profile_for_model_with_receipt(image_profile.clone(), "controlled-not-torch", &root.join("controlled-image-worker"), None, None).await?;
    anyhow::ensure!(launch.response.success, "managed worker launch failed: {:?}", launch.response);
    let observation = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            if let Some(current) = api.observe_owned_runtime_profile(&image_profile)? {
                if current.state == RuntimeLifecycleState::Running && api.owned_runtime_profile_has_listener(&image_profile, &current)? {
                    break Ok::<_, anyhow::Error>(current);
                }
            }
            tokio::time::sleep(Duration::from_millis(30)).await;
        }
    }).await??;
    record(&api, "models/controlled-image", "controlled-image", "text-to-image", RuntimeProviderId::Torch, "controlled-image-cpu", &image_url).await?;
    let plugin = PluginLoader::new_async(root.join("launcher-data/plugins")).await?;
    let size = SizeCalculator::new_with_cache(root.join("launcher-data/cache")).await;
    let handle = server::start_server(api, HashMap::new(), size, plugin, server::LoopbackHost::parse("127.0.0.1")?, 0, http_transport::HttpShutdownPolicy::from_millis(1000)?).await?;
    let receipt = json!({"gateway_url":format!("http://{}",handle.addr()),"text_backend_url":args[1],"image_backend_url":image_url,"text_alias":"controlled-text","text_profile":"controlled-text-cpu","image_alias":"controlled-image","image_profile":"controlled-image-cpu","managed_observation_debug":format!("{:?}",observation),"managed_pid":observation.pid,"owned_listener_verified":true,"compiled_without_cfg_test":true,"controlled_no_models":true,"producer_commit":"40c5cbfed67a6f0e862a1197bb5105363d67bdb1"});
    std::fs::write(root.join("gateway.json"), serde_json::to_vec_pretty(&receipt)?)?;
    println!("{}",receipt);
    // Explicit file stop keeps the server handle and runtime custody until shutdown.
    while !root.join("stop").exists() { tokio::time::sleep(Duration::from_millis(100)).await; }
    handle.shutdown().await?;
    std::fs::write(root.join("shutdown.json"), b"{\"owned_server_shutdown_completed\":true}")?;
    Ok(())
}
