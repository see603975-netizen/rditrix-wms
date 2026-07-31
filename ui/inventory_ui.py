"""InventoryUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class InventoryUIMixin:
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
            ("今日出貨件數", "dark"),
            ("今日進貨件數", "secondary"),
            ("低庫存警示", "danger"),
            ("即期品批次", "warning"),
            ("待處理出貨單", "info"),
            ("待上架批次", "warning"),
        ]
        for index, (title, style) in enumerate(card_config):
            card_col.rowconfigure(index, weight=1)
            card = tb.Frame(card_col, bootstyle=style, padding=12)
            card.grid(row=index, column=0, sticky="nsew", pady=(0 if index == 0 else 3, 0))
            tb.Label(card, text=title, font=("Microsoft JhengHei", 11), bootstyle=f"inverse-{style}").pack(anchor=W)
            value = tb.Label(card, text="0", font=("Arial", 24, "bold"), bootstyle=f"inverse-{style}")
            value.pack(anchor=W, pady=(4, 0))
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
        metrics = self.svc.inventory.dashboard_metrics()
        product_rows = metrics["product_rows"]
        total_available = metrics["total_available"]
        low_stock_rows = metrics["low_stock_rows"]
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

        near_expiry_rows = metrics["near_expiry_rows"]
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

        pending_count = metrics["pending_order_count"]
        self.dashboard_cards["商品主檔"].configure(text=str(len(product_rows)))
        self.dashboard_cards["可用庫存"].configure(text=str(total_available))
        self.dashboard_cards["今日出貨件數"].configure(text=str(metrics["today_shipped_qty"]))
        self.dashboard_cards["今日進貨件數"].configure(text=str(metrics["today_received_qty"]))
        self.dashboard_cards["低庫存警示"].configure(text=str(len(low_stock_rows)))
        self.dashboard_cards["即期品批次"].configure(text=str(len(near_expiry_rows)))
        self.dashboard_cards["待處理出貨單"].configure(text=str(pending_count))
        self.dashboard_cards["待上架批次"].configure(text=str(metrics["staging_batch_count"]))

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
        tb.Button(filter_card, text="匯出 Excel/CSV", bootstyle="success",
                  command=lambda: self.export_tree_csv(self.inventory_tree, "庫存清單")).grid(row=0, column=6, padx=4)
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
        self.inv_shelf_filter.configure(values=self.svc.location.all_shelf_codes())
        if shelf_code and not self.svc.location.shelf_by_code(shelf_code):
            self.set_status(self.inv_filter_status, f"查無儲位 {shelf_code}，請確認輸入內容", "warning")
            return
        rows = self.svc.inventory.inventory_report(shelf_code, keyword)
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
                elif days < self.svc.settings.get_setting_int("near_expiry_warn_days", 90):
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
