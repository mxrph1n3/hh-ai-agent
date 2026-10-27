import asyncio
import re
from config import CHATS_SCAN_LIMIT
from forms.links import extract_form_links
from hh.browser import BrowserSession
from storage.db import (
    is_message_processed, add_processed_message, has_any_chats,
    get_chat_preview, save_chat, add_form,
)

CHAT_LIST_URL = "https://hh.ru/chat"

_JS_CHAT_CELLS = """() => [...document.querySelectorAll('[data-qa^="chatik-open-chat-"]')].map(e => ({
    id: e.getAttribute('data-qa').replace('chatik-open-chat-', ''),
    title: e.querySelector('[data-qa="chat-cell-title"]')?.innerText?.trim() || '',
    company: e.querySelector('[data-qa="chat-cell-subtitle"]')?.innerText?.trim() || '',
    preview: e.querySelector('[data-qa="chat-cell-last-message"]')?.innerText?.trim() || '',
    time: e.querySelector('[data-qa="chat-cell-creation-time"]')?.innerText?.trim() || '',
}))"""

# В списке чатов сегодняшние сообщения показаны временем «15:54», старые — датой
TODAY_RE = re.compile(r"^\d{1,2}:\d{2}$")

_JS_MESSAGES = """() => [...document.querySelectorAll('[data-qa^="chatik-chat-message-"]')]
    .filter(e => /^chatik-chat-message-\\d+$/.test(e.getAttribute('data-qa')))
    .map(e => {
        const body = e.querySelector('[data-qa="chat-bubble-text"]');
        return {
            id: e.getAttribute('data-qa').replace('chatik-chat-message-', ''),
            author: e.querySelector('[data-qa="chat-bubble-author-name"]')?.innerText?.trim() || '',
            text: body?.innerText?.replace(/\\n{3,}/g, '\\n\\n').trim() || '',
            hrefs: body ? [...body.querySelectorAll('a[href]')].map(a => a.href) : [],
        };
    })"""


async def _collect_chat_cells(page) -> list[dict]:
    """Список чатов с прокруткой (список подгружается при скролле)."""
    cells: dict[str, dict] = {}
    stale = 0
    for _ in range(40):
        before = len(cells)
        for cell in await page.evaluate(_JS_CHAT_CELLS):
            cells.setdefault(cell["id"], cell)
        if len(cells) >= CHATS_SCAN_LIMIT:
            break
        stale = stale + 1 if len(cells) == before else 0
        if stale >= 3:
            break
        last = page.locator('[data-qa^="chatik-open-chat-"]').last
        if not await last.count():
            break
        await last.scroll_into_view_if_needed()
        await last.hover()
        await page.mouse.wheel(0, 2000)
        await asyncio.sleep(1.5)
    return list(cells.values())[:CHATS_SCAN_LIMIT]


async def check_new_messages(session: BrowserSession, notify):
    """Обходит чаты: новые сообщения работодателя → уведомление, ссылки на формы → очередь."""
    print("Проверка чатов...")
    first_run = not has_any_chats()
    page = session.page
    await page.goto(CHAT_LIST_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_selector('[data-qa^="chatik-open-chat-"]', timeout=15000)
    except Exception:
        print("   Чатов не найдено (или не загрузились).")
        return
    await asyncio.sleep(2)

    cells = await _collect_chat_cells(page)
    changed = [c for c in cells if get_chat_preview(c["id"]) != c["preview"]]
    print(f"   Чатов: {len(cells)}, изменились: {len(changed)}")

    new_forms = 0
    chat_page = await session.new_page()
    try:
        for cell in changed:
            # Первый обход — без уведомлений. Незнакомый чат (новый или впервые
            # подгрузился в списке) — только последнее сообщение и только сегодняшнее,
            # чтобы не пересылать историю
            if first_run:
                mode = "none"
            elif get_chat_preview(cell["id"]) is None:
                mode = "last" if TODAY_RE.match(cell["time"]) else "none"
            else:
                mode = "all"
            try:
                new_forms += await _process_chat(chat_page, cell, notify, mode)
            except Exception as e:
                print(f"   ⚠️ Чат {cell['id']}: {e}")
                continue
            save_chat(cell["id"], cell["title"], cell["company"], cell["preview"])
            await asyncio.sleep(1)
    finally:
        await chat_page.close()

    if first_run and new_forms:
        await notify(f"📋 Первый обход чатов: найдено ссылок на анкеты — {new_forms}.")


async def _process_chat(page, cell: dict, notify, mode: str) -> int:
    """mode: none — не уведомлять, last — только последнее сообщение работодателя, all — все новые."""
    chat_id = cell["id"]
    await page.goto(f"https://hh.ru/chat/{chat_id}", wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_selector('[data-qa^="chatik-chat-message-"]', timeout=15000)
    except Exception:
        return 0
    await asyncio.sleep(1)

    vacancy_url = ""
    link = page.locator('[data-qa="chatik-header-vacancy-link"]').first
    if await link.count():
        vacancy_url = (await link.get_attribute("href") or "").split("?")[0]

    added = 0
    to_notify = []
    for msg in await page.evaluate(_JS_MESSAGES):
        msg_key = f"chat{chat_id}_{msg['id']}"
        if is_message_processed(msg_key):
            continue
        add_processed_message(msg_key, chat_id, msg["text"])

        for url, kind in extract_form_links(msg["text"], msg["hrefs"]):
            form_id = add_form(
                url, kind, chat_id, msg["id"], cell["title"], cell["company"],
                vacancy_url, msg["text"][:2000],
            )
            if form_id:
                added += 1
                print(f"   📋 Форма [{kind}] #{form_id}: {cell['title']} — {url}")

        # Сообщения работодателя подписаны автором, свои — нет
        if msg["author"]:
            to_notify.append(msg)

    if mode == "last":
        to_notify = to_notify[-1:]
    if mode != "none":
        for msg in to_notify:
            await notify(
                f"🔔 {cell['title']} ({cell['company']})\n"
                f"{msg['author']}: {msg['text'][:3000]}\n"
                f"https://hh.ru/chat/{chat_id}"
            )
    return added
