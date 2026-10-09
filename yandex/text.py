import re
from config import YANDEX_MIN_BUDGET, YANDEX_OFFER_PRICE

_URL = re.compile(r"(https?://\S+|www\.\S+)", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_PHONE = re.compile(r"(?:\+7|8)[\s\-()]*(?:\d[\s\-()]*){10}")
_MESSENGER = re.compile(
    r"\b(?:t\.me|wa\.me|telegram|whatsapp|ватсап|телеграм)\S*",
    re.I,
)
_MONEY = re.compile(r"(\d[\d\s]{0,12})\s*(тыс\.?|₽|руб)", re.I)


def sanitize_reply(text: str) -> str:
    """Убирает контакты: в отклике Яндекса их нельзя оставлять."""
    cleaned = _URL.sub("", text)
    cleaned = _EMAIL.sub("", cleaned)
    cleaned = _PHONE.sub("", cleaned)
    cleaned = _MESSENGER.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()[:1000]


def parse_budget(text: str) -> int | None:
    """Самая крупная сумма в рублях из текста заказа."""
    values: list[int] = []
    normalized = text.replace("\u00a0", " ").replace("\u202f", " ")
    for match in _MONEY.finditer(normalized):
        number = int(re.sub(r"\s+", "", match.group(1)))
        if "тыс" in match.group(2).lower():
            number *= 1000
        if number >= 1000:
            values.append(number)
    return max(values) if values else None


def choose_price(text: str) -> tuple[int | None, str]:
    """Бюджет заказчика, если он не ниже минимума. Иначе цена студии."""
    budget = parse_budget(text)
    if budget is not None and budget >= YANDEX_MIN_BUDGET:
        return budget, "бюджет заказчика"
    if YANDEX_OFFER_PRICE > 0:
        return YANDEX_OFFER_PRICE, "цена студии"
    return None, "цена не задана"
