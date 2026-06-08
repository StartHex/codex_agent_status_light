# CodexLight 跨平台 GUI 开发计划

本文档基于 [`cross-platform-gui-design.md`](./cross-platform-gui-design.md) 编写，用于约束 v1 开发范围。实现过程中以本文档为准，不在 v1 内继续扩展新功能。

## 1. v1 目标

v1 只解决一个完整闭环：

```text
同一个版本内交付 macOS / Windows / Linux 三端桌面 GUI，
对接已经完成的独立 driver。GUI 和 driver 完全独立运行，只共享同一套灯效逻辑/协议约定。
```

v1 的最小成功标准：

```text
安装 CodexLight 桌面应用
  -> macOS 菜单栏 / Windows tray / Linux tray 出现红绿灯状态图标
  -> 不接 driver、不接硬件时，GUI 也能直接连接 relay 展示 mode / aggregation / active sessions
  -> 已有独立 driver 可继续单独运行，自动连接配置的 HTTP relay
  -> 已有独立 driver 可继续单独写入配置的串口设备
  -> server 能正确聚合多个 Codex session 的状态
  -> Codex 任务运行时 GUI、tray、实体灯按同一套 LightEffect 逻辑展示 thinking
  -> 所有 Codex 任务结束后 GUI、tray、实体灯按同一套 LightEffect 逻辑展示 off
  -> 同一次发布产出 macOS、Windows、Linux 安装包
```

## 2. 架构边界

### 2.1 三层分工

v1 必须拆成三层，不把驱动逻辑塞进 GUI：

| 层 | 职责 | 说明 |
|---|---|---|
| Server / Relay | 接收 hooks，上报/聚合多个 Codex session，提供 `/status` 和 `/mode` | `codex_light_server.py` 是权威状态源 |
| Driver | 后台轮询 relay，执行 `RuntimeStatus -> LightEffect -> serial command`，驱动 ESP32 | 已完成的独立进程/二进制，可无 GUI 运行 |
| GUI App | 直接轮询 relay，执行 `RuntimeStatus -> LightEffect -> GUI/tray`，展示状态、手动控制、日志诊断 | Tauri 桌面应用，可无 driver、无硬件运行 |

### 2.2 Driver 与 GUI 的关系

v1 采用“GUI 和 driver 是两个独立客户端”的模式：

```text
Codex hooks
  -> Server / Relay aggregation

CodexLight GUI
  -> Server / Relay aggregation
  -> shared LightEffect
  -> GUI traffic-light component + tray icon

codex-light-driver
  -> Server / Relay aggregation
  -> shared LightEffect
  -> ESP32 serial
```

约束：

- driver 必须能独立命令行运行，不能依赖 GUI 窗口。
- GUI 必须能在没有 driver、没有硬件的情况下运行。
- GUI 不直接写串口；串口写入只在 driver 层。
- GUI 不启动、不停止、不管理 driver 生命周期。
- GUI 和 driver 分别读取 relay，不能互相作为状态源。
- tray 图标属于 GUI，其状态来自 GUI 自己读取到的 relay `RuntimeStatus`。
- GUI 必须对齐已有 driver 的 `LightEffect` 映射/协议约定，不能另起一套 mode 映射。
- 现有 `codex_light_http_client.py poll` 继续保留，不被破坏。

## 3. 明确边界

### 3.1 v1 必须做

| 模块 | 范围 |
|---|---|
| 桌面框架 | `React + Vite + TypeScript + Tauri 2` |
| 平台 | macOS、Windows、Linux 同版本开发 |
| 主窗口 | `Status / Device / Settings` 三个 tab |
| Server 聚合 | v1 支持并验证多 Codex session 聚合逻辑 |
| 状态来源 | GUI 和 driver 分别读取现有 HTTP relay |
| HTTP API | `GET /status`、`POST /mode`，必要时补充兼容字段 |
| Driver | 复用已经完成的独立 driver，不在 v1 重写 |
| 硬件驱动 | 由已有 driver 负责，GUI 不接入硬件 |
| 状态模型 | `RuntimeStatus -> LightEffect` |
| 同步展示 | GUI 灯效、tray 图标、ESP32 串口命令使用同一套 `LightEffect` 逻辑 |
| Tray | macOS menu bar、Windows system tray、Linux tray/AppIndicator |
| 动效 | `thinking/busy/ai/error` 使用 tray icon 帧动画；Linux 可在不兼容环境降级静态 |
| GUI 设置 | server URL、token、poll interval、launch minimized |
| Driver 设置 | 不在 GUI v1 中管理；只展示配置路径/说明 |
| 安全 | token 不进日志，UI 默认隐藏 token |
| 诊断 | server aggregation、GUI relay、driver、device、tray 最近日志；GUI-only 模式不要求 driver/device 正常 |
| 打包 | 同时产出 macOS、Windows、Linux 包 |

