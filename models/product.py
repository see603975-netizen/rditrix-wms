"""Typed transport model for future API use; SQLite schema is unchanged."""
from dataclasses import dataclass

@dataclass
class Product:
    barcode: str
    sku: str
    name: str
