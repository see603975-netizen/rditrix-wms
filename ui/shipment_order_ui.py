"""ShipmentOrderUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class ShipmentOrderUIMixin:
    def build_orders_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "出貨單管理", "建立分店訂單、預留 FEFO 儲位批次、列印與補印出貨單")
        notebook = tb.Notebook(frame, bootstyle="primary")
        notebook.pack(fill=BOTH, expand=True)
        create_tab = tb.Frame(notebook, padding=14)
        list_tab = tb.Frame(notebook, padding=14)
        query_tab = tb.Frame(notebook, padding=14)
        # 單據建立權限：現場作業員隱藏「建立出貨單」分頁。
        if self.has_perm("create_orders"):
            notebook.add(create_tab, text=" 建立出貨單 ")
        notebook.add(list_tab, text=" 出貨單清單 ")
        notebook.add(query_tab, text=" 出貨單查詢 ")
        self.build_order_create_tab(create_tab)
        self.build_order_list_tab(list_tab)
        self.build_order_query_tab(query_tab)
        return frame

    def build_order_query_tab(self, frame):
        """V6.1：獨立的出貨單查詢頁，可依單號／日期／商品名稱或 SKU／門市查詢，純查詢不改變單據狀態。"""
        search = tb.Labelframe(frame, text="出貨單查詢", bootstyle="secondary", padding=14)
        search.pack(fill=X, pady=(0, 10))
        self.order_query_no = tb.Entry(search, width=22)
        self.order_query_date = tb.Entry(search, width=14)
        self.order_query_keyword = tb.Entry(search, width=22)
        self.order_query_branch = tb.Entry(search, width=18)
        fields = [
            ("出貨單號", self.order_query_no, 0, 0),
            ("日期（YYYY-MM-DD）", self.order_query_date, 0, 2),
            ("商品名稱／SKU", self.order_query_keyword, 0, 4),
            ("門市", self.order_query_branch, 0, 6),
        ]
        for label, widget, row, column in fields:
            tb.Label(search, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 14), pady=6)
        tb.Button(search, text="查詢", bootstyle="secondary", command=self.refresh_order_query_list).grid(row=0, column=8, padx=4)
        tb.Button(search, text="顯示全部", bootstyle="outline-secondary", command=self.clear_order_query).grid(row=0, column=9, padx=4)
        for widget in (self.order_query_no, self.order_query_date, self.order_query_keyword, self.order_query_branch):
            widget.bind("<Return>", lambda _event: self.refresh_order_query_list())

        list_holder = tb.Frame(frame)
        list_holder.pack(fill=BOTH, expand=True)
        columns = ("order_no", "date", "creator", "status", "lines", "branch")
        self.order_query_tree = tb.Treeview(list_holder, columns=columns, show="headings", height=9, bootstyle="secondary")
        headings = ("出貨單號", "建立日期", "建立人", "狀態", "品項數", "門市")
        widths = (185, 100, 120, 100, 70, 220)
        self.setup_tree_columns(self.order_query_tree, columns, headings, widths, left_columns=("branch",))
        self.order_query_tree.tag_configure("done", background="#E1F5E7")
        self.order_query_tree.tag_configure("cancel", background="#FDE2E1")
        self.order_query_tree.bind("<<TreeviewSelect>>", self.show_selected_order_query_details)
        self.add_table_interactions(self.order_query_tree, list_holder)
        self.add_tree_scrollbar(list_holder, self.order_query_tree)

        self.order_query_summary = tb.Label(frame, text="可依單號、日期、商品名稱／SKU、門市查詢，並點選查看完整明細。", bootstyle="secondary")
        self.order_query_summary.pack(anchor=W, pady=(8, 6))
        detail_holder = tb.Labelframe(frame, text="出貨單完整明細", bootstyle="info", padding=8)
        detail_holder.pack(fill=BOTH, expand=True)
        detail_columns = ("barcode", "name", "sku", "qty", "shelf", "expiry", "note")
        self.order_query_detail_tree = tb.Treeview(detail_holder, columns=detail_columns, show="headings", height=8, bootstyle="info")
        detail_headings = ("商品條碼", "商品名稱", "SKU", "數量", "儲位", "效期", "備註")
        detail_widths = (150, 220, 110, 70, 90, 100, 220)
        self.setup_tree_columns(self.order_query_detail_tree, detail_columns, detail_headings, detail_widths, left_columns=("name", "note"))
        self.add_table_interactions(self.order_query_detail_tree, detail_holder)
        self.add_tree_scrollbar(detail_holder, self.order_query_detail_tree)

    def refresh_order_query_list(self):
        self.clear_tree(self.order_query_tree)
        rows = self.svc.shipping.search_shipping_orders(
            self.order_query_no.get(), self.order_query_date.get(),
            self.order_query_keyword.get(), self.order_query_branch.get(),
        )
        for row in rows:
            tag = "done" if row["status"] == "已完成" else "cancel" if row["status"] == "已取消" else ""
            self.order_query_tree.insert(
                "", END,
                values=(
                    row["order_no"], row["order_date"], row["created_by"], row["status"],
                    row["line_count"], f"{row['branch_code']} {row['branch_name']}",
                ),
                tags=(tag,) if tag else (),
            )
        self.clear_tree(self.order_query_detail_tree)
        self.set_status(self.order_query_summary, f"查詢結果：共 {len(rows)} 筆出貨單", "secondary")

    def clear_order_query(self):
        for widget in (self.order_query_no, self.order_query_date, self.order_query_keyword, self.order_query_branch):
            widget.delete(0, END)
        self.refresh_order_query_list()

    def show_selected_order_query_details(self, _event=None):
        selected = self.order_query_tree.focus()
        if not selected:
            return
        order_no = self.order_query_tree.item(selected, "values")[0]
        self.clear_tree(self.order_query_detail_tree)
        for line, allocations in self.svc.shipping.order_lines(order_no):
            product = self.svc.product.product_by_barcode(line["barcode"])
            sku = product["sku"] if product else "-"
            if allocations:
                for allocation in allocations:
                    expiry = Utils.display_expiry(allocation["expiry_date"])
                    self.order_query_detail_tree.insert(
                        "", END,
                        values=(
                            line["barcode"], line["product_name"], sku,
                            allocation["allocated_qty"], allocation["shelf_code"], expiry,
                            f"已出 {allocation['shipped_qty']}/{allocation['allocated_qty']}",
                        ),
                    )
            else:
                self.order_query_detail_tree.insert(
                    "", END,
                    values=(line["barcode"], line["product_name"], sku, line["required_qty"], "-", "-", "尚未配貨"),
                )

    def build_order_create_tab(self, frame):
        header = tb.Labelframe(frame, text="出貨資料", bootstyle="primary", padding=14)
        header.pack(fill=X, pady=(0, 12))
        self.order_branch_combo = tb.Combobox(header, width=32, state="readonly")
        self.order_carrier_combo = tb.Combobox(header, values=CARRIERS, width=18, state="readonly")
        self.order_tracking = tb.Entry(header, width=24)
        self.order_box_count = tb.Entry(header, width=8)
        self.order_box_count.insert(0, "1")
        fields = [
            ("分店", self.order_branch_combo, 0, 0),
            ("物流商", self.order_carrier_combo, 0, 2),
            ("託運單號（可後補）", self.order_tracking, 0, 4),
            ("箱數", self.order_box_count, 0, 6),
        ]
        for label, widget, row, column in fields:
            tb.Label(header, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 16), pady=6)
        self.order_branch_combo.bind("<<ComboboxSelected>>", self.apply_branch_default_carrier)

        line_form = tb.Labelframe(frame, text="新增商品項目", bootstyle="info", padding=12)
        line_form.pack(fill=X, pady=(0, 12))
        self.order_product_combo = tb.Combobox(line_form, width=48, state="readonly")
        self.order_line_qty = tb.Entry(line_form, width=10)
        tb.Label(line_form, text="商品:").grid(row=0, column=0, sticky=W, padx=(4, 7), pady=4)
        self.order_product_combo.grid(row=0, column=1, sticky=W, padx=(0, 18), pady=4)
        tb.Label(line_form, text="需求數量:").grid(row=0, column=2, sticky=W, padx=(4, 7), pady=4)
        self.order_line_qty.grid(row=0, column=3, sticky=W, padx=(0, 18), pady=4)
        tb.Button(line_form, text="加入項目", bootstyle="info", command=self.add_order_draft_line).grid(row=0, column=4, padx=4)
        self.order_line_qty.bind("<Return>", lambda _event: self.add_order_draft_line())

        columns = ("barcode", "name", "qty", "available")
        draft_holder = tb.Frame(frame)
        self.order_draft_tree = tb.Treeview(draft_holder, columns=columns, show="headings", height=11, bootstyle="info")
        headings = ("商品條碼", "商品名稱", "需求數量", "目前可配庫存")
        widths = (190, 360, 140, 160)
        self.setup_tree_columns(self.order_draft_tree, columns, headings, widths, left_columns=("name",))
        action_bar = tb.Frame(frame)
        action_bar.pack(fill=X, pady=12)
        tb.Button(action_bar, text="移除選取項目", bootstyle="secondary", command=self.remove_order_draft_line).pack(side=LEFT)
        tb.Button(action_bar, text="清空草稿", bootstyle="secondary", command=self.clear_order_draft).pack(side=LEFT, padx=8)
        tb.Button(action_bar, text="建立出貨單並列印", bootstyle="primary", command=self.create_order_from_draft).pack(side=RIGHT)
        self.order_create_status = tb.Label(frame, text="建立後系統會依 FEFO 指定儲位與效期，庫存會先被保留。", bootstyle="secondary")
        self.order_create_status.pack(anchor=W)
        draft_holder.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.add_table_interactions(self.order_draft_tree, draft_holder)
        self.add_tree_scrollbar(draft_holder, self.order_draft_tree)

    def build_order_list_tab(self, frame):
        toolbar = tb.Frame(frame)
        toolbar.pack(fill=X, pady=(0, 8))
        tb.Button(toolbar, text="重新整理", bootstyle="secondary", command=self.refresh_order_list).pack(side=LEFT)
        tb.Button(toolbar, text="檢視配貨內容", bootstyle="info", command=self.preview_selected_order).pack(side=LEFT, padx=6)
        tb.Button(toolbar, text="補印出貨單（需填原因）", bootstyle="warning", command=self.reprint_selected_order).pack(side=LEFT, padx=6)
        if self.has_perm("create_orders"):
            tb.Button(toolbar, text="取消單據", bootstyle="danger", command=self.cancel_selected_order).pack(side=RIGHT)

        columns = ("order_no", "date", "branch", "status", "lines", "qty", "carrier", "tracking", "prints", "last_print", "label", "label_time")
        self.order_list_tree = tb.Treeview(frame, columns=columns, show="headings", height=22, bootstyle="primary")
        headings = ("出貨單號", "日期", "分店", "狀態", "品項", "件數", "物流商", "託運單號", "列印次數", "最後列印時間", "箱標補印次數", "箱標最後列印")
        widths = (175, 105, 190, 100, 70, 70, 135, 155, 80, 145, 90, 145)
        self.setup_tree_columns(self.order_list_tree, columns, headings, widths, left_columns=("branch",))
        self.order_list_tree.tag_configure("done", background="#E1F5E7")
        self.order_list_tree.tag_configure("cancel", background="#FDE2E1")
        self.add_table_interactions(self.order_list_tree, frame)
        self.add_tree_scrollbar(frame, self.order_list_tree)

    def refresh_product_choices(self):
        values = [f"{row['barcode']} | {row['name']}" for row in self.svc.product.all_products()]
        if self.widget_alive("order_product_combo"):
            self.order_product_combo.configure(values=values)
        if self.widget_alive("recv_draft_barcode"):
            self.recv_draft_barcode.configure(values=values)

    def refresh_branch_choices(self):
        values = [f"{row['id']} | {row['code']} | {row['name']}" for row in self.svc.branch.active_branches()]
        if self.widget_alive("order_branch_combo"):
            current = self.order_branch_combo.get()
            self.order_branch_combo.configure(values=values)
            if current not in values:
                self.order_branch_combo.set(values[0] if values else "")
                self.apply_branch_default_carrier()

    def apply_branch_default_carrier(self, _event=None):
        selected = self.order_branch_combo.get().strip()
        if not selected:
            return
        try:
            branch_id = int(selected.split(" | ", 1)[0])
        except ValueError:
            return
        branch = self.svc.branch.branch_by_id(branch_id)
        if branch:
            self.order_carrier_combo.set(branch["default_carrier"] or "未指定")

    def add_order_draft_line(self):
        selection = self.order_product_combo.get().strip()
        qty_text = self.order_line_qty.get().strip()
        if not selection:
            return self.set_status(self.order_create_status, "請先選擇商品", "danger")
        if not qty_text.isdigit() or int(qty_text) <= 0 or int(qty_text) > 100000:
            return self.set_status(self.order_create_status, "需求數量必須是 1 至 100,000 的整數", "danger")
        barcode = selection.split(" | ", 1)[0]
        product = self.svc.product.product_by_barcode(barcode)
        if not product:
            return self.set_status(self.order_create_status, "商品已不存在，請重新選擇", "danger")
        requested_qty = int(qty_text)
        existing = next((item for item in self.order_draft_items if item["barcode"] == barcode), None)
        if existing:
            existing["qty"] += requested_qty
        else:
            self.order_draft_items.append({"barcode": barcode, "name": product["name"], "qty": requested_qty})
        self.order_line_qty.delete(0, END)
        self.refresh_order_draft_tree()
        self.set_status(self.order_create_status, f"已加入：{product['name']} x {requested_qty}", "success")

    def refresh_order_draft_tree(self):
        self.clear_tree(self.order_draft_tree)
        for item in self.order_draft_items:
            available = self.svc.shipping.available_qty_for_order(item["barcode"])
            self.order_draft_tree.insert(
                "", END, values=(item["barcode"], item["name"], item["qty"], available)
            )

    def remove_order_draft_line(self):
        selected = self.order_draft_tree.focus()
        if not selected:
            return self.set_status(self.order_create_status, "請先選取要移除的商品項目", "warning")
        barcode, name = self.order_draft_tree.item(selected, "values")[0:2]
        if not messagebox.askyesno("移除商品", f"確定要移除「{name}」（{barcode}）嗎？"):
            return
        self.order_draft_items = [item for item in self.order_draft_items if item["barcode"] != barcode]
        self.refresh_order_draft_tree()
        self.set_status(self.order_create_status, "已移除選取項目", "secondary")

    def clear_order_draft(self):
        self.order_draft_items = []
        self.refresh_order_draft_tree()
        self.set_status(self.order_create_status, "已清空出貨單草稿", "secondary")

    def create_order_from_draft(self):
        try:
            selected_branch = self.order_branch_combo.get().strip()
            if not selected_branch:
                raise ValueError("請先選擇分店")
            try:
                branch_id = int(selected_branch.split(" | ", 1)[0])
            except ValueError as error:
                raise ValueError("分店資料格式錯誤，請重新選擇") from error
            box_text = self.order_box_count.get().strip()
            if not box_text.isdigit() or not 1 <= int(box_text) <= 99:
                raise ValueError("箱數必須是 1 至 99 的整數")
            order_no = self.svc.shipping.create_shipping_order(
                branch_id,
                self.order_carrier_combo.get() or "未指定",
                self.order_tracking.get().strip(),
                int(box_text),
                self.order_draft_items,
                self.current_user,
            )
            self.svc.log.log_operation(self.current_user, "建立出貨單", order_no)
            self.order_draft_items = []
            self.refresh_order_draft_tree()
            self.order_tracking.delete(0, END)
            self.order_box_count.delete(0, END)
            self.order_box_count.insert(0, "1")
            self.refresh_order_list()
            try:
                self.print_order_document(order_no)
                print_note = "，已開啟出貨單列印頁面"
            except Exception as print_error:
                print_note = f"，但列印失敗：{print_error}"
            self.refresh_order_list()
            self.set_status(
                self.order_create_status,
                f"已建立 {order_no}，庫存已保留並完成 FEFO 配貨{print_note}",
                "success",
            )
        except ValueError as error:
            self.set_status(self.order_create_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.order_create_status, f"建立失敗：{error}", "danger")

    def refresh_orders_view(self):
        self.refresh_product_choices()
        self.refresh_branch_choices()
        self.refresh_order_draft_tree()
        self.refresh_order_list()
        self.refresh_order_query_list()

    def refresh_order_list(self):
        self.clear_tree(self.order_list_tree)
        for row in self.svc.shipping.all_orders():
            tag = "done" if row["status"] == "已完成" else "cancel" if row["status"] == "已取消" else ""
            self.order_list_tree.insert(
                "",
                END,
                values=(
                    row["order_no"],
                    row["order_date"],
                    f"{row['branch_code']} {row['branch_name']}",
                    row["status"],
                    row["line_count"],
                    row["total_qty"],
                    row["carrier"],
                    row["tracking_no"] or "-",
                    f"已列印 {row['print_count']} 次" if row["print_count"] else "尚未列印",
                    row["last_printed_at"] or "-",
                    f"{row['label_print_count']} 次" if row["label_print_count"] else "尚未列印",
                    row["label_last_printed_at"] or "-",
                ),
                tags=(tag,),
            )

    def selected_order_no(self):
        selected = self.order_list_tree.focus()
        if not selected:
            raise ValueError("請先在清單中選取出貨單")
        return self.order_list_tree.item(selected, "values")[0]

    def preview_selected_order(self):
        try:
            self.show_order_preview(self.selected_order_no())
        except ValueError as error:
            messagebox.showwarning("無法檢視", str(error))

    def reprint_selected_order(self):
        """V6.5：補印獨立按鈕，需選擇原因後才會列印，並記錄補印人／時間／原因／次數。"""
        order_no = self.selected_order_no()
        if not order_no:
            return messagebox.showwarning("補印出貨單", "請先選取出貨單")
        reason = self.prompt_reprint_reason("補印出貨單原因")
        if not reason:
            return
        try:
            self.print_order_document(order_no, reason=reason)
            self.refresh_order_list()
            messagebox.showinfo("補印完成", f"已補印出貨單 {order_no}（原因：{reason}）")
        except ValueError as error:
            messagebox.showwarning("無法補印", str(error))
        except Exception as error:
            messagebox.showerror("補印失敗", str(error))

    def cancel_selected_order(self):
        try:
            order_no = self.selected_order_no()
            if not messagebox.askyesno("取消出貨單", f"確定要取消 {order_no} 嗎？\n保留庫存會立即釋放。"):
                return
            self.svc.shipping.cancel_order(order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "取消出貨單", order_no)
            self.refresh_order_list()
            messagebox.showinfo("完成", f"{order_no} 已取消，保留庫存已釋放")
        except ValueError as error:
            messagebox.showwarning("無法取消", str(error))

    def show_order_preview(self, order_no):
        header = self.svc.shipping.order_header(order_no)
        if not header:
            raise ValueError("查無出貨單")
        dialog = tb.Toplevel(self.root)
        dialog.title(f"出貨單內容 - {order_no}")
        dialog.geometry("1040x560")
        dialog.transient(self.root)
        body = tb.Frame(dialog, padding=16)
        body.pack(fill=BOTH, expand=True)
        title_label = tb.Label(
            body,
            text=f"{order_no}  |  {header['branch_code']} {header['branch_name']}  |  {header['status']}",
            font=("Microsoft JhengHei", 15, "bold"),
            bootstyle="primary",
        )
        title_label.pack(anchor=W, pady=(0, 10))
        columns = ("barcode", "name", "required", "scanned", "allocation")
        tree = tb.Treeview(body, columns=columns, show="headings", height=16, bootstyle="primary")
        headings = ("商品條碼", "商品名稱", "應出", "已掃", "建議儲位／批次")
        widths = (170, 260, 90, 90, 390)
        self.setup_tree_columns(tree, columns, headings, widths, left_columns=("name", "allocation"))
        self.add_table_interactions(tree, body)

        def reload_tree():
            self.clear_tree(tree)
            for line, allocations in self.svc.shipping.order_lines(order_no):
                text = self.format_allocations(allocations)
                tree.insert("", END, values=(line["barcode"], line["product_name"], line["required_qty"], line["scanned_qty"], text))

        def remove_item():
            selected = tree.focus()
            if not selected:
                return messagebox.showwarning("移除商品", "請先選取要移除的商品", parent=dialog)
            values = tree.item(selected, "values")
            barcode, name = values[0], values[1]
            if not messagebox.askyesno("移除商品", f"確定要從 {order_no} 移除「{name}」（{barcode}）嗎？", parent=dialog):
                return
            try:
                self.svc.shipping.remove_shipping_order_item(order_no, barcode, self.current_user)
                self.svc.log.log_operation(self.current_user, "移除出貨商品", order_no, f"{name}（{barcode}）")
                reload_tree()
                self.refresh_order_list()
                messagebox.showinfo("完成", f"已移除「{name}」", parent=dialog)
            except ValueError as error:
                messagebox.showwarning("無法移除", str(error), parent=dialog)

        action_bar = tb.Frame(body)
        action_bar.pack(fill=X, pady=(10, 0), side="bottom")
        tb.Button(action_bar, text="關閉", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT)
        if header["status"] == "待撿貨":
            tb.Button(action_bar, text="移除選取商品", bootstyle="danger", command=remove_item).pack(side=LEFT)
        tree.pack(fill=BOTH, expand=True)
        reload_tree()
