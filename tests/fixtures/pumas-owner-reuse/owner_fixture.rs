//! Owned original-SDK core/IPC and authored HTTP descriptor responder; no model runtime.
use pumas_library::build_info::{ProtocolAdvertisement, SchemaAdvertisement};
use pumas_library::discovery::{LoopbackHttpEndpoint, HTTP_ADVERTISEMENT_SCHEMA_VERSION};
use pumas_library::index::{ModelIndex, ModelRecord};
use pumas_library::registry::LibraryRegistry;
use pumas_library::{PumasApi, PumasBuildInfo};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

fn seed_index(root: &std::path::Path, name: &str) -> Result<(), Box<dyn std::error::Error>> {
    seed_record(root,name,"same-model-id")
}

fn seed_record(root: &std::path::Path, name: &str, id: &str) -> Result<(), Box<dyn std::error::Error>> {
    let models = root.join("shared-resources/models");
    std::fs::create_dir_all(&models)?;
    ModelIndex::new(models.join("models.db"))?.upsert(&ModelRecord {
        id:id.into(),path:id.into(),cleaned_name:"controlled".into(),
        official_name:"Controlled index fixture only".into(),model_type:"llm".into(),tags:vec![],
        hashes:HashMap::from([("sha256".into(),format!("{name}-authored-index-hash"))]),
        metadata:json!({}),updated_at:"2026-10-08T00:00:00Z".into(),
    })?;
    Ok(())
}

#[tokio::main(flavor="current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out = PathBuf::from(std::env::args_os().nth(1).ok_or("Explicit owned fixture directory required")?);
    std::fs::create_dir_all(&out)?;
    let registry_path = out.join("registry.db");
    if registry_path.exists() { return Err("Fresh owned fixture required; no retry/reclaim".into()); }
    let registry = LibraryRegistry::open_at(&registry_path)?;
    for name in ["owner", "other", "no-index"] {
        let root = out.join(name);
        std::fs::create_dir(&root)?;
        registry.register(&root, name)?;
        if name != "no-index" {
            seed_index(&root,name)?;
        }
    }
    let root = out.join("owner");
    let api = PumasApi::builder(&root).with_registry(registry.clone()).with_hf_client(false)
        .with_process_manager(false).with_connectivity_probe(false).build().await?;
    // Owner initialization legitimately removes disappeared index paths. Seed the
    // controlled, explicitly non-executable index row after that reconciliation.
    seed_index(&root,"owner")?;
    api.start_ipc_server().await?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let endpoint = format!("http://127.0.0.1:{}", listener.local_addr()?.port());
    let mut build = PumasBuildInfo::library();
    build.protocols.push(ProtocolAdvertisement{name:"pumas.local-http".into(),versions:vec![1]});
    build.schemas.push(SchemaAdvertisement{name:"pumas.http-advertisement".into(),version:HTTP_ADVERTISEMENT_SCHEMA_VERSION});
    let mut registration = api.prepare_http_service(LoopbackHttpEndpoint::parse(&endpoint)?,build)?;
    let original = Arc::new(serde_json::to_value(registration.description())?);
    let fixture_out = out.clone();
    let http_original = original.clone();
    let http = tokio::spawn(async move {
        let mut clients = Vec::new();
        loop {
            tokio::select! {
                accepted = listener.accept() => {
                    let (mut stream,_) = accepted?;
                    let out = fixture_out.clone();
                    let descriptor = http_original.clone();
                    clients.push(tokio::spawn(async move {
                        let mut bytes = [0u8;8192];
                        let n = stream.read(&mut bytes).await?;
                        let line = String::from_utf8_lossy(&bytes[..n]).lines().next().unwrap_or("").to_owned();
                        writeln!(OpenOptions::new().create(true).append(true).open(out.join("requests.jsonl"))?,"{}",json!({"request":line}))?;
                        let mode = std::fs::read_to_string(out.join("mode")).unwrap_or_default();
                        let mut value: Value = (*descriptor).clone();
                        if mode.trim()=="hold" {
                            std::fs::write(out.join("http-entered"),b"entered")?;
                            while std::fs::read_to_string(out.join("mode")).unwrap_or_default().trim()=="hold" && !out.join("stop").exists() {
                                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
                            }
                        }
                        if mode.trim()=="wrong-service" {value["service_generation"]=json!("changed-service");}
                        if mode.trim()=="wrong-core" {value["instance"]["generation"]=json!("changed-core");}
                        let ok = line.starts_with("GET /.well-known/pumas HTTP/");
                        let body = if ok {serde_json::to_vec(&value)?}else{b"{\"error\":\"Owned fixture refuses models, inference, startup and acquisition\"}".to_vec()};
                        let header = format!("HTTP/1.1 {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",if ok{"200 OK"}else{"405 Method Not Allowed"},body.len());
                        let _ = stream.write_all(header.as_bytes()).await;
                        let _ = stream.write_all(&body).await;
                        Ok::<(),Box<dyn std::error::Error+Send+Sync>>(())
                    }));
                }
                _ = tokio::time::sleep(std::time::Duration::from_millis(25)) => {
                    if fixture_out.join("stop").exists() {break;}
                }
            }
        }
        drop(listener);
        for client in clients {client.await??;}
        Ok::<(),Box<dyn std::error::Error+Send+Sync>>(())
    });
    registration.publish()?;
    let library = registry.get_by_path(&root)?.ok_or("Owned fixture library absent")?;
    std::fs::write(out.join("ready.json"),serde_json::to_vec_pretty(&json!({
        "scope":"Original pinned SDK owner/core IPC; authored HTTP descriptor responder; controlled local indexes, no model runtime",
        "producer_head":"ab9890fe3248ed7c435b958cded0b131b0700a35",
        "registry":registry_path,"selected":{"id":library.id,"root":root},"service":*original,"endpoint":endpoint,
    }))?)?;
    println!("OWNED_FIXTURE_READY={}",out.join("ready.json").display());
    while !out.join("stop").exists() {
        let command = out.join("index-command");
        if command.exists() {
            let action = std::fs::read_to_string(&command)?;
            let index = ModelIndex::new(root.join("shared-resources/models/models.db"))?;
            for n in 0..64 {
                let id = format!("controlled-overflow-{n:03}");
                if action.trim()=="oversize" {seed_record(&root,"owner",&id)?;}
                else if action.trim()=="restore" {index.delete(&id)?;}
                else {return Err("Unsupported owned index fixture action".into());}
            }
            std::fs::remove_file(command)?;
            std::fs::write(out.join("index-completed"),action)?;
        }
        tokio::time::sleep(std::time::Duration::from_millis(25)).await;
    }
    registration.revoke()?;
    http.await?.map_err(|e|e.to_string())?;
    registration.complete_shutdown(Ok(()))?;
    api.shutdown_instance().await?;
    std::fs::write(out.join("shutdown.json"),serde_json::to_vec_pretty(&json!({"ordered_http_and_core_shutdown":true,"remaining_instances":registry.list_instances()?.len()}))?)?;
    Ok(())
}
