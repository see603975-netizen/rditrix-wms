"""BranchDBMixin：分店主檔。"""
from utils.constants import *


class BranchDBMixin:
    def active_branches(self):
        return self.cursor.execute(
            "SELECT * FROM branches WHERE active=1 ORDER BY code"
        ).fetchall()

    def branch_by_id(self, branch_id):
        return self.cursor.execute("SELECT * FROM branches WHERE id=?", (branch_id,)).fetchone()

    def branch_by_code(self, code):
        return self.cursor.execute("SELECT * FROM branches WHERE code=?", (code,)).fetchone()

    def save_branch(self, branch_id, code, name, address, contact_name, contact_phone, carrier):
        if branch_id:
            self.cursor.execute(
                """
                UPDATE branches
                SET code=?, name=?, address=?, contact_name=?, contact_phone=?, default_carrier=?
                WHERE id=?
                """,
                (code, name, address, contact_name, contact_phone, carrier, branch_id),
            )
        else:
            self.cursor.execute(
                """
                INSERT INTO branches (code, name, address, contact_name, contact_phone, default_carrier)
                VALUES (?,?,?,?,?,?)
                """,
                (code, name, address, contact_name, contact_phone, carrier),
            )
        self.conn.commit()
