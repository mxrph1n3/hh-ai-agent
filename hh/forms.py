import asyncio
import re
from playwright.async_api import Page

from ai.analyzer import _ask_ollama
from config import CANDIDATE, CANDIDATE_TEXT

_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_FORM_HINT = re.compile(r"анкет|опрос|заполн|форма|questionnaire|survey|form", re.I)
_FORM_URL = re.compile(
    r"docs\.google\.com/forms|forms\.gle|docs\.google\.com/document|"
    r"docs\.google\.com/spreadsheets|forms\.office\.com|typeform\.com|"
    r"tally\.so|forms\.yandex|airtable\.com|jotform|surveymonkey|"
    r"anketa|questionnaire|/forms?/",
    re.I,
)
_NEXT = re.compile(r"далее|next|продолжить|continue|вперёд|вперед", re.I)
_SUBMIT = re.compile(r"отправ|submit|send|заверш|finish|готово", re.I)
_SKIP = re.compile(r"^(skip|нет данных|не знаю|unknown)$", re.I)

# Более длинные подписи раньше коротких, чтобы «фамилия» не спуталась с «имя».
_KNOWN = (
    (r"отчеств", "middle_name"),
    (r"фамили", "last_name"),
    (r"ф\.?\s*и\.?\s*о|полное имя|фио", "full_name"),
    (r"имя|first name|firstname", "first_name"),
    (r"телефон|phone|мобильн|whatsapp|ватсап", "phone"),
    (r"e-?mail|почт|mail", "email"),
    (r"дата рождения|birth", "birth_date"),
    (r"возраст|age", "age"),
    (r"пол\b|gender", "gender"),
    (r"гражданств", "citizenship"),
    (r"разрешен|work permit", "work_permit"),
    (r"переезд|relocation", "relocation"),
    (r"командиров", "business_trips"),
    (r"город проживания|проживаете|город\b|city", "city"),
    (r"желаем.*должност|позицию|position|должность", "position"),
    (r"занятост", "employment"),
    (r"формат работ|удален|офис", "work_format"),
    (r"опыт", "experience"),
    (r"образован|вуз|универ", "education"),
    (r"язык", "languages"),
    (r"специализац", "specialization"),
)


def extract_form_urls(text: str) -> list[str]:
    """Ссылки на анкеты из сообщения работодателя."""
    found: list[str] = []
    seen: set[str] = set()
    mentions_form = _FORM_HINT.search(text) is not None
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(").,;»\"'")
        key = url.split("?")[0]
        if key in seen:
            continue
        lowered = url.lower()
        if "hh.ru" in lowered or "hh.kz" in lowered:
            continue
        if _FORM_URL.search(lowered) or mentions_form:
            seen.add(key)
            found.append(url)
    return found


def known_answer(question: str) -> str | None:
    text = question.lower().replace("ё", "е")
    for pattern, field in _KNOWN:
        if re.search(pattern, text):
            return CANDIDATE[field]
    return None


async def answer_question(question: str, options: list[str] | None = None) -> str | None:
    known = known_answer(question)
    if known and not options:
        return known
    if known and options:
        picked = _match_option(known, options)
        if picked:
            return picked

    options_text = ""
    if options:
        options_text = "варианты:\n" + "\n".join(f"- {item}" for item in options[:20])
    prompt = f"""ответь на вопрос анкеты работодателя от лица кандидата.
только факт из профиля. если факта нет, ответь одним словом SKIP.
без пояснений и без кавычек.
если есть варианты, верни текст одного подходящего варианта дословно.

профиль:
{CANDIDATE_TEXT}

вопрос: {question}
{options_text}
"""
    try:
        raw = await _ask_ollama(prompt, "отвечай только значением поля или SKIP.")
    except Exception as e:
        print(f"   не удалось спросить модель: {e}")
        return known
    line = raw.strip().splitlines()[0].strip(" \"'«»")
    if not line or _SKIP.match(line):
        return None
    if options:
        return _match_option(line, options) or line
    return line[:500]


def _match_option(answer: str, options: list[str]) -> str | None:
    needle = answer.lower().strip()
    for option in options:
        label = option.lower().strip()
        if needle == label or needle in label or label in needle:
            return option
    return None


