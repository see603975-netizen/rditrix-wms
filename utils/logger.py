"""Logging protocol used by services without importing UI modules."""

def log_operation(database, *args, **kwargs):
    return database.log_operation(*args, **kwargs)

def log_transaction(database, *args, **kwargs):
    return database.log_transaction(*args, **kwargs)
