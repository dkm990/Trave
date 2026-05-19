from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import TravelDocument


SENSITIVE_DOC_TYPES = {"passport", "visa", "id", "id_card", "driver_license"}
ALLOWED_DOC_TYPES = {
    "ticket",
    "hotel_booking",
    "insurance",
    "itinerary",
    "voucher",
    "other",
}


class SensitiveDocumentRefused(Exception):
    """Попытка сохранить чувствительный документ — запрещено в MVP."""


@dataclass
class DocumentInput:
    trip_id: int
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


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def is_sensitive(doc_type: str) -> bool:
        return doc_type.lower().strip() in SENSITIVE_DOC_TYPES

    @staticmethod
    def normalize_type(doc_type: str) -> str:
        t = doc_type.lower().strip()
        return t if t in ALLOWED_DOC_TYPES else "other"

    async def save(self, payload: DocumentInput) -> TravelDocument:
        if self.is_sensitive(payload.doc_type):
            raise SensitiveDocumentRefused(
                "В MVP мы не храним паспорта, визы и документы с чувствительными данными."
            )
        doc = TravelDocument(
            trip_id=payload.trip_id,
            owner_user_id=payload.owner_user_id,
            visibility=payload.visibility,
            doc_type=self.normalize_type(payload.doc_type),
            title=payload.title[:200],
            telegram_file_id=payload.telegram_file_id,
            telegram_file_unique_id=payload.telegram_file_unique_id,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            file_size=payload.file_size,
            note=payload.note,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def list_for_trip(
        self,
        trip_id: int,
        viewer_user_id: int,
        query: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> list[TravelDocument]:
        stmt = select(TravelDocument).where(
            TravelDocument.trip_id == trip_id,
            or_(
                TravelDocument.visibility == "shared",
                TravelDocument.owner_user_id == viewer_user_id,
            ),
        )
        if doc_type:
            stmt = stmt.where(TravelDocument.doc_type == self.normalize_type(doc_type))
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    TravelDocument.title.ilike(like),
                    TravelDocument.note.ilike(like),
                    TravelDocument.file_name.ilike(like),
                    TravelDocument.doc_type.ilike(like),
                )
            )
        stmt = stmt.order_by(TravelDocument.created_at.desc())
        return list((await self.session.execute(stmt)).scalars())

    async def get(self, doc_id: int) -> Optional[TravelDocument]:
        return (
            await self.session.execute(
                select(TravelDocument).where(TravelDocument.id == doc_id)
            )
        ).scalar_one_or_none()