### 3.2 v1 不做

以下内容不进入 v1：

| 不做项 | 原因 |
|---|---|
| BLE 驱动 | 权限和打包复杂，v1 只保证串口 |
| Python sidecar | v1 不引入第二运行时，避免打包路径复杂 |
| 自动更新 | 发布链路后置，v1 只产出安装包 |
| Apple 签名/公证 | v1 可先产出未签名包 |
| Windows 代码签名 | v1 可先产出未签名 installer |
| Linux 仓库分发 | v1 只做 AppImage/deb/rpm 或其中明确组合 |
| 多设备同时控制 | 当前硬件只有一个灯 |
| 远程 server 管理 | GUI 只配置连接，不管理服务器进程 |
| 固件烧录入口 | 与桌面 driver 目标无关 |
| 自动安装 Codex hooks | 现有 hooks 不改 |
| 多语言 | v1 中文或中英固定文案即可 |
| 主题系统 | 固定一套浅色控制台样式 |
| 账号/API 代理功能 | 参考 `codex-tools` 的形态，不复制业务 |

### 3.3 允许修改

为支持 v1，可以修改这些区域：

- `codex_light_server.py`：只允许修改多 session 聚合相关 bug、状态字段兼容、测试性改造。
- `codex_light_http_client.py`：只允许抽取共享协议定义或保持 CLI 兼容的辅助改造。
- 新增 GUI 目录和构建配置。
- 如需共享类型，只新增 GUI 侧协议定义或从已有 driver 文档同步，不重写 driver。
- 新增 server 聚合测试。

### 3.4 不允许修改

- 不改 ESP32 固件协议，除非发现现有串口命令与 driver 无法兼容。
- 不破坏 `cc_connect_light.sh` 的 hook 协议。
- 不破坏 `codex_light_http_client.py poll` 的 CLI 使用方式。
- 不在 GUI 中重新实现一套 session 聚合算法。

## 4. 交付物

v1 结束时应产生：

| 类型 | 路径/内容 |
|---|---|
| 桌面应用源码 | `codex-light-desktop/` |
| GUI 前端源码 | `codex-light-desktop/app/src/` |
| Tauri 源码 | `codex-light-desktop/app/src-tauri/` |
| GUI 协议/灯效源码 | `codex-light-desktop/app/src/lib/` 或 `codex-light-desktop/crates/codex-light-core/` |
| Driver 兼容说明 | 记录已有 driver 的配置路径、运行方式和灯效映射约定 |
| Tray 图标资产 | `codex-light-desktop/app/src-tauri/icons/tray/` |
| Server 聚合测试 | 现有测试目录或新增 `tests/` |
| 开发说明 | `codex-light-desktop/README.md` |
| macOS 包 | `.dmg` 或 `.app` artifact |
| Windows 包 | `.msi` 或 `.exe` installer artifact |
| Linux 包 | AppImage/deb/rpm 中至少一种 artifact |

建议工作区结构：

```text
codex-light-desktop/
├─ package.json
├─ app/
│  ├─ src/
│  └─ src-tauri/
├─ crates/
│  └─ codex-light-core/        # 可选：仅放 GUI 与现有 driver 对齐的协议/灯效定义
├─ packaging/
│  ├─ macos/
│  ├─ windows/
│  └─ linux/
└─ README.md
```

## 5. 阶段计划

### Phase 0: Server 聚合基线

目标：v1 先确认并支持 server 多 session 聚合逻辑。

任务：

- 梳理 `codex_light_server.py` 当前 session 生命周期和聚合规则。
- 明确多个 Codex session 同时运行时 `mode` 的优先级。
- 明确 session 结束、超时、异常退出后的清理规则。
- 为多 session 场景补测试。
- 如现有聚合逻辑有 bug，在 server 中修复。

完成标准：

- 两个 session 同时运行时，任一 session 未结束则聚合状态保持 active。
- 一个 session 结束不会让全部状态提前 off。
- 所有 session 结束后状态进入 off。
- 超时 session 能被清理，且不会长期保持 running。
- `/status` 返回 GUI/driver 所需字段：`mode`、`seq`、`active_sessions`、`payload.active_count`。

不做：

- 不把聚合逻辑搬到 GUI。
- 不新增复杂远程管理 API。

### Phase 1: 协议与灯效对齐

目标：确认 GUI 要使用的状态模型和灯效映射与已经完成的 driver 一致。

任务：

