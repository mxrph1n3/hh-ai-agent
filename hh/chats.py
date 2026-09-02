import asyncio
from storage.db import is_message_processed, add_processed_message
from hh.browser import BrowserSession


async def check_new_messages(session: BrowserSession, notify):
    print("Проверка сообщений от работодателей...")
    page = session.page
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
            await chat_page.goto(f"https://hh.ru{chat_link}")
            await asyncio.sleep(3)
            messages = await chat_page.locator('div[data-qa="chat-message-text"]').all()
            if not messages:
                continue
            last_msg = await messages[-1].inner_text()
            msg_id = f"{chat_link}_{len(messages)}"
            if not is_message_processed(msg_id):
                add_processed_message(msg_id, chat_link, last_msg)
                await notify(
                    f"🔔 Новое сообщение: {title}\n\n{last_msg}\n"
                    f"https://hh.ru{chat_link}"
                )
        finally:
            await chat_page.close()
