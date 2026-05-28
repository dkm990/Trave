from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.ai.base import AIProvider, Intent


CURRENCY_ALIASES = {
    "руб": "RUB", "рубл": "RUB", "rub": "RUB", "р": "RUB", "₽": "RUB",
    "usd": "USD", "доллар": "USD", "долл": "USD", "бакс": "USD", "$": "USD",
    "eur": "EUR", "евро": "EUR", "€": "EUR",
    "gel": "GEL", "лари": "GEL",
    "thb": "THB", "бат": "THB",
    "vnd": "VND", "донг": "VND", "₫": "VND",
    "kzt": "KZT", "тенге": "KZT",
    "try": "TRY", "лир": "TRY", "₺": "TRY",
    "amd": "AMD", "драм": "AMD",
    "uah": "UAH", "грив": "UAH",
    "byn": "BYN",
    "cny": "CNY", "юан": "CNY", "¥": "CNY",
    "jpy": "JPY", "иен": "JPY",
    "gbp": "GBP", "фунт": "GBP", "£": "GBP",
}

PAID_VERBS_RU = (
    "оплатил", "оплатила", "заплатил", "заплатила",
    "купил", "купила", "потратил", "потратила",
)
PAID_VERBS_EN = ("paid", "spent", "bought")
ALL_KEYWORDS_RU = (
    "за всех", "на всех", "за нас", "на нас", "всех нас",
    "поровну", "пополам", "делим",
)

CURRENCY_REGEX = re.compile(
    r"(\d{1,3}(?:[ .,\u00a0]\d{3})*(?:[.,]\d+)?(?:\s*[kkкКmMмМ]{1,2})?|"
    r"\d+(?:[.,]\d+)?(?:\s*[kkкКmMмМ]{1,2})?)\s*"
    r"(rub|usd|eur|gel|thb|vnd|kzt|try|amd|uah|byn|cny|jpy|gbp|"
    r"руб(?:лей|ля|ль)?|р|долларов?|долл|бакс(?:ов|а|у)?|евро|лари|"
    r"бат(?:ов|а)?|донг(?:ов|а)?|тенге|(?:турец\w*\s+)?лир(?:а|ы)?|драм(?:ов|а)?|"
    r"гривен|юаней|иен|фунтов?|₽|\$|€|¥|£|₫|₺)",
    re.IGNORECASE,
)


KNOWN_CURRENCY_CODES = frozenset(
    {
        "USD", "EUR", "RUB", "GBP", "JPY", "CNY", "KRW", "TRY",
        "KZT", "AMD", "BYN", "UAH", "IDR", "VND", "GEL", "THB",
        "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON",
        "BGN", "ILS", "INR", "MXN", "BRL", "ZAR", "NZD", "SGD",
        "HKD", "PHP", "MYR", "ISK", "AUD", "CAD",
    }
)


def _normalize_currency_typos(text: str) -> str:
    pattern = re.compile(r"\b([A-Za-z]{2})\s+([A-Za-z])\b")

    def repl(m: re.Match[str]) -> str:
        joined = (m.group(1) + m.group(2)).upper()
        if joined in KNOWN_CURRENCY_CODES:
            return joined
        return m.group(0)

    return pattern.sub(repl, text)


def _detect_currency(token: str) -> str | None:
    t = token.strip().lower().replace(".", "")
    if t in {"₽", "$", "€", "¥", "£", "₫", "₺"}:
        return CURRENCY_ALIASES.get(t)
    for prefix, code in CURRENCY_ALIASES.items():
        if prefix.isalpha() and t.startswith(prefix):
            return code
    for prefix, code in CURRENCY_ALIASES.items():
        if prefix.isalpha() and len(prefix) >= 3 and prefix in t:
            return code
    if len(t) == 3 and t.isalpha():
        return t.upper()
    return None


