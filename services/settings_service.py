"""SettingsService：防呆／系統設定與印表機整合。"""
from utils import printing
from .base import BaseService


class SettingsService(BaseService):
    _methods = (
        "get_setting",
        "get_setting_bool",
        "get_setting_int",
        "set_setting",
        "all_settings",
    )

    @staticmethod
    def list_printers():
        return printing.list_printers()

    def print_product_label_tspl(self, barcode, name, sku, copies=1):
        """以 TSPL 直接列印商品內部條碼貼紙。"""
        payload = printing.tspl_product_label(
            self.database.get_setting("label_paper"), barcode, name, sku, copies,
        )
        printing.send_raw(self.database.get_setting("label_printer"), payload)

    def print_label_tspl(self, order_no, box_number, box_count,
                         branch_text, address_text, carrier, tracking_no, order_date):
        """以 TSPL 指令直接輸出一張箱標到設定的熱感貼紙印表機。"""
        payload = printing.tspl_box_label(
            self.database.get_setting("label_paper"),
            order_no, box_number, box_count,
            branch_text, address_text, carrier, tracking_no, order_date,
        )
        printing.send_raw(self.database.get_setting("label_printer"), payload)
