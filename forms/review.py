"""Просмотр и правка сохранённых ответов анкеты."""
from ai.form_answers import match_option
from forms.runner import is_empty

STATUS_TITLES = {
    "new": "в очереди",
    "filled": "заполнена, ждёт проверки",
    "needs_input": "не хватает данных",
    "manual": "нужно заполнить вручную",
    "failed": "ошибка",
    "submitted": "отправлена",
    "skipped": "пропущена",
    "not_form": "не форма",
}


def _format_value(value) -> str:
    if is_empty(value):
        return "—"
    if isinstance(value, list):
        return "; ".join(value)
    return str(value)


def build_review_text(form: dict) -> str:
    lines = [
        f"📋 Анкета #{form['id']} — {form['vacancy_title'] or '?'} ({form['company'] or '?'})",
        form["url"],
        f"Статус: {STATUS_TITLES.get(form['status'], form['status'])}",
    ]
    if form.get("note"):
        lines.append(form["note"])
    lines.append("")

    for num, a in enumerate(form["answers"], 1):
        mark = " *" if a["required"] else ""
        label = a["label"] if len(a["label"]) <= 150 else a["label"][:150] + "…"
        lines.append(f"{num}. {label}{mark}")
        if a["type"] == "unknown":
            lines.append("   ⚠️ поле не распознано — не заполняется")
        else:
            prefix = "❗" if a["required"] and is_empty(a["value"]) else "→"
            lines.append(f"   {prefix} {_format_value(a['value'])}")
        if a.get("error"):
            lines.append(f"   ⚠️ не вписалось: {a['error']}")
    return "\n".join(lines)


def apply_fix(form: dict, num: int, text: str) -> tuple[list[dict], str | None]:
    """Меняет ответ №num. Возвращает (answers, ошибка)."""
    answers = form["answers"]
    if not 1 <= num <= len(answers):
        return answers, f"в анкете {len(answers)} полей"
    entry = answers[num - 1]
    text = text.strip()

    if text == "-":
        value = None
    elif entry["type"] == "checkbox":
        value = []
        for part in text.split(";"):
            opt = match_option(entry["options"], part)
            if not opt:
                return answers, f"нет варианта «{part.strip()}». Варианты: " + "; ".join(entry["options"])
            value.append(opt)
    elif entry["type"] in ("radio", "select", "listbox"):
        value = match_option(entry["options"], text)
        if not value:
            return answers, "нет такого варианта. Варианты: " + "; ".join(entry["options"])
    else:
        value = text

    entry.update(value=value, source="user", error=None)
    return answers, None


def has_missing_required(answers: list[dict]) -> bool:
    return any(a["required"] and a["type"] != "unknown" and is_empty(a["value"]) for a in answers)
