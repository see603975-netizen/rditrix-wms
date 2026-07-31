"""ReturnService：供應商退貨、買家退貨品檢與報廢暫存。"""
from .base import BaseService


class ReturnService(BaseService):
    _methods = (
        "create_return_order",
        "return_order_header",
        "all_return_orders",
        "set_return_evidence",
        "mark_return_shipped",
        "move_to_scrap_hold",
        "cancel_scrap_hold",
        "process_due_scrap_holds",
        "all_scrap_holds",
        "create_buyer_return_to_qc",
        "all_buyer_returns",
        "restock_buyer_return",
        "scrap_buyer_return",
    )
