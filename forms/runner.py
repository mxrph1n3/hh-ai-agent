"""Заполнение анкет из очереди forms. Анкеты никогда не отправляются автоматически:
агент заполняет их и сохраняет ответы, а отправляете вы сами через `python -m forms.cli open <id>`."""
import asyncio
import os
import aiohttp
from playwright.async_api import Page
from config import FORMS_MAX_PER_CYCLE, FORMS_SHOTS_DIR
from ai.form_answers import answer_fields, load_profile
from forms.extract import collect_errors, extract_form, fill_field, find_nav_button, prepare_page
from storage.db import get_forms_by_status, update_form

MAX_PAGES = 10
_profile_warned = False


def _key(page_no: int, field: dict) -> str:
    return f"{page_no}|{field['type']}|{field['label']}"


def is_empty(value) -> bool:
    return value in (None, "", [])


async def run_form(page: Page, form: dict) -> dict:
    """Проходит форму постранично до последней страницы, не нажимая «Отправить».

    Сохранённые ответы (form['answers']) вписываются как есть, на новые поля
    отвечает модель. Возвращает {status, note, answers, shots}.
    """
    os.makedirs(FORMS_SHOTS_DIR, exist_ok=True)
    stored = {a["key"]: a for a in form["answers"]}
    answers: list[dict] = []
    shots: list[str] = []

    def result(status: str, note: str = "") -> dict:
        return {"status": status, "note": note, "answers": answers, "shots": shots}

    async def shot(name: str):
        path = os.path.join(FORMS_SHOTS_DIR, f"form{form['id']}_{name}.png")
        try:
            await page.screenshot(path=path, full_page=True)
            shots.append(path)
        except Exception:
            pass

    await page.goto(form["url"], wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    if "accounts.google.com" in page.url or "ServiceLogin" in page.url:
        return result("manual", "форма требует входа в Google-аккаунт")

    prev_signature = None
    for page_no in range(MAX_PAGES):
        await prepare_page(page)
        info = await extract_form(page)
        fields = info["fields"]
        signature = [f["label"] for f in fields]
        if prev_signature is not None and signature == prev_signature and fields:
            await shot(f"p{page_no}_stuck")
            errors = "; ".join(await collect_errors(page))
            return result("needs_input", "форма не пускает дальше"
                          + (f": {errors}" if errors else " — проверьте ответы на скриншоте"))
        prev_signature = signature

        if info["captcha"]:
            await shot(f"p{page_no + 1}")
            return result("manual", "на форме капча")
        if page_no == 0 and not fields:
            return result("not_form" if form["kind"] == "other" else "manual",
                          "на странице не нашлось полей формы")
        if any(f["type"] == "file" and f["required"] for f in fields):
            await shot(f"p{page_no + 1}")
            return result("manual", "нужно приложить файл")
        unknown = [f["label"][:60] for f in fields if f["type"] == "unknown" and f["required"]]
        if unknown:
            await shot(f"p{page_no + 1}")
            return result("manual", "обязательное поле нестандартного вида: " + "; ".join(unknown))

        todo = [f for f in fields if _key(page_no, f) not in stored]
        generated = await answer_fields(todo, info, form) if todo else {}

        missing = []
        for field in fields:
            key = _key(page_no, field)
            entry = dict(stored.get(key) or {"source": "llm", "value": generated.get(field["id"])})
            entry.update(
                key=key, page=page_no, label=field["label"], type=field["type"],
                options=field["options"], required=field["required"],
            )
            entry["error"] = await fill_field(page, field, entry["value"])
            if field["required"] and (is_empty(entry["value"]) or entry["error"]):
                missing.append(entry)
            answers.append(entry)
            await asyncio.sleep(0.2)

        await shot(f"p{page_no + 1}")
        if missing:
            names = "; ".join(m["label"][:60] for m in missing)
            return result("needs_input", f"не заполнены обязательные поля: {names}")

        kind, button = await find_nav_button(page)
        if kind == "next":
            await button.click()
            await page.wait_for_timeout(2500)
            continue
        if kind == "submit":
            # Последняя страница: дальше только «Отправить» — это делает человек
            return result("filled")
        return result("manual", "не нашли кнопку «Далее» или «Отправить»")
    return result("manual", f"больше {MAX_PAGES} страниц")


async def process_forms(session, notify):
    """Заполняет новые анкеты из очереди (без отправки)."""
    global _profile_warned
    if load_profile() is None:
        if not _profile_warned:
            print("⚠️ Нет profile.yaml — анкеты не заполняются. Скопируйте profile.example.yaml.")
            _profile_warned = True
        return

    for form in get_forms_by_status("new", FORMS_MAX_PER_CYCLE):
        await _handle(session, form, notify)


async def _handle(session, form: dict, notify):
    title = f"#{form['id']} {form['vacancy_title'] or ''} ({form['company'] or ''})"
    print(f"📋 Анкета {title}: {form['url']}")
    page = await session.new_page()
    try:
        res = await run_form(page, form)
    except aiohttp.ClientError as e:
        print(f"   ⚠️ Ollama недоступна ({e}) — попробуем в следующем цикле.")
        return
    except Exception as e:
        print(f"   ❌ Ошибка анкеты: {e}")
        update_form(form["id"], status="failed", note=str(e)[:500])
        return
    finally:
        await page.close()

    status, note = res["status"], res["note"]
    # Пустой список ответов не затирает сохранённые (форма могла не открыться)
    update_form(form["id"], status=status, answers=res["answers"] or None, note=note)
    if status == "filled":
        await notify(f"📋 Анкета {title} заполнена. Проверить: python -m forms.cli show {form['id']}")
    elif status == "needs_input":
        await notify(f"❗ Анкета {title}: {note}. Дополнить: python -m forms.cli show {form['id']}")
    elif status in ("manual", "failed"):
        await notify(f"⚠️ Анкету {title} нужно заполнить вручную: {note}\n{form['url']}")
