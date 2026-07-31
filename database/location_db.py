"""LocationDBMixin：儲位管理（區域-貨架-層位）。"""
from utils.constants import *
from utils.helpers import Utils


class LocationDBMixin:
    def shelf_by_code(self, shelf_code):
        return self.cursor.execute(
            "SELECT * FROM shelves WHERE shelf_code=?", (shelf_code,)
        ).fetchone()

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

    def all_shelf_codes(self):
        return [
            row["shelf_code"]
            for row in self.cursor.execute("SELECT shelf_code FROM shelves ORDER BY shelf_code").fetchall()
        ]
