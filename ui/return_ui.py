"""ReturnUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class ReturnUIMixin:
    def build_returns_view(self):
        """Keep supplier returns intact and expose buyer returns in a separate tab."""
        frame = tb.Frame(self.content_frame, bootstyle="light")
        notebook = tb.Notebook(frame, bootstyle="primary")
        notebook.pack(fill=BOTH, expand=True)
        supplier_tab = tb.Frame(notebook, bootstyle="light")
        buyer_tab = tb.Frame(notebook, bootstyle="light")
        notebook.add(supplier_tab, text="供應商退貨")
        notebook.add(buyer_tab, text="買家退貨")
        self.build_supplier_returns_tab(supplier_tab)
        self.build_buyer_returns_tab(buyer_tab)
        return frame

    def build_supplier_returns_tab(self, parent):
        frame = tb.Frame(parent, bootstyle="light")
        frame.pack(fill=BOTH, expand=True)
        self.make_title(
            frame,
            "退貨／還貨作業",
            "登錄商品異常、附上證據照片並列印退貨表；退貨紀錄不會在未指定儲位與效期時自動扣庫存。",
        )
        form = tb.Labelframe(frame, text="新增退貨紀錄", bootstyle="danger", padding=14)
        form.pack(fill=X, pady=(0, 10))
        self.return_receiving_order_no = tb.Entry(form, width=25)
        self.return_barcode = tb.Entry(form, width=25)
        self.return_qty = tb.Entry(form, width=10)
        self.return_reason = tb.Combobox(form, values=RETURN_REASONS, state="readonly", width=14)
        self.return_reason.set(RETURN_REASONS[0])
        fields = [
            ("進貨單號", self.return_receiving_order_no, 0, 0),
            ("商品條碼", self.return_barcode, 0, 2),
            ("退貨數量", self.return_qty, 0, 4),
            ("退貨原因", self.return_reason, 0, 6),
        ]
        for label, widget, row, column in fields:
            tb.Label(form, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=5)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 14), pady=5)

        self.return_photo_source = tk.StringVar(value="")
        tb.Label(form, text="異常照片:").grid(row=1, column=0, sticky=W, padx=(4, 7), pady=5)
        tb.Entry(form, textvariable=self.return_photo_source, width=58, state="readonly").grid(row=1, column=1, columnspan=5, sticky=W, padx=(0, 8), pady=5)
        tb.Button(form, text="選擇／拍攝後附上", bootstyle="info", command=self.choose_return_photo).grid(row=1, column=6, columnspan=2, padx=4, pady=5)
        self.return_note = tb.Entry(form, width=68)
        tb.Label(form, text="備註:").grid(row=2, column=0, sticky=W, padx=(4, 7), pady=5)
        self.return_note.grid(row=2, column=1, columnspan=5, sticky=W, padx=(0, 8), pady=5)
        tb.Button(form, text="建立退貨單", bootstyle="danger", command=self.create_return_record).grid(row=2, column=6, columnspan=2, padx=4, pady=5)
        self.return_qty.bind("<Return>", lambda _event: self.create_return_record())

        self.return_status = tb.Label(frame, text="請輸入原始進貨單號；可選取相機或手機拍攝的異常照片作為證據。", bootstyle="secondary")
        self.return_status.pack(anchor=W, pady=(0, 8))

        holder = tb.Labelframe(frame, text="退貨紀錄／列印退貨表", bootstyle="secondary", padding=8)
        holder.pack(fill=BOTH, expand=True)
        columns = ("return_no", "receiving_no", "barcode", "name", "qty", "reason", "status", "photo", "created")
        self.return_tree = tb.Treeview(holder, columns=columns, show="headings", height=12, bootstyle="secondary")
        headings = ("退貨單號", "進貨單號", "商品條碼", "商品名稱", "數量", "原因", "狀態", "照片", "建立時間")
        widths = (175, 170, 150, 220, 60, 90, 125, 70, 145)
        self.setup_tree_columns(self.return_tree, columns, headings, widths, left_columns=("name",))
        self.return_tree.tag_configure("shipped", background="#E1F5E7")
        self.add_table_interactions(self.return_tree, holder)
        self.add_tree_scrollbar(holder, self.return_tree)

        actions = tb.Frame(frame)
        actions.pack(fill=X, pady=(10, 0))
        tb.Button(actions, text="列印退貨表", bootstyle="primary", command=self.print_selected_return).pack(side=RIGHT)
        # 退貨審核（標記寄回）為系統管理員專屬。
        if self.has_perm("return_review"):
            tb.Button(actions, text="標記已寄回供應商", bootstyle="success", command=self.mark_selected_return_shipped).pack(side=RIGHT, padx=8)
        return frame

    def build_buyer_returns_tab(self, parent):
        """Receive buyer returns into QC; no saleable stock is created at this stage."""
        frame = tb.Frame(parent, bootstyle="light")
        frame.pack(fill=BOTH, expand=True, padx=2, pady=2)
        self.make_title(frame, "買家退貨", "掃描商品並存入品檢區；品檢完成前不可供出貨使用。")
        form = tb.Labelframe(frame, text="買家退貨入品檢區", bootstyle="info", padding=14)
        form.pack(fill=X, pady=(0, 10))
        self.buyer_return_barcode = tb.Entry(form, width=24)
        self.buyer_return_expiry = tb.Entry(form, width=16)
        self.buyer_return_qty = tb.Entry(form, width=10)
        self.buyer_return_note = tb.Entry(form, width=42)
        fields = (("商品條碼", self.buyer_return_barcode), ("效期（有期限商品必填）", self.buyer_return_expiry),
                  ("數量", self.buyer_return_qty), ("備註", self.buyer_return_note))
        for index, (label, widget) in enumerate(fields):
            tb.Label(form, text=f"{label}:").grid(row=0, column=index * 2, sticky=W, padx=(4, 6), pady=6)
            widget.grid(row=0, column=index * 2 + 1, sticky=W, padx=(0, 12), pady=6)
        tb.Button(form, text="存入品檢區", bootstyle="info", command=self.create_buyer_return).grid(
            row=0, column=8, padx=6, pady=6
        )
        self.buyer_return_qty.bind("<Return>", lambda _event: self.create_buyer_return())
        self.buyer_return_status = tb.Label(frame, text="品檢區庫存不會列入可出貨庫存。", bootstyle="secondary")
        self.buyer_return_status.pack(anchor=W, pady=(0, 8))
        holder = tb.Labelframe(frame, text="買家退貨紀錄", bootstyle="info", padding=8)
        holder.pack(fill=BOTH, expand=True)
        columns = ("return_no", "barcode", "name", "expiry", "qty", "status", "operator", "created", "note")
        self.buyer_return_tree = tb.Treeview(holder, columns=columns, show="headings", height=13, bootstyle="info")
        headings = ("退貨單號", "商品條碼", "商品名稱", "效期", "數量", "狀態", "建立人", "建立時間", "備註")
        widths = (135, 145, 220, 110, 70, 120, 100, 145, 220)
        self.setup_tree_columns(self.buyer_return_tree, columns, headings, widths, left_columns=("name", "note"))
        self.add_table_interactions(self.buyer_return_tree, holder)
        self.add_tree_scrollbar(holder, self.buyer_return_tree)
        # 退貨審核（品檢判定）為系統管理員專屬；其他角色僅能登錄與查詢。
        if self.has_perm("return_review"):
            actions = tb.Labelframe(frame, text="品檢判定（僅限待品檢紀錄，管理員專屬）", bootstyle="warning", padding=8)
            actions.pack(fill=X, pady=(8, 0))
            self.buyer_restock_shelf = tb.Combobox(actions, width=15, state="normal")
            self.buyer_restock_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=False))
            self.buyer_scrap_reason = tb.Entry(actions, width=35)
            tb.Label(actions, text="合格上架儲位:").pack(side=LEFT, padx=(4, 6))
            self.buyer_restock_shelf.pack(side=LEFT, padx=(0, 10))
            tb.Button(actions, text="品檢合格，重新上架", bootstyle="success", command=self.restock_selected_buyer_return).pack(side=LEFT, padx=(0, 14))
            tb.Label(actions, text="不合格原因:").pack(side=LEFT, padx=(4, 6))
            self.buyer_scrap_reason.pack(side=LEFT, padx=(0, 8))
            tb.Button(actions, text="品檢不合格，移至報廢區", bootstyle="danger", command=self.scrap_selected_buyer_return).pack(side=LEFT)
        return frame

    def create_buyer_return(self):
        barcode = Utils.normalize_barcode(self.buyer_return_barcode.get())
        qty_text = self.buyer_return_qty.get().strip()
        if not qty_text.isdigit():
            return self.set_status(self.buyer_return_status, "請輸入正確的退貨數量", "danger")
        try:
            return_no = self.svc.returns.create_buyer_return_to_qc(
                barcode, self.buyer_return_expiry.get().strip(), int(qty_text),
                self.buyer_return_note.get(), self.current_user,
            )
            for widget in (self.buyer_return_barcode, self.buyer_return_expiry, self.buyer_return_qty, self.buyer_return_note):
                widget.delete(0, END)
            self.refresh_buyer_returns()
            self.set_status(self.buyer_return_status, f"買家退貨 {return_no} 已存入品檢區", "success")
        except ValueError as error:
            self.set_status(self.buyer_return_status, str(error), "danger")

    def refresh_buyer_returns(self):
        if not self.widget_alive("buyer_return_tree"):
            return
        self.clear_tree(self.buyer_return_tree)
        for row in self.svc.returns.all_buyer_returns():
            self.buyer_return_tree.insert("", END, values=(
                row["return_no"], row["barcode"], row["product_name"], row["expiry_date"], row["quantity"],
                status_label(row["status"]), row["created_by"], row["created_at"], row["note"] or "-",
            ))
        if self.widget_alive("buyer_restock_shelf"):
            self.buyer_restock_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=False))

    def _selected_buyer_return_no(self):
        selected = self.buyer_return_tree.focus()
        return self.buyer_return_tree.item(selected, "values")[0] if selected else None

    def restock_selected_buyer_return(self):
        return_no = self._selected_buyer_return_no()
        if not return_no:
            return self.set_status(self.buyer_return_status, "請先選取一筆買家退貨紀錄", "warning")
        try:
            self.svc.returns.restock_buyer_return(return_no, self.buyer_restock_shelf.get(), self.current_user)
            self.refresh_buyer_returns()
            self.set_status(self.buyer_return_status, f"{return_no} 已品檢合格並重新上架", "success")
        except ValueError as error:
            self.set_status(self.buyer_return_status, str(error), "danger")

    def scrap_selected_buyer_return(self):
        return_no = self._selected_buyer_return_no()
        if not return_no:
            return self.set_status(self.buyer_return_status, "請先選取一筆買家退貨紀錄", "warning")
        try:
            hold_id, due_at = self.svc.returns.scrap_buyer_return(return_no, self.buyer_scrap_reason.get(), self.current_user)
            self.buyer_scrap_reason.delete(0, END)
            self.refresh_buyer_returns()
            self.set_status(self.buyer_return_status, f"{return_no} 已移至報廢區暫存 #{hold_id}，到期：{due_at}", "warning")
        except ValueError as error:
            self.set_status(self.buyer_return_status, str(error), "danger")

    def choose_return_photo(self):
        path = filedialog.askopenfilename(
            title="選擇商品異常證據照片",
            filetypes=[("圖片檔", "*.jpg *.jpeg *.png *.webp *.bmp"), ("所有檔案", "*.*")],
        )
        if path:
            self.return_photo_source.set(path)
            self.set_status(self.return_status, "已附上照片；建立退貨單後會複製保存為退貨證據。", "info")

    def create_return_record(self):
        receiving_order_no = self.return_receiving_order_no.get().strip().upper()
        barcode = Utils.normalize_barcode(self.return_barcode.get())
        qty_text = self.return_qty.get().strip()
        source_text = self.return_photo_source.get().strip()
        if not qty_text.isdigit():
            return self.set_status(self.return_status, "退貨數量必須是正整數", "danger")
        source = Path(source_text) if source_text else None
        if source and not source.is_file():
            return self.set_status(self.return_status, "找不到所選的異常照片，請重新選取。", "danger")
        try:
            return_no = self.svc.returns.create_return_order(
                receiving_order_no,
                barcode,
                int(qty_text),
                self.return_reason.get(),
                self.current_user,
                self.return_note.get(),
            )
            if source:
                evidence_dir = Path(__file__).resolve().parent.parent / "return_evidence"
                evidence_dir.mkdir(exist_ok=True)
                suffix = source.suffix.lower() or ".jpg"
                saved_path = evidence_dir / f"{return_no}{suffix}"
                shutil.copy2(source, saved_path)
                self.svc.returns.set_return_evidence(return_no, str(saved_path))
            for widget in (self.return_receiving_order_no, self.return_barcode, self.return_qty, self.return_note):
                widget.delete(0, END)
            self.return_photo_source.set("")
            self.return_reason.set(RETURN_REASONS[0])
            self.refresh_returns_view()
            self.set_status(self.return_status, f"已建立退貨單 {return_no}，可直接選取後列印退貨表。", "success")
        except ValueError as error:
            self.set_status(self.return_status, str(error), "danger")
        except OSError as error:
            self.refresh_returns_view()
            self.set_status(self.return_status, f"退貨單已建立，但照片儲存失敗：{error}", "warning")
        except Exception as error:
            self.set_status(self.return_status, f"建立退貨單失敗：{error}", "danger")

    def refresh_returns_view(self):
        self.refresh_buyer_returns()
        self.clear_tree(self.return_tree)
        for row in self.svc.returns.all_return_orders():
            self.return_tree.insert(
                "",
                END,
                values=(
                    row["return_no"], row["receiving_order_no"], row["barcode"], row["product_name"],
                    row["return_qty"], row["return_reason"], row["status"],
                    "已附" if row["evidence_path"] else "未附", row["created_at"],
                ),
                tags=("shipped",) if row["status"] == "已寄回供應商" else (),
            )

    def selected_return_no(self):
        selected = self.return_tree.focus()
        if not selected:
            return None
        return self.return_tree.item(selected, "values")[0]

    def mark_selected_return_shipped(self):
        return_no = self.selected_return_no()
        if not return_no:
            return self.set_status(self.return_status, "請先選取退貨單", "warning")
        try:
            self.svc.returns.mark_return_shipped(return_no, self.current_user)
            self.refresh_returns_view()
            self.set_status(self.return_status, f"退貨單 {return_no} 已標記為寄回供應商。", "success")
        except ValueError as error:
            self.set_status(self.return_status, str(error), "danger")

    def print_selected_return(self):
        return_no = self.selected_return_no()
        if not return_no:
            return self.set_status(self.return_status, "請先選取要列印的退貨單", "warning")
        try:
            self.print_return_document(return_no)
            self.set_status(self.return_status, f"已開啟退貨單 {return_no} 的列印頁面。", "success")
        except Exception as error:
            self.set_status(self.return_status, f"列印退貨表失敗：{error}", "danger")
