"""InventoryDBMixin：庫存批次操作、上架、調撥、盤點平帳、總覽與報表查詢。"""
from utils.constants import *
from utils.helpers import Utils


class InventoryDBMixin:
    # ---------- 基本批次操作 ----------

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

    def _resolve_batch_expiry(self, shelf_code, barcode, expiry_date):
        """效期留白時自動對應正確批次（報廢／調撥共用防呆）。

        無效期商品 → 一律使用內部無效期代碼；
        有效期商品且該儲位僅一個批次 → 自動帶入該批效期；
        多個批次 → 要求明確輸入，避免報錯批。"""
        expiry_date = (expiry_date or "").strip()
        if expiry_date:
            return expiry_date
        product = self.product_by_barcode(barcode)
        if product is not None and not product["expiry_required"]:
            return NO_EXPIRY_DATE
        batches = self.cursor.execute(
            "SELECT DISTINCT expiry_date FROM inventory WHERE shelf_code=? AND barcode=?",
            (shelf_code, barcode),
        ).fetchall()
        if len(batches) == 1:
            return batches[0]["expiry_date"]
        if not batches:
            raise ValueError(f"儲位 {shelf_code} 沒有此商品的庫存")
        raise ValueError("此儲位同商品有多個效期批次，請輸入要處理的批次效期")

    def _inventory_batch(self, shelf_code, barcode, expiry_date):
        return self.cursor.execute(
            "SELECT id, quantity FROM inventory WHERE shelf_code=? AND barcode=? AND expiry_date=?",
            (shelf_code, barcode, expiry_date),
        ).fetchone()

    def _move_batch(self, source_shelf, target_shelf, barcode, expiry_date, quantity, operator, tx_type, reason):
        """Move one exact batch inside the current transaction with no implicit commit."""
        batch = self._inventory_batch(source_shelf, barcode, expiry_date)
        if not batch or batch["quantity"] < quantity:
            raise ValueError(
                f"儲位 {source_shelf} 的批次（效期 {Utils.display_expiry(expiry_date)}）庫存不足"
            )
        before_qty = batch["quantity"]
        after_qty = self.deduct_inventory(batch["id"], before_qty, quantity)
        self.add_inventory(target_shelf, barcode, expiry_date, quantity)
        self.log_transaction(tx_type, barcode, source_shelf, target_shelf, before_qty, after_qty,
                             -quantity, expiry_date, operator, reason=reason)

    # ---------- 上架與調撥 ----------

    def staging_batches(self, barcode=None, only_valid=False):
        """未上架區批次；only_valid=True 時排除已過期批次（供上架 FEFO 使用）。"""
        query = """
            SELECT i.id, i.barcode, p.name, i.expiry_date, i.quantity, p.expiry_required
            FROM inventory i
            JOIN products p ON p.barcode=i.barcode
            WHERE i.shelf_code=?
        """
        params = [STAGING_SHELF]
        if barcode:
            query += " AND i.barcode=?"
            params.append(barcode)
        if only_valid:
            query += " AND (i.expiry_date='' OR i.expiry_date >= ?)"
            params.append(Utils.today_text())
        query += " ORDER BY CASE WHEN i.expiry_date='' THEN '9999-12-31' ELSE i.expiry_date END, p.name"
        return self.cursor.execute(query, params).fetchall()

    def putaway(self, barcode, shelf_code, quantity, operator):
        """由未上架區依 FEFO 取出批次移到目標儲位；回傳各批次搬移摘要文字。"""
        target_shelf = self.shelf_by_code(shelf_code)
        if not target_shelf:
            raise ValueError("目標儲位不存在")
        if target_shelf["zone"] in SPECIAL_ZONES:
            raise ValueError("目標儲位為特殊區，不能上架")
        if target_shelf["status"] != "啟用":
            raise ValueError("目標儲位已停用，不能上架")
        batches = self.staging_batches(barcode, only_valid=True)
        if sum(batch["quantity"] for batch in batches) < quantity:
            raise ValueError("未上架區可用庫存不足，或商品已過期")
        moved = []
        try:
            self.cursor.execute("BEGIN")
            remaining = quantity
            for batch in batches:
                if remaining == 0:
                    break
                move_qty = min(remaining, batch["quantity"])
                after_source = self.deduct_inventory(batch["id"], batch["quantity"], move_qty)
                before_target, after_target = self.add_inventory(
                    shelf_code, barcode, batch["expiry_date"], move_qty
                )
                self.log_transaction(
                    "上架", barcode, STAGING_SHELF, shelf_code,
                    batch["quantity"], after_source, -move_qty, batch["expiry_date"], operator,
                    reason=f"目標儲位原數量 {before_target}，上架後 {after_target}",
                )
                remaining -= move_qty
                moved.append(f"{Utils.display_expiry(batch['expiry_date'])} x {move_qty}")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return moved

    def transfer_stock(self, source_shelf, target_shelf, barcode, expiry_date, quantity, operator):
        """儲位間庫存調撥（倉庫主管以上）；來源與目標皆須為啟用中的一般儲位。"""
        source_shelf = (source_shelf or "").strip().upper()
        target_shelf = (target_shelf or "").strip().upper()
        barcode = Utils.normalize_barcode(barcode or "")
        if source_shelf == target_shelf:
            raise ValueError("來源與目標儲位不可相同")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("調撥數量必須是正整數")
        for code, label in ((source_shelf, "來源"), (target_shelf, "目標")):
            shelf = self.shelf_by_code(code)
            if not shelf:
                raise ValueError(f"{label}儲位不存在")
            if shelf["is_special"]:
                raise ValueError(f"{label}儲位為特殊區，調撥請改走上架／報廢／品檢流程")
            if shelf["status"] != "啟用":
                raise ValueError(f"{label}儲位已停用")
        if not self.product_by_barcode(barcode):
            raise ValueError("商品主檔不存在")
        expiry_date = self._resolve_batch_expiry(source_shelf, barcode, expiry_date)
        try:
            self.cursor.execute("BEGIN")
            self._move_batch(source_shelf, target_shelf, barcode, expiry_date, quantity,
                             operator, "儲位調撥", f"{source_shelf} → {target_shelf}")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "儲位調撥", "",
                           f"{barcode} x {quantity}：{source_shelf} → {target_shelf}")

    # ---------- 盤點平帳（庫存強制修改） ----------

    def adjust_inventory_count(self, shelf_code, barcode, expiry_date, real_qty, operator,
                               tx_type="盤點調整", reason=None):
        """把指定批次的系統數量直接調整為實盤數量；回傳（系統原數量, 差異）。"""
        existing = self.cursor.execute(
            "SELECT id, quantity FROM inventory WHERE shelf_code=? AND barcode=? AND expiry_date=?",
            (shelf_code, barcode, expiry_date),
        ).fetchone()
        system_qty = existing["quantity"] if existing else 0
        diff = real_qty - system_qty
        if diff == 0:
            return system_qty, 0
        try:
            self.cursor.execute("BEGIN")
            if real_qty == 0 and existing:
                self.cursor.execute("DELETE FROM inventory WHERE id=?", (existing["id"],))
            elif existing:
                self.cursor.execute(
                    "UPDATE inventory SET quantity=? WHERE id=?", (real_qty, existing["id"])
                )
            elif real_qty > 0:
                self.cursor.execute(
                    "INSERT INTO inventory (shelf_code, barcode, expiry_date, quantity) VALUES (?,?,?,?)",
                    (shelf_code, barcode, expiry_date, real_qty),
                )
            self.log_transaction(
                tx_type, barcode, shelf_code, shelf_code, system_qty, real_qty, diff,
                expiry_date, operator, reason=reason or f"系統 {system_qty} -> 實際 {real_qty}",
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(
            operator, "庫存調整",
            note=f"{shelf_code} {barcode} 系統{system_qty}->實際{real_qty}（差異{diff}）",
        )
        return system_qty, diff

    # ---------- 總覽與報表查詢 ----------

    def dashboard_metrics(self):
        """營運總覽：卡片數字與警示清單一次備齊。"""
        excluded = self.excluded_zones()
        placeholders = ",".join("?" * len(excluded))
        product_rows = self.cursor.execute(
            f"""
            SELECT p.barcode, p.name, p.safety_stock,
                   COALESCE(SUM(CASE WHEN s.zone NOT IN ({placeholders})
                                     THEN i.quantity ELSE 0 END), 0) AS available_qty
            FROM products p
            LEFT JOIN inventory i ON i.barcode=p.barcode
            LEFT JOIN shelves s ON s.shelf_code=i.shelf_code
            GROUP BY p.barcode
            ORDER BY p.name
            """,
            excluded,
        ).fetchall()
        warn_days = self.get_setting_int("near_expiry_warn_days", 90)
        near_expiry_rows = self.cursor.execute(
            """
            SELECT i.barcode, p.name, i.shelf_code, i.expiry_date, i.quantity
            FROM inventory i
            JOIN products p ON p.barcode=i.barcode
            WHERE i.expiry_date NOT IN ('', ?)
              AND i.expiry_date <= ?
            ORDER BY i.expiry_date, i.shelf_code
            """,
            (NO_EXPIRY_DATE, (date.today() + timedelta(days=warn_days)).isoformat()),
        ).fetchall()
        pending_count = self.cursor.execute(
            "SELECT COUNT(*) AS count FROM shipping_orders WHERE status IN ('待撿貨', '包裝中')"
        ).fetchone()["count"]
        low_stock_rows = [
            row for row in product_rows
            if row["safety_stock"] > 0 and row["available_qty"] <= row["safety_stock"]
        ]
        # 今日進出貨統計（以庫存異動紀錄為準，涵蓋一鍵完成等所有路徑）。
        today_prefix = f"{Utils.today_text()}%"
        today_shipped = self.cursor.execute(
            "SELECT COALESCE(SUM(-change_qty), 0) AS qty FROM transactions "
            "WHERE tx_type='訂單出貨' AND timestamp LIKE ?",
            (today_prefix,),
        ).fetchone()["qty"]
        today_received = self.cursor.execute(
            "SELECT COALESCE(SUM(change_qty), 0) AS qty FROM transactions "
            "WHERE tx_type='進貨驗收' AND timestamp LIKE ?",
            (today_prefix,),
        ).fetchone()["qty"]
        staging_count = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE shelf_code=?", (STAGING_SHELF,)
        ).fetchone()["cnt"]
        return {
            "product_rows": product_rows,
            "total_available": sum(row["available_qty"] for row in product_rows),
            "low_stock_rows": low_stock_rows,
            "near_expiry_rows": near_expiry_rows,
            "pending_order_count": pending_count,
            "today_shipped_qty": today_shipped,
            "today_received_qty": today_received,
            "staging_batch_count": staging_count,
        }

    def sidebar_todo_summary(self):
        """側欄「今日待辦」摘要：一眼看到還有什麼事要做。"""
        pending_ship = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM shipping_orders WHERE status IN ('待撿貨', '包裝中')"
        ).fetchone()["cnt"]
        pending_receive = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM receiving_orders WHERE status IN ('待驗收', '驗收中')"
        ).fetchone()["cnt"]
        staging = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE shelf_code=?", (STAGING_SHELF,)
        ).fetchone()["cnt"]
        warn_days = self.get_setting_int("near_expiry_warn_days", 90)
        near_expiry = self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE expiry_date NOT IN ('', ?) AND expiry_date <= ?",
            (NO_EXPIRY_DATE, (date.today() + timedelta(days=warn_days)).isoformat()),
        ).fetchone()["cnt"]
        return {
            "pending_shipping": pending_ship,
            "pending_receiving": pending_receive,
            "staging_batches": staging,
            "near_expiry": near_expiry,
        }

    def inventory_report(self, shelf_code="", keyword=""):
        """庫存查詢頁的批次清單；無儲位模式下未上架批次也會列出。"""
        excluded = self.excluded_zones()
        placeholders = ",".join("?" * len(excluded))
        keyword_like = f"%{keyword}%"
        hide_staging = "" if self.get_setting_bool("no_location_mode") else "AND i.shelf_code <> '未上架'"
        return self.cursor.execute(
            f"""
            WITH stock AS (
                SELECT i.barcode,
                       SUM(CASE WHEN s.zone NOT IN ({placeholders})
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
            WHERE 1=1 {hide_staging}
              AND (?='' OR i.shelf_code=?)
              AND (?='' OR i.barcode LIKE ? OR p.name LIKE ?)
            ORDER BY i.shelf_code, i.expiry_date, p.name
            """,
            (*excluded, shelf_code, shelf_code, keyword, keyword_like, keyword_like),
        ).fetchall()
