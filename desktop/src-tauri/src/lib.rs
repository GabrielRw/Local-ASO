//! Local ASO desktop shell.
//!
//! The whole product runs in the bundled Python server (`aso dashboard`). This shell:
//! 1. starts it on a free loopback port (`--port 0`) with no browser and no MCP,
//! 2. waits for its `LOCAL_ASO_READY <url>` stdout line (a contract with
//!    `local_aso_tracker.web.server.serve_dashboard`), then points the window at it,
//! 3. opens any non-local link in the user's default browser,
//! 4. sends SIGTERM on quit so the server stops its workers and closes SQLite cleanly.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

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
