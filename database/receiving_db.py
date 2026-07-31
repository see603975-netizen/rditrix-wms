"""ReceivingDBMixin：進貨單、驗收與相關防呆規則。"""
from utils.constants import *
from utils.helpers import Utils


class ReceivingDBMixin:
    def generate_receiving_order_no(self):
        """產生可列印／可掃描的進貨單號，格式與出貨單一致。"""
        return self._generate_sequential_no("receiving_orders", "order_no", "RO")

    def _check_max_receiving(self, barcode, quantity, product=None):
        """防呆設定啟用時，單一品項的進貨量不可超過商品主檔設定的最大進貨量。"""
        if not self.get_setting_bool("enforce_max_receiving"):
            return
        product = product or self.product_by_barcode(barcode)
        if not product:
            return
        keys = product.keys() if hasattr(product, "keys") else ()
        max_qty = product["max_receiving_qty"] if "max_receiving_qty" in keys else 0
        if max_qty and quantity > max_qty:
            raise ValueError(
                f"{product['name']} 的單次進貨量上限為 {max_qty}（防呆設定），本次輸入 {quantity} 已超過；"
                "如確有需要請由管理者調整商品主檔的最大進貨量"
            )

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
            self._check_max_receiving(barcode, required_qty)
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

    def validate_receiving_expiry(self, expiry_date):
        """V6.9 防呆：進貨效期必須至少大於今日加 N 天（預設 180 天，可於防呆設定調整）。

        回傳剩餘天數；不合規則丟 ValueError。"""
        valid, expired, days = Utils.validate_date(expiry_date)
        if not valid:
            raise ValueError("效期格式錯誤，請輸入 YYYY-MM-DD")
        if expired:
            raise ValueError("嚴禁驗收已過期商品")
        min_days = self.get_setting_int("expiry_min_days", 0)
        if min_days > 0 and days < min_days:
            threshold = (date.today() + timedelta(days=min_days)).isoformat()
            raise ValueError(
                f"進貨效期防呆：有效期限必須在 {threshold} 之後（今日 + {min_days} 天），"
                f"本批僅剩 {days} 天；請確認是否誤輸入即期品或錯誤日期"
            )
        return days

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
        self._check_max_receiving(barcode, line["received_qty"] + quantity, product)

        if product["expiry_required"]:
            self.validate_receiving_expiry(expiry_date)
        else:
            expiry_date = NO_EXPIRY_DATE

        try:
            self.cursor.execute("BEGIN")
            before_qty, after_qty = self.add_inventory(STAGING_SHELF, barcode, expiry_date, quantity)
            self.cursor.execute(
                "UPDATE receiving_order_items SET received_qty=received_qty+? WHERE id=?",
                (quantity, line["id"]),
            )
            self.log_transaction(
                "進貨驗收",
                barcode,
                "供應商",
                STAGING_SHELF,
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

    def quick_receive_order(self, order_no, expiry_map, operator):
        """一鍵完成驗收入庫（防呆設定啟用時才可用）：人工點數後，
        一次把所有品項的剩餘數量驗收入未上架區。

        expiry_map：{barcode: 'YYYY-MM-DD'}；有效期商品必須提供，無效期商品可省略。"""
        if not self.get_setting_bool("allow_quick_receive"):
            raise ValueError("「一鍵完成驗收入庫」尚未在防呆設定中啟用")
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] != "驗收中":
            raise ValueError("僅「驗收中」的進貨單可以一鍵完成驗收")
        missing = self.missing_products_for_receiving_order(order_no)
        if missing:
            details = "、".join(f"{row['product_name']}（{row['barcode']}）" for row in missing)
            raise ValueError(f"尚未建立商品主檔：{details}")
        received_any = False
        for line in self.receiving_order_lines(order_no):
            remaining = line["required_qty"] - line["received_qty"]
            if remaining <= 0:
                continue
            product = self.product_by_barcode(line["barcode"])
            expiry = (expiry_map or {}).get(line["barcode"], "").strip()
            if product["expiry_required"] and not expiry:
                raise ValueError(f"{line['product_name']} 為有效期商品，請輸入效期後再一鍵驗收")
            self.scan_receiving_item(order_no, line["barcode"], remaining, expiry, operator)
            received_any = True
        if not received_any:
            raise ValueError("所有品項皆已驗收足額，無需一鍵驗收")
        self.complete_receiving(order_no, operator)
        self.log_operation(operator, "一鍵完成驗收", order_no, "人工點數後整單快速入庫")

    def reset_receiving_scan_progress(self, order_no, operator):
        """商品歸零。驗收過程中若誤刷，可將此進貨單目前已驗收的數量與對應未上架庫存全部歸零重來。
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
                    "SELECT id, quantity, expiry_date FROM inventory WHERE shelf_code=? AND barcode=? ORDER BY id",
                    (STAGING_SHELF, line["barcode"]),
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
                        STAGING_SHELF,
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
        """進貨單取消。V6.9 防呆：已登記到貨（待驗收）、驗收中或已完成的單據
        一律禁止直接取消，必須改走退貨或盤點調帳流程。"""
        header = self.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無此進貨單")
        if header["status"] == "已完成":
            raise ValueError("已完成的進貨單不能取消，請以退貨流程處理")
        if header["status"] == "已取消":
            raise ValueError("此進貨單已取消")
        if header["status"] in ("待驗收", "驗收中"):
            raise ValueError(
                "此進貨單已登記到貨，禁止直接取消；"
                "多收／短收請改走「退貨作業」或由管理者以盤點調帳處理"
            )
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
        """移除進貨單中誤加入的商品明細，僅限尚未開始驗收、且該筆尚未驗收任何數量。"""
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

    def mark_receiving_order_printed(self, order_no):
        self.cursor.execute(
            "UPDATE receiving_orders SET print_count=print_count+1, last_printed_at=? WHERE order_no=?",
            (Utils.now_text(), order_no),
        )
        self.conn.commit()
        return self.receiving_order_header(order_no)["print_count"]
