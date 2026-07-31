"""服務層：UI 與 API 的唯一入口，包住資料層並集中業務規則。

用法：
    from database import DBManager
    from services import Services
    svc = Services(DBManager())
    svc.product.all_products()
"""
from .auth_service import AuthService
from .product_service import ProductService
from .branch_service import BranchService
from .location_service import LocationService
from .inventory_service import InventoryService
from .receiving_service import ReceivingService
from .shipping_service import ShippingService
from .return_service import ReturnService
from .stocktake_service import StocktakeService
from .consumable_service import ConsumableService
from .settings_service import SettingsService
from .log_service import LogService
from .report_service import ReportService


class Services:
    """所有領域服務的容器；桌面 UI 與 API 共用同一組實例。"""

    def __init__(self, database):
        self.database = database
        self.auth = AuthService(database)
        self.product = ProductService(database)
        self.branch = BranchService(database)
        self.location = LocationService(database)
        self.inventory = InventoryService(database)
        self.receiving = ReceivingService(database)
        self.shipping = ShippingService(database)
        self.returns = ReturnService(database)
        self.stocktake = StocktakeService(database)
        self.consumable = ConsumableService(database)
        self.settings = SettingsService(database)
        self.log = LogService(database)
        self.report = ReportService(database)

    def close(self):
        self.database.close()


__all__ = ["Services"]
