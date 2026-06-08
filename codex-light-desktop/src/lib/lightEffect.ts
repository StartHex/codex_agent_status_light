import type { LightEffect, LightMode, RuntimeSnapshot } from "./types";

const modeLabels: Record<string, string> = {
  off: "Off",
  thinking: "Thinking",
  busy: "Busy",
  ai: "AI Edit",
  yellow: "Waiting",
  green: "Green",
  success: "Success",
  red: "Red",
  error: "Error",
  traffic: "Traffic",
  alarm: "Alarm",
  demo: "Demo",
};

export function normalizeMode(mode: string | undefined | null): LightMode {
  const value = String(mode || "off").toLowerCase();
  if (
    [
      "off",
      "thinking",
      "busy",
      "ai",
      "yellow",
      "green",
      "success",
      "red",
      "error",
      "traffic",
      "alarm",
      "demo",
    ].includes(value)
  ) {
    return value as LightMode;
  }
  return "unknown";
}

export function effectForMode(modeInput: string | undefined | null): LightEffect {
  const mode = normalizeMode(modeInput);
  switch (mode) {
    case "off":
      return { kind: "static", mode, label: "Off", color: "gray", frameIntervalMs: 0, activeLamp: "none" };
    case "green":
    case "success":
      return { kind: "static", mode, label: modeLabels[mode], color: "green", frameIntervalMs: 0, activeLamp: "green" };
    case "yellow":
      return { kind: "static", mode, label: "Waiting", color: "yellow", frameIntervalMs: 0, activeLamp: "yellow" };
    case "red":
      return { kind: "static", mode, label: "Red", color: "red", frameIntervalMs: 0, activeLamp: "red" };
    case "error":
    case "alarm":
      return { kind: "animated", mode, label: modeLabels[mode], color: "red", frameIntervalMs: 360, activeLamp: "red" };
    case "busy":
      return { kind: "animated", mode, label: "Busy", color: "yellow", frameIntervalMs: 420, activeLamp: "yellow" };
    case "ai":
      return { kind: "animated", mode, label: "AI Edit", color: "blue", frameIntervalMs: 420, activeLamp: "blue" };
    case "thinking":
    case "traffic":
    case "demo":
      return { kind: "animated", mode, label: modeLabels[mode], color: "mixed", frameIntervalMs: 420, activeLamp: "all" };
    default:
      return { kind: "unknown", mode: "unknown", label: "Unknown", color: "gray", frameIntervalMs: 0, activeLamp: "none" };
  }
}

export function effectForSnapshot(snapshot: RuntimeSnapshot | null): LightEffect {
  if (!snapshot || snapshot.connection === "error" || snapshot.connection === "unauthorized") {
    return {
      kind: "disconnected",
      mode: "unknown",
      label: snapshot?.connection === "unauthorized" ? "Unauthorized" : "Disconnected",
      color: "gray",
      frameIntervalMs: 0,
      activeLamp: "none",
    };
  }
  return effectForMode(snapshot.status.mode);
}

export function activeCount(snapshot: RuntimeSnapshot | null): number {
  const payloadCount = snapshot?.status.payload?.active_count;
  if (typeof payloadCount === "number") return payloadCount;
  const sessions = snapshot?.status.active_sessions;
  return sessions ? Object.keys(sessions).length : 0;
}