async def fill_questionnaire(page: Page, url: str) -> str:
    """Заполняет все страницы анкеты и не нажимает отправку.

    Страница остаётся открытой, чтобы можно было перечитать.
    """
    print(f"Анкета: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(2)

    for step in range(1, 13):
        print(f"   Лист {step}")
        filled = await _fill_visible(page)
        print(f"   Заполнено полей: {filled}")
        action = await _advance_or_stop(page)
        if action == "next":
            await asyncio.sleep(1.5)
            continue
        if action == "submit":
            print("   Последний лист. Кнопку отправки не нажимаю.")
            return "draft"
        print("   Дальше листов нет. Анкета не отправлена.")
        return "draft"
    print("   Остановился после 12 листов, отправка не нажата.")
    return "draft"


async def _fill_visible(page: Page) -> int:
    filled = 0
    filled += await _fill_choice_groups(page, '[role="radiogroup"]', "radio")
    filled += await _fill_choice_groups(page, '[role="group"]', "checkbox")
    fields = page.locator(
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="radio"]):not([type="checkbox"]), textarea, select'
    )
    count = await fields.count()
    for index in range(count):
        field = fields.nth(index)
        try:
            if not await field.is_visible():
                continue
            kind = (await field.get_attribute("type") or "").lower()
            if kind in {"password", "file", "image"}:
                continue
            current = await field.input_value()
            if current.strip():
                continue
            label = await _field_label(field)
            if not label:
                continue
            tag = await field.evaluate("el => el.tagName")
            if tag == "SELECT":
                options = await field.locator("option").all_inner_texts()
                options = [item.strip() for item in options if item.strip() and item.strip().lower() not in {"выберите", "select"}]
                answer = await answer_question(label, options)
                if not answer:
                    print(f"   пропуск: {label}")
                    continue
                await field.select_option(label=answer)
            else:
                answer = await answer_question(label)
                if not answer:
                    print(f"   пропуск: {label}")
                    continue
                await field.fill(answer)
            filled += 1
            print(f"   {label} -> {answer}")
        except Exception as e:
            print(f"   поле не заполнено: {e}")
    return filled


async def _fill_choice_groups(page: Page, selector: str, kind: str) -> int:
    groups = page.locator(selector)
    filled = 0
    for index in range(await groups.count()):
        group = groups.nth(index)
        try:
            if not await group.is_visible():
                continue
            question = await _field_label(group)
            options = await _choice_options(group)
            if not question or not options:
                continue
            if kind == "radio" and await group.locator('[aria-checked="true"], input:checked').count():
                continue
            answer = await answer_question(question, options)
            if not answer:
                print(f"   пропуск: {question}")
                continue
            option = group.get_by_text(answer, exact=False).last
            if await option.count():
                await option.click(timeout=3000)
                filled += 1
                print(f"   {question} -> {answer}")
        except Exception as e:
            print(f"   вариант не выбран: {e}")
    return filled


async def _choice_options(group) -> list[str]:
    labels = await group.locator('[role="radio"], [role="checkbox"], label').all_inner_texts()
    cleaned = []
    for label in labels:
        text = " ".join(label.split())
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:20]


async def _field_label(field) -> str:
    try:
        return await field.evaluate(
            """(el) => {
                const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                const own = clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name'));
                if (own) return own.slice(0, 300);
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) return clean(label.innerText).slice(0, 300);
                }
                const wrapped = el.closest('label');
                if (wrapped) return clean(wrapped.innerText).slice(0, 300);
                const parent = el.closest('[role="listitem"], fieldset, [role="radiogroup"], [role="group"], .Qr7Oae') || el.parentElement;
                return clean(parent ? parent.innerText : '').slice(0, 300);
            }"""
        )
    except Exception:
        return ""


async def _advance_or_stop(page: Page) -> str:
    buttons = page.locator('button, [role="button"], input[type="submit"]')
    next_index = None
    has_submit = False
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        try:
            if not await button.is_visible():
                continue
            text = " ".join((await button.inner_text()).split())
            if not text:
                text = await button.get_attribute("value") or ""
            if _SUBMIT.search(text) and not _NEXT.search(text):
                has_submit = True
                continue
            if _NEXT.search(text):
                next_index = index
        except Exception:
            continue
    if next_index is not None:
        await buttons.nth(next_index).click(timeout=5000)
        return "next"
    if has_submit:
        return "submit"
    return "stop"
