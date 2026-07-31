"""ProductDBMixin：商品主檔。"""
from utils.constants import *
from utils.helpers import Utils


class ProductDBMixin:
    def product_by_barcode(self, barcode):
        return self.cursor.execute(
            "SELECT * FROM products WHERE barcode=?", (barcode,)
        ).fetchone()

    def save_product(self, old_barcode, barcode, sku, name, category, safety_stock,
                     expiry_required, max_receiving_qty=0):
        """新增或更新商品；變更條碼時同步搬移仍需關聯的資料。"""
        sku = (sku or "").strip()
        name = (name or "").strip()
        barcode = (barcode or "").strip().upper()
        if not name:
            raise ValueError("商品名稱不可空白")
        # 商品主檔防呆（可於防呆設定關閉）：是否強制需要 SKU／商品條碼。
        if not sku:
            if self.get_setting_bool("require_sku"):
                raise ValueError("SKU 不可空白（管理者可於「防呆設定」關閉此檢查）")
        elif not Utils.valid_sku(sku):
            # SKU 僅限英文與數字，禁止中文與其他符號。
            raise ValueError("SKU 僅限英文字母與數字（不可中文、空白或符號），長度 1 至 32 碼")
        if not barcode:
            if self.get_setting_bool("require_barcode"):
                raise ValueError("商品條碼不可空白（管理者可於「防呆設定」關閉此檢查）")
            # 未輸入條碼時自動產生內部代碼；庫存與單據仍以此代碼關聯。
            barcode = self._generate_sequential_no("products", "barcode", "PN")
        try:
            max_receiving_qty = int(max_receiving_qty or 0)
        except (TypeError, ValueError):
            raise ValueError("最大進貨量必須是整數（0 = 不限制）")
        if not 0 <= max_receiving_qty <= 1000000:
            raise ValueError("最大進貨量必須是 0 至 1,000,000（0 = 不限制）")
        # 防呆：同一 SKU 不可重複對應到不同條碼的商品（未填 SKU 時不檢查）。
        if sku:
            duplicate = self.cursor.execute(
                "SELECT barcode FROM products WHERE sku=? AND barcode<>?",
                (sku, old_barcode or barcode),
            ).fetchone()
            if duplicate:
                raise ValueError(f"SKU「{sku}」已被商品條碼 {duplicate['barcode']} 使用，不可重複")
        # 防呆：新增商品時條碼不可與既有商品重複（避免誤蓋既有商品資料）。
        if not old_barcode and self.product_by_barcode(barcode):
            raise ValueError(f"條碼 {barcode} 已被其他商品使用，不可新增重複條碼；如需編輯請於清單點選該商品")
        if old_barcode and old_barcode != barcode:
            if self.product_by_barcode(barcode):
                raise ValueError("新條碼已存在，不能與既有商品重複")
            try:
                self.cursor.execute("BEGIN")
                self.cursor.execute(
                    """
                    INSERT INTO products
                    (barcode, sku, name, category, safety_stock, expiry_required, max_receiving_qty)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (barcode, sku, name, category, safety_stock, int(expiry_required), max_receiving_qty),
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
            return barcode

        self.cursor.execute(
            """
            INSERT INTO products
            (barcode, sku, name, category, safety_stock, expiry_required, max_receiving_qty)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(barcode) DO UPDATE SET
                sku=excluded.sku,
                name=excluded.name,
                category=excluded.category,
                safety_stock=excluded.safety_stock,
                expiry_required=excluded.expiry_required,
                max_receiving_qty=excluded.max_receiving_qty
            """,
            (barcode, sku, name, category, safety_stock, int(expiry_required), max_receiving_qty),
        )
        self.conn.commit()
        return barcode

    def bulk_import_products(self, rows, operator):
        """商品批次匯入：條碼已存在則更新，不存在則新增；逐列驗證並回報錯誤。

        rows：[{barcode, sku, name, category, safety_stock, expiry_required, max_receiving_qty}, ...]
        回傳 (成功筆數, 錯誤訊息清單)。"""
        ok_count = 0
        errors = []
        for line_no, row in enumerate(rows, start=2):  # 第 1 列是標題
            try:
                barcode = Utils.normalize_barcode(str(row.get("barcode", "") or ""))
                existing = self.product_by_barcode(barcode) if barcode else None
                safety = str(row.get("safety_stock", "0") or "0").strip() or "0"
                max_recv = str(row.get("max_receiving_qty", "0") or "0").strip() or "0"
                expiry_flag = str(row.get("expiry_required", "1") or "1").strip()
                if not safety.isdigit() or not max_recv.isdigit():
                    raise ValueError("安全庫存與最大進貨量必須是整數")
                self.save_product(
                    barcode if existing else None,
                    barcode,
                    str(row.get("sku", "") or "").strip(),
                    str(row.get("name", "") or "").strip(),
                    str(row.get("category", "") or "").strip() or "其他類別",
                    int(safety),
                    expiry_flag in ("1", "是", "Y", "y", "TRUE", "true", "需要"),
                    int(max_recv),
                )
                ok_count += 1
            except (ValueError, sqlite3.IntegrityError) as error:
                errors.append(f"第 {line_no} 列：{error}")
        self.log_operation(operator, "商品批次匯入", "", f"成功 {ok_count} 筆，失敗 {len(errors)} 筆")
        return ok_count, errors

    def all_products(self):
        return self.cursor.execute(
            """
            SELECT barcode, sku, name, category, safety_stock, expiry_required, max_receiving_qty
            FROM products ORDER BY name COLLATE NOCASE, barcode
            """
        ).fetchall()

    def consumable_products(self):
        """耗材商品清單（分類＝耗材），供耗材報銷頁快速選取，並附目前總庫存。"""
        return self.cursor.execute(
            """
            SELECT p.barcode, p.sku, p.name,
                   COALESCE((SELECT SUM(i.quantity) FROM inventory i WHERE i.barcode=p.barcode), 0) AS stock_qty
            FROM products p
            WHERE p.category=?
            ORDER BY p.name COLLATE NOCASE
            """,
            (CONSUMABLE_CATEGORY,),
        ).fetchall()

    def product_stock_overview(self, barcode, shelf_code=""):
        """商品確認面板用：可用庫存總量與指定儲位庫存。"""
        excluded = self.excluded_zones()
        placeholders = ",".join("?" * len(excluded))
        available = self.cursor.execute(
            f"""
            SELECT COALESCE(SUM(CASE WHEN s.zone NOT IN ({placeholders})
                                     THEN i.quantity ELSE 0 END), 0) AS available_qty
            FROM inventory i JOIN shelves s ON s.shelf_code=i.shelf_code
            WHERE i.barcode=?
            """,
            (*excluded, barcode),
        ).fetchone()["available_qty"]
        shelf_qty = None
        if shelf_code:
            shelf_qty = self.cursor.execute(
                "SELECT COALESCE(SUM(quantity), 0) AS qty FROM inventory WHERE barcode=? AND shelf_code=?",
                (barcode, shelf_code),
            ).fetchone()["qty"]
        return {"available_qty": available, "shelf_qty": shelf_qty}
