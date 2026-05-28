from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TripCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    default_currency: str = Field(default="RUB", min_length=3, max_length=8)


class TripUpdateRequest(BaseModel):
    title: Optional[str] = None
    local_currency: Optional[str] = None


class TripMemberOut(ORMModel):
    id: int
    user_id: int
    display_name: Optional[str]
    role: str


class TripOut(ORMModel):
    id: int
    title: str
    default_currency: str
    local_currency: Optional[str] = None
    telegram_chat_id: Optional[int]
    created_at: datetime
    members: list[TripMemberOut] = []


class ExpenseCreateRequest(BaseModel):
    payer_user_id: int
    title: str
    amount: Decimal
    currency: str = Field(min_length=3, max_length=8)
    participant_user_ids: list[int]
    category: Optional[str] = None
    note: Optional[str] = None
    # Split mode: "equal" (default) | "by_amount" | "by_percent"
    split_mode: str = "equal"
    # Custom shares: {user_id: amount_or_percent}. Required when split_mode != "equal".
    custom_shares: Optional[dict[int, Decimal]] = None


class ExpenseUpdateRequest(BaseModel):
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    category: Optional[str] = None
    payer_user_id: Optional[int] = None
    participant_user_ids: Optional[list[int]] = None
    note: Optional[str] = None
    split_mode: Optional[str] = None
    custom_shares: Optional[dict[int, Decimal]] = None


class ExpenseShareOut(ORMModel):
    user_id: int
    share_amount_base: Decimal


class ExpenseOut(ORMModel):
    id: int
    trip_id: int
    payer_user_id: int
    title: str
    category: Optional[str]
    amount_original: Decimal
    currency_original: str
    amount_base: Decimal
    base_currency: str
    exchange_rate: Decimal
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    edited_count: int = 0
    note: Optional[str] = None
    source: Optional[str] = None
    shares: list[ExpenseShareOut] = []


class BalanceOut(BaseModel):
    user_id: int
    paid: Decimal
    owes: Decimal
    net: Decimal


class DebtOut(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: Decimal


class BalancesResponse(BaseModel):
    trip_currency: str
    base_currency: str
    balances: list[BalanceOut]
    transfers: list[DebtOut]


class PaymentCreateRequest(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: Decimal
    currency: str = Field(min_length=3, max_length=8)
    note: Optional[str] = None


class PaymentOut(ORMModel):
    id: int
    trip_id: int
    from_user_id: int
    to_user_id: int
    amount_original: Decimal
    currency_original: str
    amount_base: Decimal
    base_currency: str
    exchange_rate: Decimal
    status: str
    note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None


class CurrencyRateOut(BaseModel):
    base: str
    quote: str
    rate: Decimal
    rate_date: date
    provider: str
    fetched_at: datetime
    from_cache: bool


class CurrencyConvertOut(BaseModel):
    amount: Decimal
    base: str
    quote: str
    converted: Decimal
    rate: CurrencyRateOut


class DocumentOut(ORMModel):
    id: int
    trip_id: int
    owner_user_id: int
    visibility: str
    doc_type: str
    title: str
    telegram_file_id: str
    file_name: Optional[str]
    mime_type: Optional[str]
    file_size: Optional[int]
    note: Optional[str]
    created_at: datetime


class DocumentMetadataRequest(BaseModel):
    owner_user_id: int
    title: str
    doc_type: str
    telegram_file_id: str
    telegram_file_unique_id: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    visibility: str = "private"
    note: Optional[str] = None


class AIIntentRequest(BaseModel):
    text: str
    trip_id: Optional[int] = None


class AIIntentResponse(BaseModel):
    action: str
    confidence: float
    payload: dict
    needs_confirmation: bool
    provider: str


# ── Flights ──

class FlightCreateRequest(BaseModel):
    """Add a flight to a trip.

    MVP flow: just provide flight_number + flight_date; the provider fills the rest.
    Full flow: provide all fields directly.
    """
    flight_number: str = Field(min_length=2, max_length=16)
    flight_date: Optional[date] = None  # for MVP provider lookup
    # These become optional for MVP — filled by provider
    airline_code: Optional[str] = Field(default=None, min_length=2, max_length=8)
    airline_name: Optional[str] = None
    departure_city: Optional[str] = Field(default=None, min_length=1, max_length=64)
    arrival_city: Optional[str] = Field(default=None, min_length=1, max_length=64)
    departure_airport: Optional[str] = Field(default=None, min_length=3, max_length=8)
    arrival_airport: Optional[str] = Field(default=None, min_length=3, max_length=8)
    departure_terminal: Optional[str] = None
    arrival_terminal: Optional[str] = None
    scheduled_departure_at: Optional[datetime] = None
    scheduled_arrival_at: Optional[datetime] = None


class FlightOut(ORMModel):
    id: int
    trip_id: int
    trip_title: str
    flight_number: str
    airline_code: str
    airline_name: Optional[str] = None
    departure_city: str
    arrival_city: str
    departure_airport: str
    arrival_airport: str
    departure_terminal: Optional[str] = None
    arrival_terminal: Optional[str] = None
    scheduled_departure_at: datetime
    actual_departure_at: Optional[datetime] = None
    estimated_departure_at: Optional[datetime] = None
    scheduled_arrival_at: datetime
    actual_arrival_at: Optional[datetime] = None
    estimated_arrival_at: Optional[datetime] = None
    status: str
    check_in_counter: Optional[str] = None
    gate: Optional[str] = None
    baggage_belt: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
