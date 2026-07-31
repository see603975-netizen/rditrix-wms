"""CoreDB：SQLite 連線、schema 建置與升級、種子資料。

各領域資料操作拆分於同套件的 *_db.py 模組，最後由 database.py 組裝成 DBManager。
"""
from utils.constants import *
from utils.helpers import Utils


class CoreDB:
    """連線與 schema 管理；既有 v3 資料庫可直接升級（CREATE IF NOT EXISTS 不會覆蓋舊資料）。"""

    def __init__(self, db_name="wms_system_v3.db"):
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self.init_db()
        self.seed_data()

    # ---------- schema ----------

    def init_db(self):
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
        self.ensure_column("receiving_orders", "cancelled_at", "TEXT")
        self.ensure_column("receiving_orders", "cancelled_by", "TEXT")
        self.ensure_column("receiving_orders", "cancel_reason", "TEXT")
        self.ensure_column("receiving_orders", "print_count", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("receiving_orders", "last_printed_at", "TEXT")
        self.ensure_column("shipping_orders", "last_printed_at", "TEXT")
        self.ensure_column("shipping_orders", "cancelled_by", "TEXT")
        self.ensure_column("shipping_orders", "label_print_count", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("shipping_orders", "label_last_printed_at", "TEXT")
        self.cursor.execute(
            "UPDATE shipping_orders SET label_print_count=1 WHERE label_printed=1 AND label_print_count=0"
        )
        # V6.9：商品最大單次進貨量（0 = 不限制），由防呆設定啟用。
        self.ensure_column("products", "max_receiving_qty", "INTEGER NOT NULL DEFAULT 0")

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
        # Buyer returns are deliberately independent from supplier return_orders.
        # A buyer return first enters QC and can only later be restocked or scrapped.
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS buyer_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                return_no TEXT NOT NULL UNIQUE,
                barcode TEXT NOT NULL,
                product_name TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                note TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING_QC',
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                processed_at TEXT,
                processed_by TEXT,
                target_shelf_code TEXT,
                scrap_hold_id INTEGER,
                FOREIGN KEY(barcode) REFERENCES products(barcode),
                FOREIGN KEY(target_shelf_code) REFERENCES shelves(shelf_code)
            )
            """
        )
        # Stock is moved to Scrap immediately but is not written off for three days.
        # This provides a safe cancellation window for accidental moves.
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scrap_holds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                source_shelf_code TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                moved_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                moved_by TEXT NOT NULL,
                cancelled_at TEXT,
                cancelled_by TEXT,
                written_off_at TEXT,
                written_off_by TEXT,
                FOREIGN KEY(barcode) REFERENCES products(barcode),
                FOREIGN KEY(source_shelf_code) REFERENCES shelves(shelf_code)
            )
            """
        )
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_buyer_returns_status ON buyer_returns(status, created_at DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scrap_holds_due ON scrap_holds(status, due_at)")

        # 操作紀錄資料表，記錄登入、單據建立／完成／取消等關鍵操作，供全程追蹤。
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
        # 儲位階層化（區域-貨架-層位，如 A01-03）。既有欄位保留，新增結構化欄位與管理狀態。
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

        # ---------- V6.9 新增資料表 ----------

        # 帳號與角色（OPERATOR / SUPERVISOR / ADMIN）；密碼僅存 PBKDF2 雜湊。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'OPERATOR',
                active INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT
            )
            """
        )
        # 登入日誌：成功與失敗都記錄；連續失敗鎖定也會標記警告。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                success INTEGER NOT NULL,
                source TEXT,
                note TEXT
            )
            """
        )
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_logs ON login_logs(id DESC)")
        # 防暴力破解的鎖定狀態表（以帳號字串為鍵，即使帳號不存在也會累計）。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS login_lockouts (
                username TEXT PRIMARY KEY,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                warned INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # 系統／防呆設定（key-value，值一律存文字）。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # 動態盤點（Cycle Count）：盤點單主檔與明細。
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_count_sessions (
                session_no TEXT PRIMARY KEY,
                period_type TEXT NOT NULL,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '進行中',
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                completed_at TEXT,
                completed_by TEXT,
                print_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_count_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_no TEXT NOT NULL,
                shelf_code TEXT NOT NULL,
                barcode TEXT NOT NULL,
                product_name TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                system_qty INTEGER NOT NULL,
                counted_qty INTEGER,
                is_exception INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                FOREIGN KEY(session_no) REFERENCES cycle_count_sessions(session_no) ON DELETE CASCADE,
                UNIQUE(session_no, shelf_code, barcode, expiry_date)
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_cc_items ON cycle_count_items(session_no, shelf_code)"
        )
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

    # ---------- 種子資料 ----------

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
            """
            INSERT OR IGNORE INTO products
            (barcode, sku, name, category, safety_stock, expiry_required)
            VALUES (?,?,?,?,?,?)
            """,
            products,
        )

        now = Utils.now_text()
        shelves = [
            ("未上架", "Staging", None, None, None, 1),
            ("品檢區", "QC", None, None, None, 1),
            ("報廢區", "Scrap", None, None, None, 1),
            ("出貨暫存", "Outbound", None, None, None, 1),
        ]
        # 物理儲位採「區域-貨架-層位」階層式格式，例如 A01-03 = A區 01號貨架 第3層。
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

        # 預設系統管理員帳號（沿用 V6.8 的 PO001／123123，首次登入後請立即修改密碼）。
        has_admin = self.cursor.execute(
            "SELECT 1 FROM users WHERE role='ADMIN' AND active=1 LIMIT 1"
        ).fetchone()
        if not has_admin:
            self.cursor.execute(
                """
                INSERT OR IGNORE INTO users
                (username, password_hash, display_name, role, active, created_at, created_by)
                VALUES (?,?,?,?,1,?,?)
                """,
                ("PO001", Utils.hash_password("123123"), "系統管理員", ROLE_ADMIN, now, "SYSTEM"),
            )

        # 預設防呆／系統設定值（僅補缺，不覆蓋既有設定）。
        self.cursor.executemany(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?,?)",
            list(SETTING_DEFAULTS.items()),
        )
        self.conn.commit()

    # ---------- 共用 ----------

    def _generate_sequential_no(self, table, column, prefix_code):
        """共用：依「代碼-日期-流水號」格式產生單號，各類單據格式一致。"""
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

    def close(self):
        self.conn.close()
