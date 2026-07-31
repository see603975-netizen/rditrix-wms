"""PutawayUIMixin：上架作業與儲位調撥。"""
from utils.constants import *
from utils.helpers import Utils

class PutawayUIMixin:
    def build_putaway_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "上架作業", "系統會由未上架區依 FEFO 原則取出最早效期批次")
        card = tb.Labelframe(frame, text="上架資料", bootstyle="success", padding=18)
        card.pack(fill=X)
        self.put_barcode = tb.Entry(card, width=22)
        self.put_shelf = tb.Combobox(card, width=12, state="normal")
        self.put_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=False))
        self.put_qty = tb.Entry(card, width=10)
        fields = [("商品條碼", self.put_barcode), ("目標儲位", self.put_shelf), ("數量", self.put_qty)]
        for column, (label, widget) in enumerate(fields):
            tb.Label(card, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=8)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 18), pady=8)
        tb.Button(card, text="確認上架", bootstyle="success", command=self.process_putaway).grid(row=0, column=6, padx=6)
        self.put_barcode.bind("<Return>", lambda _event: self.put_shelf.focus_set())
        self.put_shelf.bind("<Return>", lambda _event: self.put_qty.focus_set())
        self.put_qty.bind("<Return>", lambda _event: self.process_putaway())
        self.put_barcode.bind("<FocusOut>", self.refresh_putaway_product_info)
        self.put_shelf.bind("<FocusOut>", self.refresh_putaway_product_info)
        self.put_status = tb.Label(frame, text="不可上架至未上架、品檢、報廢或出貨暫存區", bootstyle="secondary")
        self.put_status.pack(anchor=W, pady=14)
        self.put_info_tree = self.build_product_info_panel(frame, "上架商品確認")

        # 儲位調撥：倉庫主管以上才會顯示（現場作業員隱藏）。
        if self.has_perm("transfer_stock"):
            transfer_card = tb.Labelframe(frame, text="儲位調撥（主管以上）", bootstyle="info", padding=12)
            transfer_card.pack(fill=X, pady=(0, 4))
            self.transfer_source = tb.Combobox(transfer_card, width=12, state="normal")
            self.transfer_target = tb.Combobox(transfer_card, width=12, state="normal")
            self.transfer_barcode = tb.Entry(transfer_card, width=20)
            self.transfer_expiry = tb.Entry(transfer_card, width=14)
            self.transfer_qty = tb.Entry(transfer_card, width=8)
            # 小螢幕相容：分兩行排列，避免右側欄位與按鈕被裁切。
            transfer_fields = [
                ("來源儲位", self.transfer_source, 0, 0), ("目標儲位", self.transfer_target, 0, 2),
                ("商品條碼", self.transfer_barcode, 0, 4),
                ("效期（無效期可留白）", self.transfer_expiry, 1, 0), ("數量", self.transfer_qty, 1, 2),
            ]
            for label, widget, row, column in transfer_fields:
                tb.Label(transfer_card, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=6)
                widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 12), pady=6)
            tb.Button(transfer_card, text="確認調撥", bootstyle="info", command=self.process_transfer).grid(
                row=1, column=4, columnspan=2, sticky=W, padx=4)
            self.transfer_qty.bind("<Return>", lambda _event: self.process_transfer())
            self._refresh_transfer_shelves()

        pending_card = tb.Labelframe(frame, text="待上架商品（未上架區庫存，點選可直接帶入商品條碼）", bootstyle="warning", padding=10)
        pending_card.pack(fill=BOTH, expand=True, pady=(14, 0))
        pending_columns = ("barcode", "name", "expiry", "qty")
        self.put_pending_tree = tb.Treeview(pending_card, columns=pending_columns, show="headings", height=8, bootstyle="warning")
        pending_headings = ("商品條碼", "商品名稱", "效期", "未上架數量")
        pending_widths = (160, 260, 120, 110)
        self.setup_tree_columns(self.put_pending_tree, pending_columns, pending_headings, pending_widths, left_columns=("name",))
        self.put_pending_tree.bind("<<TreeviewSelect>>", self.apply_pending_putaway_selection)
        self.add_table_interactions(self.put_pending_tree, pending_card)
        self.add_tree_scrollbar(pending_card, self.put_pending_tree)
        return frame

    def _refresh_transfer_shelves(self):
        if self.widget_alive("transfer_source"):
            codes = self.svc.location.active_shelf_codes(include_special=False)
            self.transfer_source.configure(values=codes)
            self.transfer_target.configure(values=codes)

    def refresh_putaway_view(self):
        """進入上架作業頁面時，重新整理儲位選單與待上架商品清單。"""
        self.put_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=False))
        self._refresh_transfer_shelves()
        self.refresh_putaway_pending_tree()

    def refresh_putaway_pending_tree(self):
        self.clear_tree(self.put_pending_tree)
        rows = self.svc.inventory.staging_batches()
        for row in rows:
            self.put_pending_tree.insert(
                "",
                END,
                values=(
                    row["barcode"],
                    row["name"],
                    Utils.display_expiry(row["expiry_date"], bool(row["expiry_required"])),
                    row["quantity"],
                ),
            )
        return rows

    def apply_pending_putaway_selection(self, _event=None):
        selected = self.put_pending_tree.focus()
        if not selected:
            return
        barcode = self.put_pending_tree.item(selected, "values")[0]
        self.put_barcode.delete(0, END)
        self.put_barcode.insert(0, barcode)
        self.refresh_putaway_product_info()
        self.put_qty.focus_set()

    def refresh_putaway_product_info(self, _event=None):
        self.refresh_product_info_panel(self.put_info_tree, self.put_barcode.get(), self.put_shelf.get())

    def process_putaway(self):
        barcode = Utils.normalize_barcode(self.put_barcode.get())
        shelf_code = self.put_shelf.get().strip().upper()
        qty_text = self.put_qty.get().strip()
        self.refresh_product_info_panel(self.put_info_tree, barcode, shelf_code)
        if not Utils.valid_barcode(barcode) or not shelf_code or not qty_text.isdigit() or int(qty_text) <= 0:
            return self.set_status(self.put_status, "請完整輸入正確的條碼、目標儲位與數量", "danger")
        quantity = int(qty_text)
        try:
            moved = self.svc.inventory.putaway(barcode, shelf_code, quantity, self.current_user)
            self.set_status(self.put_status, f"上架成功：{quantity} 件至 {shelf_code}（{'、'.join(moved)}）", "success")
            for widget in (self.put_barcode, self.put_shelf, self.put_qty):
                widget.delete(0, END)
            self.refresh_product_info_panel(self.put_info_tree, "")
            self.refresh_putaway_pending_tree()
            self.put_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.put_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.put_status, f"上架失敗：{error}", "danger")

    def process_transfer(self):
        """儲位間調撥；權限已在畫面層隱藏，這裡再做一次保險檢查。"""
        if not self.has_perm("transfer_stock"):
            return self.set_status(self.put_status, "儲位調撥僅限倉庫主管以上", "danger")
        qty_text = self.transfer_qty.get().strip()
        if not qty_text.isdigit() or int(qty_text) <= 0:
            return self.set_status(self.put_status, "調撥數量必須是正整數", "danger")
        try:
            self.svc.inventory.transfer_stock(
                self.transfer_source.get(), self.transfer_target.get(),
                self.transfer_barcode.get(), self.transfer_expiry.get(),
                int(qty_text), self.current_user,
            )
            self.set_status(
                self.put_status,
                f"調撥完成：{self.transfer_barcode.get().strip().upper()} x {qty_text}"
                f"（{self.transfer_source.get()} → {self.transfer_target.get()}）",
                "success",
            )
            for widget in (self.transfer_barcode, self.transfer_expiry, self.transfer_qty):
                widget.delete(0, END)
            self.refresh_putaway_pending_tree()
            self.refresh_inventory()
        except ValueError as error:
            self.set_status(self.put_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.put_status, f"調撥失敗：{error}", "danger")
