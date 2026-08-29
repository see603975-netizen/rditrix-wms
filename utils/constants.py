"""
Rditrix WMS Lite V6.9 - 保養品物流管理系統

共用常數與共用匯入（UI 模組以 from utils.constants import * 取得）。

安裝需求：pip install ttkbootstrap
執行方式：python main.py
"""

import csv
import hashlib
import html
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    import ttkbootstrap as tb
    from ttkbootstrap.constants import BOTH, CENTER, END, EW, LEFT, RIGHT, W, X, Y
except ImportError:
    # 雲端 API 環境沒有圖形介面，Tkinter 不存在屬正常，
    # 只有桌面版 UI 會用到 tk / tb，API 模式不需要。
    tk = None
    tb = None


APP_VERSION = "Rditrix WMS Lite V6.9"

NO_EXPIRY_DATE = "9999-12-31"
SPECIAL_ZONES = ("Staging", "QC", "Scrap", "Outbound")
ACTIVE_ORDER_STATUSES = ("待撿貨", "包裝中")
CARRIERS = ("未指定", "蝦皮店到店", "嘉里大榮", "黑貓宅急便", "新竹物流", "自取")
RECEIVING_ORDER_STATUSES = ("已建立", "已送出訂單", "待驗收", "驗收中", "已完成")
RETURN_REASONS = ("凹損", "破損", "漏液", "中文標", "效期", "規格", "出產地", "其他")
PRODUCT_CATEGORIES = ("乳液", "乳霜", "化妝水", "精華液", "面膜", "耗材", "其他類別")
CONSUMABLE_CATEGORY = "耗材"

# ---------- 角色與權限 ----------

ROLE_OPERATOR = "OPERATOR"
ROLE_SUPERVISOR = "SUPERVISOR"
ROLE_ADMIN = "ADMIN"
ROLES = (ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_ADMIN)
ROLE_LABELS = {
    ROLE_OPERATOR: "現場作業員",
    ROLE_SUPERVISOR: "倉庫主管",
    ROLE_ADMIN: "系統管理員",
}

# 權限鍵 → 允許角色。UI 依此動態顯示／隱藏功能。
PERMISSIONS = {
    "create_orders": (ROLE_SUPERVISOR, ROLE_ADMIN),        # 建立／取消進出貨單據
    "manage_shelves": (ROLE_SUPERVISOR, ROLE_ADMIN),       # 儲位新增／修改／停用
    "manage_branches": (ROLE_SUPERVISOR, ROLE_ADMIN),      # 分店主檔
    "transfer_stock": (ROLE_SUPERVISOR, ROLE_ADMIN),       # 儲位間庫存調撥
    "scrap_stock": (ROLE_SUPERVISOR, ROLE_ADMIN),          # 報廢暫存建立／取消
    "cycle_count_close": (ROLE_SUPERVISOR, ROLE_ADMIN),    # 動態盤點完成與平帳
    "force_adjust_stock": (ROLE_ADMIN,),                   # 盲盤強制平帳（庫存強制修改）
    "return_review": (ROLE_ADMIN,),                        # 退貨審核（品檢判定／標記寄回）
    "manage_accounts": (ROLE_ADMIN,),                      # 帳號管理
    "manage_settings": (ROLE_ADMIN,),                      # 防呆設定／系統設定
}

# 防暴力破解：連續失敗次數與鎖定分鐘數。
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_MINUTES = 15

# ---------- 狀態碼中文對照（資料庫保留原碼，顯示一律轉中文） ----------

STATUS_LABELS = {
    # 買家退貨
    "PENDING_QC": "待品檢",
    "RESTOCKED": "已重新上架",
    "SCRAP_HOLD": "報廢暫存中",
    # 報廢暫存
    "PENDING": "暫存中（可取消）",
    "CANCELLED": "已取消",
    "WRITTEN_OFF": "已正式扣帳",
    # 供應商退貨（歷史資料若存英文碼也能顯示）
    "RETURN_PENDING": "待供應商確認",
    "RETURN_SHIPPED": "已寄回供應商",
}


def status_label(code):
    """單據狀態顯示一律走這裡：英文碼轉繁體中文，中文原樣返回。"""
    return STATUS_LABELS.get(code, code)


# ---------- 防呆／系統設定（app_settings 內的鍵與預設值） ----------

SETTING_DEFAULTS = {
    # 商業防呆
    "expiry_min_days": "180",          # 進貨效期須 >= 今日 + N 天；0 = 停用
    "near_expiry_warn_days": "90",     # 即期品警示天數
    "enforce_max_receiving": "1",      # 啟用商品最大進貨量限制（商品主檔逐品設定）
    # 商品主檔防呆
    "require_sku": "1",                # 建立商品必須輸入 SKU
    "require_barcode": "1",            # 建立商品必須輸入條碼；關閉後留空會自動產生內部代碼
    "allow_quick_receive": "0",        # 允許進貨一鍵完成驗收入庫（人工點數）
    "allow_quick_pack": "0",           # 允許出貨一鍵完成驗貨包裝（人工點數）
    "quick_complete_barcode": "",      # 出貨驗貨完成專用條碼（掃到即一鍵完成）
    "no_location_mode": "0",           # 無儲位模式：未上架庫存直接可配貨，不強制上架
    # 印表機
    "report_printer": "",              # 報表印表機（A4 單據）
    "label_printer": "",               # 熱感貼紙印表機
    "report_paper": "A4",
    "label_paper": "100x100",          # 毫米，寬x高，例如 100x100（10x10cm）
    "label_engine": "HTML",            # HTML（瀏覽器列印）或 TSPL（直接吐紙）
    # 顯示
    "ui_scale": "1.3",                 # 介面縮放；小螢幕筆電可調 1.0 或 1.15
    "invert_scroll": "0",              # 滾輪方向反轉（不同平台/滑鼠慣例不同，顛倒時開啟）
}

UI_SCALE_CHOICES = (
    ("1.0", "100%（小螢幕筆電）"),
    ("1.15", "115%（13-14 吋筆電）"),
    ("1.3", "130%（桌機大螢幕，預設）"),
)

LABEL_PAPER_CHOICES = ("100x100", "100x150", "50x30", "40x30")
REPORT_PAPER_CHOICES = ("A4", "Letter", "B5")

# 單號前綴（供跨頁自動帶入時判別單據類型）
ORDER_NO_PREFIXES = {
    "RO": "receiving",
    "SO": "shipping",
    "RT": "return",
    "BR": "buyer_return",
    "CC": "cycle_count",
}

# V6.9：字體整體放大約 30%（原字級 x1.3），介面元件與 Treeview 皆套用同一基準字級。
FONT_FAMILY = "Microsoft JhengHei"
FONT_SCALE = 1.3


def scaled_font(size):
    """依 FONT_SCALE 放大字級，四捨五入為整數。"""
    return max(1, round(size * FONT_SCALE))


# 報廢區防呆天數。商品移入報廢區後，需經過此天數才會被系統自動刪除庫存並扣帳，
# 讓使用者有充足時間發現誤操作並「取消報廢」移回原儲位。
SCRAP_HOLD_DAYS = 3
SCRAP_ZONE_SHELF = "報廢區"
QC_ZONE_SHELF = "品檢區"
STAGING_SHELF = "未上架"
# Treeview／Labelframe 依 bootstyle 主題色統一配色，讓表格分隔線與所在頁面框線同色。
TABLE_BOOTSTYLES = ("primary", "secondary", "success", "info", "warning", "danger")
