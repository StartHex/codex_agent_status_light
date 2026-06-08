import { invoke } from "@tauri-apps/api/core";
import type { AppSettings, LogEntry, RuntimeSnapshot } from "./types";

export function getSettings(): Promise<AppSettings> {
  return invoke("get_settings");
}

export function saveSettings(settings: AppSettings): Promise<AppSettings> {
  return invoke("save_settings", { settings });
}

export function refreshStatus(): Promise<RuntimeSnapshot> {
  return invoke("refresh_status");
}

export function getSnapshot(): Promise<RuntimeSnapshot | null> {
  return invoke("get_snapshot");
}

export function setManualMode(mode: string): Promise<RuntimeSnapshot> {
  return invoke("set_manual_mode", { mode });
}

export function getDiagnostics(): Promise<LogEntry[]> {
  return invoke("get_diagnostics");
}
