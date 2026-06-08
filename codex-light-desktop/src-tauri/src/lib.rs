use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};

const TRAY_ID: &str = "codexlight-tray";
const MENU_OPEN: &str = "open";
const MENU_REFRESH: &str = "refresh";
const MENU_QUIT: &str = "quit";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AppSettings {
    server_url: String,
    token: String,
    poll_interval_ms: u64,
    error_interval_ms: u64,
    launch_minimized: bool,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            server_url: "http://127.0.0.1:8765".to_string(),
            token: String::new(),
            poll_interval_ms: 1000,
            error_interval_ms: 5000,
            launch_minimized: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RuntimeStatus {
    mode: String,
    source: Option<String>,
    event: Option<String>,
    tool_name: Option<String>,
    payload: Value,
    active_sessions: Value,
    seq: u64,
    updated_at: Option<String>,
    manual: Option<bool>,
}

impl Default for RuntimeStatus {
    fn default() -> Self {
        Self {
            mode: "off".to_string(),
            source: Some("gui".to_string()),
            event: Some("startup".to_string()),
            tool_name: None,
            payload: json!({}),
            active_sessions: json!({}),
            seq: 0,
            updated_at: None,
            manual: Some(false),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
enum ConnectionState {
    Idle,
    Connected,
    Error,
    Unauthorized,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RuntimeSnapshot {
    status: RuntimeStatus,
    connection: ConnectionState,
    message: Option<String>,
    fetched_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LogEntry {
    ts: String,
    level: String,
    message: String,
}

#[derive(Debug, Default)]
struct InnerState {
    settings: AppSettings,
    snapshot: Option<RuntimeSnapshot>,
    logs: Vec<LogEntry>,
    current_frame: usize,
    quit_requested: bool,
}

struct AppState(Mutex<InnerState>);

#[derive(Debug, Deserialize)]
struct ServerResponse {
    status: RuntimeStatus,
}

fn unix_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_else(|_| Duration::from_secs(0))
        .as_millis()
}

fn now_string() -> String {
    let secs = unix_ms() / 1000;
    secs.to_string()
}

fn config_dir() -> Result<PathBuf, String> {
    let base = dirs_next::config_dir().ok_or_else(|| "cannot find config directory".to_string())?;
    Ok(base.join("CodexLight"))
}

fn settings_path() -> Result<PathBuf, String> {
    Ok(config_dir()?.join("settings.json"))
}

fn load_settings() -> AppSettings {
    let Ok(path) = settings_path() else {
        return AppSettings::default();
    };
    let Ok(raw) = fs::read_to_string(path) else {
        return AppSettings::default();
    };
    serde_json::from_str(&raw).unwrap_or_default()
}

fn store_settings(settings: &AppSettings) -> Result<(), String> {
    let path = settings_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let data = serde_json::to_string_pretty(settings).map_err(|err| err.to_string())?;
    fs::write(path, data).map_err(|err| err.to_string())
}

fn push_log(state: &mut InnerState, level: &str, message: impl Into<String>) {
    state.logs.insert(
        0,
        LogEntry {
            ts: now_string(),
            level: level.to_string(),
            message: message.into(),
        },
    );
    state.logs.truncate(200);
}

fn active_count(status: &RuntimeStatus) -> usize {
    status
        .payload
        .get("active_count")
        .and_then(Value::as_u64)
        .map(|value| value as usize)
        .or_else(|| status.active_sessions.as_object().map(|items| items.len()))
        .unwrap_or(0)
}

fn normalized_mode(mode: &str) -> &str {
    match mode {
        "off" | "thinking" | "busy" | "ai" | "yellow" | "green" | "success" | "red" | "error"
        | "traffic" | "alarm" | "demo" => mode,
        _ => "unknown",
    }
}

fn tray_icon_name(snapshot: Option<&RuntimeSnapshot>, frame: usize) -> &'static str {
    let Some(snapshot) = snapshot else {
        return "disconnected";
    };
    match snapshot.connection {
        ConnectionState::Connected => match normalized_mode(snapshot.status.mode.as_str()) {
            "off" => "off",
            "green" | "success" => "green",
            "yellow" => "yellow",
            "red" => "red",
            "error" | "alarm" => {
                if frame % 2 == 0 {
                    "red"
                } else {
                    "off"
                }
            }
            "busy" => {
                if frame % 2 == 0 {
                    "yellow"
                } else {
                    "off"
                }
            }
            "ai" => {
                if frame % 2 == 0 {
                    "ai"
                } else {
                    "off"
                }
            }
            "thinking" | "traffic" | "demo" => match frame % 3 {
                0 => "red",
                1 => "yellow",
                _ => "green",
            },
            _ => "disconnected",
        },
        ConnectionState::Unauthorized | ConnectionState::Error | ConnectionState::Idle => {
            "disconnected"
        }
    }
}

fn tray_image(name: &str) -> Result<Image<'static>, String> {
    let bytes: &'static [u8] = match name {
        "green" => include_bytes!("../icons/tray/green.png"),
        "yellow" => include_bytes!("../icons/tray/yellow.png"),
        "red" => include_bytes!("../icons/tray/red.png"),
        "ai" => include_bytes!("../icons/tray/ai.png"),
        "off" => include_bytes!("../icons/tray/off.png"),
        _ => include_bytes!("../icons/tray/disconnected.png"),
    };
    Image::from_bytes(bytes).map_err(|err| err.to_string())
}

fn tray_tooltip(snapshot: Option<&RuntimeSnapshot>) -> String {
    let Some(snapshot) = snapshot else {
        return "CodexLight: disconnected".to_string();
    };
    format!(
        "CodexLight: {} | {:?} | active {}",
        snapshot.status.mode,
        snapshot.connection,
        active_count(&snapshot.status)
    )
}

fn build_tray_menu(
    app: &AppHandle,
    snapshot: Option<&RuntimeSnapshot>,
) -> Result<Menu<tauri::Wry>, String> {
    let menu = Menu::new(app).map_err(|err| err.to_string())?;
    let summary = MenuItem::with_id(app, "summary", tray_tooltip(snapshot), false, None::<&str>)
        .map_err(|err| err.to_string())?;
    let open = MenuItem::with_id(app, MENU_OPEN, "Open Dashboard", true, None::<&str>)
        .map_err(|err| err.to_string())?;
    let refresh = MenuItem::with_id(app, MENU_REFRESH, "Refresh Now", true, None::<&str>)
        .map_err(|err| err.to_string())?;
    let quit = MenuItem::with_id(app, MENU_QUIT, "Quit", true, None::<&str>)
        .map_err(|err| err.to_string())?;
    let sep1 = PredefinedMenuItem::separator(app).map_err(|err| err.to_string())?;
    let sep2 = PredefinedMenuItem::separator(app).map_err(|err| err.to_string())?;
    menu.append(&summary).map_err(|err| err.to_string())?;
    menu.append(&sep1).map_err(|err| err.to_string())?;
    menu.append(&open).map_err(|err| err.to_string())?;
    menu.append(&refresh).map_err(|err| err.to_string())?;
    menu.append(&sep2).map_err(|err| err.to_string())?;
    menu.append(&quit).map_err(|err| err.to_string())?;
    Ok(menu)
}

fn update_tray(app: &AppHandle) {
    let (snapshot, frame) = {
        let state = app.state::<AppState>();
        let guard = state.0.lock().expect("state poisoned");
        (guard.snapshot.clone(), guard.current_frame)
    };
    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        return;
    };
    if let Ok(icon) = tray_image(tray_icon_name(snapshot.as_ref(), frame)) {
        let _ = tray.set_icon(Some(icon));
    }
    let _ = tray.set_tooltip(Some(tray_tooltip(snapshot.as_ref())));
    if let Ok(menu) = build_tray_menu(app, snapshot.as_ref()) {
        let _ = tray.set_menu(Some(menu));
    }
    #[cfg(target_os = "macos")]
    {
        let title = snapshot
            .as_ref()
            .map(|item| item.status.mode.clone())
            .unwrap_or_else(|| "off".to_string());
        let _ = tray.set_title(Some(title));
    }
}

async fn fetch_status(settings: &AppSettings) -> RuntimeSnapshot {
    let client = reqwest::Client::new();
    let url = format!("{}/status", settings.server_url.trim_end_matches('/'));
    let mut req = client.get(url);
    if !settings.token.is_empty() {
        req = req
            .bearer_auth(&settings.token)
            .header("X-Codex-Light-Token", settings.token.clone());
    }
    match req.send().await {
        Ok(resp) if resp.status() == StatusCode::UNAUTHORIZED => RuntimeSnapshot {
            status: RuntimeStatus::default(),
            connection: ConnectionState::Unauthorized,
            message: Some("unauthorized: check token".to_string()),
            fetched_at: now_string(),
        },
        Ok(resp) if resp.status().is_success() => match resp.json::<ServerResponse>().await {
            Ok(data) => RuntimeSnapshot {
                status: data.status,
                connection: ConnectionState::Connected,
                message: None,
                fetched_at: now_string(),
            },
            Err(err) => RuntimeSnapshot {
                status: RuntimeStatus::default(),
                connection: ConnectionState::Error,
                message: Some(format!("invalid status response: {err}")),
                fetched_at: now_string(),
            },
        },
        Ok(resp) => RuntimeSnapshot {
            status: RuntimeStatus::default(),
            connection: ConnectionState::Error,
            message: Some(format!("server returned {}", resp.status())),
            fetched_at: now_string(),
        },
        Err(err) => RuntimeSnapshot {
            status: RuntimeStatus::default(),
            connection: ConnectionState::Error,
            message: Some(err.to_string()),
            fetched_at: now_string(),
        },
    }
}

async fn post_mode(settings: &AppSettings, mode: String) -> RuntimeSnapshot {
    let client = reqwest::Client::new();
    let url = format!("{}/mode", settings.server_url.trim_end_matches('/'));
    let mut req = client.post(url).json(&json!({
        "mode": mode,
        "source": "codexlight-gui",
        "event": "manual"
    }));
    if !settings.token.is_empty() {
        req = req
            .bearer_auth(&settings.token)
            .header("X-Codex-Light-Token", settings.token.clone());
    }
    match req.send().await {
        Ok(resp) if resp.status().is_success() => fetch_status(settings).await,
        Ok(resp) if resp.status() == StatusCode::UNAUTHORIZED => RuntimeSnapshot {
            status: RuntimeStatus::default(),
            connection: ConnectionState::Unauthorized,
            message: Some("unauthorized: check token".to_string()),
            fetched_at: now_string(),
        },
        Ok(resp) => RuntimeSnapshot {
            status: RuntimeStatus::default(),
            connection: ConnectionState::Error,
            message: Some(format!("manual mode failed: {}", resp.status())),
            fetched_at: now_string(),
        },
        Err(err) => RuntimeSnapshot {
            status: RuntimeStatus::default(),
            connection: ConnectionState::Error,
            message: Some(err.to_string()),
            fetched_at: now_string(),
        },
    }
}

async fn refresh_and_store(app: AppHandle) -> RuntimeSnapshot {
    let settings = {
        let state = app.state::<AppState>();
        let guard = state.0.lock().expect("state poisoned");
        guard.settings.clone()
    };
    let snapshot = fetch_status(&settings).await;
    {
        let state = app.state::<AppState>();
        let mut guard = state.0.lock().expect("state poisoned");
        let level = match snapshot.connection {
            ConnectionState::Connected => "info",
            ConnectionState::Unauthorized => "warn",
            ConnectionState::Error | ConnectionState::Idle => "error",
        };
        push_log(
            &mut guard,
            level,
            snapshot.message.clone().unwrap_or_else(|| {
                format!("mode={} seq={}", snapshot.status.mode, snapshot.status.seq)
            }),
        );
        guard.snapshot = Some(snapshot.clone());
    }
    update_tray(&app);
    let _ = app.emit("status-updated", snapshot.clone());
    snapshot
}

fn start_background_poller(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            {
                let state = app.state::<AppState>();
                let mut guard = state.0.lock().expect("state poisoned");
                guard.current_frame = guard.current_frame.wrapping_add(1);
                if guard.quit_requested {
                    break;
                }
            }
            let snapshot = refresh_and_store(app.clone()).await;
            let settings = {
                let state = app.state::<AppState>();
                let guard = state.0.lock().expect("state poisoned");
                guard.settings.clone()
            };
            let delay = match snapshot.connection {
                ConnectionState::Connected => settings.poll_interval_ms.max(300),
                _ => settings.error_interval_ms.max(1000),
            };
            tokio::time::sleep(Duration::from_millis(delay.min(60_000))).await;
        }
    });
}

