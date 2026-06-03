#!/usr/bin/env python3
# 控制 ESP32-C3 CodexLight BLE 状态灯
#
# 首次安装：
#   python3 -m pip install bleak
#
# 用法：
#   python3 codex_light_ble.py demo
#   python3 codex_light_ble.py thinking
#   python3 codex_light_ble.py ai
#   python3 codex_light_ble.py busy
#   python3 codex_light_ble.py success
#   python3 codex_light_ble.py error
#   python3 codex_light_ble.py alarm
#   python3 codex_light_ble.py traffic
#   python3 codex_light_ble.py off

import argparse
import asyncio
import os
import sys

try:
    from bleak import BleakScanner, BleakClient
except ImportError:
    BleakScanner = None
    BleakClient = None

DEVICE_NAME = os.environ.get("CODEX_LIGHT_DEVICE_NAME", "CodexLight")
MODE_CHAR_UUID = "b8b7e002-7a6b-4f4f-9a8b-11c0ffee0001"

VALID_MODES = {
    "red",
    "yellow",
    "green",
    "busy",
    "error",
    "thinking",
    "ai",
    "success",
    "traffic",
    "alarm",
    "demo",
    "off",
}

def parse_args():
    parser = argparse.ArgumentParser(description="控制 ESP32-C3 CodexLight BLE 状态灯")
    parser.add_argument("mode", help="灯效 mode")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要发送的 mode，不扫描蓝牙设备，适合无硬件测试",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    mode = args.mode.strip().lower()
    if mode not in VALID_MODES:
        print(f"未知 mode: {mode}")
        print("可用 mode:", ", ".join(sorted(VALID_MODES)))
        sys.exit(1)

    dry_run = args.dry_run or os.environ.get("CODEX_LIGHT_DRY_RUN") == "1"
    if dry_run:
        print(f"[dry-run] CodexLight mode={mode}")
        return

    if BleakScanner is None or BleakClient is None:
        print("缺少依赖 bleak。安装：python3 -m pip install bleak")
        sys.exit(4)

    print(f"正在扫描 BLE 设备：{DEVICE_NAME} ...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)

    if device is None:
        print("没有找到 CodexLight。请确认：")
        print("1. ESP32 已通电")
        print("2. 代码已刷入 BLE 增强版")
        print("3. 距离足够近")
        print("4. macOS 蓝牙已打开，并给 Terminal 蓝牙权限")
        sys.exit(2)

    print(f"找到设备: {device.address}")

    async with BleakClient(device) as client:
        if not client.is_connected:
            print("连接失败")
            sys.exit(3)

        print(f"已连接，发送 mode={mode}")
        await client.write_gatt_char(MODE_CHAR_UUID, mode.encode("utf-8"), response=True)
        print("发送完成")

if __name__ == "__main__":
    asyncio.run(main())
