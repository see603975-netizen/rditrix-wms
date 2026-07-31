"""InventoryService：庫存總覽、報表、上架與調撥。"""
from .base import BaseService


class InventoryService(BaseService):
    _methods = (
        "inventory_qty",
        "dashboard_metrics",
        "inventory_report",
        "staging_batches",
        "putaway",
        "transfer_stock",
        "adjust_inventory_count",
        "sidebar_todo_summary",
    )
