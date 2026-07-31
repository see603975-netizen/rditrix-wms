"""
泡泡貓 WMS Lite V6.8 - 保養品物流管理系統

安裝需求：pip install ttkbootstrap
執行方式：python 泡泡貓wmsV6.py

"""

import html
import re
import shutil
import sqlite3
import tkinter as tk
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, CENTER, END, EW, LEFT, RIGHT, W, X, Y


APP_VERSION = "泡泡貓 WMS Lite V6.8"
LOGIN_ACCOUNT = "PO001"
LOGIN_PASSWORD = "123123"

NO_EXPIRY_DATE = "9999-12-31"
SPECIAL_ZONES = ("Staging", "QC", "Scrap", "Outbound")
ACTIVE_ORDER_STATUSES = ("待撿貨", "包裝中")
CARRIERS = ("未指定", "蝦皮店到店", "嘉里大榮", "黑貓宅急便", "新竹物流", "自取")
RECEIVING_ORDER_STATUSES = ("已建立", "已送出訂單", "待驗收", "驗收中", "已完成")
RETURN_REASONS = ("凹損", "破損", "漏液", "中文標", "效期", "規格", "出產地", "其他")
PRODUCT_CATEGORIES = ("乳液", "乳霜", "化妝水", "精華液", "其他類別")

# V6.8：字體整體放大約 30%（原字級 x1.3），介面元件與 Treeview 皆套用同一基準字級。
FONT_FAMILY = "Microsoft JhengHei"
FONT_SCALE = 1.3


def scaled_font(size):
    """依 FONT_SCALE 放大字級，四捨五入為整數。"""
    return max(1, round(size * FONT_SCALE))


# V6.8：報廢區防呆天數。商品移入報廢區後，需經過此天數才會被系統自動刪除庫存並扣帳，
# 讓使用者有充足時間發現誤操作並「取消報廢」移回原儲位。
SCRAP_HOLD_DAYS = 3
SCRAP_ZONE_SHELF = "報廢區"
QC_ZONE_SHELF = "品檢區"
# V6.8：Treeview／Labelframe 依 bootstyle 主題色統一配色，讓表格分隔線與所在頁面框線同色。
TABLE_BOOTSTYLES = ("primary", "secondary", "success", "info", "warning", "danger")


class Utils:
    """輸入與日期相關的小工具。"""

    @staticmethod
    def now_text():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def today_text():
        return date.today().isoformat()

    @staticmethod
    def normalize_barcode(value):
        return value.strip().upper()

    @staticmethod
    def valid_barcode(value):
        # 可支援一般 EAN 數字條碼，也保留英數混合的 Code 128 商品碼。
        return bool(re.fullmatch(r"[A-Z0-9-]{3,64}", value))

    @staticmethod
    def valid_shelf_code(value):
        """V6.4：階層式儲位格式，例如 A01-03（區域-貨架-層位）。"""
        return bool(re.fullmatch(r"[A-Z]\d{2}-\d{2}", value))

    @staticmethod
    def validate_date(date_text):
        """回傳 (格式有效, 已過期, 剩餘天數)。效期當天仍可使用。"""
        try:
            expiry = datetime.strptime(date_text, "%Y-%m-%d").date()
            days = (expiry - date.today()).days
            return True, days < 0, days
        except ValueError:
            return False, False, 0

    @staticmethod
    def is_no_expiry(expiry_date):
        return expiry_date in ("", None, NO_EXPIRY_DATE)

    @staticmethod
    def display_expiry(expiry_date, expiry_required=True):
        if not expiry_required or Utils.is_no_expiry(expiry_date):
            return "無效期"
        return expiry_date


