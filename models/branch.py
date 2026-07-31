"""Typed transport model for future API use; SQLite schema is unchanged."""
from dataclasses import dataclass

@dataclass
class Branch:
    branch_id: int | None
    name: str
