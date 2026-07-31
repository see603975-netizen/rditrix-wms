"""ReceivingUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class ReceivingUIMixin:
    def build_receiving_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame,
            "進貨／驗貨作業",
            "現場驗貨、建立叫貨單與歷史對帳分頁處理；所有商品驗收後先進入未上架區",
        )
        self.receiving_notebook = tb.Notebook(frame, bootstyle="primary")
        self.receiving_notebook.pack(fill=BOTH, expand=True)
        self.receiving_scan_tab = tb.Frame(self.receiving_notebook, padding=14)
        self.receiving_create_tab = tb.Frame(self.receiving_notebook, padding=14)
        self.receiving_query_tab = tb.Frame(self.receiving_notebook, padding=14)
        self.receiving_notebook.add(self.receiving_scan_tab, text=" 掃描進貨／驗貨 ")
        # 單據建立權限：現場作業員隱藏「建立進貨單」分頁。
        if self.has_perm("create_orders"):
            self.receiving_notebook.add(self.receiving_create_tab, text=" 建立進貨單 ")
        self.receiving_notebook.add(self.receiving_query_tab, text=" 查詢進貨單 ")
        self.build_receiving_scan_tab(self.receiving_scan_tab)
        self.build_receiving_order_tab(self.receiving_create_tab)
        self.build_receiving_query_tab(self.receiving_query_tab)
        return frame

    def build_receiving_scan_tab(self, frame):
        load_card = tb.Labelframe(frame, text="步驟 1：掃描或輸入進貨單號", bootstyle="primary", padding=14)
        load_card.pack(fill=X, pady=(0, 10))
        self.recv_order_no = tb.Entry(load_card, width=30)
        tb.Label(load_card, text="進貨單條碼:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.recv_order_no.grid(row=0, column=1, sticky=W, padx=(0, 12), pady=4)
        tb.Button(load_card, text="讀取進貨單", bootstyle="primary", command=self.load_receiving_order).grid(row=0, column=2, padx=4)
        tb.Button(load_card, text="前往建立進貨單", bootstyle="secondary", command=self.show_receiving_management).grid(row=0, column=3, padx=4)
        self.recv_order_no.bind("<Return>", lambda _event: self.load_receiving_order())

        self.recv_summary = tb.Label(frame, text="尚未讀取進貨單", font=("Microsoft JhengHei", 11), bootstyle="secondary")
        self.recv_summary.pack(anchor=W, pady=(0, 10))

        columns = ("line", "barcode", "name", "master", "required", "received", "remaining", "status")
        holder = tb.Frame(frame)
        holder.pack(fill=BOTH, expand=True)
        self.recv_tree = tb.Treeview(holder, columns=columns, show="headings", height=13, bootstyle="primary")
        headings = ("#", "商品條碼", "進貨單品名", "商品主檔", "應收", "已驗收", "剩餘", "狀態")
        widths = (50, 160, 250, 110, 75, 75, 75, 110)
        self.setup_tree_columns(self.recv_tree, columns, headings, widths, left_columns=("name",))
        self.recv_tree.tag_configure("done", background="#E1F5E7")
        self.recv_tree.tag_configure("missing", background="#FFF1D6")
        self.add_table_interactions(self.recv_tree, holder)
        self.add_tree_scrollbar(holder, self.recv_tree)

        scan_card = tb.Labelframe(frame, text="步驟 2：掃描商品並驗收", bootstyle="success", padding=14)
        scan_card.pack(fill=X, pady=12)
        self.recv_barcode = tb.Entry(scan_card, width=28)
        self.recv_qty = tb.Entry(scan_card, width=8)
        self.recv_expiry = tb.Entry(scan_card, width=16)
        self.recv_qty.insert(0, "1")
        fields = [("商品條碼", self.recv_barcode), ("本次數量", self.recv_qty), ("效期（YYYY-MM-DD）", self.recv_expiry)]
        for column, (label, widget) in enumerate(fields):
            tb.Label(scan_card, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=4)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=4)
        self.recv_scan_button = tb.Button(scan_card, text="確認驗收", bootstyle="success", command=self.scan_receiving_item)
        self.recv_scan_button.grid(row=0, column=6, padx=4)
        self.recv_barcode.bind("<Return>", lambda _event: self.scan_receiving_item())
        self.recv_qty.bind("<Return>", lambda _event: self.scan_receiving_item())
        self.recv_expiry.bind("<Return>", lambda _event: self.scan_receiving_item())
        self.recv_barcode.bind("<FocusOut>", lambda _event: self.sync_receiving_expiry_lock())

        action_bar = tb.Frame(frame)
        action_bar.pack(fill=X)
        self.recv_complete_button = tb.Button(action_bar, text="完成驗收並鎖定進貨單（全數驗收後自動觸發）", bootstyle="primary", command=self.complete_current_receiving)
        self.recv_complete_button.pack(side=RIGHT)
        self.recv_start_button = tb.Button(action_bar, text="開始驗收（讀取待驗收單後自動觸發）", bootstyle="success", command=self.start_current_receiving)
        self.recv_start_button.pack(side=RIGHT, padx=8)
        tb.Button(action_bar, text="建立商品主檔", bootstyle="warning", command=self.open_receiving_product_master).pack(side=RIGHT, padx=8)
        tb.Button(action_bar, text="一鍵完成驗收入庫（人工點數）", bootstyle="success-outline", command=self.quick_receive_current_order).pack(side=LEFT)
        self.recv_reset_button = tb.Button(action_bar, text="商品歸零", bootstyle="danger-outline", command=self.reset_current_receiving_scan)
        self.recv_reset_button.pack(side=RIGHT, padx=8)
        self.recv_status = tb.Label(frame, text="掃描進貨單條碼後將自動開始驗收，逐項掃描商品；全數驗收足額後會自動完成並鎖定。", bootstyle="secondary")
        self.recv_status.pack(anchor=W, pady=(10, 7))
        self.recv_info_tree = self.build_product_info_panel(frame, "目前掃描商品確認")

    def build_receiving_order_tab(self, frame):
        create = tb.Labelframe(frame, text="建立進貨單", bootstyle="primary", padding=14)
        create.pack(fill=X, pady=(0, 12))
        self.recv_supplier = tb.Entry(create, width=28)
        self.recv_note = tb.Entry(create, width=45)
        tb.Label(create, text="供應商:").grid(row=0, column=0, sticky=W, padx=(4, 7), pady=4)
        self.recv_supplier.grid(row=0, column=1, sticky=W, padx=(0, 16), pady=4)
        tb.Label(create, text="備註:").grid(row=0, column=2, sticky=W, padx=(4, 7), pady=4)
        self.recv_note.grid(row=0, column=3, sticky=W, padx=(0, 16), pady=4)

        line = tb.Labelframe(frame, text="新增進貨項目（可直接點選商品清單，或輸入新品供應商品名，驗收前必須建商品主檔）", bootstyle="info", padding=12)
        line.pack(fill=X, pady=(0, 12))
        self.recv_draft_barcode = tb.Combobox(line, width=42, state="normal")
        self.recv_draft_name = tb.Entry(line, width=32)
        self.recv_draft_qty = tb.Entry(line, width=10)
        fields = [("商品條碼／點選商品", self.recv_draft_barcode), ("單據品名", self.recv_draft_name), ("預計數量", self.recv_draft_qty)]
        for column, (label, widget) in enumerate(fields):
            tb.Label(line, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=4)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=4)
        tb.Button(line, text="加入項目", bootstyle="info", command=self.add_receiving_draft_line).grid(row=0, column=6, padx=4)
        self.recv_draft_barcode.bind("<<ComboboxSelected>>", self.apply_receiving_draft_selection)
        self.recv_draft_barcode.bind("<FocusOut>", self.apply_receiving_draft_selection)
        self.recv_draft_qty.bind("<Return>", lambda _event: self.add_receiving_draft_line())
        self.recv_draft_info = tb.Label(line, text="", bootstyle="secondary")
        self.recv_draft_info.grid(row=1, column=0, columnspan=7, sticky=W, padx=(4, 0), pady=(6, 0))

        draft_holder = tb.Frame(frame)
        draft_holder.pack(fill=BOTH, expand=True)
        columns = ("barcode", "name", "qty", "master")
        self.recv_draft_tree = tb.Treeview(draft_holder, columns=columns, show="headings", height=8, bootstyle="info")
        headings = ("商品條碼", "單據品名", "預計數量", "商品主檔")
        widths = (180, 360, 120, 120)
        self.setup_tree_columns(self.recv_draft_tree, columns, headings, widths, left_columns=("name",))
        self.add_table_interactions(self.recv_draft_tree, draft_holder)
        self.add_tree_scrollbar(draft_holder, self.recv_draft_tree)

        action = tb.Frame(frame)
        action.pack(fill=X, pady=12)
        tb.Button(action, text="移除選取項目", bootstyle="secondary", command=self.remove_receiving_draft_line).pack(side=LEFT)
        tb.Button(action, text="清空草稿", bootstyle="secondary", command=self.clear_receiving_draft).pack(side=LEFT, padx=8)
        tb.Button(action, text="建立進貨單並列印", bootstyle="primary", command=self.create_receiving_order_from_draft).pack(side=RIGHT)
        self.recv_create_status = tb.Label(frame, text="建立後會自動開啟進貨單列印頁面，請至「查詢進貨單」送出訂單並登錄到貨，再進行驗收。", bootstyle="secondary")
        self.recv_create_status.pack(anchor=W)

    def build_receiving_query_tab(self, frame):
        search = tb.Labelframe(frame, text="依進貨單號查詢／歷史對帳", bootstyle="secondary", padding=14)
        search.pack(fill=X, pady=(0, 10))
        self.recv_query_no = tb.Entry(search, width=32)
        tb.Label(search, text="進貨單號:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.recv_query_no.grid(row=0, column=1, sticky=W, padx=(0, 10), pady=4)
        tb.Button(search, text="查詢進貨單", bootstyle="secondary", command=self.refresh_receiving_order_list).grid(row=0, column=2, padx=4)
        tb.Button(search, text="顯示全部", bootstyle="outline-secondary", command=self.clear_receiving_query).grid(row=0, column=3, padx=4)
        self.recv_query_no.bind("<Return>", lambda _event: self.refresh_receiving_order_list())

        list_holder = tb.Frame(frame)
        list_holder.pack(fill=BOTH, expand=True)
        columns = ("order_no", "date", "supplier", "status", "lines", "required", "received", "progress", "prints", "last_print")
        self.recv_order_list_tree = tb.Treeview(list_holder, columns=columns, show="headings", height=9, bootstyle="secondary")
        headings = ("進貨單號", "日期", "供應商", "狀態", "品項", "應收", "已驗收", "驗收進度", "列印次數", "最後列印時間")
        widths = (185, 100, 180, 120, 60, 75, 75, 105, 80, 145)
        self.setup_tree_columns(self.recv_order_list_tree, columns, headings, widths, left_columns=("supplier",))
        self.recv_order_list_tree.tag_configure("done", background="#E1F5E7")
        self.recv_order_list_tree.tag_configure("in_progress", background="#FFF1D6")
        self.recv_order_list_tree.tag_configure("cancel", background="#FDE2E1")
        self.recv_order_list_tree.bind("<<TreeviewSelect>>", self.show_selected_receiving_order_details)
        self.add_table_interactions(self.recv_order_list_tree, list_holder)
        self.add_tree_scrollbar(list_holder, self.recv_order_list_tree)

        action = tb.Frame(frame)
        action.pack(fill=X, pady=10)
        tb.Button(action, text="標記已送出訂單", bootstyle="primary", command=lambda: self.advance_selected_receiving_order("已送出訂單")).pack(side=LEFT)
        tb.Button(action, text="登錄到貨／待驗收", bootstyle="warning", command=lambda: self.advance_selected_receiving_order("待驗收")).pack(side=LEFT, padx=8)
        if self.has_perm("create_orders"):
            tb.Button(action, text="取消進貨單", bootstyle="danger", command=self.cancel_selected_receiving_order).pack(side=LEFT, padx=8)
        tb.Button(action, text="補印進貨單（需填原因）", bootstyle="warning", command=self.reprint_selected_receiving_order).pack(side=LEFT, padx=8)
        tb.Button(action, text="帶入掃描驗貨", bootstyle="success", command=self.use_selected_receiving_order).pack(side=RIGHT)

        self.recv_query_summary = tb.Label(frame, text="輸入進貨單號可查詢狀態、驗收進度與歷史明細。", bootstyle="secondary")
        self.recv_query_summary.pack(anchor=W, pady=(0, 6))
        detail_holder = tb.Labelframe(frame, text="進貨單明細（尚未開始驗收時可移除誤加入的商品）", bootstyle="info", padding=8)
        detail_holder.pack(fill=BOTH, expand=True)
        detail_action = tb.Frame(detail_holder)
        detail_action.pack(fill=X, pady=(0, 6))
        tb.Button(detail_action, text="移除選取商品", bootstyle="secondary", command=self.remove_selected_receiving_order_item).pack(side=LEFT)
        detail_columns = ("line", "barcode", "name", "required", "received", "remaining", "status")
        self.recv_query_detail_tree = tb.Treeview(detail_holder, columns=detail_columns, show="headings", height=6, bootstyle="info")
        detail_headings = ("#", "商品條碼", "品名", "應收", "已驗收", "未驗收", "明細狀態")
        detail_widths = (45, 175, 300, 80, 80, 80, 120)
        self.setup_tree_columns(self.recv_query_detail_tree, detail_columns, detail_headings, detail_widths, left_columns=("name",))
        self.add_table_interactions(self.recv_query_detail_tree, detail_holder)
        self.add_tree_scrollbar(detail_holder, self.recv_query_detail_tree)

    def apply_receiving_draft_selection(self, _event=None):
        """點選商品清單或輸入條碼後，自動帶出 SKU／分類／效期設定，並鎖定已建檔商品的品名避免打錯。"""
        raw = self.recv_draft_barcode.get().strip()
        if " | " in raw:
            barcode = raw.split(" | ", 1)[0].strip()
            self.recv_draft_barcode.set(barcode)
        else:
            barcode = Utils.normalize_barcode(raw)
        self.refresh_receiving_draft_product_info(barcode)

    def fill_receiving_draft_product_name(self, _event=None):
        # 保留給舊呼叫路徑使用，實際邏輯統一由 refresh_receiving_draft_product_info 處理。
        barcode = Utils.normalize_barcode(self.recv_draft_barcode.get())
        self.refresh_receiving_draft_product_info(barcode)

    def refresh_receiving_draft_product_info(self, barcode):
        if not Utils.valid_barcode(barcode):
            self.recv_draft_info.configure(text="")
            return
        product = self.svc.product.product_by_barcode(barcode)
        if product:
            # 已建檔商品：鎖定品名為主檔名稱，避免條碼對應到錯誤品名（如化妝水條碼卻顯示紙杯）。
            self.recv_draft_name.configure(state="normal")
            self.recv_draft_name.delete(0, END)
            self.recv_draft_name.insert(0, product["name"])
            self.recv_draft_name.configure(state="readonly")
            expiry_text = "需要效期／建立 LOT" if product["expiry_required"] else "無效期商品"
            self.recv_draft_info.configure(
                text=f"已建檔商品｜SKU：{product['sku']}｜分類：{product['category'] or '其他類別'}｜{expiry_text}",
                bootstyle="success",
            )
        else:
            self.recv_draft_name.configure(state="normal")
            self.recv_draft_info.configure(
                text="此條碼尚未建立商品主檔，屬新品；請輸入供應商單據品名，驗收前需先建檔。",
                bootstyle="warning",
            )

    def add_receiving_draft_line(self):
        raw_selection = self.recv_draft_barcode.get().strip()
        if " | " in raw_selection:
            raw_selection = raw_selection.split(" | ", 1)[0]
        barcode = Utils.normalize_barcode(raw_selection)
        name = self.recv_draft_name.get().strip()
        qty_text = self.recv_draft_qty.get().strip()
        if not Utils.valid_barcode(barcode):
            return self.set_status(self.recv_create_status, "條碼格式錯誤：限英數與連字號，長度 3 至 64 碼", "danger")
        if not name:
            product = self.svc.product.product_by_barcode(barcode)
            name = product["name"] if product else ""
        if not name:
            return self.set_status(self.recv_create_status, "新品請輸入供應商單據上的商品名稱", "danger")
        if not qty_text.isdigit() or not 1 <= int(qty_text) <= 100000:
            return self.set_status(self.recv_create_status, "預計數量必須是 1 至 100,000 的整數", "danger")
        quantity = int(qty_text)
        if not messagebox.askyesno(
            "預計進貨數量確認",
            f"商品：{name}\n預計進貨數量：{quantity} 件\n\n是否確認？（避免如 50 誤打成 500 等輸入錯誤）",
        ):
            self.recv_draft_qty.focus_set()
            self.recv_draft_qty.select_range(0, END)
            return self.set_status(self.recv_create_status, "請修改預計進貨數量後再加入", "warning")
        existing = next((item for item in self.receiving_draft_items if item["barcode"] == barcode), None)
        if existing:
            existing["qty"] += quantity
        else:
            self.receiving_draft_items.append({"barcode": barcode, "name": name, "qty": quantity})
        for widget in (self.recv_draft_barcode, self.recv_draft_qty):
            widget.delete(0, END)
        self.recv_draft_name.configure(state="normal")
        self.recv_draft_name.delete(0, END)
        self.recv_draft_info.configure(text="")
        self.refresh_receiving_draft_tree()
        self.set_status(self.recv_create_status, f"已加入：{name} x {quantity}", "success")
        self.recv_draft_barcode.focus_set()

    def refresh_receiving_draft_tree(self):
        self.clear_tree(self.recv_draft_tree)
        for item in self.receiving_draft_items:
            master_status = "已建檔" if self.svc.product.product_by_barcode(item["barcode"]) else "待建檔"
            self.recv_draft_tree.insert("", END, values=(item["barcode"], item["name"], item["qty"], master_status))

    def remove_receiving_draft_line(self):
        selected = self.recv_draft_tree.focus()
        if not selected:
            return self.set_status(self.recv_create_status, "請先選取要移除的進貨項目", "warning")
        barcode, name = self.recv_draft_tree.item(selected, "values")[0:2]
        if not messagebox.askyesno("移除商品", f"確定要移除「{name}」（{barcode}）嗎？"):
            return
        self.receiving_draft_items = [item for item in self.receiving_draft_items if item["barcode"] != barcode]
        self.refresh_receiving_draft_tree()
        self.set_status(self.recv_create_status, "已移除選取項目", "secondary")

    def clear_receiving_draft(self):
        self.receiving_draft_items = []
        self.refresh_receiving_draft_tree()
        self.set_status(self.recv_create_status, "已清空進貨單草稿", "secondary")

    def create_receiving_order_from_draft(self):
        try:
            order_no = self.svc.receiving.create_receiving_order(
                self.recv_supplier.get(), self.receiving_draft_items, self.current_user, self.recv_note.get()
            )
            self.svc.log.log_operation(self.current_user, "建立進貨單", order_no, self.recv_supplier.get().strip())
            self.receiving_draft_items = []
            self.recv_supplier.delete(0, END)
            self.recv_note.delete(0, END)
            self.refresh_receiving_draft_tree()
            self.recv_query_no.delete(0, END)
            self.recv_query_no.insert(0, order_no)
            self.refresh_receiving_order_list()
            try:
                self.print_receiving_document(order_no)
                print_note = "，已開啟進貨單列印頁面"
            except Exception as print_error:
                print_note = f"，但列印失敗：{print_error}"
            self.refresh_receiving_order_list()
            self.set_status(
                self.recv_create_status,
                f"已建立進貨單 {order_no}{print_note}；請至「查詢進貨單」標記已送出訂單並登錄到貨。",
                "success",
            )
            self.receiving_notebook.select(self.receiving_query_tab)
        except ValueError as error:
            self.set_status(self.recv_create_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_create_status, f"建立失敗：{error}", "danger")

    def refresh_receiving_order_list(self):
        self.clear_tree(self.recv_order_list_tree)
        for row in self.svc.receiving.all_receiving_orders(self.recv_query_no.get()):
            progress = f"{row['received_qty']}/{row['total_qty']}"
            tag = (
                "done" if row["status"] == "已完成"
                else "cancel" if row["status"] == "已取消"
                else "in_progress" if row["status"] == "驗收中"
                else ""
            )
            self.recv_order_list_tree.insert(
                "", END,
                values=(
                    row["order_no"], row["order_date"], row["supplier_name"], row["status"],
                    row["line_count"], row["total_qty"], row["received_qty"], progress,
                    f"已列印 {row['print_count']} 次" if row["print_count"] else "尚未列印",
                    row["last_printed_at"] or "-",
                ),
                tags=(tag,) if tag else (),
            )
        self.clear_tree(self.recv_query_detail_tree)
        self.recv_query_summary.configure(text=f"查詢結果：共 {len(self.recv_order_list_tree.get_children())} 筆進貨單", bootstyle="secondary")

    def clear_receiving_query(self):
        self.recv_query_no.delete(0, END)
        self.refresh_receiving_order_list()

    def show_selected_receiving_order_details(self, _event=None, order_no=None):
        if not order_no:
            selected = self.recv_order_list_tree.focus()
            if not selected:
                return
            order_no = self.recv_order_list_tree.item(selected, "values")[0]
        header = self.svc.receiving.receiving_order_header(order_no)
        if not header:
            return
        self.recv_query_summary.configure(
            text=(
                f"單號：{header['order_no']}    供應商：{header['supplier_name']}    "
                f"目前狀態：{header['status']}    建立日：{header['order_date']}"
            ),
            bootstyle="primary" if header["status"] != "已完成" else "success",
        )
        self.clear_tree(self.recv_query_detail_tree)
        for line in self.svc.receiving.receiving_order_lines(order_no):
            remaining = line["required_qty"] - line["received_qty"]
            item_status = "已驗收完成" if remaining == 0 else "待驗收"
            self.recv_query_detail_tree.insert(
                "",
                END,
                values=(
                    line["line_no"], line["barcode"], line["product_name"],
                    line["required_qty"], line["received_qty"], remaining, item_status,
                ),
            )

    def advance_selected_receiving_order(self, new_status):
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        order_no = self.recv_order_list_tree.item(selected, "values")[0]
        try:
            self.svc.receiving.set_receiving_order_status(order_no, new_status, self.current_user)
            self.refresh_receiving_order_list()
            self.set_status(self.recv_query_summary, f"進貨單 {order_no} 已更新為「{new_status}」", "success")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")

    def cancel_selected_receiving_order(self):
        """V6.1：取消進貨單。草稿可取消，已完成不可取消，取消後保留歷史紀錄。"""
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        order_no = self.recv_order_list_tree.item(selected, "values")[0]
        if not messagebox.askyesno("取消進貨單", f"是否確定取消此進貨單？\n{order_no}"):
            return
        try:
            self.svc.receiving.cancel_receiving_order(order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "取消進貨單", order_no)
            self.refresh_receiving_order_list()
            self.set_status(self.recv_query_summary, f"進貨單 {order_no} 已取消", "danger")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")

    def reprint_selected_receiving_order(self):
        """V6.5：補印獨立按鈕，需選擇原因後才會列印，並記錄補印人／時間／原因／次數。"""
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        order_no = self.recv_order_list_tree.item(selected, "values")[0]
        reason = self.prompt_reprint_reason("補印進貨單原因")
        if not reason:
            return
        try:
            self.print_receiving_document(order_no, reason=reason)
            self.refresh_receiving_order_list()
            self.set_status(self.recv_query_summary, f"已補印進貨單 {order_no}（原因：{reason}）", "success")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_query_summary, f"補印失敗：{error}", "danger")

    def remove_selected_receiving_order_item(self):
        """V6.1：移除進貨單中誤加入的商品明細；已完成單據禁止移除。"""
        order_selected = self.recv_order_list_tree.focus()
        item_selected = self.recv_query_detail_tree.focus()
        if not order_selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        if not item_selected:
            return self.set_status(self.recv_query_summary, "請先選取要移除的商品明細", "warning")
        order_no = self.recv_order_list_tree.item(order_selected, "values")[0]
        values = self.recv_query_detail_tree.item(item_selected, "values")
        barcode, name = values[1], values[2]
        if not messagebox.askyesno("移除商品", f"確定要從進貨單 {order_no} 移除「{name}」（{barcode}）嗎？"):
            return
        try:
            self.svc.receiving.remove_receiving_order_item(order_no, barcode, self.current_user)
            self.svc.log.log_operation(self.current_user, "移除進貨商品", order_no, f"{name}（{barcode}）")
            self.refresh_receiving_order_list()
            self.show_selected_receiving_order_details(order_no=order_no)
            self.set_status(self.recv_query_summary, f"已從 {order_no} 移除「{name}」", "secondary")
        except ValueError as error:
            self.set_status(self.recv_query_summary, str(error), "danger")

    def refresh_receiving_view(self):
        self.refresh_product_choices()
        self.refresh_receiving_draft_tree()
        self.refresh_receiving_order_list()
        if self.active_receiving_order_no:
            self.refresh_receiving_order()

    def show_receiving_management(self):
        self.receiving_notebook.select(self.receiving_create_tab)

    def use_selected_receiving_order(self):
        selected = self.recv_order_list_tree.focus()
        if not selected:
            return self.set_status(self.recv_query_summary, "請先選取進貨單", "warning")
        values = self.recv_order_list_tree.item(selected, "values")
        order_no, status = values[0], values[3]
        if status not in ("待驗收", "驗收中"):
            return self.set_status(
                self.recv_query_summary,
                "請先完成「已送出訂單」與「登錄到貨／待驗收」流程後，再帶入掃描驗貨。",
                "warning",
            )
        self.recv_order_no.delete(0, END)
        self.recv_order_no.insert(0, order_no)
        self.receiving_notebook.select(self.receiving_scan_tab)
        self.load_receiving_order()

    def set_receiving_actions(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget in (self.recv_barcode, self.recv_qty, self.recv_expiry, self.recv_scan_button, self.recv_complete_button, self.recv_reset_button):
            widget.configure(state=state)

    def load_receiving_order(self):
        order_no = self.recv_order_no.get().strip().upper()
        self.recv_expiry.configure(state="normal")
        if not order_no:
            return self.set_status(self.recv_status, "請先掃描或輸入進貨單號", "danger")
        header = self.svc.receiving.receiving_order_header(order_no)
        if not header:
            self.active_receiving_order_no = None
            self.receiving_read_only = False
            self.set_receiving_actions(False)
            self.recv_start_button.configure(state="disabled")
            self.clear_tree(self.recv_tree)
            self.recv_summary.configure(text="尚未讀取進貨單", bootstyle="secondary")
            return self.set_status(self.recv_status, "查無此進貨單", "danger")

        self.active_receiving_order_no = order_no
        self.receiving_read_only = header["status"] == "已完成"
        self.refresh_receiving_order()
        if self.receiving_read_only:
            self.set_receiving_actions(False)
            self.recv_start_button.configure(state="disabled")
            return self.set_status(self.recv_status, "此進貨單已完成；目前為唯讀查詢模式，禁止重複驗收。", "warning")
        if header["status"] == "待驗收":
            return self.start_current_receiving()
        if header["status"] == "驗收中":
            self.set_receiving_actions(True)
            self.recv_start_button.configure(state="disabled")
            missing = self.svc.receiving.missing_products_for_receiving_order(order_no)
            if missing:
                details = "、".join(f"{row['product_name']}（{row['barcode']}）" for row in missing)
                self.set_status(self.recv_status, f"偵測到未建檔商品：{details}；請先建立商品主檔。", "warning")
                messagebox.showwarning("商品主檔防呆", f"進貨單 {order_no} 有未建檔商品：\n{details}\n\n請先建立商品主檔後再驗收該商品。")
            else:
                self.set_status(self.recv_status, "已載入驗收中的進貨單，請逐項掃描商品。", "success")
                self.recv_barcode.focus_set()
            return
        if header["status"] == "已取消":
            self.set_receiving_actions(False)
            self.recv_start_button.configure(state="disabled")
            return self.set_status(self.recv_status, "此進貨單已取消；目前為唯讀查詢模式。", "danger")

        self.set_receiving_actions(False)
        self.recv_start_button.configure(state="disabled")
        self.set_status(
            self.recv_status,
            f"此單目前為「{header['status']}」；請先在「查詢進貨單」完成送單與到貨登錄。",
            "warning",
        )

    def start_current_receiving(self):
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        try:
            header = self.svc.receiving.start_receiving(self.active_receiving_order_no)
            self.receiving_read_only = header["status"] == "已完成"
            self.set_receiving_actions(not self.receiving_read_only)
            self.recv_start_button.configure(state="disabled")
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.recv_barcode.focus_set()
            self.set_status(self.recv_status, "已開始驗收，請逐項掃描商品條碼。", "success")
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")

    def refresh_receiving_order(self):
        if not self.active_receiving_order_no:
            return
        header = self.svc.receiving.receiving_order_header(self.active_receiving_order_no)
        if not header:
            return
        self.recv_summary.configure(
            text=(f"單號：{header['order_no']}    日期：{header['order_date']}    "
                  f"供應商：{header['supplier_name']}    狀態：{header['status']}"),
            bootstyle="warning" if header["status"] == "已完成" else "primary",
        )
        self.clear_tree(self.recv_tree)
        for line in self.svc.receiving.receiving_order_lines(self.active_receiving_order_no):
            remaining = line["required_qty"] - line["received_qty"]
            product_exists = bool(self.svc.product.product_by_barcode(line["barcode"]))
            done = remaining == 0
            status = "待建商品主檔" if not product_exists else "已完成" if done else "待驗收"
            tag = "missing" if not product_exists else "done" if done else ""
            self.recv_tree.insert(
                "", END,
                values=(line["line_no"], line["barcode"], line["product_name"], "已建檔" if product_exists else "未建檔", line["required_qty"], line["received_qty"], remaining, status),
                tags=(tag,) if tag else (),
            )

    def open_receiving_product_master(self):
        barcode = Utils.normalize_barcode(self.recv_barcode.get())
        if not Utils.valid_barcode(barcode) and self.active_receiving_order_no:
            missing = self.svc.receiving.missing_products_for_receiving_order(self.active_receiving_order_no)
            if missing:
                barcode = missing[0]["barcode"]
        self.show_view("products")
        if Utils.valid_barcode(barcode):
            self.open_new_product_dialog(barcode, after_save=self.refresh_receiving_order)

    def sync_receiving_expiry_lock(self, _event=None):
        """依商品主檔的效期管理開關鎖定／解鎖效期輸入框，無效期商品禁止輸入效期，避免產生錯誤 LOT。"""
        self.refresh_product_info_panel(self.recv_info_tree, self.recv_barcode.get(), "未上架")
        barcode = Utils.normalize_barcode(self.recv_barcode.get())
        product = self.svc.product.product_by_barcode(barcode) if Utils.valid_barcode(barcode) else None
        if product and not product["expiry_required"]:
            self.recv_expiry.configure(state="normal")
            self.recv_expiry.delete(0, END)
            self.recv_expiry.configure(state="disabled")
        else:
            self.recv_expiry.configure(state="normal")

    def scan_receiving_item(self):
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先掃描進貨單條碼", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成進貨單只能查詢，禁止重複驗收。", "danger")
        barcode = Utils.normalize_barcode(self.recv_barcode.get())
        qty_text = self.recv_qty.get().strip()
        if not Utils.valid_barcode(barcode):
            return self.set_status(self.recv_status, "商品條碼格式錯誤", "danger")
        if not qty_text.isdigit() or not 1 <= int(qty_text) <= 100000:
            return self.set_status(self.recv_status, "本次數量必須是 1 至 100,000 的整數", "danger")
        product = self.svc.product.product_by_barcode(barcode)
        self.sync_receiving_expiry_lock()
        if not product:
            self.set_status(self.recv_status, f"條碼 {barcode} 尚未建立商品主檔，請先建檔。", "warning")
            messagebox.showwarning("商品主檔防呆", f"條碼 {barcode} 尚未建立商品主檔。\n請完成建檔後再掃描驗收。")
            return
        expiry = self.recv_expiry.get().strip()
        if product["expiry_required"]:
            # V6.9 防呆：效期須大於今日 + N 天（預設 180，可於防呆設定調整），資料層強制檢核。
            try:
                self.svc.receiving.validate_receiving_expiry(expiry)
            except ValueError as error:
                messagebox.showwarning("進貨效期防呆", str(error))
                return self.set_status(self.recv_status, str(error), "danger")
        try:
            name, received, required = self.svc.receiving.scan_receiving_item(
                self.active_receiving_order_no, barcode, int(qty_text), expiry, self.current_user
            )
            self.refresh_receiving_order()
            self.refresh_inventory()
            for widget in (self.recv_barcode, self.recv_qty):
                widget.delete(0, END)
            self.recv_expiry.configure(state="normal")
            self.recv_expiry.delete(0, END)
            self.recv_qty.insert(0, "1")
            self.set_status(self.recv_status, f"驗收成功：{name}（{received}/{required}）", "success")
            if self.receiving_order_fully_received(self.active_receiving_order_no):
                self.auto_complete_receiving()
            else:
                self.recv_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_status, f"驗收失敗：{error}", "danger")

    def receiving_order_fully_received(self, order_no):
        """判斷進貨單是否所有品項都已驗收足額，做為自動完成驗收的依據。"""
        lines = self.svc.receiving.receiving_order_lines(order_no)
        if not lines:
            return False
        return all(line["received_qty"] >= line["required_qty"] for line in lines)

    def auto_complete_receiving(self):
        """所有商品驗收足額後自動完成並鎖定進貨單，無需再手動點擊按鈕。"""
        order_no = self.active_receiving_order_no
        try:
            self.svc.receiving.complete_receiving(order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "完成進貨單", order_no)
            self.receiving_read_only = True
            self.set_receiving_actions(False)
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.refresh_dashboard()
            self.set_status(self.recv_status, f"已全部驗收完成，進貨單 {order_no} 自動完成並鎖定。", "success")
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")

    def complete_current_receiving(self):
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成進貨單只能查詢，禁止重複驗收。", "danger")
        if not messagebox.askyesno("完成進貨單", f"確定要完成並鎖定進貨單 {self.active_receiving_order_no} 嗎？\n完成後不可修改。"):
            return
        try:
            self.svc.receiving.complete_receiving(self.active_receiving_order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "完成進貨單", self.active_receiving_order_no)
            self.receiving_read_only = True
            self.set_receiving_actions(False)
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.refresh_dashboard()
            self.set_status(self.recv_status, "進貨單已完成並鎖定；後續僅能查詢，不能重複進貨。", "success")
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")

    def quick_receive_current_order(self):
        """一鍵完成驗收入庫：人工點數後整單快速入庫（防呆設定啟用時才可用）。
        有效期商品會先跳出效期輸入視窗，逐品項填入後才執行。"""
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成進貨單只能查詢。", "danger")
        if not self.svc.settings.get_setting_bool("allow_quick_receive"):
            return self.set_status(self.recv_status, "「一鍵完成驗收入庫」尚未在防呆設定中啟用，請洽管理者。", "warning")
        order_no = self.active_receiving_order_no
        pending_lines = [
            line for line in self.svc.receiving.receiving_order_lines(order_no)
            if line["required_qty"] > line["received_qty"]
        ]
        if not pending_lines:
            return self.set_status(self.recv_status, "所有品項皆已驗收足額。", "info")
        expiry_lines = []
        for line in pending_lines:
            product = self.svc.product.product_by_barcode(line["barcode"])
            if product and product["expiry_required"]:
                expiry_lines.append(line)

        dialog = tb.Toplevel(self.root)
        dialog.title("一鍵完成驗收入庫")
        dialog.transient(self.root)
        dialog.grab_set()
        body = tb.Frame(dialog, padding=18)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text=f"進貨單 {order_no}：確認人工已清點所有商品數量。",
                 font=("Microsoft JhengHei", 12, "bold"), bootstyle="primary").pack(anchor=W)
        tb.Label(body, text="此模式跳過逐件掃描，正確性依賴人工點數。",
                 bootstyle="secondary").pack(anchor=W, pady=(2, 10))
        expiry_entries = {}
        if expiry_lines:
            grid = tb.Labelframe(body, text="有效期商品請輸入效期（YYYY-MM-DD）", bootstyle="warning", padding=10)
            grid.pack(fill=X, pady=(0, 10))
            for row, line in enumerate(expiry_lines):
                tb.Label(grid, text=f"{line['product_name']}（{line['barcode']}）x {line['required_qty'] - line['received_qty']}:").grid(
                    row=row, column=0, sticky=W, pady=4, padx=(2, 8))
                entry = tb.Entry(grid, width=16)
                entry.grid(row=row, column=1, sticky=W, pady=4)
                expiry_entries[line["barcode"]] = entry
        status = tb.Label(body, text="", bootstyle="danger")
        status.pack(anchor=W, pady=(0, 6))

        def confirm():
            expiry_map = {barcode: entry.get().strip() for barcode, entry in expiry_entries.items()}
            try:
                self.svc.receiving.quick_receive_order(order_no, expiry_map, self.current_user)
            except ValueError as error:
                return status.configure(text=str(error))
            except Exception as error:
                return status.configure(text=f"一鍵驗收失敗：{error}")
            dialog.destroy()
            self.receiving_read_only = True
            self.set_receiving_actions(False)
            self.refresh_receiving_order()
            self.refresh_receiving_order_list()
            self.refresh_inventory()
            self.refresh_putaway_view()
            self.refresh_dashboard()
            self.set_status(self.recv_status, f"進貨單 {order_no} 已一鍵驗收入庫並鎖定。", "success")

        button_bar = tb.Frame(body)
        button_bar.pack(fill=X, pady=(6, 0))
        tb.Button(button_bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT, padx=(8, 0))
        tb.Button(button_bar, text="確認一鍵驗收入庫", bootstyle="success", command=confirm).pack(side=RIGHT)

    def reset_current_receiving_scan(self):
        """V6.6：商品歸零，防止刷到一半誤刷多件，將此張進貨單已驗收數量與未上架庫存全部重置。"""
        if not self.active_receiving_order_no:
            return self.set_status(self.recv_status, "請先讀取進貨單", "danger")
        if self.receiving_read_only:
            return self.set_status(self.recv_status, "已完成或已取消進貨單只能查詢，無法歸零。", "danger")
        if not messagebox.askyesno(
            "商品歸零",
            f"確定要將進貨單 {self.active_receiving_order_no} 已驗收的商品數量全部歸零嗎？\n此動作會同步移除已寫入未上架區的庫存，且無法復原。",
        ):
            return
        try:
            self.svc.receiving.reset_receiving_scan_progress(self.active_receiving_order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "驗收商品歸零", self.active_receiving_order_no)
            self.refresh_receiving_order()
            self.refresh_inventory()
            self.refresh_putaway_view()
            for widget in (self.recv_barcode, self.recv_qty):
                widget.delete(0, END)
            self.recv_qty.insert(0, "1")
            self.recv_expiry.configure(state="normal")
            self.recv_expiry.delete(0, END)
            self.set_status(self.recv_status, "已將此進貨單已驗收數量歸零，請重新掃描。", "warning")
            self.recv_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.recv_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.recv_status, f"歸零失敗：{error}", "danger")
