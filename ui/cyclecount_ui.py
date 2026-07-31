"""CycleCountUIMixin：今日／本週／本月動態盤點（Cycle Count）。"""
from utils.constants import *
from utils.helpers import Utils

class CycleCountUIMixin:
    def build_cycle_count_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame, "動態盤點",
            "自動撈取當日／當週／當月有異動的儲位；正常品一鍵確認，只有異常品需要輸入數量",
        )

        create_card = tb.Labelframe(frame, text="步驟 1：建立盤點單", bootstyle="primary", padding=12)
        create_card.pack(fill=X, pady=(0, 10))
        self.cc_period = tb.Combobox(create_card, values=("當日", "當週", "當月"), width=8, state="readonly")
        self.cc_period.set("當日")
        tb.Label(create_card, text="盤點期間:").pack(side=LEFT, padx=(4, 6))
        self.cc_period.pack(side=LEFT, padx=(0, 12))
        tb.Button(create_card, text="建立盤點單（撈取異動儲位）", bootstyle="primary",
                  command=self.create_cycle_count).pack(side=LEFT, padx=4)
        tb.Button(create_card, text="列印盤點單（A4）", bootstyle="secondary",
                  command=lambda: self.print_cycle_count_document("A4")).pack(side=LEFT, padx=4)
        tb.Button(create_card, text="列印盤點單（熱感貼紙）", bootstyle="secondary",
                  command=lambda: self.print_cycle_count_document("LABEL")).pack(side=LEFT, padx=4)

        self.cc_status = tb.Label(frame, text="建立盤點單後可列印給現場人員手寫核對，再回來輸入結果。", bootstyle="secondary")
        self.cc_status.pack(anchor=W, pady=(0, 8))

        session_holder = tb.Labelframe(frame, text="盤點單清單", bootstyle="secondary", padding=8)
        session_holder.pack(fill=X, pady=(0, 10))
        session_columns = ("session_no", "period", "range", "status", "items", "counted", "diff", "created")
        self.cc_session_tree = tb.Treeview(session_holder, columns=session_columns, show="headings",
                                           height=5, bootstyle="secondary")
        session_headings = ("盤點單號", "期間", "日期範圍", "狀態", "品項數", "已輸入", "差異數", "建立時間")
        session_widths = (170, 70, 190, 90, 80, 80, 80, 150)
        self.setup_tree_columns(self.cc_session_tree, session_columns, session_headings, session_widths)
        self.cc_session_tree.tag_configure("done", background="#E1F5E7")
        self.cc_session_tree.bind("<<TreeviewSelect>>", self.show_cycle_count_items)
        self.add_table_interactions(self.cc_session_tree, session_holder)
        self.add_tree_scrollbar(session_holder, self.cc_session_tree)

        entry_card = tb.Labelframe(frame, text="步驟 2：輸入實盤（掃描儲位＋商品條碼；正常品可直接一鍵確認）",
                                   bootstyle="success", padding=12)
        entry_card.pack(fill=X, pady=(0, 10))
        self.cc_shelf = tb.Entry(entry_card, width=12)
        self.cc_barcode = tb.Entry(entry_card, width=20)
        self.cc_expiry = tb.Entry(entry_card, width=13)
        self.cc_qty = tb.Entry(entry_card, width=8)
        self.cc_note = tb.Entry(entry_card, width=20)
        # 小螢幕相容：分兩行排列，避免右側欄位與按鈕被裁切。
        fields = [
            ("儲位", self.cc_shelf, 0, 0), ("商品條碼", self.cc_barcode, 0, 2),
            ("效期（同品多批必填）", self.cc_expiry, 0, 4),
            ("實盤數量", self.cc_qty, 1, 0), ("異常備註", self.cc_note, 1, 2),
        ]
        for label, widget, row, column in fields:
            tb.Label(entry_card, text=f"{label}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=6)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 12), pady=6)
        tb.Button(entry_card, text="登記實盤", bootstyle="success", command=self.record_cycle_count_entry).grid(
            row=1, column=4, columnspan=2, sticky=W, padx=4)
        self.cc_qty.bind("<Return>", lambda _event: self.record_cycle_count_entry())
        action_bar = tb.Frame(entry_card)
        action_bar.grid(row=2, column=0, columnspan=6, sticky=W, pady=(8, 0))
        tb.Button(action_bar, text="一鍵全部正常（未輸入者視為帳實相符）", bootstyle="success-outline",
                  command=self.confirm_cycle_count_normal).pack(side=LEFT, padx=(2, 8))
        if self.has_perm("cycle_count_close"):
            tb.Button(action_bar, text="完成盤點並平帳差異（主管以上）", bootstyle="warning",
                      command=self.complete_cycle_count_session).pack(side=LEFT)

        items_holder = tb.Labelframe(frame, text="盤點明細（依儲位排序）", bootstyle="info", padding=8)
        items_holder.pack(fill=BOTH, expand=True)
        item_columns = ("shelf", "barcode", "name", "expiry", "system", "counted", "diff", "flag", "note")
        self.cc_item_tree = tb.Treeview(items_holder, columns=item_columns, show="headings",
                                        height=11, bootstyle="info")
        item_headings = ("儲位", "商品條碼", "商品名稱", "效期", "系統數量", "實盤數量", "差異", "狀態", "備註")
        item_widths = (90, 150, 220, 110, 90, 90, 70, 110, 160)
        self.setup_tree_columns(self.cc_item_tree, item_columns, item_headings, item_widths, left_columns=("name", "note"))
        self.cc_item_tree.tag_configure("diff", background="#FDE2E1")
        self.cc_item_tree.tag_configure("ok", background="#E1F5E7")
        self.add_table_interactions(self.cc_item_tree, items_holder)
        self.add_tree_scrollbar(items_holder, self.cc_item_tree)
        return frame

    # ---------- 動作 ----------

    def _selected_cycle_session(self):
        selected = self.cc_session_tree.focus()
        if not selected:
            return None
        return self.cc_session_tree.item(selected, "values")[0]

    def refresh_cycle_count_view(self):
        self.clear_tree(self.cc_session_tree)
        for row in self.svc.stocktake.cycle_count_sessions():
            self.cc_session_tree.insert(
                "", END,
                values=(
                    row["session_no"], row["period_type"],
                    f"{row['date_from']} ~ {row['date_to']}", row["status"],
                    row["item_count"], row["counted_count"] or 0, row["diff_count"] or 0,
                    row["created_at"],
                ),
                tags=("done",) if row["status"] == "已完成" else (),
            )
        self.clear_tree(self.cc_item_tree)

    def create_cycle_count(self):
        try:
            session_no, shelf_count = self.svc.stocktake.create_cycle_count_session(
                self.cc_period.get(), self.current_user
            )
            self.refresh_cycle_count_view()
            self.set_status(self.cc_status,
                            f"已建立盤點單 {session_no}（{shelf_count} 個異動儲位）；可直接列印或開始輸入實盤。",
                            "success")
        except ValueError as error:
            self.set_status(self.cc_status, str(error), "warning")

    def show_cycle_count_items(self, _event=None):
        session_no = self._selected_cycle_session()
        if not session_no:
            return
        self.clear_tree(self.cc_item_tree)
        for item in self.svc.stocktake.cycle_count_items(session_no):
            counted = item["counted_qty"]
            diff = "" if counted is None else counted - item["system_qty"]
            if counted is None:
                flag, tag = "未輸入", ""
            elif diff == 0:
                flag, tag = "帳實相符", "ok"
            else:
                flag, tag = "異常差異", "diff"
            self.cc_item_tree.insert(
                "", END,
                values=(
                    item["shelf_code"], item["barcode"], item["product_name"],
                    Utils.display_expiry(item["expiry_date"]), item["system_qty"],
                    "-" if counted is None else counted, diff, flag, item["note"] or "-",
                ),
                tags=(tag,) if tag else (),
            )

    def record_cycle_count_entry(self):
        session_no = self._selected_cycle_session()
        if not session_no:
            return self.set_status(self.cc_status, "請先在清單選取盤點單", "warning")
        qty_text = self.cc_qty.get().strip()
        if not qty_text.isdigit():
            return self.set_status(self.cc_status, "實盤數量必須是 0 以上的整數", "danger")
        try:
            system_qty, diff = self.svc.stocktake.record_cycle_count(
                session_no, self.cc_shelf.get(), self.cc_barcode.get(), int(qty_text),
                expiry_date=self.cc_expiry.get().strip() or None,
                note=self.cc_note.get(),
            )
            for widget in (self.cc_barcode, self.cc_expiry, self.cc_qty, self.cc_note):
                widget.delete(0, END)
            self.show_cycle_count_items()
            self.refresh_cycle_count_view_row(session_no)
            style = "success" if diff == 0 else "warning"
            self.set_status(self.cc_status,
                            f"已登記：系統 {system_qty}、實盤 {system_qty + diff}（差異 {diff}）", style)
            self.cc_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.cc_status, str(error), "danger")

    def refresh_cycle_count_view_row(self, session_no):
        """更新清單統計但保留選取狀態。"""
        selected = session_no
        self.refresh_cycle_count_view()
        for row_id in self.cc_session_tree.get_children():
            if self.cc_session_tree.item(row_id, "values")[0] == selected:
                self.cc_session_tree.selection_set(row_id)
                self.cc_session_tree.focus(row_id)
                self.show_cycle_count_items()
                break

    def confirm_cycle_count_normal(self):
        session_no = self._selected_cycle_session()
        if not session_no:
            return self.set_status(self.cc_status, "請先在清單選取盤點單", "warning")
        if not messagebox.askyesno(
            "一鍵全部正常",
            f"確定將盤點單 {session_no} 尚未輸入的品項全部視為帳實相符嗎？\n（異常品請先逐筆輸入實盤數量再執行）",
        ):
            return
        try:
            updated = self.svc.stocktake.confirm_cycle_count_all_normal(session_no, self.current_user)
            self.refresh_cycle_count_view_row(session_no)
            self.set_status(self.cc_status, f"已將 {updated} 筆未輸入品項確認為帳實相符。", "success")
        except ValueError as error:
            self.set_status(self.cc_status, str(error), "danger")

    def complete_cycle_count_session(self):
        if not self.has_perm("cycle_count_close"):
            return self.set_status(self.cc_status, "完成盤點與平帳需要倉庫主管以上權限", "danger")
        session_no = self._selected_cycle_session()
        if not session_no:
            return self.set_status(self.cc_status, "請先在清單選取盤點單", "warning")
        if not messagebox.askyesno(
            "完成盤點",
            f"確定完成盤點單 {session_no} 嗎？\n差異品項會自動平帳並寫入盤點調整紀錄。",
        ):
            return
        try:
            adjusted = self.svc.stocktake.complete_cycle_count(session_no, self.current_user)
            self.refresh_cycle_count_view_row(session_no)
            self.refresh_inventory()
            self.set_status(self.cc_status, f"盤點單 {session_no} 已完成，平帳 {adjusted} 筆差異。", "success")
        except ValueError as error:
            self.set_status(self.cc_status, str(error), "danger")

    # ---------- 列印 ----------

    def print_cycle_count_document(self, paper_mode="A4"):
        """列印盤點單：A4 全表或熱感貼紙逐儲位；按儲位順序排列供現場手寫核對。"""
        session_no = self._selected_cycle_session()
        if not session_no:
            return self.set_status(self.cc_status, "請先在清單選取要列印的盤點單", "warning")
        session = self.svc.stocktake.cycle_count_session(session_no)
        items = self.svc.stocktake.cycle_count_items(session_no)
        if not items:
            return self.set_status(self.cc_status, "此盤點單沒有明細", "warning")
        print_count = self.svc.stocktake.mark_cycle_count_printed(session_no)
        self.svc.log.log_operation(self.current_user, "列印盤點單", session_no,
                                   f"{paper_mode}，第 {print_count} 次")
        if paper_mode == "LABEL":
            label_width, label_height = self.svc.settings.get_setting("label_paper").split("x")
            page_css = f"@page {{ size: {label_width}mm {label_height}mm; margin:4mm; }}"
            sections = []
            current_shelf, rows = None, []

            def flush():
                if current_shelf is None:
                    return
                sections.append(
                    f"<section class='label'><h2>儲位 {html.escape(current_shelf)}</h2>"
                    f"<div class='meta'>{html.escape(session_no)}｜{html.escape(session['period_type'])}盤點</div>"
                    "<table><thead><tr><th>商品</th><th>效期</th><th>帳量</th><th>實盤</th></tr></thead>"
                    f"<tbody>{''.join(rows)}</tbody></table></section>"
                )

            for item in items:
                if item["shelf_code"] != current_shelf:
                    flush()
                    current_shelf, rows = item["shelf_code"], []
                rows.append(
                    f"<tr><td>{html.escape(item['product_name'])}<br><small>{html.escape(item['barcode'])}</small></td>"
                    f"<td>{html.escape(Utils.display_expiry(item['expiry_date']))}</td>"
                    f"<td class='qty'>{item['system_qty']}</td><td class='fill'></td></tr>"
                )
            flush()
            body = "".join(sections)
            style = (
                f"{page_css} body{{margin:0;font-family:'Microsoft JhengHei',Arial,sans-serif;font-size:10px;}}"
                ".label{page-break-after:always;padding:2mm;}.label:last-child{page-break-after:auto;}"
                "h2{margin:0 0 2mm;font-size:15px;} .meta{color:#555;margin-bottom:2mm;}"
                "table{width:100%;border-collapse:collapse;}th,td{border:1px solid #999;padding:3px;text-align:left;}"
                "td.qty{text-align:center;} td.fill{min-width:14mm;}"
            )
        else:
            report_paper = self.svc.settings.get_setting("report_paper") or "A4"
            page_css = f"@page {{ size: {report_paper}; margin: 12mm; }}"
            rows = []
            for item in items:
                rows.append(
                    "<tr>"
                    f"<td>{html.escape(item['shelf_code'])}</td>"
                    f"<td>{html.escape(item['barcode'])}</td>"
                    f"<td>{html.escape(item['product_name'])}</td>"
                    f"<td>{html.escape(Utils.display_expiry(item['expiry_date']))}</td>"
                    f"<td class='qty'>{item['system_qty']}</td>"
                    "<td class='fill'></td><td class='fill'></td>"
                    "</tr>"
                )
            body = f"""<div class="sheet">
<h1>動態盤點單</h1>
<div class="info">
<span><b>盤點單號：</b>{html.escape(session_no)}</span>
<span><b>期間：</b>{html.escape(session['period_type'])}（{html.escape(session['date_from'])} ~ {html.escape(session['date_to'])}）</span>
<span><b>建立人：</b>{html.escape(session['created_by'])}</span>
<span><b>列印時間：</b>{Utils.now_text()}</span>
</div>
<table><thead><tr><th>儲位</th><th>商品條碼</th><th>商品名稱</th><th>效期</th><th>帳上數量</th><th>實盤數量</th><th>差異／備註</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<div class="footer">正常品免填實盤數量，回系統按「一鍵全部正常」；僅異常品需填寫實盤數量與備註。</div>
</div>"""
            style = (
                f"{page_css} body{{font-family:'Microsoft JhengHei',Arial,sans-serif;font-size:12px;color:#172033;}}"
                ".sheet{max-width:190mm;margin:auto;} h1{font-size:24px;border-bottom:2px solid #1f5eff;padding-bottom:8px;}"
                ".info{display:flex;flex-wrap:wrap;gap:8px 26px;margin:10px 0 14px;}"
                "table{width:100%;border-collapse:collapse;}th{background:#eaf0ff;}"
                "th,td{border:1px solid #aebbd0;padding:7px;text-align:left;}td.qty{text-align:center;font-weight:bold;}"
                "td.fill{min-width:22mm;} .footer{margin-top:14px;color:#56657f;}"
            )
        content = (f"<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
                   f"<title>{html.escape(session_no)} 盤點單</title><style>{style}</style></head>"
                   f"<body>{body}</body></html>")
        self.write_print_file(f"{session_no}_盤點單_{print_count}.html", content)
        self.set_status(self.cc_status, f"已開啟盤點單 {session_no} 列印頁面（{paper_mode}）。", "success")
