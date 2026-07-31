"""BaseService：領域服務的共用基底。

每個服務以 `_methods` 白名單宣告對 UI／API 公開的資料層方法，
額外的業務組合邏輯以一般方法實作。白名單同時就是 API 的介面文件。
"""


class BaseService:
    _methods = ()

    def __init__(self, database):
        self.database = database

    def __getattr__(self, name):
        if name in type(self)._methods:
            return getattr(self.database, name)
        raise AttributeError(
            f"{type(self).__name__} 未公開方法 {name}；請確認服務層白名單"
        )

    def __dir__(self):
        return sorted(set(list(super().__dir__()) + list(type(self)._methods)))
