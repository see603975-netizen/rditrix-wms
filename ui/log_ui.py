"""LogUIMixin: source-preserving UI module extracted from V6.8."""
from utils.constants import *
from utils.helpers import Utils

class LogUIMixin:
    def build_history_view(self):
        frame = tb.Frame(self.content_frame, bootstyle="light")
        self.make_title(frame, "作業紀錄", "保留進貨、上架、盤點與訂單出貨的完整異動資料")
        notebook = tb.Notebook(frame, bootstyle="secondary")
        notebook.pack(fill=BOTH, expand=True)
        tx_tab = tb.Frame(notebook, padding=10)
        op_tab = tb.Frame(notebook, padding=10)
        login_tab = tb.Frame(notebook, padding=10)
        notebook.add(tx_tab, text=" 庫存異動紀錄 ")
        notebook.add(op_tab, text=" 操作紀錄 ")
        notebook.add(login_tab, text=" 登入日誌 ")

        columns = ("time", "type", "order", "barcode", "from", "to", "before", "after", "change", "expiry", "user", "reason")
        self.history_tree = tb.Treeview(tx_tab, columns=columns, show="headings", bootstyle="secondary")
        headings = ("時間", "作業", "相關單號", "條碼", "來源", "去向", "前", "後", "異動", "效期", "人員", "備註")
        widths = (155, 100, 165, 145, 110, 130, 65, 65, 70, 110, 135, 230)
        self.setup_tree_columns(self.history_tree, columns, headings, widths, left_columns=("reason",))
        self.add_table_interactions(self.history_tree, tx_tab)
        self.add_tree_scrollbar(tx_tab, self.history_tree)

        # V6.1：操作紀錄頁籤，記錄登入、單據建立／完成／取消等關鍵操作。
        op_columns = ("time", "user", "action", "order", "note")
        self.op_log_tree = tb.Treeview(op_tab, columns=op_columns, show="headings", bootstyle="secondary")
        op_headings = ("時間", "使用者", "動作", "相關單號", "備註")
        op_widths = (160, 130, 130, 180, 320)
        self.setup_tree_columns(self.op_log_tree, op_columns, op_headings, op_widths, left_columns=("note",))
        self.add_table_interactions(self.op_log_tree, op_tab)
        self.add_tree_scrollbar(op_tab, self.op_log_tree)

        # 登入日誌：成功／失敗與鎖定警告全數留痕。
        login_columns = ("time", "username", "result", "source", "note")
        self.login_log_tree = tb.Treeview(login_tab, columns=login_columns, show="headings", bootstyle="secondary")
        login_headings = ("時間", "帳號", "結果", "來源機器", "備註")
        login_widths = (160, 130, 90, 150, 420)
        self.setup_tree_columns(self.login_log_tree, login_columns, login_headings, login_widths, left_columns=("note",))
        self.login_log_tree.tag_configure("fail", background="#FDE2E1")
        self.add_table_interactions(self.login_log_tree, login_tab)
        self.add_tree_scrollbar(login_tab, self.login_log_tree)
        return frame

    def refresh_history(self):
        self.clear_tree(self.history_tree)
        rows = self.svc.log.recent_transactions(300)
        for row in rows:
            product = self.svc.product.product_by_barcode(row["barcode"])
            expiry_required = bool(product["expiry_required"]) if product else True
            self.history_tree.insert(
                "",
                END,
                values=(
                    row["timestamp"], row["tx_type"], row["order_no"] or "-", row["barcode"],
                    row["from_shelf"] or "-", row["to_shelf"] or "-",
                    row["before_qty"] if row["before_qty"] is not None else "-",
                    row["after_qty"] if row["after_qty"] is not None else "-",
                    row["change_qty"], Utils.display_expiry(row["expiry_date"], expiry_required),
                    row["operator"], row["reason"] or "-",
                ),
            )
        self.clear_tree(self.op_log_tree)
        for row in self.svc.log.recent_operation_logs():
            self.op_log_tree.insert(
                "", END,
                values=(row["timestamp"], row["operator"], row["action"], row["order_no"] or "-", row["note"] or "-"),
            )
        self.clear_tree(self.login_log_tree)
        for row in self.svc.log.recent_login_logs():
            self.login_log_tree.insert(
                "", END,
                values=(
                    row["timestamp"], row["username"],
                    "成功" if row["success"] else "失敗",
                    row["source"] or "-", row["note"] or "-",
                ),
                tags=() if row["success"] else ("fail",),
            )

    # ---------- 列印文件 ----------

    def format_allocations(self, allocations):
        if not allocations:
            return "尚未配貨"
        parts = []
        for allocation in allocations:
            expiry = Utils.display_expiry(allocation["expiry_date"])
            parts.append(f"{allocation['shelf_code']} / {expiry} x {allocation['allocated_qty']}")
        return "；".join(parts)

    def code39_svg(self, value, height=64):
        """產生可由支援 Code 39 的掃描器讀取的 SVG 條碼。"""
        patterns = {
            "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn",
            "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw",
            "8": "wnnwnnwnn", "9": "nnwwnnwnn", "A": "wnnnnwnnw", "B": "nnwnnwnnw",
            "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn",
            "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
            "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww",
            "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn",
            "S": "nnwnnnwwn", "T": "nnnnwnwwn", "U": "wwnnnnnnw", "V": "nwwnnnnnw",
            "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
            "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "*": "nwnnwnwnn",
            "$": "nwnwnwnnn", "/": "nwnwnnnwn", "+": "nwnnnwnwn", "%": "nnnwnwnwn",
        }
        encoded = f"*{value.upper()}*"
        if any(character not in patterns for character in encoded):
            raise ValueError("此單號含有 Code 39 不支援的字元")
        narrow, wide, gap, quiet = 2, 5, 2, 16
        x = quiet
        bars = []
        for character in encoded:
            for index, element in enumerate(patterns[character]):
                width = wide if element == "w" else narrow
                if index % 2 == 0:
                    bars.append(f'<rect x="{x}" y="0" width="{width}" height="{height}"/>')
                x += width
            x += gap
        total_width = x + quiet
        return f'<svg class="barcode" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_width} {height}" role="img">{"".join(bars)}</svg>'

    def write_print_file(self, filename, content):
        output_dir = Path(__file__).resolve().parent.parent / "printouts"
        output_dir.mkdir(exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        webbrowser.open(path.resolve().as_uri())
        return path

    def prompt_reprint_reason(self, title="補印原因"):
        """V6.5：補印獨立於正常列印，必須先選擇原因才會執行；取消則回傳 None。"""
        dialog = tb.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("360x280")
        dialog.transient(self.root)
        dialog.grab_set()
        body = tb.Frame(dialog, padding=16)
        body.pack(fill=BOTH, expand=True)
        tb.Label(body, text="請選擇補印原因：", font=("Microsoft JhengHei", 11, "bold")).pack(anchor=W, pady=(0, 10))
        reason_var = tk.StringVar(value="標籤破損")
        for option in ("標籤破損", "印表機故障", "其他"):
            tb.Radiobutton(body, text=option, variable=reason_var, value=option).pack(anchor=W, pady=3)
        other_entry = tb.Entry(body, width=28)
        other_entry.pack(anchor=W, padx=24, pady=(2, 10))
        other_entry.configure(state="disabled")

        def sync_other_state(*_args):
            other_entry.configure(state="normal" if reason_var.get() == "其他" else "disabled")

        reason_var.trace_add("write", sync_other_state)

        result = {"reason": None}

        def confirm():
            reason = reason_var.get()
            if reason == "其他":
                detail = other_entry.get().strip()
                reason = f"其他：{detail}" if detail else "其他"
            result["reason"] = reason
            dialog.destroy()

        action_bar = tb.Frame(body)
        action_bar.pack(fill=X, pady=(10, 0), side="bottom")
        tb.Button(action_bar, text="取消", bootstyle="secondary", command=dialog.destroy).pack(side=RIGHT, padx=(8, 0))
        tb.Button(action_bar, text="確認補印", bootstyle="warning", command=confirm).pack(side=RIGHT)
        dialog.wait_window()
        return result["reason"]

    def print_order_document(self, order_no, reason=None):
        header = self.svc.shipping.order_header(order_no)
        if not header:
            raise ValueError("查無出貨單")
        print_count = self.svc.shipping.mark_order_printed(order_no)
        document_mark = "正本" if print_count == 1 else f"補印第 {print_count - 1} 次"
        self.svc.log.log_operation(
            self.current_user, "列印出貨單" if print_count == 1 else "補印出貨單",
            order_no, reason or ("正本首次列印" if print_count == 1 else "-"),
        )
        rows = []
        for line, allocations in self.svc.shipping.order_lines(order_no):
            rows.append(
                "<tr>"
                f"<td>{line['line_no']}</td>"
                f"<td>{html.escape(line['barcode'])}</td>"
                f"<td>{html.escape(line['product_name'])}</td>"
                f"<td>{html.escape(self.format_allocations(allocations))}</td>"
                f"<td class=\"qty\">{line['required_qty']}</td>"
                "</tr>"
            )
        barcode_svg = self.code39_svg(order_no, height=72)
        content = f"""<!doctype html>
<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><title>{html.escape(order_no)} 出貨單</title>
<style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: \"Microsoft JhengHei\", Arial, sans-serif; color:#172033; font-size:12px; }}
.sheet {{ max-width: 190mm; margin:auto; }} .top {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #1f5eff; padding-bottom:12px; }}
h1 {{ margin:0; font-size:25px; }} .mark {{ border:1px solid #f0a000; color:#9a5d00; padding:5px 10px; font-weight:bold; }}
.barcode-wrap {{ text-align:center; margin:13px 0 9px; }} .barcode {{ width:285px; height:72px; }} .barcode-text {{ letter-spacing:1px; font-weight:bold; }}
.info {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 28px; margin:12px 0 16px; }} .info div {{ border-bottom:1px solid #d9dfeb; padding:5px 0; }}
table {{ width:100%; border-collapse:collapse; }} th {{ background:#eaf0ff; }} th,td {{ border:1px solid #aebbd0; padding:8px; text-align:left; vertical-align:top; }} td.qty {{ text-align:center; font-size:15px; font-weight:bold; }}
.footer {{ margin-top:20px; display:flex; justify-content:space-between; color:#56657f; }} @media print {{ .no-print {{ display:none; }} }}
</style></head><body><div class=\"sheet\">
<div class=\"top\"><div><h1>分店出貨單</h1><div>單據狀態：{html.escape(header['status'])}</div></div><div class=\"mark\">{document_mark}</div></div>
<div class=\"barcode-wrap\">{barcode_svg}<div class=\"barcode-text\">{html.escape(order_no)}</div></div>
<div class=\"info\">
<div><b>出貨日期：</b>{html.escape(header['order_date'])}</div><div><b>物流商：</b>{html.escape(header['carrier'])}</div>
<div><b>分店：</b>{html.escape(header['branch_code'])} {html.escape(header['branch_name'])}</div><div><b>託運單號：</b>{html.escape(header['tracking_no'] or '待補')}</div>
<div><b>地址：</b>{html.escape(header['address'] or '未填寫')}</div><div><b>聯絡人：</b>{html.escape(header['contact_name'] or '未填寫')} {html.escape(header['contact_phone'] or '')}</div>
<div><b>箱數：</b>{header['box_count']} 箱</div><div><b>建立人員：</b>{html.escape(header['created_by'])}</div>
</div>
<table><thead><tr><th>#</th><th>商品條碼</th><th>商品名稱</th><th>建議儲位／效期批次</th><th>數量</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class=\"footer\"><span>請依建議儲位撿貨，包裝時須掃描此單號及所有商品。</span><span>列印時間：{Utils.now_text()}</span></div>
</div></body></html>"""
        filename = f"{order_no}_出貨單_{print_count}.html"
        self.write_print_file(filename, content)

    def print_receiving_document(self, order_no, reason=None):
        header = self.svc.receiving.receiving_order_header(order_no)
        if not header:
            raise ValueError("查無進貨單")
        print_count = self.svc.receiving.mark_receiving_order_printed(order_no)
        document_mark = "正本" if print_count == 1 else f"補印第 {print_count - 1} 次"
        self.svc.log.log_operation(
            self.current_user, "列印進貨單" if print_count == 1 else "補印進貨單",
            order_no, reason or ("正本首次列印" if print_count == 1 else "-"),
        )
        rows = []
        for line in self.svc.receiving.receiving_order_lines(order_no):
            rows.append(
                "<tr>"
                f"<td>{line['line_no']}</td>"
                f"<td>{html.escape(line['barcode'])}</td>"
                f"<td>{html.escape(line['product_name'])}</td>"
                f"<td class=\"qty\">{line['required_qty']}</td>"
                "</tr>"
            )
        barcode_svg = self.code39_svg(order_no, height=72)
        content = f"""<!doctype html>
<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><title>{html.escape(order_no)} 進貨單</title>
<style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: \"Microsoft JhengHei\", Arial, sans-serif; color:#172033; font-size:12px; }}
.sheet {{ max-width: 190mm; margin:auto; }} .top {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #1f5eff; padding-bottom:12px; }}
h1 {{ margin:0; font-size:25px; }} .mark {{ border:1px solid #f0a000; color:#9a5d00; padding:5px 10px; font-weight:bold; }}
.barcode-wrap {{ text-align:center; margin:13px 0 9px; }} .barcode {{ width:285px; height:72px; }} .barcode-text {{ letter-spacing:1px; font-weight:bold; }}
.info {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 28px; margin:12px 0 16px; }} .info div {{ border-bottom:1px solid #d9dfeb; padding:5px 0; }}
table {{ width:100%; border-collapse:collapse; }} th {{ background:#eaf0ff; }} th,td {{ border:1px solid #aebbd0; padding:8px; text-align:left; vertical-align:top; }} td.qty {{ text-align:center; font-size:15px; font-weight:bold; }}
.footer {{ margin-top:20px; display:flex; justify-content:space-between; color:#56657f; }} @media print {{ .no-print {{ display:none; }} }}
</style></head><body><div class=\"sheet\">
<div class=\"top\"><div><h1>供應商進貨單</h1><div>單據狀態：{html.escape(header['status'])}</div></div><div class=\"mark\">{document_mark}</div></div>
<div class=\"barcode-wrap\">{barcode_svg}<div class=\"barcode-text\">{html.escape(order_no)}</div></div>
<div class=\"info\">
<div><b>進貨日期：</b>{html.escape(header['order_date'])}</div><div><b>廠商：</b>{html.escape(header['supplier_name'])}</div>
<div><b>建立人員：</b>{html.escape(header['created_by'])}</div><div><b>建立時間：</b>{html.escape(header['created_at'])}</div>
<div><b>備註：</b>{html.escape(header['note'] or '—')}</div>
</div>
<table><thead><tr><th>#</th><th>商品條碼</th><th>商品名稱</th><th>預計數量</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class=\"footer\"><span>請依此單核對到貨商品，驗收時須掃描此單號及所有商品。</span><span>列印時間：{Utils.now_text()}</span></div>
</div></body></html>"""
        filename = f"{order_no}_進貨單_{print_count}.html"
        self.write_print_file(filename, content)

    def print_return_document(self, return_no):
        header = self.svc.returns.return_order_header(return_no)
        if not header:
            raise ValueError("查無退貨單")
        receiving = self.svc.receiving.receiving_order_header(header["receiving_order_no"])
        supplier = receiving["supplier_name"] if receiving else "未指定"
        evidence_html = "<p class=\"empty\">未附異常照片</p>"
        evidence_path = Path(header["evidence_path"]) if header["evidence_path"] else None
        if evidence_path and evidence_path.is_file():
            evidence_html = (
                f'<img class="evidence" src="{html.escape(evidence_path.resolve().as_uri(), quote=True)}" '
                'alt="商品異常證據照片">'
            )
        barcode_svg = self.code39_svg(return_no, height=62)
        content = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>{html.escape(return_no)} 退貨表</title>
<style>
@page {{ size:A4; margin:12mm; }}
body {{ font-family:"Microsoft JhengHei", Arial, sans-serif; color:#172033; font-size:12px; }}
.sheet {{ max-width:190mm; margin:auto; }} .top {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #c92a2a; padding-bottom:10px; }}
h1 {{ margin:0; font-size:26px; }} .status {{ color:#9d1c1c; border:1px solid #c92a2a; padding:5px 10px; font-weight:bold; }}
.barcode-wrap {{ text-align:center; margin:12px 0; }} .barcode {{ width:270px; height:62px; }}
.info {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 24px; margin:10px 0 15px; }} .info div {{ border-bottom:1px solid #d9dfeb; padding:6px 0; }}
table {{ width:100%; border-collapse:collapse; margin-top:10px; }} th {{ background:#fff0f0; }} th,td {{ border:1px solid #aebbd0; padding:9px; text-align:left; }} td.qty {{ text-align:center; font-size:16px; font-weight:bold; }}
.evidence-box {{ border:1px solid #aebbd0; margin-top:16px; padding:10px; }} .evidence {{ max-width:100%; max-height:120mm; display:block; margin:8px auto 0; }} .empty {{ color:#56657f; }}
.footer {{ margin-top:20px; display:flex; justify-content:space-between; color:#56657f; }}
</style></head><body><div class="sheet">
<div class="top"><div><h1>供應商退貨表</h1><div>商品異常退貨／還貨證明</div></div><div class="status">{html.escape(header['status'])}</div></div>
<div class="barcode-wrap">{barcode_svg}<div><b>{html.escape(return_no)}</b></div></div>
<div class="info">
<div><b>退貨單號：</b>{html.escape(return_no)}</div><div><b>原進貨單號：</b>{html.escape(header['receiving_order_no'])}</div>
<div><b>供應商：</b>{html.escape(supplier)}</div><div><b>建立時間：</b>{html.escape(header['created_at'])}</div>
<div><b>建立人員：</b>{html.escape(header['created_by'])}</div><div><b>退貨原因：</b>{html.escape(header['return_reason'])}</div>
</div>
<table><thead><tr><th>商品條碼</th><th>商品名稱</th><th>退貨數量</th><th>異常原因</th></tr></thead>
<tbody><tr><td>{html.escape(header['barcode'])}</td><td>{html.escape(header['product_name'])}</td><td class="qty">{header['return_qty']}</td><td>{html.escape(header['return_reason'])}</td></tr></tbody></table>
<div class="evidence-box"><b>商品異常證據照片</b>{evidence_html}</div>
<div class="evidence-box"><b>備註：</b>{html.escape(header['note'] or '—')}</div>
<div class="footer"><span>此表供供應商核對退貨商品與異常證據使用。</span><span>列印時間：{Utils.now_text()}</span></div>
</div></body></html>"""
        self.write_print_file(f"{return_no}_退貨表.html", content)

    def print_label_document(self, order_no, reason=None):
        header = self.svc.shipping.order_header(order_no)
        if not header:
            raise ValueError("查無出貨單")
        if header["status"] != "已完成":
            raise ValueError("只有完成包裝的出貨單可以列印物流箱標")
        # 熱感貼紙模式：以 TSPL 指令直接吐紙（系統設定指定貼紙機與尺寸），不經瀏覽器。
        if self.svc.settings.get_setting("label_engine") == "TSPL":
            for box_number in range(1, header["box_count"] + 1):
                self.svc.settings.print_label_tspl(
                    order_no, box_number, header["box_count"],
                    f"{header['branch_code']} {header['branch_name']}",
                    header["address"] or "地址未填寫",
                    header["carrier"], header["tracking_no"] or "",
                    header["order_date"],
                )
            label_print_count = self.svc.shipping.mark_label_printed(order_no)
            self.svc.log.log_operation(
                self.current_user, "列印箱標" if label_print_count == 1 else "補印箱標",
                order_no, reason or ("正本首次列印（TSPL 熱感）" if label_print_count == 1 else "TSPL 熱感"),
            )
            return
        label_width, label_height = self.svc.settings.get_setting("label_paper").split("x")
        labels = []
        for box_number in range(1, header["box_count"] + 1):
            label_code = f"{order_no}-B{box_number}"
            barcode_svg = self.code39_svg(label_code, height=72)
            labels.append(
                f"""<section class=\"label\">
<div class=\"label-top\"><h1>物流箱標</h1><div>第 {box_number} 箱／共 {header['box_count']} 箱</div></div>
<div class=\"branch\">{html.escape(header['branch_code'])} {html.escape(header['branch_name'])}</div>
<div class=\"address\">{html.escape(header['address'] or '地址未填寫')}</div>
<div class=\"grid\"><div><b>物流商</b><br>{html.escape(header['carrier'])}</div><div><b>託運單號</b><br>{html.escape(header['tracking_no'] or '待補')}</div><div><b>出貨日期</b><br>{html.escape(header['order_date'])}</div><div><b>出貨單號</b><br>{html.escape(order_no)}</div></div>
<div class=\"barcode-wrap\">{barcode_svg}<div>{html.escape(label_code)}</div></div>
<div class=\"note\">內部箱標。官方蝦皮／嘉里大榮面單需由物流後台或 API 取得。</div>
</section>"""
            )
        content = f"""<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><title>{html.escape(order_no)} 物流箱標</title>
<style>
@page {{ size: {label_width}mm {label_height}mm; margin:5mm; }} body {{ margin:0; font-family:\"Microsoft JhengHei\", Arial, sans-serif; color:#172033; }}
.label {{ width:90mm; min-height:138mm; border:2px solid #172033; box-sizing:border-box; padding:6mm; page-break-after:always; }}
.label:last-child {{ page-break-after:auto; }} .label-top {{ display:flex; justify-content:space-between; align-items:baseline; border-bottom:2px solid #1f5eff; }} h1 {{ margin:0 0 4mm; font-size:22px; }} .branch {{ font-size:19px; font-weight:bold; margin-top:5mm; }} .address {{ margin-top:3mm; min-height:11mm; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:3mm; margin-top:5mm; }} .grid div {{ border:1px solid #aebbd0; padding:3mm; min-height:10mm; }} .barcode-wrap {{ text-align:center; margin-top:7mm; font-weight:bold; }} .barcode {{ width:74mm; height:72px; }} .note {{ margin-top:5mm; font-size:10px; color:#56657f; }}
</style></head><body>{''.join(labels)}</body></html>"""
        label_print_count = self.svc.shipping.mark_label_printed(order_no)
        self.svc.log.log_operation(
            self.current_user, "列印箱標" if label_print_count == 1 else "補印箱標",
            order_no, reason or ("正本首次列印" if label_print_count == 1 else "-"),
        )
        self.write_print_file(f"{order_no}_物流箱標.html", content)

    # ---------- Treeview 滾動條 ----------

    def add_tree_scrollbar(self, parent, tree):
        """Treeview 與捲軸必須建立在同一個父容器；小螢幕表格過寬時可用底部橫向捲軸。

        另外把觸控板雙指左右滑（Shift-滾輪事件）接到表格的橫向捲動，
        不必再去拖底部的捲軸。"""
        vertical = tb.Scrollbar(parent, orient="vertical", command=tree.yview)
        horizontal = tb.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill=X)
        vertical.pack(side=RIGHT, fill=Y)
        tree.pack(side=LEFT, fill=BOTH, expand=True)

        def scroll_horizontal(event, table=tree):
            steps = self._wheel_steps(event)
            if not steps:
                return "break"
            first, last = table.xview()
            if first <= 0.0 and last >= 1.0:
                # 表格本身放得下、不需捲動時，左右滑改捲動整個頁面。
                try:
                    if self.content_frame.winfo_reqwidth() > self.content_canvas.winfo_width():
                        self.content_canvas.xview_scroll(steps, "units")
                except Exception:
                    pass
            else:
                table.xview_scroll(steps, "units")
            return "break"

        tree.bind("<Shift-MouseWheel>", scroll_horizontal, add="+")
        tree.bind("<Shift-Button-4>", scroll_horizontal, add="+")
        tree.bind("<Shift-Button-5>", scroll_horizontal, add="+")
