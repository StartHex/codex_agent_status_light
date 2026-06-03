#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap(text: str, width: int = 88) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def make_pdf(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    pages: list[list[tuple[int, str, str]]] = []
    page: list[tuple[int, str, str]] = []
    y = 800

    def add_line(size: int, font: str, text: str, gap: int | None = None) -> None:
        nonlocal page, y
        if y < 60:
            pages.append(page)
            page = []
            y = 800
        page.append((y, font, f"/{font} {size} Tf 50 {y} Td ({esc(text)}) Tj"))
        y -= gap or int(size * 1.65)

    add_line(22, "F2", title, 34)
    for heading, lines in sections:
        add_line(15, "F2", heading, 24)
        for line in lines:
            for wrapped in wrap(line):
                add_line(10, "F1", wrapped, 16)
        y -= 8
    if page:
        pages.append(page)

    objects: list[bytes] = []
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_object_ids: list[int] = []
    for page_lines in pages:
        content = "BT\n"
        for _, _, op in page_lines:
            content += op + "\n"
        content += "ET\n"
        stream = content.encode("latin-1")
        content_obj_id = len(objects) + 1
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")
        page_obj_id = len(objects) + 1
        page_object_ids.append(page_obj_id)
        page_dict = (
            f"<< /Type /Page /Parent {{PAGES}} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 1 0 R /F2 2 0 R >> >> "
            f"/Contents {content_obj_id} 0 R >>"
        ).encode("latin-1")
        objects.append(page_dict)

    pages_obj_id = len(objects) + 1
    kids = " ".join(f"{obj_id} 0 R" for obj_id in page_object_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("latin-1"))

    catalog_obj_id = len(objects) + 1
    objects.append(f"<< /Type /Catalog /Pages {pages_obj_id} 0 R >>".encode("latin-1"))

    objects = [obj.replace(b"{PAGES}", str(pages_obj_id).encode()) for obj in objects]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("latin-1"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f\n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n\n".encode("latin-1"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_obj_id} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(out)


def main() -> None:
    docs = [
        (
            "步骤一--CodexLight_购买清单.pdf",
            "CodexLight Step 1 - Bill of Materials",
            [
                ("Core Parts", [
                    "ESP32-C3 SuperMini development board with USB-C.",
                    "Toy traffic-light ornament or any three-light red/yellow/green enclosure.",
                    "Three 220 ohm resistors, one per LED channel.",
                    "Thin hookup wire, heat-shrink tube, USB data cable, soldering tools.",
                ]),
                ("Electrical Notes", [
                    "The firmware assumes a common-anode light board.",
                    "GPIO LOW means LED on; GPIO HIGH means LED off.",
                    "Default pins: IO2 green, IO3 yellow, IO4 red.",
                ]),
            ],
        ),
        (
            "步骤二--CodexLight_ESP32蓝牙固件烧录.pdf",
            "CodexLight Step 2 - ESP32 BLE Firmware Flashing",
            [
                ("Firmware File", [
                    "Open ESP32_C3_ToyBoard_CommonAnode_BLE_Enhanced_CodexLight.ino in Arduino IDE.",
                    "Board: ESP32C3 Dev Module. Enable USB CDC On Boot when available.",
                    "BLE advertised name: CodexLight.",
                    "Mode characteristic UUID: b8b7e002-7a6b-4f4f-9a8b-11c0ffee0001.",
                ]),
                ("Upload Check", [
                    "After upload, open Serial Monitor at 115200 baud.",
                    "Expected boot log includes: BLE device name: CodexLight.",
                    "Supported modes: demo, thinking, ai, busy, success, error, alarm, traffic, off, red, yellow, green.",
                ]),
            ],
        ),
        (
            "步骤三--CodexLight_安装与使用指南.pdf",
            "CodexLight Step 3 - Codex CLI Installation",
            [
                ("Install Hooks", [
                    "cd codex-light-bundle",
                    "./install-codex-light.sh",
                    "Start Codex CLI and run /hooks. Review and trust the CodexLight hook definitions.",
                ]),
                ("No-Hardware Test", [
                    "CODEX_LIGHT_DRY_RUN=1 python3 codex-light-bundle/codex_light.py --mode thinking",
                    "CODEX_LIGHT_DRY_RUN=1 python3 codex-light-bundle/codex_light_ble.py success",
                ]),
                ("Real Hardware Test", [
                    "python3 -m pip install bleak",
                    "python3 codex-light-bundle/codex_light_ble.py green",
                    "If the device name differs, set CODEX_LIGHT_DEVICE_NAME before running the BLE script.",
                ]),
            ],
        ),
    ]

    for filename, title, sections in docs:
        make_pdf(ROOT / filename, title, sections)


if __name__ == "__main__":
    main()
