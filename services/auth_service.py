"""AuthService：登入驗證、帳號管理與權限判斷。"""
from utils.constants import PERMISSIONS, ROLES
from .base import BaseService


class AuthService(BaseService):
    _methods = (
        "login",
        "all_users",
        "create_user",
        "deactivate_user",
        "reset_user_password",
        "unlock_user",
        "recent_login_logs",
    )

    @staticmethod
    def has_permission(role, permission):
        """依角色檢查權限鍵；未知權限一律拒絕。"""
        if role not in ROLES:
            return False
        return role in PERMISSIONS.get(permission, ())
