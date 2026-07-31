"""BranchUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *

class BranchUIMixin:
    def build_branch_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "分店管理", "維護分店名稱、地址、聯絡人與預設物流方式")

        form = tb.Labelframe(frame, text="分店資料", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 12))
        self.branch_code = tb.Entry(form, width=16)
        self.branch_name = tb.Entry(form, width=24)
        self.branch_address = tb.Entry(form, width=44)
        self.branch_contact = tb.Entry(form, width=16)
        self.branch_phone = tb.Entry(form, width=18)
        self.branch_carrier = tb.Combobox(form, values=CARRIERS, width=16, state="readonly")
        self.branch_carrier.set("未指定")

        fields = [
            ("分店代碼", self.branch_code, 0, 0),
            ("分店名稱", self.branch_name, 0, 2),
            ("地址", self.branch_address, 1, 0),
            ("聯絡人", self.branch_contact, 2, 0),
            ("電話", self.branch_phone, 2, 2),
            ("預設物流", self.branch_carrier, 2, 4),
        ]
        for text, widget, row, column in fields:
            tb.Label(form, text=f"{text}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=7)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 18), pady=7)

        tb.Button(form, text="儲存分店", bootstyle="primary", command=self.save_branch_from_form).grid(
            row=0, column=4, padx=8, pady=7
        )
        tb.Button(form, text="清除欄位", bootstyle="secondary", command=self.clear_branch_form).grid(
            row=1, column=4, padx=8, pady=7
        )

        columns = ("code", "name", "address", "contact", "phone", "carrier")
        self.branch_tree = tb.Treeview(frame, columns=columns, show="headings", height=18, bootstyle="primary")
        headings = ("分店代碼", "分店名稱", "地址", "聯絡人", "電話", "預設物流")
        widths = (120, 180, 380, 120, 150, 150)
        self.setup_tree_columns(self.branch_tree, columns, headings, widths, left_columns=("name", "address"))
        self.branch_tree.bind("<<TreeviewSelect>>", self.on_branch_select)
        self.add_table_interactions(self.branch_tree, frame)
        self.add_tree_scrollbar(frame, self.branch_tree)
        return frame

    def clear_branch_form(self):
        self.branch_selected_id = None
        for widget in (
            self.branch_code,
            self.branch_name,
            self.branch_address,
            self.branch_contact,
            self.branch_phone,
        ):
            widget.delete(0, END)
        self.branch_carrier.set("未指定")
        self.branch_code.focus_set()

    def on_branch_select(self, _event=None):
        selected = self.branch_tree.focus()
        if not selected:
            return
        values = self.branch_tree.item(selected, "values")
        code = values[0]
        row = self.svc.branch.branch_by_code(code)
        if not row:
            return
        self.branch_selected_id = row["id"]
        mapping = {
            self.branch_code: row["code"],
            self.branch_name: row["name"],
            self.branch_address: row["address"] or "",
            self.branch_contact: row["contact_name"] or "",
            self.branch_phone: row["contact_phone"] or "",
        }
        for widget, value in mapping.items():
            widget.delete(0, END)
            widget.insert(0, value)
        self.branch_carrier.set(row["default_carrier"] or "未指定")

    def save_branch_from_form(self):
        try:
            code = self.branch_code.get().strip().upper()
            name = self.branch_name.get().strip()
            if not re.fullmatch(r"[A-Z0-9-]{2,20}", code):
                raise ValueError("分店代碼限英文、數字與連字號，長度 2 至 20 碼")
            if not name:
                raise ValueError("分店名稱為必填")
            self.svc.branch.save_branch(
                self.branch_selected_id,
                code,
                name,
                self.branch_address.get().strip(),
                self.branch_contact.get().strip(),
                self.branch_phone.get().strip(),
                self.branch_carrier.get() or "未指定",
            )
            self.refresh_branches()
            self.clear_branch_form()
            messagebox.showinfo("完成", f"分店「{name}」已儲存")
        except (ValueError, sqlite3.IntegrityError) as error:
            messagebox.showerror("無法儲存分店", str(error))

    def refresh_branches(self):
        self.clear_tree(self.branch_tree)
        rows = self.svc.branch.active_branches()
        for row in rows:
            self.branch_tree.insert(
                "",
                END,
                values=(
                    row["code"],
                    row["name"],
                    row["address"] or "-",
                    row["contact_name"] or "-",
                    row["contact_phone"] or "-",
                    row["default_carrier"],
                ),
            )
        self.refresh_branch_choices()