fn refresh_in_background(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        refresh_and_store(app).await;
    });
}

fn restore_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
    refresh_in_background(app);
}

#[tauri::command]
fn get_settings(state: State<'_, AppState>) -> AppSettings {
    let guard = state.0.lock().expect("state poisoned");
    guard.settings.clone()
}

#[tauri::command]
fn save_settings(
    settings: AppSettings,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<AppSettings, String> {
    let mut normalized = settings;
    normalized.server_url = normalized
        .server_url
        .trim()
        .trim_end_matches('/')
        .to_string();
    if normalized.server_url.is_empty() {
        normalized.server_url = AppSettings::default().server_url;
    }
    normalized.poll_interval_ms = normalized.poll_interval_ms.clamp(300, 60_000);
    normalized.error_interval_ms = normalized.error_interval_ms.clamp(1000, 120_000);
    store_settings(&normalized)?;
    {
        let mut guard = state.0.lock().expect("state poisoned");
        guard.settings = normalized.clone();
        push_log(&mut guard, "info", "settings saved");
    }
    update_tray(&app);
    Ok(normalized)
}

#[tauri::command]
async fn refresh_status(app: AppHandle) -> RuntimeSnapshot {
    refresh_and_store(app).await
}

#[tauri::command]
fn get_snapshot(state: State<'_, AppState>) -> Option<RuntimeSnapshot> {
    state.0.lock().expect("state poisoned").snapshot.clone()
}

#[tauri::command]
async fn set_manual_mode(mode: String, app: AppHandle) -> RuntimeSnapshot {
    let settings = {
        let state = app.state::<AppState>();
        let guard = state.0.lock().expect("state poisoned");
        guard.settings.clone()
    };
    let snapshot = post_mode(&settings, mode).await;
    {
        let state = app.state::<AppState>();
        let mut guard = state.0.lock().expect("state poisoned");
        push_log(
            &mut guard,
            "info",
            format!("manual mode -> {}", snapshot.status.mode),
        );
        guard.snapshot = Some(snapshot.clone());
    }
    update_tray(&app);
    let _ = app.emit("status-updated", snapshot.clone());
    snapshot
}

#[tauri::command]
fn get_diagnostics(state: State<'_, AppState>) -> Vec<LogEntry> {
    state.0.lock().expect("state poisoned").logs.clone()
}

pub fn run() {
    let settings = load_settings();
    tauri::Builder::default()
        .manage(AppState(Mutex::new(InnerState {
            settings,
            snapshot: None,
            logs: Vec::new(),
            current_frame: 0,
            quit_requested: false,
        })))
        .invoke_handler(tauri::generate_handler![
            get_settings,
            save_settings,
            refresh_status,
            get_snapshot,
            set_manual_mode,
            get_diagnostics
        ])
        .setup(|app| {
            let menu = build_tray_menu(app.handle(), None)?;
            let icon = tray_image("disconnected")?;
            TrayIconBuilder::with_id(TRAY_ID)
                .icon(icon)
                .menu(&menu)
                .tooltip("CodexLight")
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        ..
                    } = event
                    {
                        restore_main_window(tray.app_handle());
                    }
                })
                .build(app)?;
            start_background_poller(app.handle().clone());
            Ok(())
        })
        .on_menu_event(|app, event| match event.id().as_ref() {
            MENU_OPEN => restore_main_window(app),
            MENU_REFRESH => {
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    refresh_and_store(app).await;
                });
            }
            MENU_QUIT => {
                let state = app.state::<AppState>();
                state.0.lock().expect("state poisoned").quit_requested = true;
                app.exit(0);
            }
            _ => {}
        })
        .on_window_event(|window, event| match event {
            WindowEvent::CloseRequested { api, .. } => {
                api.prevent_close();
                let _ = window.hide();
            }
            WindowEvent::Focused(true) => {
                refresh_in_background(window.app_handle());
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running CodexLight");
}