def _parse_amount(s: str) -> Decimal | None:
    raw = s.strip().lower().replace("\u00a0", " ")
    multiplier = Decimal("1")
    m = re.fullmatch(r"\s*([\d.,\s]+?)\s*([kkкmMм]{1,2})\s*", raw, re.IGNORECASE)
    if m:
        num_part = m.group(1)
        suffix = m.group(2).lower().replace("к", "k").replace("м", "m")
        if suffix == "kk":
            multiplier = Decimal("1000000")
        elif suffix == "k":
            multiplier = Decimal("1000")
        elif suffix == "m":
            multiplier = Decimal("1000000")
        elif suffix == "mm":
            multiplier = Decimal("1000000000")
    else:
        num_part = raw

    num_part = num_part.replace(" ", "")
    if "," in num_part and "." in num_part:
        if num_part.rfind(",") > num_part.rfind("."):
            num_part = num_part.replace(".", "").replace(",", ".")
        else:
            num_part = num_part.replace(",", "")
    elif "," in num_part:
        comma_pos = num_part.rfind(",")
        decimals = len(num_part) - comma_pos - 1
        if decimals == 3 and multiplier == Decimal("1"):
            num_part = num_part.replace(",", "")
        else:
            num_part = num_part.replace(",", ".")
    try:
        value = Decimal(num_part) * multiplier
        if multiplier != Decimal("1"):
            return value.quantize(Decimal("1"))
        return value
    except InvalidOperation:
        return None


