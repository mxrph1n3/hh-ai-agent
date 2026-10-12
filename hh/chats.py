import asyncio
from storage.db import is_message_processed, add_processed_message, is_form_prepared, add_form_draft
from hh.browser import BrowserSession
from hh.forms import extract_form_urls, fill_questionnaire


async def check_new_messages(session: BrowserSession, notify):
    print("Проверка сообщений от работодателей...")
    page = await session.new_page()
    try:
        await page.goto("https://hh.ru/applicant/negotiations", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        cards = await page.locator('div[data-qa="negotiations-item"]').filter(
            has=page.locator('span[data-qa="negotiations-item-badge"]')
        ).all()

        for card in cards:
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
                last_msg = await messages[-1].inner_text()
                msg_id = f"{chat_link}_{len(messages)}"
                if is_message_processed(msg_id):
                    continue
                add_processed_message(msg_id, chat_link, last_msg)
                await notify(
                    f"Новое сообщение: {title}\n\n{last_msg}\n"
                    f"https://hh.ru{chat_link}"
                )
                await _open_forms(session, title, last_msg, notify)
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
