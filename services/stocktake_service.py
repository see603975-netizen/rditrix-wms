"""StocktakeService：動態盤點（Cycle Count）。"""
from .base import BaseService


class StocktakeService(BaseService):
    _methods = (
        "create_cycle_count_session",
        "cycle_count_sessions",
        "cycle_count_session",
        "cycle_count_items",
        "record_cycle_count",
        "confirm_cycle_count_all_normal",
        "complete_cycle_count",
        "mark_cycle_count_printed",
    )
