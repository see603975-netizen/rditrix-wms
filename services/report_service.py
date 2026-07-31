"""ReportService：統計報表。"""
from .base import BaseService


class ReportService(BaseService):
    _methods = (
        "shipping_report",
        "loss_report",
    )
