# Rditrix WMS Lite V6.9（模組化完成版）

## 執行

```bash
pip install ttkbootstrap
python main.py
```

預設管理員帳號：`PO001` / `123123`（**首次登入後請至「帳號管理」建立自己的帳號並重設密碼**）。

## 架構

```
main.py                  # 桌面進入點：組合各 UI mixin
api/server.py            # REST API 預留骨架（pip install fastapi uvicorn 後：uvicorn api.server:app）
ui/                      # 純畫面層：只透過 self.svc.<領域>.<方法> 存取資料，不含 SQL
services/                # 服務層：UI 與 API 的唯一入口；各檔案的 _methods 白名單即對外介面
database/                # 資料層：core.py（連線/schema/種子）＋ 各領域 *_db.py mixin，組成 DBManager
utils/                   # 常數、驗證工具、印表機（TSPL/RAW）支援
models/                  # 傳輸用 dataclass（供未來 API 擴充）
printouts/               # 列印輸出的 HTML（原 ui/wms_printouts）
legacy_v6_8_original.py  # V6.8 原始單檔備份，僅供追溯，未被引用
```

依賴方向固定為 `ui → services → database`；新增功能時：資料表與交易寫在 `database/*_db.py`，
在對應 service 的 `_methods` 白名單公開，UI 或 API 再呼叫。

## 角色權限

| 功能 | 現場作業員 | 倉庫主管 | 系統管理員 |
|---|---|---|---|
| 掃描驗收／上架／出貨掃描／動態盤點輸入／耗材報銷 | ✔ | ✔ | ✔ |
| 建立與取消進出貨單、儲位管理、分店管理、報廢、儲位調撥、動態盤點平帳 | ✘ | ✔ | ✔ |
| 退貨審核（品檢判定/寄回）、盲盤強制平帳、帳號管理、防呆/系統設定 | ✘ | ✘ | ✔ |

登入安全：`users`／`login_logs` 資料表，密碼 PBKDF2 雜湊；同帳號連續失敗 5 次自動鎖定 15 分鐘並記錄警告。

## V6.9 新增功能

- **動態盤點（Cycle Count）**：自動撈取當日/當週/當月有異動的儲位、A4 或熱感紙列印盤點單、
  掃描輸入實盤、「一鍵全部正常」、異常品輸入差異後由主管完成平帳。
- **防呆設定頁（管理員）**：進貨效期門檻（預設今日+180天）、商品最大進貨量限制、
  一鍵完成驗收入庫、一鍵完成出貨驗貨（含自訂完成條碼）、無儲位模式。
- **耗材報銷頁**：點選耗材、輸入數量一鍵報銷（立即扣帳，不進三天保護期）。
- **系統設定頁**：報表印表機與熱感貼紙印表機分開指定、紙張尺寸（A4／100x100 等）、
  TSPL 直接吐紙模式（TSC 系列）與測試列印。
- **商業防呆**：已登記到貨/完成的進貨單禁止直接取消（改走退貨/調帳）；SKU 僅限英數；
  買家退貨與報廢狀態碼全面顯示繁體中文。
- **UI/UX**：點擊表格單號/條碼自動複製並提示、跨頁自動帶入單號/條碼、右鍵選單放大、
  內容區 Canvas+捲軸（小螢幕/高縮放不裁切）。

## 資料庫

SQLite（`wms_system_v3.db`），啟動時自動升級 schema（CREATE IF NOT EXISTS / ALTER ADD COLUMN），
既有資料不受影響。新增資料表：`users`、`login_logs`、`login_lockouts`、`app_settings`、
`cycle_count_sessions`、`cycle_count_items`。
