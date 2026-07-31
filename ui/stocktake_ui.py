"""StocktakeUIMixin：盲盤平帳（庫存強制修改，僅系統管理員）。"""
from utils.constants import *
from utils.helpers import Utils

class StocktakeUIMixin:
    def build_counting_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "盤點平帳（管理員）", "直接把系統數量改成實際數量並留下差異紀錄；日常盤點請改用「動態盤點」")
        card = tb.Labelframe(frame, text="盲盤資料", bootstyle="warning", padding=16)
        card.pack(fill=X)
        self.cnt_shelf = tb.Combobox(card, width=12, state="normal")
        self.cnt_shelf.configure(values=self.svc.location.active_shelf_codes(include_special=True))
        self.cnt_barcode = tb.Entry(card, width=22)
        self.cnt_expiry = tb.Entry(card, width=16)
        self.cnt_qty = tb.Entry(card, width=10)
        fields = [
            ("儲位", self.cnt_shelf),
            ("商品條碼", self.cnt_barcode),
            ("效期", self.cnt_expiry),
            ("實際數量", self.cnt_qty),
        ]
        for column, (label, widget) in enumerate(fields):
            tb.Label(card, text=f"{label}:").grid(row=0, column=column * 2, sticky=W, padx=(4, 7), pady=6)
            widget.grid(row=0, column=column * 2 + 1, sticky=W, padx=(0, 14), pady=6)
        tb.Button(card, text="送出盤點", bootstyle="warning", command=self.process_counting).grid(row=0, column=8, padx=4)
        self.cnt_qty.bind("<Return>", lambda _event: self.process_counting())
        self.cnt_barcode.bind("<FocusOut>", self.refresh_counting_product_info)
        self.cnt_shelf.bind("<FocusOut>", self.refresh_counting_product_info)
        self.cnt_status = tb.Label(frame, text="無保存期限商品的效期欄可留白。", bootstyle="secondary")
        self.cnt_status.pack(anchor=W, pady=14)
        self.cnt_info_tree = self.build_product_info_panel(frame, "盤點商品確認")
        return frame

    def refresh_counting_product_info(self, _event=None):
        self.refresh_product_info_panel(self.cnt_info_tree, self.cnt_barcode.get(), self.cnt_shelf.get())

    def process_counting(self):
        if not self.has_perm("force_adjust_stock"):
            return self.set_status(self.cnt_status, "盲盤平帳（庫存強制修改）僅系統管理員可執行", "danger")
        shelf_code = self.cnt_shelf.get().strip().upper()
        barcode = Utils.normalize_barcode(self.cnt_barcode.get())
        expiry = self.cnt_expiry.get().strip()
        qty_text = self.cnt_qty.get().strip()
        self.refresh_product_info_panel(self.cnt_info_tree, barcode, shelf_code)
        if not shelf_code or not Utils.valid_barcode(barcode) or not qty_text.isdigit():
            return self.set_status(self.cnt_status, "請輸入正確的儲位、條碼與實際數量", "danger")
        shelf = self.svc.location.shelf_by_code(shelf_code)
        product = self.svc.product.product_by_barcode(barcode)
        if not shelf:
            return self.set_status(self.cnt_status, "儲位不存在", "danger")
        if not product:
            return self.set_status(self.cnt_status, "商品不存在，請先建立商品主檔", "danger")
        if product["expiry_required"]:
            valid, _expired, _days = Utils.validate_date(expiry)
            if not valid:
                return self.set_status(self.cnt_status, "效期格式錯誤，請輸入 YYYY-MM-DD", "danger")
        else:
            expiry = NO_EXPIRY_DATE
        real_qty = int(qty_text)
        if real_qty > 1000000:
            return self.set_status(self.cnt_status, "實際數量不可超過 1,000,000", "danger")

        system_qty = self.svc.inventory.inventory_qty(shelf_code, barcode, expiry)
        diff = real_qty - system_qty
        if diff == 0:
            return self.set_status(self.cnt_status, "盤點無差異，不需平帳", "success")
        if not messagebox.askyesno(
            "庫存調整確認",
            f"儲位 {shelf_code} 商品 {barcode}\n系統數量 {system_qty} -> 實際數量 {real_qty}（差異 {diff}）\n確定要平帳嗎？",
        ):
            return self.set_status(self.cnt_status, "已取消本次庫存調整", "secondary")

        try:
            system_qty, diff = self.svc.inventory.adjust_inventory_count(
                shelf_code, barcode, expiry, real_qty, self.current_user
            )
            self.set_status(self.cnt_status, f"平帳完成：系統 {system_qty} -> 實際 {real_qty}（差異 {diff}）", "warning")
            for widget in (self.cnt_barcode, self.cnt_expiry, self.cnt_qty):
                widget.delete(0, END)
            self.refresh_product_info_panel(self.cnt_info_tree, "", shelf_code)
            self.cnt_barcode.focus_set()
        except Exception as error:
            self.set_status(self.cnt_status, f"盤點失敗：{error}", "danger")
