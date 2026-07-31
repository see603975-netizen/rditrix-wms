"""ReturnDBMixin：供應商退貨、買家退貨品檢、報廢暫存流程。"""
from utils.constants import *
from utils.helpers import Utils


class ReturnDBMixin:
    # ---------- 供應商退貨 ----------

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

    # ---------- 報廢暫存（三天保護期） ----------

    def move_to_scrap_hold(self, source_shelf, barcode, expiry_date, quantity, reason, operator):
        """Move stock to Scrap and start the three-day reversible hold period."""
        source_shelf = (source_shelf or "").strip().upper()
        barcode = Utils.normalize_barcode(barcode or "")
        reason = (reason or "").strip()
        if source_shelf in ("", SCRAP_ZONE_SHELF) or not Utils.valid_barcode(barcode):
            raise ValueError("請輸入正確的來源儲位與商品條碼")
        if not isinstance(quantity, int) or not 1 <= quantity <= 100000:
            raise ValueError("報廢數量必須是 1 至 100,000 的整數")
        if not reason:
            raise ValueError("請填寫報廢原因")
        if not self.shelf_by_code(source_shelf):
            raise ValueError("來源儲位不存在")
        if not self.product_by_barcode(barcode):
            raise ValueError("商品主檔不存在")
        # V6.9 修正：效期留白時自動對應批次（無效期商品如紙杯過去會誤報庫存不足）。
        expiry_date = self._resolve_batch_expiry(source_shelf, barcode, expiry_date)
        moved_at = Utils.now_text()
        due_at = (datetime.now() + timedelta(days=SCRAP_HOLD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.cursor.execute("BEGIN")
            self._move_batch(source_shelf, SCRAP_ZONE_SHELF, barcode, expiry_date, quantity, operator,
                             "報廢暫存移轉", reason)
            self.cursor.execute(
                """INSERT INTO scrap_holds
                   (barcode, expiry_date, quantity, source_shelf_code, reason, moved_at, due_at, moved_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (barcode, expiry_date, quantity, source_shelf, reason, moved_at, due_at, operator),
            )
            hold_id = self.cursor.lastrowid
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "報廢暫存", str(hold_id), f"{barcode} x {quantity}；到期：{due_at}；{reason}")
        self.conn.commit()
        return hold_id, due_at

    def cancel_scrap_hold(self, hold_id, operator):
        hold = self.cursor.execute("SELECT * FROM scrap_holds WHERE id=?", (hold_id,)).fetchone()
        if not hold or hold["status"] != "PENDING":
            raise ValueError("僅能取消仍在三天保護期內的報廢暫存")
        if hold["due_at"] <= Utils.now_text():
            raise ValueError("報廢暫存已到期，請先執行到期扣帳")
        try:
            self.cursor.execute("BEGIN")
            self._move_batch(SCRAP_ZONE_SHELF, hold["source_shelf_code"], hold["barcode"], hold["expiry_date"],
                             hold["quantity"], operator, "取消報廢", f"取消報廢暫存 #{hold_id}")
            self.cursor.execute("UPDATE scrap_holds SET status='CANCELLED', cancelled_at=?, cancelled_by=? WHERE id=?",
                                (Utils.now_text(), operator, hold_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "取消報廢", str(hold_id))
        self.conn.commit()

    def process_due_scrap_holds(self, operator="SYSTEM"):
        """Permanently write off only holds whose three-day protection period has elapsed."""
        due_rows = self.cursor.execute(
            "SELECT * FROM scrap_holds WHERE status='PENDING' AND due_at<=? ORDER BY id", (Utils.now_text(),)
        ).fetchall()
        completed = []
        for hold in due_rows:
            try:
                self.cursor.execute("BEGIN")
                batch = self._inventory_batch(SCRAP_ZONE_SHELF, hold["barcode"], hold["expiry_date"])
                if not batch or batch["quantity"] < hold["quantity"]:
                    raise ValueError("報廢區庫存不足，保留暫存紀錄供人工處理")
                after_qty = self.deduct_inventory(batch["id"], batch["quantity"], hold["quantity"])
                self.log_transaction("報廢正式扣帳", hold["barcode"], SCRAP_ZONE_SHELF, None,
                                     batch["quantity"], after_qty, -hold["quantity"], hold["expiry_date"],
                                     operator, reason=f"報廢暫存 #{hold['id']} 到期扣帳：{hold['reason']}")
                self.cursor.execute(
                    "UPDATE scrap_holds SET status='WRITTEN_OFF', written_off_at=?, written_off_by=? WHERE id=?",
                    (Utils.now_text(), operator, hold["id"]),
                )
                self.conn.commit()
                completed.append(hold["id"])
            except Exception:
                self.conn.rollback()
        for hold_id in completed:
            self.log_operation(operator, "報廢正式扣帳", str(hold_id))
        if completed:
            self.conn.commit()
        return completed

    def all_scrap_holds(self):
        return self.cursor.execute(
            """SELECT h.*, p.name AS product_name FROM scrap_holds h
               JOIN products p ON p.barcode=h.barcode ORDER BY CASE h.status WHEN 'PENDING' THEN 0 ELSE 1 END, h.due_at"""
        ).fetchall()

    # ---------- 買家退貨（品檢流程） ----------

    def create_buyer_return_to_qc(self, barcode, expiry_date, quantity, note, operator):
        barcode = Utils.normalize_barcode(barcode or "")
        product = self.product_by_barcode(barcode)
        if not product:
            raise ValueError("商品主檔不存在，不能建立買家退貨")
        if not isinstance(quantity, int) or not 1 <= quantity <= 100000:
            raise ValueError("退貨數量必須是 1 至 100,000 的整數")
        if product["expiry_required"]:
            valid, _expired, _days = Utils.validate_date(expiry_date)
            if not valid:
                raise ValueError("有期限商品必須輸入 YYYY-MM-DD 效期")
        else:
            expiry_date = NO_EXPIRY_DATE
        return_no = self._generate_sequential_no("buyer_returns", "return_no", "BR")
        try:
            self.cursor.execute("BEGIN")
            self.add_inventory(QC_ZONE_SHELF, barcode, expiry_date, quantity)
            self.cursor.execute(
                """INSERT INTO buyer_returns
                   (return_no, barcode, product_name, expiry_date, quantity, note, created_at, created_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (return_no, barcode, product["name"], expiry_date, quantity, (note or "").strip(), Utils.now_text(), operator),
            )
            self.log_transaction("買家退貨入品檢", barcode, None, QC_ZONE_SHELF, 0, quantity, quantity,
                                 expiry_date, operator, reason=f"買家退貨 {return_no}")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "買家退貨入品檢", return_no, f"{barcode} x {quantity}")
        self.conn.commit()
        return return_no

    def all_buyer_returns(self):
        return self.cursor.execute("SELECT * FROM buyer_returns ORDER BY id DESC").fetchall()

    def restock_buyer_return(self, return_no, target_shelf, operator):
        """Release a QC-approved buyer return to an active physical shelf."""
        row = self.cursor.execute("SELECT * FROM buyer_returns WHERE return_no=?", (return_no,)).fetchone()
        if not row or row["status"] != "PENDING_QC":
            raise ValueError("僅能處理待品檢的買家退貨")
        shelf = self.shelf_by_code((target_shelf or "").strip().upper())
        if not shelf or shelf["is_special"] or shelf["status"] != "啟用":
            raise ValueError("請選擇啟用中的一般實體儲位")
        try:
            self.cursor.execute("BEGIN")
            self._move_batch(QC_ZONE_SHELF, shelf["shelf_code"], row["barcode"], row["expiry_date"], row["quantity"],
                             operator, "買退品檢合格上架", f"買家退貨 {return_no} 品檢合格")
            self.cursor.execute(
                """UPDATE buyer_returns SET status='RESTOCKED', processed_at=?, processed_by=?, target_shelf_code=?
                   WHERE return_no=?""", (Utils.now_text(), operator, shelf["shelf_code"], return_no)
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "買退品檢合格上架", return_no, f"移至 {shelf['shelf_code']}")
        self.conn.commit()

    def scrap_buyer_return(self, return_no, reason, operator):
        """Move a failed QC return to the reversible scrap hold workflow."""
        row = self.cursor.execute("SELECT * FROM buyer_returns WHERE return_no=?", (return_no,)).fetchone()
        if not row or row["status"] != "PENDING_QC":
            raise ValueError("僅能處理待品檢的買家退貨")
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("請填寫品檢不合格／報廢原因")
        moved_at = Utils.now_text()
        due_at = (datetime.now() + timedelta(days=SCRAP_HOLD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.cursor.execute("BEGIN")
            self._move_batch(QC_ZONE_SHELF, SCRAP_ZONE_SHELF, row["barcode"], row["expiry_date"], row["quantity"],
                             operator, "買退品檢不合格", reason)
            self.cursor.execute(
                """INSERT INTO scrap_holds
                   (barcode, expiry_date, quantity, source_shelf_code, reason, moved_at, due_at, moved_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (row["barcode"], row["expiry_date"], row["quantity"], QC_ZONE_SHELF,
                 f"買家退貨 {return_no}：{reason}", moved_at, due_at, operator),
            )
            hold_id = self.cursor.lastrowid
            self.cursor.execute(
                """UPDATE buyer_returns SET status='SCRAP_HOLD', processed_at=?, processed_by=?, scrap_hold_id=?
                   WHERE return_no=?""", (moved_at, operator, hold_id, return_no)
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "買退品檢不合格報廢", return_no, f"報廢暫存 #{hold_id}；到期：{due_at}")
        self.conn.commit()
        return hold_id, due_at
