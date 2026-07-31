"""BranchService：分店主檔。"""
from .base import BaseService


class BranchService(BaseService):
    _methods = (
        "active_branches",
        "branch_by_id",
        "branch_by_code",
        "save_branch",
    )