- 整理已有 driver 的 mode 支持范围和串口灯效映射。
- 定义 GUI 侧 `RuntimeStatus`、`LightMode`、`LightEffect`、server response model。
- 建立 `RuntimeStatus -> LightEffect` 映射测试。
- 写明 GUI 与 driver 的关系：只共享协议/灯效约定，不互相调用。

完成标准：

- GUI 侧灯效映射与已有 driver 的灯效语义一致。
- `thinking/off/green/yellow/red/error/busy/ai` 都有明确映射。
- 未知 mode 的 GUI 处理规则明确。

不做：

- 不开发新 driver。
- 不改已有 driver。
- 不写串口。

### Phase 2: GUI 脚手架

目标：建立跨平台 Tauri GUI 空壳。

任务：

- 配置 React、Vite、TypeScript、Tauri 2。
- 配置窗口和单实例。
- 实现 `Status / Device / Settings` 三个 tab。
- 实现跨平台 tray 基础菜单。
- GUI 使用已对齐的 `LightEffect` 映射渲染本地模拟状态。

完成标准：

- macOS、Windows、Linux 都能启动 GUI。
- tray 菜单包含打开窗口、刷新状态、退出。
- 关闭窗口后应用按平台习惯后台驻留。
- 不配置 driver、不连接硬件时 GUI 仍可正常运行。

不做：

- 不做第四个 tab。
- 不做主题系统。
- 不接硬件。

### Phase 3: GUI Relay Client

目标：GUI 不依赖 driver，直接读取 relay 并展示同一套灯效。

任务：

- GUI 实现 `GET /status`。
- GUI 实现 `POST /mode`。
- GUI 展示 server、aggregation、mode、active sessions。
- GUI 通过 `LightEffect` 渲染窗口灯效和 tray 状态。
- Settings 只保存 GUI 自己的 relay/display 配置。
- Device tab 展示“硬件由独立 driver 负责”的只读说明和 driver 配置文件路径，不扫描、不写串口。

完成标准：

- GUI 不直接写串口。
- GUI 能显示 `active_count` 和 active session 摘要。
- GUI 在没有 driver、没有硬件时仍可作为状态看板使用。
- GUI 手动 `off/green/yellow/red/thinking` 能通过 relay 更新状态。

不做：

- 不在 GUI 中管理 driver 生命周期。
- 不在 GUI 中扫描串口或测试硬件。
- 不在 GUI 中实现 session 聚合。

### Phase 4: Tray 动效同步

目标：三平台 tray 图标与 GUI、硬件灯效语义一致。

任务：

- 创建 tray icon 帧资产。
- 实现 `LightEffect -> tray frame`。
- 动态状态启动 frame ticker。
- 静态状态停止 frame ticker。
- tray tooltip/menu 显示 mode、server、active sessions；driver/device 状态不作为 GUI 必需依赖。

完成标准：

- macOS 显示彩色红绿灯菜单栏图标。
- Windows 显示彩色红绿灯 system tray 图标。
- Linux 支持 tray/AppIndicator；不支持动画的环境降级静态但状态正确。
- tray 动效失败不影响 GUI 状态展示，也不影响已有 driver 串口下发。

不做：

- 不追求硬件 PWM 与 tray 毫秒级同步。

### Phase 5: 既有 Driver 兼容验收

目标：确认 GUI 与已完成 driver 在同一个 relay 上各自独立运行，灯效语义一致。

任务：

- 记录已有 driver 的启动命令、配置路径、日志路径。
- 用同一个 relay 同时运行 GUI 和已有 driver。
- 验证 `thinking/off/green/yellow/red` 的 GUI/tray 表现与硬件表现语义一致。
- 验证 GUI-only 模式不依赖 driver。

完成标准：

- GUI 不启动、不停止、不管理 driver。
- driver 关闭时，GUI 仍正常展示 relay 状态。
- driver 运行时，实体灯和 GUI/tray 使用相同 `LightEffect` 语义。

不做：

- 不改 driver 架构。
- 不把 driver 源码迁入 GUI 工程。

### Phase 6: 三平台打包

目标：同一版本同时产出 macOS、Windows、Linux GUI 包。

任务：

- 配置 GitHub Actions 或等价 CI matrix：
  - macOS runner 构建 `.dmg` 或 `.app`
  - Windows runner 构建 `.msi` 或 `.exe`
  - Linux runner 构建 AppImage/deb/rpm 中至少一种
- 确保 GUI 包不依赖 driver binary。
- 确保配置目录和日志目录按平台规范落盘。
- 编写三平台安装/运行说明。

完成标准：

- 同一次 release workflow 产生三平台 artifact。
- 每个平台安装后 GUI 不依赖 driver 即可进入 GUI-only 模式。
- 每个平台都能读取 relay 或进入 dry-run 展示状态。

