"""印表機支援：列出系統印表機、傳送 TSPL/ESC 原始指令到熱感貼紙機。

跨平台策略：
- Windows：優先使用 pywin32（win32print）；未安裝時退回 PowerShell 查詢。
- macOS / Linux：使用 CUPS 的 lpstat 列印機清單、lp -o raw 傳送原始指令。
"""
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # Windows 專用，其他平台沒有此套件屬正常情況。
    import win32print  # type: ignore
except ImportError:
    win32print = None


def list_printers():
    """回傳系統目前可用的印表機名稱清單；查不到時回傳空清單（UI 允許手動輸入）。"""
    if win32print is not None:
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            return [printer[2] for printer in win32print.EnumPrinters(flags)]
        except Exception:
            return []
    if sys.platform == "win32":
        try:
            output = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Printer | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout
            return [line.strip() for line in output.splitlines() if line.strip()]
        except (OSError, subprocess.SubprocessError):
            return []
    try:
        output = subprocess.run(
            ["lpstat", "-p"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
        printers = []
        for line in output.splitlines():
            if line.startswith("printer "):
                printers.append(line.split()[1])
        return printers
    except (OSError, subprocess.SubprocessError):
        return []


def send_raw(printer_name, payload):
    """將原始位元組（TSPL/ESC 指令）直接送給指定印表機，跳過驅動排版以確保吐紙不偏移。"""
    if not printer_name:
        raise ValueError("尚未在系統設定中指定熱感貼紙印表機")
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if win32print is not None:
        handle = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(handle, 1, ("WMS Label", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
        finally:
            win32print.ClosePrinter(handle)
        return
    with tempfile.NamedTemporaryFile(delete=False, suffix=".prn") as tmp:
        tmp.write(payload)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["lp", "-d", printer_name, "-o", "raw", tmp_path],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "lp 指令執行失敗")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def parse_label_size(label_paper):
    """'100x150' → (100, 150)；格式錯誤時回退 100x100。"""
    try:
        width_text, height_text = label_paper.lower().split("x", 1)
        return int(width_text), int(height_text)
    except (AttributeError, ValueError):
        return 100, 100


def tspl_product_label(label_paper, barcode, name, sku, copies=1):
    """商品內部條碼貼紙的 TSPL 指令（含品名、SKU 與 Code 39 條碼）。"""
    width_mm, height_mm = parse_label_size(label_paper)
    dots = 8
    margin = 3 * dots
    line_height = int(3.4 * dots)
    y = margin

    def esc(text):
        return (text or "").replace('"', "'")

    lines = [
        f"SIZE {width_mm} mm,{height_mm} mm",
        "GAP 2 mm,0 mm",
        "DIRECTION 1",
        "CLS",
        f'TEXT {margin},{y},"TSS24.BF2",0,2,2,"{esc(name)[:20]}"',
    ]
    y += line_height * 2
    if sku:
        lines.append(f'TEXT {margin},{y},"TSS24.BF2",0,1,1,"SKU: {esc(sku)}"')
        y += line_height
    y += dots
    barcode_height = max(8 * dots, (height_mm * dots) - y - 6 * dots)
    lines.append(f'BARCODE {margin},{y},"39",{barcode_height},1,0,2,4,"{esc(barcode)}"')
    lines.append(f"PRINT {max(1, int(copies))},1")
    return "\r\n".join(lines) + "\r\n"


def tspl_box_label(label_paper, order_no, box_number, box_count,
                   branch_text, address_text, carrier, tracking_no, order_date):
    """產生一張物流箱標的 TSPL 指令（TSC 系列熱感機通用），精準定位避免吐紙偏移。"""
    width_mm, height_mm = parse_label_size(label_paper)
    label_code = f"{order_no}-B{box_number}"
    dots = 8  # 203dpi ≒ 8 dots/mm
    margin = 3 * dots
    line_height = int(3.4 * dots)
    y = margin

    def esc(text):
        return (text or "").replace('"', "'")

    lines = [
        f"SIZE {width_mm} mm,{height_mm} mm",
        "GAP 2 mm,0 mm",
        "DIRECTION 1",
        "CLS",
    ]
    lines.append(f'TEXT {margin},{y},"TSS24.BF2",0,2,2,"物流箱標 {box_number}/{box_count}"')
    y += line_height * 2
    lines.append(f'TEXT {margin},{y},"TSS24.BF2",0,2,2,"{esc(branch_text)}"')
    y += line_height * 2
    lines.append(f'TEXT {margin},{y},"TSS24.BF2",0,1,1,"{esc(address_text)}"')
    y += line_height
    lines.append(f'TEXT {margin},{y},"TSS24.BF2",0,1,1,"物流：{esc(carrier)}  日期：{esc(order_date)}"')
    y += line_height
    lines.append(f'TEXT {margin},{y},"TSS24.BF2",0,1,1,"託運單號：{esc(tracking_no) or "待補"}"')
    y += line_height + dots
    barcode_height = 10 * dots
    lines.append(f'BARCODE {margin},{y},"39",{barcode_height},1,0,2,4,"{esc(label_code)}"')
    lines.append("PRINT 1,1")
    return "\r\n".join(lines) + "\r\n"
