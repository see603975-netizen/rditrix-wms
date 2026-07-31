"""ReceivingService：進貨單與驗收流程。"""
from .base import BaseService


class ReceivingService(BaseService):
    _methods = (
        "generate_receiving_order_no",
        "create_receiving_order",
        "receiving_order_header",
        "receiving_order_lines",
        "all_receiving_orders",
        "missing_products_for_receiving_order",
        "set_receiving_order_status",
        "start_receiving",
        "validate_receiving_expiry",
        "scan_receiving_item",
        "quick_receive_order",
        "reset_receiving_scan_progress",
        "complete_receiving",
        "cancel_receiving_order",
        "remove_receiving_order_item",
        "mark_receiving_order_printed",
    )
