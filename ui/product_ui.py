"""ProductUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class ProductUIMixin:
    def build_product_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "商品主檔", "新增、修改條碼、SKU、名稱、安全庫存與效期設定")

        form = tb.Labelframe(frame, text="商品資料", bootstyle="primary", padding=14)
        form.pack(fill=X, pady=(0, 12))

        self.prod_barcode = tb.Entry(form, width=24)
        self.prod_sku = tb.Entry(form, width=18)
        self.prod_name = tb.Entry(form, width=28)
        self.prod_category = tb.Combobox(form, width=16, state="readonly", values=PRODUCT_CATEGORIES)
        self.prod_category.set(PRODUCT_CATEGORIES[-1])
        self.prod_safety = tb.Entry(form, width=10)
        self.prod_max_receiving = tb.Entry(form, width=10)
        self.prod_max_receiving.insert(0, "0")
        self.prod_expiry_required = tk.BooleanVar(value=True)

        fields = [
            ("商品條碼", self.prod_barcode, 0, 0),
            ("SKU（限英數）", self.prod_sku, 0, 2),
            ("商品名稱", self.prod_name, 0, 4),
            ("分類", self.prod_category, 1, 0),
            ("安全庫存", self.prod_safety, 1, 2),
            ("最大進貨量（0=不限）", self.prod_max_receiving, 2, 0),
        ]
        for text, widget, row, column in fields:
            tb.Label(form, text=f"{text}:").grid(row=row, column=column, sticky=W, padx=(4, 6), pady=8)
            widget.grid(row=row, column=column + 1, sticky=W, padx=(0, 18), pady=8)

        tb.Checkbutton(
            form,
            text="有效期商品（開啟才會要求輸入效期／建立 LOT）",
            variable=self.prod_expiry_required,
            bootstyle="primary-round-toggle",
        ).grid(row=1, column=4, columnspan=2, sticky=W, padx=4)
        tb.Button(form, text="儲存商品", bootstyle="primary", command=self.save_product_from_form).grid(
            row=0, column=6, padx=(12, 6), pady=8
        )
        tb.Button(form, text="清除欄位", bootstyle="secondary", command=self.clear_product_form).grid(
            row=1, column=6, padx=(12, 6), pady=8
        )
        self.prod_barcode.bind("<FocusOut>", self.check_product_barcode_duplicate)
        self.prod_barcode_hint = tb.Label(form, text="", bootstyle="danger")
        self.prod_barcode_hint.grid(row=3, column=0, columnspan=6, sticky=W, padx=4)

        filter_bar = tb.Frame(frame)
        filter_bar.pack(fill=X, pady=(0, 8))
        self.prod_filter_category = tb.Combobox(filter_bar, width=14, state="readonly", values=("全部類別",) + PRODUCT_CATEGORIES)
        self.prod_filter_category.set("全部類別")
        self.prod_filter_keyword = tb.Entry(filter_bar, width=28)
        tb.Label(filter_bar, text="分類篩選:").pack(side=LEFT, padx=(4, 6))
        self.prod_filter_category.pack(side=LEFT, padx=(0, 16))
        tb.Label(filter_bar, text="搜尋（條碼／SKU／名稱）:").pack(side=LEFT, padx=(4, 6))
        self.prod_filter_keyword.pack(side=LEFT, padx=(0, 8))
        tb.Button(filter_bar, text="查詢", bootstyle="secondary", command=self.refresh_products).pack(side=LEFT, padx=4)
        tb.Button(filter_bar, text="顯示全部", bootstyle="outline-secondary", command=self.clear_product_filter).pack(side=LEFT, padx=4)
        tb.Button(filter_bar, text="列印條碼貼紙", bootstyle="warning", command=self.print_product_barcode_label).pack(side=RIGHT, padx=4)
        tb.Button(filter_bar, text="批次匯入商品", bootstyle="success", command=self.import_products_from_csv).pack(side=RIGHT, padx=4)
        tb.Button(filter_bar, text="下載匯入範本", bootstyle="outline-success", command=self.download_product_import_template).pack(side=RIGHT, padx=4)
        self.prod_filter_category.bind("<<ComboboxSelected>>", lambda _event: self.refresh_products())
        self.prod_filter_keyword.bind("<Return>", lambda _event: self.refresh_products())

        columns = ("barcode", "sku", "name", "category", "safety", "expiry")
        self.product_tree = tb.Treeview(frame, columns=columns, show="headings", height=18, bootstyle="primary")
        headings = ("商品條碼", "SKU", "商品名稱", "分類", "安全庫存", "保存期限")
        widths = (180, 130, 260, 140, 110, 110)
        self.setup_tree_columns(self.product_tree, columns, headings, widths, left_columns=("name",))
        self.product_tree.bind("<<TreeviewSelect>>", self.on_product_select)
        self.add_table_interactions(self.product_tree, frame)
        self.add_tree_scrollbar(frame, self.product_tree)
        return frame

    def clear_product_form(self):
        self.product_selected_barcode = None
        for widget in (self.prod_barcode, self.prod_sku, self.prod_name, self.prod_safety, self.prod_max_receiving):
            widget.delete(0, END)
        self.prod_max_receiving.insert(0, "0")
        self.prod_category.set(PRODUCT_CATEGORIES[-1])
        self.prod_expiry_required.set(True)
        self.prod_barcode_hint.configure(text="")
        self.prod_barcode.focus_set()

    def check_product_barcode_duplicate(self, _event=None):
        """V6.3：新增商品時即時提示條碼是否已被使用，避免存檔時才發現重複。"""
        barcode = Utils.normalize_barcode(self.prod_barcode.get())
        if not Utils.valid_barcode(barcode):
            self.prod_barcode_hint.configure(text="")
            return
        existing = self.svc.product.product_by_barcode(barcode)
        if existing and barcode != self.product_selected_barcode:
            self.prod_barcode_hint.configure(text=f"⚠ 此條碼已被商品「{existing['name']}」（SKU:{existing['sku']}）使用，不可重複建立")
        else:
            self.prod_barcode_hint.configure(text="")

    def on_product_select(self, _event=None):
        selected = self.product_tree.focus()
        if not selected:
            return
        barcode = self.product_tree.item(selected, "values")[0]
        product = self.svc.product.product_by_barcode(barcode)
        if not product:
            return
        self.product_selected_barcode = barcode
        max_receiving = product["max_receiving_qty"] if "max_receiving_qty" in product.keys() else 0
        values = {
            self.prod_barcode: product["barcode"],
            self.prod_sku: product["sku"],
            self.prod_name: product["name"],
            self.prod_safety: str(product["safety_stock"]),
            self.prod_max_receiving: str(max_receiving or 0),
        }
        for widget, value in values.items():
            widget.delete(0, END)
            widget.insert(0, value)
        self.prod_category.set(product["category"] if product["category"] in PRODUCT_CATEGORIES else PRODUCT_CATEGORIES[-1])
        self.prod_expiry_required.set(bool(product["expiry_required"]))
        self.prod_barcode_hint.configure(text="")

    def save_product_from_form(self):
        try:
            barcode = Utils.normalize_barcode(self.prod_barcode.get())
            sku = self.prod_sku.get().strip()
            name = self.prod_name.get().strip()
            category = self.prod_category.get().strip() or PRODUCT_CATEGORIES[-1]
            safety_text = self.prod_safety.get().strip()
            require_sku = self.svc.settings.get_setting_bool("require_sku")
            require_barcode = self.svc.settings.get_setting_bool("require_barcode")
            if barcode:
                if not Utils.valid_barcode(barcode):
                    raise ValueError("條碼只能使用英文字母、數字與連字號，長度 3 至 64 碼")
            elif require_barcode:
                raise ValueError("商品條碼為必填（管理者可於「防呆設定」關閉；關閉後留空會自動產生內部代碼）")
            if not name:
                raise ValueError("商品名稱為必填")
            if sku:
                if not Utils.valid_sku(sku):
                    raise ValueError("SKU 僅限英文字母與數字（不可中文、空白或符號）")
            elif require_sku:
                raise ValueError("SKU 為必填（管理者可於「防呆設定」關閉此檢查）")
            if not safety_text.isdigit() or int(safety_text) > 1000000:
                raise ValueError("安全庫存請輸入 0 至 1,000,000 的整數")
            max_receiving_text = self.prod_max_receiving.get().strip() or "0"
            if not max_receiving_text.isdigit():
                raise ValueError("最大進貨量請輸入整數（0 = 不限制）")
            is_new = self.product_selected_barcode is None
            saved_barcode = self.svc.product.save_product(
                self.product_selected_barcode,
                barcode,
                sku,
                name,
                category,
                int(safety_text),
                self.prod_expiry_required.get(),
                int(max_receiving_text),
            )
            self.svc.log.log_operation(
                self.current_user,
                "新增商品" if is_new else "修改商品",
                saved_barcode,
                f"{name}（SKU:{sku or '未填'}）",
            )
            self.refresh_products()
            self.clear_product_form()
            if not barcode and saved_barcode:
                messagebox.showinfo("完成", f"商品「{name}」已儲存。\n未輸入條碼，系統自動產生內部代碼：{saved_barcode}")
            else:
                messagebox.showinfo("完成", f"商品「{name}」已儲存")
        except (ValueError, sqlite3.IntegrityError) as error:
            messagebox.showerror("無法儲存商品", str(error))

    def clear_product_filter(self):
        self.prod_filter_category.set("全部類別")
        self.prod_filter_keyword.delete(0, END)
        self.refresh_products()

    def refresh_products(self):
        self.clear_tree(self.product_tree)
        category_filter = self.prod_filter_category.get().strip() if hasattr(self, "prod_filter_category") else "全部類別"
        keyword = self.prod_filter_keyword.get().strip().lower() if hasattr(self, "prod_filter_keyword") else ""
        for product in self.svc.product.all_products():
            if category_filter and category_filter != "全部類別" and (product["category"] or "") != category_filter:
                continue
            if keyword and keyword not in product["barcode"].lower() and keyword not in product["sku"].lower() and keyword not in product["name"].lower():
                continue
            self.product_tree.insert(
                "",
                END,
                values=(
                    product["barcode"],
                    product["sku"] or "-",
                    product["name"],
                    product["category"] or "-",
                    product["safety_stock"],
                    "需要" if product["expiry_required"] else "不需要",
                ),
            )
        self.refresh_product_choices()

    # ---------- 批次匯入 ----------

    PRODUCT_IMPORT_HEADERS = ("商品條碼", "SKU", "商品名稱", "分類", "安全庫存", "需要效期(1/0)", "最大進貨量(0=不限)")

    def download_product_import_template(self):
        path = filedialog.asksaveasfilename(
            title="下載商品匯入範本", defaultextension=".csv",
            initialfile="商品匯入範本.csv",
            filetypes=[("Excel 可開啟的 CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(self.PRODUCT_IMPORT_HEADERS)
                writer.writerow(("4711234500001", "AB0001", "範例商品A", "精華液", 10, 1, 0))
                writer.writerow(("4711234500002", "TAPE02", "範例耗材B", "耗材", 0, 0, 0))
        except OSError as error:
            return messagebox.showerror("無法建立範本", str(error))
        self.show_toast(f"範本已儲存：{Path(path).name}（可用 Excel 編輯後匯入）", "success")

    def import_products_from_csv(self):
        path = filedialog.askopenfilename(
            title="選擇商品匯入 CSV",
            filetypes=[("CSV 檔", "*.csv"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            for encoding in ("utf-8-sig", "cp950", "utf-8"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("無法辨識檔案編碼，請以範本另存或存成 UTF-8")
            reader = csv.reader(text.splitlines())
            header = next(reader, None)
            if not header:
                raise ValueError("檔案沒有內容")
            rows = []
            for values in reader:
                if not any(str(value).strip() for value in values):
                    continue
                values = list(values) + [""] * (7 - len(values))
                rows.append({
                    "barcode": values[0], "sku": values[1], "name": values[2],
                    "category": values[3], "safety_stock": values[4],
                    "expiry_required": values[5], "max_receiving_qty": values[6],
                })
        except (OSError, ValueError, csv.Error) as error:
            return messagebox.showerror("匯入失敗", str(error))
        if not rows:
            return messagebox.showwarning("批次匯入", "檔案中沒有資料列")
        if not messagebox.askyesno(
            "批次匯入商品",
            f"共讀到 {len(rows)} 筆商品，開始匯入嗎？\n（條碼已存在會更新該商品，不存在會新增）",
        ):
            return
        ok_count, errors = self.svc.product.bulk_import_products(rows, self.current_user)
        self.refresh_products()
        summary = f"匯入完成：成功 {ok_count} 筆，失敗 {len(errors)} 筆"
        if errors:
            detail = "\n".join(errors[:10])
            if len(errors) > 10:
                detail += f"\n…其餘 {len(errors) - 10} 筆省略"
            messagebox.showwarning("批次匯入結果", f"{summary}\n\n{detail}")
        else:
            messagebox.showinfo("批次匯入結果", summary)

    # ---------- 條碼貼紙列印 ----------

    def print_product_barcode_label(self):
        """列印商品內部條碼貼紙（無條碼商品的 PN- 內部代碼也適用）。"""
        barcode = self.product_selected_barcode or Utils.normalize_barcode(self.prod_barcode.get())
        if not barcode:
            selected = self.product_tree.focus()
            if selected:
                barcode = self.product_tree.item(selected, "values")[0]
        product = self.svc.product.product_by_barcode(barcode) if barcode else None
        if not product:
            return messagebox.showwarning("列印條碼貼紙", "請先在清單點選要列印的商品")

        dialog = tb.Toplevel(self.root)
        dialog.title("列印條碼貼紙")
        dialog.transient(self.root)
        dialog.grab_set()
        body = tb.Frame(dialog, padding=18)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text=f"{product['name']}（{product['barcode']}）",
                 font=("Microsoft JhengHei", 11, "bold")).pack(anchor=W)
        row = tb.Frame(body)
        row.pack(anchor=W, pady=(10, 4))
        tb.Label(row, text="列印張數:").pack(side=LEFT, padx=(0, 8))
        copies_entry = tb.Entry(row, width=8)
        copies_entry.insert(0, "1")
        copies_entry.pack(side=LEFT)
        status = tb.Label(body, text="", bootstyle="danger")
        status.pack(anchor=W, pady=(6, 0))

        def confirm():
            copies_text = copies_entry.get().strip()
            if not copies_text.isdigit() or not 1 <= int(copies_text) <= 100:
                return status.configure(text="張數請輸入 1 至 100")
            copies = int(copies_text)
            try:
                if self.svc.settings.get_setting("label_engine") == "TSPL":
                    self.svc.settings.print_product_label_tspl(
                        product["barcode"], product["name"], product["sku"] or "", copies)
                else:
                    self._print_product_label_html(product, copies)
                self.svc.log.log_operation(self.current_user, "列印商品條碼",
                                           product["barcode"], f"{product['name']} x {copies} 張")
            except Exception as error:
                return status.configure(text=f"列印失敗：{error}")
            dialog.destroy()
            self.show_toast(f"已送出 {copies} 張條碼貼紙", "success")

        bar = tb.Frame(body)
        bar.pack(fill=X, pady=(12, 0))
        tb.Button(bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT, padx=(8, 0))
        tb.Button(bar, text="列印", bootstyle="warning", command=confirm).pack(side=RIGHT)
        copies_entry.focus_set()

    def _print_product_label_html(self, product, copies):
        """HTML 模式：依系統設定的貼紙尺寸產生條碼貼紙頁面，交給瀏覽器列印。"""
        label_width, label_height = self.svc.settings.get_setting("label_paper").split("x")
        barcode_svg = self.code39_svg(product["barcode"], height=64)
        label = f"""<section class="label">
