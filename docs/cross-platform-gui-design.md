# CodexLight 跨平台 GUI + 任务栏软件设计文档

## 1. 目标

为 CodexLight 做一个常驻桌面软件，让用户不用手工启动命令行 poller，也能在 Mac、Windows、Linux 上完成：

- 菜单栏/任务栏常驻显示当前 CodexLight 状态。
- 状态栏图标、GUI 主灯效、ESP32 硬件灯使用同一套状态映射。
- GUI 自动轮询 HTTP relay，用同一套 `LightEffect` 逻辑展示窗口灯效和 tray 图标。
- 已有独立 driver 自动轮询 HTTP relay，并把同一套 `LightEffect` 语义转换为 ESP32 串口命令。
- 不接 driver、不接硬件时，GUI 也可以单独作为状态看板使用。
- 提供图形化配置、连接测试、手动控制和日志诊断。
- 支持开机启动、断线重连、单实例运行。

这个 GUI 不替代现有 `codex_light_server.py`，也不替代已经完成的硬件 driver。v1 采用两个独立客户端：

```text
CodexLight GUI
  -> GET /status
  -> RuntimeStatus -> LightEffect -> GUI/tray

codex-light-driver
  -> GET /status
  -> RuntimeStatus -> LightEffect -> ESP32 serial
```

## 2. 现有基础

当前项目已经有三层能力：

```text
Codex / cc-connect hooks
  -> HTTP relay server
  -> local poller
  -> serial / BLE
  -> ESP32-C3 CodexLight
```

已有可复用文件：

| 文件 | 现有职责 | GUI/driver 中的复用方式 |
|---|---|---|
| `codex_light_server.py` | HTTP 状态服务，维护 `mode/seq/active_sessions` | 作为权威状态源；v1 可修复/验证多 session 聚合 |
| `codex_light_http_client.py` | 查询状态、手动写状态、poll、serial/BLE 下发 | 保持 CLI 兼容；协议和灯效映射可抽取到新 core |
| `codex_light_ble.py` | BLE 写入模式 | v1 不接入 GUI，后续 driver 可评估 |
| `cc_connect_light.sh` | cc-connect lifecycle hook 上报 | 不改 |
| `com.codexlight.poller.plist.example` | Mac 后台 poller 示例 | 后续由独立 driver 的开机启动替代 |

## 3. 参考 codex-tools