class DBManager:
    """SQLite 資料存取與出貨配貨邏輯。"""

    def __init__(self, db_name="wms_system_v3.db"):
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self.init_db()
        self.seed_data()

    def init_db(self):
        # 既有 v3 資料庫可直接升級；CREATE IF NOT EXISTS 不會覆蓋舊資料。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                barcode TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                safety_stock INTEGER NOT NULL DEFAULT 0,
                expiry_required BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shelves (
                shelf_code TEXT PRIMARY KEY,
                zone TEXT NOT NULL
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelf_code TEXT NOT NULL,
                barcode TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                FOREIGN KEY(barcode) REFERENCES products(barcode),
                FOREIGN KEY(shelf_code) REFERENCES shelves(shelf_code),
                UNIQUE(shelf_code, barcode, expiry_date)
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_type TEXT NOT NULL,
                barcode TEXT NOT NULL,
                from_shelf TEXT,
                to_shelf TEXT,
                before_qty INTEGER,
                after_qty INTEGER,
                change_qty INTEGER NOT NULL,
                expiry_date TEXT,
                timestamp TEXT NOT NULL,
                operator TEXT NOT NULL,
                reason TEXT
            )
            """
        )

        # 新增的主檔與出貨單資料。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                address TEXT,
                contact_name TEXT,
                contact_phone TEXT,
                default_carrier TEXT NOT NULL DEFAULT '未指定',
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shipping_orders (
                order_no TEXT PRIMARY KEY,
                branch_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '待撿貨',
                carrier TEXT NOT NULL DEFAULT '未指定',
                tracking_no TEXT,
                box_count INTEGER NOT NULL DEFAULT 1 CHECK(box_count > 0),
                print_count INTEGER NOT NULL DEFAULT 0,
                label_printed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                packed_at TEXT,
                packed_by TEXT,
                cancelled_at TEXT,
                cancel_reason TEXT,
                FOREIGN KEY(branch_id) REFERENCES branches(id)
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shipping_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                line_no INTEGER NOT NULL,
                barcode TEXT NOT NULL,
                product_name TEXT NOT NULL,
                required_qty INTEGER NOT NULL CHECK(required_qty > 0),
                scanned_qty INTEGER NOT NULL DEFAULT 0 CHECK(scanned_qty >= 0),
                FOREIGN KEY(order_no) REFERENCES shipping_orders(order_no) ON DELETE CASCADE,
                FOREIGN KEY(barcode) REFERENCES products(barcode),
                UNIQUE(order_no, barcode)
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shipping_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                barcode TEXT NOT NULL,
                shelf_code TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                allocated_qty INTEGER NOT NULL CHECK(allocated_qty > 0),
                shipped_qty INTEGER NOT NULL DEFAULT 0 CHECK(shipped_qty >= 0),
                FOREIGN KEY(order_no) REFERENCES shipping_orders(order_no) ON DELETE CASCADE,
                FOREIGN KEY(barcode) REFERENCES products(barcode),
                FOREIGN KEY(shelf_code) REFERENCES shelves(shelf_code),
                UNIQUE(order_no, barcode, shelf_code, expiry_date)
            )
            """
        )

        # 進貨單與驗收明細。條碼不設 products 外鍵，才能先匯入供應商單據，
        # 並在驗收時明確攔截尚未建立商品主檔的新品。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS receiving_orders (
                order_no TEXT PRIMARY KEY,
                supplier_name TEXT NOT NULL DEFAULT '未指定',
                order_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '已建立',
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                sent_at TEXT,
                sent_by TEXT,
                ready_for_receipt_at TEXT,
                ready_for_receipt_by TEXT,
                received_at TEXT,
                received_by TEXT,
                note TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS receiving_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                line_no INTEGER NOT NULL,
                barcode TEXT NOT NULL,
                product_name TEXT NOT NULL,
                required_qty INTEGER NOT NULL CHECK(required_qty > 0),
                received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty >= 0),
                FOREIGN KEY(order_no) REFERENCES receiving_orders(order_no) ON DELETE CASCADE,
                UNIQUE(order_no, barcode)
            )
            """
        )

        self.ensure_column("transactions", "order_no", "TEXT")
        self.ensure_column("receiving_orders", "sent_at", "TEXT")
        self.ensure_column("receiving_orders", "sent_by", "TEXT")
        self.ensure_column("receiving_orders", "ready_for_receipt_at", "TEXT")
        self.ensure_column("receiving_orders", "ready_for_receipt_by", "TEXT")
        # V6.1：進貨單取消追蹤欄位（保留歷史紀錄，禁止直接刪除單據）。
        self.ensure_column("receiving_orders", "cancelled_at", "TEXT")
        self.ensure_column("receiving_orders", "cancelled_by", "TEXT")
        self.ensure_column("receiving_orders", "cancel_reason", "TEXT")
        # V6.2：進貨單列印次數追蹤，格式與出貨單一致（正本／補印）。
        self.ensure_column("receiving_orders", "print_count", "INTEGER NOT NULL DEFAULT 0")
        # V6.3：記錄最後列印時間，讓建立單據後列印清單能立即反映列印狀態。
        self.ensure_column("receiving_orders", "last_printed_at", "TEXT")
        self.ensure_column("shipping_orders", "last_printed_at", "TEXT")
        # V6.1：出貨單取消操作人補齊（原本只有取消時間與原因）。
        self.ensure_column("shipping_orders", "cancelled_by", "TEXT")
        # V6.5：內部物流箱標補印次數／時間追蹤，格式與出貨單／進貨單一致。
        self.ensure_column("shipping_orders", "label_print_count", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("shipping_orders", "label_last_printed_at", "TEXT")
        self.cursor.execute(
            "UPDATE shipping_orders SET label_print_count=1 WHERE label_printed=1 AND label_print_count=0"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS return_orders (
                return_no TEXT PRIMARY KEY,
                receiving_order_no TEXT NOT NULL,
                barcode TEXT NOT NULL,
                product_name TEXT NOT NULL,
                return_qty INTEGER NOT NULL CHECK(return_qty > 0),
                return_reason TEXT NOT NULL,
                evidence_path TEXT,
                note TEXT,
                status TEXT NOT NULL DEFAULT '待供應商確認',
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                shipped_at TEXT,
                shipped_by TEXT,
                FOREIGN KEY(receiving_order_no) REFERENCES receiving_orders(order_no)
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_inv_barcode_expiry ON inventory(barcode, expiry_date)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_order_status ON shipping_orders(status, order_date)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_alloc_stock ON shipping_allocations(barcode, shelf_code, expiry_date)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_receiving_order_status ON receiving_orders(status, order_date)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_receiving_order_item ON receiving_order_items(order_no, barcode)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_return_receiving_order ON return_orders(receiving_order_no, barcode)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_return_status ON return_orders(status, created_at)"
        )

        # V6.1：操作紀錄資料表，記錄登入、單據建立／完成／取消等關鍵操作，供全程追蹤。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                operator TEXT NOT NULL,
                action TEXT NOT NULL,
                order_no TEXT,
                note TEXT
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_oplog_time ON operation_logs(id DESC)"
        )
        # V6.4：儲位階層化（區域-貨架-層位，如 A01-03）。既有欄位保留，新增結構化欄位與管理狀態。
        self.ensure_column("shelves", "area", "TEXT")
        self.ensure_column("shelves", "rack", "TEXT")
        self.ensure_column("shelves", "level", "TEXT")
        self.ensure_column("shelves", "status", "TEXT NOT NULL DEFAULT '啟用'")
        self.ensure_column("shelves", "is_special", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("shelves", "note", "TEXT")
        self.ensure_column("shelves", "created_at", "TEXT")
        self.ensure_column("shelves", "updated_at", "TEXT")
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_shelves_status ON shelves(status, area, rack, level)"
        )
        # 標記既有四個特殊區（未上架／品檢區／報廢區／出貨暫存），避免被誤判為可編輯的物理儲位。
        self.cursor.execute(
            f"UPDATE shelves SET is_special=1 WHERE zone IN ({','.join('?' * len(SPECIAL_ZONES))})",
            SPECIAL_ZONES,
        )
        # 清理沒有任何庫存與保留紀錄的舊格式儲位（如 A01），改用新的階層式格式（如 A01-01）；
        # 僅在無資料時清除，不會動到任何已有庫存或保留中的儲位。
        legacy_codes = [
            row["shelf_code"]
            for row in self.cursor.execute(
                "SELECT shelf_code FROM shelves WHERE is_special=0 AND shelf_code GLOB '[A-Z][0-9][0-9]'"
            ).fetchall()
        ]
        for code in legacy_codes:
            has_inventory = self.cursor.execute(
                "SELECT 1 FROM inventory WHERE shelf_code=? LIMIT 1", (code,)
            ).fetchone()
            has_allocation = self.cursor.execute(
                "SELECT 1 FROM shipping_allocations WHERE shelf_code=? LIMIT 1", (code,)
            ).fetchone()
            if not has_inventory and not has_allocation:
                self.cursor.execute("DELETE FROM shelves WHERE shelf_code=?", (code,))
        self.conn.commit()

    def ensure_column(self, table_name, column_name, definition):
        columns = {
            row["name"]
            for row in self.cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            self.cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )

    def seed_data(self):
        products = [
            ("4711234567890", "ES0001", "玻尿酸保濕精華", "精華液", 50, 1),
            ("4711234567891", "LO0001", "全效修護乳液", "乳液", 30, 1),
            ("4711234567892", "MK0001", "面膜", "面膜", 100, 1),
            ("4711234567893", "TN0001", "保養水", "化妝水", 50, 1),
            ("4711234567894", "CR0001", "保濕霜", "乳霜", 30, 1),
            ("4711234567895", "CP0001", "紙杯", "耗材", 100, 0),
        ]
        self.cursor.executemany(
            "INSERT OR IGNORE INTO products VALUES (?,?,?,?,?,?)", products
        )

        now = Utils.now_text()
        shelves = [
            ("未上架", "Staging", None, None, None, 1),
            ("品檢區", "QC", None, None, None, 1),
            ("報廢區", "Scrap", None, None, None, 1),
            ("出貨暫存", "Outbound", None, None, None, 1),
        ]
        # V6.4：物理儲位改採「區域-貨架-層位」階層式格式，例如 A01-03 = A區 01號貨架 第3層。
        for area in ("A", "B", "C"):
            for rack in range(1, 3):
                for level in range(1, 4):
                    rack_text, level_text = f"{rack:02d}", f"{level:02d}"
                    shelves.append((f"{area}{rack_text}-{level_text}", area, area, rack_text, level_text, 0))
        self.cursor.executemany(
            """
            INSERT OR IGNORE INTO shelves (shelf_code, zone, area, rack, level, is_special, status, created_at)
            VALUES (?,?,?,?,?,?, '啟用', ?)
            """,
            [(code, zone, area, rack, level, is_special, now) for code, zone, area, rack, level, is_special in shelves],
        )

        branches = [
            ("BR001", "台北示範分店", "台北市信義區示範路 1 號", "陳店長", "0912-345-678", "黑貓宅急便"),
            ("BR002", "台中示範分店", "台中市西屯區示範路 88 號", "林店長", "0922-345-678", "嘉里大榮"),
        ]
        self.cursor.executemany(
            """
            INSERT OR IGNORE INTO branches
            (code, name, address, contact_name, contact_phone, default_carrier)
            VALUES (?,?,?,?,?,?)
            """,
            branches,
        )
        self.conn.commit()

    # ---------- 共用資料庫操作 ----------

    def log_transaction(
        self,
        tx_type,
        barcode,
        from_shelf,
        to_shelf,
        before_qty,
        after_qty,
        change_qty,
        expiry_date,
        operator,
        reason="",
        order_no=None,
    ):
        self.cursor.execute(
            """
            INSERT INTO transactions
            (tx_type, barcode, from_shelf, to_shelf, before_qty, after_qty,
             change_qty, expiry_date, timestamp, operator, reason, order_no)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tx_type,
                barcode,
                from_shelf,
                to_shelf,
                before_qty,
                after_qty,
                change_qty,
                expiry_date,
                Utils.now_text(),
                operator,
                reason,
                order_no,
            ),
        )

    def log_operation(self, operator, action, order_no="", note=""):
        """V6.1：操作紀錄。所有登入、單據建立／完成／取消等重要操作皆須可追蹤。"""
        self.cursor.execute(
            """
            INSERT INTO operation_logs (timestamp, operator, action, order_no, note)
            VALUES (?,?,?,?,?)
            """,
            (Utils.now_text(), operator, action, order_no or "", note or ""),
        )
        self.conn.commit()

    def recent_operation_logs(self, limit=300):
        return self.cursor.execute(
            """
            SELECT timestamp, operator, action, order_no, note
            FROM operation_logs ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def product_by_barcode(self, barcode):
        return self.cursor.execute(
            "SELECT * FROM products WHERE barcode=?", (barcode,)
        ).fetchone()

    def shelf_by_code(self, shelf_code):
        return self.cursor.execute(
            "SELECT * FROM shelves WHERE shelf_code=?", (shelf_code,)
        ).fetchone()

    # ---------- V6.4：儲位管理（區域-貨架-層位） ----------

    def search_shelves(self, keyword="", status_filter="全部", sort_by="code"):
        """儲位查詢／排序；keyword 比對儲位代碼或備註，status_filter 為 全部／啟用／停用。"""
        keyword = keyword.strip().upper()
        order_clause = {
            "code": "s.is_special DESC, s.area, s.rack, s.level, s.shelf_code",
            "created": "s.created_at DESC",
            "stock": "stock_qty DESC",
        }.get(sort_by, "s.is_special DESC, s.area, s.rack, s.level, s.shelf_code")
        rows = self.cursor.execute(
            f"""
            SELECT s.shelf_code, s.zone, s.area, s.rack, s.level, s.status, s.is_special,
                   s.note, s.created_at, s.updated_at,
                   COALESCE((SELECT SUM(quantity) FROM inventory i WHERE i.shelf_code = s.shelf_code), 0) AS stock_qty
            FROM shelves s
            WHERE (? = '' OR UPPER(s.shelf_code) LIKE '%' || ? || '%' OR UPPER(COALESCE(s.note, '')) LIKE '%' || ? || '%')
              AND (? = '全部' OR s.status = ?)
            ORDER BY {order_clause}
            """,
            (keyword, keyword, keyword, status_filter, status_filter),
        ).fetchall()
        return rows

    def shelf_reference_summary(self, shelf_code):
        """修改／停用儲位前的防呆檢查：回傳目前庫存量與未完成出貨保留筆數。"""
        stock_qty = self.cursor.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS qty FROM inventory WHERE shelf_code=?", (shelf_code,)
        ).fetchone()["qty"]
        pending_allocations = self.cursor.execute(
            """
            SELECT COUNT(DISTINCT a.order_no) AS cnt
            FROM shipping_allocations a
            JOIN shipping_orders so ON so.order_no = a.order_no
            WHERE a.shelf_code=? AND so.status NOT IN ('已完成', '已取消')
            """,
            (shelf_code,),
        ).fetchone()["cnt"]
        return {"stock_qty": stock_qty, "pending_orders": pending_allocations}

    def create_shelf(self, area, rack, level, note=""):
        """新增儲位；格式為 區域(單一大寫字母)-貨架(2碼)-層位(2碼)，例如 A01-03。"""
        area = (area or "").strip().upper()
        if not re.fullmatch(r"[A-Z]", area):
            raise ValueError("區域請輸入單一英文字母，例如 A")
        try:
            rack_no, level_no = int(rack), int(level)
        except (TypeError, ValueError):
            raise ValueError("貨架與層位請輸入數字")
        if not (1 <= rack_no <= 99) or not (1 <= level_no <= 99):
            raise ValueError("貨架與層位請輸入 1 至 99 的數字")
        rack_text, level_text = f"{rack_no:02d}", f"{level_no:02d}"
        shelf_code = f"{area}{rack_text}-{level_text}"
        if self.shelf_by_code(shelf_code):
            raise ValueError(f"儲位 {shelf_code} 已存在")
        self.cursor.execute(
            """
            INSERT INTO shelves (shelf_code, zone, area, rack, level, status, is_special, note, created_at)
            VALUES (?,?,?,?,?, '啟用', 0, ?, ?)
            """,
            (shelf_code, area, area, rack_text, level_text, note.strip(), Utils.now_text()),
        )
        self.conn.commit()
        return shelf_code

    def rename_shelf(self, old_code, area, rack, level, note=None):
        """修改儲位代碼／備註；沿用階層式格式，並將既有庫存與保留記錄一併搬移到新代碼。"""
        shelf = self.shelf_by_code(old_code)
        if not shelf:
            raise ValueError("查無此儲位")
        if shelf["is_special"]:
            raise ValueError("特殊區（未上架／品檢區／報廢區／出貨暫存）不可修改代碼")
        area = (area or "").strip().upper()
        if not re.fullmatch(r"[A-Z]", area):
            raise ValueError("區域請輸入單一英文字母，例如 A")
        try:
            rack_no, level_no = int(rack), int(level)
        except (TypeError, ValueError):
            raise ValueError("貨架與層位請輸入數字")
        if not (1 <= rack_no <= 99) or not (1 <= level_no <= 99):
            raise ValueError("貨架與層位請輸入 1 至 99 的數字")
        rack_text, level_text = f"{rack_no:02d}", f"{level_no:02d}"
        new_code = f"{area}{rack_text}-{level_text}"
        if new_code != old_code and self.shelf_by_code(new_code):
            raise ValueError(f"儲位 {new_code} 已存在，不可重複")
        try:
            self.cursor.execute("BEGIN")
            if new_code != old_code:
                # 先建立新代碼再搬移庫存／保留紀錄，最後才移除舊代碼，避免違反外鍵限制。
                self.cursor.execute(
                    """
                    INSERT INTO shelves (shelf_code, zone, area, rack, level, status, is_special, note, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,0,?,?,?)
                    """,
                    (new_code, area, area, rack_text, level_text, shelf["status"],
                     note if note is not None else shelf["note"], shelf["created_at"], Utils.now_text()),
                )
                self.cursor.execute("UPDATE inventory SET shelf_code=? WHERE shelf_code=?", (new_code, old_code))
                self.cursor.execute("UPDATE shipping_allocations SET shelf_code=? WHERE shelf_code=?", (new_code, old_code))
                self.cursor.execute("DELETE FROM shelves WHERE shelf_code=?", (old_code,))
            elif note is not None:
                self.cursor.execute(
                    "UPDATE shelves SET note=?, updated_at=? WHERE shelf_code=?", (note, Utils.now_text(), old_code)
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return new_code

    def set_shelf_status(self, shelf_code, status):
        """啟用／停用儲位；不刪除單據，只切換狀態。"""
        shelf = self.shelf_by_code(shelf_code)
        if not shelf:
            raise ValueError("查無此儲位")
        if shelf["is_special"]:
            raise ValueError("特殊區（未上架／品檢區／報廢區／出貨暫存）不可停用")
        self.cursor.execute(
            "UPDATE shelves SET status=?, updated_at=? WHERE shelf_code=?", (status, Utils.now_text(), shelf_code)
        )
        self.conn.commit()

    def active_shelf_codes(self, include_special=False):
        query = "SELECT shelf_code FROM shelves WHERE status='啟用'"
        if not include_special:
            query += " AND is_special=0"
        query += " ORDER BY is_special DESC, area, rack, level, shelf_code"
        return [row["shelf_code"] for row in self.cursor.execute(query).fetchall()]

    def inventory_qty(self, shelf_code, barcode, expiry_date):
        row = self.cursor.execute(
            """
            SELECT quantity FROM inventory
            WHERE shelf_code=? AND barcode=? AND expiry_date=?
            """,
            (shelf_code, barcode, expiry_date),
        ).fetchone()
        return row["quantity"] if row else 0

    def add_inventory(self, shelf_code, barcode, expiry_date, quantity):
        """增加一筆庫存，回傳增加前與增加後數量。"""
        before_qty = self.inventory_qty(shelf_code, barcode, expiry_date)
        self.cursor.execute(
            """
            INSERT INTO inventory (shelf_code, barcode, expiry_date, quantity)
            VALUES (?,?,?,?)
            ON CONFLICT(shelf_code, barcode, expiry_date)
            DO UPDATE SET quantity = inventory.quantity + excluded.quantity
            """,
            (shelf_code, barcode, expiry_date, quantity),
        )
        return before_qty, before_qty + quantity

    def deduct_inventory(self, inventory_id, current_qty, deduct_qty):
        """從指定儲位批次扣除庫存，回傳扣除後數量。"""
        after_qty = current_qty - deduct_qty
        if after_qty < 0:
            raise ValueError("庫存扣除後不可小於 0")
        if after_qty == 0:
            self.cursor.execute("DELETE FROM inventory WHERE id=?", (inventory_id,))
        else:
            self.cursor.execute(
                "UPDATE inventory SET quantity=? WHERE id=?", (after_qty, inventory_id)
            )
        return after_qty

    # ---------- 商品主檔 ----------

    def save_product(self, old_barcode, barcode, sku, name, category, safety_stock, expiry_required):
        """新增或更新商品；變更條碼時同步搬移仍需關聯的資料。"""
        sku = (sku or "").strip()
        name = (name or "").strip()
        if not sku:
            raise ValueError("SKU 不可空白")
        if not name:
            raise ValueError("商品名稱不可空白")
        if not barcode:
            raise ValueError("商品條碼不可空白")
        # V6.1 防呆：同一 SKU 不可重複對應到不同條碼的商品。
        duplicate = self.cursor.execute(
            "SELECT barcode FROM products WHERE sku=? AND barcode<>?",
            (sku, old_barcode or barcode),
        ).fetchone()
        if duplicate:
            raise ValueError(f"SKU「{sku}」已被商品條碼 {duplicate['barcode']} 使用，不可重複")
        # V6.3 防呆：新增商品時條碼不可與既有商品重複（避免誤蓋既有商品資料）。
        if not old_barcode and self.product_by_barcode(barcode):
            raise ValueError(f"條碼 {barcode} 已被其他商品使用，不可新增重複條碼；如需編輯請於清單點選該商品")
        if old_barcode and old_barcode != barcode:
            if self.product_by_barcode(barcode):
                raise ValueError("新條碼已存在，不能與既有商品重複")
            try:
                self.cursor.execute("BEGIN")
                self.cursor.execute(
                    """
                    INSERT INTO products (barcode, sku, name, category, safety_stock, expiry_required)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (barcode, sku, name, category, safety_stock, int(expiry_required)),
                )
                self.cursor.execute(
                    "UPDATE inventory SET barcode=? WHERE barcode=?", (barcode, old_barcode)
                )
                self.cursor.execute(
                    "UPDATE shipping_order_items SET barcode=? WHERE barcode=?",
                    (barcode, old_barcode),
                )
                self.cursor.execute(
                    "UPDATE shipping_allocations SET barcode=? WHERE barcode=?",
                    (barcode, old_barcode),
                )
                self.cursor.execute("DELETE FROM products WHERE barcode=?", (old_barcode,))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return

        self.cursor.execute(
            """
            INSERT INTO products (barcode, sku, name, category, safety_stock, expiry_required)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(barcode) DO UPDATE SET
                sku=excluded.sku,
                name=excluded.name,
                category=excluded.category,
                safety_stock=excluded.safety_stock,
                expiry_required=excluded.expiry_required
            """,
            (barcode, sku, name, category, safety_stock, int(expiry_required)),
        )
        self.conn.commit()

    def all_products(self):
        return self.cursor.execute(
            """
            SELECT barcode, sku, name, category, safety_stock, expiry_required
            FROM products ORDER BY name COLLATE NOCASE, barcode
            """
        ).fetchall()

    # ---------- 分店主檔 ----------

    def active_branches(self):
        return self.cursor.execute(
            "SELECT * FROM branches WHERE active=1 ORDER BY code"
        ).fetchall()

    def branch_by_id(self, branch_id):
        return self.cursor.execute("SELECT * FROM branches WHERE id=?", (branch_id,)).fetchone()

    def save_branch(self, branch_id, code, name, address, contact_name, contact_phone, carrier):
        if branch_id:
            self.cursor.execute(
                """
                UPDATE branches
                SET code=?, name=?, address=?, contact_name=?, contact_phone=?, default_carrier=?
                WHERE id=?
                """,
                (code, name, address, contact_name, contact_phone, carrier, branch_id),
            )
        else:
            self.cursor.execute(
                """
                INSERT INTO branches (code, name, address, contact_name, contact_phone, default_carrier)
                VALUES (?,?,?,?,?,?)
                """,
                (code, name, address, contact_name, contact_phone, carrier),
            )
        self.conn.commit()

    # ---------- 進貨單與驗收 ----------

    def _generate_sequential_no(self, table, column, prefix_code):
        """共用：依「代碼-日期-流水號」格式產生單號，進貨單／出貨單／退貨單格式一致。"""
        prefix = f"{prefix_code}-{date.today():%Y%m%d}-"
        rows = self.cursor.execute(
            f"SELECT {column} FROM {table} WHERE {column} LIKE ?", (f"{prefix}%",)
        ).fetchall()
        latest = 0
        for row in rows:
            try:
                latest = max(latest, int(row[column].rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue
        return f"{prefix}{latest + 1:04d}"

    def generate_receiving_order_no(self):
        """產生可列印／可掃描的進貨單號，格式與出貨單一致。"""
        return self._generate_sequential_no("receiving_orders", "order_no", "RO")

    def create_receiving_order(self, supplier_name, items, operator, note=""):
        """建立進貨單。允許新品條碼先進單，但驗收前必須建立主檔。"""
        if not items:
            raise ValueError("進貨單至少需要一項商品")

        prepared_items = []
        seen_barcodes = set()
        for item in items:
            barcode = Utils.normalize_barcode(item["barcode"])
            name = item["name"].strip()
            try:
                required_qty = int(item["qty"])
            except (TypeError, ValueError) as error:
                raise ValueError("進貨數量必須是整數") from error
            if not Utils.valid_barcode(barcode):
                raise ValueError(f"商品條碼格式錯誤：{barcode}")
            if not name:
                raise ValueError(f"請輸入條碼 {barcode} 的商品名稱")
            if not 1 <= required_qty <= 100000:
                raise ValueError(f"{name} 的預計進貨數量必須是 1 至 100,000")
            if barcode in seen_barcodes:
                raise ValueError("同一商品請合併成一筆進貨數量")
            seen_barcodes.add(barcode)
            prepared_items.append((barcode, name, required_qty))

        order_no = self.generate_receiving_order_no()
        try:
            self.cursor.execute("BEGIN")
            self.cursor.execute(
                """
                INSERT INTO receiving_orders
                (order_no, supplier_name, order_date, status, created_at, created_by, note)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    order_no,
                    supplier_name.strip() or "未指定",
                    Utils.today_text(),
                    "已建立",
                    Utils.now_text(),
                    operator,
                    note.strip(),
                ),
            )
            for line_no, (barcode, name, quantity) in enumerate(prepared_items, start=1):
                self.cursor.execute(
                    """
                    INSERT INTO receiving_order_items
                    (order_no, line_no, barcode, product_name, required_qty)
                    VALUES (?,?,?,?,?)
                    """,
                    (order_no, line_no, barcode, name, quantity),
                )
            self.conn.commit()
            return order_no
        except Exception:
            self.conn.rollback()
            raise

    def receiving_order_header(self, order_no):
        return self.cursor.execute(
            "SELECT * FROM receiving_orders WHERE order_no=?", (order_no,)
        ).fetchone()

    def receiving_order_lines(self, order_no):
        return self.cursor.execute(
            """
            SELECT id, line_no, barcode, product_name, required_qty, received_qty
            FROM receiving_order_items WHERE order_no=? ORDER BY line_no
            """,
            (order_no,),
        ).fetchall()

    def all_receiving_orders(self, order_no_filter=""):
        """供獨立查詢頁使用；查詢本身完全不改變單據狀態。"""
        keyword = order_no_filter.strip().upper()
        return self.cursor.execute(
            """
            SELECT ro.order_no, ro.order_date, ro.supplier_name, ro.status,
                   COUNT(roi.id) AS line_count, COALESCE(SUM(roi.required_qty), 0) AS total_qty,
                   COALESCE(SUM(roi.received_qty), 0) AS received_qty,
                   ro.print_count AS print_count, ro.last_printed_at AS last_printed_at
            FROM receiving_orders ro
            LEFT JOIN receiving_order_items roi ON roi.order_no=ro.order_no
            WHERE (? = '' OR UPPER(ro.order_no) LIKE ?)
            GROUP BY ro.order_no
            ORDER BY ro.created_at DESC
            """,
            (keyword, f"%{keyword}%"),
        ).fetchall()

    def missing_products_for_receiving_order(self, order_no):
        return [
            line for line in self.receiving_order_lines(order_no)
            if not self.product_by_barcode(line["barcode"])
        ]

    def set_receiving_order_status(self, order_no, new_status, operator):
        """依既定流程推進單據，避免查詢或誤按跳過採購／到貨節點。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        allowed = {
            "已建立": "已送出訂單",
            "已送出訂單": "待驗收",
        }
        if allowed.get(header["status"]) != new_status:
            raise ValueError(
                f"進貨單目前為「{header['status']}」，不可直接改為「{new_status}」"
            )
        if new_status == "已送出訂單":
            self.cursor.execute(
                """
                UPDATE receiving_orders SET status=?, sent_at=?, sent_by=?
                WHERE order_no=?
                """,
                (new_status, Utils.now_text(), operator, order_no),
            )
        else:
            self.cursor.execute(
                """
                UPDATE receiving_orders
                SET status=?, ready_for_receipt_at=?, ready_for_receipt_by=?
                WHERE order_no=?
                """,
                (new_status, Utils.now_text(), operator, order_no),
            )
        self.conn.commit()
        return self.receiving_order_header(order_no)

    def start_receiving(self, order_no):
        """只有到貨且待驗收的單據才能開始掃描；載入查詢不會改變狀態。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] == "已完成":
            return header
        if header["status"] == "驗收中":
            return header
        if header["status"] != "待驗收":
            raise ValueError("請先於「查詢進貨單」完成送單及到貨登錄，才可開始驗收")
        self.cursor.execute(
            "UPDATE receiving_orders SET status='驗收中' WHERE order_no=?", (order_no,)
        )
        self.conn.commit()
        return self.receiving_order_header(order_no)

    def scan_receiving_item(self, order_no, barcode, quantity, expiry_date, operator):
        """驗收一項商品並立即寫入未上架區；所有限制在資料層再次檢核。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] == "已完成":
            raise ValueError("此進貨單已完成，只能查詢，不能重複進貨")
        if header["status"] != "驗收中":
            raise ValueError("此進貨單目前不可驗收")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("本次驗收數量必須是正整數")

        barcode = Utils.normalize_barcode(barcode)
        line = self.cursor.execute(
            """
            SELECT id, product_name, required_qty, received_qty
            FROM receiving_order_items WHERE order_no=? AND barcode=?
            """,
            (order_no, barcode),
        ).fetchone()
        if not line:
            raise ValueError("此商品不在目前進貨單內，請先核對單據")
        product = self.product_by_barcode(barcode)
        if not product:
            raise ValueError(
                f"{line['product_name']}（{barcode}）尚未建立商品主檔，請先至商品主檔建檔"
            )
        remaining = line["required_qty"] - line["received_qty"]
        if quantity > remaining:
            raise ValueError(
                f"{line['product_name']} 單據數量為 {line['required_qty']}，尚可驗收 {remaining}；本次不可輸入 {quantity}"
            )

        if product["expiry_required"]:
            valid, expired, _days = Utils.validate_date(expiry_date)
            if not valid:
                raise ValueError("效期格式錯誤，請輸入 YYYY-MM-DD")
            if expired:
                raise ValueError("嚴禁驗收已過期商品")
        else:
            expiry_date = NO_EXPIRY_DATE

        try:
            self.cursor.execute("BEGIN")
            before_qty, after_qty = self.add_inventory("未上架", barcode, expiry_date, quantity)
            self.cursor.execute(
                "UPDATE receiving_order_items SET received_qty=received_qty+? WHERE id=?",
                (quantity, line["id"]),
            )
            self.log_transaction(
                "進貨驗收",
                barcode,
                "供應商",
                "未上架",
                before_qty,
                after_qty,
                quantity,
                expiry_date,
                operator,
                reason=f"進貨單 {order_no} 驗收",
                order_no=order_no,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return line["product_name"], line["received_qty"] + quantity, line["required_qty"]

    def reset_receiving_scan_progress(self, order_no, operator):
        """V6.6：商品歸零。驗收過程中若誤刷，可將此進貨單目前已驗收的數量與對應未上架庫存全部歸零重來。
        以目前各品項的 received_qty 為準去反扣未上架庫存，可重複執行而不出錯（自我校正，不依賴歷史交易重播）。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] != "驗收中":
            raise ValueError("僅「驗收中」的進貨單可以執行商品歸零")
        lines = self.cursor.execute(
            "SELECT barcode, received_qty FROM receiving_order_items WHERE order_no=? AND received_qty>0",
            (order_no,),
        ).fetchall()
        if not lines:
            raise ValueError("此進貨單尚未驗收任何商品，無需歸零")
        try:
            self.cursor.execute("BEGIN")
            for line in lines:
                remaining_to_deduct = line["received_qty"]
                batches = self.cursor.execute(
                    "SELECT id, quantity, expiry_date FROM inventory WHERE shelf_code='未上架' AND barcode=? ORDER BY id",
                    (line["barcode"],),
                ).fetchall()
                available = sum(batch["quantity"] for batch in batches)
                if available < remaining_to_deduct:
                    raise ValueError(
                        f"商品 {line['barcode']} 部分數量可能已上架或異動，無法歸零；如需重驗，請聯絡管理員以退貨或盤點方式處理"
                    )
                for batch in batches:
                    if remaining_to_deduct == 0:
                        break
                    deduct_qty = min(remaining_to_deduct, batch["quantity"])
                    after_qty = self.deduct_inventory(batch["id"], batch["quantity"], deduct_qty)
                    self.log_transaction(
                        "驗收歸零",
                        line["barcode"],
                        "未上架",
                        "作廢",
                        batch["quantity"],
                        after_qty,
                        -deduct_qty,
                        batch["expiry_date"],
                        operator,
                        reason=f"進貨單 {order_no} 商品歸零",
                        order_no=order_no,
                    )
                    remaining_to_deduct -= deduct_qty
            self.cursor.execute(
                "UPDATE receiving_order_items SET received_qty=0 WHERE order_no=?", (order_no,)
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def complete_receiving(self, order_no, operator):
        """只有所有品項足額、且商品皆有主檔時才可完成並鎖定進貨單。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] == "已完成":
            raise ValueError("此進貨單已完成，只能查詢")
        if header["status"] != "驗收中":
            raise ValueError("請先將進貨單帶入掃描驗貨並開始驗收")
        missing = self.missing_products_for_receiving_order(order_no)
        if missing:
            details = "、".join(f"{row['product_name']}（{row['barcode']}）" for row in missing)
            raise ValueError(f"尚未建立商品主檔：{details}")
        incomplete = self.cursor.execute(
            """
            SELECT product_name, received_qty, required_qty
            FROM receiving_order_items
            WHERE order_no=? AND received_qty <> required_qty
            """,
            (order_no,),
        ).fetchall()
        if incomplete:
            details = "、".join(
                f"{row['product_name']} ({row['received_qty']}/{row['required_qty']})"
                for row in incomplete
            )
            raise ValueError(f"尚未驗收完成：{details}")
        self.cursor.execute(
            """
            UPDATE receiving_orders
            SET status='已完成', received_at=?, received_by=?
            WHERE order_no=? AND status <> '已完成'
            """,
            (Utils.now_text(), operator, order_no),
        )
        self.conn.commit()

    def cancel_receiving_order(self, order_no, operator):
        """V6.1：進貨單取消。只有尚未完成的單據可取消，取消後保留歷史紀錄，禁止直接刪除。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] == "已完成":
            raise ValueError("已完成的進貨單不能取消，請以退貨流程處理")
        if header["status"] == "已取消":
            raise ValueError("此進貨單已取消")
        self.cursor.execute(
            """
            UPDATE receiving_orders
            SET status='已取消', cancelled_at=?, cancelled_by=?, cancel_reason=?
            WHERE order_no=?
            """,
            (Utils.now_text(), operator, f"由 {operator} 取消", order_no),
        )
        self.conn.commit()

    def remove_receiving_order_item(self, order_no, barcode, operator):
        """V6.1：移除進貨單中誤加入的商品明細，僅限尚未開始驗收、且該筆尚未驗收任何數量。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] in ("已完成", "已取消"):
            raise ValueError(f"進貨單目前為「{header['status']}」，不可移除商品")
        line = self.cursor.execute(
            "SELECT id, received_qty FROM receiving_order_items WHERE order_no=? AND barcode=?",
            (order_no, barcode),
        ).fetchone()
        if not line:
            raise ValueError("此商品不在進貨單內")
        if line["received_qty"] > 0:
            raise ValueError("此商品已有驗收數量，不能移除，請改用退貨流程")
        remaining_lines = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM receiving_order_items WHERE order_no=?", (order_no,)
        ).fetchone()["cnt"]
        if remaining_lines <= 1:
            raise ValueError("進貨單至少需保留一項商品，如需清空請直接取消整張進貨單")
        self.cursor.execute("DELETE FROM receiving_order_items WHERE id=?", (line["id"],))
        self.conn.commit()

    # ---------- 退貨／還貨 ----------

    def generate_return_no(self):
        return self._generate_sequential_no("return_orders", "return_no", "RT")

    def create_return_order(
        self, receiving_order_no, barcode, quantity, reason, operator, note="", evidence_path=""
    ):
        """建立供應商退貨紀錄；不在缺少儲位與效期資訊時自動扣庫存。"""
        receiving_order_no = receiving_order_no.strip().upper()
        barcode = Utils.normalize_barcode(barcode)
        if not self.receiving_order_header(receiving_order_no):
            raise ValueError("進貨單號不存在，請先核對原始進貨單")
        if not Utils.valid_barcode(barcode):
            raise ValueError("商品條碼格式錯誤")
        if not isinstance(quantity, int) or not 1 <= quantity <= 100000:
            raise ValueError("退貨數量必須是 1 至 100,000 的整數")
        if reason not in RETURN_REASONS:
            raise ValueError("請選擇有效的退貨原因")
        line = self.cursor.execute(
            """
            SELECT product_name, required_qty FROM receiving_order_items
            WHERE order_no=? AND barcode=?
            """,
            (receiving_order_no, barcode),
        ).fetchone()
        if not line:
            raise ValueError("此商品不在該進貨單內，請核對進貨單號與商品條碼")
        returned = self.cursor.execute(
            """
            SELECT COALESCE(SUM(return_qty), 0) AS qty FROM return_orders
            WHERE receiving_order_no=? AND barcode=? AND status <> '已取消'
            """,
            (receiving_order_no, barcode),
        ).fetchone()["qty"]
        if returned + quantity > line["required_qty"]:
            raise ValueError(
                f"{line['product_name']} 此進貨單最多可登錄 {line['required_qty']} 件退貨；"
                f"目前已登錄 {returned} 件"
            )
        return_no = self.generate_return_no()
        self.cursor.execute(
            """
            INSERT INTO return_orders
            (return_no, receiving_order_no, barcode, product_name, return_qty,
             return_reason, evidence_path, note, created_at, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                return_no,
                receiving_order_no,
                barcode,
                line["product_name"],
                quantity,
                reason,
                evidence_path,
                note.strip(),
                Utils.now_text(),
                operator,
            ),
        )
        self.conn.commit()
        return return_no

    def return_order_header(self, return_no):
        return self.cursor.execute(
            "SELECT * FROM return_orders WHERE return_no=?", (return_no,)
        ).fetchone()

    def all_return_orders(self):
        return self.cursor.execute(
            """
            SELECT return_no, receiving_order_no, barcode, product_name, return_qty,
                   return_reason, status, evidence_path, created_at
            FROM return_orders ORDER BY created_at DESC
            """
        ).fetchall()

    def set_return_evidence(self, return_no, evidence_path):
        self.cursor.execute(
            "UPDATE return_orders SET evidence_path=? WHERE return_no=?",
            (evidence_path, return_no),
        )
        self.conn.commit()

    def mark_return_shipped(self, return_no, operator):
        header = self.return_order_header(return_no)
        if not header:
            raise ValueError("查無退貨單")
        if header["status"] == "已寄回供應商":
            raise ValueError("此退貨單已標記為寄回供應商")
        self.cursor.execute(
            """
            UPDATE return_orders
            SET status='已寄回供應商', shipped_at=?, shipped_by=?
            WHERE return_no=?
            """,
            (Utils.now_text(), operator, return_no),
        )
        self.conn.commit()

    # ---------- 出貨單與配貨 ----------

    def generate_order_no(self):
        return self._generate_sequential_no("shipping_orders", "order_no", "SO")

    def available_batches_for_order(self, barcode):
        """取得可配貨庫存，並扣除其他未完成出貨單已保留的數量。"""
        query = """
            SELECT i.id, i.shelf_code, i.expiry_date, i.quantity,
                   COALESCE((
                       SELECT SUM(a.allocated_qty - a.shipped_qty)
                       FROM shipping_allocations a
                       JOIN shipping_orders so ON so.order_no = a.order_no
                       WHERE a.barcode = i.barcode
                         AND a.shelf_code = i.shelf_code
                         AND a.expiry_date = i.expiry_date
                         AND so.status IN ('待撿貨', '包裝中')
                   ), 0) AS reserved_qty
            FROM inventory i
            JOIN shelves s ON s.shelf_code = i.shelf_code
            WHERE i.barcode = ?
              AND s.zone NOT IN ('Staging', 'QC', 'Scrap', 'Outbound')
              AND (i.expiry_date = '' OR i.expiry_date >= ?)
            ORDER BY CASE WHEN i.expiry_date = '' THEN '9999-12-31' ELSE i.expiry_date END,
                     i.shelf_code
        """
        rows = self.cursor.execute(query, (barcode, Utils.today_text())).fetchall()
        return [row for row in rows if row["quantity"] - row["reserved_qty"] > 0]

    def available_qty_for_order(self, barcode):
        return sum(
            row["quantity"] - row["reserved_qty"]
            for row in self.available_batches_for_order(barcode)
        )

    def create_shipping_order(self, branch_id, carrier, tracking_no, box_count, items, operator):
        """建立出貨單並依 FEFO 保留儲位與批次；尚未扣除實體庫存。"""
        if not items:
            raise ValueError("出貨單至少需要一項商品")

        plans = []
        seen_barcodes = set()
        for item in items:
            barcode = item["barcode"]
            required_qty = int(item["qty"])
            if barcode in seen_barcodes:
                raise ValueError("同一商品請合併成一筆出貨數量")
            seen_barcodes.add(barcode)
            product = self.product_by_barcode(barcode)
            if not product:
                raise ValueError(f"商品條碼 {barcode} 已不存在")

            remaining = required_qty
            allocations = []
            for batch in self.available_batches_for_order(barcode):
                free_qty = batch["quantity"] - batch["reserved_qty"]
                allocate_qty = min(remaining, free_qty)
                if allocate_qty > 0:
                    allocations.append(
                        {
                            "shelf_code": batch["shelf_code"],
                            "expiry_date": batch["expiry_date"] or NO_EXPIRY_DATE,
                            "qty": allocate_qty,
                        }
                    )
                    remaining -= allocate_qty
                if remaining == 0:
                    break
            if remaining > 0:
                available = required_qty - remaining
                raise ValueError(
                    f"{product['name']} 可配庫存不足：需要 {required_qty}，目前可配 {available}"
                )
            plans.append(
                {
                    "barcode": barcode,
                    "name": product["name"],
                    "qty": required_qty,
                    "allocations": allocations,
                }
            )

        order_no = self.generate_order_no()
        try:
            self.cursor.execute("BEGIN")
            self.cursor.execute(
                """
                INSERT INTO shipping_orders
                (order_no, branch_id, order_date, status, carrier, tracking_no,
                 box_count, created_at, created_by)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    order_no,
                    branch_id,
                    Utils.today_text(),
                    "待撿貨",
                    carrier or "未指定",
                    tracking_no,
                    box_count,
                    Utils.now_text(),
                    operator,
                ),
            )
            for line_no, plan in enumerate(plans, start=1):
                self.cursor.execute(
                    """
                    INSERT INTO shipping_order_items
                    (order_no, line_no, barcode, product_name, required_qty)
                    VALUES (?,?,?,?,?)
                    """,
                    (order_no, line_no, plan["barcode"], plan["name"], plan["qty"]),
                )
                for allocation in plan["allocations"]:
                    self.cursor.execute(
                        """
                        INSERT INTO shipping_allocations
                        (order_no, barcode, shelf_code, expiry_date, allocated_qty)
                        VALUES (?,?,?,?,?)
                        """,
                        (
                            order_no,
                            plan["barcode"],
                            allocation["shelf_code"],
                            allocation["expiry_date"],
                            allocation["qty"],
                        ),
                    )
            self.conn.commit()
            return order_no
        except Exception:
            self.conn.rollback()
            raise

    def order_header(self, order_no):
        return self.cursor.execute(
            """
            SELECT so.*, b.code AS branch_code, b.name AS branch_name,
                   b.address, b.contact_name, b.contact_phone
            FROM shipping_orders so
            JOIN branches b ON b.id = so.branch_id
            WHERE so.order_no=?
            """,
            (order_no,),
        ).fetchone()

    def order_lines(self, order_no):
        lines = self.cursor.execute(
            """
            SELECT id, line_no, barcode, product_name, required_qty, scanned_qty
            FROM shipping_order_items
            WHERE order_no=? ORDER BY line_no
            """,
            (order_no,),
        ).fetchall()
        result = []
        for line in lines:
            allocations = self.cursor.execute(
                """
                SELECT shelf_code, expiry_date, allocated_qty, shipped_qty
                FROM shipping_allocations
                WHERE order_no=? AND barcode=?
                ORDER BY expiry_date, shelf_code
                """,
                (order_no, line["barcode"]),
            ).fetchall()
            result.append((line, allocations))
        return result

    def all_orders(self):
        return self.cursor.execute(
            """
            SELECT so.order_no, so.order_date, b.code AS branch_code, b.name AS branch_name,
                   so.status, so.carrier, so.tracking_no, so.box_count, so.print_count,
                   so.label_printed, so.last_printed_at, so.label_print_count, so.label_last_printed_at,
                   SUM(oi.required_qty) AS total_qty,
                   COUNT(oi.id) AS line_count
            FROM shipping_orders so
            JOIN branches b ON b.id = so.branch_id
            JOIN shipping_order_items oi ON oi.order_no = so.order_no
            GROUP BY so.order_no
            ORDER BY so.created_at DESC
            """
        ).fetchall()

    def search_shipping_orders(self, order_no="", date_text="", keyword="", branch_keyword=""):
        """V6.1：出貨單查詢頁專用；可依單號、日期、商品名稱／SKU、門市查詢，純查詢不改變狀態。"""
        order_no = order_no.strip().upper()
        date_text = date_text.strip()
        keyword = keyword.strip().upper()
        branch_keyword = branch_keyword.strip().upper()
        rows = self.cursor.execute(
            """
            SELECT DISTINCT so.order_no, so.order_date, so.status, so.created_by, so.created_at,
                   b.code AS branch_code, b.name AS branch_name,
                   COUNT(oi.id) OVER (PARTITION BY so.order_no) AS line_count
            FROM shipping_orders so
            JOIN branches b ON b.id = so.branch_id
            JOIN shipping_order_items oi ON oi.order_no = so.order_no
            LEFT JOIN products p ON p.barcode = oi.barcode
            WHERE (? = '' OR UPPER(so.order_no) LIKE '%' || ? || '%')
              AND (? = '' OR so.order_date = ?)
              AND (? = '' OR UPPER(oi.product_name) LIKE '%' || ? || '%'
                        OR UPPER(oi.barcode) LIKE '%' || ? || '%'
                        OR UPPER(COALESCE(p.sku, '')) LIKE '%' || ? || '%')
              AND (? = '' OR UPPER(b.code) LIKE '%' || ? || '%'
                        OR UPPER(b.name) LIKE '%' || ? || '%')
            ORDER BY so.created_at DESC
            """,
            (
                order_no, order_no,
                date_text, date_text,
                keyword, keyword, keyword, keyword,
                branch_keyword, branch_keyword, branch_keyword,
            ),
        ).fetchall()
        return rows

    def start_packing(self, order_no):
        header = self.order_header(order_no)
        if not header:
            raise ValueError("查無此出貨單")
        # 已完成／已取消單據仍可讀取明細，但絕不能被重開或改寫。
        if header["status"] in ("已取消", "已完成"):
            return header
        if header["status"] == "待撿貨":
            self.cursor.execute(
                "UPDATE shipping_orders SET status='包裝中' WHERE order_no=?", (order_no,)
            )
            self.conn.commit()
            header = self.order_header(order_no)
        return header

    def scan_order_item(self, order_no, barcode, quantity):
        header = self.start_packing(order_no)
        if header["status"] == "已完成":
            raise ValueError("此出貨單已完成，只能查詢，不能重複出貨")
        if header["status"] == "已取消":
            raise ValueError("此出貨單已取消，只能查詢")
        line = self.cursor.execute(
            """
            SELECT id, product_name, required_qty, scanned_qty
            FROM shipping_order_items WHERE order_no=? AND barcode=?
            """,
            (order_no, barcode),
        ).fetchone()
        if not line:
            raise ValueError("此商品不在目前出貨單內，請勿放入箱內")
        remaining = line["required_qty"] - line["scanned_qty"]
        if quantity > remaining:
            raise ValueError(
                f"{line['product_name']} 只剩 {remaining} 件未掃，掃描數量不可超過需求"
            )
        self.cursor.execute(
            "UPDATE shipping_order_items SET scanned_qty=scanned_qty+? WHERE id=?",
            (quantity, line["id"]),
        )
        self.conn.commit()
        return line["product_name"], line["scanned_qty"] + quantity, line["required_qty"]

    def reset_packing_scan_progress(self, order_no):
        """V6.6：商品歸零。出貨掃描過程中若誤刷，可將此出貨單目前已掃描的數量全部歸零重來。
        掃描階段尚未扣庫存（扣庫存於完成包裝時才發生），因此僅需重置已掃數量。"""
        header = self.order_header(order_no)
        if not header:
            raise ValueError("查無此出貨單")
        if header["status"] not in ("待撿貨", "包裝中"):
            raise ValueError("僅「包裝中」的出貨單可以執行商品歸零")
        self.cursor.execute(
            "UPDATE shipping_order_items SET scanned_qty=0 WHERE order_no=?", (order_no,)
        )
        self.conn.commit()

    def complete_packing(self, order_no, operator):
        header = self.order_header(order_no)
        if not header:
            raise ValueError("查無此出貨單")
        if header["status"] == "已完成":
            raise ValueError("此單已完成出貨")
        if header["status"] == "已取消":
            raise ValueError("已取消單據不能出貨")

        incomplete = self.cursor.execute(
            """
            SELECT product_name, required_qty, scanned_qty
            FROM shipping_order_items
            WHERE order_no=? AND scanned_qty <> required_qty
            """,
            (order_no,),
        ).fetchall()
        if incomplete:
            details = "、".join(
                f"{row['product_name']} ({row['scanned_qty']}/{row['required_qty']})"
                for row in incomplete
            )
            raise ValueError(f"尚未掃描完成：{details}")

        allocations = self.cursor.execute(
            """
            SELECT a.id, a.barcode, a.shelf_code, a.expiry_date, a.allocated_qty,
                   i.id AS inventory_id, i.quantity AS current_qty
            FROM shipping_allocations a
            LEFT JOIN inventory i
              ON i.shelf_code=a.shelf_code
             AND i.barcode=a.barcode
             AND i.expiry_date=a.expiry_date
            WHERE a.order_no=?
            ORDER BY a.expiry_date, a.shelf_code
            """,
            (order_no,),
        ).fetchall()
        today = Utils.today_text()
        for allocation in allocations:
            if allocation["inventory_id"] is None or allocation["current_qty"] < allocation["allocated_qty"]:
                raise ValueError(
                    f"儲位 {allocation['shelf_code']} 的保留庫存不足，請先盤點或重新建立出貨單"
                )
            if allocation["expiry_date"] not in ("", NO_EXPIRY_DATE) and allocation["expiry_date"] < today:
                raise ValueError(
                    f"儲位 {allocation['shelf_code']} 有已過期批次，請改由有效批次出貨"
                )

        try:
            self.cursor.execute("BEGIN")
            for allocation in allocations:
                before_qty = allocation["current_qty"]
                after_qty = self.deduct_inventory(
                    allocation["inventory_id"], before_qty, allocation["allocated_qty"]
                )
                self.cursor.execute(
                    "UPDATE shipping_allocations SET shipped_qty=allocated_qty WHERE id=?",
                    (allocation["id"],),
                )
                self.log_transaction(
                    "訂單出貨",
                    allocation["barcode"],
                    allocation["shelf_code"],
                    f"分店:{header['branch_code']}",
                    before_qty,
                    after_qty,
                    -allocation["allocated_qty"],
                    allocation["expiry_date"],
                    operator,
                    reason=f"出貨單 {order_no}",
                    order_no=order_no,
                )
            self.cursor.execute(
                """
                UPDATE shipping_orders
                SET status='已完成', packed_at=?, packed_by=?
                WHERE order_no=?
                """,
                (Utils.now_text(), operator, order_no),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def cancel_order(self, order_no, operator):
        header = self.order_header(order_no)
        if not header:
            raise ValueError("查無此出貨單")
        if header["status"] == "已完成":
            raise ValueError("已完成出貨的單據不能取消，請以退貨流程處理")
        if header["status"] == "已取消":
            raise ValueError("此單據已取消")
        self.cursor.execute(
            """
            UPDATE shipping_orders
            SET status='已取消', cancelled_at=?, cancel_reason=?
            WHERE order_no=?
            """,
            (Utils.now_text(), f"由 {operator} 取消", order_no),
        )
        self.cursor.execute(
            "UPDATE shipping_order_items SET scanned_qty=0 WHERE order_no=?", (order_no,)
        )
        self.conn.commit()

    def remove_shipping_order_item(self, order_no, barcode, operator):
        """V6.1：移除出貨單中誤加入的商品明細，僅限尚未掃描、且單據尚未完成／取消。"""
        header = self.order_header(order_no)
        if not header:
            raise ValueError("查無此出貨單")
        if header["status"] in ("已完成", "已取消"):
            raise ValueError(f"出貨單目前為「{header['status']}」，不可移除商品")
        line = self.cursor.execute(
            "SELECT id, scanned_qty FROM shipping_order_items WHERE order_no=? AND barcode=?",
            (order_no, barcode),
        ).fetchone()
        if not line:
            raise ValueError("此商品不在出貨單內")
        if line["scanned_qty"] > 0:
            raise ValueError("此商品已有掃描數量，不能移除")
        remaining_lines = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM shipping_order_items WHERE order_no=?", (order_no,)
        ).fetchone()["cnt"]
        if remaining_lines <= 1:
            raise ValueError("出貨單至少需保留一項商品，如需清空請直接取消整張出貨單")
        try:
            self.cursor.execute("BEGIN")
            self.cursor.execute(
                "DELETE FROM shipping_allocations WHERE order_no=? AND barcode=?",
                (order_no, barcode),
            )
            self.cursor.execute("DELETE FROM shipping_order_items WHERE id=?", (line["id"],))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def mark_order_printed(self, order_no):
        self.cursor.execute(
            "UPDATE shipping_orders SET print_count=print_count+1, last_printed_at=? WHERE order_no=?",
            (Utils.now_text(), order_no),
        )
        self.conn.commit()
        return self.order_header(order_no)["print_count"]

    def mark_receiving_order_printed(self, order_no):
        self.cursor.execute(
            "UPDATE receiving_orders SET print_count=print_count+1, last_printed_at=? WHERE order_no=?",
            (Utils.now_text(), order_no),
        )
        self.conn.commit()
        return self.receiving_order_header(order_no)["print_count"]

    def mark_label_printed(self, order_no):
        self.cursor.execute(
            """
            UPDATE shipping_orders
            SET label_printed=1, label_print_count=label_print_count+1, label_last_printed_at=?
            WHERE order_no=?
            """,
            (Utils.now_text(), order_no),
        )
        self.conn.commit()
        return self.order_header(order_no)["label_print_count"]

    def close(self):
        self.conn.close()


