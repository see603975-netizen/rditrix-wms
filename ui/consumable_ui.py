"""ConsumableUIMixin：耗材快速報銷（膠帶、紙箱等，立即扣帳）。"""
from utils.constants import *
from utils.helpers import Utils

class ConsumableUIMixin:
    def build_consumable_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame, "耗材報銷",
            "點選耗材、輸入數量即可一鍵報銷；立即扣帳、不進三天保護期（一般商品請走報廢作業）",
        )

        form = tb.Labelframe(frame, text="快速報銷", bootstyle="danger", padding=14)
        form.pack(fill=X, pady=(0, 10))
        self.consumable_barcode = tb.Entry(form, width=22)
        self.consumable_qty = tb.Entry(form, width=10)
        self.consumable_note = tb.Entry(form, width=30)
        # 小螢幕相容：分兩行排列，避免右側欄位與按鈕被裁切。
        fields = [
            ("耗材條碼（可點下方清單帶入）", self.consumable_barcode, 0, 0),
            ("報銷數量", self.consumable_qty, 0, 2),
            ("用途／備註", self.consumable_note, 1, 0),
        ]
        for label, widget, row, column in fields:
            tb.Label(form, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 14), pady=6)
        tb.Button(form, text="一鍵報銷", bootstyle="danger", command=self.writeoff_consumable).grid(
            row=1, column=2, columnspan=2, sticky=W, padx=6)
        self.consumable_qty.bind("<Return>", lambda _event: self.writeoff_consumable())

        self.consumable_status = tb.Label(frame, text="耗材＝商品分類為「耗材」的品項；報銷會依批次自動跨儲位扣除。", bootstyle="secondary")
        self.consumable_status.pack(anchor=W, pady=(0, 8))

        body = tb.Frame(frame, bootstyle="light")
        body.pack(fill=BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        list_holder = tb.Labelframe(body, text="耗材清單（點選帶入條碼）", bootstyle="info", padding=8)
        list_holder.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        columns = ("barcode", "sku", "name", "stock")
        self.consumable_tree = tb.Treeview(list_holder, columns=columns, show="headings", height=12, bootstyle="info")
        headings = ("條碼", "SKU", "耗材名稱", "目前庫存")
        widths = (150, 100, 200, 90)
        self.setup_tree_columns(self.consumable_tree, columns, headings, widths, left_columns=("name",))
        self.consumable_tree.bind("<<TreeviewSelect>>", self.apply_consumable_selection)
        self.add_table_interactions(self.consumable_tree, list_holder)
        self.add_tree_scrollbar(list_holder, self.consumable_tree)

        log_holder = tb.Labelframe(body, text="最近報銷紀錄", bootstyle="secondary", padding=8)
        log_holder.grid(row=0, column=1, sticky="nsew")
        log_columns = ("time", "name", "shelf", "qty", "operator", "reason")
        self.consumable_log_tree = tb.Treeview(log_holder, columns=log_columns, show="headings",
                                               height=12, bootstyle="secondary")
        log_headings = ("時間", "耗材", "來源儲位", "數量", "人員", "備註")
        log_widths = (145, 160, 90, 70, 100, 170)
        self.setup_tree_columns(self.consumable_log_tree, log_columns, log_headings, log_widths,
                                left_columns=("name", "reason"))
        self.add_table_interactions(self.consumable_log_tree, log_holder)
        self.add_tree_scrollbar(log_holder, self.consumable_log_tree)
        return frame

    def refresh_consumable_view(self):
        self.clear_tree(self.consumable_tree)
        for row in self.svc.consumable.consumable_products():
            self.consumable_tree.insert(
                "", END,
                values=(row["barcode"], row["sku"], row["name"], row["stock_qty"]),
            )
        self.clear_tree(self.consumable_log_tree)
        for row in self.svc.consumable.recent_consumable_writeoffs(100):
            self.consumable_log_tree.insert(
                "", END,
                values=(row["timestamp"], row["name"], row["from_shelf"] or "-", row["qty"],
                        row["operator"], row["reason"] or "-"),
            )

    def apply_consumable_selection(self, _event=None):
        selected = self.consumable_tree.focus()
        if not selected:
            return
        barcode = self.consumable_tree.item(selected, "values")[0]
        self.consumable_barcode.delete(0, END)
        self.consumable_barcode.insert(0, barcode)
        self.consumable_qty.focus_set()

    def writeoff_consumable(self):
        barcode = Utils.normalize_barcode(self.consumable_barcode.get())
        qty_text = self.consumable_qty.get().strip()
        if not Utils.valid_barcode(barcode) or not qty_text.isdigit() or int(qty_text) <= 0:
            return self.set_status(self.consumable_status, "請輸入正確的耗材條碼與數量", "danger")
        product = self.svc.product.product_by_barcode(barcode)
        name = product["name"] if product else barcode
        if not messagebox.askyesno("耗材報銷", f"確定報銷「{name}」x {qty_text} 嗎？\n報銷立即扣帳且無保護期。"):
            return
        try:
            moved = self.svc.consumable.writeoff_consumable(
                barcode, int(qty_text), self.current_user, self.consumable_note.get()
            )
            for widget in (self.consumable_barcode, self.consumable_qty, self.consumable_note):
                widget.delete(0, END)
            self.refresh_consumable_view()
            self.set_status(self.consumable_status,
                            f"已報銷 {name} x {qty_text}（{'、'.join(moved)}）", "success")
        except ValueError as error:
            self.set_status(self.consumable_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.consumable_status, f"報銷失敗：{error}", "danger")