<div class="name">{html.escape(product['name'])}</div>
<div class="sku">SKU：{html.escape(product['sku'] or '-')}</div>
<div class="barcode-wrap">{barcode_svg}<div class="code">{html.escape(product['barcode'])}</div></div>
</section>"""
        content = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>{html.escape(product['barcode'])} 條碼貼紙</title>
<style>
@page {{ size: {label_width}mm {label_height}mm; margin: 3mm; }}
body {{ margin:0; font-family:"Microsoft JhengHei", Arial, sans-serif; color:#111; }}
.label {{ page-break-after:always; padding:2mm; text-align:center; }}
.label:last-child {{ page-break-after:auto; }}
.name {{ font-size:15px; font-weight:bold; }}
.sku {{ font-size:11px; color:#444; margin:1mm 0 2mm; }}
.barcode {{ width:90%; height:64px; }} .code {{ font-size:12px; letter-spacing:1px; font-weight:bold; }}
</style></head><body>{label * copies}</body></html>"""
        self.write_print_file(f"{product['barcode']}_條碼貼紙.html", content)

    def open_new_product_dialog(self, initial_barcode, after_save=None):
        dialog = tb.Toplevel(self.root)
        dialog.title("建立新商品")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x360")

        body = tb.Frame(dialog, padding=22)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text="查無商品主檔", font=("Microsoft JhengHei", 16, "bold"), bootstyle="warning").pack(anchor=W)
        tb.Label(body, text="請建立商品後，系統會接續原本的進貨資料。", bootstyle="secondary").pack(anchor=W, pady=(2, 16))

        barcode_entry = tb.Entry(body, width=28)
        sku_entry = tb.Entry(body, width=28)
        name_entry = tb.Entry(body, width=28)
        category_entry = tb.Entry(body, width=28)
        safety_entry = tb.Entry(body, width=28)
        expiry_var = tk.BooleanVar(value=True)
        barcode_entry.insert(0, initial_barcode)
        safety_entry.insert(0, "0")
        widgets = [
            ("商品條碼", barcode_entry),
            ("SKU", sku_entry),
            ("商品名稱", name_entry),
            ("分類", category_entry),
            ("安全庫存", safety_entry),
        ]
        for row, (label, widget) in enumerate(widgets):
            tb.Label(body, text=f"{label}:").grid(row=row + 2, column=0, sticky=W, pady=6)
            widget.grid(row=row + 2, column=1, sticky=W, pady=6, padx=(12, 0))
        tb.Checkbutton(
            body,
            text="需要保存期限",
            variable=expiry_var,
            bootstyle="primary-round-toggle",
        ).grid(row=7, column=1, sticky=W, pady=8)

        def save_and_continue():
            try:
                barcode = Utils.normalize_barcode(barcode_entry.get())
                safety = safety_entry.get().strip()
                if not Utils.valid_barcode(barcode):
                    raise ValueError("條碼格式不正確")
                if not name_entry.get().strip():
                    raise ValueError("商品名稱為必填")
                if not sku_entry.get().strip() and self.svc.settings.get_setting_bool("require_sku"):
                    raise ValueError("SKU 為必填（管理者可於「防呆設定」關閉此檢查）")
                if not safety.isdigit():
                    raise ValueError("安全庫存必須是整數")
                self.svc.product.save_product(
                    None,
                    barcode,
                    sku_entry.get().strip(),
                    name_entry.get().strip(),
                    category_entry.get().strip(),
                    int(safety),
                    expiry_var.get(),
                )
                self.svc.log.log_operation(
                    self.current_user, "新增商品", barcode,
                    f"{name_entry.get().strip()}（SKU:{sku_entry.get().strip()}）",
                )
                self.refresh_products()
                dialog.destroy()
                if after_save:
                    after_save()
            except (ValueError, sqlite3.IntegrityError) as error:
                messagebox.showerror("無法建立商品", str(error), parent=dialog)

        button_bar = tb.Frame(body)
        button_bar.grid(row=8, column=0, columnspan=2, sticky=EW, pady=(12, 0))
        tb.Button(button_bar, text="建立並繼續進貨", bootstyle="primary", command=save_and_continue).pack(side=LEFT)
        tb.Button(button_bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=LEFT, padx=8)
        name_entry.focus_set()
