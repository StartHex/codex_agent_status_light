import { useCallback, useEffect, useMemo, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleOff,
  Cog,
  Gauge,
  History,
  MonitorCog,
  Power,
  RefreshCw,
  Save,
  Server,
  Settings,
  TerminalSquare,
  TrafficCone,
  Zap,
} from "lucide-react";
import { activeCount, effectForSnapshot } from "./lib/lightEffect";
import { getDiagnostics, getSettings, getSnapshot, refreshStatus, saveSettings, setManualMode } from "./lib/tauriApi";
import type { AppSettings, LogEntry, RuntimeSnapshot } from "./lib/types";

type Tab = "status" | "device" | "settings";

const defaultSettings: AppSettings = {
  server_url: "http://127.0.0.1:8765",
  token: "",
  poll_interval_ms: 1000,
  error_interval_ms: 5000,
  launch_minimized: false,
};

function TrafficLight({ snapshot }: { snapshot: RuntimeSnapshot | null }) {
  const effect = effectForSnapshot(snapshot);
  const active = effect.activeLamp;
  const className = `traffic-light effect-${effect.color} mode-${effect.mode} ${effect.kind === "animated" ? "is-animated" : ""}`;
  return (
    <div className={className} aria-label={effect.label}>
      <div className={`lamp lamp-red ${active === "red" || active === "all" ? "on" : ""}`} />
      <div className={`lamp lamp-yellow ${active === "yellow" || active === "all" ? "on" : ""}`} />
      <div className={`lamp lamp-green ${active === "green" || active === "all" ? "on" : ""}`} />
      {active === "blue" ? <div className="ai-glow" /> : null}
    </div>
  );
}

