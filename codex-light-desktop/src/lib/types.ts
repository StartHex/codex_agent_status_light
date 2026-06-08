export type LightMode =
  | "off"
  | "thinking"
  | "busy"
  | "ai"
  | "yellow"
  | "green"
  | "red"
  | "success"
  | "error"
  | "traffic"
  | "alarm"
  | "demo"
  | "unknown";

export type ConnectionState = "idle" | "connected" | "error" | "unauthorized";

export interface RuntimeStatus {
  mode: string;
  source?: string | null;
  event?: string | null;
  tool_name?: string | null;
  payload?: Record<string, unknown>;
  active_sessions?: Record<string, unknown>;
  seq?: number;
  updated_at?: string | null;
  manual?: boolean;
}

export interface RuntimeSnapshot {
  status: RuntimeStatus;
  connection: ConnectionState;
  message?: string | null;
  fetched_at: string;
}

export interface AppSettings {
  server_url: string;
  token: string;
  poll_interval_ms: number;
  error_interval_ms: number;
  launch_minimized: boolean;
}

export interface LightEffect {
  kind: "static" | "animated" | "disconnected" | "unknown";
  mode: LightMode;
  label: string;
  color: "gray" | "green" | "yellow" | "red" | "blue" | "mixed";
  frameIntervalMs: number;
  activeLamp: "red" | "yellow" | "green" | "blue" | "all" | "none";
}

export interface LogEntry {
  ts: string;
  level: "info" | "warn" | "error";
  message: string;
}
