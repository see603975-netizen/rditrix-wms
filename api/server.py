"""REST API 骨架（預留擴充用，桌面版不需要啟動）。

啟動方式：
    pip install fastapi uvicorn
    uvicorn api.server:app --reload --port 8000

- 與桌面 UI 共用同一個 services 層與 SQLite 資料庫，商業規則完全一致。
- 已提供常用唯讀端點與登入驗證範例；寫入端點可依需求比照擴充，
  服務層方法（services/*.py 的 _methods 白名單）就是可公開的 API 介面清單。
"""
from database import DBManager
from services import Services

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError as error:  # pragma: no cover - 桌面環境未安裝 fastapi 屬正常
    raise ImportError(
        "API 模式需要 fastapi 與 uvicorn：pip install fastapi uvicorn"
    ) from error


def _rows(rows):
    return [dict(row) for row in rows]


class LoginPayload(BaseModel):
    username: str
    password: str


def create_app():
    app = FastAPI(title="Rditrix WMS API", version="6.9")
    svc = Services(DBManager())

    @app.post("/auth/login")
    def login(payload: LoginPayload):
        try:
            return svc.auth.login(payload.username, payload.password)
        except ValueError as error:
            raise HTTPException(status_code=401, detail=str(error))

    @app.get("/products")
    def products():
        return _rows(svc.product.all_products())

    @app.get("/inventory")
    def inventory(shelf_code: str = "", keyword: str = ""):
        return _rows(svc.inventory.inventory_report(shelf_code, keyword))

    @app.get("/dashboard")
    def dashboard():
        metrics = svc.inventory.dashboard_metrics()
        return {
            "total_available": metrics["total_available"],
            "low_stock": _rows(metrics["low_stock_rows"]),
            "near_expiry": _rows(metrics["near_expiry_rows"]),
            "pending_orders": metrics["pending_order_count"],
        }

    @app.get("/shipping-orders")
    def shipping_orders():
        return _rows(svc.shipping.all_orders())

    @app.get("/receiving-orders")
    def receiving_orders(order_no: str = ""):
        return _rows(svc.receiving.all_receiving_orders(order_no))

    @app.get("/cycle-counts")
    def cycle_counts():
        return _rows(svc.stocktake.cycle_count_sessions())

    return app


app = create_app()
