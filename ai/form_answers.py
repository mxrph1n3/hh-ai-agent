"""Ответы на вопросы анкеты через локальную Ollama (structured outputs)."""
import json
import os
import re
import aiohttp
import yaml
from config import OLLAMA_BASE, FORMS_MODEL, MY_RESUME_SUMMARY, PROFILE_FILE

BATCH_SIZE = 15
CHOICE_TYPES = ("radio", "select", "listbox")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "value": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                },
                "required": ["id", "value"],
            },
        }
    },
    "required": ["answers"],
}

SYSTEM = """ты заполняешь анкету работодателя от имени кандидата на вакансию.
верни JSON: {"answers": [{"id": "<id поля>", "value": ...}]} — по одному элементу на каждое поле.

правила:
- пиши от первого лица, по-русски (если вопрос на английском — по-английски). живо и по делу, без канцелярита.
- фио, контакты, ссылки, даты, город, зарплату и прочие факты бери ТОЛЬКО из профиля. если нужного факта нет — value: null. ничего не выдумывай, никаких примерных ссылок и ников.
- если у поля есть hint (формат, пример) — соблюдай его.
- опыт, навыки, цифры и кейсы — только из резюме. если опыта честно нет — так и выбирай.
- radio / select / listbox: value — строка, ровно один вариант из options, дословно.
- checkbox: value — массив ВСЕХ подходящих по резюме вариантов из options, дословно. согласие на обработку персональных данных и подобные галочки — отмечай.
- «Другое» выбирай, только если ни один вариант не подходит; тогда заполни и поле «свой вариант» под ним, иначе оставь его null.
- открытые вопросы: 2–4 предложения, до 500 символов, конкретно, с цифрами из резюме. если в профиле есть готовый ответ (faq) — используй его.
- шкала оценок — честная оценка по резюме.
- необязательное поле, на которое нечего ответить — null.
- type unknown — value: null."""


_profile_cache: dict | None = None