function StatusPill({ label, value, tone = "neutral" }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`status-pill tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AppTopBar({ onRefresh, refreshing }: { onRefresh: () => void; refreshing: boolean }) {
  return (
    <header className="topbar" data-tauri-drag-region>
      <div className="brand" data-tauri-drag-region>
        <div className="brand-mark">
          <span />
          <span />
          <span />
        </div>
        <div>
          <div className="brand-title">CODEXLIGHT</div>
          <div className="brand-subtitle">Relay Status Console</div>
        </div>
      </div>
      <button className="icon-button" onClick={onRefresh} title="刷新状态" type="button">
        <RefreshCw size={18} className={refreshing ? "spin" : ""} />
      </button>
    </header>
  );
}

function StatusDashboard({
  snapshot,
  logs,
  onManual,
  manualBusy,
}: {
  snapshot: RuntimeSnapshot | null;
  logs: LogEntry[];
  onManual: (mode: string) => void;
  manualBusy: boolean;
}) {
  const effect = effectForSnapshot(snapshot);
  const count = activeCount(snapshot);
  const status = snapshot?.status;
  const connectionTone = snapshot?.connection === "connected" ? "good" : snapshot?.connection === "unauthorized" ? "bad" : "warn";

  return (
    <main className="dashboard-grid">
      <section className="panel current-panel">
        <div className="panel-heading">
          <TrafficCone size={18} />
          <span>当前灯效</span>
        </div>
        <div className="light-stage">
          <TrafficLight snapshot={snapshot} />
          <div className="light-meta">
            <div className="mode-name">{effect.label}</div>
            <div className="mode-detail">mode: {status?.mode || "unknown"}</div>
          </div>
        </div>
        <div className="manual-grid">
          {["off", "green", "yellow", "red", "thinking", "busy", "ai", "error"].map((mode) => (
            <button key={mode} type="button" className={`mode-button mode-${mode}`} onClick={() => onManual(mode)} disabled={manualBusy}>
              {mode === "off" ? <Power size={16} /> : mode === "ai" ? <Zap size={16} /> : <Activity size={16} />}
              <span>{mode}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <Server size={18} />
          <span>Relay 状态</span>
        </div>
        <div className="metric-stack">
          <StatusPill label="连接" value={snapshot?.connection || "idle"} tone={connectionTone} />
          <StatusPill label="seq" value={String(status?.seq ?? "--")} />
          <StatusPill label="active sessions" value={String(count)} tone={count > 0 ? "active" : "neutral"} />
          <StatusPill label="source" value={String(status?.source || "--")} />
          <StatusPill label="event" value={String(status?.event || "--")} />
        </div>
        {snapshot?.message ? <div className="inline-error">{snapshot.message}</div> : null}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <MonitorCog size={18} />
          <span>Active Sessions</span>
        </div>
        <div className="session-list">
          {status?.active_sessions && Object.entries(status.active_sessions).length > 0 ? (
            Object.entries(status.active_sessions).map(([key, value]) => (
              <div className="session-row" key={key}>
                <span>{key}</span>
                <code>{typeof value === "object" ? JSON.stringify(value).slice(0, 140) : String(value)}</code>
              </div>
            ))
          ) : (
            <div className="empty-state">没有活跃 session</div>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <History size={18} />
          <span>诊断日志</span>
        </div>
        <div className="log-list">
          {logs.slice(0, 10).map((entry, index) => (
            <div className={`log-row level-${entry.level}`} key={`${entry.ts}-${index}`}>
              <span>{entry.ts}</span>
              <strong>{entry.level}</strong>
              <p>{entry.message}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function DevicePanel() {
  return (
    <main className="single-column">
      <section className="panel">
        <div className="panel-heading">
          <TerminalSquare size={18} />
          <span>硬件 Driver</span>
        </div>
        <div className="device-note">
          <CheckCircle2 size={22} />
          <div>
            <h2>GUI 和硬件 driver 完全独立</h2>
            <p>这个 GUI 不扫描串口、不写串口、不启动或停止 driver。硬件灯由仓库现有的 poller/driver 继续负责。</p>
          </div>
        </div>
        <div className="command-box">
          <code>python3 codex-light-bundle/codex_light_http_client.py poll</code>
          <code>CODEX_LIGHT_DRIVER=serial CODEX_LIGHT_SERIAL_PORT=/dev/cu.usbmodem1101</code>
        </div>
      </section>
    </main>
  );
}

function SettingsPanel({
  settings,
  onChange,
  onSave,
  saving,
}: {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
  onSave: () => void;
  saving: boolean;
}) {
  return (
    <main className="single-column">
      <section className="panel settings-panel">
        <div className="panel-heading">
          <Cog size={18} />
          <span>GUI 设置</span>
        </div>
        <label>
          <span>Server URL</span>
          <input value={settings.server_url} onChange={(event) => onChange({ ...settings, server_url: event.target.value })} />
        </label>
        <label>
          <span>Token</span>
          <input
            type="password"
            value={settings.token}
            onChange={(event) => onChange({ ...settings, token: event.target.value })}
            placeholder="可选"
          />
        </label>
        <label>
          <span>Poll interval (ms)</span>
          <input
            type="number"
            min={300}
            step={100}
            value={settings.poll_interval_ms}
            onChange={(event) => onChange({ ...settings, poll_interval_ms: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>Error interval (ms)</span>
          <input
            type="number"
            min={1000}
            step={500}
            value={settings.error_interval_ms}
            onChange={(event) => onChange({ ...settings, error_interval_ms: Number(event.target.value) })}
          />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={settings.launch_minimized}
            onChange={(event) => onChange({ ...settings, launch_minimized: event.target.checked })}
          />
          <span>启动后隐藏主窗口</span>
        </label>
        <button type="button" className="primary-button" onClick={onSave} disabled={saving}>
          <Save size={16} />
          <span>{saving ? "保存中" : "保存设置"}</span>
        </button>
      </section>
    </main>
  );
}

function BottomDock({ tab, onChange }: { tab: Tab; onChange: (tab: Tab) => void }) {
  const items: Array<{ id: Tab; label: string; icon: JSX.Element }> = [
    { id: "status", label: "Status", icon: <Gauge size={18} /> },
    { id: "device", label: "Device", icon: <TerminalSquare size={18} /> },
    { id: "settings", label: "Settings", icon: <Settings size={18} /> },
  ];
  return (
    <nav className="bottom-dock">
      {items.map((item) => (
        <button key={item.id} type="button" className={tab === item.id ? "active" : ""} onClick={() => onChange(item.id)}>
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("status");
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);

  const reloadLogs = useCallback(async () => {
    setLogs(await getDiagnostics());
  }, []);

  const reloadStatus = useCallback(async () => {
    setRefreshing(true);
    try {
      setSnapshot(await refreshStatus());
      await reloadLogs();
    } finally {
      setRefreshing(false);
    }
  }, [reloadLogs]);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => setSettings(defaultSettings));
    reloadStatus().catch(() => undefined);
    const unlistenPromise = listen<RuntimeSnapshot>("status-updated", (event) => {
      setSnapshot(event.payload);
      reloadLogs().catch(() => undefined);
    });
    const snapshotInterval = window.setInterval(() => {
      getSnapshot()
        .then((latest) => {
          if (latest) {
            setSnapshot(latest);
          }
        })
        .catch(() => undefined);
    }, 1000);
    return () => {
      window.clearInterval(snapshotInterval);
      unlistenPromise.then((unlisten) => unlisten()).catch(() => undefined);
    };
  }, [reloadLogs, reloadStatus]);

  const topTone = useMemo(() => {
    if (!snapshot) return "warn";
    if (snapshot.connection === "connected") return "good";
    if (snapshot.connection === "unauthorized") return "bad";
    return "warn";
  }, [snapshot]);

  async function handleManual(mode: string) {
    setManualBusy(true);
    try {
      setSnapshot(await setManualMode(mode));
      await reloadLogs();
    } finally {
      setManualBusy(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      setSettings(await saveSettings(settings));
      await reloadStatus();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="app-shell">
      <AppTopBar onRefresh={reloadStatus} refreshing={refreshing} />
      <section className="meta-strip">
        <StatusPill label="mode" value={snapshot?.status.mode || "--"} tone={topTone} />
        <StatusPill label="server" value={snapshot?.connection || "idle"} tone={topTone} />
        <StatusPill label="active" value={String(activeCount(snapshot))} />
        <StatusPill label="updated" value={snapshot?.status.updated_at || "--"} />
      </section>
      {snapshot?.connection === "error" ? (
        <div className="banner">
          <AlertCircle size={18} />
          <span>{snapshot.message || "Relay 连接失败"}</span>
        </div>
      ) : null}
      {tab === "status" ? <StatusDashboard snapshot={snapshot} logs={logs} onManual={handleManual} manualBusy={manualBusy} /> : null}
      {tab === "device" ? <DevicePanel /> : null}
      {tab === "settings" ? <SettingsPanel settings={settings} onChange={setSettings} onSave={handleSave} saving={saving} /> : null}
      <BottomDock tab={tab} onChange={setTab} />
    </div>
  );
}