def _detect_split_count(text: str) -> int | None:
    words = {"двоих": 2, "троих": 3, "четверых": 4, "пятерых": 5,
             "шестерых": 6, "семерых": 7}
    m = re.search(
        r"(?:на|за)\s+(двоих|троих|четверых|пятерых|шестерых|семерых)", text
    )
    if m:
        return words.get(m.group(1))
    m = re.search(r"(?:на|за)\s+(\d+)\s*(?:чел|человек|людей)?", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _looks_like_split_all(text: str) -> bool:
    return any(k in text for k in ALL_KEYWORDS_RU) or "for all" in text or "split" in text


def _looks_like_paid(text: str) -> bool:
    return (
        any(v in text for v in PAID_VERBS_RU)
        or any(v in text for v in PAID_VERBS_EN)
    )


def _detect_participants(original: str) -> list[str]:
    names: list[str] = []
    for m in re.finditer(
        r"\bс\s+([A-ZА-ЯЁ][a-zа-яёA-ZА-ЯЁ]+(?:\s+и\s+[A-ZА-ЯЁ][a-zа-яёA-ZА-ЯЁ]+)*)",
        original,
    ):
        chunk = m.group(1)
        for raw in re.split(r"\s+и\s+|\s*,\s*", chunk):
            raw = raw.strip()
            if raw and raw not in names:
                names.append(raw)
    return names


def _detect_participants(original: str) -> list[str]:
    """Extract mentioned participants from patterns like 'с Зоей', 'with Zoe'."""
    names: list[str] = []
    for m in re.finditer(
        r"\b(?:с|with)\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]*(?:\s*(?:и|and|,)\s*[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]*)*)",
        original,
        re.IGNORECASE,
    ):
        chunk = m.group(1)
        for raw in re.split(r"\s*(?:и|and|,)\s*", chunk, flags=re.IGNORECASE):
            candidate = raw.strip()
            if candidate and candidate not in names:
                names.append(candidate)
    return names


def _detect_participants(original: str) -> list[str]:
    """Final participant parser used by expense intent extraction."""
    names: list[str] = []
    for m in re.finditer(
        r"\b(?:с|with)\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]*(?:(?:\s+и\s+|\s+and\s+|\s*,\s*)[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]*)*)",
        original,
        re.IGNORECASE,
    ):
        chunk = m.group(1)
        for raw in re.split(r"(?:\s+и\s+|\s+and\s+|\s*,\s*)", chunk, flags=re.IGNORECASE):
            candidate = raw.strip()
            if candidate and candidate not in names:
                names.append(candidate)
    return names


def _detect_uneven_split(text: str) -> tuple[str, list[dict] | None]:
    name_amount_pairs = re.findall(
        r"(?:(\d+(?:[.,]\d+)?)\s*(?:с\s+)?(я|меня|мне|[A-ZА-ЯЁ][a-zа-яё]+)|"
        r"(я|меня|мне|[A-ZА-ЯЁ][a-zа-яё]+)\s+(\d+(?:[.,]\d+)?))",
        text,
    )
    if len(name_amount_pairs) >= 2:
        shares = []
        for m in name_amount_pairs:
            if m[0]:
                share = m[0]
                name = m[1]
            else:
                name = m[2]
                share = m[3]
            shares.append({"name": name.strip(), "share": share.strip()})
        return "by_amount", shares

    name_pct_pairs = re.findall(
        r"(?:(\d+(?:[.,]\d+)?)\s*%\s*(?:с\s+)?(я|меня|мне|[A-ZА-ЯЁ][a-zа-яё]+)|"
        r"(я|меня|мне|[A-ZА-ЯЁ][a-zа-яё]+)\s+(\d+(?:[.,]\d+)?)\s*%)",
        text,
    )
    if len(name_pct_pairs) >= 2:
        shares = []
        for m in name_pct_pairs:
            if m[0]:
                share = m[0]
                name = m[1]
            else:
                name = m[2]
                share = m[3]
            shares.append({"name": name.strip(), "share": share.strip()})
        return "by_percent", shares

    return "equal", None


CATEGORY_KEYWORDS = {
    "food": ("ресторан", "ужин", "обед", "завтрак", "кафе", "еда",
             "ресто", "coffee", "lunch", "dinner", "кофе", "пицца"),
    "taxi": ("такси", "uber", "yandex", "грэб", "grab", "bolt", "транспорт"),
    "hotel": ("отель", "hotel", "хостел", "hostel", "airbnb",
              "ночёвка", "ночевка", "отеля"),
    "tickets": ("билет", "ticket", "tickets", "перелёт", "перелет",
                "поезд", "автобус", "flight"),
    "shopping": ("магазин", "shopping", "одежда", "продукты", "groceries"),
}


def _detect_category(title: str, full_text: str) -> str:
    blob = (title + " " + full_text).lower()
    for cat, words in CATEGORY_KEYWORDS.items():
        if any(w in blob for w in words):
            return cat
    return "other"


class RuleBasedProvider(AIProvider):
    name = "rule_based"

    async def parse_intent(self, text: str, *, context: dict | None = None) -> Intent:
        original = text
        normalized = _normalize_currency_typos(text)
        t = normalized.strip().lower()

        if not t:
            return Intent(action="unknown", raw_text=original)

        # show_today_spending
        if re.search(
            r"(сколько\s+(мы\s+)?потратил\w*\s*(за\s+)?сегодн)|"
            r"((?:\u0442\u0440\u0430\u0442\u044b|\u0440\u0430\u0441\u0445\u043e\u0434\u044b)\s*(?:\u0437\u0430\s+)?\u0441\u0435\u0433\u043e\u0434\u043d\u044f)|"
            r"(today\s+spending)|(today\s+expenses)",
            t,
        ):
            return Intent(
                action="show_today_spending",
                confidence=0.85,
                payload={"date": "today", "group_by": "category"},
                raw_text=original,
            )

        # show_balance
        if re.search(
            r"\b(скинь\s+баланс|покажи\s+баланс|балан|кто\s+кому|"
            r"кто\s+должен|кто\s+сколько|debts?|balance)\b",
            t,
        ):
            return Intent(
                action="show_balance",
                confidence=0.85,
                payload={"scope": "trip"},
                raw_text=original,
            )

        # convert_currency
        m_conv = re.search(
            r"(?:конвертир|перевед|конверт|convert|rate|курс)\D*?(\d[\d .,]*)\s*"
            r"([a-zа-я$€₽£¥₫]+)\s*(?:в|->|to|→)\s*([a-zа-я$€₽£¥₫]+)",
            t,
        )
        if m_conv:
            amount = _parse_amount(m_conv.group(1))
            base = _detect_currency(m_conv.group(2))
            quote = _detect_currency(m_conv.group(3))
            if amount and base and quote:
                return Intent(
                    action="convert_currency",
                    confidence=0.9,
                    payload={"amount": str(amount), "from": base, "to": quote},
                    raw_text=original,
                )

        # find_document
        if re.search(
            r"\b(где|найди|покажи|find|show)\b.*"
            r"\b(билет|бронь|hotel|insurance|ticket|документ|booking|voucher)\b",
            t,
        ):
            return Intent(
                action="find_document",
                confidence=0.7,
                payload={"query": original.strip()},
                raw_text=original,
            )

        # add_expense paths
        money = CURRENCY_REGEX.search(t)
        if money and _looks_like_paid(t):
            return self._build_expense(
                original, normalized, money, t,
                confidence=0.8, has_verb=True,
            )

        if money and re.search(
            r"делим|поровну|пополам|на\s+(?:троих|двоих|четверых|\d+)", t
        ):
            return self._build_expense(
                original, normalized, money, t,
                confidence=0.7, has_verb=False,
            )

        if money:
            return self._build_expense(
                original, normalized, money, t,
                confidence=0.5, has_verb=False,
            )

        # Fallback: amount without currency + paid verb → add_expense with currency=None
        if _looks_like_paid(t):
            amount_only = re.search(
                r"(\d{1,3}(?:[ .,\u00a0]\d{3})+(?:[.,]\d+)?(?:\s*[kkкКmMмМ]{1,2})?|"
                r"\d+(?:[.,]\d+)?(?:\s*[kkкКmMмМ]{1,2})?)",
                t,
            )
            if amount_only:
                amount = _parse_amount(amount_only.group(1))
                if amount and amount > 0:
                    title = _extract_title(normalized, amount_only)
                    if not title or len(title) < 2:
                        title = "Расход"
                    category = _detect_category(title, t)
                    participants = _detect_participants(original)
                    split_scope = "mentioned" if participants else "self"
                    return Intent(
                        action="add_expense",
                        confidence=0.6,
                        payload={
                            "amount": str(amount), "currency": None,
                            "title": title, "payer_name": None,
                            "participant_names": participants or None,
                            "split_scope": split_scope, "split_all": False,
                            "split_count": None, "category": category,
                        },
                        raw_text=original,
                        needs_confirmation=True,
                    )

        # currency-prefix amount: "₺250"
        m_prefix = re.search(
            r"([₽$€¥£₫₺])\s*(\d{1,3}(?:[ .,\u00a0]\d{3})*(?:[.,]\d+)?(?:\s*[kkкКmMмМ]{1,2})?|"
            r"\d+(?:[.,]\d+)?(?:\s*[kkкКmMмМ]{1,2})?)",
            t,
        )
        if m_prefix:
            currency = _detect_currency(m_prefix.group(1))
            amount = _parse_amount(m_prefix.group(2))
            if currency and amount:
                title = _extract_title(normalized, m_prefix)
                split_count = _detect_split_count(t)
                participants = _detect_participants(original)
                if _looks_like_split_all(t):
                    split_scope = "all"
                elif participants:
                    split_scope = "mentioned"
                elif split_count:
                    split_scope = "all"
                else:
                    split_scope = "self"
                category = _detect_category(title or "", t)
                split_mode, custom_shares = _detect_uneven_split(original)
                if split_mode != "equal" and custom_shares:
                    return Intent(
                        action="add_expense",
                        confidence=0.6,
                        payload={
                            "amount": str(amount),
                            "currency": currency,
                            "title": title or "Расход",
                            "payer_name": None,
                            "participant_names": None,
                            "split_scope": "mentioned",
                            "split_all": False,
                            "split_count": None,
                            "category": category,
                            "split_mode": split_mode,
                            "custom_shares": custom_shares,
                        },
                        raw_text=original,
                        needs_confirmation=True,
                    )
                return Intent(
                    action="add_expense",
                    confidence=0.7 if (_looks_like_split_all(t) or participants) else 0.5,
                    payload={
                        "amount": str(amount),
                        "currency": currency,
                        "title": title or "Расход",
                        "payer_name": None,
                        "participant_names": participants or None,
                        "split_scope": split_scope,
                        "split_all": split_scope == "all",
                        "split_count": split_count,
                        "category": category,
                    },
                    raw_text=original,
                    needs_confirmation=True,
                )

        # Weather (get_weather) — no trailing \b so Cyrillic works
        m_weather = re.search(
            r"(?:погод|weather|сколько\s+градусов|температур|дождь|снег|ветер|влажность)",
            t,
        )
        if m_weather:
            city = None
            m_city = re.search(
                r"(?:погод[аыуе]?\s+(?:в|на|во)\s+|weather\s+(?:in|at)\s+|"
                r"сколько\s+градусов\s+(?:в|на|во)\s+|"
                r"температур[аы]\s+(?:в|на|во)\s+|"
                r"(?:какая\s+)?погода\s+(?:в|на|во)\s+|"
                r"(?:какой\s+)?дождь\s+(?:в|на|во)\s+)"
                r"([A-ZА-ЯЁ][A-Za-zА-Яа-яёЁ\s\-]+)",
                original,
            )
            if m_city:
                city = m_city.group(1).strip().rstrip("?")
            else:
                m2 = re.search(
                    r"(?:погод[аыуе]?|weather)\s+([A-ZА-ЯЁ][A-Za-zА-Яа-яёЁ\s\-]{2,30})$",
                    original,
                    re.IGNORECASE,
                )
                if m2:
                    city = m2.group(1).strip().rstrip("?!")

            if city:
                return Intent(
                    action="get_weather",
                    confidence=0.85,
                    payload={"city": city},
                    raw_text=original,
                )

        return Intent(action="unknown", confidence=0.0, raw_text=original)

    def _build_expense(
        self, original, normalized, money, t,
        *, confidence: float, has_verb: bool,
    ) -> Intent:
        amount = _parse_amount(money.group(1))
        currency = _detect_currency(money.group(2))
        if not amount:
            return Intent(action="unknown", confidence=0.0, raw_text=original)
        if not currency:
            currency = None
        title = _extract_title(normalized, money)
        if not title or len(title) < 2:
            title = "Расход"

        split_count = _detect_split_count(t)
        participants = _detect_participants(original)
        if _looks_like_split_all(t):
            split_scope = "all"
        elif participants:
            split_scope = "mentioned"
        elif split_count:
            split_scope = "all"
        else:
            split_scope = "self"

        category = _detect_category(title, t)
        split_mode, custom_shares = _detect_uneven_split(original)
        if split_mode != "equal" and custom_shares:
            return Intent(
                action="add_expense",
                confidence=confidence - 0.1,
                payload={
                    "amount": str(amount), "currency": currency,
                    "title": title, "payer_name": None,
                    "participant_names": None,
                    "split_scope": "mentioned", "split_all": False,
                    "split_count": None, "category": category,
                    "split_mode": split_mode, "custom_shares": custom_shares,
                },
                raw_text=original, needs_confirmation=True,
            )

        return Intent(
            action="add_expense",
            confidence=confidence,
            payload={
                "amount": str(amount), "currency": currency,
                "title": title, "payer_name": None,
                "participant_names": participants or None,
                "split_scope": split_scope, "split_all": split_scope == "all",
                "split_count": split_count, "category": category,
            },
            raw_text=original, needs_confirmation=True,
        )


def _extract_title(normalized: str, money_match: re.Match[str]) -> str:
    """Extract the title of an expense by stripping the matched amount/currency."""
    start, end = money_match.span()
    title = (normalized[:start] + normalized[end:]).strip()
    # Remove leading delimiters and known structural words
    title = re.sub(
        r"^[,.\-:;!?\s]+|[,.\-:;!?\s]+$", "", title
    )
    # Remove leading "в" / "за" prepositions if they're standalone
    title = re.sub(
        r"^(в|за|на)\s+(?!всех|нас|все|них)", "", title
    ).strip()
    return title[:120] if title else None
