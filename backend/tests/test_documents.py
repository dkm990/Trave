import pytest

from app.services.document_service import (
    DocumentService,
    SENSITIVE_DOC_TYPES,
)


@pytest.mark.parametrize("t", list(SENSITIVE_DOC_TYPES))
def test_sensitive_types_detected(t):
    assert DocumentService.is_sensitive(t) is True


@pytest.mark.parametrize("t", ["ticket", "hotel_booking", "insurance", "voucher", "other"])
def test_allowed_types_not_sensitive(t):
    assert DocumentService.is_sensitive(t) is False


def test_normalize_unknown_to_other():
    assert DocumentService.normalize_type("foobar") == "other"
    assert DocumentService.normalize_type("TICKET") == "ticket"
