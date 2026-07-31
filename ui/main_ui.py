"""MainUIMixin：登入、主框架、側欄權限選單與共用 UI 元件。"""
from utils.constants import *
from utils.helpers import Utils
from database import DBManager
from services import Services
import json
from tkinter import font as tkfont

class MainUIMixin:
    """WMS 的主要使用者介面。"""

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_VERSION} - 物流與庫存管理")
        # 視窗大小以螢幕為上限，避免小螢幕筆電底部被切在螢幕外。
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(1500, screen_width - 40)
        window_height = min(900, screen_height - 120)
        offset_x = max((screen_width - window_width) // 2, 0)
        self.root.geometry(f"{window_width}x{window_height}+{offset_x}+24")
        self.root.minsize(960, 600)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass
        self.db = DBManager()
        self.svc = Services(self.db)
        # 先讀取顯示縮放設定再套用樣式；小螢幕筆電可在「系統設定」把縮放調小。
        try:
            import utils.constants as _constants
            stored_scale = self.svc.settings.get_setting("ui_scale") or "1.3"
            scale = float(stored_scale)
            # 小螢幕自動調降：使用者沒改過縮放、且螢幕偏矮時，直接改用 100%。
            if stored_scale == SETTING_DEFAULTS["ui_scale"] and screen_height < 1000:
                scale = 1.0
                self.svc.settings.set_setting("ui_scale", "1.0")
            _constants.FONT_SCALE = min(max(scale, 0.8), 1.6)
        except (TypeError, ValueError):
            pass
        self._configure_accessible_styles()
        self.current_user = None
        self.current_username = None
        self.current_role = None
        self.login_time = None
        self.active_order_no = None
        self.active_receiving_order_no = None
        self.shipping_read_only = False
        self.receiving_read_only = False
        self.order_draft_items = []
        self.receiving_draft_items = []
        self.product_selected_barcode = None
        self.branch_selected_id = None
        # 跨頁上下文：最近一次點選／複製的單號與條碼，切換頁面時自動帶入。
        self.last_context = {"orders": {}, "barcode": ""}
        # 滾輪方向（系統設定可反轉；快取避免每次滾動查資料庫）。
        self._scroll_invert = self.svc.settings.get_setting_bool("invert_scroll")
        self.svc.returns.process_due_scrap_holds("SYSTEM")
        self.root.after(60 * 60 * 1000, self._run_scheduled_scrap_writeoff)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_login_view()

    # ---------- 權限 ----------

    def has_perm(self, permission):
        return self.svc.auth.has_permission(self.current_role, permission)

    def _configure_accessible_styles(self):
        """Globally apply the requested 130% scale and visible table heading borders."""
        base_size = scaled_font(10)
        try:
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                tkfont.nametofont(name).configure(family=FONT_FAMILY, size=base_size)
            style = tb.Style()
            # 表格化外觀：外框實線、表頭立體邊線，加上斑馬紋近似 Word/Excel 表格。
            style.configure("Treeview", font=(FONT_FAMILY, base_size), rowheight=scaled_font(24),
                            borderwidth=1, relief="solid")
            style.configure("Treeview.Heading", font=(FONT_FAMILY, base_size, "bold"), relief="raised", borderwidth=2)
            style.configure("TButton", font=(FONT_FAMILY, base_size))
            style.configure("TEntry", font=(FONT_FAMILY, base_size))
            style.configure("TCombobox", font=(FONT_FAMILY, base_size))
            style.configure("TLabelframe.Label", font=(FONT_FAMILY, base_size, "bold"))
        except tk.TclError:
            pass

    def _run_scheduled_scrap_writeoff(self):
        try:
            self.svc.returns.process_due_scrap_holds("SYSTEM")
            if self.widget_alive("scrap_tree"):
                self.refresh_scrap_view()
        finally:
            self.root.after(60 * 60 * 1000, self._run_scheduled_scrap_writeoff)

    def on_close(self):
        if self.current_user:
            try:
                self.svc.log.log_operation(self.current_user, "登出", note=f"登入者：{self.current_user}")
            except Exception:
                pass
        self.svc.close()
        self.root.destroy()

    # ---------- 登入畫面 ----------

    def build_login_view(self):
        """啟動時先顯示登入畫面；帳號、角色與鎖定規則由 users 資料表控管。"""
        self.login_frame = tb.Frame(self.root, bootstyle="light")
        self.login_frame.pack(fill=BOTH, expand=True)

        card = tb.Frame(self.login_frame, bootstyle="light", padding=30)
        card.place(relx=0.5, rely=0.5, anchor=CENTER)

        tb.Label(
            card, text="Rditrix WMS Lite", font=("Microsoft JhengHei", 26, "bold"), bootstyle="primary"
        ).pack(anchor=W)
        tb.Label(
            card, text=f"{APP_VERSION}　請登入以繼續", font=("Microsoft JhengHei", 10), bootstyle="secondary"
        ).pack(anchor=W, pady=(0, 18))

        form = tb.Frame(card)
        form.pack(fill=X)
        self.login_account_entry = tb.Entry(form, width=28)
        self.login_password_entry = tb.Entry(form, width=28, show="*")
        self.login_name_entry = tb.Entry(form, width=28)
        rows = [
            ("帳號", self.login_account_entry),
            ("密碼", self.login_password_entry),
            ("使用者姓名", self.login_name_entry),
        ]
        for index, (label, widget) in enumerate(rows):
            tb.Label(form, text=f"{label}:").grid(row=index, column=0, sticky=W, padx=(0, 10), pady=7)
            widget.grid(row=index, column=1, sticky=W, pady=7)
        tb.Label(
            card, text="使用者姓名會記錄在所有操作紀錄中，方便追蹤實際操作人。",
            font=("Microsoft JhengHei", 9), bootstyle="secondary",
        ).pack(anchor=W, pady=(2, 0))

        self.login_status = tb.Label(card, text="", bootstyle="danger", wraplength=380, justify=LEFT)
        self.login_status.pack(anchor=W, pady=(6, 6))

        tb.Button(card, text="登入", bootstyle="primary", command=self.attempt_login).pack(anchor="e", pady=(6, 0))

        self.login_account_entry.bind("<Return>", lambda _e: self.login_password_entry.focus_set())
        self.login_password_entry.bind("<Return>", lambda _e: self.login_name_entry.focus_set())
        self.login_name_entry.bind("<Return>", lambda _e: self.attempt_login())
        self.login_account_entry.focus_set()

    def attempt_login(self):
        account = self.login_account_entry.get().strip()
        password = self.login_password_entry.get().strip()
        name = self.login_name_entry.get().strip()
        if not name:
            return self.set_status(self.login_status, "使用者姓名為必填（記錄在操作紀錄中，方便追蹤）", "danger")
        try:
            user = self.svc.auth.login(account, password)
        except ValueError as error:
            self.login_password_entry.delete(0, END)
            return self.set_status(self.login_status, str(error), "danger")
        # 操作紀錄一律以登入畫面輸入的姓名為操作人；帳號與角色另記在備註供稽核。
        self.current_user = name
        self.current_username = user["username"]
        self.current_role = user["role"]
        self.login_time = Utils.now_text()
        self.svc.log.log_operation(
            self.current_user, "登入",
            note=(f"帳號 {user['username']}／{user['display_name']}"
                  f"（{ROLE_LABELS.get(user['role'], user['role'])}），登入時間 {self.login_time}"),
        )
        self.login_frame.destroy()
        self.build_ui()
        self.show_view("dashboard")

    # ---------- 共用 UI ----------

    def build_ui(self):
        main_frame = tb.Frame(self.root)
        main_frame.pack(fill=BOTH, expand=True)

        self.sidebar = tb.Frame(main_frame, bootstyle="dark", width=220)
        self.sidebar.pack(side=LEFT, fill=Y)
        self.sidebar.pack_propagate(False)

        tb.Label(
            self.sidebar,
            text="Rditrix WMS Lite",
            font=("Microsoft JhengHei", 15, "bold"),
            bootstyle="inverse-dark",
        ).pack(anchor=W, padx=22, pady=(12, 0))
        tb.Label(
            self.sidebar,
            text="物流與庫存管理",
            font=("Microsoft JhengHei", 9),
            bootstyle="inverse-secondary",
        ).pack(anchor=W, padx=24, pady=(0, 8))

        # 依角色動態顯示功能；標記權限鍵的項目僅在具備權限時出現。
        self.menu_buttons = {}
        menu_items = [
            ("總覽", "dashboard", None),
            ("商品主檔", "products", None),
            ("庫存查詢", "inventory", None),
            ("進貨作業", "receiving", None),
            ("上架作業", "putaway", None),
            ("出貨單管理", "orders", None),
            ("出貨作業", "shipping", None),
            ("動態盤點", "cycle", None),
            ("盤點平帳", "counting", "force_adjust_stock"),
            ("耗材報銷", "consumables", None),
            ("儲位管理", "shelves", "manage_shelves"),
            ("報廢作業", "scrap", "scrap_stock"),
            ("分店管理", "branches", "manage_branches"),
            ("退貨作業", "returns", None),
            ("統計報表", "reports", None),
            ("作業紀錄", "history", None),
            ("防呆設定", "guards", "manage_settings"),
            ("系統設定", "system", "manage_settings"),
            ("帳號管理", "accounts", "manage_accounts"),
        ]
        # 小螢幕防呆：登入資訊固定在底部，選單本體放進可捲動的 Canvas，
        # 螢幕高度不足時選單可用滾輪捲動，不會被裁切。
        tb.Label(
            self.sidebar,
            text=(f"登入者\n{self.current_user}（{ROLE_LABELS.get(self.current_role, self.current_role)}）\n"
                  f"登入時間 {self.login_time}"),
            justify=LEFT,
            font=("Microsoft JhengHei", 9),
            bootstyle="inverse-secondary",
        ).pack(side="bottom", anchor=W, padx=22, pady=8)
        # 今日待辦摘要：利用側欄下方空間，一開程式就知道還有什麼事要做。
        self.sidebar_todo_label = tb.Label(
            self.sidebar, text="", justify=LEFT,
            font=("Microsoft JhengHei", 9), bootstyle="inverse-dark",
        )
        self.sidebar_todo_label.pack(side="bottom", anchor=W, padx=22, pady=(0, 6))

        dark_color = tb.Style().colors.dark
        menu_holder = tb.Frame(self.sidebar, bootstyle="dark")
        menu_holder.pack(fill=BOTH, expand=True)
        self.menu_canvas = tk.Canvas(menu_holder, highlightthickness=0, bd=0, background=dark_color)
        self._menu_scrollbar = tb.Scrollbar(menu_holder, orient="vertical",
                                            command=self.menu_canvas.yview, bootstyle="dark-round")
        self.menu_canvas.configure(yscrollcommand=self._menu_scrollbar.set)
        # 捲軸預設不顯示；選單放不下時才出現（大螢幕保持固定不動）。
        self.menu_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        menu_inner = tb.Frame(self.menu_canvas, bootstyle="dark")
        self._menu_window = self.menu_canvas.create_window((0, 0), window=menu_inner, anchor="nw")
        menu_inner.bind("<Configure>", self._sync_menu_scroll)
        self.menu_canvas.bind("<Configure>", self._sync_menu_scroll)

        for text, mode, permission in menu_items:
            if permission and not self.has_perm(permission):
                continue
            button = tb.Button(
                menu_inner,
                text=text,
                bootstyle="dark-outline",
                command=lambda selected=mode: self.show_view(selected),
            )
            button.pack(fill=X, padx=12, pady=1)
            self.menu_buttons[mode] = button

        # RWD：內容區以 Canvas + 雙向捲軸（grid 排版）包裹；
        # 小螢幕或高縮放時，垂直／水平放不下的部分都能捲動，捲軸自動顯示／隱藏。
        content_holder = tb.Frame(main_frame, bootstyle="light")
        content_holder.pack(side=RIGHT, fill=BOTH, expand=True, padx=(20, 4), pady=(14, 4))
        content_holder.rowconfigure(0, weight=1)
        content_holder.columnconfigure(0, weight=1)
        self.content_canvas = tk.Canvas(content_holder, highlightthickness=0, bd=0,
                                        background=tb.Style().colors.light)
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        content_scrollbar = tb.Scrollbar(content_holder, orient="vertical",
                                         command=self.content_canvas.yview)
        content_scrollbar.grid(row=0, column=1, sticky="ns")
        self._content_hscroll = tb.Scrollbar(content_holder, orient="horizontal",
                                             command=self.content_canvas.xview)
        self._content_hscroll.grid(row=1, column=0, sticky="ew")
        self._content_hscroll.grid_remove()
        self.content_canvas.configure(yscrollcommand=content_scrollbar.set,
                                      xscrollcommand=self._content_hscroll.set)
        self._content_layout = None
        self.content_frame = tb.Frame(self.content_canvas, bootstyle="light")
        self._content_window = self.content_canvas.create_window(
            (0, 0), window=self.content_frame, anchor="nw"
        )
        self.content_canvas.bind("<Configure>", self._sync_content_size)
        self.content_frame.bind("<Configure>", self._sync_content_size)
        self.root.bind_all("<MouseWheel>", self._on_content_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_content_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._on_content_mousewheel, add="+")
        # 觸控板雙指左右滑（Mac 會送出 Shift-滾輪事件）＝整頁橫向捲動。
        self.root.bind_all("<Shift-MouseWheel>", self._on_content_mousewheel, add="+")
        self.root.bind_all("<Shift-Button-4>", self._on_content_mousewheel, add="+")
        self.root.bind_all("<Shift-Button-5>", self._on_content_mousewheel, add="+")

        self.setup_context_menus()

        view_builders = {
            "dashboard": self.build_dashboard_view,
            "products": self.build_product_view,
            "branches": self.build_branch_view,
            "shelves": self.build_shelf_view,
            "scrap": self.build_scrap_view,
            "inventory": self.build_inventory_view,
            "receiving": self.build_receiving_view,
            "returns": self.build_returns_view,
            "putaway": self.build_putaway_view,
            "orders": self.build_orders_view,
            "shipping": self.build_shipping_view,
            "cycle": self.build_cycle_count_view,
            "counting": self.build_counting_view,
            "consumables": self.build_consumable_view,
            "reports": self.build_reports_view,
            "history": self.build_history_view,
            "guards": self.build_guard_settings_view,
            "system": self.build_system_settings_view,
            "accounts": self.build_account_view,
        }
        self.views = {
            mode: builder() for mode, builder in view_builders.items()
            if mode in self.menu_buttons
        }

    def _menu_overflows(self):
        """側欄選單內容是否超過可視高度（超過才允許捲動）。"""
        try:
            bbox = self.menu_canvas.bbox("all")
            if not bbox:
                return False
            return (bbox[3] - bbox[1]) > self.menu_canvas.winfo_height()
        except tk.TclError:
            return False

    def _sync_menu_scroll(self, _event=None):
        """大螢幕：選單固定、捲軸隱藏；小螢幕放不下時才顯示捲軸並允許捲動。"""
        try:
            canvas_width = self.menu_canvas.winfo_width()
            canvas_height = self.menu_canvas.winfo_height()
            self.menu_canvas.itemconfigure(self._menu_window, width=canvas_width)
            bbox = self.menu_canvas.bbox("all")
            content_height = (bbox[3] - bbox[1]) if bbox else 0
            if content_height > canvas_height:
                self.menu_canvas.configure(scrollregion=(0, 0, canvas_width, content_height))
                if not self._menu_scrollbar.winfo_ismapped():
                    self._menu_scrollbar.pack(side=RIGHT, fill=Y)
            else:
                # 放得下：把捲動範圍鎖成可視高度，滾輪就不會讓選單彈跳。
                self.menu_canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
                self.menu_canvas.yview_moveto(0)
                if self._menu_scrollbar.winfo_ismapped():
                    self._menu_scrollbar.pack_forget()
        except tk.TclError:
            pass

    def _sync_content_size(self, _event=None):
        """內容貼齊視窗；高度或寬度放不下時自動出現對應捲軸，放得下則隱藏。

        以快取避免重複套用同一組尺寸造成 Configure 事件風暴。"""
        try:
            canvas_width = self.content_canvas.winfo_width()
            canvas_height = self.content_canvas.winfo_height()
            if canvas_width <= 1 or canvas_height <= 1:
                return
            required_width = self.content_frame.winfo_reqwidth()
            required_height = self.content_frame.winfo_reqheight()
            width = max(canvas_width, required_width)
            height = max(canvas_height, required_height)
            show_horizontal = required_width > canvas_width
            layout = (width, height, show_horizontal)
            if layout == self._content_layout:
                return
            self._content_layout = layout
            self.content_canvas.itemconfigure(self._content_window, width=width, height=height)
            self.content_canvas.configure(scrollregion=(0, 0, width, height))
            if show_horizontal:
                self._content_hscroll.grid()
            else:
                self._content_hscroll.grid_remove()
                self.content_canvas.xview_moveto(0)
        except tk.TclError:
            pass

    def _wheel_steps(self, event):
        if getattr(event, "num", None) == 4:
            steps = -2
        elif getattr(event, "num", None) == 5:
            steps = 2
        elif getattr(event, "delta", 0):
            steps = -2 if event.delta > 0 else 2
        else:
            return 0
        # 不同平台／滑鼠的滾動慣例相反時，可在系統設定勾選反轉。
        return -steps if self._scroll_invert else steps

    def _on_content_mousewheel(self, event):
        """內容超出視窗時支援滾輪捲動；表格內滾動仍交給表格本身，側欄選單也可捲動。"""
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        in_sidebar = False
        while widget is not None:
            try:
                if widget is getattr(self, "sidebar", None):
                    in_sidebar = True
                    break
                if widget.winfo_class() in ("Treeview", "Text", "Listbox", "TCombobox"):
                    return
            except tk.TclError:
                return
            widget = getattr(widget, "master", None)
        steps = self._wheel_steps(event)
        if not steps:
            return
        try:
            if in_sidebar:
                if self._menu_overflows():
                    self.menu_canvas.yview_scroll(steps, "units")
                return
            # 按住 Shift 滾動＝左右捲動（表單太寬時使用）。
            if getattr(event, "state", 0) & 0x1:
                if self.content_frame.winfo_reqwidth() > self.content_canvas.winfo_width():
                    self.content_canvas.xview_scroll(steps, "units")
                return
            if self.content_frame.winfo_reqheight() <= self.content_canvas.winfo_height():
                return
            self.content_canvas.yview_scroll(steps, "units")
        except Exception:
            # 捲動屬輔助功能，任何例外都不應中斷操作。
            pass

    def make_title(self, frame, title, subtitle):
        header = tb.Frame(frame, bootstyle="light")
        header.pack(fill=X, pady=(0, 14))
        tb.Label(
            header,
            text=title,
            font=("Microsoft JhengHei", 20, "bold"),
            bootstyle="inverse-light",
        ).pack(anchor=W)
        tb.Label(
            header,
            text=subtitle,
            font=("Microsoft JhengHei", 10),
            bootstyle="secondary",
        ).pack(anchor=W, pady=(2, 0))

    def widget_alive(self, name):
        """跨頁面共用元件更新前的防呆：屬性存在且 widget 尚未被銷毀。"""
        widget = getattr(self, name, None)
        try:
            return widget is not None and bool(widget.winfo_exists())
        except tk.TclError:
            return False

    def clear_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def set_status(self, label, text, style="secondary"):
        label.configure(text=text, bootstyle=style)

    def show_toast(self, text, bootstyle="dark"):
        """畫面底部短暫提示（複製成功等輕量回饋）。"""
        toast = tb.Label(self.root, text=text, bootstyle=f"inverse-{bootstyle}",
                         font=(FONT_FAMILY, scaled_font(10)), padding=(16, 8))
        toast.place(relx=0.5, rely=0.93, anchor=CENTER)
        self.root.after(1500, toast.destroy)

    def setup_tree_columns(self, tree, columns, headings, widths, left_columns=()):
        """共用：設定 Treeview 欄位標題、寬度與對齊方式，避免重複 for 迴圈。

        只有名稱／備註類欄位（left_columns）與最後一欄自動延展；
        其餘欄位拖拉分隔線調整後不會被重新分配，欄寬所見即所得。"""
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            stretchable = column in left_columns or column == columns[-1]
            tree.column(column, width=width, minwidth=40, stretch=stretchable,
                        anchor=W if column in left_columns else CENTER)
        tree.bind("<ButtonRelease-1>", lambda _event, table=tree: self._save_tree_layout(table), add="+")
        tree.bind("<Motion>", lambda event, table=tree: self._update_header_cursor(event, table), add="+")
        self._restore_tree_layout(tree, columns)
        # 表格化外觀：斑馬紋交錯列，行與行之間更容易對齊閱讀。
        self._enable_tree_stripes(tree)

    def _enable_tree_stripes(self, tree):
        """讓表格每隔一列淡藍底色（近似 Excel 表格效果）；
        既有的狀態底色標籤（完成／取消等）優先於斑馬紋。"""
        tree.tag_configure("stripe", background="#EDF2F9")
        base_insert = tree.insert

        def striped_insert(parent="", index=END, *args, **kwargs):
            item = base_insert(parent, index, *args, **kwargs)
            if len(tree.get_children("")) % 2 == 0:
                existing = tree.item(item, "tags") or ()
                tree.item(item, tags=tuple(existing) + ("stripe",))
            return item

        tree.insert = striped_insert

    def _table_layout_path(self):
        return Path(__file__).resolve().parent.parent / "table_layouts.json"

    def _restore_tree_layout(self, tree, columns):
        try:
            layouts = json.loads(self._table_layout_path().read_text(encoding="utf-8"))
            for column, width in layouts.get(str(tree), {}).items():
                if column in columns:
                    tree.column(column, width=max(tree.column(column, "minwidth"), int(width)))
        except (OSError, ValueError, tk.TclError):
            pass

    def _save_tree_layout(self, tree):
        try:
            path = self._table_layout_path()
            layouts = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            layouts[str(tree)] = {column: int(tree.column(column, "width")) for column in tree["columns"]}
            path.write_text(json.dumps(layouts, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError, tk.TclError):
            pass

    def _update_header_cursor(self, event, tree):
        """游標只在欄位分隔線上變成左右調整形狀，提示可拖拉調整欄寬。"""
        try:
            region = tree.identify_region(event.x, event.y)
            tree.configure(cursor="sb_h_double_arrow" if region == "separator" else "")
        except tk.TclError:
            pass

    def setup_context_menus(self):
        """提供一致的複製、貼上與表格欄位複製操作；字體放大以利滑鼠點選。"""
        self.table_selection_vars = {}
        self._context_tree = None
        self._context_cell_value = ""
        self._context_input = None

        menu_font = (FONT_FAMILY, scaled_font(11))
        self.tree_context_menu = tk.Menu(
            self.root, tearoff=0, font=menu_font, activeborderwidth=6
        )
        self.tree_context_menu.add_command(label="　複製此欄位　", command=self.copy_selected_tree_cell)
        self.tree_context_menu.add_command(label="　複製整列　", command=self.copy_selected_tree_row)
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(label="　匯出表格（Excel/CSV）　", command=self.export_context_tree_csv)

        self.input_context_menu = tk.Menu(
            self.root, tearoff=0, font=menu_font, activeborderwidth=6
        )
        self.input_context_menu.add_command(label="　剪下　", command=lambda: self.send_input_virtual_event("<<Cut>>"))
        self.input_context_menu.add_command(label="　複製　", command=lambda: self.send_input_virtual_event("<<Copy>>"))
        self.input_context_menu.add_command(label="　貼上　", command=lambda: self.send_input_virtual_event("<<Paste>>"))
        self.input_context_menu.add_separator()
        self.input_context_menu.add_command(label="　全選　", command=self.select_all_input_text)
        self.root.bind_all("<Button-3>", self.show_input_context_menu, add="+")

    def is_text_input_widget(self, widget):
        return widget.winfo_class() in {"Entry", "TEntry", "TCombobox", "Text"}

    def show_input_context_menu(self, event):
        if not self.is_text_input_widget(event.widget):
            return None
        self._context_input = event.widget
        try:
            self.input_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.input_context_menu.grab_release()
        return "break"

    def send_input_virtual_event(self, event_name):
        if self._context_input:
            self._context_input.event_generate(event_name)

    def select_all_input_text(self):
        if not self._context_input:
            return
        if self._context_input.winfo_class() == "Text":
            self._context_input.tag_add("sel", "1.0", "end-1c")
        else:
            self._context_input.selection_range(0, END)
            self._context_input.icursor(END)

    def copy_to_clipboard(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(value))
        self.root.update()

    # ---------- 跨頁上下文（單號／條碼自動帶入） ----------

    def remember_context(self, value):
        value = str(value or "").strip()
        if not value or value == "-":
            return
        match = re.fullmatch(r"(RO|SO|RT|BR|CC)-\d{8}-\d+", value.upper())
        if match:
            self.last_context["orders"][match.group(1)] = value.upper()
        elif Utils.valid_barcode(value.upper()):
            self.last_context["barcode"] = value.upper()

    def _prefill_entry(self, entry, value):
        try:
            if value and not entry.get().strip():
                entry.insert(0, value)
                return True
        except tk.TclError:
            pass
        return False

    def apply_view_context(self, mode):
        """切換頁面時，自動帶入上一頁點選／複製的單號或條碼，減少重複輸入。"""
        orders = self.last_context["orders"]
        prefills = {
            "receiving": [("recv_order_no", orders.get("RO"))],
            "shipping": [("pack_order_no", orders.get("SO"))],
            "returns": [("return_receiving_order_no", orders.get("RO")),
                        ("return_barcode", self.last_context["barcode"])],
            "putaway": [("put_barcode", self.last_context["barcode"])],
            "counting": [("cnt_barcode", self.last_context["barcode"])],
            "consumables": [("consumable_barcode", self.last_context["barcode"])],
        }
        filled = []
        for attr, value in prefills.get(mode, []):
            entry = getattr(self, attr, None)
            if entry is not None and value and self._prefill_entry(entry, value):
                filled.append(value)
        if filled:
            self.show_toast(f"已自動帶入：{'、'.join(filled)}", "info")

    def add_table_interactions(self, tree, info_parent):
        """讓每張表格能點選欄位、在底部確認內容並以右鍵複製。"""
        selected_text = tk.StringVar(value="點選表格欄位後，可在此選取文字或按右鍵複製；點擊單號／條碼欄位會自動複製。")
        self.table_selection_vars[tree] = selected_text

        selection_bar = tb.Frame(info_parent, bootstyle="light")
        selection_bar.pack(side="bottom", fill=X, pady=(7, 0))
        tb.Label(selection_bar, text="選取內容:", bootstyle="secondary").pack(side=LEFT, padx=(2, 7))
        display = tb.Entry(selection_bar, textvariable=selected_text, state="readonly")
        display.pack(side=LEFT, fill=X, expand=True)

        tree.bind("<Button-3>", lambda event, source=tree: self.show_tree_context_menu(event, source), add="+")
        tree.bind("<ButtonRelease-1>", lambda event, source=tree: self.update_tree_selection_display(event, source), add="+")
        tree.bind("<<TreeviewSelect>>", lambda _event, source=tree: self.update_tree_selection_from_row(source), add="+")

    def tree_cell_details(self, tree, row_id, column_id):
        if not row_id or not column_id:
            return "", ""
        try:
            column_index = int(column_id.replace("#", "")) - 1
            values = tree.item(row_id, "values")
            columns = tree.cget("columns")
            column_name = columns[column_index]
            heading = tree.heading(column_name, "text")
            return heading, values[column_index]
        except (IndexError, ValueError, tk.TclError):
            return "", ""

    def update_tree_selection_display(self, event, tree):
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if row_id:
            tree.selection_set(row_id)
            tree.focus(row_id)
        heading, value = self.tree_cell_details(tree, row_id, column_id)
        if heading and tree in self.table_selection_vars:
            self.table_selection_vars[tree].set(f"{heading}: {value}")
        # 一鍵複製：點擊單號／條碼類欄位即複製至剪貼簿並提示。
        if heading and value and str(value).strip() not in ("-", ""):
            if any(key in heading for key in ("單號", "條碼", "編號")):
                self.copy_to_clipboard(value)
                self.remember_context(value)
                self.show_toast(f"已複製：{value}")

    def update_tree_selection_from_row(self, tree):
        row_id = tree.focus()
        if not row_id or tree not in self.table_selection_vars:
            return
        values = tree.item(row_id, "values")
        columns = tree.cget("columns")
        if values and columns:
            self.table_selection_vars[tree].set(f"{tree.heading(columns[0], 'text')}: {values[0]}")
            self.remember_context(values[0])

    def show_tree_context_menu(self, event, tree):
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not row_id:
            return None
        tree.selection_set(row_id)
        tree.focus(row_id)
        heading, value = self.tree_cell_details(tree, row_id, column_id)
        self._context_tree = tree
        self._context_cell_value = value
        if heading and tree in self.table_selection_vars:
            self.table_selection_vars[tree].set(f"{heading}: {value}")
        try:
            self.tree_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_context_menu.grab_release()
        return "break"

    def copy_selected_tree_cell(self):
        self.copy_to_clipboard(self._context_cell_value)
        self.show_toast(f"已複製：{self._context_cell_value}")

    def copy_selected_tree_row(self):
        if not self._context_tree:
            return
        row_id = self._context_tree.focus()
        if row_id:
            self.copy_to_clipboard("\t".join(str(value) for value in self._context_tree.item(row_id, "values")))
            self.show_toast("已複製整列")

    # ---------- 表格匯出（Excel 可直接開啟的 CSV） ----------

    def export_context_tree_csv(self):
        if self._context_tree is not None:
            self.export_tree_csv(self._context_tree)

    def export_tree_csv(self, tree, default_name="表格匯出"):
        """把表格目前顯示的內容（含篩選結果）匯出成 Excel 可直接開啟的 CSV。"""
        columns = tree.cget("columns")
        headings = [tree.heading(column, "text") for column in columns]
        rows = [tree.item(item, "values") for item in tree.get_children("")]
        if not rows:
            return self.show_toast("表格目前沒有資料可匯出", "warning")
        path = filedialog.asksaveasfilename(
            title="匯出表格",
            defaultextension=".csv",
            initialfile=f"{default_name}_{Utils.today_text()}.csv",
            filetypes=[("Excel 可開啟的 CSV", "*.csv"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            # utf-8-sig（含 BOM）讓 Excel 直接雙擊開啟不會中文亂碼。
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(headings)
                writer.writerows(rows)
        except OSError as error:
            return self.show_toast(f"匯出失敗：{error}", "danger")
        self.svc.log.log_operation(self.current_user, "匯出表格", "",
                                   f"{default_name} {len(rows)} 筆 → {Path(path).name}")
        self.show_toast(f"已匯出 {len(rows)} 筆：{Path(path).name}", "success")

    # ---------- 側欄今日待辦 ----------

    def refresh_sidebar_todo(self):
        if not self.widget_alive("sidebar_todo_label"):
            return
        try:
            todo = self.svc.inventory.sidebar_todo_summary()
        except Exception:
            return
        self.sidebar_todo_label.configure(
            text=("── 今日待辦 ──\n"
                  f"待撿貨/包裝　{todo['pending_shipping']} 單\n"
                  f"待驗收　　　{todo['pending_receiving']} 單\n"
                  f"待上架　　　{todo['staging_batches']} 批\n"
                  f"即期品　　　{todo['near_expiry']} 批"),
        )

    def build_product_info_panel(self, parent, title="商品確認"):
        """作業畫面用的小型商品資訊表，避免只靠單行狀態文字確認。"""
        panel = tb.Labelframe(parent, text=title, bootstyle="info", padding=8)
        panel.pack(fill=X, pady=(0, 10))
        holder = tb.Frame(panel)
        columns = ("barcode", "sku", "name", "category", "expiry", "safety", "available", "shelf_qty")
        tree = tb.Treeview(holder, columns=columns, show="headings", height=2, bootstyle="info")
        headings = ("條碼", "SKU", "商品名稱", "分類", "保存期限", "安全庫存", "可用庫存", "查詢儲位庫存")
        widths = (150, 110, 220, 120, 100, 100, 100, 130)
        self.setup_tree_columns(tree, columns, headings, widths, left_columns=("name",))
        self.add_table_interactions(tree, panel)
        holder.pack(fill=X)
        self.add_tree_scrollbar(holder, tree)
        return tree

    def refresh_product_info_panel(self, tree, barcode_text, shelf_code=""):
        self.clear_tree(tree)
        barcode = Utils.normalize_barcode(barcode_text)
        if not barcode or not Utils.valid_barcode(barcode):
            return
        product = self.svc.product.product_by_barcode(barcode)
        if not product:
            tree.insert("", END, values=(barcode, "-", "查無商品主檔", "-", "-", "-", "-", "-"), tags=("warning",))
            return
        overview = self.svc.product.product_stock_overview(barcode, shelf_code.strip().upper())
        shelf_qty = overview["shelf_qty"] if overview["shelf_qty"] is not None else "-"
        tree.insert(
            "",
            END,
            values=(
                product["barcode"],
                product["sku"],
                product["name"],
                product["category"] or "-",
                "需要" if product["expiry_required"] else "不需要",
                product["safety_stock"],
                overview["available_qty"],
                shelf_qty,
            ),
        )

    def show_view(self, mode):
        if mode not in self.views:
            return self.show_toast("此功能需要更高的權限", "danger")
        for frame in self.views.values():
            frame.pack_forget()
        self.views[mode].pack(fill=BOTH, expand=True)

        for item_mode, button in self.menu_buttons.items():
            button.configure(bootstyle="primary" if item_mode == mode else "dark-outline")

        refreshers = {
            "dashboard": self.refresh_dashboard,
            "products": self.refresh_products,
            "branches": self.refresh_branches,
            "shelves": self.refresh_shelf_view,
            "scrap": self.refresh_scrap_view,
            "inventory": self.refresh_inventory,
            "receiving": self.refresh_receiving_view,
            "returns": self.refresh_returns_view,
            "putaway": self.refresh_putaway_view,
            "orders": self.refresh_orders_view,
            "cycle": self.refresh_cycle_count_view,
            "consumables": self.refresh_consumable_view,
            "reports": self.refresh_reports_view,
            "history": self.refresh_history,
            "guards": self.refresh_guard_settings_view,
            "system": self.refresh_system_settings_view,
            "accounts": self.refresh_account_view,
        }
        if mode in refreshers:
            refreshers[mode]()
        self.refresh_sidebar_todo()

        # 跨頁自動帶入上下文，再把游標移到主要輸入框。
        self.apply_view_context(mode)
        focus_widgets = {
            "receiving": "recv_order_no",
            "returns": "return_receiving_order_no",
            "putaway": "put_barcode",
            "shipping": "pack_order_no",
            "counting": "cnt_shelf",
            "consumables": "consumable_barcode",
        }
        if mode in focus_widgets:
            widget = getattr(self, focus_widgets[mode], None)
            if widget is not None:
                self.root.after(80, widget.focus_set)
        self.root.after(120, self._sync_content_size)
