"""ConsumableDBMixin：耗材快速報銷（膠帶、紙箱等）。

與一般商品報廢不同：耗材報銷立即扣帳、不進三天保護期，
自動依批次順序（FEFO）跨儲位扣除，讓現場一鍵完成。
"""
from utils.constants import *
from utils.helpers import Utils


class ConsumableDBMixin:
    def writeoff_consumable(self, barcode, quantity, operator, note=""):
        """立即報銷指定數量的耗材；回傳扣除批次摘要清單。"""
        barcode = Utils.normalize_barcode(barcode or "")
        product = self.product_by_barcode(barcode)
        if not product:
            raise ValueError("商品主檔不存在")
        if product["category"] != CONSUMABLE_CATEGORY:
            raise ValueError(f"「{product['name']}」不是耗材（分類須為「{CONSUMABLE_CATEGORY}」），"
                             "一般商品請走報廢流程（有三天保護期）")
        if not isinstance(quantity, int) or not 1 <= quantity <= 100000:
            raise ValueError("報銷數量必須是 1 至 100,000 的整數")
        batches = self.cursor.execute(
            """
            SELECT id, shelf_code, expiry_date, quantity FROM inventory
            WHERE barcode=?
            ORDER BY CASE WHEN expiry_date='' THEN '9999-12-31' ELSE expiry_date END, shelf_code
            """,
            (barcode,),
        ).fetchall()
        total = sum(batch["quantity"] for batch in batches)
        if total < quantity:
            raise ValueError(f"{product['name']} 目前庫存僅 {total}，不足報銷 {quantity}")
        moved = []
        reason = (note or "").strip() or "耗材報銷"
        try:
            self.cursor.execute("BEGIN")
            remaining = quantity
            for batch in batches:
                if remaining == 0:
                    break
                deduct_qty = min(remaining, batch["quantity"])
                after_qty = self.deduct_inventory(batch["id"], batch["quantity"], deduct_qty)
                self.log_transaction(
                    "耗材報銷", barcode, batch["shelf_code"], None,
                    batch["quantity"], after_qty, -deduct_qty, batch["expiry_date"],
                    operator, reason=reason,
                )
                remaining -= deduct_qty
                moved.append(f"{batch['shelf_code']} x {deduct_qty}")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.log_operation(operator, "耗材報銷", "", f"{product['name']}（{barcode}）x {quantity}；{reason}")
        return moved

    def recent_consumable_writeoffs(self, limit=200):
        return self.cursor.execute(
            """
            SELECT t.timestamp, t.barcode, p.name, t.from_shelf, -t.change_qty AS qty,
                   t.operator, t.reason
            FROM transactions t JOIN products p ON p.barcode=t.barcode
            WHERE t.tx_type='耗材報銷'
            ORDER BY t.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
