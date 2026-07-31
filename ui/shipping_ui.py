"""ShippingUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class ShippingUIMixin:
    def build_shipping_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "出貨作業", "先掃出貨單條碼，再逐項掃商品；全部掃描足額後會自動完成包裝、扣庫存並列印箱標")
        load_card = tb.Labelframe(frame, text="步驟 1：掃描出貨單", bootstyle="primary", padding=14)
        load_card.pack(fill=X, pady=(0, 10))
        self.pack_order_no = tb.Entry(load_card, width=30)
        tb.Label(load_card, text="出貨單條碼:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.pack_order_no.grid(row=0, column=1, sticky=W, padx=(0, 12), pady=4)
        tb.Button(load_card, text="讀取出貨單", bootstyle="primary", command=self.load_order_for_packing).grid(row=0, column=2, padx=4)
        self.pack_order_no.bind("<Return>", lambda _event: self.load_order_for_packing())

        self.pack_summary = tb.Label(frame, text="尚未讀取出貨單", font=("Microsoft JhengHei", 11), bootstyle="secondary")
        self.pack_summary.pack(anchor=W, pady=(0, 10))

        columns = ("line", "barcode", "name", "allocation", "required", "scanned", "remaining", "status")
        shipping_body = tb.Frame(frame)
        shipping_body.pack(fill=BOTH, expand=True)
        tree_holder = tb.Frame(shipping_body)
        self.pack_tree = tb.Treeview(tree_holder, columns=columns, show="headings", height=14, bootstyle="primary")
        headings = ("#", "商品條碼", "商品名稱", "建議儲位／批次", "應出", "已掃", "剩餘", "狀態")
        widths = (50, 160, 210, 370, 80, 80, 80, 110)
        self.setup_tree_columns(self.pack_tree, columns, headings, widths, left_columns=("name", "allocation"))
        self.pack_tree.tag_configure("done", background="#E1F5E7")
        tree_holder.grid(row=0, column=0, sticky="nsew")
        self.add_table_interactions(self.pack_tree, tree_holder)
        self.add_tree_scrollbar(tree_holder, self.pack_tree)

        scan_card = tb.Labelframe(shipping_body, text="步驟 2：掃描箱內商品", bootstyle="success", padding=14)
        scan_card.grid(row=1, column=0, sticky=EW, pady=12)
        self.pack_item_barcode = tb.Entry(scan_card, width=28)
        self.pack_scan_qty = tb.Entry(scan_card, width=8)
        self.pack_scan_qty.insert(0, "1")
        tb.Label(scan_card, text="商品條碼:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=4)
        self.pack_item_barcode.grid(row=0, column=1, sticky=W, padx=(0, 15), pady=4)
        tb.Label(scan_card, text="本次數量:").grid(row=0, column=2, sticky=W, padx=(4, 8), pady=4)
        self.pack_scan_qty.grid(row=0, column=3, sticky=W, padx=(0, 15), pady=4)
        self.pack_scan_button = tb.Button(scan_card, text="確認掃描", bootstyle="success", command=self.scan_packing_item)
        self.pack_scan_button.grid(row=0, column=4, padx=4)
        self.pack_item_barcode.bind("<Return>", lambda _event: self.scan_packing_item())
        self.pack_scan_qty.bind("<Return>", lambda _event: self.scan_packing_item())

        action_bar = tb.Frame(shipping_body)
        action_bar.grid(row=2, column=0, sticky=EW)
        self.pack_complete_button = tb.Button(action_bar, text="手動完成包裝並扣庫存（備援，一般會自動觸發）", bootstyle="primary", command=self.complete_current_packing)
        self.pack_complete_button.pack(side=RIGHT)
        tb.Button(action_bar, text="補印箱標（需填原因）", bootstyle="warning", command=self.reprint_current_label).pack(side=RIGHT, padx=8)
        self.pack_quick_button = tb.Button(action_bar, text="一鍵完成驗貨（人工點數）", bootstyle="success-outline", command=self.quick_pack_current_order)
        self.pack_quick_button.pack(side=LEFT)
        self.pack_reset_button = tb.Button(action_bar, text="商品歸零", bootstyle="danger-outline", command=self.reset_current_packing_scan)
        self.pack_reset_button.pack(side=RIGHT, padx=8)
        self.pack_status = tb.Label(shipping_body, text="商品一次掃一件；整箱商品可輸入本次數量。全部掃描足額後會自動完成包裝並列印箱標。", bootstyle="secondary")
        self.pack_status.grid(row=3, column=0, sticky=W, pady=(10, 0))
        shipping_body.columnconfigure(0, weight=1)
        shipping_body.rowconfigure(0, weight=1)
        return frame

    def set_packing_actions(self, enabled):
        """完成／取消單載入後切成唯讀，UI 與資料層雙重防止重複出貨。"""
        state = "normal" if enabled else "disabled"
        for widget in (self.pack_item_barcode, self.pack_scan_qty, self.pack_scan_button, self.pack_complete_button, self.pack_reset_button):
            widget.configure(state=state)

    def load_order_for_packing(self):
        order_no = self.pack_order_no.get().strip().upper()
        if not order_no:
            return self.set_status(self.pack_status, "請先掃描或輸入出貨單號", "danger")
        try:
            header = self.svc.shipping.start_packing(order_no)
            self.active_order_no = order_no
            self.shipping_read_only = header["status"] in ("已完成", "已取消")
            self.set_packing_actions(not self.shipping_read_only)
            self.refresh_packing_order()
            if self.shipping_read_only:
                self.set_status(self.pack_status, f"此出貨單狀態為「{header['status']}」；目前為唯讀查詢模式，禁止重複出貨。", "warning")
            else:
                self.set_status(self.pack_status, "已載入出貨單，請依出貨單儲位撿貨後逐項掃描商品", "success")
                self.pack_item_barcode.focus_set()
        except ValueError as error:
            self.active_order_no = None
            self.shipping_read_only = False
            self.set_packing_actions(True)
            self.clear_tree(self.pack_tree)
            self.pack_summary.configure(text="尚未讀取出貨單", bootstyle="secondary")
            self.set_status(self.pack_status, str(error), "danger")

    def refresh_packing_order(self):
        if not self.active_order_no:
            return
        header = self.svc.shipping.order_header(self.active_order_no)
        if not header:
            return
        self.pack_summary.configure(
            text=(
                f"單號：{header['order_no']}    日期：{header['order_date']}    分店：{header['branch_code']} {header['branch_name']}"
                f"    物流：{header['carrier']}    狀態：{header['status']}"
            ),
            bootstyle="primary",
        )
        self.clear_tree(self.pack_tree)
        for line, allocations in self.svc.shipping.order_lines(self.active_order_no):
            remaining = line["required_qty"] - line["scanned_qty"]
            done = remaining == 0
            self.pack_tree.insert(
                "",
                END,
                values=(
                    line["line_no"],
                    line["barcode"],
                    line["product_name"],
                    self.format_allocations(allocations),
                    line["required_qty"],
                    line["scanned_qty"],
                    remaining,
                    "已完成" if done else "待掃描",
                ),
                tags=("done",) if done else (),
            )

    def scan_packing_item(self):
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先掃描出貨單條碼", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢，禁止重複出貨。", "danger")
        barcode = Utils.normalize_barcode(self.pack_item_barcode.get())
        qty_text = self.pack_scan_qty.get().strip()
        # 防呆設定：掃到「完成驗收出貨專屬條碼」即等同一鍵完成驗貨。
        quick_barcode = Utils.normalize_barcode(self.svc.settings.get_setting("quick_complete_barcode") or "")
        if quick_barcode and barcode == quick_barcode:
            self.pack_item_barcode.delete(0, END)
            return self.quick_pack_current_order(confirmed_by_barcode=True)
        if not Utils.valid_barcode(barcode):
            return self.set_status(self.pack_status, "商品條碼格式錯誤", "danger")
        if not qty_text.isdigit() or not 1 <= int(qty_text) <= 100000:
            return self.set_status(self.pack_status, "本次數量必須是正整數", "danger")
        try:
            name, scanned, required = self.svc.shipping.scan_order_item(self.active_order_no, barcode, int(qty_text))
            self.refresh_packing_order()
            self.pack_item_barcode.delete(0, END)
            self.pack_scan_qty.delete(0, END)
            self.pack_scan_qty.insert(0, "1")
            self.set_status(self.pack_status, f"掃描成功：{name}（{scanned}/{required}）", "success")
            if self.packing_order_fully_scanned(self.active_order_no):
                self.auto_complete_packing()
            else:
                self.pack_item_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")

    def packing_order_fully_scanned(self, order_no):
        """判斷出貨單是否所有品項都已掃描足額，做為自動完成包裝的依據。"""
        return self.svc.shipping.order_fully_scanned(order_no)

    def auto_complete_packing(self):
        """V6.5：出貨掃描流程優化。全部商品掃描足額後，系統自動完成包裝、扣庫存並列印通運貼紙，
        不需再手動點擊「確認包裝成功」與「列印箱標」，減少倉庫作業的滑鼠操作與步驟。"""
        order_no = self.active_order_no
        try:
            self.svc.shipping.complete_packing(order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "完成出貨單", order_no, "全數掃描足額，系統自動完成")
            self.shipping_read_only = True
            self.set_packing_actions(False)
            self.refresh_packing_order()
            self.refresh_dashboard()
            self.refresh_inventory()
            self.print_label_document(order_no)
            self.set_status(
                self.pack_status,
                f"已全部掃描完成，出貨單 {order_no} 自動完成、扣庫存並開啟物流箱標列印頁面，可繼續掃描下一張出貨單。",
                "success",
            )
            self.reset_packing_screen_for_next_order()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"自動完成出貨失敗：{error}", "danger")

    def quick_pack_current_order(self, confirmed_by_barcode=False):
        """一鍵完成出貨驗貨：人工點數後整單快速完成（防呆設定啟用時才可用）。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢。", "danger")
        if not confirmed_by_barcode and not messagebox.askyesno(
            "一鍵完成驗貨",
            f"確定人工已核對出貨單 {self.active_order_no} 的所有商品數量，"
            "直接完成包裝並扣庫存嗎？\n（此模式跳過逐件掃描，正確性依賴人工點數）",
        ):
            return
        try:
            self.svc.shipping.quick_pack_order(self.active_order_no, self.current_user)
            order_no = self.active_order_no
            self.shipping_read_only = True
            self.set_packing_actions(False)
            self.refresh_packing_order()
            self.refresh_dashboard()
            self.refresh_inventory()
            self.print_label_document(order_no)
            self.set_status(self.pack_status, f"出貨單 {order_no} 已一鍵完成、扣庫存並列印箱標。", "success")
            self.reset_packing_screen_for_next_order()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"一鍵完成失敗：{error}", "danger")

    def complete_current_packing(self):
        """手動完成包裝的備援路徑（正常情況下全數掃描足額會自動觸發，不需手動點擊）。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢，禁止重複出貨。", "danger")
        if not messagebox.askyesno("完成出貨單", f"確定要完成出貨單 {self.active_order_no} 並扣除庫存嗎？\n完成後不可修改。"):
            return
        try:
            self.svc.shipping.complete_packing(self.active_order_no, self.current_user)
            self.svc.log.log_operation(self.current_user, "完成出貨單", self.active_order_no)
            self.shipping_read_only = True
            self.set_packing_actions(False)
            self.refresh_packing_order()
            self.refresh_dashboard()
            self.refresh_inventory()
            self.print_label_document(self.active_order_no)
            self.set_status(self.pack_status, "包裝成功，庫存已扣除，並已開啟物流箱標列印頁面，可繼續掃描下一張出貨單。", "success")
            self.reset_packing_screen_for_next_order()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"出貨失敗：{error}", "danger")

    def reset_packing_screen_for_next_order(self):
        """V6.6：箱標列印後自動回到出貨作業介面，讓使用者可直接刷下一張出貨單條碼，形成連續出貨的循環。"""
        self.active_order_no = None
        self.shipping_read_only = False
        self.set_packing_actions(True)
        self.clear_tree(self.pack_tree)
        self.pack_summary.configure(text="尚未讀取出貨單", bootstyle="secondary")
        self.pack_order_no.delete(0, END)

        def refocus_app():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.after(200, lambda: self.root.attributes("-topmost", False))
                self.root.focus_force()
            except Exception:
                pass
            self.pack_order_no.focus_set()

        self.root.after(300, refocus_app)

    def reset_current_packing_scan(self):
        """V6.6：商品歸零，防止刷到一半誤刷多件，將此張出貨單已掃描數量全部重置。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        if self.shipping_read_only:
            return self.set_status(self.pack_status, "已完成或已取消出貨單只能查詢，無法歸零。", "danger")
        if not messagebox.askyesno(
            "商品歸零",
            f"確定要將出貨單 {self.active_order_no} 已掃描的商品數量全部歸零嗎？",
        ):
            return
        try:
            self.svc.shipping.reset_packing_scan_progress(self.active_order_no)
            self.svc.log.log_operation(self.current_user, "出貨商品歸零", self.active_order_no)
            self.refresh_packing_order()
            self.pack_item_barcode.delete(0, END)
            self.pack_scan_qty.delete(0, END)
            self.pack_scan_qty.insert(0, "1")
            self.set_status(self.pack_status, "已將此出貨單已掃描數量歸零，請重新掃描。", "warning")
            self.pack_item_barcode.focus_set()
        except ValueError as error:
            self.set_status(self.pack_status, str(error), "danger")
        except Exception as error:
            self.set_status(self.pack_status, f"歸零失敗：{error}", "danger")

    def reprint_current_label(self):
        """V6.5：補印獨立按鈕，需選擇原因後才會補印，並記錄補印人／時間／原因／次數。"""
        if not self.active_order_no:
            return self.set_status(self.pack_status, "請先讀取出貨單", "danger")
        header = self.svc.shipping.order_header(self.active_order_no)
        if header["status"] != "已完成":
            return self.set_status(self.pack_status, "請先完成包裝與扣庫存後，再補印物流箱標", "warning")
        reason = self.prompt_reprint_reason("補印箱標原因")
        if not reason:
            return
        try:
            self.print_label_document(self.active_order_no, reason=reason)
            self.set_status(self.pack_status, f"已補印內部物流箱標（原因：{reason}）", "success")
        except Exception as error:
            self.set_status(self.pack_status, f"補印失敗：{error}", "danger")
