"""DBManager：由各領域資料模組組裝而成的資料存取層。

每個 mixin 各自負責一個領域的資料表與交易；CoreDB 負責連線、schema 與種子資料。
UI 一律透過 services 層存取，不直接操作 cursor / conn。
"""
from database.core import CoreDB
from database.settings_db import SettingsDBMixin
from database.log_db import LogDBMixin
from database.auth_db import AuthDBMixin
from database.product_db import ProductDBMixin
from database.location_db import LocationDBMixin
from database.inventory_db import InventoryDBMixin
from database.receiving_db import ReceivingDBMixin
from database.shipping_db import ShippingDBMixin
from database.branch_db import BranchDBMixin
from database.return_db import ReturnDBMixin
from database.stocktake_db import StocktakeDBMixin
from database.consumable_db import ConsumableDBMixin
from database.report_db import ReportDBMixin


class DBManager(
    SettingsDBMixin,
    LogDBMixin,
    AuthDBMixin,
    ProductDBMixin,
    LocationDBMixin,
    InventoryDBMixin,
    ReceivingDBMixin,
    ShippingDBMixin,
    BranchDBMixin,
    ReturnDBMixin,
    StocktakeDBMixin,
    ConsumableDBMixin,
    ReportDBMixin,
    CoreDB,
):
    """SQLite 資料存取與出貨配貨邏輯（各領域模組的組合體）。"""
