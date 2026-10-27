import re
from config import TITLE_ALLOW, TITLE_REJECT


_STEMS = {
    "контент", "соцсет", "рилс", "копирайт", "смм", "smm", "reels", "сторис", "ugc",
}


def reject_reason(title: str) -> str | None:
    """Возвращает стоп-слово, если название не подходит."""
    title_lower = title.lower().replace("ё", "е")
    for word in TITLE_REJECT:
        w = word.lower().replace("ё", "е")
        if " " in w or "+" in w or "-" in w or w in _STEMS:
            if w in title_lower:
                return w
        elif re.search(rf"(?<!\w){re.escape(w)}(?!\w)", title_lower, flags=re.UNICODE):
            return w
    return None


_ROLE_MARKERS = (
    "smm", "смм", "контент-маркетолог", "контент маркетолог",
    "контент-менеджер", "контент менеджер", "контент-мейкер", "контент мейкер",
    "копирайтер", "рилсмейкер", "reels", "ведение соцсет",
    "контент-план", "контент план", "ugc",
)


def content_smm_reason(text: str) -> str | None:
    """Стоп-слово, если в тексте роль про контент или SMM."""
    lowered = text.lower().replace("ё", "е")
    for marker in _ROLE_MARKERS:
        if marker in lowered:
            return marker
    return None


def title_passes(title: str) -> bool:
    """True, если в названии есть маркетинговое ключевое слово."""
    title_lower = title.lower()
    return any(w in title_lower for w in TITLE_ALLOW)
