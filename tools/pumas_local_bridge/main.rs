//! Consumer-private pipe adapter, not a new Pumas discovery protocol.
use pumas_library::discovery::{CompatibilityRequirements, LocalDiscovery};
use pumas_library::models::ModelLibrarySelectorSnapshotRequest;
use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{Read, Write};
use std::path::PathBuf;

const SOURCE: &str = "ab9890fe3248ed7c435b958cded0b131b0700a35";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Selection {
    id: String,
    root: PathBuf,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    operation: String,
    registry: PathBuf,
    selected: Option<Selection>,
}

async fn run(request: Request) -> Result<Value, Box<dyn std::error::Error>> {
    if !matches!(request.operation.as_str(), "list" | "borrow") {
        return Err("Unsupported operation; no owner startup, shutdown or acquisition".into());
    }
    if !request.registry.is_absolute() {
        return Err("Explicit absolute registry path required".into());
    }
    let discovery = LocalDiscovery::open_at(&request.registry)?;
    let snapshot = discovery.snapshot()?;
    if snapshot.registered_libraries.len() > 32 || snapshot.tracked_instances.len() > 32
        || snapshot.advertised_http_services.len() > 32
    {
        return Err("Registry exceeds bounded 32-library observation".into());
    }
    let data = if request.operation == "list" {
        if request.selected.is_some() { return Err("List has no implicit selected library".into()); }
        let models = discovery.local_model_snapshots(ModelLibrarySelectorSnapshotRequest {
            offset: Some(0), limit: Some(64), ..Default::default()
        })?;
        json!({
            "registered_libraries":snapshot.registered_libraries.iter().map(|row|json!({
                "id":row.id,"name":row.name,"root":row.path,"version":row.version
            })).collect::<Vec<_>>(),
            "tracked_instances":snapshot.tracked_instances.iter().map(|row|json!({
                "root":row.library_root,"generation":row.generation,"status":row.status
            })).collect::<Vec<_>>(),
            "local_models":models,
        })
    } else {
        let selected = request.selected.ok_or("Explicit selected library required")?;
        if !snapshot.registered_libraries.iter().any(|row|row.id == selected.id && row.path == selected.root) {
            return Err("Selected registered library context changed".into());
        }
        let borrowed = discovery.borrow_http_service(&selected.root, &CompatibilityRequirements::default()).await?;
        let description = borrowed.description();
        if description.instance.registry_library_id != selected.id || description.instance.library_root != selected.root {
            return Err("Authenticated owner changed selected library".into());
        }
        json!({"service":description})
    };
    Ok(json!({"bridge_schema":1,"producer_commit":SOURCE,"operation":request.operation,"data":data}))
}

#[tokio::main(flavor="current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut raw = Vec::new();
    std::io::stdin().take(16385).read_to_end(&mut raw)?;
    if raw.len() > 16384 { return Err("Bridge request exceeds16KiB".into()); }
    let result = run(serde_json::from_slice(&raw)?).await?;
    let raw = serde_json::to_vec(&result)?;
    if raw.len() > 1024*1024 { return Err("Bridge observation exceeds1MiB".into()); }
    std::io::stdout().write_all(&raw)?;
    Ok(())
}