def load_profile() -> dict | None:
    """profile.yaml без пустых значений. None — файла нет."""
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache
    if not os.path.exists(PROFILE_FILE):
        return None
    with open(PROFILE_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _profile_cache = _strip_empty(data)
    return _profile_cache


def _strip_empty(value):
    if isinstance(value, dict):
        cleaned = {k: _strip_empty(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, "", {}, [])}
    if isinstance(value, str):
        return value.strip()
    return value


async def answer_fields(fields: list[dict], form_info: dict, form_row: dict) -> dict[str, object]:
    """{field_id: value} для переданных полей. Значения уже сверены с options."""
    profile = load_profile() or {}
    answers: dict[str, object] = {}
    askable = [f for f in fields if f["type"] not in ("unknown", "file")]

    for i in range(0, len(askable), BATCH_SIZE):
        batch = askable[i:i + BATCH_SIZE]
        raw = await _ask(batch, form_info, form_row, profile)
        for field in batch:
            answers[field["id"]] = _validate(field, raw.get(field["id"]))

    facts = _facts_text(profile)
    for field in askable:
        fid = field["id"]
        # Контакты — из профиля напрямую, модель их не придумывает
        key = _contact_key(field)
        if key:
            answers[fid] = _format_contact(key, profile.get(key), field.get("hint", ""))
        elif isinstance(answers.get(fid), str) and not _grounded(answers[fid], facts):
            print(f"   ⚠️ Отброшен ответ с фактами не из профиля: {field['label'][:50]} → {answers[fid][:80]}")
            answers[fid] = None
    return answers


CONTACT_PATTERNS = (
    ("telegram", re.compile(r"telegram|телеграм|\btg\b|тг\b", re.I)),
    ("email", re.compile(r"e-?mail|электронн\w* почт|^почта", re.I)),
    ("phone", re.compile(r"телефон|phone|номер тел|whatsapp", re.I)),
)
URL_RE = re.compile(r"https?://\S+|\b[\w-]+\.(?:ru|com|io|me|so|site|pro)/\S*", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
HANDLE_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{3,}")
PHONE_RE = re.compile(r"\+?\d[\d\s()\-]{8,}\d")


def _contact_key(field: dict) -> str | None:
    if field["type"] == "email":
        return "email"
    if field["type"] == "tel":
        return "phone"
    if field["type"] not in ("text", "url"):
        return None
    for key, pattern in CONTACT_PATTERNS:
        if pattern.search(field["label"]):
            return key
    return None


def _format_contact(key: str, value, hint: str):
    if not value:
        return None
    value = str(value).strip()
    if key == "telegram" and not value.startswith(("@", "http")):
        value = "@" + value
    if key == "phone" and re.search(r"без пробел|без скоб|\+7\d{10}|\+79\d", hint):
        value = re.sub(r"[^\d+]", "", value)
    return value


def _facts_text(profile: dict) -> str:
    return (yaml.safe_dump(profile, allow_unicode=True) + MY_RESUME_SUMMARY).lower()


def _grounded(text: str, facts: str) -> bool:
    """Ссылки, email, @ники и телефоны в ответе должны быть из профиля или резюме."""
    facts_digits = re.sub(r"\D", "", facts)
    for match in URL_RE.findall(text) + EMAIL_RE.findall(text) + HANDLE_RE.findall(text):
        if match.lower().rstrip(".,;)/") not in facts:
            return False
    for match in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if len(digits) >= 10 and digits[-10:] not in facts_digits:
            return False
    return True


async def _ask(fields: list[dict], form_info: dict, form_row: dict, profile: dict) -> dict:
    compact = [
        {
            "id": f["id"], "type": f["type"], "question": f["label"][:500],
            "required": f["required"],
            **({"hint": f["hint"]} if f.get("hint") else {}),
            **({"options": [o[:150] for o in f["options"]]} if f["options"] else {}),
        }
        for f in fields
    ]
    prompt = (
        f"профиль кандидата (факты):\n{yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)}\n"
        f"резюме:\n{MY_RESUME_SUMMARY.strip()}\n\n"
        f"вакансия: {form_row.get('vacancy_title') or '?'} — {form_row.get('company') or '?'}\n"
        f"сообщение работодателя со ссылкой:\n{(form_row.get('context') or '')[:1500]}\n\n"
        f"анкета: {form_info.get('title', '')}\n{form_info.get('description', '')}\n\n"
        f"поля:\n{json.dumps(compact, ensure_ascii=False, indent=1)}"
    )
    payload = {
        "model": FORMS_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "format": ANSWER_SCHEMA,
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{OLLAMA_BASE}/api/chat", json=payload,
            timeout=aiohttp.ClientTimeout(total=600),
        ) as response:
            response.raise_for_status()
            data = await response.json()
    content = data.get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        print(f"⚠️ Ollama вернула не JSON: {content[:200]}")
        return {}
    return {str(a.get("id")): a.get("value") for a in parsed.get("answers", []) if isinstance(a, dict)}


def match_option(options: list[str], value) -> str | None:
    """Сопоставляет ответ модели (или пользователя) с вариантом из формы."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().casefold()
    for opt in options:
        if opt.casefold() == v:
            return opt
    for opt in options:
        o = opt.casefold()
        if o.startswith(v) or v.startswith(o) or (len(v) > 3 and v in o):
            return opt
    return None


def _validate(field: dict, value):
    ftype = field["type"]
    if value is None:
        return None
    if ftype in CHOICE_TYPES:
        if isinstance(value, list):
            value = value[0] if value else None
        return match_option(field["options"], value)
    if ftype == "checkbox":
        values = value if isinstance(value, list) else [value]
        matched = [m for m in (match_option(field["options"], v) for v in values) if m]
        return list(dict.fromkeys(matched)) or None
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    text = str(value).strip()
    if not text or text.lower() in ("null", "none", "нет данных"):
        return None
    if field.get("max_length"):
        text = text[:field["max_length"]]
    return text
