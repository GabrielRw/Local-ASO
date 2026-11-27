//! Local ASO desktop shell.
//!
//! The whole product runs in the bundled Python server (`aso dashboard`). This shell:
//! 1. starts it on a free loopback port (`--port 0`) with no browser and no MCP,
//! 2. waits for its `LOCAL_ASO_READY <url>` stdout line (a contract with
//!    `local_aso_tracker.web.server.serve_dashboard`), then points the window at it,
//! 3. opens any non-local link in the user's default browser,
//! 4. sends SIGTERM on quit so the server stops its workers and closes SQLite cleanly,
//! 5. once the dashboard is up, checks this repository's GitHub Releases for a newer
//!    version signed with our updater key (opt-out in `desktop.json`), and offers to
//!    install it. The web page gets no Tauri commands; all of this runs in Rust.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_updater::UpdaterExt;

const READY_PREFIX: &str = "LOCAL_ASO_READY ";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);
const SHUTDOWN_GRACE: Duration = Duration::from_secs(6);

struct ServerProcess(Mutex<Option<Child>>);

/// The bundled server, or a development override.
///
/// `LOCAL_ASO_SERVER_CMD` runs a shell command instead (for example
/// `uv run --project /path/to/repo aso`), so the shell can be developed
/// without rebuilding the frozen server.
fn server_command(app: &AppHandle) -> Result<Command, String> {
    let args = ["dashboard", "--no-open", "--no-mcp", "--port", "0"];
    if let Ok(custom) = std::env::var("LOCAL_ASO_SERVER_CMD") {
        let mut command = Command::new("/bin/sh");
        command.arg("-c").arg(format!("exec {} {}", custom, args.join(" ")));
        return Ok(command);
    }
    let resources = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Cannot locate the app resources: {error}"))?;
    let binary: PathBuf = resources.join("aso-server").join("aso-server");
    if !binary.is_file() {
        return Err(format!("The bundled server is missing at {}", binary.display()));
    }
    let mut command = Command::new(binary);
    command.args(args);
    Ok(command)
}

/// The data folder the server uses (`ASO_DATA_DIR`, else `~/.local-aso-tracker`).
fn data_dir() -> Option<PathBuf> {
    if let Ok(custom) = std::env::var("ASO_DATA_DIR") {
        return Some(PathBuf::from(custom));
    }
    std::env::var("HOME").ok().map(|home| PathBuf::from(home).join(".local-aso-tracker"))
}

/// `desktop.json` is written by the server (Settings → Licence & updates); default on.
fn update_checks_enabled() -> bool {
    let Some(path) = data_dir().map(|dir| dir.join("desktop.json")) else { return true };
    let Ok(text) = std::fs::read_to_string(path) else { return true };
    serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|value| value.get("checkUpdates").and_then(|flag| flag.as_bool()))
        .unwrap_or(true)
}

/// Check for a signed update and offer to install it. Never blocks or breaks launch.
fn check_for_update(app: AppHandle) {
    if !update_checks_enabled() {
        return;
    }
    thread::spawn(move || {
        if let Err(error) = tauri::async_runtime::block_on(offer_update(&app)) {
            eprintln!("Local ASO update check failed: {error}");
        }
    });
}

async fn offer_update(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    #[allow(unused_mut)]
    let mut builder = app.updater_builder();
    // Development builds can point at a local feed and key to exercise the flow;
    // release builds only ever use the endpoint and key in tauri.conf.json.
    #[cfg(debug_assertions)]
    {
        if let Ok(endpoint) = std::env::var("LOCAL_ASO_UPDATE_ENDPOINT") {
            builder = builder.endpoints(vec![Url::parse(&endpoint)?])?;
        }
        if let Ok(pubkey) = std::env::var("LOCAL_ASO_UPDATE_PUBKEY") {
            builder = builder.pubkey(pubkey);
        }
    }
    let Some(update) = builder.build()?.check().await? else { return Ok(()) };
    let notes = update.body.clone().unwrap_or_default();
    let message = format!(
        "Local ASO {} is available (you have {}).\n\n{}",
        update.version,
        update.current_version,
        notes.trim()
    );
    #[cfg(debug_assertions)]
    let accepted = std::env::var("LOCAL_ASO_UPDATE_AUTO_ACCEPT").is_ok()
        || ask_to_install(app, &message);
    #[cfg(not(debug_assertions))]
    let accepted = ask_to_install(app, &message);
    if !accepted {
        return Ok(());
    }
    update.download_and_install(|_, _| {}, || {}).await?;
    stop_server(app);
    app.restart();
}

