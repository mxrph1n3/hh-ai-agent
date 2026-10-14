import asyncio
from storage.db import is_message_processed, add_processed_message, is_form_prepared, add_form_draft
from hh.browser import BrowserSession
from hh.forms import extract_form_urls, fill_questionnaire


async def check_new_messages(session: BrowserSession, notify):
    await _scan_chats(session, notify, unread_only=True)


async def fill_chat_forms(session: BrowserSession, notify):
    """Все видимые чаты, не только непрочитанные. Вакансии не ищет."""
    await _scan_chats(session, notify, unread_only=False)


async def _scan_chats(session: BrowserSession, notify, unread_only: bool):
    print("Проверка сообщений от работодателей...")
    page = await session.new_page()
    try:
        await page.goto("https://hh.ru/applicant/negotiations", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        cards = page.locator('div[data-qa="negotiations-item"]')
        if unread_only:
            cards = cards.filter(has=page.locator('span[data-qa="negotiations-item-badge"]'))
        found = await cards.count()
        print(f"Чатов к проверке: {found}")

        for index in range(found):
            card = cards.nth(index)
            title_loc = card.locator('a[data-qa="negotiations-item-vacancy-link"]')
            title = await title_loc.inner_text() if await title_loc.is_visible() else "?"
            chat_link = await title_loc.get_attribute("href")
            if not chat_link:
                continue

            chat_page = await session.new_page()
            try:
                href = f"https://hh.ru{chat_link}" if chat_link.startswith("/") else chat_link
                await chat_page.goto(href)
                await asyncio.sleep(3)
                messages = await chat_page.locator('div[data-qa="chat-message-text"]').all()
                if not messages:
                    continue
                texts = [await item.inner_text() for item in messages]
                last_msg = texts[-1]
                msg_id = f"{chat_link}_{len(messages)}"
                fresh = not is_message_processed(msg_id)
                if fresh:
                    add_processed_message(msg_id, chat_link, last_msg)
                    await notify(
                        f"Новое сообщение: {title}\n\n{last_msg}\n"
                        f"https://hh.ru{chat_link}"
                    )
                blob = last_msg if unread_only else "\n".join(texts)
                await _open_forms(session, title, blob, notify)
            finally:
                await chat_page.close()
    finally:
        await page.close()


async def _open_forms(session: BrowserSession, title: str, message: str, notify):
    for url in extract_form_urls(message):
        if is_form_prepared(url):
            continue
        form_page = await session.new_page()
        try:
            status = await fill_questionnaire(form_page, url)
            add_form_draft(url, title, status)
            await notify(
                f"Анкета заполнена и не отправлена: {title}\n{url}\n"
                "Окно оставлено открытым. Перечитайте и отправьте сами."
            )
            print("Окно анкеты оставлено открытым. Отправка не нажата.")
        except Exception as e:
            print(f"Анкета не заполнена {url}: {e}")
            await form_page.close()
