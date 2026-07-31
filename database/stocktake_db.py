"""StocktakeDBMixin：動態盤點（Cycle Count）。

流程：
1. 建立盤點單（當日／當週／當月）：自動撈取期間內有進貨、出貨、上架或調撥異動的儲位，
   並以目前庫存快照為盤點明細。
2. 列印盤點單（按儲位排序），現場人員走動手寫核對。
3. 輸入結果：掃描儲位＋條碼輸入實盤數量；正常品可「一鍵全部正常」，
   只有異常品需勾選並輸入實際數量。
4. 完成盤點：差異品項自動平帳（需倉庫主管以上權限，由 UI 與服務層把關）。
"""
from utils.constants import *
from utils.helpers import Utils


class StocktakeDBMixin:
    PERIOD_TYPES = ("當日", "當週", "當月")

    def _cycle_period_range(self, period_type):
        today = date.today()
        if period_type == "當日":
            return today.isoformat(), today.isoformat()
        if period_type == "當週":
            monday = today - timedelta(days=today.weekday())
            return monday.isoformat(), today.isoformat()
        if period_type == "當月":
            return today.replace(day=1).isoformat(), today.isoformat()
        raise ValueError("盤點期間請選擇 當日／當週／當月")

    def cycle_count_moved_shelves(self, date_from, date_to):
        """期間內有異動（進貨、出貨、上架、調撥、盤點等）的實體儲位清單。"""
        rows = self.cursor.execute(
            """
            SELECT DISTINCT shelf FROM (
                SELECT from_shelf AS shelf FROM transactions
                WHERE timestamp >= ? AND timestamp <= ? AND from_shelf IS NOT NULL
                UNION
                SELECT to_shelf AS shelf FROM transactions
                WHERE timestamp >= ? AND timestamp <= ? AND to_shelf IS NOT NULL
            )
            JOIN shelves s ON s.shelf_code = shelf
            WHERE s.is_special = 0
            ORDER BY shelf
            """,
            (f"{date_from} 00:00:00", f"{date_to} 23:59:59",
             f"{date_from} 00:00:00", f"{date_to} 23:59:59"),
        ).fetchall()
        return [row["shelf"] for row in rows]

    def create_cycle_count_session(self, period_type, operator):
        """建立動態盤點單；快照異動儲位目前的庫存明細。回傳 (session_no, 明細數)。"""
        if period_type not in self.PERIOD_TYPES:
            raise ValueError("盤點期間請選擇 當日／當週／當月")
        date_from, date_to = self._cycle_period_range(period_type)
        shelves = self.cycle_count_moved_shelves(date_from, date_to)
        if not shelves:
            raise ValueError(f"{period_type}（{date_from} ~ {date_to}）沒有任何儲位異動，無需盤點")
        placeholders = ",".join("?" * len(shelves))
        snapshot = self.cursor.execute(
            f"""
            SELECT i.shelf_code, i.barcode, p.name AS product_name, i.expiry_date, i.quantity
            FROM inventory i JOIN products p ON p.barcode=i.barcode
            WHERE i.shelf_code IN ({placeholders})
            ORDER BY i.shelf_code, p.name, i.expiry_date
            """,
            shelves,
        ).fetchall()
        session_no = self._generate_sequential_no("cycle_count_sessions", "session_no", "CC")
        try:
            self.cursor.execute("BEGIN")
            self.cursor.execute(
                """
                INSERT INTO cycle_count_sessions
                (session_no, period_type, date_from, date_to, created_at, created_by)
                VALUES (?,?,?,?,?,?)
                """,
                (session_no, period_type, date_from, date_to, Utils.now_text(), operator),
            )
            for row in snapshot:
                self.cursor.execute(
                    """
                    INSERT INTO cycle_count_items
                    (session_no, shelf_code, barcode, product_name, expiry_date, system_qty)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (session_no, row["shelf_code"], row["barcode"], row["product_name"],
                     row["expiry_date"], row["quantity"]),
                )
            # 期間有異動但目前帳上為 0 的儲位也要盤（確認真的是空的）——
            # 快照沒有明細的儲位補一筆「空儲位確認」列。
            snapshot_shelves = {row["shelf_code"] for row in snapshot}
            for shelf_code in shelves:
                if shelf_code not in snapshot_shelves:
                    self.cursor.execute(
                        """
                        INSERT INTO cycle_count_items
                        (session_no, shelf_code, barcode, product_name, expiry_date, system_qty)
                        VALUES (?,?,?,?,?,0)
                        """,
                        (session_no, shelf_code, "-", "（空儲位確認）", NO_EXPIRY_DATE),
                    )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "建立動態盤點單", session_no,
                           f"{period_type}（{date_from} ~ {date_to}），{len(shelves)} 個儲位")
        return session_no, len(shelves)

    def cycle_count_sessions(self, limit=100):
        return self.cursor.execute(
            """
            SELECT s.*, COUNT(i.id) AS item_count,
                   SUM(CASE WHEN i.counted_qty IS NOT NULL THEN 1 ELSE 0 END) AS counted_count,
                   SUM(CASE WHEN i.counted_qty IS NOT NULL AND i.counted_qty <> i.system_qty THEN 1 ELSE 0 END) AS diff_count
            FROM cycle_count_sessions s
            LEFT JOIN cycle_count_items i ON i.session_no=s.session_no
            GROUP BY s.session_no
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def cycle_count_session(self, session_no):
        return self.cursor.execute(
            "SELECT * FROM cycle_count_sessions WHERE session_no=?", (session_no,)
        ).fetchone()

    def cycle_count_items(self, session_no):
        return self.cursor.execute(
            """
            SELECT * FROM cycle_count_items WHERE session_no=?
            ORDER BY shelf_code, product_name, expiry_date
            """,
            (session_no,),
        ).fetchall()

    def _open_cycle_session(self, session_no):
        session = self.cycle_count_session(session_no)
        if not session:
            raise ValueError("查無此盤點單")
        if session["status"] != "進行中":
            raise ValueError("此盤點單已完成，只能查詢")
        return session

    def record_cycle_count(self, session_no, shelf_code, barcode, counted_qty,
                           expiry_date=None, is_exception=False, note=""):
        """輸入單筆實盤數量（掃描儲位＋商品條碼）。expiry_date 省略時，
        該儲位同品項僅一批才可自動對應。"""
        self._open_cycle_session(session_no)
        shelf_code = (shelf_code or "").strip().upper()
        barcode = Utils.normalize_barcode(barcode or "")
        if not isinstance(counted_qty, int) or counted_qty < 0 or counted_qty > 1000000:
            raise ValueError("實盤數量必須是 0 至 1,000,000 的整數")
        params = [session_no, shelf_code, barcode]
        query = "SELECT * FROM cycle_count_items WHERE session_no=? AND shelf_code=? AND barcode=?"
        if expiry_date:
            query += " AND expiry_date=?"
            params.append(expiry_date)
        rows = self.cursor.execute(query, params).fetchall()
        if not rows:
            raise ValueError("此儲位＋商品不在本盤點單內；若為盤點外新發現，請改用管理員盤點平帳")
        if len(rows) > 1:
            raise ValueError("此儲位同商品有多個效期批次，請一併輸入效期")
        item = rows[0]
        self.cursor.execute(
            """
            UPDATE cycle_count_items
            SET counted_qty=?, is_exception=?, note=?
            WHERE id=?
            """,
            (counted_qty, int(bool(is_exception) or counted_qty != item["system_qty"]),
             (note or "").strip(), item["id"]),
        )
        self.conn.commit()
        return item["system_qty"], counted_qty - item["system_qty"]

    def confirm_cycle_count_all_normal(self, session_no, operator):
        """一鍵確認：所有尚未輸入實盤的品項視為帳實相符（counted = system）。"""
        self._open_cycle_session(session_no)
        updated = self.cursor.execute(
            """
            UPDATE cycle_count_items SET counted_qty=system_qty
            WHERE session_no=? AND counted_qty IS NULL
            """,
            (session_no,),
        ).rowcount
        self.conn.commit()
        self.log_operation(operator, "動態盤點一鍵正常", session_no, f"{updated} 筆視為帳實相符")
        return updated

    def complete_cycle_count(self, session_no, operator):
        """完成盤點：所有品項須已輸入實盤；差異品項自動平帳並留下盤點調整紀錄。"""
        self._open_cycle_session(session_no)
        pending = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM cycle_count_items WHERE session_no=? AND counted_qty IS NULL",
            (session_no,),
        ).fetchone()["cnt"]
        if pending:
            raise ValueError(
                f"尚有 {pending} 筆未輸入實盤數量；正常品可先按「一鍵全部正常」，異常品逐筆輸入"
            )
        diff_items = self.cursor.execute(
            """
            SELECT * FROM cycle_count_items
            WHERE session_no=? AND counted_qty <> system_qty AND barcode <> '-'
            """,
            (session_no,),
        ).fetchall()
        adjusted = 0
        for item in diff_items:
            self.adjust_inventory_count(
                item["shelf_code"], item["barcode"], item["expiry_date"],
                item["counted_qty"], operator,
                tx_type="動態盤點調整",
                reason=f"盤點單 {session_no}：系統 {item['system_qty']} -> 實盤 {item['counted_qty']}",
            )
            adjusted += 1
        self.cursor.execute(
            """
            UPDATE cycle_count_sessions
            SET status='已完成', completed_at=?, completed_by=?
            WHERE session_no=?
            """,
            (Utils.now_text(), operator, session_no),
        )
        self.conn.commit()
        self.log_operation(operator, "完成動態盤點", session_no, f"平帳 {adjusted} 筆差異")
        return adjusted

    def mark_cycle_count_printed(self, session_no):
        self.cursor.execute(
            "UPDATE cycle_count_sessions SET print_count=print_count+1 WHERE session_no=?",
            (session_no,),
        )
        self.conn.commit()
        return self.cycle_count_session(session_no)["print_count"]
