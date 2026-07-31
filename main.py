"""Desktop entry point. It composes isolated UI modules without cross-imports."""
from utils.constants import tb
from ui.main_ui import MainUIMixin
from ui.product_ui import ProductUIMixin
from ui.inventory_ui import InventoryUIMixin
from ui.receiving_ui import ReceivingUIMixin
from ui.putaway_ui import PutawayUIMixin
from ui.shipment_order_ui import ShipmentOrderUIMixin
from ui.shipping_ui import ShippingUIMixin
from ui.stocktake_ui import StocktakeUIMixin
from ui.cyclecount_ui import CycleCountUIMixin
from ui.location_ui import LocationUIMixin
from ui.branch_ui import BranchUIMixin
from ui.return_ui import ReturnUIMixin
from ui.consumable_ui import ConsumableUIMixin
from ui.reports_ui import ReportsUIMixin
from ui.account_ui import AccountUIMixin
from ui.settings_ui import SettingsUIMixin
from ui.log_ui import LogUIMixin

class WMSApp(MainUIMixin, ProductUIMixin, InventoryUIMixin, ReceivingUIMixin,
             PutawayUIMixin, ShipmentOrderUIMixin, ShippingUIMixin,
             StocktakeUIMixin, CycleCountUIMixin, LocationUIMixin, BranchUIMixin,
             ReturnUIMixin, ConsumableUIMixin, ReportsUIMixin, AccountUIMixin,
             SettingsUIMixin, LogUIMixin):
    """Composed desktop application; UI 一律透過 services 層存取資料。"""

if __name__ == "__main__":
    app = tb.Window(themename="flatly")
    WMSApp(app)
    app.mainloop()
