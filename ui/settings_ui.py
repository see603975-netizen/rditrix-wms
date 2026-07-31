"""SettingsUIMixin：防呆設定（老闆可自訂）與系統設定（印表機／紙張尺寸）。"""
from utils.constants import *
from utils.helpers import Utils

class SettingsUIMixin:
    # ---------- 防呆設定 ----------

    def build_guard_settings_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame, "防呆設定",
            "管理者可依營運需求開關防呆與快速作業模式；儲存後立即生效",
        )

        rules = tb.Labelframe(frame, text="商業防呆規則", bootstyle="primary", padding=14)
        rules.pack(fill=X, pady=(0, 10))
        self.guard_expiry_days = tb.Entry(rules, width=8)
        self.guard_warn_days = tb.Entry(rules, width=8)
        self.guard_enforce_max = tk.BooleanVar()
        tb.Label(rules, text="進貨效期須大於今日＋").grid(row=0, column=0, sticky=W, padx=(4, 4), pady=6)
        self.guard_expiry_days.grid(row=0, column=1, sticky=W, pady=6)
        tb.Label(rules, text="天（預設 180，填 0 停用；防止誤收即期品）").grid(row=0, column=2, sticky=W, padx=(4, 20), pady=6)
        tb.Label(rules, text="即期品警示天數：剩餘").grid(row=1, column=0, sticky=W, padx=(4, 4), pady=6)
        self.guard_warn_days.grid(row=1, column=1, sticky=W, pady=6)
        tb.Label(rules, text="天以内在總覽與庫存頁標示為即期品").grid(row=1, column=2, sticky=W, padx=(4, 20), pady=6)
        tb.Checkbutton(
            rules, text="啟用「商品最大進貨量」限制（於商品主檔逐品設定上限，例如 50 個）",
            variable=self.guard_enforce_max, bootstyle="primary-round-toggle",
        ).grid(row=2, column=0, columnspan=3, sticky=W, padx=4, pady=6)

        master = tb.Labelframe(frame, text="商品主檔防呆", bootstyle="secondary", padding=14)
        master.pack(fill=X, pady=(0, 10))
        self.guard_require_sku = tk.BooleanVar()
        self.guard_require_barcode = tk.BooleanVar()
        tb.Checkbutton(
            master, text="建立商品必須輸入 SKU（關閉後 SKU 可留空）",
            variable=self.guard_require_sku, bootstyle="secondary-round-toggle",
        ).grid(row=0, column=0, sticky=W, padx=4, pady=6)
        tb.Checkbutton(
            master, text="建立商品必須輸入商品條碼（關閉後留空會自動產生內部代碼 PN-日期-流水號）",
            variable=self.guard_require_barcode, bootstyle="secondary-round-toggle",
        ).grid(row=1, column=0, sticky=W, padx=4, pady=6)

        quick = tb.Labelframe(frame, text="快速作業模式（人工點數，速度優先；正確率依賴人工）", bootstyle="warning", padding=14)
        quick.pack(fill=X, pady=(0, 10))
        self.guard_quick_receive = tk.BooleanVar()
        self.guard_quick_pack = tk.BooleanVar()
        self.guard_quick_barcode = tb.Entry(quick, width=24)
        tb.Checkbutton(
            quick, text="進貨：允許「一鍵完成驗收入庫」（人工算好數量後整單快速入庫）",
            variable=self.guard_quick_receive, bootstyle="warning-round-toggle",
        ).grid(row=0, column=0, columnspan=3, sticky=W, padx=4, pady=6)
        tb.Checkbutton(
            quick, text="出貨：允許「一鍵完成驗貨包裝」（人工算好數量後整單快速出貨）",
            variable=self.guard_quick_pack, bootstyle="warning-round-toggle",
        ).grid(row=1, column=0, columnspan=3, sticky=W, padx=4, pady=6)
        tb.Label(quick, text="出貨驗收完成專屬條碼（掃到即一鍵完成，可自行印製）:").grid(row=2, column=0, sticky=W, padx=4, pady=6)
        self.guard_quick_barcode.grid(row=2, column=1, sticky=W, pady=6)

        mode = tb.Labelframe(frame, text="流程客製", bootstyle="info", padding=14)
        mode.pack(fill=X, pady=(0, 10))
        self.guard_no_location = tk.BooleanVar()
        tb.Checkbutton(
            mode, text="無儲位模式：未上架庫存直接視為可出貨庫存，不強制上架（適合無固定儲位的小型倉）",
            variable=self.guard_no_location, bootstyle="info-round-toggle",
        ).grid(row=0, column=0, sticky=W, padx=4, pady=6)

        self.guard_status = tb.Label(frame, text="", bootstyle="secondary")
        self.guard_status.pack(anchor=W, pady=(0, 6))
        tb.Button(frame, text="儲存防呆設定", bootstyle="primary", command=self.save_guard_settings).pack(anchor=W)
        return frame

    def refresh_guard_settings_view(self):
        if not self.has_perm("manage_settings"):
            return
        settings = self.svc.settings.all_settings()
        for entry, key in ((self.guard_expiry_days, "expiry_min_days"),
                           (self.guard_warn_days, "near_expiry_warn_days"),
                           (self.guard_quick_barcode, "quick_complete_barcode")):
            entry.delete(0, END)
            entry.insert(0, settings.get(key, ""))
        self.guard_enforce_max.set(settings.get("enforce_max_receiving") == "1")
        self.guard_require_sku.set(settings.get("require_sku") == "1")
        self.guard_require_barcode.set(settings.get("require_barcode") == "1")
        self.guard_quick_receive.set(settings.get("allow_quick_receive") == "1")
        self.guard_quick_pack.set(settings.get("allow_quick_pack") == "1")
        self.guard_no_location.set(settings.get("no_location_mode") == "1")

    def save_guard_settings(self):
        if not self.has_perm("manage_settings"):
            return self.set_status(self.guard_status, "僅系統管理員可修改防呆設定", "danger")
        expiry_days = self.guard_expiry_days.get().strip() or "0"
        warn_days = self.guard_warn_days.get().strip() or "0"
        if not expiry_days.isdigit() or not warn_days.isdigit():
            return self.set_status(self.guard_status, "天數請輸入 0 以上的整數", "danger")
        quick_barcode = Utils.normalize_barcode(self.guard_quick_barcode.get())
        if quick_barcode and not Utils.valid_barcode(quick_barcode):
            return self.set_status(self.guard_status, "完成專屬條碼格式錯誤（限英數與連字號）", "danger")
        try:
            self.svc.settings.set_setting("expiry_min_days", expiry_days)
            self.svc.settings.set_setting("near_expiry_warn_days", warn_days)
            self.svc.settings.set_setting("enforce_max_receiving", "1" if self.guard_enforce_max.get() else "0")
            self.svc.settings.set_setting("require_sku", "1" if self.guard_require_sku.get() else "0")
            self.svc.settings.set_setting("require_barcode", "1" if self.guard_require_barcode.get() else "0")
            self.svc.settings.set_setting("allow_quick_receive", "1" if self.guard_quick_receive.get() else "0")
            self.svc.settings.set_setting("allow_quick_pack", "1" if self.guard_quick_pack.get() else "0")
            self.svc.settings.set_setting("quick_complete_barcode", quick_barcode)
            self.svc.settings.set_setting("no_location_mode", "1" if self.guard_no_location.get() else "0")
            self.svc.log.log_operation(self.current_user, "修改防呆設定", "",
                                       f"效期+{expiry_days}天；快速收{int(self.guard_quick_receive.get())}"
                                       f"／出{int(self.guard_quick_pack.get())}；無儲位{int(self.guard_no_location.get())}")
            self.set_status(self.guard_status, "防呆設定已儲存並立即生效。", "success")
            self.show_toast("防呆設定已儲存", "success")
        except ValueError as error:
            self.set_status(self.guard_status, str(error), "danger")

    # ---------- 系統設定（印表機） ----------

    def build_system_settings_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(
            frame, "系統設定",
            "分別指定報表印表機與熱感貼紙印表機，並設定紙張尺寸與列印方式",
        )

        printers = tb.Labelframe(frame, text="印表機", bootstyle="primary", padding=14)
        printers.pack(fill=X, pady=(0, 10))
        self.sys_report_printer = tb.Combobox(printers, width=34, state="normal")
        self.sys_label_printer = tb.Combobox(printers, width=34, state="normal")
        tb.Label(printers, text="報表印表機（出貨單／進貨單／盤點單）:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=6)
        self.sys_report_printer.grid(row=0, column=1, sticky=W, pady=6)
        tb.Label(printers, text="熱感貼紙印表機（物流箱標）:").grid(row=1, column=0, sticky=W, padx=(4, 8), pady=6)
        self.sys_label_printer.grid(row=1, column=1, sticky=W, pady=6)
        tb.Button(printers, text="重新偵測印表機", bootstyle="secondary",
                  command=self.refresh_printer_choices).grid(row=0, column=2, rowspan=2, padx=10)

        papers = tb.Labelframe(frame, text="紙張尺寸", bootstyle="info", padding=14)
        papers.pack(fill=X, pady=(0, 10))
        self.sys_report_paper = tb.Combobox(papers, width=12, state="readonly", values=REPORT_PAPER_CHOICES)
        self.sys_label_paper = tb.Combobox(papers, width=12, state="normal", values=LABEL_PAPER_CHOICES)
        tb.Label(papers, text="報表紙張:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=6)
        self.sys_report_paper.grid(row=0, column=1, sticky=W, pady=6)
        tb.Label(papers, text="熱感貼紙尺寸（毫米，寬x高；100x100 = 10x10cm）:").grid(row=0, column=2, sticky=W, padx=(20, 8), pady=6)
        self.sys_label_paper.grid(row=0, column=3, sticky=W, pady=6)

        display = tb.Labelframe(frame, text="顯示縮放（筆電小螢幕看不到完整區塊時請調小）", bootstyle="success", padding=14)
        display.pack(fill=X, pady=(0, 10))
        self.sys_ui_scale = tb.Combobox(
            display, width=26, state="readonly",
            values=[f"{value}｜{label}" for value, label in UI_SCALE_CHOICES],
        )
        tb.Label(display, text="介面縮放:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=6)
        self.sys_ui_scale.grid(row=0, column=1, sticky=W, pady=6)
        tb.Label(display, text="儲存後重新啟動程式生效", bootstyle="secondary").grid(
            row=0, column=2, sticky=W, padx=(12, 0), pady=6)
        self.sys_invert_scroll = tk.BooleanVar()
        tb.Checkbutton(
            display, text="反轉滾輪／觸控板捲動方向（左側選單或頁面捲動方向顛倒時勾選，儲存後立即生效）",
            variable=self.sys_invert_scroll, bootstyle="success-round-toggle",
        ).grid(row=1, column=0, columnspan=3, sticky=W, padx=4, pady=(8, 2))

        engine = tb.Labelframe(frame, text="箱標列印方式", bootstyle="warning", padding=14)
        engine.pack(fill=X, pady=(0, 10))
        self.sys_label_engine = tb.Combobox(engine, width=36, state="readonly",
                                            values=("HTML｜瀏覽器列印（相容所有印表機）",
                                                    "TSPL｜直接吐紙（TSC 系列熱感機，精準不偏移）"))
        tb.Label(engine, text="物流箱標輸出:").grid(row=0, column=0, sticky=W, padx=(4, 8), pady=6)
        self.sys_label_engine.grid(row=0, column=1, sticky=W, pady=6)
        tb.Button(engine, text="測試列印箱標（TSPL）", bootstyle="warning",
                  command=self.test_print_label).grid(row=0, column=2, padx=10)

        self.sys_status = tb.Label(frame, text="", bootstyle="secondary")
        self.sys_status.pack(anchor=W, pady=(0, 6))
        tb.Button(frame, text="儲存系統設定", bootstyle="primary", command=self.save_system_settings).pack(anchor=W)
        return frame

    def refresh_printer_choices(self):
        printers = self.svc.settings.list_printers()
        self.sys_report_printer.configure(values=printers)
        self.sys_label_printer.configure(values=printers)
        note = f"偵測到 {len(printers)} 台印表機" if printers else "未偵測到印表機，可手動輸入印表機名稱"
        self.set_status(self.sys_status, note, "info")

    def refresh_system_settings_view(self):
        if not self.has_perm("manage_settings"):
            return
        settings = self.svc.settings.all_settings()
        self.refresh_printer_choices()
        self.sys_report_printer.set(settings.get("report_printer", ""))
        self.sys_label_printer.set(settings.get("label_printer", ""))
        self.sys_report_paper.set(settings.get("report_paper", "A4"))
        self.sys_label_paper.set(settings.get("label_paper", "100x100"))
        engine = settings.get("label_engine", "HTML")
        self.sys_label_engine.set(
            "TSPL｜直接吐紙（TSC 系列熱感機，精準不偏移）" if engine == "TSPL"
            else "HTML｜瀏覽器列印（相容所有印表機）"
        )
        self.sys_invert_scroll.set(settings.get("invert_scroll") == "1")
        current_scale = settings.get("ui_scale", "1.3")
        for value, label in UI_SCALE_CHOICES:
            if value == current_scale:
                self.sys_ui_scale.set(f"{value}｜{label}")
                break
        else:
            self.sys_ui_scale.set(f"{current_scale}｜自訂")

    def save_system_settings(self):
        if not self.has_perm("manage_settings"):
            return self.set_status(self.sys_status, "僅系統管理員可修改系統設定", "danger")
        label_paper = self.sys_label_paper.get().strip().lower().replace("×", "x")
        if not re.fullmatch(r"\d{2,3}x\d{2,3}", label_paper):
            return self.set_status(self.sys_status, "貼紙尺寸格式錯誤，請輸入如 100x100（毫米）", "danger")
        engine = "TSPL" if self.sys_label_engine.get().startswith("TSPL") else "HTML"
        ui_scale = (self.sys_ui_scale.get() or "1.3").split("｜", 1)[0]
        try:
            self.svc.settings.set_setting("report_printer", self.sys_report_printer.get().strip())
            self.svc.settings.set_setting("label_printer", self.sys_label_printer.get().strip())
            self.svc.settings.set_setting("report_paper", self.sys_report_paper.get() or "A4")
            self.svc.settings.set_setting("label_paper", label_paper)
            self.svc.settings.set_setting("label_engine", engine)
            scale_changed = ui_scale != self.svc.settings.get_setting("ui_scale")
            self.svc.settings.set_setting("ui_scale", ui_scale)
            self.svc.settings.set_setting("invert_scroll", "1" if self.sys_invert_scroll.get() else "0")
            self._scroll_invert = self.sys_invert_scroll.get()
            self.svc.log.log_operation(self.current_user, "修改系統設定", "",
                                       f"報表機={self.sys_report_printer.get().strip() or '未指定'}；"
                                       f"貼紙機={self.sys_label_printer.get().strip() or '未指定'}；"
                                       f"貼紙={label_paper}；引擎={engine}")
            if scale_changed:
                self.set_status(self.sys_status, "系統設定已儲存；顯示縮放將在重新啟動程式後生效。", "success")
                messagebox.showinfo("顯示縮放", "縮放設定已儲存，請關閉並重新開啟程式以套用新的縮放比例。")
            else:
                self.set_status(self.sys_status, "系統設定已儲存。", "success")
            self.show_toast("系統設定已儲存", "success")
        except ValueError as error:
            self.set_status(self.sys_status, str(error), "danger")

    def test_print_label(self):
        try:
            self.svc.settings.set_setting("label_printer", self.sys_label_printer.get().strip())
            self.svc.settings.set_setting("label_paper",
                                          self.sys_label_paper.get().strip().lower() or "100x100")
            self.svc.settings.print_label_tspl(
                "TEST-00000000-0000", 1, 1, "測試門市", "測試地址",
                "測試物流", "T123456789", Utils.today_text(),
            )
            self.set_status(self.sys_status, "已送出測試箱標，請確認貼紙機出紙是否置中無偏移。", "success")
        except Exception as error:
            self.set_status(self.sys_status, f"測試列印失敗：{error}", "danger")
