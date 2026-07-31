"""LocationUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class LocationUIMixin:
    def build_shelf_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "儲位管理", "階層式儲位格式：區域-貨架-層位，例如 A01-03 = A區 01號貨架 第3層")

        form = tb.Labelframe(frame, text="新增／修改儲位", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 12))
        self.shelf_area = tb.Entry(form, width=6)
        self.shelf_rack = tb.Entry(form, width=6)
        self.shelf_level = tb.Entry(form, width=6)
        self.shelf_note = tb.Entry(form, width=30)
        fields = [
            ("區域（單一英文字母，如 A）", self.shelf_area, 0, 0),
            ("貨架（數字，如 1）", self.shelf_rack, 0, 2),
            ("層位（數字，如 3）", self.shelf_level, 0, 4),
            ("備註", self.shelf_note, 0, 6),
        ]
        for text, widget, row, column in fields:
            tb.Label(form, text=f"{text}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=7)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 16), pady=7)
        self.shelf_preview = tb.Label(form, text="儲位代碼預覽：-", bootstyle="secondary")
        self.shelf_preview.grid(row=1, column=0, columnspan=4, sticky=W, padx=4, pady=(0, 6))
        for widget in (self.shelf_area, self.shelf_rack, self.shelf_level):
            widget.bind("<KeyRelease>", self.update_shelf_code_preview)
        tb.Button(form, text="新增儲位", bootstyle="primary", command=self.create_shelf_from_form).grid(row=0, column=8, padx=8, pady=7)
        tb.Button(form, text="儲存修改", bootstyle="warning", command=self.rename_shelf_from_form).grid(row=1, column=6, padx=8, pady=(0, 6))
        tb.Button(form, text="清除欄位", bootstyle="secondary", command=self.clear_shelf_form).grid(row=1, column=7, padx=8, pady=(0, 6))
        self.shelf_form_status = tb.Label(frame, text="點選下方清單可帶入修改；特殊區（未上架／品檢區／報廢區／出貨暫存）不可編輯。", bootstyle="secondary")
        self.shelf_form_status.pack(anchor=W, pady=(0, 10))

        search = tb.Labelframe(frame, text="儲位搜尋", bootstyle="secondary", padding=10)
        search.pack(fill=X, pady=(0, 10))
        self.shelf_search_keyword = tb.Entry(search, width=22)
        self.shelf_search_status = tb.Combobox(search, values=("全部", "啟用", "停用"), width=10, state="readonly")
        self.shelf_search_status.set("全部")
        self.shelf_search_sort = tb.Combobox(search, values=("依儲位代碼", "依建立時間", "依庫存量"), width=12, state="readonly")
        self.shelf_search_sort.set("依儲位代碼")
        tb.Label(search, text="關鍵字（代碼／備註）:").pack(side=LEFT, padx=(4, 6))
        self.shelf_search_keyword.pack(side=LEFT, padx=(0, 14))
        tb.Label(search, text="狀態:").pack(side=LEFT, padx=(4, 6))
        self.shelf_search_status.pack(side=LEFT, padx=(0, 14))
        tb.Label(search, text="排序:").pack(side=LEFT, padx=(4, 6))
        self.shelf_search_sort.pack(side=LEFT, padx=(0, 14))
        tb.Button(search, text="查詢", bootstyle="secondary", command=self.refresh_shelf_view).pack(side=LEFT, padx=4)
        tb.Button(search, text="顯示全部", bootstyle="outline-secondary", command=self.clear_shelf_search).pack(side=LEFT, padx=4)
        self.shelf_search_keyword.bind("<Return>", lambda _event: self.refresh_shelf_view())
        self.shelf_search_status.bind("<<ComboboxSelected>>", lambda _event: self.refresh_shelf_view())
        self.shelf_search_sort.bind("<<ComboboxSelected>>", lambda _event: self.refresh_shelf_view())

        action = tb.Frame(frame)
        action.pack(fill=X, pady=(0, 8))
        tb.Button(action, text="停用選取儲位", bootstyle="danger", command=lambda: self.set_selected_shelf_status("停用")).pack(side=LEFT)
        tb.Button(action, text="啟用選取儲位", bootstyle="success", command=lambda: self.set_selected_shelf_status("啟用")).pack(side=LEFT, padx=8)

        columns = ("code", "area", "rack", "level", "status", "stock", "note", "created")
        self.shelf_tree = tb.Treeview(frame, columns=columns, show="headings", height=14, bootstyle="primary")
        headings = ("儲位代碼", "區域", "貨架", "層位", "狀態", "庫存量", "備註", "建立時間")
        widths = (110, 60, 60, 60, 70, 80, 220, 150)
        self.setup_tree_columns(self.shelf_tree, columns, headings, widths, left_columns=("note",))
        self.shelf_tree.tag_configure("disabled", background="#FDE2E1")
        self.shelf_tree.tag_configure("special", background="#EAF0FF")
        self.shelf_tree.bind("<<TreeviewSelect>>", self.on_shelf_select)
        self.add_table_interactions(self.shelf_tree, frame)
        self.add_tree_scrollbar(frame, self.shelf_tree)
        return frame

    def update_shelf_code_preview(self, _event=None):
        area = self.shelf_area.get().strip().upper()
        rack = self.shelf_rack.get().strip()
        level = self.shelf_level.get().strip()
        if re.fullmatch(r"[A-Z]", area) and rack.isdigit() and level.isdigit():
            self.shelf_preview.configure(text=f"儲位代碼預覽：{area}{int(rack):02d}-{int(level):02d}")
        else:
            self.shelf_preview.configure(text="儲位代碼預覽：-")

    def clear_shelf_form(self):
        self.shelf_selected_code = None
        for widget in (self.shelf_area, self.shelf_rack, self.shelf_level, self.shelf_note):
            widget.delete(0, END)
        self.shelf_preview.configure(text="儲位代碼預覽：-")
        self.set_status(self.shelf_form_status, "點選下方清單可帶入修改；特殊區不可編輯。", "secondary")
        self.shelf_area.focus_set()

    def clear_shelf_search(self):
        self.shelf_search_keyword.delete(0, END)
        self.shelf_search_status.set("全部")
        self.shelf_search_sort.set("依儲位代碼")
        self.refresh_shelf_view()

    def create_shelf_from_form(self):
        try:
            shelf_code = self.svc.location.create_shelf(
                self.shelf_area.get(), self.shelf_rack.get(), self.shelf_level.get(), self.shelf_note.get()
            )
            self.svc.log.log_operation(self.current_user, "新增儲位", shelf_code)
            self.clear_shelf_form()
            self.refresh_shelf_view()
            self.set_status(self.shelf_form_status, f"已新增儲位 {shelf_code}", "success")
        except ValueError as error:
            self.set_status(self.shelf_form_status, str(error), "danger")

    def on_shelf_select(self, _event=None):
        selected = self.shelf_tree.focus()
        if not selected:
            return
        values = self.shelf_tree.item(selected, "values")
        shelf_code = values[0]
        shelf = self.svc.location.shelf_by_code(shelf_code)
        if not shelf or shelf["is_special"]:
            self.shelf_selected_code = None
            for widget in (self.shelf_area, self.shelf_rack, self.shelf_level, self.shelf_note):
                widget.delete(0, END)
            self.shelf_preview.configure(text="儲位代碼預覽：-")
            self.set_status(self.shelf_form_status, "此為特殊區，不可編輯", "warning")
            return
        self.shelf_selected_code = shelf_code
        self.shelf_area.delete(0, END); self.shelf_area.insert(0, shelf["area"])
        self.shelf_rack.delete(0, END); self.shelf_rack.insert(0, str(int(shelf["rack"])))
        self.shelf_level.delete(0, END); self.shelf_level.insert(0, str(int(shelf["level"])))
        self.shelf_note.delete(0, END); self.shelf_note.insert(0, shelf["note"] or "")
        self.update_shelf_code_preview()
        self.set_status(self.shelf_form_status, f"正在修改 {shelf_code}，儲存後將套用新代碼／備註", "info")

    def rename_shelf_from_form(self):
        if not getattr(self, "shelf_selected_code", None):
            return self.set_status(self.shelf_form_status, "請先在下方清單點選要修改的儲位", "warning")
        old_code = self.shelf_selected_code
        area = self.shelf_area.get().strip().upper()
        rack, level = self.shelf_rack.get().strip(), self.shelf_level.get().strip()
        try:
            rack_no, level_no = int(rack), int(level)
            new_code = f"{area}{rack_no:02d}-{level_no:02d}"
        except (TypeError, ValueError):
            return self.set_status(self.shelf_form_status, "貨架與層位請輸入數字", "danger")

        # V6.4 防呆：儲位如仍有庫存或未完成出貨保留，修改前二次確認，避免庫存追蹤錯亂。
        summary = self.svc.location.shelf_reference_summary(old_code)
        if new_code != old_code and (summary["stock_qty"] > 0 or summary["pending_orders"] > 0):
            if not messagebox.askyesno(
                "修改儲位確認",
                f"此儲位目前存在庫存或未完成單據（庫存 {summary['stock_qty']} 件、"
                f"未完成出貨保留 {summary['pending_orders']} 張），修改可能影響庫存追蹤，是否確認修改？",
            ):
                return self.set_status(self.shelf_form_status, "已取消修改", "secondary")
        try:
            new_code = self.svc.location.rename_shelf(old_code, area, rack, level, self.shelf_note.get())
            self.svc.log.log_operation(self.current_user, "修改儲位", new_code, f"原代碼：{old_code}")
            self.shelf_selected_code = None
            self.clear_shelf_form()
            self.refresh_shelf_view()
            self.set_status(self.shelf_form_status, f"已將 {old_code} 更新為 {new_code}", "success")
        except ValueError as error:
            self.set_status(self.shelf_form_status, str(error), "danger")

    def set_selected_shelf_status(self, status):
        selected = self.shelf_tree.focus()
        if not selected:
            return self.set_status(self.shelf_form_status, "請先選取儲位", "warning")
        shelf_code = self.shelf_tree.item(selected, "values")[0]
        shelf = self.svc.location.shelf_by_code(shelf_code)
        if not shelf or shelf["is_special"]:
            return self.set_status(self.shelf_form_status, "特殊區不可停用／啟用", "danger")
        if status == "停用":
            summary = self.svc.location.shelf_reference_summary(shelf_code)
            if summary["stock_qty"] > 0 or summary["pending_orders"] > 0:
                confirmed = messagebox.askyesno(
                    "停用儲位確認",
                    f"此儲位目前存在庫存或未完成單據（庫存 {summary['stock_qty']} 件、"
                    f"未完成出貨保留 {summary['pending_orders']} 張），修改可能影響庫存追蹤，是否確認修改？",
                )
            else:
                confirmed = messagebox.askyesno("停用儲位確認", f"確定要停用儲位 {shelf_code} 嗎？")
            if not confirmed:
                return self.set_status(self.shelf_form_status, "已取消", "secondary")
        try:
            self.svc.location.set_shelf_status(shelf_code, status)
            self.svc.log.log_operation(self.current_user, f"{status}儲位", shelf_code)
            self.refresh_shelf_view()
            self.set_status(self.shelf_form_status, f"儲位 {shelf_code} 已{status}", "success")
        except ValueError as error:
            self.set_status(self.shelf_form_status, str(error), "danger")

    def refresh_shelf_view(self):
        self.clear_tree(self.shelf_tree)
        sort_map = {"依儲位代碼": "code", "依建立時間": "created", "依庫存量": "stock"}
        rows = self.svc.location.search_shelves(
            self.shelf_search_keyword.get(),
            self.shelf_search_status.get(),
            sort_map.get(self.shelf_search_sort.get(), "code"),
        )
        for row in rows:
            if row["is_special"]:
                tag, area, rack, level = "special", "-", "-", "-"
            else:
                tag = "disabled" if row["status"] == "停用" else ""
                area, rack, level = row["area"], row["rack"], row["level"]
            self.shelf_tree.insert(
                "", END,
                values=(row["shelf_code"], area, rack, level, row["status"], row["stock_qty"], row["note"] or "-", row["created_at"] or "-"),
                tags=(tag,) if tag else (),
            )
        # 同步更新上架／盤點頁的儲位下拉選單，僅列出啟用中的儲位。
        if self.widget_alive("put_shelf"):
            self.put_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=False))
        if self.widget_alive("cnt_shelf"):
            self.cnt_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=True))

    def build_scrap_view(self):
        """Dedicated disposal screen: the only normal UI path into Scrap."""
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame, "報廢作業",
            "一般商品報廢：先移入報廢區保留三天（防誤按反悔期），期滿系統自動正式扣帳；"
            "膠帶、紙箱等耗材請改用「耗材報銷」頁（立即扣帳，較快）。",
        )
        form = tb.Labelframe(frame, text="建立報廢暫存（三天內可取消）", bootstyle="danger", padding=14)
        form.pack(fill=X, pady=(0, 10))
        self.scrap_source = tb.Combobox(form, width=15, state="normal")
        self.scrap_source.configure(values=self.svc.location.active_shelf_codes(include_special=True))
        self.scrap_barcode = tb.Entry(form, width=22)
        self.scrap_expiry = tb.Entry(form, width=14)
        self.scrap_qty = tb.Entry(form, width=9)
        self.scrap_reason = tb.Entry(form, width=34)
        fields = (("來源儲位", self.scrap_source), ("商品條碼", self.scrap_barcode), ("效期（可留白自動對應）", self.scrap_expiry),
                  ("數量", self.scrap_qty), ("報廢原因", self.scrap_reason))
        for index, (label, widget) in enumerate(fields):
            tb.Label(form, text=f"{label}:").grid(row=0, column=index * 2, sticky=W, padx=(4, 6), pady=6)
            widget.grid(row=0, column=index * 2 + 1, sticky=W, padx=(0, 10), pady=6)
        tb.Button(form, text="移入報廢區（保護三天）", bootstyle="danger", command=self.create_scrap_hold).grid(
            row=1, column=0, columnspan=4, sticky=W, padx=4, pady=(8, 0)
        )
        tb.Button(form, text="手動執行到期扣帳（平常系統會自動）", bootstyle="warning-outline", command=self.process_due_scrap_holds_ui).grid(
            row=1, column=4, columnspan=3, sticky=W, padx=4, pady=(8, 0)
        )
        self.scrap_qty.bind("<Return>", lambda _event: self.create_scrap_hold())
        self.scrap_status = tb.Label(
            frame,
            text="移入報廢區的商品不會被出貨；滿三天後系統自動正式扣帳（開程式時與每小時檢查一次），"
                 "旁邊的按鈕只是不想等自動檢查時手動觸發用。",
            bootstyle="secondary",
        )
        self.scrap_status.pack(anchor=W, pady=(0, 8))
        holder = tb.Labelframe(frame, text="報廢暫存紀錄", bootstyle="danger", padding=8)
        holder.pack(fill=BOTH, expand=True)
        columns = ("id", "barcode", "name", "expiry", "qty", "source", "reason", "due", "status")
        self.scrap_tree = tb.Treeview(holder, columns=columns, show="headings", height=14, bootstyle="danger")
        headings = ("編號", "商品條碼", "商品名稱", "效期", "數量", "來源儲位", "原因", "正式扣帳時間", "狀態")
        widths = (60, 145, 200, 110, 70, 100, 230, 155, 105)
        self.setup_tree_columns(self.scrap_tree, columns, headings, widths, left_columns=("name", "reason"))
        self.add_table_interactions(self.scrap_tree, holder)
        self.add_tree_scrollbar(holder, self.scrap_tree)
        actions = tb.Frame(frame)
        actions.pack(fill=X, pady=(8, 0))
        tb.Button(actions, text="取消選取報廢（移回原儲位）", bootstyle="success", command=self.cancel_selected_scrap_hold).pack(side=LEFT)
        return frame

    def create_scrap_hold(self):
        qty_text = self.scrap_qty.get().strip()
        if not qty_text.isdigit():
            return self.set_status(self.scrap_status, "請輸入正確的報廢數量", "danger")
        try:
            hold_id, due_at = self.svc.returns.move_to_scrap_hold(
                self.scrap_source.get(), self.scrap_barcode.get(), self.scrap_expiry.get().strip(), int(qty_text),
                self.scrap_reason.get(), self.current_user,
            )
            for widget in (self.scrap_barcode, self.scrap_expiry, self.scrap_qty, self.scrap_reason):
                widget.delete(0, END)
            self.refresh_scrap_view()
            self.set_status(self.scrap_status, f"已建立報廢暫存 #{hold_id}；將於 {due_at} 正式扣帳", "success")
        except ValueError as error:
            self.set_status(self.scrap_status, str(error), "danger")

    def refresh_scrap_view(self):
        if not self.widget_alive("scrap_tree"):
            return
        self.clear_tree(self.scrap_tree)
        for row in self.svc.returns.all_scrap_holds():
            self.scrap_tree.insert("", END, values=(
                row["id"], row["barcode"], row["product_name"], row["expiry_date"], row["quantity"],
                row["source_shelf_code"], row["reason"], row["due_at"], status_label(row["status"]),
            ))

    def cancel_selected_scrap_hold(self):
        selected = self.scrap_tree.focus()
        if not selected:
            return self.set_status(self.scrap_status, "請先選取一筆報廢暫存紀錄", "warning")
        hold_id = int(self.scrap_tree.item(selected, "values")[0])
        if not messagebox.askyesno("取消報廢", "確定將此批商品移回原儲位嗎？"):
            return
        try:
            self.svc.returns.cancel_scrap_hold(hold_id, self.current_user)
            self.refresh_scrap_view()
            self.set_status(self.scrap_status, f"已取消報廢暫存 #{hold_id} 並移回原儲位", "success")
        except ValueError as error:
            self.set_status(self.scrap_status, str(error), "danger")

    def process_due_scrap_holds_ui(self):
        completed = self.svc.returns.process_due_scrap_holds(self.current_user or "SYSTEM")
        self.refresh_scrap_view()
        self.set_status(self.scrap_status, f"已完成 {len(completed)} 筆到期報廢正式扣帳", "success" if completed else "info")