class WMSApp:
    """WMS 的主要使用者介面。"""

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_VERSION} - 物流與庫存管理")
        self.root.geometry("1500x900")
        self.root.minsize(1180, 720)
        self.db = DBManager()
        self.current_user = None
        self.login_time = None
        self.active_order_no = None
        self.active_receiving_order_no = None
        self.shipping_read_only = False
        self.receiving_read_only = False
        self.order_draft_items = []
        self.receiving_draft_items = []
        self.product_selected_barcode = None
        self.branch_selected_id = None

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_login_view()

    def on_close(self):
        if self.current_user:
            try:
                self.db.log_operation(self.current_user, "登出", note=f"登入者：{self.current_user}")
            except Exception:
                pass
        self.db.close()
        self.root.destroy()

    # ---------- 登入畫面 ----------

    def build_login_view(self):
        """V6.1：啟動時先顯示登入畫面，登入成功後才能進入主系統。"""
        self.login_frame = tb.Frame(self.root, bootstyle="light")
        self.login_frame.pack(fill=BOTH, expand=True)

        card = tb.Frame(self.login_frame, bootstyle="light", padding=30)
        card.place(relx=0.5, rely=0.5, anchor=CENTER)

        tb.Label(
            card, text="泡泡貓WMS", font=("Microsoft JhengHei", 26, "bold"), bootstyle="primary"
        ).pack(anchor=W)
        tb.Label(
            card, text=f"{APP_VERSION}　請登入以繼續", font=("Microsoft JhengHei", 10), bootstyle="secondary"
        ).pack(anchor=W, pady=(0, 18))

        form = tb.Frame(card)
        form.pack(fill=X)
        self.login_account_entry = tb.Entry(form, width=28)
        self.login_password_entry = tb.Entry(form, width=28, show="*")
        self.login_name_entry = tb.Entry(form, width=28)
        rows = [
            ("帳號", self.login_account_entry),
            ("密碼", self.login_password_entry),
            ("使用者姓名", self.login_name_entry),
        ]
        for index, (label, widget) in enumerate(rows):
            tb.Label(form, text=f"{label}:").grid(row=index, column=0, sticky=W, padx=(0, 10), pady=7)
            widget.grid(row=index, column=1, sticky=W, pady=7)

        self.login_status = tb.Label(card, text="", bootstyle="danger")
        self.login_status.pack(anchor=W, pady=(6, 6))

        tb.Button(card, text="登入", bootstyle="primary", command=self.attempt_login).pack(anchor="e", pady=(6, 0))

        self.login_account_entry.bind("<Return>", lambda _e: self.login_password_entry.focus_set())
        self.login_password_entry.bind("<Return>", lambda _e: self.login_name_entry.focus_set())
        self.login_name_entry.bind("<Return>", lambda _e: self.attempt_login())
        self.login_account_entry.focus_set()

    def attempt_login(self):
        account = self.login_account_entry.get().strip()
        password = self.login_password_entry.get().strip()
        name = self.login_name_entry.get().strip()
        if not name:
            return self.set_status(self.login_status, "使用者姓名為必填", "danger")
        if account != LOGIN_ACCOUNT or password != LOGIN_PASSWORD:
            return self.set_status(self.login_status, "帳號或密碼錯誤，請重新輸入", "danger")
        self.current_user = name
        self.login_time = Utils.now_text()
        self.db.log_operation(self.current_user, "登入", note=f"登入時間 {self.login_time}")
        self.login_frame.destroy()
        self.build_ui()
        self.show_view("dashboard")

    # ---------- 共用 UI ----------

    def build_ui(self):
        main_frame = tb.Frame(self.root)
        main_frame.pack(fill=BOTH, expand=True)

        self.sidebar = tb.Frame(main_frame, bootstyle="dark", width=220)
        self.sidebar.pack(side=LEFT, fill=Y)
        self.sidebar.pack_propagate(False)

        tb.Label(
            self.sidebar,
            text="泡泡貓WMS",
            font=("Microsoft JhengHei", 22, "bold"),
            bootstyle="inverse-dark",
        ).pack(anchor=W, padx=22, pady=(24, 2))
        tb.Label(
            self.sidebar,
            text="物流與庫存管理",
            font=("Microsoft JhengHei", 10),
            bootstyle="inverse-secondary",
        ).pack(anchor=W, padx=24, pady=(0, 26))

        self.menu_buttons = {}
        menu_items = [
            ("總覽", "dashboard"),
            ("商品主檔", "products"),
            ("庫存查詢", "inventory"),
            ("進貨作業", "receiving"),
            ("上架作業", "putaway"),
            ("出貨單管理", "orders"),
            ("出貨作業", "shipping"),
            ("盤點作業", "counting"),
            ("儲位管理", "shelves"),
            ("分店管理", "branches"),
            ("退貨作業", "returns"),
            ("作業紀錄", "history"),
        ]
        for text, mode in menu_items:
            button = tb.Button(
                self.sidebar,
                text=text,
                bootstyle="dark-outline",
                command=lambda selected=mode: self.show_view(selected),
            )
            button.pack(fill=X, padx=12, pady=3)
            self.menu_buttons[mode] = button

        tb.Label(
            self.sidebar,
            text=f"登入者\n{self.current_user}\n登入時間 {self.login_time}",
            justify=LEFT,
            font=("Microsoft JhengHei", 9),
            bootstyle="inverse-secondary",
        ).pack(side="bottom", anchor=W, padx=22, pady=22)

        self.content_frame = tb.Frame(main_frame, bootstyle="light")
        self.content_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=20, pady=18)

        self.setup_context_menus()

        self.views = {
            "dashboard": self.build_dashboard_view(),
            "products": self.build_product_view(),
            "branches": self.build_branch_view(),
            "shelves": self.build_shelf_view(),
            "inventory": self.build_inventory_view(),
            "receiving": self.build_receiving_view(),
            "returns": self.build_returns_view(),
            "putaway": self.build_putaway_view(),
            "orders": self.build_orders_view(),
            "shipping": self.build_shipping_view(),
            "counting": self.build_counting_view(),
            "history": self.build_history_view(),
        }

    def make_title(self, frame, title, subtitle):
        header = tb.Frame(frame, bootstyle="light")
        header.pack(fill=X, pady=(0, 14))
        tb.Label(
            header,
            text=title,
            font=("Microsoft JhengHei", 20, "bold"),
            bootstyle="inverse-light",
        ).pack(anchor=W)
        tb.Label(
            header,
            text=subtitle,
            font=("Microsoft JhengHei", 10),
            bootstyle="secondary",
        ).pack(anchor=W, pady=(2, 0))

    def clear_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def set_status(self, label, text, style="secondary"):
        label.configure(text=text, bootstyle=style)

    def setup_tree_columns(self, tree, columns, headings, widths, left_columns=()):
        """共用：設定 Treeview 欄位標題、寬度與對齊方式，避免重複 for 迴圈。"""
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor=W if column in left_columns else CENTER)

    def setup_context_menus(self):
        """提供一致的複製、貼上與表格欄位複製操作。"""
        self.table_selection_vars = {}
        self._context_tree = None
        self._context_cell_value = ""
        self._context_input = None

        self.tree_context_menu = tk.Menu(self.root, tearoff=0)
        self.tree_context_menu.add_command(label="複製此欄位", command=self.copy_selected_tree_cell)
        self.tree_context_menu.add_command(label="複製整列", command=self.copy_selected_tree_row)

        self.input_context_menu = tk.Menu(self.root, tearoff=0)
        self.input_context_menu.add_command(label="剪下", command=lambda: self.send_input_virtual_event("<<Cut>>"))
        self.input_context_menu.add_command(label="複製", command=lambda: self.send_input_virtual_event("<<Copy>>"))
        self.input_context_menu.add_command(label="貼上", command=lambda: self.send_input_virtual_event("<<Paste>>"))
        self.input_context_menu.add_separator()
        self.input_context_menu.add_command(label="全選", command=self.select_all_input_text)
        self.root.bind_all("<Button-3>", self.show_input_context_menu, add="+")

    def is_text_input_widget(self, widget):
        return widget.winfo_class() in {"Entry", "TEntry", "TCombobox", "Text"}

    def show_input_context_menu(self, event):
        if not self.is_text_input_widget(event.widget):
            return None
        self._context_input = event.widget
        try:
            self.input_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.input_context_menu.grab_release()
        return "break"

    def send_input_virtual_event(self, event_name):
        if self._context_input:
            self._context_input.event_generate(event_name)

    def select_all_input_text(self):
        if not self._context_input:
            return
        if self._context_input.winfo_class() == "Text":
            self._context_input.tag_add("sel", "1.0", "end-1c")
        else:
            self._context_input.selection_range(0, END)
            self._context_input.icursor(END)

    def copy_to_clipboard(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(value))
        self.root.update()

    def add_table_interactions(self, tree, info_parent):
        """讓每張表格能點選欄位、在底部確認內容並以右鍵複製。"""
        selected_text = tk.StringVar(value="點選表格欄位後，可在此選取文字或按右鍵複製。")
        self.table_selection_vars[tree] = selected_text

        selection_bar = tb.Frame(info_parent, bootstyle="light")
        selection_bar.pack(side="bottom", fill=X, pady=(7, 0))
        tb.Label(selection_bar, text="選取內容:", bootstyle="secondary").pack(side=LEFT, padx=(2, 7))
        display = tb.Entry(selection_bar, textvariable=selected_text, state="readonly")
        display.pack(side=LEFT, fill=X, expand=True)

        tree.bind("<Button-3>", lambda event, source=tree: self.show_tree_context_menu(event, source), add="+")
        tree.bind("<ButtonRelease-1>", lambda event, source=tree: self.update_tree_selection_display(event, source), add="+")
        tree.bind("<<TreeviewSelect>>", lambda _event, source=tree: self.update_tree_selection_from_row(source), add="+")

    def tree_cell_details(self, tree, row_id, column_id):
        if not row_id or not column_id:
            return "", ""
        try:
            column_index = int(column_id.replace("#", "")) - 1
            values = tree.item(row_id, "values")
            columns = tree.cget("columns")
            column_name = columns[column_index]
            heading = tree.heading(column_name, "text")
            return heading, values[column_index]
        except (IndexError, ValueError, tk.TclError):
            return "", ""

    def update_tree_selection_display(self, event, tree):
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if row_id:
            tree.selection_set(row_id)
            tree.focus(row_id)
        heading, value = self.tree_cell_details(tree, row_id, column_id)
        if heading and tree in self.table_selection_vars:
            self.table_selection_vars[tree].set(f"{heading}: {value}")

    def update_tree_selection_from_row(self, tree):
        row_id = tree.focus()
        if not row_id or tree not in self.table_selection_vars:
            return
        values = tree.item(row_id, "values")
        columns = tree.cget("columns")
        if values and columns:
            self.table_selection_vars[tree].set(f"{tree.heading(columns[0], 'text')}: {values[0]}")

    def show_tree_context_menu(self, event, tree):
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not row_id:
            return None
        tree.selection_set(row_id)
        tree.focus(row_id)
        heading, value = self.tree_cell_details(tree, row_id, column_id)
        self._context_tree = tree
        self._context_cell_value = value
        if heading and tree in self.table_selection_vars:
            self.table_selection_vars[tree].set(f"{heading}: {value}")
        try:
            self.tree_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_context_menu.grab_release()
        return "break"

    def copy_selected_tree_cell(self):
        self.copy_to_clipboard(self._context_cell_value)

    def copy_selected_tree_row(self):
        if not self._context_tree:
            return
        row_id = self._context_tree.focus()
        if row_id:
            self.copy_to_clipboard("\t".join(str(value) for value in self._context_tree.item(row_id, "values")))

    def build_product_info_panel(self, parent, title="商品確認"):
        """作業畫面用的小型商品資訊表，避免只靠單行狀態文字確認。"""
        panel = tb.Labelframe(parent, text=title, bootstyle="info", padding=8)
        panel.pack(fill=X, pady=(0, 10))
        holder = tb.Frame(panel)
        columns = ("barcode", "sku", "name", "category", "expiry", "safety", "available", "shelf_qty")
        tree = tb.Treeview(holder, columns=columns, show="headings", height=2, bootstyle="info")
        headings = ("條碼", "SKU", "商品名稱", "分類", "保存期限", "安全庫存", "可用庫存", "查詢儲位庫存")
        widths = (150, 110, 220, 120, 100, 100, 100, 130)
        self.setup_tree_columns(tree, columns, headings, widths, left_columns=("name",))
        self.add_table_interactions(tree, panel)
        holder.pack(fill=X)
        self.add_tree_scrollbar(holder, tree)
        return tree

    def refresh_product_info_panel(self, tree, barcode_text, shelf_code=""):
        self.clear_tree(tree)
        barcode = Utils.normalize_barcode(barcode_text)
        if not barcode or not Utils.valid_barcode(barcode):
            return
        product = self.db.product_by_barcode(barcode)
        if not product:
            tree.insert("", END, values=(barcode, "-", "查無商品主檔", "-", "-", "-", "-", "-"), tags=("warning",))
            return
        stock = self.db.cursor.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN s.zone NOT IN ('Staging', 'QC', 'Scrap', 'Outbound')
                                     THEN i.quantity ELSE 0 END), 0) AS available_qty
            FROM inventory i JOIN shelves s ON s.shelf_code=i.shelf_code
            WHERE i.barcode=?
            """,
            (barcode,),
        ).fetchone()["available_qty"]
        shelf_code = shelf_code.strip().upper()
        shelf_qty = "-"
        if shelf_code:
            shelf_qty = self.db.cursor.execute(
                "SELECT COALESCE(SUM(quantity), 0) AS qty FROM inventory WHERE barcode=? AND shelf_code=?",
                (barcode, shelf_code),
            ).fetchone()["qty"]
        tree.insert(
            "",
            END,
            values=(
                product["barcode"],
                product["sku"],
                product["name"],
                product["category"] or "-",
                "需要" if product["expiry_required"] else "不需要",
                product["safety_stock"],
                stock,
                shelf_qty,
            ),
        )

    def show_view(self, mode):
        for frame in self.views.values():
            frame.pack_forget()
        self.views[mode].pack(fill=BOTH, expand=True)

        for item_mode, button in self.menu_buttons.items():
            button.configure(bootstyle="primary" if item_mode == mode else "dark-outline")

        refreshers = {
            "dashboard": self.refresh_dashboard,
            "products": self.refresh_products,
            "branches": self.refresh_branches,
            "shelves": self.refresh_shelf_view,
            "inventory": self.refresh_inventory,
            "receiving": self.refresh_receiving_view,
            "returns": self.refresh_returns_view,
            "putaway": self.refresh_putaway_view,
            "orders": self.refresh_orders_view,
            "history": self.refresh_history,
        }
        if mode in refreshers:
            refreshers[mode]()

        focus_widgets = {
            "receiving": self.recv_order_no,
            "returns": self.return_receiving_order_no,
            "putaway": self.put_barcode,
            "shipping": self.pack_order_no,
            "counting": self.cnt_shelf,
        }
        if mode in focus_widgets:
            self.root.after(80, focus_widgets[mode].focus_set)

    # ---------- 商品主檔 ----------

    def build_product_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "商品主檔", "新增、修改條碼、SKU、名稱、安全庫存與效期設定")

        form = tb.Labelframe(frame, text="商品資料", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 12))

        self.prod_barcode = tb.Entry(form, width=24)
        self.prod_sku = tb.Entry(form, width=18)
        self.prod_name = tb.Entry(form, width=28)
        self.prod_category = tb.Combobox(form, width=16, state="readonly", values=PRODUCT_CATEGORIES)
        self.prod_category.set(PRODUCT_CATEGORIES[-1])
        self.prod_safety = tb.Entry(form, width=10)
        self.prod_expiry_required = tk.BooleanVar(value=True)

        fields = [
            ("商品條碼", self.prod_barcode, 0, 0),
            ("SKU", self.prod_sku, 0, 2),
            ("商品名稱", self.prod_name, 0, 4),
            ("分類", self.prod_category, 1, 0),
            ("安全庫存", self.prod_safety, 1, 2),
        ]
        for text, widget, row, column in fields:
            tb.Label(form, text=f"{text}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=8)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 18), pady=8)

        tb.Checkbutton(
            form,
            text="有效期商品（開啟才會要求輸入效期／建立 LOT）",
            variable=self.prod_expiry_required,
            bootstyle="primary-round-toggle",
        ).grid(row=1, column=4, columnspan=2, sticky=W, padx=4)
        tb.Button(form, text="儲存商品", bootstyle="primary", command=self.save_product_from_form).grid(
            row=0, column=6, padx=(12, 6), pady=8
        )
        tb.Button(form, text="清除欄位", bootstyle="secondary", command=self.clear_product_form).grid(
            row=1, column=6, padx=(12, 6), pady=8
        )
        self.prod_barcode.bind("<FocusOut>", self.check_product_barcode_duplicate)
        self.prod_barcode_hint = tb.Label(form, text="", bootstyle="danger")
        self.prod_barcode_hint.grid(row=2, column=0, columnspan=4, sticky=W, padx=4)

        filter_bar = tb.Frame(frame)
        filter_bar.pack(fill=X, pady=(0, 8))
        self.prod_filter_category = tb.Combobox(filter_bar, width=14, state="readonly", values=("全部類別",) + PRODUCT_CATEGORIES)
        self.prod_filter_category.set("全部類別")
        self.prod_filter_keyword = tb.Entry(filter_bar, width=28)
        tb.Label(filter_bar, text="分類篩選:").pack(side=LEFT, padx=(4, 6))
        self.prod_filter_category.pack(side=LEFT, padx=(0, 16))
        tb.Label(filter_bar, text="搜尋（條碼／SKU／名稱）:").pack(side=LEFT, padx=(4, 6))
        self.prod_filter_keyword.pack(side=LEFT, padx=(0, 8))
        tb.Button(filter_bar, text="查詢", bootstyle="secondary", command=self.refresh_products).pack(side=LEFT, padx=4)
        tb.Button(filter_bar, text="顯示全部", bootstyle="outline-secondary", command=self.clear_product_filter).pack(side=LEFT, padx=4)
        self.prod_filter_category.bind("<<ComboboxSelected>>", lambda _event: self.refresh_products())
        self.prod_filter_keyword.bind("<Return>", lambda _event: self.refresh_products())

        columns = ("barcode", "sku", "name", "category", "safety", "expiry")
        self.product_tree = tb.Treeview(frame, columns=columns, show="headings", height=18, bootstyle="primary")
        headings = ("商品條碼", "SKU", "商品名稱", "分類", "安全庫存", "保存期限")
        widths = (180, 130, 260, 140, 110, 110)
        self.setup_tree_columns(self.product_tree, columns, headings, widths, left_columns=("name",))
        self.product_tree.bind("<<TreeviewSelect>>", self.on_product_select)
        self.add_table_interactions(self.product_tree, frame)
        self.add_tree_scrollbar(frame, self.product_tree)
        return frame

    def clear_product_form(self):
        self.product_selected_barcode = None
        for widget in (self.prod_barcode, self.prod_sku, self.prod_name, self.prod_safety):
            widget.delete(0, END)
        self.prod_category.set(PRODUCT_CATEGORIES[-1])
        self.prod_expiry_required.set(True)
        self.prod_barcode_hint.configure(text="")
        self.prod_barcode.focus_set()

    def check_product_barcode_duplicate(self, _event=None):
        """V6.3：新增商品時即時提示條碼是否已被使用，避免存檔時才發現重複。"""
        barcode = Utils.normalize_barcode(self.prod_barcode.get())
        if not Utils.valid_barcode(barcode):
            self.prod_barcode_hint.configure(text="")
            return
        existing = self.db.product_by_barcode(barcode)
        if existing and barcode != self.product_selected_barcode:
            self.prod_barcode_hint.configure(text=f"⚠ 此條碼已被商品「{existing['name']}」（SKU:{existing['sku']}）使用，不可重複建立")
        else:
            self.prod_barcode_hint.configure(text="")

    def on_product_select(self, _event=None):
        selected = self.product_tree.focus()
        if not selected:
            return
        barcode = self.product_tree.item(selected, "values")[0]
        product = self.db.product_by_barcode(barcode)
        if not product:
            return
        self.product_selected_barcode = barcode
        values = {
            self.prod_barcode: product["barcode"],
            self.prod_sku: product["sku"],
            self.prod_name: product["name"],
            self.prod_safety: str(product["safety_stock"]),
        }
        for widget, value in values.items():
            widget.delete(0, END)
            widget.insert(0, value)
        self.prod_category.set(product["category"] if product["category"] in PRODUCT_CATEGORIES else PRODUCT_CATEGORIES[-1])
        self.prod_expiry_required.set(bool(product["expiry_required"]))
        self.prod_barcode_hint.configure(text="")

    def save_product_from_form(self):
        try:
            barcode = Utils.normalize_barcode(self.prod_barcode.get())
            sku = self.prod_sku.get().strip()
            name = self.prod_name.get().strip()
            category = self.prod_category.get().strip() or PRODUCT_CATEGORIES[-1]
            safety_text = self.prod_safety.get().strip()
            if not Utils.valid_barcode(barcode):
                raise ValueError("條碼只能使用英文字母、數字與連字號，長度 3 至 64 碼")
            if not sku or not name:
                raise ValueError("SKU 與商品名稱為必填")
            if not safety_text.isdigit() or int(safety_text) > 1000000:
                raise ValueError("安全庫存請輸入 0 至 1,000,000 的整數")
            is_new = self.product_selected_barcode is None
            self.db.save_product(
                self.product_selected_barcode,
                barcode,
                sku,
                name,
                category,
                int(safety_text),
                self.prod_expiry_required.get(),
            )
            self.db.log_operation(
                self.current_user,
                "新增商品" if is_new else "修改商品",
                barcode,
                f"{name}（SKU:{sku}）",
            )
            self.refresh_products()
            self.clear_product_form()
            messagebox.showinfo("完成", f"商品「{name}」已儲存")
        except (ValueError, sqlite3.IntegrityError) as error:
            messagebox.showerror("無法儲存商品", str(error))

    def clear_product_filter(self):
        self.prod_filter_category.set("全部類別")
        self.prod_filter_keyword.delete(0, END)
        self.refresh_products()

    def refresh_products(self):
        self.clear_tree(self.product_tree)
        category_filter = self.prod_filter_category.get().strip() if hasattr(self, "prod_filter_category") else "全部類別"
        keyword = self.prod_filter_keyword.get().strip().lower() if hasattr(self, "prod_filter_keyword") else ""
        for product in self.db.all_products():
            if category_filter and category_filter != "全部類別" and (product["category"] or "") != category_filter:
                continue
            if keyword and keyword not in product["barcode"].lower() and keyword not in product["sku"].lower() and keyword not in product["name"].lower():
                continue
            self.product_tree.insert(
                "",
                END,
                values=(
                    product["barcode"],
                    product["sku"],
                    product["name"],
                    product["category"] or "-",
                    product["safety_stock"],
                    "需要" if product["expiry_required"] else "不需要",
                ),
            )
        self.refresh_product_choices()

    def open_new_product_dialog(self, initial_barcode, after_save=None):
        dialog = tb.Toplevel(self.root)
        dialog.title("建立新商品")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x360")

        body = tb.Frame(dialog, padding=22)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text="查無商品主檔", font=("Microsoft JhengHei", 16, "bold"), bootstyle="warning").pack(anchor=W)
        tb.Label(body, text="請建立商品後，系統會接續原本的進貨資料。", bootstyle="secondary").pack(anchor=W, pady=(2, 16))

        barcode_entry = tb.Entry(body, width=28)
        sku_entry = tb.Entry(body, width=28)
        name_entry = tb.Entry(body, width=28)
        category_entry = tb.Entry(body, width=28)
        safety_entry = tb.Entry(body, width=28)
        expiry_var = tk.BooleanVar(value=True)
        barcode_entry.insert(0, initial_barcode)
        safety_entry.insert(0, "0")
        widgets = [
            ("商品條碼", barcode_entry),
            ("SKU", sku_entry),
            ("商品名稱", name_entry),
            ("分類", category_entry),
            ("安全庫存", safety_entry),
        ]
        for row, (label, widget) in enumerate(widgets):
            tb.Label(body, text=f"{label}:").grid(row=row + 2, column=0, sticky=W, pady=6)
            widget.grid(row=row + 2, column=1, sticky=W, pady=6, padx=(12, 0))
        tb.Checkbutton(
            body,
            text="需要保存期限",
            variable=expiry_var,
            bootstyle="primary-round-toggle",
        ).grid(row=7, column=1, sticky=W, pady=8)

        def save_and_continue():
            try:
                barcode = Utils.normalize_barcode(barcode_entry.get())
                safety = safety_entry.get().strip()
                if not Utils.valid_barcode(barcode):
                    raise ValueError("條碼格式不正確")
                if not sku_entry.get().strip() or not name_entry.get().strip():
                    raise ValueError("SKU 與商品名稱為必填")
                if not safety.isdigit():
                    raise ValueError("安全庫存必須是整數")
                self.db.save_product(
                    None,
                    barcode,
                    sku_entry.get().strip(),
                    name_entry.get().strip(),
                    category_entry.get().strip(),
                    int(safety),
                    expiry_var.get(),
                )
                self.db.log_operation(
                    self.current_user, "新增商品", barcode,
                    f"{name_entry.get().strip()}（SKU:{sku_entry.get().strip()}）",
                )
                self.refresh_products()
                dialog.destroy()
                if after_save:
                    after_save()
            except (ValueError, sqlite3.IntegrityError) as error:
                messagebox.showerror("無法建立商品", str(error), parent=dialog)

        button_bar = tb.Frame(body)
        button_bar.grid(row=8, column=0, columnspan=2, sticky=EW, pady=(12, 0))
        tb.Button(button_bar, text="建立並繼續進貨", bootstyle="primary", command=save_and_continue).pack(side=LEFT)
        tb.Button(button_bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=LEFT, padx=8)
        name_entry.focus_set()

    # ---------- 分店管理 ----------

    def build_branch_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "分店管理", "維護分店名稱、地址、聯絡人與預設物流方式")

        form = tb.Labelframe(frame, text="分店資料", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 12))
        self.branch_code = tb.Entry(form, width=16)
        self.branch_name = tb.Entry(form, width=24)
        self.branch_address = tb.Entry(form, width=44)
        self.branch_contact = tb.Entry(form, width=16)
        self.branch_phone = tb.Entry(form, width=18)
        self.branch_carrier = tb.Combobox(form, values=CARRIERS, width=16, state="readonly")
        self.branch_carrier.set("未指定")

        fields = [
            ("分店代碼", self.branch_code, 0, 0),
            ("分店名稱", self.branch_name, 0, 2),
            ("地址", self.branch_address, 1, 0),
            ("聯絡人", self.branch_contact, 2, 0),
            ("電話", self.branch_phone, 2, 2),
            ("預設物流", self.branch_carrier, 2, 4),
        ]
        for text, widget, row, column in fields:
            tb.Label(form, text=f"{text}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=7)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 18), pady=7)

        tb.Button(form, text="儲存分店", bootstyle="primary", command=self.save_branch_from_form).grid(
            row=0, column=4, padx=8, pady=7
        )
        tb.Button(form, text="清除欄位", bootstyle="secondary", command=self.clear_branch_form).grid(
            row=1, column=4, padx=8, pady=7
        )

        columns = ("code", "name", "address", "contact", "phone", "carrier")
        self.branch_tree = tb.Treeview(frame, columns=columns, show="headings", height=18, bootstyle="primary")
        headings = ("分店代碼", "分店名稱", "地址", "聯絡人", "電話", "預設物流")
        widths = (120, 180, 380, 120, 150, 150)
        self.setup_tree_columns(self.branch_tree, columns, headings, widths, left_columns=("name", "address"))
        self.branch_tree.bind("<<TreeviewSelect>>", self.on_branch_select)
        self.add_table_interactions(self.branch_tree, frame)
        self.add_tree_scrollbar(frame, self.branch_tree)
        return frame

    def clear_branch_form(self):
        self.branch_selected_id = None
        for widget in (
            self.branch_code,
            self.branch_name,
            self.branch_address,
            self.branch_contact,
            self.branch_phone,
        ):
            widget.delete(0, END)
        self.branch_carrier.set("未指定")
        self.branch_code.focus_set()

    def on_branch_select(self, _event=None):
        selected = self.branch_tree.focus()
        if not selected:
            return
        values = self.branch_tree.item(selected, "values")
        code = values[0]
        row = self.db.cursor.execute("SELECT * FROM branches WHERE code=?", (code,)).fetchone()
        if not row:
            return
        self.branch_selected_id = row["id"]
        mapping = {
            self.branch_code: row["code"],
            self.branch_name: row["name"],
            self.branch_address: row["address"] or "",
            self.branch_contact: row["contact_name"] or "",
            self.branch_phone: row["contact_phone"] or "",
        }
        for widget, value in mapping.items():
            widget.delete(0, END)
            widget.insert(0, value)
        self.branch_carrier.set(row["default_carrier"] or "未指定")

    def save_branch_from_form(self):
        try:
            code = self.branch_code.get().strip().upper()
            name = self.branch_name.get().strip()
            if not re.fullmatch(r"[A-Z0-9-]{2,20}", code):
                raise ValueError("分店代碼限英文、數字與連字號，長度 2 至 20 碼")
            if not name:
                raise ValueError("分店名稱為必填")
            self.db.save_branch(
                self.branch_selected_id,
                code,
                name,
                self.branch_address.get().strip(),
                self.branch_contact.get().strip(),
                self.branch_phone.get().strip(),
                self.branch_carrier.get() or "未指定",
            )
            self.refresh_branches()
            self.clear_branch_form()
            messagebox.showinfo("完成", f"分店「{name}」已儲存")
        except (ValueError, sqlite3.IntegrityError) as error:
            messagebox.showerror("無法儲存分店", str(error))

    def refresh_branches(self):
        self.clear_tree(self.branch_tree)
        rows = self.db.cursor.execute("SELECT * FROM branches WHERE active=1 ORDER BY code").fetchall()
        for row in rows:
            self.branch_tree.insert(
                "",
                END,
                values=(
                    row["code"],
                    row["name"],
                    row["address"] or "-",
                    row["contact_name"] or "-",
                    row["contact_phone"] or "-",
                    row["default_carrier"],
                ),
            )
        self.refresh_branch_choices()

    # ---------- V6.4：儲位管理（區域-貨架-層位） ----------

    def build_shelf_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "儲位管理", "階層式儲位格式：區域-貨架-層位，例如 A01-03 = A區 01號貨架 第3層")

        form = tb.Labelframe(frame, text="新增／修改儲位", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 12))
        self.shelf_area = tb.Entry(form, width=6)
        self.shelf_rack = tb.Entry(form, width=6)
        self.shelf_level = tb.Entry(form, width=6)
        self.shelf_note = tb.Entry(form, width=30)
        fields = [
            ("區域（單一英文字母，如 A）", self.shelf_area, 0, 0),
            ("貨架（數字，如 1）", self.shelf_rack, 0, 2),
            ("層位（數字，如 3）", self.shelf_level, 0, 4),
            ("備註", self.shelf_note, 0, 6),
        ]
        for text, widget, row, column in fields:
            tb.Label(form, text=f"{text}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=7)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 16), pady=7)
        self.shelf_preview = tb.Label(form, text="儲位代碼預覽：-", bootstyle="secondary")
        self.shelf_preview.grid(row=1, column=0, columnspan=4, sticky=W, padx=4, pady=(0, 6))
        for widget in (self.shelf_area, self.shelf_rack, self.shelf_level):
            widget.bind("<KeyRelease>", self.update_shelf_code_preview)
        tb.Button(form, text="新增儲位", bootstyle="primary", command=self.create_shelf_from_form).grid(row=0, column=8, padx=8, pady=7)
        tb.Button(form, text="儲存修改", bootstyle="warning", command=self.rename_shelf_from_form).grid(row=1, column=6, padx=8, pady=(0, 6))
        tb.Button(form, text="清除欄位", bootstyle="secondary", command=self.clear_shelf_form).grid(row=1, column=7, padx=8, pady=(0, 6))
        self.shelf_form_status = tb.Label(frame, text="點選下方清單可帶入修改；特殊區（未上架／品檢區／報廢區／出貨暫存）不可編輯。", bootstyle="secondary")
        self.shelf_form_status.pack(anchor=W, pady=(0, 10))

        search = tb.Labelframe(frame, text="儲位搜尋", bootstyle="secondary", padding=10)
        search.pack(fill=X, pady=(0, 10))
        self.shelf_search_keyword = tb.Entry(search, width=22)
        self.shelf_search_status = tb.Combobox(search, values=("全部", "啟用", "停用"), width=10, state="readonly")
        self.shelf_search_status.set("全部")
        self.shelf_search_sort = tb.Combobox(search, values=("依儲位代碼", "依建立時間", "依庫存量"), width=12, state="readonly")
        self.shelf_search_sort.set("依儲位代碼")
        tb.Label(search, text="關鍵字（代碼／備註）:").pack(side=LEFT, padx=(4, 6))
        self.shelf_search_keyword.pack(side=LEFT, padx=(0, 14))
        tb.Label(search, text="狀態:").pack(side=LEFT, padx=(4, 6))
        self.shelf_search_status.pack(side=LEFT, padx=(0, 14))
        tb.Label(search, text="排序:").pack(side=LEFT, padx=(4, 6))
        self.shelf_search_sort.pack(side=LEFT, padx=(0, 14))
        tb.Button(search, text="查詢", bootstyle="secondary", command=self.refresh_shelf_view).pack(side=LEFT, padx=4)
        tb.Button(search, text="顯示全部", bootstyle="outline-secondary", command=self.clear_shelf_search).pack(side=LEFT, padx=4)
        self.shelf_search_keyword.bind("<Return>", lambda _event: self.refresh_shelf_view())
        self.shelf_search_status.bind("<<ComboboxSelected>>", lambda _event: self.refresh_shelf_view())
        self.shelf_search_sort.bind("<<ComboboxSelected>>", lambda _event: self.refresh_shelf_view())

        action = tb.Frame(frame)
        action.pack(fill=X, pady=(0, 8))
        tb.Button(action, text="停用選取儲位", bootstyle="danger", command=lambda: self.set_selected_shelf_status("停用")).pack(side=LEFT)
        tb.Button(action, text="啟用選取儲位", bootstyle="success", command=lambda: self.set_selected_shelf_status("啟用")).pack(side=LEFT, padx=8)

        columns = ("code", "area", "rack", "level", "status", "stock", "note", "created")
        self.shelf_tree = tb.Treeview(frame, columns=columns, show="headings", height=14, bootstyle="primary")
        headings = ("儲位代碼", "區域", "貨架", "層位", "狀態", "庫存量", "備註", "建立時間")
        widths = (110, 60, 60, 60, 70, 80, 220, 150)
        self.setup_tree_columns(self.shelf_tree, columns, headings, widths, left_columns=("note",))
        self.shelf_tree.tag_configure("disabled", background="#FDE2E1")
        self.shelf_tree.tag_configure("special", background="#EAF0FF")
        self.shelf_tree.bind("<<TreeviewSelect>>", self.on_shelf_select)
        self.add_table_interactions(self.shelf_tree, frame)
        self.add_tree_scrollbar(frame, self.shelf_tree)
        return frame

    def update_shelf_code_preview(self, _event=None):
        area = self.shelf_area.get().strip().upper()
        rack = self.shelf_rack.get().strip()
        level = self.shelf_level.get().strip()
        if re.fullmatch(r"[A-Z]", area) and rack.isdigit() and level.isdigit():
            self.shelf_preview.configure(text=f"儲位代碼預覽：{area}{int(rack):02d}-{int(level):02d}")
        else:
            self.shelf_preview.configure(text="儲位代碼預覽：-")

    def clear_shelf_form(self):
        self.shelf_selected_code = None
        for widget in (self.shelf_area, self.shelf_rack, self.shelf_level, self.shelf_note):
            widget.delete(0, END)
        self.shelf_preview.configure(text="儲位代碼預覽：-")
        self.set_status(self.shelf_form_status, "點選下方清單可帶入修改；特殊區不可編輯。", "secondary")
        self.shelf_area.focus_set()

    def clear_shelf_search(self):
        self.shelf_search_keyword.delete(0, END)
        self.shelf_search_status.set("全部")
        self.shelf_search_sort.set("依儲位代碼")
        self.refresh_shelf_view()

    def create_shelf_from_form(self):
        try:
            shelf_code = self.db.create_shelf(
                self.shelf_area.get(), self.shelf_rack.get(), self.shelf_level.get(), self.shelf_note.get()
            )
            self.db.log_operation(self.current_user, "新增儲位", shelf_code)
            self.clear_shelf_form()
            self.refresh_shelf_view()
            self.set_status(self.shelf_form_status, f"已新增儲位 {shelf_code}", "success")
        except ValueError as error:
            self.set_status(self.shelf_form_status, str(error), "danger")

    def on_shelf_select(self, _event=None):
        selected = self.shelf_tree.focus()
        if not selected:
            return
        values = self.shelf_tree.item(selected, "values")
        shelf_code = values[0]
        shelf = self.db.shelf_by_code(shelf_code)
        if not shelf or shelf["is_special"]:
            self.shelf_selected_code = None
            for widget in (self.shelf_area, self.shelf_rack, self.shelf_level, self.shelf_note):
                widget.delete(0, END)
            self.shelf_preview.configure(text="儲位代碼預覽：-")
            self.set_status(self.shelf_form_status, "此為特殊區，不可編輯", "warning")
            return
        self.shelf_selected_code = shelf_code
        self.shelf_area.delete(0, END); self.shelf_area.insert(0, shelf["area"])
        self.shelf_rack.delete(0, END); self.shelf_rack.insert(0, str(int(shelf["rack"])))
        self.shelf_level.delete(0, END); self.shelf_level.insert(0, str(int(shelf["level"])))
        self.shelf_note.delete(0, END); self.shelf_note.insert(0, shelf["note"] or "")
        self.update_shelf_code_preview()
        self.set_status(self.shelf_form_status, f"正在修改 {shelf_code}，儲存後將套用新代碼／備註", "info")

    def rename_shelf_from_form(self):
        if not getattr(self, "shelf_selected_code", None):
            return self.set_status(self.shelf_form_status, "請先在下方清單點選要修改的儲位", "warning")
        old_code = self.shelf_selected_code
        area = self.shelf_area.get().strip().upper()
        rack, level = self.shelf_rack.get().strip(), self.shelf_level.get().strip()
        try:
            rack_no, level_no = int(rack), int(level)
            new_code = f"{area}{rack_no:02d}-{level_no:02d}"
        except (TypeError, ValueError):
            return self.set_status(self.shelf_form_status, "貨架與層位請輸入數字", "danger")

        # V6.4 防呆：儲位如仍有庫存或未完成出貨保留，修改前二次確認，避免庫存追蹤錯亂。
        summary = self.db.shelf_reference_summary(old_code)
        if new_code != old_code and (summary["stock_qty"] > 0 or summary["pending_orders"] > 0):
            if not messagebox.askyesno(
                "修改儲位確認",
                f"此儲位目前存在庫存或未完成單據（庫存 {summary['stock_qty']} 件、"
                f"未完成出貨保留 {summary['pending_orders']} 張），修改可能影響庫存追蹤，是否確認修改？",
            ):
                return self.set_status(self.shelf_form_status, "已取消修改", "secondary")
        try:
            new_code = self.db.rename_shelf(old_code, area, rack, level, self.shelf_note.get())
            self.db.log_operation(self.current_user, "修改儲位", new_code, f"原代碼：{old_code}")
            self.shelf_selected_code = None
            self.clear_shelf_form()
            self.refresh_shelf_view()
            self.set_status(self.shelf_form_status, f"已將 {old_code} 更新為 {new_code}", "success")
        except ValueError as error:
            self.set_status(self.shelf_form_status, str(error), "danger")

    def set_selected_shelf_status(self, status):
        selected = self.shelf_tree.focus()
        if not selected:
            return self.set_status(self.shelf_form_status, "請先選取儲位", "warning")
        shelf_code = self.shelf_tree.item(selected, "values")[0]
        shelf = self.db.shelf_by_code(shelf_code)
        if not shelf or shelf["is_special"]:
            return self.set_status(self.shelf_form_status, "特殊區不可停用／啟用", "danger")
        if status == "停用":
            summary = self.db.shelf_reference_summary(shelf_code)
            if summary["stock_qty"] > 0 or summary["pending_orders"] > 0:
                confirmed = messagebox.askyesno(
                    "停用儲位確認",
                    f"此儲位目前存在庫存或未完成單據（庫存 {summary['stock_qty']} 件、"
                    f"未完成出貨保留 {summary['pending_orders']} 張），修改可能影響庫存追蹤，是否確認修改？",
                )
            else:
                confirmed = messagebox.askyesno("停用儲位確認", f"確定要停用儲位 {shelf_code} 嗎？")
            if not confirmed:
                return self.set_status(self.shelf_form_status, "已取消", "secondary")
        try:
            self.db.set_shelf_status(shelf_code, status)
            self.db.log_operation(self.current_user, f"{status}儲位", shelf_code)
            self.refresh_shelf_view()
            self.set_status(self.shelf_form_status, f"儲位 {shelf_code} 已{status}", "success")
        except ValueError as error:
            self.set_status(self.shelf_form_status, str(error), "danger")

    def refresh_shelf_view(self):
        self.clear_tree(self.shelf_tree)
        sort_map = {"依儲位代碼": "code", "依建立時間": "created", "依庫存量": "stock"}
        rows = self.db.search_shelves(
            self.shelf_search_keyword.get(),
            self.shelf_search_status.get(),
            sort_map.get(self.shelf_search_sort.get(), "code"),
        )
        for row in rows:
            if row["is_special"]:
                tag, area, rack, level = "special", "-", "-", "-"
            else:
                tag = "disabled" if row["status"] == "停用" else ""
                area, rack, level = row["area"], row["rack"], row["level"]
            self.shelf_tree.insert(
                "", END,
                values=(row["shelf_code"], area, rack, level, row["status"], row["stock_qty"], row["note"] or "-", row["created_at"] or "-"),
                tags=(tag,) if tag else (),
            )
        # 同步更新上架／盤點頁的儲位下拉選單，僅列出啟用中的儲位。
        if hasattr(self, "put_shelf"):
            self.put_shelf.configure(values=self.db.active_shelf_codes(include_special=False))
        if hasattr(self, "cnt_shelf"):
            self.cnt_shelf.configure(values=self.db.active_shelf_codes(include_special=True))

    # ---------- 庫存總覽 ----------

    def build_dashboard_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "營運總覽", "即時掌握庫存、低庫存與即期品狀態")

        body = tb.Frame(frame, bootstyle="light")
        body.pack(fill=BOTH, expand=True)
        body.columnconfigure(0, weight=0, minsize=260)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        card_col = tb.Frame(body, bootstyle="light")
        card_col.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        card_col.columnconfigure(0, weight=1)

        self.dashboard_cards = {}
        card_config = [
            ("商品主檔", "primary"),
            ("可用庫存", "success"),
            ("低庫存警示", "danger"),
            ("即期品批次", "warning"),
            ("待處理出貨單", "info"),
        ]
        for index, (title, style) in enumerate(card_config):
            card_col.rowconfigure(index, weight=1)
            card = tb.Frame(card_col, bootstyle=style, padding=18)
            card.grid(row=index, column=0, sticky="nsew", pady=(0 if index == 0 else 3, 0))
            tb.Label(card, text=title, font=("Microsoft JhengHei", 12), bootstyle=f"inverse-{style}").pack(anchor=W)
            value = tb.Label(card, text="0", font=("Arial", 30, "bold"), bootstyle=f"inverse-{style}")
            value.pack(anchor=W, pady=(10, 0))
            self.dashboard_cards[title] = value

        alert_frame = tb.Labelframe(body, text="需要注意的商品", bootstyle="warning", padding=10)
        alert_frame.grid(row=0, column=1, sticky="nsew")
        columns = ("type", "barcode", "name", "available", "safety", "detail")
        self.dashboard_alert_tree = tb.Treeview(alert_frame, columns=columns, show="headings", height=18, bootstyle="warning")
        headings = ("類型", "條碼", "商品", "可用庫存", "安全庫存", "說明")
        widths = (120, 160, 260, 120, 120, 440)
        self.setup_tree_columns(self.dashboard_alert_tree, columns, headings, widths, left_columns=("name", "detail"))
        self.add_table_interactions(self.dashboard_alert_tree, alert_frame)
        self.add_tree_scrollbar(alert_frame, self.dashboard_alert_tree)
        return frame

    def refresh_dashboard(self):
        self.clear_tree(self.dashboard_alert_tree)
        product_rows = self.db.cursor.execute(
            """
            SELECT p.barcode, p.name, p.safety_stock,
                   COALESCE(SUM(CASE WHEN s.zone NOT IN ('Staging', 'QC', 'Scrap', 'Outbound')
                                     THEN i.quantity ELSE 0 END), 0) AS available_qty
            FROM products p
            LEFT JOIN inventory i ON i.barcode=p.barcode
            LEFT JOIN shelves s ON s.shelf_code=i.shelf_code
            GROUP BY p.barcode
            ORDER BY p.name
            """
        ).fetchall()
        total_available = sum(row["available_qty"] for row in product_rows)
        low_stock_rows = [
            row
            for row in product_rows
            if row["safety_stock"] > 0 and row["available_qty"] <= row["safety_stock"]
        ]
        for row in low_stock_rows:
            self.dashboard_alert_tree.insert(
                "",
                END,
                values=(
                    "低庫存",
                    row["barcode"],
                    row["name"],
                    row["available_qty"],
                    row["safety_stock"],
                    "可用庫存已低於或等於安全庫存",
                ),
                tags=("danger",),
            )

        near_expiry_rows = self.db.cursor.execute(
            """
            SELECT i.barcode, p.name, i.shelf_code, i.expiry_date, i.quantity
            FROM inventory i
            JOIN products p ON p.barcode=i.barcode
            WHERE i.expiry_date NOT IN ('', ?)
              AND i.expiry_date <= ?
            ORDER BY i.expiry_date, i.shelf_code
            """,
            (NO_EXPIRY_DATE, (date.today().fromordinal(date.today().toordinal() + 90)).isoformat()),
        ).fetchall()
        for row in near_expiry_rows:
            valid, expired, days = Utils.validate_date(row["expiry_date"])
            detail = "已過期，請移至報廢區" if expired else f"儲位 {row['shelf_code']}，剩餘 {days} 天"
            self.dashboard_alert_tree.insert(
                "",
                END,
                values=(
                    "已過期" if expired else "即期品",
                    row["barcode"],
                    row["name"],
                    row["quantity"],
                    "-",
                    detail,
                ),
                tags=("danger" if expired else "warning",),
            )

        pending_count = self.db.cursor.execute(
            "SELECT COUNT(*) AS count FROM shipping_orders WHERE status IN ('待撿貨', '包裝中')"
        ).fetchone()["count"]
        self.dashboard_cards["商品主檔"].configure(text=str(len(product_rows)))
        self.dashboard_cards["可用庫存"].configure(text=str(total_available))
        self.dashboard_cards["低庫存警示"].configure(text=str(len(low_stock_rows)))
        self.dashboard_cards["即期品批次"].configure(text=str(len(near_expiry_rows)))
        self.dashboard_cards["待處理出貨單"].configure(text=str(pending_count))

    def build_inventory_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "庫存查詢", "輸入儲位可只查看該儲位的商品、數量與保存期限（未上架商品請至「上架作業」查看）")

        filter_card = tb.Labelframe(frame, text="快速查詢", bootstyle="info", padding=12)
        filter_card.pack(fill=X, pady=(0, 12))
        self.inv_shelf_filter = tb.Combobox(filter_card, width=18)
        self.inv_keyword_filter = tb.Entry(filter_card, width=28)
        tb.Label(filter_card, text="儲位:").grid(row=0, column=0, sticky=W, padx=(4, 7), pady=4)
        self.inv_shelf_filter.grid(row=0, column=1, sticky=W, padx=(0, 16), pady=4)
        tb.Label(filter_card, text="商品名稱／條碼:").grid(row=0, column=2, sticky=W, padx=(4, 7), pady=4)
        self.inv_keyword_filter.grid(row=0, column=3, sticky=W, padx=(0, 16), pady=4)
        tb.Button(filter_card, text="查詢", bootstyle="info", command=self.refresh_inventory).grid(row=0, column=4, padx=4)
        tb.Button(filter_card, text="清除", bootstyle="secondary", command=self.clear_inventory_filter).grid(row=0, column=5, padx=4)
        self.inv_shelf_filter.bind("<Return>", lambda _event: self.refresh_inventory())
        self.inv_keyword_filter.bind("<Return>", lambda _event: self.refresh_inventory())
        self.inv_filter_status = tb.Label(frame, text="顯示全部儲位的庫存資料", bootstyle="secondary")
        self.inv_filter_status.pack(anchor=W, pady=(0, 8))

        columns = ("shelf", "barcode", "name", "qty", "available", "expiry", "zone", "status")
        self.inventory_tree = tb.Treeview(frame, columns=columns, show="headings", bootstyle="info")
        headings = ("儲位", "商品條碼", "商品名稱", "儲位數量", "可用總量", "效期", "區域", "狀態")
        widths = (100, 160, 250, 100, 100, 120, 110, 240)
        self.setup_tree_columns(self.inventory_tree, columns, headings, widths, left_columns=("name", "status"))
        self.inventory_tree.tag_configure("danger", background="#FDE2E1")
        self.inventory_tree.tag_configure("warning", background="#FFF1CC")
        self.add_table_interactions(self.inventory_tree, frame)
        self.add_tree_scrollbar(frame, self.inventory_tree)
        return frame

    def clear_inventory_filter(self):
        self.inv_shelf_filter.set("")
        self.inv_keyword_filter.delete(0, END)
        self.refresh_inventory()
        self.inv_shelf_filter.focus_set()

    def refresh_inventory(self):
        self.clear_tree(self.inventory_tree)
        shelf_code = self.inv_shelf_filter.get().strip().upper()
        keyword = self.inv_keyword_filter.get().strip()
        keyword_like = f"%{keyword}%"
        shelf_codes = [row["shelf_code"] for row in self.db.cursor.execute("SELECT shelf_code FROM shelves ORDER BY shelf_code").fetchall()]
        self.inv_shelf_filter.configure(values=shelf_codes)
        if shelf_code and not self.db.shelf_by_code(shelf_code):
            self.set_status(self.inv_filter_status, f"查無儲位 {shelf_code}，請確認輸入內容", "warning")
            return
        rows = self.db.cursor.execute(
            """
            WITH stock AS (
                SELECT i.barcode,
                       SUM(CASE WHEN s.zone NOT IN ('Staging', 'QC', 'Scrap', 'Outbound')
                                THEN i.quantity ELSE 0 END) AS available_qty
                FROM inventory i JOIN shelves s ON s.shelf_code=i.shelf_code
                GROUP BY i.barcode
            )
            SELECT i.shelf_code, i.barcode, p.name, p.safety_stock, p.expiry_required,
                   i.quantity, i.expiry_date, s.zone, COALESCE(stock.available_qty, 0) AS available_qty
            FROM inventory i
            JOIN products p ON p.barcode=i.barcode
            JOIN shelves s ON s.shelf_code=i.shelf_code
            LEFT JOIN stock ON stock.barcode=i.barcode
            WHERE i.shelf_code <> '未上架'
              AND (?='' OR i.shelf_code=?)
              AND (?='' OR i.barcode LIKE ? OR p.name LIKE ?)
            ORDER BY i.shelf_code, i.expiry_date, p.name
            """,
            (shelf_code, shelf_code, keyword, keyword_like, keyword_like),
        ).fetchall()
        for row in rows:
            status = "正常"
            tag = ""
            if row["zone"] in SPECIAL_ZONES:
                status = f"特殊區：{row['zone']}（不可配貨）"
            if row["expiry_required"] and not Utils.is_no_expiry(row["expiry_date"]):
                valid, expired, days = Utils.validate_date(row["expiry_date"])
                if not valid:
                    status, tag = "效期資料異常", "danger"
                elif expired:
                    status, tag = "已過期，請報廢", "danger"
                elif days < 90:
                    status, tag = f"即期品（剩 {days} 天）", "warning"
            if tag == "" and row["safety_stock"] > 0 and row["available_qty"] <= row["safety_stock"]:
                status, tag = "低於安全庫存", "danger"
            self.inventory_tree.insert(
                "",
                END,
                values=(
                    row["shelf_code"],
                    row["barcode"],
                    row["name"],
                    row["quantity"],
                    row["available_qty"],
                    Utils.display_expiry(row["expiry_date"], bool(row["expiry_required"])),
                    row["zone"],
                    status,
                ),
                tags=(tag,),
            )
        location_text = f"儲位 {shelf_code}" if shelf_code else "全部儲位"
        keyword_text = f"；關鍵字「{keyword}」" if keyword else ""
        self.set_status(self.inv_filter_status, f"{location_text}{keyword_text}：共 {len(rows)} 筆庫存批次", "info")

    # ---------- 進貨與上架 ----------

    def build_receiving_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame,
            "進貨／驗貨作業",
            "現場驗貨、建立叫貨單與歷史對帳分頁處理；所有商品驗收後先進入未上架區",
        )
        self.receiving_notebook = tb.Notebook(frame, bootstyle="primary")
        self.receiving_notebook.pack(fill=BOTH, expand=True)
        self.receiving_scan_tab = tb.Frame(self.receiving_notebook, padding=14)
        self.receiving_create_tab = tb.Frame(self.receiving_notebook, padding=14)
        self.receiving_query_tab = tb.Frame(self.receiving_notebook, padding=14)
        self.receiving_notebook.add(self.receiving_scan_tab, text=" 掃描進貨／驗貨 ")
        self.receiving_notebook.add(self.receiving_create_tab, text=" 建立進貨單 ")
        self.receiving_notebook.add(self.receiving_query_tab, text=" 查詢進貨單 ")
        self.build_receiving_scan_tab(self.receiving_scan_tab)
        self.build_receiving_order_tab(self.receiving_create_tab)
        self.build_receiving_query_tab(self.receiving_query_tab)
        return frame

    def build_receiving_scan_tab(self, frame):
        load_card = tb.Labelframe(frame, text="步驟 1：掃描或輸入進貨單號", bootstyle="primary", padding=14)
        load_card.pack(fill=X, pady=(0, 10))
        self.recv_order_no = tb.Entry(load_card, width=30)
        tb.Label(load_card, text="進貨單條碼:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.recv_order_no.grid(row=0, column=1, sticky=W, padx=(0, 12), pady=4)
        tb.Button(load_card, text="讀取進貨單", bootstyle="primary", command=self.load_receiving_order).grid(row=0, column=2, padx=4)
        tb.Button(load_card, text="前往建立進貨單", bootstyle="secondary", command=self.show_receiving_management).grid(row=0, column=3, padx=4)
        self.recv_order_no.bind("<Return>", lambda _event: self.load_receiving_order())

        self.recv_summary = tb.Label(frame, text="尚未讀取進貨單", font=("Microsoft JhengHei", 11), bootstyle="secondary")
        self.recv_summary.pack(anchor=W, pady=(0, 10))

        columns = ("line", "barcode", "name", "master", "required", "received", "remaining", "status")
        holder = tb.Frame(frame)
        holder.pack(fill=BOTH, expand=True)
        self.recv_tree = tb.Treeview(holder, columns=columns, show="headings", height=13, bootstyle="primary")
        headings = ("#", "商品條碼", "進貨單品名", "商品主檔", "應收", "已驗收", "剩餘", "狀態")
        widths = (50, 160, 250, 110, 75, 75, 75, 110)
        self.setup_tree_columns(self.recv_tree, columns, headings, widths, left_columns=("name",))
        self.recv_tree.tag_configure("done", background="#E1F5E7")
        self.recv_tree.tag_configure("missing", background="#FFF1D6")
        self.add_table_interactions(self.recv_tree, holder)
        self.add_tree_scrollbar(holder, self.recv_tree)

        scan_card = tb.Labelframe(frame, text="步驟 2：掃描商品並驗收", bootstyle="success", padding=14)
        scan_card.pack(fill=X, pady=12)
        self.recv_barcode = tb.Entry(scan_card, width=28)
        self.recv_qty = tb.Entry(scan_card, width=8)
        self.recv_expiry = tb.Entry(scan_card, width=16)
        self.recv_qty.insert(0, "1")
        fields = [("商品條碼", self.recv_barcode), ("本次數量", self.recv_qty), ("效期（YYYY-MM-DD）", self.recv_expiry)]
        for column, (label, widget) in enumerate(fields):
            tb.Label(scan_card, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=4)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=4)
        self.recv_scan_button = tb.Button(scan_card, text="確認驗收", bootstyle="success", command=self.scan_receiving_item)
        self.recv_scan_button.grid(row=0, column=6, padx=4)
        self.recv_barcode.bind("<Return>", lambda _event: self.scan_receiving_item())
        self.recv_qty.bind("<Return>", lambda _event: self.scan_receiving_item())
        self.recv_expiry.bind("<Return>", lambda _event: self.scan_receiving_item())
        self.recv_barcode.bind("<FocusOut>", lambda _event: self.sync_receiving_expiry_lock())

        action_bar = tb.Frame(frame)
        action_bar.pack(fill=X)
        self.recv_complete_button = tb.Button(action_bar, text="完成驗收並鎖定進貨單（全數驗收後自動觸發）", bootstyle="primary", command=self.complete_current_receiving)
        self.recv_complete_button.pack(side=RIGHT)
        self.recv_start_button = tb.Button(action_bar, text="開始驗收（讀取待驗收單後自動觸發）", bootstyle="success", command=self.start_current_receiving)
        self.recv_start_button.pack(side=RIGHT, padx=8)
        tb.Button(action_bar, text="建立商品主檔", bootstyle="warning", command=self.open_receiving_product_master).pack(side=RIGHT, padx=8)
        self.recv_reset_button = tb.Button(action_bar, text="商品歸零", bootstyle="danger-outline", command=self.reset_current_receiving_scan)
        self.recv_reset_button.pack(side=RIGHT, padx=8)
        self.recv_status = tb.Label(frame, text="掃描進貨單條碼後將自動開始驗收，逐項掃描商品；全數驗收足額後會自動完成並鎖定。", bootstyle="secondary")
        self.recv_status.pack(anchor=W, pady=(10, 7))
        self.recv_info_tree = self.build_product_info_panel(frame, "目前掃描商品確認")

    def build_receiving_order_tab(self, frame):
        create = tb.Labelframe(frame, text="建立進貨單", bootstyle="primary", padding=14)
        create.pack(fill=X, pady=(0, 12))
        self.recv_supplier = tb.Entry(create, width=28)
        self.recv_note = tb.Entry(create, width=45)
        tb.Label(create, text="供應商:").grid(row=0, column=0, sticky=W, padx=(4, 7), pady=4)
        self.recv_supplier.grid(row=0, column=1, sticky=W, padx=(0, 16), pady=4)
        tb.Label(create, text="備註:").grid(row=0, column=2, sticky=W, padx=(4, 7), pady=4)
        self.recv_note.grid(row=0, column=3, sticky=W, padx=(0, 16), pady=4)

        line = tb.Labelframe(frame, text="新增進貨項目（可直接點選商品清單，或輸入新品供應商品名，驗收前必須建商品主檔）", bootstyle="info", padding=12)
        line.pack(fill=X, pady=(0, 12))
        self.recv_draft_barcode = tb.Combobox(line, width=42, state="normal")
        self.recv_draft_name = tb.Entry(line, width=32)
        self.recv_draft_qty = tb.Entry(line, width=10)
        fields = [("商品條碼／點選商品", self.recv_draft_barcode), ("單據品名", self.recv_draft_name), ("預計數量", self.recv_draft_qty)]
        for column, (label, widget) in enumerate(fields):
            tb.Label(line, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=4)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=4)
        tb.Button(line, text="加入項目", bootstyle="info", command=self.add_receiving_draft_line).grid(row=0, column=6, padx=4)
        self.recv_draft_barcode.bind("<<ComboboxSelected>>", self.apply_receiving_draft_selection)
        self.recv_draft_barcode.bind("<FocusOut>", self.apply_receiving_draft_selection)
        self.recv_draft_qty.bind("<Return>", lambda _event: self.add_receiving_draft_line())
        self.recv_draft_info = tb.Label(line, text="", bootstyle="secondary")
        self.recv_draft_info.grid(row=1, column=0, columnspan=7, sticky=W, padx=(4, 0), pady=(6, 0))

        draft_holder = tb.Frame(frame)
        draft_holder.pack(fill=BOTH, expand=True)
        columns = ("barcode", "name", "qty", "master")
        self.recv_draft_tree = tb.Treeview(draft_holder, columns=columns, show="headings", height=8, bootstyle="info")
        headings = ("商品條碼", "單據品名", "預計數量", "商品主檔")
        widths = (180, 360, 120, 120)
        self.setup_tree_columns(self.recv_draft_tree, columns, headings, widths, left_columns=("name",))
        self.add_table_interactions(self.recv_draft_tree, draft_holder)
        self.add_tree_scrollbar(draft_holder, self.recv_draft_tree)

        action = tb.Frame(frame)
        action.pack(fill=X, pady=12)
        tb.Button(action, text="移除選取項目", bootstyle="secondary", command=self.remove_receiving_draft_line).pack(side=LEFT)
        tb.Button(action, text="清空草稿", bootstyle="secondary", command=self.clear_receiving_draft).pack(side=LEFT, padx=8)
        tb.Button(action, text="建立進貨單並列印", bootstyle="primary", command=self.create_receiving_order_from_draft).pack(side=RIGHT)
        self.recv_create_status = tb.Label(frame, text="建立後會自動開啟進貨單列印頁面，請至「查詢進貨單」送出訂單並登錄到貨，再進行驗收。", bootstyle="secondary")
        self.recv_create_status.pack(anchor=W)

    def build_receiving_query_tab(self, frame):
        search = tb.Labelframe(frame, text="依進貨單號查詢／歷史對帳", bootstyle="secondary", padding=14)
        search.pack(fill=X, pady=(0, 10))
        self.recv_query_no = tb.Entry(search, width=32)
        tb.Label(search, text="進貨單號:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.recv_query_no.grid(row=0, column=1, sticky=W, padx=(0, 10), pady=4)
        tb.Button(search, text="查詢進貨單", bootstyle="secondary", command=self.refresh_receiving_order_list).grid(row=0, column=2, padx=4)
        tb.Button(search, text="顯示全部", bootstyle="outline-secondary", command=self.clear_receiving_query).grid(row=0, column=3, padx=4)
        self.recv_query_no.bind("<Return>", lambda _event: self.refresh_receiving_order_list())

        list_holder = tb.Frame(frame)
        list_holder.pack(fill=BOTH, expand=True)
        columns = ("order_no", "date", "supplier", "status", "lines", "required", "received", "progress", "prints", "last_print")
        self.recv_order_list_tree = tb.Treeview(list_holder, columns=columns, show="headings", height=9, bootstyle="secondary")
        headings = ("進貨單號", "日期", "供應商", "狀態", "品項", "應收", "已驗收", "驗收進度", "列印次數", "最後列印時間")
        widths = (185, 100, 180, 120, 60, 75, 75, 105, 80, 145)
        self.setup_tree_columns(self.recv_order_list_tree, columns, headings, widths, left_columns=("supplier",))
        self.recv_order_list_tree.tag_configure("done", background="#E1F5E7")
        self.recv_order_list_tree.tag_configure("in_progress", background="#FFF1D6")
        self.recv_order_list_tree.tag_configure("cancel", background="#FDE2E1")
        self.recv_order_list_tree.bind("<<TreeviewSelect>>", self.show_selected_receiving_order_details)
        self.add_table_interactions(self.recv_order_list_tree, list_holder)
        self.add_tree_scrollbar(list_holder, self.recv_order_list_tree)

        action = tb.Frame(frame)
        action.pack(fill=X, pady=10)
        tb.Button(action, text="標記已送出訂單", bootstyle="primary", command=lambda: self.advance_selected_receiving_order("已送出訂單")).pack(side=LEFT)
        tb.Button(action, text="登錄到貨／待驗收", bootstyle="warning", command=lambda: self.advance_selected_receiving_order("待驗收")).pack(side=LEFT, padx=8)
        tb.Button(action, text="取消進貨單", bootstyle="danger", command=self.cancel_selected_receiving_order).pack(side=LEFT, padx=8)
        tb.Button(action, text="補印進貨單（需填原因）", bootstyle="warning", command=self.reprint_selected_receiving_order).pack(side=LEFT, padx=8)
        tb.Button(action, text="帶入掃描驗貨", bootstyle="success", command=self.use_selected_receiving_order).pack(side=RIGHT)

        self.recv_query_summary = tb.Label(frame, text="輸入進貨單號可查詢狀態、驗收進度與歷史明細。", bootstyle="secondary")
        self.recv_query_summary.pack(anchor=W, pady=(0, 6))
        detail_holder = tb.Labelframe(frame, text="進貨單明細（尚未開始驗收時可移除誤加入的商品）", bootstyle="info", padding=8)
        detail_holder.pack(fill=BOTH, expand=True)
        detail_action = tb.Frame(detail_holder)
        detail_action.pack(fill=X, pady=(0, 6))
        tb.Button(detail_action, text="移除選取商品", bootstyle="secondary", command=self.remove_selected_receiving_order_item).pack(side=LEFT)
        detail_columns = ("line", "barcode", "name", "required", "received", "remaining", "status")
        self.recv_query_detail_tree = tb.Treeview(detail_holder, columns=detail_columns, show="headings", height=6, bootstyle="info")
        detail_headings = ("#", "商品條碼", "品名", "應收", "已驗收", "未驗收", "明細狀態")
        detail_widths = (45, 175, 300, 80, 80, 80, 120)
        self.setup_tree_columns(self.recv_query_detail_tree, detail_columns, detail_headings, detail_widths, left_columns=("name",))
        self.add_table_interactions(self.recv_query_detail_tree, detail_holder)
        self.add_tree_scrollbar(detail_holder, self.recv_query_detail_tree)

    def apply_receiving_draft_selection(self, _event=None):
        """點選商品清單或輸入條碼後，自動帶出 SKU／分類／效期設定，並鎖定已建檔商品的品名避免打錯。"""
        raw = self.recv_draft_barcode.get().strip()
        if " | " in raw:
            barcode = raw.split(" | ", 1)[0].strip()
            self.recv_draft_barcode.set(barcode)
        else:
            barcode = Utils.normalize_barcode(raw)
        self.refresh_receiving_draft_product_info(barcode)

    def fill_receiving_draft_product_name(self, _event=None):
        # 保留給舊呼叫路徑使用，實際邏輯統一由 refresh_receiving_draft_product_info 處理。
        barcode = Utils.normalize_barcode(self.recv_draft_barcode.get())
        self.refresh_receiving_draft_product_info(barcode)

    def refresh_receiving_draft_product_info(self, barcode):
        if not Utils.valid_barcode(barcode):
            self.recv_draft_info.configure(text="")
            return
        product = self.db.product_by_barcode(barcode)
        if product:
            # 已建檔商品：鎖定品名為主檔名稱，避免條碼對應到錯誤品名（如化妝水條碼卻顯示紙杯）。
            self.recv_draft_name.configure(state="normal")
            self.recv_draft_name.delete(0, END)
            self.recv_draft_name.insert(0, product["name"])
            self.recv_draft_name.configure(state="readonly")
            expiry_text = "需要效期／建立 LOT" if product["expiry_required"] else "無效期商品"
            self.recv_draft_info.configure(
                text=f"已建檔商品｜SKU：{product['sku']}｜分類：{product['category'] or '其他類別'}｜{expiry_text}",
                bootstyle="success",
            )
        else:
            self.recv_draft_name.configure(state="normal")
            self.recv_draft_info.configure(
                text="此條碼尚未建立商品主檔，屬新品；請輸入供應商單據品名，驗收前需先建檔。",
                bootstyle="warning",
            )

    def add_receiving_draft_line(self):
        raw_selection = self.recv_draft_barcode.get().strip()
        if " | " in raw_selection:
            raw_selection = raw_selection.split(" | ", 1)[0]
        barcode = Utils.normalize_barcode(raw_selection)
        name = self.recv_draft_name.get().strip()
        qty_text = self.recv_draft_qty.get().strip()
        if not Utils.valid_barcode(barcode):
            return self.set_status(self.recv_create_status, "條碼格式錯誤：限英數與連字號，長度 3 至 64 碼", "danger")
        if not name:
            product = self.db.product_by_barcode(barcode)
            name = product["name"] if product else ""
        if not name:
            return self.set_status(self.recv_create_status, "新品請輸入供應商單據上的商品名稱", "danger")
        if not qty_text.isdigit() or not 1 <= int(qty_text) <= 100000:
            return self.set_status(self.recv_create_status, "預計數量必須是 1 至 100,000 的整數", "danger")
        quantity = int(qty_text)
        if not messagebox.askyesno(
            "預計進貨數量確認",
            f"商品：{name}\n預計進貨數量：{quantity} 件\n\n是否確認？（避免如 50 誤打成 500 等輸入錯誤）",
        ):
            self.recv_draft_qty.focus_set()
            self.recv_draft_qty.select_range(0, END)
            return self.set_status(self.recv_create_status, "請修改預計進貨數量後再加入", "warning")
        existing = next((item for item in self.receiving_draft_items if item["barcode"] == barcode), None)
        if existing:
            existing["qty"] += quantity
        else:
            self.receiving_draft_items.append({"barcode": barcode, "name": name, "qty": quantity})
        for widget in (self.recv_draft_barcode, self.recv_draft_qty):
            widget.delete(0, END)
        self.recv_draft_name.configure(state="normal")
        self.recv_draft_name.delete(0, END)
        self.recv_draft_info.configure(text="")
        self.refresh_receiving_draft_tree()
        self.set_status(self.recv_create_status, f"已加入：{name} x {quantity}", "success")
        self.recv_draft_barcode.focus_set()

    def refresh_receiving_draft_tree(self):
        self.clear_tree(self.recv_draft_tree)
        for item in self.receiving_draft_items:
            master_status = "已建檔" if self.db.product_by_barcode(item["barcode"]) else "待建檔"
            self.recv_draft_tree.insert("", END, values=(item["barcode"], item["name"], item["qty"], master_status))

    def remove_receiving_draft_line(self):
        selected = self.recv_draft_tree.focus()
        if not selected:
            return self.set_status(self.recv_create_status, "請先選取要移除的進貨項目", "warning")
        barcode, name = self.recv_draft_tree.item(selected, "values")[0:2]
        if not messagebox.askyesno("移除商品", f"確定要移除「{name}」（{barcode}）嗎？"):
            return
        self.receiving_draft_items = [item for item in self.receiving_draft_items if item["barcode"] != barcode]
        self.refresh_receiving_draft_tree()
        self.set_status(self.recv_create_status, "已移除選取項目", "secondary")

    def clear_receiving_draft(self):
        self.receiving_draft_items = []
        self.refresh_receiving_draft_tree()
        self.set_status(self.recv_create_status, "已清空進貨單草稿", "secondary")

    def create_receiving_order_from_draft(self):
        try:
            order_no = self.db.create_receiving_order(
                self.recv_supplier.get(), self.receiving_draft_items, self.current_user, self.recv_note.get()
            )
            self.db.log_operation(self.current_user, "建立進貨單", order_no, self.recv_supplier.get().strip())
            self.receiving_draft_items = []
            self.recv_supplier.delete(0, END)
            self.recv_note.delete(0, END)
            self.refresh_receiving_draft_tree()
            self.recv_query_no.delete(0, END)
            self.recv_query_no.insert(0, order_no)
            self.refresh_receiving_order_list()
            try:
                self.print_receiving_document(order_no)
                print_note = "，已開啟進貨單列印頁面"
            except Exception as print_error:
                print_note = f"，但列印失敗：{print_error}"
            self.refresh_receiving_order_list()
            self.set_status(
                self.recv_create_status,
                f"已建立進貨單 {order_no}{print_note}；請至「查詢進貨單」標記已送出訂單並登錄到貨。",
                "success",
            )
            self.receiving_notebook.select(self.receiving_query_tab)
        except ValueError as error:
            self.set_status(self.recv_create_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_create_status, f"建立失敗：{error}", "danger")

    def refresh_receiving_order_list(self):
        self.clear_tree(self.recv_order_list_tree)
        for row in self.db.all_receiving_orders(self.recv_query_no.get()):
            progress = f"{row['received_qty']}/{row['total_qty']}"
            tag = (
                "done" if row["status"] == "已完成"
                else "cancel" if row["status"] == "已取消"
                else "in_progress" if row["status"] == "驗收中"
                else ""
            )
            self.recv_order_list_tree.insert(
                "", END,
                values=(
                    row["order_no"], row["order_date"], row["supplier_name"], row["status"],
                    row["line_count"], row["total_qty"], row["received_qty"], progress,
                    f"已列印 {row['print_count']} 次" if row["print_count"] else "尚未列印",
                    row["last_printed_at"] or "-",
                ),
                tags=(tag,) if tag else (),
            )
        self.clear_tree(self.recv_query_detail_tree)
        self.recv_query_summary.configure(text=f"查詢結果：共 {len(self.recv_order_list_tree.get_children())} 筆進貨單", bootstyle="secondary")

    def clear_receiving_query(self):
        self.recv_query_no.delete(0, END)
        self.refresh_receiving_order_list()

    def show_selected_receiving_order_details(self, _event=None, order_no=None):
        if not order_no:
            selected = self.recv_order_list_tree.focus()
            if not selected:
                return
            order_no = self.recv_order_list_tree.item(selected, "values")[0]
        header = self.db.receiving_order_header(order_no)
        if not header:
            return
        self.recv_query_summary.configure(
            text=(
                f"單號：{header['order_no']}    供應商：{header['supplier_name']}    "
                f"目前狀態：{header['status']}    建立日：{header['order_date']}"
            ),
            bootstyle="primary" if header["status"] != "已完成" else "success",
        )
        self.clear_tree(self.recv_query_detail_tree)
        for line in self.db.receiving_order_lines(order_no):
            remaining = line["required_qty"] - line["received_qty"]
            item_status = "已驗收完成" if remaining == 0 else "待驗收"
            self.recv_query_detail_tree.insert(
                "",
                END,
                values=(
                    line["line_no"], line["barcode"], line["product_name"],
                    line["required_qty"], line["received_qty"], remaining, item_status,
                ),
            )

    def advance_selected_receiving_order(self, new_status):
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        order_no = self.recv_order_list_tree.item(selected, "values")[0]
        try:
            self.db.set_receiving_order_status(order_no, new_status, self.current_user)
            self.refresh_receiving_order_list()
            self.set_status(self.recv_query_summary, f"進貨單 {order_no} 已更新為「{new_status}」", "success")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")

    def cancel_selected_receiving_order(self):
        """V6.1：取消進貨單。草稿可取消，已完成不可取消，取消後保留歷史紀錄。"""
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        order_no = self.recv_order_list_tree.item(selected, "values")[0]
        if not messagebox.askyesno("取消進貨單", f"是否確定取消此進貨單？\n{order_no}"):
            return
        try:
            self.db.cancel_receiving_order(order_no, self.current_user)
            self.db.log_operation(self.current_user, "取消進貨單", order_no)
            self.refresh_receiving_order_list()
            self.set_status(self.recv_query_summary, f"進貨單 {order_no} 已取消", "danger")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")

    def reprint_selected_receiving_order(self):
        """V6.5：補印獨立按鈕，需選擇原因後才會列印，並記錄補印人／時間／原因／次數。"""
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        order_no = self.recv_order_list_tree.item(selected, "values")[0]
        reason = self.prompt_reprint_reason("補印進貨單原因")
        if not reason:
            return
        try:
            self.print_receiving_document(order_no, reason=reason)
            self.refresh_receiving_order_list()
            self.set_status(self.recv_query_summary, f"已補印進貨單 {order_no}（原因：{reason}）", "success")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_query_summary, f"補印失敗：{error}", "danger")

    def remove_selected_receiving_order_item(self):
        """V6.1：移除進貨單中誤加入的商品明細；已完成單據禁止移除。"""
        order_selected = self.recv_order_list_tree.focus()
        item_selected = self.recv_query_detail_tree.focus()
        if not order_selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        if not item_selected:
            return self.set_status(self.recv_query_summary, "請先選取要移除的商品明細", "warning")
        order_no = self.recv_order_list_tree.item(order_selected, "values")[0]
        values = self.recv_query_detail_tree.item(item_selected, "values")
        barcode, name = values[1], values[2]
        if not messagebox.askyesno("移除商品", f"確定要從進貨單 {order_no} 移除「{name}」（{barcode}）嗎？"):
            return
        try:
            self.db.remove_receiving_order_item(order_no, barcode, self.current_user)
            self.db.log_operation(self.current_user, "移除進貨商品", order_no, f"{name}（{barcode}）")
            self.refresh_receiving_order_list()
            self.show_selected_receiving_order_details(order_no=order_no)
            self.set_status(self.recv_query_summary, f"已從 {order_no} 移除「{name}」", "secondary")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")

    def refresh_receiving_view(self):
        self.refresh_product_choices()
        self.refresh_receiving_draft_tree()
        self.refresh_receiving_order_list()
        if self.active_receiving_order_no:
            self.refresh_receiving_order()

    def show_receiving_management(self):
        self.receiving_notebook.select(self.receiving_create_tab)

    def use_selected_receiving_order(self):
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        values = self.recv_order_list_tree.item(selected, "values")
        order_no, status = values[0], values[3]
        if status not in ("待驗收", "驗收中"):
            return self.set_status(
                self.recv_query_summary,
                "請先完成「已送出訂單」與「登錄到貨／待驗收」流程後，再帶入掃描驗貨。",
                "warning",
            )
        self.recv_order_no.delete(0, END)
        self.recv_order_no.insert(0, order_no)
        self.receiving_notebook.select(self.receiving_scan_tab)
        self.load_receiving_order()

    def set_receiving_actions(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget in (self.recv_barcode, self.recv_qty, self.recv_expiry, self.recv_scan_button, self.recv_complete_button, self.recv_reset_button):
            widget.configure(state=state)

    def load_receiving_order(self):
        order_no = self.recv_order_no.get().strip().upper()
        self.recv_expiry.configure(state="normal")
        if not order_no:
            return self.set_status(self.recv_status, "請先掃描或輸入進貨單號", "danger")
        header = self.db.receiving_order_header(order_no)
        if not header:
            self.active_receiving_order_no = None
            self.receiving_read_only = False
            self.set_receiving_actions(False)
            self.recv_start_button.configure(state="disabled")
            self.clear_tree(self.recv_tree)
            self.recv_summary.configure(text="尚未讀取進貨單", bootstyle="secondary")
            return self.set_status(self.recv_status, "查無此進貨單", "danger")

        self.active_receiving_order_no = order_no
        self.receiving_read_only = header["status"] == "已完成"
        self.refresh_receiving_order()
        if self.receiving_read_only:
            self.set_receiving_actions(False)
            self.recv_start_button.configure(state="disabled")
            return self.set_status(self.recv_status, "此進貨單已完成；目前為唯讀查詢模式，禁止重複驗收。", "warning")
        if header["status"] == "待驗收":
            return self.start_current_receiving()
        if header["status"] == "驗收中":
            self.set_receiving_actions(True)
            self.recv_start_button.configure(state="disabled")
            missing = self.db.missing_products_for_receiving_order(order_no)
            if missing:
                details = "、".join(f"{row['product_name']}（{row['barcode']}）" for row in missing)
                self.set_status(self.recv_status, f"偵測到未建檔商品：{details}；請先建立商品主檔。", "warning")
                messagebox.showwarning("商品主檔防呆", f"進貨單 {order_no} 有未建檔商品：\n{details}\n\n請先建立商品主檔後再驗收該商品。")
            else:
                self.set_status(self.recv_status, "已載入驗收中的進貨單，請逐項掃描商品。", "success")
                self.recv_barcode.focus_set()
            return
        if header["status"] == "已取消":
            self.set_receiving_actions(False)
            self.recv_start_button.configure(state="disabled")
            return self.set_status(self.recv_status, "此進貨單已取消；目前為唯讀查詢模式。", "danger")

        self.set_receiving_actions(False)
        self.recv_start_button.configure(state="disabled")
        self.set_status(
            self.recv_status,
            f"此單目前為「{header['status']}」；請先在「查詢進貨單」完成送單與到貨登錄。",
            "warning",
        )

    def start_current_receiving(self):
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        try:
            header = self.db.start_receiving(self.active_receiving_order_no)
            self.receiving_read_only = header["status"] == "已完成"
            self.set_receiving_actions(not self.receiving_read_only)
            self.recv_start_button.configure(state="disabled")
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.recv_barcode.focus_set()
            self.set_status(self.recv_status, "已開始驗收，請逐項掃描商品條碼。", "success")
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")

    def refresh_receiving_order(self):
        if not self.active_receiving_order_no:
            return
        header = self.db.receiving_order_header(self.active_receiving_order_no)
        if not header:
            return
        self.recv_summary.configure(
            text=(f"單號：{header['order_no']}    日期：{header['order_date']}    "
                  f"供應商：{header['supplier_name']}    狀態：{header['status']}"),
            bootstyle="warning" if header["status"] == "已完成" else "primary",
        )
        self.clear_tree(self.recv_tree)
        for line in self.db.receiving_order_lines(self.active_receiving_order_no):
            remaining = line["required_qty"] - line["received_qty"]
            product_exists = bool(self.db.product_by_barcode(line["barcode"]))
            done = remaining == 0
            status = "待建商品主檔" if not product_exists else "已完成" if done else "待驗收"
            tag = "missing" if not product_exists else "done" if done else ""
            self.recv_tree.insert(
                "", END,
                values=(line["line_no"], line["barcode"], line["product_name"], "已建檔" if product_exists else "未建檔", line["required_qty"], line["received_qty"], remaining, status),
                tags=(tag,) if tag else (),
            )

    def open_receiving_product_master(self):
        barcode = Utils.normalize_barcode(self.recv_barcode.get())
        if not Utils.valid_barcode(barcode) and self.active_receiving_order_no:
            missing = self.db.missing_products_for_receiving_order(self.active_receiving_order_no)
            if missing:
                barcode = missing[0]["barcode"]
        self.show_view("products")
        if Utils.valid_barcode(barcode):
            self.open_new_product_dialog(barcode, after_save=self.refresh_receiving_order)

    def sync_receiving_expiry_lock(self, _event=None):
        """依商品主檔的效期管理開關鎖定／解鎖效期輸入框，無效期商品禁止輸入效期，避免產生錯誤 LOT。"""
        self.refresh_product_info_panel(self.recv_info_tree, self.recv_barcode.get(), "未上架")
        barcode = Utils.normalize_barcode(self.recv_barcode.get())
        product = self.db.product_by_barcode(barcode) if Utils.valid_barcode(barcode) else None
        if product and not product["expiry_required"]:
            self.recv_expiry.configure(state="normal")
            self.recv_expiry.delete(0, END)
            self.recv_expiry.configure(state="disabled")
        else:
            self.recv_expiry.configure(state="normal")

    def scan_receiving_item(self):
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先掃描進貨單條碼", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成進貨單只能查詢，禁止重複驗收。", "danger")
        barcode = Utils.normalize_barcode(self.recv_barcode.get())
        qty_text = self.recv_qty.get().strip()
        if not Utils.valid_barcode(barcode):
            return self.set_status(self.recv_status, "商品條碼格式錯誤", "danger")
        if not qty_text.isdigit() or not 1 <= int(qty_text) <= 100000:
            return self.set_status(self.recv_status, "本次數量必須是 1 至 100,000 的整數", "danger")
        product = self.db.product_by_barcode(barcode)
        self.sync_receiving_expiry_lock()
        if not product:
            self.set_status(self.recv_status, f"條碼 {barcode} 尚未建立商品主檔，請先建檔。", "warning")
            messagebox.showwarning("商品主檔防呆", f"條碼 {barcode} 尚未建立商品主檔。\n請完成建檔後再掃描驗收。")
            return
        expiry = self.recv_expiry.get().strip()
        if product["expiry_required"]:
            valid, expired, days = Utils.validate_date(expiry)
            if not valid:
                return self.set_status(self.recv_status, "效期格式錯誤，請輸入 YYYY-MM-DD", "danger")
            if expired:
                return self.set_status(self.recv_status, "嚴禁驗收已過期商品", "danger")
            if days < 90 and not messagebox.askyesno("即期品確認", f"{product['name']} 剩餘 {days} 天，仍要驗收嗎？"):
                return self.set_status(self.recv_status, "已取消本次驗收", "secondary")
        try:
            name, received, required = self.db.scan_receiving_item(
                self.active_receiving_order_no, barcode, int(qty_text), expiry, self.current_user
            )
            self.refresh_receiving_order()
            self.refresh_inventory()
            for widget in (self.recv_barcode, self.recv_qty):
                widget.delete(0, END)
            self.recv_expiry.configure(state="normal")
            self.recv_expiry.delete(0, END)
            self.recv_qty.insert(0, "1")
            self.set_status(self.recv_status, f"驗收成功：{name}（{received}/{required}）", "success")
            if self.receiving_order_fully_received(self.active_receiving_order_no):
                self.auto_complete_receiving()
            else:
                self.recv_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_status, f"驗收失敗：{error}", "danger")

    def receiving_order_fully_received(self, order_no):
        """判斷進貨單是否所有品項都已驗收足額，做為自動完成驗收的依據。"""
        lines = self.db.receiving_order_lines(order_no)
        if not lines:
            return False
        return all(line["received_qty"] >= line["required_qty"] for line in lines)

    def auto_complete_receiving(self):
        """所有商品驗收足額後自動完成並鎖定進貨單，無需再手動點擊按鈕。"""
        order_no = self.active_receiving_order_no
        try:
            self.db.complete_receiving(order_no, self.current_user)
            self.db.log_operation(self.current_user, "完成進貨單", order_no)
            self.receiving_read_only = True
            self.set_receiving_actions(False)
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.refresh_dashboard()
            self.set_status(self.recv_status, f"已全部驗收完成，進貨單 {order_no} 自動完成並鎖定。", "success")
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")

    def complete_current_receiving(self):
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成進貨單只能查詢，禁止重複驗收。", "danger")
        if not messagebox.askyesno("完成進貨單", f"確定要完成並鎖定進貨單 {self.active_receiving_order_no} 嗎？\n完成後不可修改。"):
            return
        try:
            self.db.complete_receiving(self.active_receiving_order_no, self.current_user)
            self.db.log_operation(self.current_user, "完成進貨單", self.active_receiving_order_no)
            self.receiving_read_only = True
            self.set_receiving_actions(False)
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.refresh_dashboard()
            self.set_status(self.recv_status, "進貨單已完成並鎖定；後續僅能查詢，不能重複進貨。", "success")
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")

    def reset_current_receiving_scan(self):
        """V6.6：商品歸零，防止刷到一半誤刷多件，將此張進貨單已驗收數量與未上架庫存全部重置。"""
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成或已取消進貨單只能查詢，無法歸零。", "danger")
        if not messagebox.askyesno(
            "商品歸零",
            f"確定要將進貨單 {self.active_receiving_order_no} 已驗收的商品數量全部歸零嗎？\n此動作會同步移除已寫入未上架區的庫存，且無法復原。",
        ):
            return
        try:
            self.db.reset_receiving_scan_progress(self.active_receiving_order_no, self.current_user)
            self.db.log_operation(self.current_user, "驗收商品歸零", self.active_receiving_order_no)
            self.refresh_receiving_order()
            self.refresh_inventory()
            self.refresh_putaway_view()
            for widget in (self.recv_barcode, self.recv_qty):
                widget.delete(0, END)
            self.recv_qty.insert(0, "1")
            self.recv_expiry.configure(state="normal")
            self.recv_expiry.delete(0, END)
            self.set_status(self.recv_status, "已將此進貨單已驗收數量歸零，請重新掃描。", "warning")
            self.recv_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_status, f"歸零失敗：{error}", "danger")

    # ---------- 退貨／還貨 ----------

    def build_returns_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame,
            "退貨／還貨作業",
            "登錄商品異常、附上證據照片並列印退貨表；退貨紀錄不會在未指定儲位與效期時自動扣庫存。",
        )
        form = tb.Labelframe(frame, text="新增退貨紀錄", bootstyle="danger", padding=14)
        form.pack(fill=X, pady=(0, 10))
        self.return_receiving_order_no = tb.Entry(form, width=25)
        self.return_barcode = tb.Entry(form, width=25)
        self.return_qty = tb.Entry(form, width=10)
        self.return_reason = tb.Combobox(form, values=RETURN_REASONS, state="readonly", width=14)
        self.return_reason.set(RETURN_REASONS[0])
        fields = [
            ("進貨單號", self.return_receiving_order_no, 0, 0),
            ("商品條碼", self.return_barcode, 0, 2),
            ("退貨數量", self.return_qty, 0, 4),
            ("退貨原因", self.return_reason, 0, 6),
        ]
        for label, widget, row, column in fields:
            tb.Label(form, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=5)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 14), pady=5)

        self.return_photo_source = tk.StringVar(value="")
        tb.Label(form, text="異常照片:").grid(row=1, column=0, sticky=W, padx=(4, 7), pady=5)
        tb.Entry(form, textvariable=self.return_photo_source, width=58, state="readonly").grid(row=1, column=1, columnspan=5, sticky=W, padx=(0, 8), pady=5)
        tb.Button(form, text="選擇／拍攝後附上", bootstyle="info", command=self.choose_return_photo).grid(row=1, column=6, columnspan=2, padx=4, pady=5)
        self.return_note = tb.Entry(form, width=68)
        tb.Label(form, text="備註:").grid(row=2, column=0, sticky=W, padx=(4, 7), pady=5)
        self.return_note.grid(row=2, column=1, columnspan=5, sticky=W, padx=(0, 8), pady=5)
        tb.Button(form, text="建立退貨單", bootstyle="danger", command=self.create_return_record).grid(row=2, column=6, columnspan=2, padx=4, pady=5)
        self.return_qty.bind("<Return>", lambda _event: self.create_return_record())

        self.return_status = tb.Label(frame, text="請輸入原始進貨單號；可選取相機或手機拍攝的異常照片作為證據。", bootstyle="secondary")
        self.return_status.pack(anchor=W, pady=(0, 8))

        holder = tb.Labelframe(frame, text="退貨紀錄／列印退貨表", bootstyle="secondary", padding=8)
        holder.pack(fill=BOTH, expand=True)
        columns = ("return_no", "receiving_no", "barcode", "name", "qty", "reason", "status", "photo", "created")
        self.return_tree = tb.Treeview(holder, columns=columns, show="headings", height=12, bootstyle="secondary")
        headings = ("退貨單號", "進貨單號", "商品條碼", "商品名稱", "數量", "原因", "狀態", "照片", "建立時間")
        widths = (175, 170, 150, 220, 60, 90, 125, 70, 145)
        self.setup_tree_columns(self.return_tree, columns, headings, widths, left_columns=("name",))
        self.return_tree.tag_configure("shipped", background="#E1F5E7")
        self.add_table_interactions(self.return_tree, holder)
        self.add_tree_scrollbar(holder, self.return_tree)

        actions = tb.Frame(frame)
        actions.pack(fill=X, pady=(10, 0))
        tb.Button(actions, text="列印退貨表", bootstyle="primary", command=self.print_selected_return).pack(side=RIGHT)
        tb.Button(actions, text="標記已寄回供應商", bootstyle="success", command=self.mark_selected_return_shipped).pack(side=RIGHT, padx=8)
        return frame

    def choose_return_photo(self):
        path = filedialog.askopenfilename(
            title="選擇商品異常證據照片",
            filetypes=[("圖片檔", "*.jpg *.jpeg *.png *.webp *.bmp"), ("所有檔案", "*.*")],
        )
        if path:
            self.return_photo_source.set(path)
            self.set_status(self.return_status, "已附上照片；建立退貨單後會複製保存為退貨證據。", "info")

    def create_return_record(self):
        receiving_order_no = self.return_receiving_order_no.get().strip().upper()
        barcode = Utils.normalize_barcode(self.return_barcode.get())
        qty_text = self.return_qty.get().strip()
        source_text = self.return_photo_source.get().strip()
        if not qty_text.isdigit():
            return self.set_status(self.return_status, "退貨數量必須是正整數", "danger")
        source = Path(source_text) if source_text else None
        if source and not source.is_file():
            return self.set_status(self.return_status, "找不到所選的異常照片，請重新選取。", "danger")
        try:
            return_no = self.db.create_return_order(
                receiving_order_no,
                barcode,
                int(qty_text),
                self.return_reason.get(),
                self.current_user,
                self.return_note.get(),
            )
            if source:
                evidence_dir = Path(__file__).resolve().parent / "wms_return_evidence"
                evidence_dir.mkdir(exist_ok=True)
                suffix = source.suffix.lower() or ".jpg"
                saved_path = evidence_dir / f"{return_no}{suffix}"
                shutil.copy2(source, saved_path)
                self.db.set_return_evidence(return_no, str(saved_path))
            for widget in (self.return_receiving_order_no, self.return_barcode, self.return_qty, self.return_note):
                widget.delete(0, END)
            self.return_photo_source.set("")
            self.return_reason.set(RETURN_REASONS[0])
            self.refresh_returns_view()
            self.set_status(self.return_status, f"已建立退貨單 {return_no}，可直接選取後列印退貨表。", "success")
        except ValueError as error:
            self.set_status(self.return_status, str(error), "danger")
        except OSError as error:
            self.refresh_returns_view()
            self.set_status(self.return_status, f"退貨單已建立，但照片儲存失敗：{error}", "warning")
        except Exception as error:
            self.set_status(self.return_status, f"建立退貨單失敗：{error}", "danger")

    def refresh_returns_view(self):
        self.clear_tree(self.return_tree)
        for row in self.db.all_return_orders():
            self.return_tree.insert(
                "",
                END,
                values=(
                    row["return_no"], row["receiving_order_no"], row["barcode"], row["product_name"],
                    row["return_qty"], row["return_reason"], row["status"],
                    "已附" if row["evidence_path"] else "未附", row["created_at"],
                ),
                tags=("shipped",) if row["status"] == "已寄回供應商" else (),
            )

    def selected_return_no(self):
        selected = self.return_tree.focus()
        if not selected:
            return None
        return self.return_tree.item(selected, "values")[0]

    def mark_selected_return_shipped(self):
        return_no = self.selected_return_no()
        if not return_no:
            return self.set_status(self.return_status, "請先選取退貨單", "warning")
        try:
            self.db.mark_return_shipped(return_no, self.current_user)
            self.refresh_returns_view()
            self.set_status(self.return_status, f"退貨單 {return_no} 已標記為寄回供應商。", "success")
        except ValueError as error:
            self.set_status(self.return_status, str(error), "danger")

    def print_selected_return(self):
        return_no = self.selected_return_no()
        if not return_no:
            return self.set_status(self.return_status, "請先選取要列印的退貨單", "warning")
        try:
            self.print_return_document(return_no)
            self.set_status(self.return_status, f"已開啟退貨單 {return_no} 的列印頁面。", "success")
        except Exception as error:
            self.set_status(self.return_status, f"列印退貨表失敗：{error}", "danger")

    def build_putaway_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "上架作業", "系統會由未上架區依 FEFO 原則取出最早效期批次")
        card = tb.Labelframe(frame, text="上架資料", bootstyle="success", padding=18)
        card.pack(fill=X)
        self.put_barcode = tb.Entry(card, width=22)
        self.put_shelf = tb.Combobox(card, width=12, state="normal")
        self.put_shelf.configure(values=self.db.active_shelf_codes(include_special=False))
        self.put_qty = tb.Entry(card, width=10)
        fields = [("商品條碼", self.put_barcode), ("目標儲位", self.put_shelf), ("數量", self.put_qty)]
        for column, (label, widget) in enumerate(fields):
            tb.Label(card, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=8)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 18), pady=8)
        tb.Button(card, text="確認上架", bootstyle="success", command=self.process_putaway).grid(row=0, column=6, padx=6)
        self.put_barcode.bind("<Return>", lambda _event: self.put_shelf.focus_set())
        self.put_shelf.bind("<Return>", lambda _event: self.put_qty.focus_set())
        self.put_qty.bind("<Return>", lambda _event: self.process_putaway())
        self.put_barcode.bind("<FocusOut>", self.refresh_putaway_product_info)
        self.put_shelf.bind("<FocusOut>", self.refresh_putaway_product_info)
        self.put_status = tb.Label(frame, text="不可上架至未上架、品檢、報廢或出貨暫存區", bootstyle="secondary")
        self.put_status.pack(anchor=W, pady=14)
        self.put_info_tree = self.build_product_info_panel(frame, "上架商品確認")

        pending_card = tb.Labelframe(frame, text="待上架商品（未上架區庫存，點選可直接帶入商品條碼）", bootstyle="warning", padding=10)
        pending_card.pack(fill=BOTH, expand=True, pady=(14, 0))
        pending_columns = ("barcode", "name", "expiry", "qty")
        self.put_pending_tree = tb.Treeview(pending_card, columns=pending_columns, show="headings", height=8, bootstyle="warning")
        pending_headings = ("商品條碼", "商品名稱", "效期", "未上架數量")
        pending_widths = (160, 260, 120, 110)
        self.setup_tree_columns(self.put_pending_tree, pending_columns, pending_headings, pending_widths, left_columns=("name",))
        self.put_pending_tree.bind("<<TreeviewSelect>>", self.apply_pending_putaway_selection)
        self.add_table_interactions(self.put_pending_tree, pending_card)
        self.add_tree_scrollbar(pending_card, self.put_pending_tree)
        return frame

    def refresh_putaway_view(self):
        """V6.6：進入上架作業頁面時，重新整理儲位選單與待上架商品清單。"""
        self.put_shelf.configure(values=self.db.active_shelf_codes(include_special=False))
        self.refresh_putaway_pending_tree()

    def refresh_putaway_pending_tree(self):
        self.clear_tree(self.put_pending_tree)
        rows = self.db.cursor.execute(
            """
            SELECT i.barcode, p.name, i.expiry_date, i.quantity, p.expiry_required
            FROM inventory i
            JOIN products p ON p.barcode=i.barcode
            WHERE i.shelf_code='未上架'
            ORDER BY p.name, i.expiry_date
            """
        ).fetchall()
        for row in rows:
            self.put_pending_tree.insert(
                "",
                END,
                values=(
                    row["barcode"],
                    row["name"],
                    Utils.display_expiry(row["expiry_date"], bool(row["expiry_required"])),
                    row["quantity"],
                ),
            )
        return rows

    def apply_pending_putaway_selection(self, _event=None):
        selected = self.put_pending_tree.focus()
        if not selected:
            return
        barcode = self.put_pending_tree.item(selected, "values")[0]
        self.put_barcode.delete(0, END)
        self.put_barcode.insert(0, barcode)
        self.refresh_putaway_product_info()
        self.put_qty.focus_set()

    def refresh_putaway_product_info(self, _event=None):
        self.refresh_product_info_panel(self.put_info_tree, self.put_barcode.get(), self.put_shelf.get())

    def process_putaway(self):
        barcode = Utils.normalize_barcode(self.put_barcode.get())
        shelf_code = self.put_shelf.get().strip().upper()
        qty_text = self.put_qty.get().strip()
        self.refresh_product_info_panel(self.put_info_tree, barcode, shelf_code)
        if not Utils.valid_barcode(barcode) or not shelf_code or not qty_text.isdigit() or int(qty_text) <= 0:
            return self.set_status(self.put_status, "請完整輸入正確的條碼、目標儲位與數量", "danger")
        target_shelf = self.db.shelf_by_code(shelf_code)
        if not target_shelf:
            return self.set_status(self.put_status, "目標儲位不存在", "danger")
        if target_shelf["zone"] in SPECIAL_ZONES:
            return self.set_status(self.put_status, "目標儲位為特殊區，不能上架", "danger")

        quantity = int(qty_text)
        batches = self.db.cursor.execute(
            """
            SELECT id, quantity, expiry_date FROM inventory
            WHERE shelf_code='未上架' AND barcode=?
              AND (expiry_date='' OR expiry_date >= ?)
            ORDER BY CASE WHEN expiry_date='' THEN '9999-12-31' ELSE expiry_date END
            """,
            (barcode, Utils.today_text()),
        ).fetchall()
        if sum(batch["quantity"] for batch in batches) < quantity:
            return self.set_status(self.put_status, "未上架區可用庫存不足，或商品已過期", "danger")

        try:
            self.db.cursor.execute("BEGIN")
            remaining = quantity
            moved = []
            for batch in batches:
                if remaining == 0:
                    break
                move_qty = min(remaining, batch["quantity"])
                after_source = self.db.deduct_inventory(batch["id"], batch["quantity"], move_qty)
                before_target, after_target = self.db.add_inventory(
                    shelf_code, barcode, batch["expiry_date"], move_qty
                )
                self.db.log_transaction(
                    "上架",
                    barcode,
                    "未上架",
                    shelf_code,
                    batch["quantity"],
                    after_source,
                    -move_qty,
                    batch["expiry_date"],
                    self.current_user,
                    reason=f"目標儲位原數量 {before_target}，上架後 {after_target}",
                )
                remaining -= move_qty
                moved.append(f"{Utils.display_expiry(batch['expiry_date'])} x {move_qty}")
            self.db.conn.commit()
            self.set_status(self.put_status, f"上架成功：{quantity} 件至 {shelf_code}（{'、'.join(moved)}）", "success")
            for widget in (self.put_barcode, self.put_shelf, self.put_qty):
                widget.delete(0, END)
            self.refresh_product_info_panel(self.put_info_tree, "")
            self.refresh_putaway_pending_tree()
            self.put_barcode.focus_set()
        except Exception as error:
            self.db.conn.rollback()
            self.set_status(self.put_status, f"上架失敗：{error}", "danger")

    # ---------- 出貨單管理 ----------

    def build_orders_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "出貨單管理", "建立分店訂單、預留 FEFO 儲位批次、列印與補印出貨單")
        notebook = tb.Notebook(frame, bootstyle="primary")
        notebook.pack(fill=BOTH, expand=True)
        create_tab = tb.Frame(notebook, padding=14)
        list_tab = tb.Frame(notebook, padding=14)
        query_tab = tb.Frame(notebook, padding=14)
        notebook.add(create_tab, text=" 建立出貨單 ")
        notebook.add(list_tab, text=" 出貨單清單 ")
        notebook.add(query_tab, text=" 出貨單查詢 ")
        self.build_order_create_tab(create_tab)
        self.build_order_list_tab(list_tab)
        self.build_order_query_tab(query_tab)
        return frame

    def build_order_query_tab(self, frame):
        """V6.1：獨立的出貨單查詢頁，可依單號／日期／商品名稱或 SKU／門市查詢，純查詢不改變單據狀態。"""
        search = tb.Labelframe(frame, text="出貨單查詢", bootstyle="secondary", padding=14)
        search.pack(fill=X, pady=(0, 10))
        self.order_query_no = tb.Entry(search, width=22)
        self.order_query_date = tb.Entry(search, width=14)
        self.order_query_keyword = tb.Entry(search, width=22)
        self.order_query_branch = tb.Entry(search, width=18)
        fields = [
            ("出貨單號", self.order_query_no, 0, 0),
            ("日期（YYYY-MM-DD）", self.order_query_date, 0, 2),
            ("商品名稱／SKU", self.order_query_keyword, 0, 4),
            ("門市", self.order_query_branch, 0, 6),
        ]
        for label, widget, row, column in fields:
            tb.Label(search, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 14), pady=6)
        tb.Button(search, text="查詢", bootstyle="secondary", command=self.refresh_order_query_list).grid(row=0, column=8, padx=4)
        tb.Button(search, text="顯示全部", bootstyle="outline-secondary", command=self.clear_order_query).grid(row=0, column=9, padx=4)
        for widget in (self.order_query_no, self.order_query_date, self.order_query_keyword, self.order_query_branch):
            widget.bind("<Return>", lambda _event: self.refresh_order_query_list())

        list_holder = tb.Frame(frame)
        list_holder.pack(fill=BOTH, expand=True)
        columns = ("order_no", "date", "creator", "status", "lines", "branch")
        self.order_query_tree = tb.Treeview(list_holder, columns=columns, show="headings", height=9, bootstyle="secondary")
        headings = ("出貨單號", "建立日期", "建立人", "狀態", "品項數", "門市")
        widths = (185, 100, 120, 100, 70, 220)
        self.setup_tree_columns(self.order_query_tree, columns, headings, widths, left_columns=("branch",))
        self.order_query_tree.tag_configure("done", background="#E1F5E7")
        self.order_query_tree.tag_configure("cancel", background="#FDE2E1")
        self.order_query_tree.bind("<<TreeviewSelect>>", self.show_selected_order_query_details)
        self.add_table_interactions(self.order_query_tree, list_holder)
        self.add_tree_scrollbar(list_holder, self.order_query_tree)

        self.order_query_summary = tb.Label(frame, text="可依單號、日期、商品名稱／SKU、門市查詢，並點選查看完整明細。", bootstyle="secondary")
        self.order_query_summary.pack(anchor=W, pady=(8, 6))
        detail_holder = tb.Labelframe(frame, text="出貨單完整明細", bootstyle="info", padding=8)
        detail_holder.pack(fill=BOTH, expand=True)
        detail_columns = ("barcode", "name", "sku", "qty", "shelf", "expiry", "note")
        self.order_query_detail_tree = tb.Treeview(detail_holder, columns=detail_columns, show="headings", height=8, bootstyle="info")
        detail_headings = ("商品條碼", "商品名稱", "SKU", "數量", "儲位", "效期", "備註")
        detail_widths = (150, 220, 110, 70, 90, 100, 220)
        self.setup_tree_columns(self.order_query_detail_tree, detail_columns, detail_headings, detail_widths, left_columns=("name", "note"))
        self.add_table_interactions(self.order_query_detail_tree, detail_holder)
        self.add_tree_scrollbar(detail_holder, self.order_query_detail_tree)

    def refresh_order_query_list(self):
        self.clear_tree(self.order_query_tree)
        rows = self.db.search_shipping_orders(
            self.order_query_no.get(), self.order_query_date.get(),
            self.order_query_keyword.get(), self.order_query_branch.get(),
        )
        for row in rows:
            tag = "done" if row["status"] == "已完成" else "cancel" if row["status"] == "已取消" else ""
            self.order_query_tree.insert(
                "", END,
                values=(
                    row["order_no"], row["order_date"], row["created_by"], row["status"],
                    row["line_count"], f"{row['branch_code']} {row['branch_name']}",
                ),
                tags=(tag,) if tag else (),
            )
        self.clear_tree(self.order_query_detail_tree)
        self.set_status(self.order_query_summary, f"查詢結果：共 {len(rows)} 筆出貨單", "secondary")

    def clear_order_query(self):
        for widget in (self.order_query_no, self.order_query_date, self.order_query_keyword, self.order_query_branch):
            widget.delete(0, END)
        self.refresh_order_query_list()

    def show_selected_order_query_details(self, _event=None):
        selected = self.order_query_tree.focus()
        if not selected:
            return
        order_no = self.order_query_tree.item(selected, "values")[0]
        self.clear_tree(self.order_query_detail_tree)
        for line, allocations in self.db.order_lines(order_no):
            product = self.db.product_by_barcode(line["barcode"])
            sku = product["sku"] if product else "-"
            if allocations:
                for allocation in allocations:
                    expiry = Utils.display_expiry(allocation["expiry_date"])
                    self.order_query_detail_tree.insert(
                        "", END,
                        values=(
                            line["barcode"], line["product_name"], sku,
                            allocation["allocated_qty"], allocation["shelf_code"], expiry,
                            f"已出 {allocation['shipped_qty']}/{allocation['allocated_qty']}",
                        ),
                    )
            else:
                self.order_query_detail_tree.insert(
                    "", END,
                    values=(line["barcode"], line["product_name"], sku, line["required_qty"], "-", "-", "尚未配貨"),
                )

    def build_order_create_tab(self, frame):
        header = tb.Labelframe(frame, text="出貨資料", bootstyle="primary", padding=14)
        header.pack(fill=X, pady=(0, 12))
        self.order_branch_combo = tb.Combobox(header, width=32, state="readonly")
        self.order_carrier_combo = tb.Combobox(header, values=CARRIERS, width=18, state="readonly")
        self.order_tracking = tb.Entry(header, width=24)
        self.order_box_count = tb.Entry(header, width=8)
        self.order_box_count.insert(0, "1")
        fields = [
            ("分店", self.order_branch_combo, 0, 0),
            ("物流商", self.order_carrier_combo, 0, 2),
            ("託運單號（可後補）", self.order_tracking, 0, 4),
            ("箱數", self.order_box_count, 0, 6),
        ]
        for label, widget, row, column in fields:
            tb.Label(header, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 16), pady=6)
        self.order_branch_combo.bind("<<ComboboxSelected>>", self.apply_branch_default_carrier)

        line_form = tb.Labelframe(frame, text="新增商品項目", bootstyle="info", padding=12)
        line_form.pack(fill=X, pady=(0, 12))
        self.order_product_combo = tb.Combobox(line_form, width=48, state="readonly")
        self.order_line_qty = tb.Entry(line_form, width=10)
        tb.Label(line_form, text="商品:").grid(row=0, column=0, sticky=W, padx=(4, 7), pady=4)
        self.order_product_combo.grid(row=0, column=1, sticky=W, padx=(0, 18), pady=4)
        tb.Label(line_form, text="需求數量:").grid(row=0, column=2, sticky=W, padx=(4, 7), pady=4)
        self.order_line_qty.grid(row=0, column=3, sticky=W, padx=(0, 18), pady=4)
        tb.Button(line_form, text="加入項目", bootstyle="info", command=self.add_order_draft_line).grid(row=0, column=4, padx=4)
        self.order_line_qty.bind("<Return>", lambda _event: self.add_order_draft_line())

        columns = ("barcode", "name", "qty", "available")
        draft_holder = tb.Frame(frame)
        self.order_draft_tree = tb.Treeview(draft_holder, columns=columns, show="headings", height=11, bootstyle="info")
        headings = ("商品條碼", "商品名稱", "需求數量", "目前可配庫存")
        widths = (190, 360, 140, 160)
        self.setup_tree_columns(self.order_draft_tree, columns, headings, widths, left_columns=("name",))
        action_bar = tb.Frame(frame)
        action_bar.pack(fill=X, pady=12)
        tb.Button(action_bar, text="移除選取項目", bootstyle="secondary", command=self.remove_order_draft_line).pack(side=LEFT)
        tb.Button(action_bar, text="清空草稿", bootstyle="secondary", command=self.clear_order_draft).pack(side=LEFT, padx=8)
        tb.Button(action_bar, text="建立出貨單並列印", bootstyle="primary", command=self.create_order_from_draft).pack(side=RIGHT)
        self.order_create_status = tb.Label(frame, text="建立後系統會依 FEFO 指定儲位與效期，庫存會先被保留。", bootstyle="secondary")
        self.order_create_status.pack(anchor=W)
        draft_holder.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.add_table_interactions(self.order_draft_tree, draft_holder)
        self.add_tree_scrollbar(draft_holder, self.order_draft_tree)

    def build_order_list_tab(self, frame):
        toolbar = tb.Frame(frame)
        toolbar.pack(fill=X, pady=(0, 8))
        tb.Button(toolbar, text="重新整理", bootstyle="secondary", command=self.refresh_order_list).pack(side=LEFT)
        tb.Button(toolbar, text="檢視配貨內容", bootstyle="info", command=self.preview_selected_order).pack(side=LEFT, padx=6)
        tb.Button(toolbar, text="補印出貨單（需填原因）", bootstyle="warning", command=self.reprint_selected_order).pack(side=LEFT, padx=6)
        tb.Button(toolbar, text="取消單據", bootstyle="danger", command=self.cancel_selected_order).pack(side=RIGHT)

        columns = ("order_no", "date", "branch", "status", "lines", "qty", "carrier", "tracking", "prints", "last_print", "label", "label_time")
        self.order_list_tree = tb.Treeview(frame, columns=columns, show="headings", height=22, bootstyle="primary")
        headings = ("出貨單號", "日期", "分店", "狀態", "品項", "件數", "物流商", "託運單號", "列印次數", "最後列印時間", "箱標補印次數", "箱標最後列印")
        widths = (175, 105, 190, 100, 70, 70, 135, 155, 80, 145, 90, 145)
        self.setup_tree_columns(self.order_list_tree, columns, headings, widths, left_columns=("branch",))
        self.order_list_tree.tag_configure("done", background="#E1F5E7")
        self.order_list_tree.tag_configure("cancel", background="#FDE2E1")
        self.add_table_interactions(self.order_list_tree, frame)
        self.add_tree_scrollbar(frame, self.order_list_tree)

    def refresh_product_choices(self):
        values = [f"{row['barcode']} | {row['name']}" for row in self.db.all_products()]
        if hasattr(self, "order_product_combo"):
            self.order_product_combo.configure(values=values)
        if hasattr(self, "recv_draft_barcode"):
            self.recv_draft_barcode.configure(values=values)

    def refresh_branch_choices(self):
        values = [f"{row['id']} | {row['code']} | {row['name']}" for row in self.db.active_branches()]
        if hasattr(self, "order_branch_combo"):
            current = self.order_branch_combo.get()
            self.order_branch_combo.configure(values=values)
            if current not in values:
                self.order_branch_combo.set(values[0] if values else "")
                self.apply_branch_default_carrier()

    def apply_branch_default_carrier(self, _event=None):
        selected = self.order_branch_combo.get().strip()
        if not selected:
            return
        try:
            branch_id = int(selected.split(" | ", 1)[0])
        except ValueError:
            return
        branch = self.db.branch_by_id(branch_id)
        if branch:
            self.order_carrier_combo.set(branch["default_carrier"] or "未指定")

    def add_order_draft_line(self):
        selection = self.order_product_combo.get().strip()
        qty_text = self.order_line_qty.get().strip()
        if not selection:
            return self.set_status(self.order_create_status, "請先選擇商品", "danger")
        if not qty_text.isdigit() or int(qty_text) <= 0 or int(qty_text) > 100000:
            return self.set_status(self.order_create_status, "需求數量必須是 1 至 100,000 的整數", "danger")
        barcode = selection.split(" | ", 1)[0]
        product = self.db.product_by_barcode(barcode)
        if not product:
            return self.set_status(self.order_create_status, "商品已不存在，請重新選擇", "danger")
        requested_qty = int(qty_text)
        existing = next((item for item in self.order_draft_items if item["barcode"] == barcode), None)
        if existing:
            existing["qty"] += requested_qty
        else:
            self.order_draft_items.append({"barcode": barcode, "name": product["name"], "qty": requested_qty})
        self.order_line_qty.delete(0, END)
        self.refresh_order_draft_tree()
        self.set_status(self.order_create_status, f"已加入：{product['name']} x {requested_qty}", "success")

    def refresh_order_draft_tree(self):
        self.clear_tree(self.order_draft_tree)
        for item in self.order_draft_items:
            available = self.db.available_qty_for_order(item["barcode"])
            self.order_draft_tree.insert(
                "", END, values=(item["barcode"], item["name"], item["qty"], available)
            )

    def remove_order_draft_line(self):
        selected = self.order_draft_tree.focus()
        if not selected:
            return self.set_status(self.order_create_status, "請先選取要移除的商品項目", "warning")
        barcode, name = self.order_draft_tree.item(selected, "values")[0:2]
        if not messagebox.askyesno("移除商品", f"確定要移除「{name}」（{barcode}）嗎？"):
            return
        self.order_draft_items = [item for item in self.order_draft_items if item["barcode"] != barcode]
        self.refresh_order_draft_tree()
        self.set_status(self.order_create_status, "已移除選取項目", "secondary")

    def clear_order_draft(self):
        self.order_draft_items = []
        self.refresh_order_draft_tree()
        self.set_status(self.order_create_status, "已清空出貨單草稿", "secondary")

    def create_order_from_draft(self):
        try:
            selected_branch = self.order_branch_combo.get().strip()
            if not selected_branch:
                raise ValueError("請先選擇分店")
            try:
                branch_id = int(selected_branch.split(" | ", 1)[0])
            except ValueError as error:
                raise ValueError("分店資料格式錯誤，請重新選擇") from error
            box_text = self.order_box_count.get().strip()
            if not box_text.isdigit() or not 1 <= int(box_text) <= 99:
                raise ValueError("箱數必須是 1 至 99 的整數")
            order_no = self.db.create_shipping_order(
                branch_id,
                self.order_carrier_combo.get() or "未指定",
                self.order_tracking.get().strip(),
                int(box_text),
                self.order_draft_items,
                self.current_user,
            )
            self.db.log_operation(self.current_user, "建立出貨單", order_no)
            self.order_draft_items = []
            self.refresh_order_draft_tree()
            self.order_tracking.delete(0, END)
            self.order_box_count.delete(0, END)
            self.order_box_count.insert(0, "1")
            self.refresh_order_list()
            try:
                self.print_order_document(order_no)
                print_note = "，已開啟出貨單列印頁面"
            except Exception as print_error:
                print_note = f"，但列印失敗：{print_error}"
            self.refresh_order_list()
            self.set_status(
                self.order_create_status,
                f"已建立 {order_no}，庫存已保留並完成 FEFO 配貨{print_note}",
                "success",
            )
        except ValueError as error:
            self.set_status(self.order_create_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.order_create_status, f"建立失敗：{error}", "danger")

    def refresh_orders_view(self):
        self.refresh_product_choices()
        self.refresh_branch_choices()
        self.refresh_order_draft_tree()
        self.refresh_order_list()
        self.refresh_order_query_list()

    def refresh_order_list(self):
        self.clear_tree(self.order_list_tree)
        for row in self.db.all_orders():
            tag = "done" if row["status"] == "已完成" else "cancel" if row["status"] == "已取消" else ""
            self.order_list_tree.insert(
                "",
                END,
                values=(
                    row["order_no"],
                    row["order_date"],
                    f"{row['branch_code']} {row['branch_name']}",
                    row["status"],
                    row["line_count"],
                    row["total_qty"],
                    row["carrier"],
                    row["tracking_no"] or "-",
                    f"已列印 {row['print_count']} 次" if row["print_count"] else "尚未列印",
                    row["last_printed_at"] or "-",
                    f"{row['label_print_count']} 次" if row["label_print_count"] else "尚未列印",
                    row["label_last_printed_at"] or "-",
                ),
                tags=(tag,),
            )

    def selected_order_no(self):
        selected = self.order_list_tree.focus()
        if not selected:
            raise ValueError("請先在清單中選取出貨單")
        return self.order_list_tree.item(selected, "values")[0]

    def preview_selected_order(self):
        try:
            self.show_order_preview(self.selected_order_no())
        except ValueError as error:
            messagebox.showwarning("無法檢視", str(error))

    def reprint_selected_order(self):
        """V6.5：補印獨立按鈕，需選擇原因後才會列印，並記錄補印人／時間／原因／次數。"""
        order_no = self.selected_order_no()
        if not order_no:
            return messagebox.showwarning("補印出貨單", "請先選取出貨單")
        reason = self.prompt_reprint_reason("補印出貨單原因")
        if not reason:
            return
        try:
            self.print_order_document(order_no, reason=reason)
            self.refresh_order_list()
            messagebox.showinfo("補印完成", f"已補印出貨單 {order_no}（原因：{reason}）")
        except ValueError as error:
            messagebox.showwarning("無法補印", str(error))
        except Exception as error:
            messagebox.showerror("補印失敗", str(error))

    def cancel_selected_order(self):
        try:
            order_no = self.selected_order_no()
            if not messagebox.askyesno("取消出貨單", f"確定要取消 {order_no} 嗎？\n保留庫存會立即釋放。"):
                return
            self.db.cancel_order(order_no, self.current_user)
            self.db.log_operation(self.current_user, "取消出貨單", order_no)
            self.refresh_order_list()
            messagebox.showinfo("完成", f"{order_no} 已取消，保留庫存已釋放")
        except ValueError as error:
            messagebox.showwarning("無法取消", str(error))

    def show_order_preview(self, order_no):
        header = self.db.order_header(order_no)
        if not header:
            raise ValueError("查無出貨單")
        dialog = tb.Toplevel(self.root)
        dialog.title(f"出貨單內容 - {order_no}")
        dialog.geometry("1040x560")
        dialog.transient(self.root)
        body = tb.Frame(dialog, padding=16)
        body.pack(fill=BOTH, expand=True)
        title_label = tb.Label(
            body,
            text=f"{order_no}  |  {header['branch_code']} {header['branch_name']}  |  {header['status']}",
            font=("Microsoft JhengHei", 15, "bold"),
            bootstyle="primary",
        )
        title_label.pack(anchor=W, pady=(0, 10))
        columns = ("barcode", "name", "required", "scanned", "allocation")
        tree = tb.Treeview(body, columns=columns, show="headings", height=16, bootstyle="primary")
        headings = ("商品條碼", "商品名稱", "應出", "已掃", "建議儲位／批次")
        widths = (170, 260, 90, 90, 390)
        self.setup_tree_columns(tree, columns, headings, widths, left_columns=("name", "allocation"))
        self.add_table_interactions(tree, body)

        def reload_tree():
            self.clear_tree(tree)
            for line, allocations in self.db.order_lines(order_no):
                text = self.format_allocations(allocations)
                tree.insert("", END, values=(line["barcode"], line["product_name"], line["required_qty"], line["scanned_qty"], text))

        def remove_item():
            selected = tree.focus()
            if not selected:
                return messagebox.showwarning("移除商品", "請先選取要移除的商品", parent=dialog)
            values = tree.item(selected, "values")
            barcode, name = values[0], values[1]
            if not messagebox.askyesno("移除商品", f"確定要從 {order_no} 移除「{name}」（{barcode}）嗎？", parent=dialog):
                return
            try:
                self.db.remove_shipping_order_item(order_no, barcode, self.current_user)
                self.db.log_operation(self.current_user, "移除出貨商品", order_no, f"{name}（{barcode}）")
                reload_tree()
                self.refresh_order_list()
                messagebox.showinfo("完成", f"已移除「{name}」", parent=dialog)
            except ValueError as error:
                messagebox.showwarning("無法移除", str(error), parent=dialog)

        action_bar = tb.Frame(body)
        action_bar.pack(fill=X, pady=(10, 0), side="bottom")
        tb.Button(action_bar, text="關閉", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT)
        if header["status"] == "待撿貨":
            tb.Button(action_bar, text="移除選取商品", bootstyle="danger", command=remove_item).pack(side=LEFT)
        tree.pack(fill=BOTH, expand=True)
        reload_tree()

    # ---------- 出貨掃描與包裝 ----------

    def build_shipping_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "出貨作業", "先掃出貨單條碼，再逐項掃商品；全部掃描足額後會自動完成包裝、扣庫存並列印箱標")
        load_card = tb.Labelframe(frame, text="步驟 1：掃描出貨單", bootstyle="primary", padding=14)
        load_card.pack(fill=X, pady=(0, 10))
        self.pack_order_no = tb.Entry(load_card, width=30)
        tb.Label(load_card, text="出貨單條碼:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.pack_order_no.grid(row=0, column=1, sticky=W, padx=(0, 12), pady=4)
        tb.Button(load_card, text="讀取出貨單", bootstyle="primary", command=self.load_order_for_packing).grid(row=0, column=2, padx=4)
        self.pack_order_no.bind("<Return>", lambda _event: self.load_order_for_packing())

        self.pack_summary = tb.Label(frame, text="尚未讀取出貨單", font=("Microsoft JhengHei", 11), bootstyle="secondary")
        self.pack_summary.pack(anchor=W, pady=(0, 10))

        columns = ("line", "barcode", "name", "allocation", "required", "scanned", "remaining", "status")
        shipping_body = tb.Frame(frame)
        shipping_body.pack(fill=BOTH, expand=True)
        tree_holder = tb.Frame(shipping_body)
        self.pack_tree = tb.Treeview(tree_holder, columns=columns, show="headings", height=14, bootstyle="primary")
        headings = ("#", "商品條碼", "商品名稱", "建議儲位／批次", "應出", "已掃", "剩餘", "狀態")
        widths = (50, 160, 210, 370, 80, 80, 80, 110)
        self.setup_tree_columns(self.pack_tree, columns, headings, widths, left_columns=("name", "allocation"))
        self.pack_tree.tag_configure("done", background="#E1F5E7")
        tree_holder.grid(row=0, column=0, sticky="nsew")
        self.add_table_interactions(self.pack_tree, tree_holder)
        self.add_tree_scrollbar(tree_holder, self.pack_tree)

        scan_card = tb.Labelframe(shipping_body, text="步驟 2：掃描箱內商品", bootstyle="success", padding=14)
        scan_card.grid(row=1, column=0, sticky=EW, pady=12)
        self.pack_item_barcode = tb.Entry(scan_card, width=28)
        self.pack_scan_qty = tb.Entry(scan_card, width=8)
        self.pack_scan_qty.insert(0, "1")
        tb.Label(scan_card, text="商品條碼:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.pack_item_barcode.grid(row=0, column=1, sticky=W, padx=(0, 15), pady=4)
        tb.Label(scan_card, text="本次數量:").grid(row=0, column=2, sticky=W, padx=(4, 8), pady=4)
        self.pack_scan_qty.grid(row=0, column=3, sticky=W, padx=(0, 15), pady=4)
        self.pack_scan_button = tb.Button(scan_card, text="確認掃描", bootstyle="success", command=self.scan_packing_item)
        self.pack_scan_button.grid(row=0, column=4, padx=4)
        self.pack_item_barcode.bind("<Return>", lambda _event: self.scan_packing_item())
        self.pack_scan_qty.bind("<Return>", lambda _event: self.scan_packing_item())

        action_bar = tb.Frame(shipping_body)
        action_bar.grid(row=2, column=0, sticky=EW)
        self.pack_complete_button = tb.Button(action_bar, text="手動完成包裝並扣庫存（備援，一般會自動觸發）", bootstyle="primary", command=self.complete_current_packing)
        self.pack_complete_button.pack(side=RIGHT)
        tb.Button(action_bar, text="補印箱標（需填原因）", bootstyle="warning", command=self.reprint_current_label).pack(side=RIGHT, padx=8)
        self.pack_reset_button = tb.Button(action_bar, text="商品歸零", bootstyle="danger-outline", command=self.reset_current_packing_scan)
        self.pack_reset_button.pack(side=RIGHT, padx=8)
        self.pack_status = tb.Label(shipping_body, text="商品一次掃一件；整箱商品可輸入本次數量。全部掃描足額後會自動完成包裝並列印箱標。", bootstyle="secondary")
        self.pack_status.grid(row=3, column=0, sticky=W, pady=(10, 0))
        shipping_body.columnconfigure(0, weight=1)
        shipping_body.rowconfigure(0, weight=1)
        return frame

    def set_packing_actions(self, enabled):
        """完成／取消單載入後切成唯讀，UI 與資料層雙重防止重複出貨。"""
        state = "normal" if enabled else "disabled"
        for widget in (self.pack_item_barcode, self.pack_scan_qty, self.pack_scan_button, self.pack_complete_button, self.pack_reset_button):
            widget.configure(state=state)

    def load_order_for_packing(self):
        order_no = self.pack_order_no.get().strip().upper()
        if not order_no:
            return self.set_status(self.pack_status, "請先掃描或輸入出貨單號", "danger")
        try:
            header = self.db.start_packing(order_no)
            self.active_order_no = order_no
            self.shipping_read_only = header["status"] in ("已完成", "已取消")
            self.set_packing_actions(not self.shipping_read_only)
            self.refresh_packing_order()
            if self.shipping_read_only:
                self.set_status(self.pack_status, f"此出貨單狀態為「{header['status']}」；目前為唯讀查詢模式，禁止重複出貨。", "warning")
            else:
                self.set_status(self.pack_status, "已載入出貨單，請依出貨單儲位撿貨後逐項掃描商品", "success")
                self.pack_item_barcode.focus_set()
        except ValueError as error:
            self.active_order_no = None
            self.shipping_read_only = False
            self.set_packing_actions(True)
            self.clear_tree(self.pack_tree)
            self.pack_summary.configure(text="尚未讀取出貨單", bootstyle="secondary")
            self.set_status(self.pack_status, str(error), "danger")

    def refresh_packing_order(self):
        if not self.active_order_no:
            return
        header = self.db.order_header(self.active_order_no)
        if not header:
            return
        self.pack_summary.configure(
            text=(
                f"單號：{header['order_no']}    日期：{header['order_date']}    分店：{header['branch_code']} {header['branch_name']}"
                f"    物流：{header['carrier']}    狀態：{header['status']}"
            ),
            bootstyle="primary",
        )
        self.clear_tree(self.pack_tree)
        for line, allocations in self.db.order_lines(self.active_order_no):
            remaining = line["required_qty"] - line["scanned_qty"]
            done = remaining == 0
            self.pack_tree.insert(
                "",
                END,
                values=(
                    line["line_no"],
                    line["barcode"],
                    line["product_name"],
                    self.format_allocations(allocations),
                    line["required_qty"],
                    line["scanned_qty"],
                    remaining,
                    "已完成" if done else "待掃描",
                ),
                tags=("done",) if done else (),
            )

    def scan_packing_item(self):
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先掃描出貨單條碼", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢，禁止重複出貨。", "danger")
        barcode = Utils.normalize_barcode(self.pack_item_barcode.get())
        qty_text = self.pack_scan_qty.get().strip()
        if not Utils.valid_barcode(barcode):
            return self.set_status(self.pack_status, "商品條碼格式錯誤", "danger")
        if not qty_text.isdigit() or not 1 <= int(qty_text) <= 100000:
            return self.set_status(self.pack_status, "本次數量必須是正整數", "danger")
        try:
            name, scanned, required = self.db.scan_order_item(self.active_order_no, barcode, int(qty_text))
            self.refresh_packing_order()
            self.pack_item_barcode.delete(0, END)
            self.pack_scan_qty.delete(0, END)
            self.pack_scan_qty.insert(0, "1")
            self.set_status(self.pack_status, f"掃描成功：{name}（{scanned}/{required}）", "success")
            if self.packing_order_fully_scanned(self.active_order_no):
                self.auto_complete_packing()
            else:
                self.pack_item_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")

    def packing_order_fully_scanned(self, order_no):
        """判斷出貨單是否所有品項都已掃描足額，做為自動完成包裝的依據。"""
        lines = self.db.cursor.execute(
            "SELECT required_qty, scanned_qty FROM shipping_order_items WHERE order_no=?", (order_no,)
        ).fetchall()
        if not lines:
            return False
        return all(line["scanned_qty"] >= line["required_qty"] for line in lines)

    def auto_complete_packing(self):
        """V6.5：出貨掃描流程優化。全部商品掃描足額後，系統自動完成包裝、扣庫存並列印通運貼紙，
        不需再手動點擊「確認包裝成功」與「列印箱標」，減少倉庫作業的滑鼠操作與步驟。"""
        order_no = self.active_order_no
        try:
            self.db.complete_packing(order_no, self.current_user)
            self.db.log_operation(self.current_user, "完成出貨單", order_no, "全數掃描足額，系統自動完成")
            self.shipping_read_only = True
            self.set_packing_actions(False)
            self.refresh_packing_order()
            self.refresh_dashboard()
            self.refresh_inventory()
            self.print_label_document(order_no)
            self.set_status(
                self.pack_status,
                f"已全部掃描完成，出貨單 {order_no} 自動完成、扣庫存並開啟物流箱標列印頁面，可繼續掃描下一張出貨單。",
                "success",
            )
            self.reset_packing_screen_for_next_order()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"自動完成出貨失敗：{error}", "danger")

    def complete_current_packing(self):
        """手動完成包裝的備援路徑（正常情況下全數掃描足額會自動觸發，不需手動點擊）。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢，禁止重複出貨。", "danger")
        if not messagebox.askyesno("完成出貨單", f"確定要完成出貨單 {self.active_order_no} 並扣除庫存嗎？\n完成後不可修改。"):
            return
        try:
            self.db.complete_packing(self.active_order_no, self.current_user)
            self.db.log_operation(self.current_user, "完成出貨單", self.active_order_no)
            self.shipping_read_only = True
            self.set_packing_actions(False)
            self.refresh_packing_order()
            self.refresh_dashboard()
            self.refresh_inventory()
            self.print_label_document(self.active_order_no)
            self.set_status(self.pack_status, "包裝成功，庫存已扣除，並已開啟物流箱標列印頁面，可繼續掃描下一張出貨單。", "success")
            self.reset_packing_screen_for_next_order()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"出貨失敗：{error}", "danger")

    def reset_packing_screen_for_next_order(self):
        """V6.6：箱標列印後自動回到出貨作業介面，讓使用者可直接刷下一張出貨單條碼，形成連續出貨的循環。"""
        self.active_order_no = None
        self.shipping_read_only = False
        self.set_packing_actions(True)
        self.clear_tree(self.pack_tree)
        self.pack_summary.configure(text="尚未讀取出貨單", bootstyle="secondary")
        self.pack_order_no.delete(0, END)

        def refocus_app():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.after(200, lambda: self.root.attributes("-topmost", False))
                self.root.focus_force()
            except Exception:
                pass
            self.pack_order_no.focus_set()

        self.root.after(300, refocus_app)

    def reset_current_packing_scan(self):
        """V6.6：商品歸零，防止刷到一半誤刷多件，將此張出貨單已掃描數量全部重置。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢，無法歸零。", "danger")
        if not messagebox.askyesno(
            "商品歸零",
            f"確定要將出貨單 {self.active_order_no} 已掃描的商品數量全部歸零嗎？",
        ):
            return
        try:
            self.db.reset_packing_scan_progress(self.active_order_no)
            self.db.log_operation(self.current_user, "出貨商品歸零", self.active_order_no)
            self.refresh_packing_order()
            self.pack_item_barcode.delete(0, END)
            self.pack_scan_qty.delete(0, END)
            self.pack_scan_qty.insert(0, "1")
            self.set_status(self.pack_status, "已將此出貨單已掃描數量歸零，請重新掃描。", "warning")
            self.pack_item_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"歸零失敗：{error}", "danger")

    def reprint_current_label(self):
        """V6.5：補印獨立按鈕，需選擇原因後才會補印，並記錄補印人／時間／原因／次數。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        header = self.db.order_header(self.active_order_no)
        if header["status"] != "已完成":
            return self.set_status(self.pack_status, "請先完成包裝與扣庫存後，再補印物流箱標", "warning")
        reason = self.prompt_reprint_reason("補印箱標原因")
        if not reason:
            return
        try:
            self.print_label_document(self.active_order_no, reason=reason)
            self.set_status(self.pack_status, f"已補印內部物流箱標（原因：{reason}）", "success")
        except Exception as error:
            self.set_status(self.pack_status, f"補印失敗：{error}", "danger")

    # ---------- 盤點 ----------

    def build_counting_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "盤點作業", "輸入實際數量後直接平帳，系統會留下差異紀錄")
        card = tb.Labelframe(frame, text="盲盤資料", bootstyle="warning", padding=16)
        card.pack(fill=X)
        self.cnt_shelf = tb.Combobox(card, width=12, state="normal")
        self.cnt_shelf.configure(values=self.db.active_shelf_codes(include_special=True))
        self.cnt_barcode = tb.Entry(card, width=22)
        self.cnt_expiry = tb.Entry(card, width=16)
        self.cnt_qty = tb.Entry(card, width=10)
        fields = [
            ("儲位", self.cnt_shelf),
            ("商品條碼", self.cnt_barcode),
            ("效期", self.cnt_expiry),
            ("實際數量", self.cnt_qty),
        ]
        for column, (label, widget) in enumerate(fields):
            tb.Label(card, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=6)
        tb.Button(card, text="送出盤點", bootstyle="warning", command=self.process_counting).grid(row=0, column=8, padx=4)
        self.cnt_qty.bind("<Return>", lambda _event: self.process_counting())
        self.cnt_barcode.bind("<FocusOut>", self.refresh_counting_product_info)
        self.cnt_shelf.bind("<FocusOut>", self.refresh_counting_product_info)
        self.cnt_status = tb.Label(frame, text="無保存期限商品的效期欄可留白。", bootstyle="secondary")
        self.cnt_status.pack(anchor=W, pady=14)
        self.cnt_info_tree = self.build_product_info_panel(frame, "盤點商品確認")
        return frame

    def refresh_counting_product_info(self, _event=None):
        self.refresh_product_info_panel(self.cnt_info_tree, self.cnt_barcode.get(), self.cnt_shelf.get())

    def process_counting(self):
        shelf_code = self.cnt_shelf.get().strip().upper()
        barcode = Utils.normalize_barcode(self.cnt_barcode.get())
        expiry = self.cnt_expiry.get().strip()
        qty_text = self.cnt_qty.get().strip()
        self.refresh_product_info_panel(self.cnt_info_tree, barcode, shelf_code)
        if not shelf_code or not Utils.valid_barcode(barcode) or not qty_text.isdigit():
            return self.set_status(self.cnt_status, "請輸入正確的儲位、條碼與實際數量", "danger")
        shelf = self.db.shelf_by_code(shelf_code)
        product = self.db.product_by_barcode(barcode)
        if not shelf:
            return self.set_status(self.cnt_status, "儲位不存在", "danger")
        if not product:
            return self.set_status(self.cnt_status, "商品不存在，請先建立商品主檔", "danger")
        if product["expiry_required"]:
            valid, _expired, _days = Utils.validate_date(expiry)
            if not valid:
                return self.set_status(self.cnt_status, "效期格式錯誤，請輸入 YYYY-MM-DD", "danger")
        else:
            expiry = NO_EXPIRY_DATE
        real_qty = int(qty_text)
        if real_qty > 1000000:
            return self.set_status(self.cnt_status, "實際數量不可超過 1,000,000", "danger")

        existing = self.db.cursor.execute(
            """
            SELECT id, quantity FROM inventory
            WHERE shelf_code=? AND barcode=? AND expiry_date=?
            """,
            (shelf_code, barcode, expiry),
        ).fetchone()
        system_qty = existing["quantity"] if existing else 0
        diff = real_qty - system_qty
        if diff == 0:
            return self.set_status(self.cnt_status, "盤點無差異，不需平帳", "success")
        if not messagebox.askyesno(
            "庫存調整確認",
            f"儲位 {shelf_code} 商品 {barcode}\n系統數量 {system_qty} -> 實際數量 {real_qty}（差異 {diff}）\n確定要平帳嗎？",
        ):
            return self.set_status(self.cnt_status, "已取消本次庫存調整", "secondary")

        try:
            self.db.cursor.execute("BEGIN")
            if real_qty == 0 and existing:
                self.db.cursor.execute("DELETE FROM inventory WHERE id=?", (existing["id"],))
            elif existing:
                self.db.cursor.execute(
                    "UPDATE inventory SET quantity=? WHERE id=?", (real_qty, existing["id"])
                )
            elif real_qty > 0:
                self.db.cursor.execute(
                    """
                    INSERT INTO inventory (shelf_code, barcode, expiry_date, quantity)
                    VALUES (?,?,?,?)
                    """,
                    (shelf_code, barcode, expiry, real_qty),
                )
            self.db.log_transaction(
                "盤點調整",
                barcode,
                shelf_code,
                shelf_code,
                system_qty,
                real_qty,
                diff,
                expiry,
                self.current_user,
                reason=f"系統 {system_qty} -> 實際 {real_qty}",
            )
            self.db.conn.commit()
            self.db.log_operation(
                self.current_user, "庫存調整", note=f"{shelf_code} {barcode} 系統{system_qty}->實際{real_qty}（差異{diff}）",
            )
            self.set_status(self.cnt_status, f"平帳完成：系統 {system_qty} -> 實際 {real_qty}（差異 {diff}）", "warning")
            for widget in (self.cnt_barcode, self.cnt_expiry, self.cnt_qty):
                widget.delete(0, END)
            self.refresh_product_info_panel(self.cnt_info_tree, "", shelf_code)
            self.cnt_barcode.focus_set()
        except Exception as error:
            self.db.conn.rollback()
            self.set_status(self.cnt_status, f"盤點失敗：{error}", "danger")

    # ---------- 作業紀錄 ----------

    def build_history_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "作業紀錄", "保留進貨、上架、盤點與訂單出貨的完整異動資料")
        notebook = tb.Notebook(frame, bootstyle="secondary")
        notebook.pack(fill=BOTH, expand=True)
        tx_tab = tb.Frame(notebook, padding=10)
        op_tab = tb.Frame(notebook, padding=10)
        notebook.add(tx_tab, text=" 庫存異動紀錄 ")
        notebook.add(op_tab, text=" 操作紀錄 ")

        columns = ("time", "type", "order", "barcode", "from", "to", "before", "after", "change", "expiry", "user", "reason")
        self.history_tree = tb.Treeview(tx_tab, columns=columns, show="headings", bootstyle="secondary")
        headings = ("時間", "作業", "相關單號", "條碼", "來源", "去向", "前", "後", "異動", "效期", "人員", "備註")
        widths = (155, 100, 165, 145, 110, 130, 65, 65, 70, 110, 135, 230)
        self.setup_tree_columns(self.history_tree, columns, headings, widths, left_columns=("reason",))
        self.add_table_interactions(self.history_tree, tx_tab)
        self.add_tree_scrollbar(tx_tab, self.history_tree)

        # V6.1：操作紀錄頁籤，記錄登入、單據建立／完成／取消等關鍵操作。
        op_columns = ("time", "user", "action", "order", "note")
        self.op_log_tree = tb.Treeview(op_tab, columns=op_columns, show="headings", bootstyle="secondary")
        op_headings = ("時間", "使用者", "動作", "相關單號", "備註")
        op_widths = (160, 130, 130, 180, 320)
        self.setup_tree_columns(self.op_log_tree, op_columns, op_headings, op_widths, left_columns=("note",))
        self.add_table_interactions(self.op_log_tree, op_tab)
        self.add_tree_scrollbar(op_tab, self.op_log_tree)
        return frame

    def refresh_history(self):
        self.clear_tree(self.history_tree)
        rows = self.db.cursor.execute(
            """
            SELECT timestamp, tx_type, order_no, barcode, from_shelf, to_shelf,
                   before_qty, after_qty, change_qty, expiry_date, operator, reason
            FROM transactions ORDER BY id DESC LIMIT 300
            """
        ).fetchall()
        for row in rows:
            product = self.db.product_by_barcode(row["barcode"])
            expiry_required = bool(product["expiry_required"]) if product else True
            self.history_tree.insert(
                "",
                END,
                values=(
                    row["timestamp"], row["tx_type"], row["order_no"] or "-", row["barcode"],
                    row["from_shelf"] or "-", row["to_shelf"] or "-",
                    row["before_qty"] if row["before_qty"] is not None else "-",
                    row["after_qty"] if row["after_qty"] is not None else "-",
                    row["change_qty"], Utils.display_expiry(row["expiry_date"], expiry_required),
                    row["operator"], row["reason"] or "-",
                ),
            )
        self.clear_tree(self.op_log_tree)
        for row in self.db.recent_operation_logs():
            self.op_log_tree.insert(
                "", END,
                values=(row["timestamp"], row["operator"], row["action"], row["order_no"] or "-", row["note"] or "-"),
            )

    # ---------- 列印文件 ----------

    def format_allocations(self, allocations):
        if not allocations:
            return "尚未配貨"
        parts = []
        for allocation in allocations:
            expiry = Utils.display_expiry(allocation["expiry_date"])
            parts.append(f"{allocation['shelf_code']} / {expiry} x {allocation['allocated_qty']}")
        return "；".join(parts)

    def code39_svg(self, value, height=64):
        """產生可由支援 Code 39 的掃描器讀取的 SVG 條碼。"""
        patterns = {
            "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn",
            "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw",
            "8": "wnnwnnwnn", "9": "nnwwnnwnn", "A": "wnnnnwnnw", "B": "nnwnnwnnw",
            "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn",
            "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
            "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww",
            "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn",
            "S": "nnwnnnwwn", "T": "nnnnwnwwn", "U": "wwnnnnnnw", "V": "nwwnnnnnw",
            "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
            "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "*": "nwnnwnwnn",
            "$": "nwnwnwnnn", "/": "nwnwnnnwn", "+": "nwnnnwnwn", "%": "nnnwnwnwn",
        }
        encoded = f"*{value.upper()}*"
        if any(character not in patterns for character in encoded):
            raise ValueError("此單號含有 Code 39 不支援的字元")
        narrow, wide, gap, quiet = 2, 5, 2, 16
        x = quiet
        bars = []
        for character in encoded:
            for index, element in enumerate(patterns[character]):
                width = wide if element == "w" else narrow
                if index % 2 == 0:
                    bars.append(f'<rect x="{x}" y="0" width="{width}" height="{height}"/>')
                x += width
            x += gap
        total_width = x + quiet
        return f'<svg class="barcode" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_width} {height}" role="img">{"".join(bars)}</svg>'

    def write_print_file(self, filename, content):
        output_dir = Path(__file__).resolve().parent / "wms_printouts"
        output_dir.mkdir(exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        webbrowser.open(path.resolve().as_uri())
        return path

    def prompt_reprint_reason(self, title="補印原因"):
        """V6.5：補印獨立於正常列印，必須先選擇原因才會執行；取消則回傳 None。"""
        dialog = tb.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("360x280")
        dialog.transient(self.root)
        dialog.grab_set()
        body = tb.Frame(dialog, padding=16)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text="請選擇補印原因：", font=("Microsoft JhengHei", 11, "bold")).pack(anchor=W, pady=(0, 10))
        reason_var = tk.StringVar(value="標籤破損")
        for option in ("標籤破損", "印表機故障", "其他"):
            tb.Radiobutton(body, text=option, variable=reason_var, value=option).pack(anchor=W, pady=3)
        other_entry = tb.Entry(body, width=28)
        other_entry.pack(anchor=W, padx=24, pady=(2, 10))
        other_entry.configure(state="disabled")

        def sync_other_state(*_args):
            other_entry.configure(state="normal" if reason_var.get() == "其他" else "disabled")

        reason_var.trace_add("write", sync_other_state)

        result = {"reason": None}

        def confirm():
            reason = reason_var.get()
            if reason == "其他":
                detail = other_entry.get().strip()
                reason = f"其他：{detail}" if detail else "其他"
            result["reason"] = reason
            dialog.destroy()

        action_bar = tb.Frame(body)
        action_bar.pack(fill=X, pady=(10, 0), side="bottom")
        tb.Button(action_bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT, padx=(8, 0))
        tb.Button(action_bar, text="確認補印", bootstyle="warning", command=confirm).pack(side=RIGHT)
        dialog.wait_window()
        return result["reason"]

    def print_order_document(self, order_no, reason=None):
        header = self.db.order_header(order_no)
        if not header:
            raise ValueError("查無出貨單")
        print_count = self.db.mark_order_printed(order_no)
        document_mark = "正本" if print_count == 1 else f"補印第 {print_count - 1} 次"
        self.db.log_operation(
            self.current_user, "列印出貨單" if print_count == 1 else "補印出貨單",
            order_no, reason or ("正本首次列印" if print_count == 1 else "-"),
        )
        rows = []
        for line, allocations in self.db.order_lines(order_no):
            rows.append(
                "<tr>"
                f"<td>{line['line_no']}</td>"
                f"<td>{html.escape(line['barcode'])}</td>"
                f"<td>{html.escape(line['product_name'])}</td>"
                f"<td>{html.escape(self.format_allocations(allocations))}</td>"
                f"<td class=\"qty\">{line['required_qty']}</td>"
                "</tr>"
            )
        barcode_svg = self.code39_svg(order_no, height=72)
        content = f"""<!doctype html>
<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><title>{html.escape(order_no)} 出貨單</title>
<style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: \"Microsoft JhengHei\", Arial, sans-serif; color:#172033; font-size:12px; }}
.sheet {{ max-width: 190mm; margin:auto; }} .top {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #1f5eff; padding-bottom:12px; }}
h1 {{ margin:0; font-size:25px; }} .mark {{ border:1px solid #f0a000; color:#9a5d00; padding:5px 10px; font-weight:bold; }}
.barcode-wrap {{ text-align:center; margin:13px 0 9px; }} .barcode {{ width:285px; height:72px; }} .barcode-text {{ letter-spacing:1px; font-weight:bold; }}
.info {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 28px; margin:12px 0 16px; }} .info div {{ border-bottom:1px solid #d9dfeb; padding:5px 0; }}
table {{ width:100%; border-collapse:collapse; }} th {{ background:#eaf0ff; }} th,td {{ border:1px solid #aebbd0; padding:8px; text-align:left; vertical-align:top; }} td.qty {{ text-align:center; font-size:15px; font-weight:bold; }}
.footer {{ margin-top:20px; display:flex; justify-content:space-between; color:#56657f; }} @media print {{ .no-print {{ display:none; }} }}
</style></head><body><div class=\"sheet\">
<div class=\"top\"><div><h1>分店出貨單</h1><div>單據狀態：{html.escape(header['status'])}</div></div><div class=\"mark\">{document_mark}</div></div>
<div class=\"barcode-wrap\">{barcode_svg}<div class=\"barcode-text\">{html.escape(order_no)}</div></div>
<div class=\"info\">
<div><b>出貨日期：</b>{html.escape(header['order_date'])}</div><div><b>物流商：</b>{html.escape(header['carrier'])}</div>
<div><b>分店：</b>{html.escape(header['branch_code'])} {html.escape(header['branch_name'])}</div><div><b>託運單號：</b>{html.escape(header['tracking_no'] or '待補')}</div>
<div><b>地址：</b>{html.escape(header['address'] or '未填寫')}</div><div><b>聯絡人：</b>{html.escape(header['contact_name'] or '未填寫')} {html.escape(header['contact_phone'] or '')}</div>
<div><b>箱數：</b>{header['box_count']} 箱</div><div><b>建立人員：</b>{html.escape(header['created_by'])}</div>
</div>
<table><thead><tr><th>#</th><th>商品條碼</th><th>商品名稱</th><th>建議儲位／效期批次</th><th>數量</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class=\"footer\"><span>請依建議儲位撿貨，包裝時須掃描此單號及所有商品。</span><span>列印時間：{Utils.now_text()}</span></div>
</div></body></html>"""
        filename = f"{order_no}_出貨單_{print_count}.html"
        self.write_print_file(filename, content)

    def print_receiving_document(self, order_no, reason=None):
        header = self.db.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無進貨單")
        print_count = self.db.mark_receiving_order_printed(order_no)
        document_mark = "正本" if print_count == 1 else f"補印第 {print_count - 1} 次"
        self.db.log_operation(
            self.current_user, "列印進貨單" if print_count == 1 else "補印進貨單",
            order_no, reason or ("正本首次列印" if print_count == 1 else "-"),
        )
        rows = []
        for line in self.db.receiving_order_lines(order_no):
            rows.append(
                "<tr>"
                f"<td>{line['line_no']}</td>"
                f"<td>{html.escape(line['barcode'])}</td>"
                f"<td>{html.escape(line['product_name'])}</td>"
                f"<td class=\"qty\">{line['required_qty']}</td>"
                "</tr>"
            )
        barcode_svg = self.code39_svg(order_no, height=72)
        content = f"""<!doctype html>
<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><title>{html.escape(order_no)} 進貨單</title>
<style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: \"Microsoft JhengHei\", Arial, sans-serif; color:#172033; font-size:12px; }}
.sheet {{ max-width: 190mm; margin:auto; }} .top {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #1f5eff; padding-bottom:12px; }}
h1 {{ margin:0; font-size:25px; }} .mark {{ border:1px solid #f0a000; color:#9a5d00; padding:5px 10px; font-weight:bold; }}
.barcode-wrap {{ text-align:center; margin:13px 0 9px; }} .barcode {{ width:285px; height:72px; }} .barcode-text {{ letter-spacing:1px; font-weight:bold; }}
.info {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 28px; margin:12px 0 16px; }} .info div {{ border-bottom:1px solid #d9dfeb; padding:5px 0; }}
table {{ width:100%; border-collapse:collapse; }} th {{ background:#eaf0ff; }} th,td {{ border:1px solid #aebbd0; padding:8px; text-align:left; vertical-align:top; }} td.qty {{ text-align:center; font-size:15px; font-weight:bold; }}
.footer {{ margin-top:20px; display:flex; justify-content:space-between; color:#56657f; }} @media print {{ .no-print {{ display:none; }} }}
</style></head><body><div class=\"sheet\">
<div class=\"top\"><div><h1>供應商進貨單</h1><div>單據狀態：{html.escape(header['status'])}</div></div><div class=\"mark\">{document_mark}</div></div>
<div class=\"barcode-wrap\">{barcode_svg}<div class=\"barcode-text\">{html.escape(order_no)}</div></div>
<div class=\"info\">
<div><b>進貨日期：</b>{html.escape(header['order_date'])}</div><div><b>廠商：</b>{html.escape(header['supplier_name'])}</div>
<div><b>建立人員：</b>{html.escape(header['created_by'])}</div><div><b>建立時間：</b>{html.escape(header['created_at'])}</div>
<div><b>備註：</b>{html.escape(header['note'] or '—')}</div>
</div>
<table><thead><tr><th>#</th><th>商品條碼</th><th>商品名稱</th><th>預計數量</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class=\"footer\"><span>請依此單核對到貨商品，驗收時須掃描此單號及所有商品。</span><span>列印時間：{Utils.now_text()}</span></div>
</div></body></html>"""
        filename = f"{order_no}_進貨單_{print_count}.html"
        self.write_print_file(filename, content)

    def print_return_document(self, return_no):
        header = self.db.return_order_header(return_no)
        if not header:
            raise ValueError("查無退貨單")
        receiving = self.db.receiving_order_header(header["receiving_order_no"])
        supplier = receiving["supplier_name"] if receiving else "未指定"
        evidence_html = "<p class=\"empty\">未附異常照片</p>"
        evidence_path = Path(header["evidence_path"]) if header["evidence_path"] else None
        if evidence_path and evidence_path.is_file():
            evidence_html = (
                f'<img class="evidence" src="{html.escape(evidence_path.resolve().as_uri(), quote=True)}" '
                'alt="商品異常證據照片">'
            )
        barcode_svg = self.code39_svg(return_no, height=62)
        content = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>{html.escape(return_no)} 退貨表</title>
