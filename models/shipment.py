"""Typed transport model for future API use; SQLite schema is unchanged."""
from dataclasses import dataclass

@dataclass
class Shipment:
    order_no: str
    status: str