不做：

- 不做自动更新。
- 不做签名/公证。
- 不做 Linux 软件源发布。

### Phase 7: 验收与冻结

目标：只修 v1 验收问题，不增加功能。

任务：

- 跑 server 聚合测试。
- 跑 GUI 基础截图/交互测试。
- 跑 GUI-only 冒烟测试。
- 跑与已有 driver 的兼容验收。
- 三平台打包产物冒烟测试。
- 更新 README。

完成标准：

- v1 验收清单全部通过。
- 未通过项只允许修复，不允许扩展新功能。

不做：

- 不改既有 driver 功能。

## 6. 数据模型边界

### 6.1 LightMode

v1 只支持这些 mode：

```text
off
thinking
busy
ai
yellow
green
red
success
error
```

未知 mode 处理为：

```text
GUI: unknown
tray: disconnected 或灰色问号图标
driver: 不下发 serial command
log: warn unknown mode
```

### 6.2 RuntimeStatus

v1 依赖这些字段：

```text
mode
seq
updated_at
active_sessions
payload.active_count
source
event
```

其他字段只作为日志原文，不进入 UI 或 driver 业务逻辑。

### 6.3 LightEffect

统一灯效模型：

```text
kind: static | animated | disconnected | unknown
mode: LightMode
serial_command: string | null
tray_frames: string[]
gui_frames: string[]
frame_interval_ms: number
```

硬件、GUI、tray 必须从这个模型派生，不允许各自写一套 mode 映射。

### 6.4 AggregationState

server 聚合状态至少需要表达：

```text
active_count: number
active_sessions: map
last_event: string | null
last_source: string | null
mode: LightMode
seq: number
updated_at: string
```

权威聚合只在 server 层。driver 和 GUI 只消费结果。

## 7. 验收清单

v1 验收时只看以下清单：

| 编号 | 项目 | 必须通过 |
|---|---|---|
| A1 | server 多 session 聚合测试通过 | 是 |
| A2 | GUI 无 driver/无硬件也可启动并展示 relay 状态 | 是 |
| A3 | GUI 有 `Status / Device / Settings` | 是 |
| A4 | GUI 显示 active_count 和 session 摘要 | 是 |
| A5 | tray 图标与 GUI 状态一致 | 是 |
| A6 | 既有 driver 与 GUI 使用同一 relay 时语义一致 | 是 |
| A7 | Codex 任务开始时 GUI、tray、实体灯按同一 `LightEffect` 语义展示 thinking | 是 |
| A8 | 所有 Codex 任务结束后 GUI、tray、实体灯按同一 `LightEffect` 语义展示 off | 是 |
| A9 | token 不出现在日志 | 是 |
| A10 | GUI 配置重启后保留 | 是 |
| A11 | macOS 包产出 | 是 |
| A12 | Windows 包产出 | 是 |
| A13 | Linux 包产出 | 是 |

未列入清单的功能，不作为 v1 验收要求。

## 8. 开发规则

- driver 是 driver，GUI 是 GUI；GUI 不直接写串口，不管理 driver 生命周期。
- driver 已经完成，v1 不重写、不迁移、不重构 driver。
- GUI 必须支持 GUI-only 模式：不接 driver、不接硬件也能作为 relay 状态看板使用。
- GUI 和 driver 只共享协议模型和灯效语义；如创建 `codex-light-core`，它只服务 GUI 侧对齐，不作为重写 driver 的前置条件。
- server 聚合逻辑是 v1 范围，必须有测试和验收。
- macOS、Windows、Linux 是同一个 v1 版本范围，不再后置。
- 三平台打包是 v1 范围，不再后置。
- 每个 Phase 完成后才能进入下一 Phase。
- 每个 Phase 只做本阶段列出的任务。
- 如发现必须扩展范围，先更新本文档的边界说明，再开始编码。
- 不因为 UI 参考 `codex-tools` 而复制它的账号、API 代理、用量监控功能。
- 不把 BLE、自动更新、签名、公证混入 v1。

## 9. 推荐执行顺序

```text
Phase 0  Server 聚合基线
Phase 1  协议与灯效对齐
Phase 2  GUI 脚手架
Phase 3  GUI Relay Client
Phase 4  Tray 动效同步
Phase 5  既有 Driver 兼容验收
Phase 6  三平台打包
Phase 7  验收与冻结
```

任何阶段出现分歧时，优先保证：

```text
Server 聚合正确
既有 Driver 不被改坏
GUI 独立可用
GUI / driver 灯效语义一致
macOS / Windows / Linux 同版本产出
```

其余功能全部后置。
