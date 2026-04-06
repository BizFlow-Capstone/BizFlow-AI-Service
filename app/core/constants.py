"""
core/constants.py

Shared string constants that mirror values used in the BizFlow .NET backend.
Centralising them here prevents typos and makes future changes a single-file edit.
"""


class OrderStatus:
    """Mirrors BizFlow.Domain.Enums.OrderStatus in the .NET service."""
    PENDING   = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
