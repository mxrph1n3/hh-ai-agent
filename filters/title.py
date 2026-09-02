import re
from config import TITLE_ALLOW, TITLE_REJECT


def reject_reason(title: str) -> str | None:
    """Возвращает стоп-слово, если название не подходит."""
    title_lower = title.lower()
    for word in TITLE_REJECT:
        w = word.lower()
        if " " in w or "+" in w or "-" in w:
            if w in title_lower:
                return w
        elif re.search(rf"(?<!\w){re.escape(w)}(?!\w)", title_lower, flags=re.UNICODE):
            return w
    return None


def title_passes(title: str) -> bool:
    """True, если в названии есть маркетинговое ключевое слово."""
    title_lower = title.lower()
    return any(w in title_lower for w in TITLE_ALLOW)
