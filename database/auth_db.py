"""AuthDBMixin：帳號、角色、登入驗證、登入日誌與防暴力破解鎖定。"""
import socket

from utils.constants import *
from utils.helpers import Utils


class AuthDBMixin:
    # ---------- 登入 ----------

    def _login_source(self):
        try:
            return socket.gethostname()
        except OSError:
            return "unknown"

    def _record_login(self, username, success, note=""):
        self.cursor.execute(
            """
            INSERT INTO login_logs (timestamp, username, success, source, note)
            VALUES (?,?,?,?,?)
            """,
            (Utils.now_text(), username, int(success), self._login_source(), note),
        )
        self.conn.commit()

    def _lockout_row(self, username):
        return self.cursor.execute(
            "SELECT * FROM login_lockouts WHERE username=?", (username,)
        ).fetchone()

    def _register_login_failure(self, username):
        """登入失敗累計；達上限即鎖定並標記警告。回傳（已鎖定, 提示訊息）。"""
        row = self._lockout_row(username)
        failed = (row["failed_attempts"] if row else 0) + 1
        locked_until = None
        note = f"登入失敗（第 {failed} 次）"
        if failed >= LOGIN_MAX_FAILURES:
            locked_until = (
                datetime.now() + timedelta(minutes=LOGIN_LOCK_MINUTES)
            ).strftime("%Y-%m-%d %H:%M:%S")
            note = (
                f"⚠ 連續登入失敗達 {LOGIN_MAX_FAILURES} 次，"
                f"帳號鎖定 {LOGIN_LOCK_MINUTES} 分鐘（至 {locked_until}）"
            )
        self.cursor.execute(
            """
            INSERT INTO login_lockouts (username, failed_attempts, locked_until, warned)
            VALUES (?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET
                failed_attempts=excluded.failed_attempts,
                locked_until=excluded.locked_until,
                warned=excluded.warned
            """,
            (username, failed if not locked_until else 0, locked_until, int(bool(locked_until))),
        )
        self.conn.commit()
        self._record_login(username, False, note)
        return bool(locked_until), note

    def _clear_login_failures(self, username):
        self.cursor.execute("DELETE FROM login_lockouts WHERE username=?", (username,))
        self.conn.commit()

    def login(self, username, password):
        """驗證帳密並回傳使用者資料 dict；失敗一律丟 ValueError（訊息可直接顯示）。"""
        username = (username or "").strip()
        if not username or not password:
            raise ValueError("請輸入帳號與密碼")

        lockout = self._lockout_row(username)
        if lockout and lockout["locked_until"]:
            if lockout["locked_until"] > Utils.now_text():
                self._record_login(username, False, "帳號鎖定期間嘗試登入")
                raise ValueError(
                    f"此帳號因連續登入失敗已被鎖定，請於 {lockout['locked_until']} 後再試"
                )
            self._clear_login_failures(username)

        user = self.cursor.execute(
            "SELECT * FROM users WHERE username=? AND active=1", (username,)
        ).fetchone()
        if not user or not Utils.verify_password(password, user["password_hash"]):
            locked, _note = self._register_login_failure(username)
            if locked:
                raise ValueError(
                    f"帳號或密碼錯誤；已連續失敗 {LOGIN_MAX_FAILURES} 次，"
                    f"帳號鎖定 {LOGIN_LOCK_MINUTES} 分鐘"
                )
            raise ValueError("帳號或密碼錯誤，請重新輸入")

        self._clear_login_failures(username)
        self._record_login(username, True, f"角色：{ROLE_LABELS.get(user['role'], user['role'])}")
        return {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        }

    # ---------- 帳號管理（僅系統管理員可呼叫；UI 與服務層雙重把關） ----------

    def all_users(self, include_inactive=False):
        query = "SELECT id, username, display_name, role, active, locked_until, created_at, created_by FROM users"
        if not include_inactive:
            query += " WHERE active=1"
        query += " ORDER BY role DESC, username"
        return self.cursor.execute(query).fetchall()

    def create_user(self, username, password, display_name, role, operator):
        username = (username or "").strip()
        display_name = (display_name or "").strip() or username
        if not re.fullmatch(r"[A-Za-z0-9]{3,20}", username):
            raise ValueError("帳號限英文字母與數字，長度 3 至 20 碼")
        if len(password or "") < 6:
            raise ValueError("密碼至少 6 碼")
        if role not in ROLES:
            raise ValueError("角色無效，請選擇 現場作業員／倉庫主管／系統管理員")
        existing = self.cursor.execute(
            "SELECT id, active FROM users WHERE username=?", (username,)
        ).fetchone()
        if existing and existing["active"]:
            raise ValueError(f"帳號 {username} 已存在")
        if existing:
            self.cursor.execute(
                """
                UPDATE users SET password_hash=?, display_name=?, role=?, active=1,
                       failed_attempts=0, locked_until=NULL, created_at=?, created_by=?
                WHERE id=?
                """,
                (Utils.hash_password(password), display_name, role,
                 Utils.now_text(), operator, existing["id"]),
            )
        else:
            self.cursor.execute(
                """
                INSERT INTO users
                (username, password_hash, display_name, role, active, created_at, created_by)
                VALUES (?,?,?,?,1,?,?)
                """,
                (username, Utils.hash_password(password), display_name, role,
                 Utils.now_text(), operator),
            )
        self.conn.commit()
        self.log_operation(operator, "建立帳號", username,
                           f"{display_name}（{ROLE_LABELS.get(role, role)}）")

    def deactivate_user(self, username, operator):
        """刪除帳號＝停用（保留操作紀錄可追溯）；不可刪除自己與最後一位管理員。"""
        username = (username or "").strip()
        user = self.cursor.execute(
            "SELECT * FROM users WHERE username=? AND active=1", (username,)
        ).fetchone()
        if not user:
            raise ValueError("查無此帳號")
        if user["role"] == ROLE_ADMIN:
            admin_count = self.cursor.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE role='ADMIN' AND active=1"
            ).fetchone()["cnt"]
            if admin_count <= 1:
                raise ValueError("至少需保留一位系統管理員帳號，不可刪除")
        self.cursor.execute("UPDATE users SET active=0 WHERE id=?", (user["id"],))
        self.conn.commit()
        self.log_operation(operator, "刪除帳號", username, user["display_name"])

    def reset_user_password(self, username, new_password, operator):
        if len(new_password or "") < 6:
            raise ValueError("密碼至少 6 碼")
        user = self.cursor.execute(
            "SELECT id FROM users WHERE username=? AND active=1", (username,)
        ).fetchone()
        if not user:
            raise ValueError("查無此帳號")
        self.cursor.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (Utils.hash_password(new_password), user["id"]),
        )
        self.conn.commit()
        self._clear_login_failures(username)
        self.log_operation(operator, "重設密碼", username)

    def unlock_user(self, username, operator):
        self._clear_login_failures(username)
        self.log_operation(operator, "解除帳號鎖定", username)