参考项目：[170-carry/codex-tools](https://github.com/170-carry/codex-tools)

它对 CodexLight 最有价值的不是业务功能，而是桌面软件形态：

- `React + Vite + TypeScript` 做主界面。
- `Tauri 2 + Rust` 做系统托盘、窗口、单实例、开机启动、更新和本地命令。
- macOS 菜单栏使用 template icon，并能显示状态标题。
- Windows/Linux 使用 system tray 菜单。
- 主窗口是一个常驻工具控制台，不是营销页。
- 顶部品牌栏 + 主状态卡片 + 底部 dock/tab 的结构清晰，适合改造成 CodexLight 控制台。
- 支持主题、多语言、后台驻留、更新检查，这些都可以作为后续扩展。

对 CodexLight 的适配原则：

- 保留 `codex-tools` 的桌面壳方向：Tauri、托盘、单实例、开机启动、自动更新。
- 视觉上参考它的轻量半透明控制台、顶部栏、底部 dock、状态卡片，但不要照搬账号/API 代理业务。
- CodexLight 是硬件状态工具，界面要更偏运维控制台：状态清楚、连接清楚、错误清楚。
- GUI 和 driver 是完全独立的两个客户端，只共享协议模型和 `LightEffect` 灯效逻辑。
- 硬件驱动不要放进 GUI。HTTP 展示逻辑在 GUI，串口写入逻辑在 driver。

## 4. 产品形态

### 4.1 常驻任务栏

跨平台映射：

| 平台 | 显示位置 |
|---|---|
| macOS | menu bar status item |
| Windows | system tray |
| Linux | system tray / app indicator |

任务栏图标需要表达当前状态：

| mode | 状态栏图标 | GUI 灯效 | 硬件灯效 |
|---|---|---|---|
| `off` | 灰色空心交通灯 | 灭灯 | 灭灯 |
| `thinking` | 红/黄/绿轮转帧 | 跑马灯/轮转 | 跑马灯/轮转 |
| `busy` | 黄灯脉冲帧 | 黄灯脉冲 | 黄灯脉冲 |
| `ai` | 青/蓝脉冲帧 | 青/蓝脉冲 | 青/蓝脉冲 |
| `yellow` | 黄灯常亮 | 黄灯常亮 | 黄灯常亮 |
| `error` | 红灯快闪或红灯常亮 | 红灯错误态 | 红灯错误态 |
| `success` / `green` | 绿灯常亮 | 绿灯常亮 | 绿灯常亮 |
| `red` | 红灯常亮 | 红灯常亮 | 红灯常亮 |
| 连接失败 | 灰色交通灯 + 斜杠 | disconnected | 不下发新状态 |

实现要求：

- 状态栏图标、GUI 大灯效、硬件灯效都从同一个 `LightEffect` 模型派生，避免三处表现不一致。
- 静态状态使用单张 PNG/icon。
- 动态状态使用 2-4 张帧图，每 300-500ms 切换一次。
- 动画只在 `thinking/busy/ai/error` 等需要动效的状态运行，`off/green/yellow/red` 不跑定时器。
- Linux tray 动画如果兼容性不好，允许降级为静态图标，但 GUI 和硬件仍保持完整灯效。

任务栏菜单：

```text
CodexLight: thinking
Server: connected
Device: serial /dev/cu.usbmodem1101
Active sessions: 2
---
Open Dashboard
Refresh Now
Reconnect Device
---
Send: off
Send: green
Send: yellow
Send: red
Send: thinking
---
Pause Polling
Start at Login [x]
---
Logs
Quit
```

### 4.2 主窗口

主窗口直接进入控制台视图，参考 `codex-tools` 的桌面工具布局：

```text
┌──────────────────────────────────────────────────────────────┐
│  CodexLight                                      refresh icon │
├──────────────────────────────────────────────────────────────┤
│  mode thinking   server connected   device serial   sessions 2│
├───────────────────────────────┬──────────────────────────────┤
│  当前灯效                      │  Relay 状态                   │
│  大号红绿灯状态                │  URL / seq / updated_at        │
│  off/green/yellow/red buttons  │  active_sessions 摘要          │
├───────────────────────────────┼──────────────────────────────┤
│  硬件连接                      │  诊断日志                      │
│  driver / port / scan / test   │  最近 poll/send/error          │
└──────────────────────────────────────────────────────────────┘
             Status      Device      Settings
```

底部 dock/tab 建议：

| Tab | 内容 |
|---|---|
| `Status` | 当前 mode、seq、server/device 连接、active sessions、手动模式 |
| `Device` | 说明硬件由独立 driver 负责，展示可选 driver 配置路径/状态，不作为 GUI 运行依赖 |
| `Settings` | server URL、token、poll interval、开机启动、日志导出 |

### 4.3 视觉方向

参考 `codex-tools`：

- 顶部栏：左侧交通灯形 logo + `CODEXLIGHT`，右侧刷新/最小化/设置按钮。
- 背景：浅色柔和背景，允许轻微 glass/blur，但主信息要高对比。
- 卡片：状态类卡片分层清楚，不做营销式大 hero。
- 操作按钮：手动灯效用颜色明确的 icon+text 按钮。
- dock：底部 3 个主 tab，常用入口稳定。

CodexLight 自己的区别：

- 主视觉应该是实体交通灯状态，而不是账号管理面板。
- 主页面必须一眼看出：server 是否连上、设备是否连上、当前是否有活跃任务。
- 错误态要比装饰更重要，不能只靠颜色，必须有文字状态。

## 5. 技术选型

### 推荐方案：React + Tauri 2 + Rust Shell

原因：

- 用户指定的参考项目就是 Tauri 2 桌面形态，照这个方向实现后 UI 和桌面能力最一致。
- Tauri 原生支持 tray、菜单、窗口管理、单实例、开机启动、更新插件。
- GUI 的 HTTP relay 访问可以用 Rust `reqwest` 或前端经 Tauri command 实现。
- 硬件串口访问由已经完成的独立 driver 负责，和 GUI 进程分离。
- BLE 权限和跨平台差异较大，v1 不进入 GUI，也不作为 driver 的必须项。

建议依赖：

```text
Frontend:
React
Vite
TypeScript
lucide-react

Tauri/Rust:
tauri
tauri-plugin-single-instance
tauri-plugin-autostart
tauri-plugin-updater
tauri-plugin-process
reqwest
tokio
serde
keyring or tauri-plugin-stronghold
```

可选替代：

| 方案 | 优点 | 缺点 |
|---|---|---|
| PySide6 | 复用 Python 最快，硬件代码改动小 | UI 质感和参考项目差异大，托盘/更新/分发需要自己补 |
| Electron | UI 生态成熟，tray 好做 | 包体大，硬件桥接仍要做 |
| .NET MAUI | Windows 体验好 | macOS/Linux 和现有 Python 复用成本不理想 |

结论：v1 采用 Tauri 做 GUI，并对接已经完成的独立 driver。GUI 和 driver 对齐 `RuntimeStatus -> LightEffect` 语义，但互不依赖。

## 6. 模块设计

建议新增目录：

```text
codex-light-desktop/
├─ package.json
├─ index.html
├─ src/
│  ├─ App.tsx
│  ├─ main.tsx
│  ├─ components/
│  │  ├─ AppTopBar.tsx
│  │  ├─ BottomDock.tsx
│  │  ├─ StatusDashboard.tsx
│  │  ├─ DevicePanel.tsx
│  │  ├─ SettingsPanel.tsx
│  │  ├─ ManualControl.tsx
│  │  └─ DiagnosticsPanel.tsx
│  ├─ hooks/
│  │  ├─ useStatusPoller.ts
│  │  └─ useAppSettings.ts
│  ├─ lib/
│  │  ├─ tauriApi.ts
│  │  └─ statusModel.ts
│  └─ styles/
│     └─ app.css
├─ src-tauri/
│  ├─ Cargo.toml
│  ├─ tauri.conf.json
│  ├─ icons/
│  └─ src/
│     ├─ main.rs
│     ├─ tray.rs
│     ├─ models.rs
│     ├─ settings.rs
│     ├─ status_client.rs
│     ├─ poll_controller.rs
│     └─ diagnostics.rs
├─ crates/
│  └─ codex-light-core/
└─ README.md
```

### 6.1 Tauri Commands

前端不直接访问文件系统、串口或 keychain，只通过 Tauri commands：

```text
get_settings() -> Settings
save_settings(settings) -> Settings
get_status() -> RuntimeStatus
refresh_status() -> RuntimeStatus
set_manual_mode(mode) -> RuntimeStatus
get_diagnostics() -> Vec<LogEntry>
set_start_at_login(enabled) -> bool
```

### 6.2 Status Client

Rust 侧实现 HTTP relay API：

```text
GET  /status
POST /mode { mode, source: "gui", event: "manual" }
```

关键规则：

- token 永远不写日志。
- GUI 只把 `RuntimeStatus` 转成 `LightEffect` 后更新窗口和 tray，不下发硬件。
- 手动控制只调用 relay 的 `/mode`，不绕过 relay 写硬件。
- `active_sessions` 只展示，不在 GUI 里重新聚合，避免和 server 逻辑打架。

### 6.3 Poll Controller

Rust 后台 task 负责：

- 每 `poll_interval` 秒请求 `/status`。
- 比较 `seq/mode`。
- 把 `mode` 转换为统一的 `LightEffect`，更新 GUI 和 tray。
- 通过 Tauri event 推送给前端更新界面。
- 更新 tray 图标、title 和菜单状态。

状态机：

```text
idle
connecting_server
server_connected
server_error
paused
```

### 6.4 已有独立 Driver

driver 已经完成，是独立进程，不属于 GUI 进程。v1 不重写 driver，只记录兼容关系：

| 项目 | 约束 |
|---|---|
| 运行方式 | 独立启动，不由 GUI 管理 |
| 状态来源 | 与 GUI 一样读取 HTTP relay |
| 灯效语义 | 与 GUI 对齐 `LightEffect` |
| 硬件访问 | 只在 driver 内部完成 |

GUI 不启动、不停止、不依赖 driver。没有 driver 或没有硬件时，GUI 仍能通过 relay 展示状态。

BLE 或其他硬件能力属于 driver 后续演进，不进入 GUI v1。

### 6.5 Config

配置路径：

| 平台 | 示例 |
|---|---|
| macOS | `~/Library/Application Support/CodexLight/config.json` |
| Windows | `%APPDATA%/CodexLight/config.json` |
| Linux | `~/.config/codexlight/config.json` |

配置内容：

```json
{
  "server_url": "http://10.106.106.80:8765",
  "poll_interval": 1.0,
  "error_interval": 5.0,
  "start_at_login": true,
  "show_notifications": true,
  "launch_minimized": true
}
```

Token 存储：

- 优先用系统 keychain 或 Tauri stronghold。
- 如果安全存储不可用，允许保存到 config，但 UI 必须显示风险提示，并设置文件权限为用户可读写。
- 日志、诊断导出、错误上报永远不输出 token。

### 6.6 Tray Icon

实现方式参考 `codex-tools`：

- macOS 参考它的 menu bar 集成方式，但 CodexLight 为了显示红黄绿，应使用非 template 彩色 icon。
- Windows/Linux 使用彩色 tray icon。
- `thinking/ai/busy` 可以通过定时切换 2-4 张 icon 模拟动画。
- Linux tray 动画支持不稳定时降级为静态图标。

为了让状态栏图标展示红绿灯并和 GUI、硬件保持同样灯效，实际实现要分两层：

```text
RuntimeStatus(mode, seq, active_sessions)
  -> LightEffect(kind, color, animation_frames, frame_interval_ms)
     -> GUI traffic-light component
     -> Tray icon frame

codex-light-driver 也读取同一个 LightEffect：
RuntimeStatus(mode, seq, active_sessions)
  -> LightEffect(kind, color, animation_frames, frame_interval_ms)
     -> ESP32 serial command
```

图标资产建议：

```text
src-tauri/icons/tray/
├─ off.png
├─ disconnected.png
├─ green.png
├─ yellow.png
├─ red.png
├─ thinking-0.png
├─ thinking-1.png
├─ thinking-2.png
├─ busy-0.png
├─ busy-1.png
├─ ai-0.png
└─ ai-1.png
```

平台注意点：

| 平台 | 可实现效果 | 限制 |
|---|---|---|
| macOS | 彩色交通灯图标、菜单栏标题、tooltip、菜单 | 如果用 `icon_as_template(true)` 会变成系统单色图标；要显示红黄绿必须用非 template 彩色 icon |
| Windows | 彩色交通灯图标、tooltip、菜单、点击打开窗口 | Tauri tray title 在 Windows 不支持，状态文字放 tooltip/menu |
| Linux | 彩色图标、tooltip、菜单 | 不同桌面环境差异大，动效可能降级 |

Tray 更新策略：

- `mode/seq` 变化时立即切换到对应 icon。
- 动态 effect 启动一个轻量 frame ticker，只改 tray icon 和 GUI frame，不重新请求 server。
- frame ticker 由当前 `LightEffect` 控制；切到静态状态时停止。
- tray、GUI、driver 的失败要分别记录；GUI 失败不影响 driver，driver 失败也不影响 GUI-only 使用。

### 6.7 Start at Login

优先使用 `tauri-plugin-autostart`：

| 平台 | 实现方向 |
|---|---|
| macOS | LaunchAgent |
| Windows | Startup / registry |
| Linux | XDG autostart `.desktop` |

UI 只切换当前应用自己的开机启动项，不覆盖用户已有脚本。

## 7. 行为细节

### 7.1 首次启动

1. 显示设置窗口。
2. 自动填充默认值：
   - server URL: `http://127.0.0.1:8765`
   - poll interval: `1`
3. 用户点击 `Test Server`。
4. 成功后 GUI 开始展示 relay 状态，可最小化到菜单栏/任务栏。
5. 如果用户另外运行 driver，硬件灯也会按同一套 `LightEffect` 同步。

### 7.2 后台运行

```text
start app
  -> single instance guard
  -> load config
  -> create tray
  -> start GUI poll controller
  -> poll /status
  -> if seq/mode changed: map to LightEffect
  -> update tray + dashboard
```

### 7.3 手动模式

手动按钮默认调用 HTTP relay 的 `/mode`：

```text
GUI -> POST /mode { mode, source: "gui", event: "manual" }
GUI -> 下一次 GET /status -> 更新 GUI/tray
driver -> 下一次 GET /status -> 如独立运行，则更新硬件
```

### 7.4 多任务状态

GUI 不自行计算多任务状态。它只展示 server 返回的：

```json
{
  "mode": "thinking",
  "active_sessions": {},
  "payload": {
    "active_count": 2
  }
}
```

这样不会和 `codex_light_server.py` 的聚合逻辑打架。

## 8. 错误处理

| 场景 | UI 行为 | 后台行为 |
|---|---|---|
| server 连不上 | tray 灰色斜杠，主窗口显示 server error | 按 error interval 重试 |
| token 错误 | 显示 unauthorized，提示检查 token | 保持 GUI 可用但不更新状态 |
| driver 未运行 | Device tab 显示 GUI-only mode | 不影响 GUI/tray |
| 硬件未连接 | Device tab 显示 hardware optional | 不影响 GUI/tray |
| 状态 JSON 异常 | 记录响应摘要 | 保持上一次有效状态 |

## 9. 安全设计

- Token 不显示明文，默认以 password field 展示。
- 日志脱敏：
  - `Authorization`
  - `CODEX_LIGHT_API_TOKEN`
  - token query/header
- 诊断导出不包含 token。
- 配置文件权限尽量限制为当前用户。
- 不在 GUI 里保存 SSH 密码或服务器管理凭据。

## 10. 打包与发布

### macOS

- Tauri 生成 `.app` 和 `.dmg`。
- 默认菜单栏常驻，关闭窗口不退出应用。
- 需要处理：
  - GUI-only 模式不需要串口权限。
  - driver 如单独安装，需要串口权限提示。
  - 开机启动。
  - Apple 签名/公证作为后续发布项。

### Windows

- Tauri 生成 `.msi` 或 `.exe` installer。
- system tray 常驻。
- GUI-only 模式不依赖串口；既有 driver 负责串口访问。
- 开机启动通过 Tauri autostart 插件。

### Linux

- Tauri 生成 AppImage/deb/rpm，优先 AppImage。
- Tray 依赖桌面环境，Wayland/GNOME 下可能需要 AppIndicator 支持。
- GUI-only 模式不依赖串口；driver 使用串口时可能需要用户加入 `dialout` 组。

### 更新

参考 `codex-tools`，后续可接入 `tauri-plugin-updater`：

- GitHub Releases 发布安装包。
- 应用内检查更新。
- v1 可以先不启用自动更新，只保留配置位置。

## 11. 测试计划

### 单元测试

- settings load/save。
- token 脱敏。
- status JSON 解析。
- seq/mode 变化判断。
- `RuntimeStatus -> LightEffect` 映射。

### 集成测试

- 本地启动 `codex_light_server.py`。
- Tauri app dry-run poll。
- POST `/mode` 后 GUI 状态更新。
- GUI-only 模式不启动 driver 也可运行。
- 独立 driver dry-run。

### 前端验收

- Playwright 截图检查主窗口在 1320x860 和窄窗口下无文字重叠。
- Status/Device/Settings tab 切换正常。
- server/error/off/thinking 状态都有明确视觉反馈。

### 手工验收

| 用例 | 预期 |
|---|---|
| 启动 GUI | tray 出现，主窗口可打开 |
| server 正常 | 显示 connected |
| 手动 green | 灯变绿，tray 变绿 |
| 手动 off | 灯灭，tray 灰色 |
| 断开 server | tray disconnected，日志有错误 |
| 不接硬件 | GUI-only 模式仍可显示 relay 状态 |
| 开机启动 | 重启登录后自动出现 tray |

## 12. 实施计划

### Phase 1: Tauri 脚手架

- 新建 `codex-light-desktop/`。
- 配置 React/Vite/TypeScript/Tauri。
- 做出参考 `codex-tools` 的顶部栏、底部 dock、三页布局。
- 加入静态 tray icon 和单实例。

### Phase 2: Rust Relay Client

- 实现 `/status` 和 `/mode` 调用。
- 实现 settings 存储和 token 安全存储。
- 前端展示真实 relay 状态。
- 保持 `codex_light_server.py` 不变。

### Phase 3: 既有 Driver 兼容说明

- 记录已有 driver 的启动方式、配置路径、日志路径。
- 确认 driver 与 GUI 使用同一 relay 状态。
- 确认 driver 与 GUI 的 `LightEffect` 语义一致。
- GUI 不启动、不停止、不依赖 driver。

### Phase 4: Tray 常驻

- tray 菜单和状态图标。
- macOS menu bar title。
- 关闭窗口后后台继续运行。
- paused/reconnect/manual mode 菜单项。

### Phase 5: 开机启动与打包

- `tauri-plugin-autostart`。
- macOS dmg。
- Windows installer。
- Linux AppImage best effort。

### Phase 6: 诊断增强

- 日志窗口。
- 一键复制诊断信息。
- GUI-only 模式诊断。
- 独立 driver 日志路径说明。

## 13. 风险与决策点

| 风险 | 影响 | 处理 |
|---|---|---|
| Tauri 引入前端/Rust 栈 | 初期开发量比 PySide6 大 | 用户已指定 codex-tools 参考，换来更好桌面形态 |
| driver 与 GUI 边界混淆 | GUI 可能被写成硬件控制器 | 强制共享 core，GUI 不写串口 |
| Linux tray 支持不一致 | 图标可能不显示 | Linux v1 标注为 best effort |
| Token 安全存储差异 | keychain/stronghold 可用性不同 | fallback + 明确提示 |
| 现有 CLI 兼容性 | 老用户脚本不能坏 | GUI 新增目录，不破坏 bundle 和 hooks |

## 14. 推荐 v1 范围

v1 只做这些：

- Tauri 主窗口，参考 `codex-tools` 的顶部栏、底部 dock 和控制台卡片。
- Tray 显示当前状态。
- GUI 设置 server URL/token/poll interval。
- GUI 后台轮询 relay，展示 GUI/tray 灯效。
- 独立 driver 使用同一套灯效逻辑驱动实体灯。
- 手动发 mode。
- 查看最近日志。
- macOS/Windows/Linux 同版本打包。

暂缓：

- 多设备同时控制。
- 远程 server 管理。
- 固件烧录入口。
- 自动安装 Codex/cc-connect hooks。
- 自动更新发布链路。

## 15. 最小成功标准

v1 最小成功标准：

```text
打开 CodexLight.app
  -> 菜单栏出现图标
  -> 自动连接 http://10.106.106.80:8765
  -> 不接硬件也能展示 GUI/tray 状态
  -> 如果独立 driver 运行，实体灯使用同一套 LightEffect 变化
  -> Codex 运行时 GUI/tray 显示 thinking
  -> Codex 结束后 GUI/tray 显示 off
```

这个标准需要在 macOS、Windows、Linux 同版本范围内验证。
