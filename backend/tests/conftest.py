from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Изолируем тестовую БД: ставим ДО любого импорта app.config / app.database,
# и используем явный override (а не setdefault), чтобы случайно подхваченный
# DATABASE_URL из окружения не мешал тестам.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DEV_ALLOW_INSECURE_AUTH"] = "1"
os.environ["AI_PROVIDER"] = "rule_based"


import pytest


@pytest.fixture(autouse=True)
def _reset_app_singletons():
    """Each test gets a fresh database engine, session factory, and settings.

    Без этого `app.database._engine` и `app.config.get_settings` (lru_cache)
    переживают тесты, и in-memory SQLite одного теста "видит" строки,
    созданные предыдущим тестом, что ломает test_currency_conversion.
    """
    yield  # body of test runs first; reset happens AFTER each test
    try:
        from app import database as _db
        _db._engine = None  # noqa: SLF001
        _db._session_factory = None  # noqa: SLF001
    except Exception:
        pass
    try:
        from app.config import get_settings as _gs
        _gs.cache_clear()
    except Exception:
        pass
    try:
        from app.ai.factory import get_ai_provider as _gp
        _gp.cache_clear()
    except Exception:
        pass