fn ask_to_install(app: &AppHandle, message: &str) -> bool {
    app.dialog()
        .message(message)
        .title("Update available")
        .kind(MessageDialogKind::Info)
        .buttons(MessageDialogButtons::OkCancelCustom("Install and Restart".into(), "Later".into()))
        .blocking_show()
}

fn is_local(url: &Url) -> bool {
    match url.scheme() {
        "tauri" | "about" | "data" | "blob" => true,
        "http" | "https" => matches!(url.host_str(), Some("127.0.0.1") | Some("localhost") | Some("tauri.localhost")),
        _ => false,
    }
}

fn open_externally(url: &Url) {
    if matches!(url.scheme(), "http" | "https" | "mailto") {
        let _ = Command::new("open").arg(url.as_str()).spawn();
    }
}

fn show_error(window: &WebviewWindow, message: &str) {
    let escaped = message.replace('\\', "\\\\").replace('\'', "\\'").replace('\n', "\\n");
    let _ = window.eval(&format!(
        "var s=document.getElementById('status');if(s){{s.className='error';s.textContent='{escaped}';}}"
    ));
}

/// Spawn the server and report its URL (or an error) once, then keep draining stdout.
fn start_server(app: &AppHandle) -> Result<(Child, mpsc::Receiver<Result<String, String>>), String> {
    let mut command = server_command(app)?;
    // Tells the server it runs inside the Mac app (licence gate, version in Settings).
    command
        .env("LOCAL_ASO_DESKTOP", "1")
        .env("LOCAL_ASO_VERSION", app.package_info().version.to_string());
    command.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::inherit());
    let mut child = command
        .spawn()
        .map_err(|error| format!("Could not start the local server: {error}"))?;
    let stdout = child.stdout.take().ok_or("The local server has no output stream")?;
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut sent = false;
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            if !sent {
                if let Some(url) = line.strip_prefix(READY_PREFIX) {
                    let _ = sender.send(Ok(url.trim().to_string()));
                    sent = true;
                }
            }
        }
        if !sent {
            let _ = sender.send(Err("The local server stopped before it was ready.".into()));
        }
    });
    Ok((child, receiver))
}

fn stop_server(app: &AppHandle) {
    let Some(state) = app.try_state::<ServerProcess>() else { return };
    let Some(mut child) = state.0.lock().ok().and_then(|mut guard| guard.take()) else { return };
    #[cfg(unix)]
    unsafe {
        libc::kill(child.id() as libc::pid_t, libc::SIGTERM);
    }
    let deadline = Instant::now() + SHUTDOWN_GRACE;
    while Instant::now() < deadline {
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    let _ = child.wait();
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .manage(ServerProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Local ASO")
                .inner_size(1320.0, 860.0)
                .min_inner_size(960.0, 640.0)
                .on_navigation(|url| {
                    if is_local(url) {
                        true
                    } else {
                        open_externally(url);
                        false
                    }
                })
                .on_new_window(|url, _features| {
                    open_externally(&url);
                    NewWindowResponse::Deny
                })
                .build()?;

            match start_server(&handle) {
                Ok((child, ready)) => {
                    if let Some(state) = handle.try_state::<ServerProcess>() {
                        if let Ok(mut guard) = state.0.lock() {
                            *guard = Some(child);
                        }
                    }
                    thread::spawn(move || match ready.recv_timeout(STARTUP_TIMEOUT) {
                        Ok(Ok(url)) => match Url::parse(&url) {
                            Ok(parsed) => {
                                let _ = window.navigate(parsed);
                                check_for_update(window.app_handle().clone());
                            }
                            Err(error) => show_error(&window, &format!("Invalid server address: {error}")),
                        },
                        Ok(Err(message)) => show_error(&window, &message),
                        Err(_) => show_error(&window, "The local server did not start in time."),
                    });
                }
                Err(message) => show_error(&window, &message),
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Local ASO app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_server(handle);
        }
    });
}
