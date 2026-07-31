"""Typed transport model for future API use; SQLite schema is unchanged."""
from dataclasses import dataclass


@dataclass
class User:
    username: str
    display_name: str
    role: str
