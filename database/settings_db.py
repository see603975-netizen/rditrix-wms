"""SettingsDBMixin：系統／防呆設定的 key-value 存取。"""
from utils.constants import *


class SettingsDBMixin:
    def get_setting(self, key):
        row = self.cursor.execute(
            "SELECT value FROM app_settings WHERE key=?", (key,)
        ).fetchone()
        if row is not None:
            return row["value"]
        return SETTING_DEFAULTS.get(key, "")

    def get_setting_bool(self, key):
        return self.get_setting(key) in ("1", "true", "True", "on")

    def get_setting_int(self, key, fallback=0):
        try:
            return int(self.get_setting(key))
        except (TypeError, ValueError):
            return fallback

    def set_setting(self, key, value):
        if key not in SETTING_DEFAULTS:
            raise ValueError(f"未知的設定項目：{key}")
        self.cursor.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, str(value)),
        )
        self.conn.commit()

    def all_settings(self):
        stored = {
            row["key"]: row["value"]
            for row in self.cursor.execute("SELECT key, value FROM app_settings").fetchall()
        }
        return {**SETTING_DEFAULTS, **stored}

    def excluded_zones(self):
        """可配貨庫存要排除的特殊區；無儲位模式下未上架（Staging）視為可配貨。"""
        if self.get_setting_bool("no_location_mode"):
            return ("QC", "Scrap", "Outbound")
        return ("Staging", "QC", "Scrap", "Outbound")
