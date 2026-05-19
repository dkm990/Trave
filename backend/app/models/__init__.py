from app.models.user import User
from app.models.trip import Trip, TripMember
from app.models.expense import Expense, ExpenseShare, Settlement
from app.models.document import TravelDocument
from app.models.currency import ExchangeRateCache
from app.models.group_memory import GroupMessage, GroupMemory

# Объединённый импорт, чтобы Alembic / create_all видели все модели
all_models = (
    User,
    Trip,
    TripMember,
    Expense,
    ExpenseShare,
    Settlement,
    TravelDocument,
    ExchangeRateCache,
    GroupMessage,
    GroupMemory,
)

__all__ = [
    "User",
    "Trip",
    "TripMember",
    "Expense",
    "ExpenseShare",
    "Settlement",
    "TravelDocument",
    "ExchangeRateCache",
    "GroupMessage",
    "GroupMemory",
    "all_models",
]
