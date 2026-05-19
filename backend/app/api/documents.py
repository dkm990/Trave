from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models.document import TravelDocument
from app.models.user import User
from app.schemas.common import DocumentMetadataRequest, DocumentOut
from app.services.document_service import (
    DocumentInput,
    DocumentService,
    SensitiveDocumentRefused,
)
from app.services.trip_service import TripService

trip_router = APIRouter(prefix="/api/trips", tags=["documents"])
doc_router = APIRouter(prefix="/api/documents", tags=["document-download"])


@trip_router.get("/{trip_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    trip_id: int,
    q: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    trip_svc = TripService(session)
    if not await trip_svc.get_trip(trip_id):
        raise HTTPException(404, "Trip not found")
    svc = DocumentService(session)
    return await svc.list_for_trip(trip_id, viewer_user_id=user.id, query=q, doc_type=doc_type)


@trip_router.post("/{trip_id}/documents/metadata", response_model=DocumentOut)
async def save_document_metadata(
    trip_id: int,
    payload: DocumentMetadataRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    trip_svc = TripService(session)
    if not await trip_svc.get_trip(trip_id):
        raise HTTPException(404, "Trip not found")
    svc = DocumentService(session)
    try:
        doc = await svc.save(
            DocumentInput(
                trip_id=trip_id,
                owner_user_id=payload.owner_user_id,
                title=payload.title,
                doc_type=payload.doc_type,
                telegram_file_id=payload.telegram_file_id,
                telegram_file_unique_id=payload.telegram_file_unique_id,
                file_name=payload.file_name,
                mime_type=payload.mime_type,
                file_size=payload.file_size,
                visibility=payload.visibility,
                note=payload.note,
            )
        )
    except SensitiveDocumentRefused as exc:
        raise HTTPException(400, str(exc)) from exc
    return doc


@doc_router.get("/{doc_id}/download")
async def download_document(
    doc_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    """Proxies a Telegram file through our API so the Mini App can download/view it.

    IMPORTANT: httpx.AsyncClient is created WITHOUT ``async with`` because
    the StreamingResponse runs the async generator AFTER this handler returns.
    An ``async with`` context manager would close the client before streaming begins,
    resulting in "Cannot send a request, as the client has been closed."
    The client is closed by the generator itself when streaming finishes.
    """
    doc = await session.get(TravelDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    if doc.visibility != "shared" and doc.owner_user_id != user.id:
        raise HTTPException(403, "Access denied")

    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise HTTPException(500, "Bot token not configured")

    # Create client outside of context manager — StreamingResponse needs it alive
    client = httpx.AsyncClient(timeout=30)

    # 1. Get file_path from Telegram
    tg_resp = await client.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": doc.telegram_file_id},
    )
    tg_data = tg_resp.json()
    if not tg_data.get("ok"):
        await client.aclose()
        raise HTTPException(502, f"Telegram getFile failed: {tg_data.get('description', 'unknown')}")

    file_path = tg_data["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    mime = doc.mime_type or "application/octet-stream"
    filename = doc.file_name or f"document_{doc.id}"

    async def stream_file():
        try:
            async with client.stream("GET", file_url) as resp:
                async for chunk in resp.aiter_bytes(65536):
                    yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(
        stream_file(),
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=86400",
        },
    )
