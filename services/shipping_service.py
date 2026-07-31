"""ShippingService：出貨單、FEFO 配貨與包裝出貨。"""
from .base import BaseService


class ShippingService(BaseService):
    _methods = (
        "generate_order_no",
        "available_batches_for_order",
        "available_qty_for_order",
        "create_shipping_order",
        "order_header",
        "order_lines",
        "all_orders",
        "search_shipping_orders",
        "start_packing",
        "scan_order_item",
        "order_fully_scanned",
        "quick_pack_order",
        "reset_packing_scan_progress",
        "complete_packing",
        "cancel_order",
        "remove_shipping_order_item",
        "mark_order_printed",
        "mark_label_printed",
    )
