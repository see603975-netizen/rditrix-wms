"""LogService：操作紀錄、庫存異動與登入日誌查詢。"""
from .base import BaseService


class LogService(BaseService):
    _methods = (
        "log_operation",
        "recent_operation_logs",
        "recent_transactions",
        "recent_login_logs",
    )