<style>
@page {{ size:A4; margin:12mm; }}
body {{ font-family:"Microsoft JhengHei", Arial, sans-serif; color:#172033; font-size:12px; }}
.sheet {{ max-width:190mm; margin:auto; }} .top {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #c92a2a; padding-bottom:10px; }}
h1 {{ margin:0; font-size:26px; }} .status {{ color:#9d1c1c; border:1px solid #c92a2a; padding:5px 10px; font-weight:bold; }}
.barcode-wrap {{ text-align:center; margin:12px 0; }} .barcode {{ width:270px; height:62px; }}
.info {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 24px; margin:10px 0 15px; }} .info div {{ border-bottom:1px solid #d9dfeb; padding:6px 0; }}
table {{ width:100%; border-collapse:collapse; margin-top:10px; }} th {{ background:#fff0f0; }} th,td {{ border:1px solid #aebbd0; padding:9px; text-align:left; }} td.qty {{ text-align:center; font-size:16px; font-weight:bold; }}
.evidence-box {{ border:1px solid #aebbd0; margin-top:16px; padding:10px; }} .evidence {{ max-width:100%; max-height:120mm; display:block; margin:8px auto 0; }} .empty {{ color:#56657f; }}
.footer {{ margin-top:20px; display:flex; justify-content:space-between; color:#56657f; }}
</style></head><body><div class="sheet">
<div class="top"><div><h1>供應商退貨表</h1><div>商品異常退貨／還貨證明</div></div><div class="status">{html.escape(header['status'])}</div></div>
<div class="barcode-wrap">{barcode_svg}<div><b>{html.escape(return_no)}</b></div></div>
<div class="info">
<div><b>退貨單號：</b>{html.escape(return_no)}</div><div><b>原進貨單號：</b>{html.escape(header['receiving_order_no'])}</div>
<div><b>供應商：</b>{html.escape(supplier)}</div><div><b>建立時間：</b>{html.escape(header['created_at'])}</div>
<div><b>建立人員：</b>{html.escape(header['created_by'])}</div><div><b>退貨原因：</b>{html.escape(header['return_reason'])}</div>
</div>
<table><thead><tr><th>商品條碼</th><th>商品名稱</th><th>退貨數量</th><th>異常原因</th></tr></thead>
<tbody><tr><td>{html.escape(header['barcode'])}</td><td>{html.escape(header['product_name'])}</td><td class="qty">{header['return_qty']}</td><td>{html.escape(header['return_reason'])}</td></tr></tbody></table>
<div class="evidence-box"><b>商品異常證據照片</b>{evidence_html}</div>
<div class="evidence-box"><b>備註：</b>{html.escape(header['note'] or '—')}</div>
<div class="footer"><span>此表供供應商核對退貨商品與異常證據使用。</span><span>列印時間：{Utils.now_text()}</span></div>
</div></body></html>"""
        self.write_print_file(f"{return_no}_退貨表.html", content)

    def print_label_document(self, order_no, reason=None):
        header = self.db.order_header(order_no)
        if not header:
            raise ValueError("查無出貨單")
        if header["status"] != "已完成":
            raise ValueError("只有完成包裝的出貨單可以列印物流箱標")
        labels = []
        for box_number in range(1, header["box_count"] + 1):
            label_code = f"{order_no}-B{box_number}"
            barcode_svg = self.code39_svg(label_code, height=72)
            labels.append(
                f"""<section class=\"label\">
<div class=\"label-top\"><h1>物流箱標</h1><div>第 {box_number} 箱／共 {header['box_count']} 箱</div></div>
<div class=\"branch\">{html.escape(header['branch_code'])} {html.escape(header['branch_name'])}</div>
<div class=\"address\">{html.escape(header['address'] or '地址未填寫')}</div>
<div class=\"grid\"><div><b>物流商</b><br>{html.escape(header['carrier'])}</div><div><b>託運單號</b><br>{html.escape(header['tracking_no'] or '待補')}</div><div><b>出貨日期</b><br>{html.escape(header['order_date'])}</div><div><b>出貨單號</b><br>{html.escape(order_no)}</div></div>
<div class=\"barcode-wrap\">{barcode_svg}<div>{html.escape(label_code)}</div></div>
<div class=\"note\">內部箱標。官方蝦皮／嘉里大榮面單需由物流後台或 API 取得。</div>
</section>"""
            )
        content = f"""<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><title>{html.escape(order_no)} 物流箱標</title>
<style>
@page {{ size: 100mm 150mm; margin:5mm; }} body {{ margin:0; font-family:\"Microsoft JhengHei\", Arial, sans-serif; color:#172033; }}
.label {{ width:90mm; min-height:138mm; border:2px solid #172033; box-sizing:border-box; padding:6mm; page-break-after:always; }}
.label:last-child {{ page-break-after:auto; }} .label-top {{ display:flex; justify-content:space-between; align-items:baseline; border-bottom:2px solid #1f5eff; }} h1 {{ margin:0 0 4mm; font-size:22px; }} .branch {{ font-size:19px; font-weight:bold; margin-top:5mm; }} .address {{ margin-top:3mm; min-height:11mm; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:3mm; margin-top:5mm; }} .grid div {{ border:1px solid #aebbd0; padding:3mm; min-height:10mm; }} .barcode-wrap {{ text-align:center; margin-top:7mm; font-weight:bold; }} .barcode {{ width:74mm; height:72px; }} .note {{ margin-top:5mm; font-size:10px; color:#56657f; }}
</style></head><body>{''.join(labels)}</body></html>"""
        label_print_count = self.db.mark_label_printed(order_no)
        self.db.log_operation(
            self.current_user, "列印箱標" if label_print_count == 1 else "補印箱標",
            order_no, reason or ("正本首次列印" if label_print_count == 1 else "-"),
        )
        self.write_print_file(f"{order_no}_物流箱標.html", content)

    # ---------- Treeview 滾動條 ----------

    def add_tree_scrollbar(self, parent, tree):
        """Treeview 與垂直捲軸必須建立在同一個父容器。"""
        scrollbar = tb.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)


if __name__ == "__main__":
    app = tb.Window(themename="flatly")
    WMSApp(app)
    app.mainloop()