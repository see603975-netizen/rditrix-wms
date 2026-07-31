"""LocationService：儲位管理。"""
from .base import BaseService


class LocationService(BaseService):
    _methods = (
        "shelf_by_code",
        "search_shelves",
        "shelf_reference_summary",
        "create_shelf",
        "rename_shelf",
        "set_shelf_status",
        "active_shelf_codes",
        "all_shelf_codes",
    )
