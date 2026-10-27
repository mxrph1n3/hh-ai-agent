import re
from urllib.parse import urlparse, parse_qs, unquote

URL_RE = re.compile(r"https?://[^\s<>\"'«»]+", re.I)

# Хосты, которые точно не анкеты (мессенджеры, видеозвонки, сам HH)
IGNORE_HOSTS = (
    "hh.ru", "headhunter.ru", "hhcdn.ru", "t.me", "telegram.me", "telegram.org",
    "wa.me", "whatsapp.com", "vk.com", "vk.me", "zoom.us", "telemost.yandex.ru",
    "meet.google.com", "calendly.com", "youtube.com", "youtu.be",
)

# Для неизвестных сайтов — берём ссылку, только если рядом говорят об анкете
FORM_CONTEXT_RE = re.compile(
    r"анкет|\bформ[уаеы]?\b|\bопрос|заполн|\bтест\b|\bquestionnaire|\bform\b", re.I
)

# Документы и файлы — это не анкеты (тестовое задание человек откроет сам)
DOC_HOSTS = ("drive.google.com", "disk.yandex.ru", "disk.yandex.com", "disk.360.yandex.ru",
             "notion.so", "notion.site", "miro.com", "figma.com")


def unwrap_hh_away(url: str) -> str:
    """hh.ru/away?to=<url> → <url>."""
    parsed = urlparse(url)
    if parsed.netloc.endswith("hh.ru") and parsed.path.startswith("/away"):
        to = parse_qs(parsed.query).get("to")
        if to:
            return unquote(to[0])
    return url


def normalize_url(url: str) -> str:
    return unwrap_hh_away(url).rstrip(".,;:!?)»]")


def classify(url: str) -> str | None:
    """Тип формы по URL или None, если это не форма."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()

    if host == "docs.google.com":
        return "google" if "/forms/" in path else None
    if host in ("forms.gle", "goo.gl") and (host == "forms.gle" or path.startswith("/forms")):
        return "google"
    if host.startswith("forms.yandex.") or host == "forms.360.yandex.ru":
        return "yandex"
    if host.endswith("typeform.com"):
        return "typeform"
    if host == "tally.so":
        return "tally"
    if any(host == h or host.endswith("." + h) for h in IGNORE_HOSTS + DOC_HOSTS):
        return None
    # Главная страница сайта — не форма
    if path.strip("/") == "" and not parsed.query:
        return None
    return "other"


def extract_form_links(text: str, hrefs: list[str]) -> list[tuple[str, str]]:
    """Ссылки на формы из сообщения: [(url, kind)]."""
    candidates = [normalize_url(h) for h in hrefs]
    candidates += [normalize_url(m) for m in URL_RE.findall(text or "")]

    result, seen = [], set()
    for url in candidates:
        if url in seen or not url.lower().startswith("http"):
            continue
        seen.add(url)
        kind = classify(url)
        if kind is None:
            continue
        if kind == "other" and not FORM_CONTEXT_RE.search(text or ""):
            continue
        result.append((url, kind))
    return result
