"""Shared date, text and validation helper functions."""
from .constants import *


class Utils:
    """輸入與日期相關的小工具。"""

    @staticmethod
    def now_text():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def today_text():
        return date.today().isoformat()

    @staticmethod
    def normalize_barcode(value):
        return value.strip().upper()

    @staticmethod
    def valid_barcode(value):
        # 可支援一般 EAN 數字條碼，也保留英數混合的 Code 128 商品碼。
        return bool(re.fullmatch(r"[A-Z0-9-]{3,64}", value))

    @staticmethod
    def valid_sku(value):
        """SKU 僅限英文字母與數字（不可中文、空白或符號），1 至 32 碼。"""
        return bool(re.fullmatch(r"[A-Za-z0-9]{1,32}", value or ""))

    @staticmethod
    def valid_shelf_code(value):
        """階層式儲位格式，例如 A01-03（區域-貨架-層位）。"""
        return bool(re.fullmatch(r"[A-Z]\d{2}-\d{2}", value))

    @staticmethod
    def validate_date(date_text):
        """回傳 (格式有效, 已過期, 剩餘天數)。效期當天仍可使用。"""
        try:
            expiry = datetime.strptime(date_text, "%Y-%m-%d").date()
            days = (expiry - date.today()).days
            return True, days < 0, days
        except ValueError:
            return False, False, 0

    @staticmethod
    def is_no_expiry(expiry_date):
        return expiry_date in ("", None, NO_EXPIRY_DATE)

    @staticmethod
    def display_expiry(expiry_date, expiry_required=True):
        if not expiry_required or Utils.is_no_expiry(expiry_date):
            return "無效期"
        return expiry_date

    # ---------- 密碼雜湊（帳號系統用；不儲存明碼） ----------

    @staticmethod
    def hash_password(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
        ).hex()
        return f"{salt}${digest}"

    @staticmethod
    def verify_password(password, stored):
        try:
            salt, _digest = stored.split("$", 1)
        except (AttributeError, ValueError):
            return False
        return secrets.compare_digest(Utils.hash_password(password, salt), stored)
