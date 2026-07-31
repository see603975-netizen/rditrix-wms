"""AccountUIMixin：帳號管理（僅系統管理員；選單也僅管理員可見）。"""
from utils.constants import *
from utils.helpers import Utils

class AccountUIMixin:
    def build_account_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "帳號管理", "建立／停用帳號、指派角色、重設密碼與解除鎖定（僅系統管理員）")

        form = tb.Labelframe(frame, text="建立新帳號", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 10))
        self.account_username = tb.Entry(form, width=18)
        self.account_password = tb.Entry(form, width=18, show="*")
        self.account_display = tb.Entry(form, width=18)
        self.account_role = tb.Combobox(
            form, width=14, state="readonly",
            values=[f"{role}｜{ROLE_LABELS[role]}" for role in ROLES],
        )
        self.account_role.set(f"{ROLE_OPERATOR}｜{ROLE_LABELS[ROLE_OPERATOR]}")
        fields = [
            ("帳號（英數 3-20 碼）", self.account_username),
            ("密碼（至少 6 碼）", self.account_password),
            ("顯示名稱", self.account_display),
            ("角色", self.account_role),
        ]
        for column, (label, widget) in enumerate(fields):
            tb.Label(form, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=6)
        tb.Button(form, text="建立帳號", bootstyle="primary", command=self.create_account).grid(row=0, column=8, padx=6)

        self.account_status = tb.Label(
            frame,
            text=f"角色權限：{ROLE_LABELS[ROLE_OPERATOR]}＝現場作業；{ROLE_LABELS[ROLE_SUPERVISOR]}＝加開單據／調撥／盤點平帳；{ROLE_LABELS[ROLE_ADMIN]}＝全功能。",
            bootstyle="secondary",
        )
        self.account_status.pack(anchor=W, pady=(0, 8))

        holder = tb.Labelframe(frame, text="帳號清單", bootstyle="secondary", padding=8)
        holder.pack(fill=BOTH, expand=True)
        columns = ("username", "display", "role", "locked", "created", "creator")
        self.account_tree = tb.Treeview(holder, columns=columns, show="headings", height=12, bootstyle="secondary")
        headings = ("帳號", "顯示名稱", "角色", "鎖定狀態", "建立時間", "建立者")
        widths = (130, 150, 140, 170, 150, 110)
        self.setup_tree_columns(self.account_tree, columns, headings, widths)
        self.account_tree.tag_configure("locked", background="#FDE2E1")
        self.add_table_interactions(self.account_tree, holder)
        self.add_tree_scrollbar(holder, self.account_tree)

        actions = tb.Frame(frame)
        actions.pack(fill=X, pady=(8, 0))
        tb.Button(actions, text="刪除（停用）選取帳號", bootstyle="danger", command=self.deactivate_account).pack(side=LEFT)
        tb.Button(actions, text="重設密碼", bootstyle="warning", command=self.reset_account_password).pack(side=LEFT, padx=8)
        tb.Button(actions, text="解除鎖定", bootstyle="success", command=self.unlock_account).pack(side=LEFT)
        return frame

    def refresh_account_view(self):
        if not self.has_perm("manage_accounts"):
            return
        self.clear_tree(self.account_tree)
        now = Utils.now_text()
        for row in self.svc.auth.all_users():
            locked = row["locked_until"] if row["locked_until"] and row["locked_until"] > now else ""
            self.account_tree.insert(
                "", END,
                values=(
                    row["username"], row["display_name"],
                    ROLE_LABELS.get(row["role"], row["role"]),
                    f"鎖定至 {locked}" if locked else "正常",
                    row["created_at"] or "-", row["created_by"] or "-",
                ),
                tags=("locked",) if locked else (),
            )

    def _selected_account(self):
        selected = self.account_tree.focus()
        if not selected:
            return None
        return self.account_tree.item(selected, "values")[0]

    def create_account(self):
        if not self.has_perm("manage_accounts"):
            return self.set_status(self.account_status, "僅系統管理員可管理帳號", "danger")
        role = (self.account_role.get() or "").split("｜", 1)[0]
        try:
            self.svc.auth.create_user(
                self.account_username.get(), self.account_password.get(),
                self.account_display.get(), role, self.current_user,
            )
            username = self.account_username.get().strip()
            for widget in (self.account_username, self.account_password, self.account_display):
                widget.delete(0, END)
            self.refresh_account_view()
            self.set_status(self.account_status, f"已建立帳號 {username}（{ROLE_LABELS.get(role, role)}）", "success")
        except ValueError as error:
            self.set_status(self.account_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.account_status, f"建立失敗：{error}", "danger")

    def deactivate_account(self):
        username = self._selected_account()
        if not username:
            return self.set_status(self.account_status, "請先選取帳號", "warning")
        if username == self.current_username:
            return self.set_status(self.account_status, "不可刪除目前登入中的帳號", "danger")
        if not messagebox.askyesno("刪除帳號", f"確定要停用帳號 {username} 嗎？\n（保留歷史操作紀錄，可再重新建立）"):
            return
        try:
            self.svc.auth.deactivate_user(username, self.current_user)
            self.refresh_account_view()
            self.set_status(self.account_status, f"帳號 {username} 已停用", "success")
        except ValueError as error:
            self.set_status(self.account_status, str(error), "danger")

    def reset_account_password(self):
        username = self._selected_account()
        if not username:
            return self.set_status(self.account_status, "請先選取帳號", "warning")
        dialog = tb.Toplevel(self.root)
        dialog.title(f"重設密碼 - {username}")
        dialog.transient(self.root)
        dialog.grab_set()
        body = tb.Frame(dialog, padding=18)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text=f"輸入 {username} 的新密碼（至少 6 碼）:").pack(anchor=W, pady=(0, 8))
        password_entry = tb.Entry(body, width=26, show="*")
        password_entry.pack(anchor=W)
        status = tb.Label(body, text="", bootstyle="danger")
        status.pack(anchor=W, pady=(6, 0))

        def confirm():
            try:
                self.svc.auth.reset_user_password(username, password_entry.get(), self.current_user)
            except ValueError as error:
                return status.configure(text=str(error))
            dialog.destroy()
            self.set_status(self.account_status, f"帳號 {username} 密碼已重設", "success")

        bar = tb.Frame(body)
        bar.pack(fill=X, pady=(12, 0))
        tb.Button(bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT, padx=(8, 0))
        tb.Button(bar, text="確認重設", bootstyle="warning", command=confirm).pack(side=RIGHT)
        password_entry.focus_set()

    def unlock_account(self):
        username = self._selected_account()
        if not username:
            return self.set_status(self.account_status, "請先選取帳號", "warning")
        self.svc.auth.unlock_user(username, self.current_user)
        self.refresh_account_view()
        self.set_status(self.account_status, f"帳號 {username} 已解除鎖定", "success")
