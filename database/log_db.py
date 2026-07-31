"""LogDBMixin：庫存異動紀錄與操作紀錄。"""
from utils.constants import *
from utils.helpers import Utils


class LogDBMixin:
    def log_transaction(
        self,
        tx_type,
        barcode,
        from_shelf,
        to_shelf,
        before_qty,
        after_qty,
        change_qty,
        expiry_date,
        operator,
        reason="",
        order_no=None,
    ):
        self.cursor.execute(
            """
            INSERT INTO transactions
            (tx_type, barcode, from_shelf, to_shelf, before_qty, after_qty,
             change_qty, expiry_date, timestamp, operator, reason, order_no)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tx_type,
                barcode,
                from_shelf,
                to_shelf,
                before_qty,
                after_qty,
                change_qty,
                expiry_date,
                Utils.now_text(),
                operator,
                reason,
                order_no,
            ),
        )

    def log_operation(self, operator, action, order_no="", note=""):
        """操作紀錄。所有登入、單據建立／完成／取消等重要操作皆須可追蹤。"""
        self.cursor.execute(
            """
            INSERT INTO operation_logs (timestamp, operator, action, order_no, note)
            VALUES (?,?,?,?,?)
            """,
            (Utils.now_text(), operator, action, order_no or "", note or ""),
        )
        self.conn.commit()

    def recent_operation_logs(self, limit=300):
        return self.cursor.execute(
            """
            SELECT timestamp, operator, action, order_no, note
            FROM operation_logs ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def recent_transactions(self, limit=300):
        return self.cursor.execute(
            """
            SELECT timestamp, tx_type, order_no, barcode, from_shelf, to_shelf,
                   before_qty, after_qty, change_qty, expiry_date, operator, reason
            FROM transactions ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def recent_login_logs(self, limit=300):
        return self.cursor.execute(
            """
            SELECT timestamp, username, success, source, note
            FROM login_logs ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
