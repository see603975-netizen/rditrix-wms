"""ShippingDBMixin：出貨單、FEFO 配貨、包裝掃描與扣庫存。"""
from utils.constants import *
from utils.helpers import Utils


class ShippingDBMixin:
    def generate_order_no(self):
        return self._generate_sequential_no("shipping_orders", "order_no", "SO")

    def available_batches_for_order(self, barcode):
        """取得可配貨庫存，並扣除其他未完成出貨單已保留的數量。

        無儲位模式（防呆設定）下，未上架區庫存也視為可配貨。"""
        excluded = self.excluded_zones()
        placeholders = ",".join("?" * len(excluded))
        query = f"""
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
              AND s.zone NOT IN ({placeholders})
              AND (i.expiry_date = '' OR i.expiry_date >= ?)
            ORDER BY CASE WHEN i.expiry_date = '' THEN '9999-12-31' ELSE i.expiry_date END,
                     i.shelf_code
        """
        rows = self.cursor.execute(query, (barcode, *excluded, Utils.today_text())).fetchall()
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
        """出貨單查詢頁專用；可依單號、日期、商品名稱／SKU、門市查詢，純查詢不改變狀態。"""
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

    def order_fully_scanned(self, order_no):
        """判斷出貨單是否所有品項都已掃描足額，做為自動完成包裝的依據。"""
        lines = self.cursor.execute(
            "SELECT required_qty, scanned_qty FROM shipping_order_items WHERE order_no=?", (order_no,)
        ).fetchall()
        if not lines:
            return False
        return all(line["scanned_qty"] >= line["required_qty"] for line in lines)

    def quick_pack_order(self, order_no, operator):
        """一鍵完成出貨驗貨（防呆設定啟用時才可用）：人工點數後，
        直接將所有品項標記掃描足額並完成包裝、扣庫存。"""
        if not self.get_setting_bool("allow_quick_pack"):
            raise ValueError("「一鍵完成出貨驗貨」尚未在防呆設定中啟用")
        header = self.start_packing(order_no)
        if header["status"] in ("已完成", "已取消"):
            raise ValueError(f"此出貨單狀態為「{header['status']}」，不可一鍵完成")
        self.cursor.execute(
            "UPDATE shipping_order_items SET scanned_qty=required_qty WHERE order_no=?", (order_no,)
        )
        self.conn.commit()
        self.complete_packing(order_no, operator)
        self.log_operation(operator, "一鍵完成出貨", order_no, "人工點數後整單快速出貨")

    def reset_packing_scan_progress(self, order_no):
        """商品歸零。出貨掃描過程中若誤刷，可將此出貨單目前已掃描的數量全部歸零重來。
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
            SET status='已取消', cancelled_at=?, cancelled_by=?, cancel_reason=?
            WHERE order_no=?
            """,
            (Utils.now_text(), operator, f"由 {operator} 取消", order_no),
        )
        self.cursor.execute(
            "UPDATE shipping_order_items SET scanned_qty=0 WHERE order_no=?", (order_no,)
        )
        self.conn.commit()

    def remove_shipping_order_item(self, order_no, barcode, operator):
        """移除出貨單中誤加入的商品明細，僅限尚未掃描、且單據尚未完成／取消。"""
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
