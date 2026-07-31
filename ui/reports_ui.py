"""ReportsUIMixin：統計報表（出貨統計、損耗統計）。"""
from utils.constants import *
from utils.helpers import Utils

class ReportsUIMixin:
    def build_reports_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "統計報表", "出貨與損耗彙總；任何表格按右鍵可匯出 Excel/CSV")

        range_card = tb.Labelframe(frame, text="統計區間", bootstyle="primary", padding=12)
        range_card.pack(fill=X, pady=(0, 10))
        tb.Button(range_card, text="今日", bootstyle="primary", command=lambda: self.set_report_range("today")).pack(side=LEFT, padx=(4, 4))
        tb.Button(range_card, text="本週", bootstyle="primary-outline", command=lambda: self.set_report_range("week")).pack(side=LEFT, padx=4)
        tb.Button(range_card, text="本月", bootstyle="primary-outline", command=lambda: self.set_report_range("month")).pack(side=LEFT, padx=4)
        tb.Label(range_card, text="　自訂：").pack(side=LEFT)
        self.report_from = tb.Entry(range_card, width=12)
        self.report_to = tb.Entry(range_card, width=12)
        self.report_from.pack(side=LEFT, padx=(0, 4))
        tb.Label(range_card, text="～").pack(side=LEFT)
        self.report_to.pack(side=LEFT, padx=(4, 8))
        tb.Button(range_card, text="查詢", bootstyle="secondary", command=self.refresh_reports_view).pack(side=LEFT, padx=4)
        self.report_to.bind("<Return>", lambda _event: self.refresh_reports_view())

        def report_range_text():
            try:
                date_from, date_to = self._report_range()
            except ValueError:
                return Utils.today_text()
            return date_from if date_from == date_to else f"{date_from}至{date_to}"

        self._report_range_text = report_range_text

        notebook = tb.Notebook(frame, bootstyle="primary")
        notebook.pack(fill=BOTH, expand=True)
        ship_tab = tb.Frame(notebook, padding=12)
        loss_tab = tb.Frame(notebook, padding=12)
        notebook.add(ship_tab, text=" 出貨統計 ")
        notebook.add(loss_tab, text=" 損耗統計 ")

        # ---- 出貨統計 ----
        ship_top = tb.Frame(ship_tab)
        ship_top.pack(fill=X, pady=(0, 8))
        self.report_ship_summary = tb.Label(ship_top, text="尚未查詢", font=("Microsoft JhengHei", 12, "bold"), bootstyle="primary")
        self.report_ship_summary.pack(side=LEFT)
        tb.Button(ship_top, text="匯出分店彙總 Excel/CSV", bootstyle="success-outline",
                  command=lambda: self.export_tree_csv(self.report_branch_tree, f"出貨統計_分店_{self._report_range_text()}")).pack(side=RIGHT, padx=4)
        tb.Button(ship_top, text="匯出商品彙總 Excel/CSV", bootstyle="success",
                  command=lambda: self.export_tree_csv(self.report_product_tree, f"出貨統計_商品_{self._report_range_text()}")).pack(side=RIGHT, padx=4)
        product_holder = tb.Labelframe(ship_tab, text="依商品彙總（出了什麼、出了多少）", bootstyle="info", padding=8)
        product_holder.pack(fill=BOTH, expand=True)
        columns = ("barcode", "name", "sku", "qty", "orders")
        self.report_product_tree = tb.Treeview(product_holder, columns=columns, show="headings", height=9, bootstyle="info")
        headings = ("商品條碼", "商品名稱", "SKU", "出貨件數", "出現單數")
        widths = (160, 260, 110, 100, 100)
        self.setup_tree_columns(self.report_product_tree, columns, headings, widths, left_columns=("name",))
        self.add_table_interactions(self.report_product_tree, product_holder)
        self.add_tree_scrollbar(product_holder, self.report_product_tree)

        branch_holder = tb.Labelframe(ship_tab, text="依分店彙總", bootstyle="secondary", padding=8)
        branch_holder.pack(fill=X, pady=(10, 0))
        branch_columns = ("branch", "orders", "qty")
        self.report_branch_tree = tb.Treeview(branch_holder, columns=branch_columns, show="headings", height=4, bootstyle="secondary")
        branch_headings = ("分店", "出貨單數", "出貨件數")
        branch_widths = (260, 110, 110)
        self.setup_tree_columns(self.report_branch_tree, branch_columns, branch_headings, branch_widths, left_columns=("branch",))
        self.add_table_interactions(self.report_branch_tree, branch_holder)
        self.add_tree_scrollbar(branch_holder, self.report_branch_tree)

        # ---- 損耗統計 ----
        loss_top = tb.Frame(loss_tab)
        loss_top.pack(fill=X, pady=(0, 8))
        self.report_loss_summary = tb.Label(loss_top, text="尚未查詢", font=("Microsoft JhengHei", 12, "bold"), bootstyle="danger")
        self.report_loss_summary.pack(side=LEFT)
        tb.Button(loss_top, text="匯出損耗明細 Excel/CSV", bootstyle="success",
                  command=lambda: self.export_tree_csv(self.report_loss_tree, f"損耗統計_{self._report_range_text()}")).pack(side=RIGHT, padx=4)
        loss_holder = tb.Labelframe(loss_tab, text="損耗明細（商品報廢＝三天期滿正式扣帳；含耗材報銷與盤點短少）", bootstyle="danger", padding=8)
        loss_holder.pack(fill=BOTH, expand=True)
        loss_columns = ("type", "barcode", "name", "qty", "cnt")
        self.report_loss_tree = tb.Treeview(loss_holder, columns=loss_columns, show="headings", height=13, bootstyle="danger")
        loss_headings = ("損耗類型", "商品條碼", "商品名稱", "損耗件數", "筆數")
        loss_widths = (110, 160, 260, 100, 80)
        self.setup_tree_columns(self.report_loss_tree, loss_columns, loss_headings, loss_widths, left_columns=("name",))
        self.report_loss_tree.tag_configure("scrap", background="#FDE2E1")
        self.add_table_interactions(self.report_loss_tree, loss_holder)
        self.add_tree_scrollbar(loss_holder, self.report_loss_tree)
        return frame

    # ---------- 區間 ----------

    def set_report_range(self, period):
        today = date.today()
        if period == "today":
            start = today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
        else:
            start = today.replace(day=1)
        for entry, value in ((self.report_from, start.isoformat()), (self.report_to, today.isoformat())):
            entry.delete(0, END)
            entry.insert(0, value)
        self.refresh_reports_view()

    def _report_range(self):
        date_from = self.report_from.get().strip()
        date_to = self.report_to.get().strip()
        if not date_from or not date_to:
            today = date.today().isoformat()
            return today, today
        for value in (date_from, date_to):
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"日期格式錯誤：{value}（請用 YYYY-MM-DD）")
        return date_from, date_to

    # ---------- 查詢 ----------

    def refresh_reports_view(self):
        if not self.report_from.get().strip():
            today = date.today().isoformat()
            self.report_from.insert(0, today)
            self.report_to.insert(0, today)
        try:
            date_from, date_to = self._report_range()
        except ValueError as error:
            return self.set_status(self.report_ship_summary, str(error), "danger")
        label = f"{date_from} ～ {date_to}" if date_from != date_to else date_from

        ship = self.svc.report.shipping_report(date_from, date_to)
        self.report_ship_summary.configure(
            text=f"{label}　共出貨 {ship['order_count']} 單、{ship['total_qty']} 件",
            bootstyle="primary",
        )
        self.clear_tree(self.report_product_tree)
        for row in ship["by_product"]:
            self.report_product_tree.insert(
                "", END,
                values=(row["barcode"], row["product_name"], row["sku"] or "-", row["qty"], row["orders"]),
            )
        self.clear_tree(self.report_branch_tree)
        for row in ship["by_branch"]:
            self.report_branch_tree.insert("", END, values=(row["branch"], row["orders"], row["qty"]))

        loss = self.svc.report.loss_report(date_from, date_to)
        totals = loss["totals"]
        total_text = "、".join(f"{key} {value} 件" for key, value in totals.items()) or "無損耗"
        self.report_loss_summary.configure(
            text=f"{label}　損耗合計：{total_text}", bootstyle="danger" if totals else "success",
        )
        self.clear_tree(self.report_loss_tree)
        for row in loss["rows"]:
            self.report_loss_tree.insert(
                "", END,
                values=(row["loss_type"], row["barcode"], row["name"], row["qty"], row["cnt"]),
                tags=("scrap",) if row["loss_type"] == "商品報廢" else (),
            )
