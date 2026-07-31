"""ConsumableService：耗材快速報銷。"""
from .base import BaseService


class ConsumableService(BaseService):
    _methods = (
        "consumable_products",
        "writeoff_consumable",
        "recent_consumable_writeoffs",
    )
