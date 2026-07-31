"""Typed transport model for future API use; SQLite schema is unchanged."""
from dataclasses import dataclass

@dataclass
class Location:
    shelf_code: str
    status: str
