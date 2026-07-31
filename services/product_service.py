"""ProductService：商品主檔。"""
from .base import BaseService


class ProductService(BaseService):
    _methods = (
        "product_by_barcode",
        "save_product",
        "all_products",
        "product_stock_overview",
        "consumable_products",
        "bulk_import_products",
    )
