"""Typed transport model for future API use; SQLite schema is unchanged."""
from dataclasses import dataclass

@dataclass
class Inventory:
    barcode: str
    shelf_code: str
    quantity: int
