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
        items = await page.evaluate(
            """() => {
                const cards = [...document.querySelectorAll('[data-qa="negotiations-item"]')];
                return cards.map((card) => {
                    const links = [...card.querySelectorAll('a[href]')].map((a) => ({
                        href: a.getAttribute('href') || '',
                        text: (a.innerText || '').trim().slice(0, 200),
                    }));
                    const preferred = links.find((item) => /negotiation|topic|chat/i.test(item.href))
                        || links.find((item) => /vacancy/i.test(item.href))
                        || links[0]
                        || { href: '', text: '' };
                    return { title: preferred.text || '?', href: preferred.href, links: links.slice(0, 6) };
                });
            }"""
        )
        if items and not any(item.get("href") for item in items):
            print("В карточках нет ссылок. Первая карточка:")
            print(items[0])
            await page.screenshot(path="negotiations.png")
            print("Скрин: negotiations.png")

        for item in items:
            title = item.get("title") or "?"
            chat_link = item.get("href") or ""
            if not chat_link:
                print(f"Пропуск без ссылки: {title}")
                continue

            chat_page = await session.new_page()
            try:
                href = f"https://hh.ru{chat_link}" if chat_link.startswith("/") else chat_link
                print(f"Чат: {title}")
                await chat_page.goto(href, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2)
                messages = chat_page.locator(
                    'div[data-qa="chat-message-text"], [data-qa*="chat-message"], [data-qa*="message-text"]'
                )
                count = await messages.count()
                if count == 0:
                    print(f"   Сообщений не видно: {title}")
                    continue
                texts = []
                for msg_index in range(count):
                    try:
                        texts.append(await messages.nth(msg_index).inner_text(timeout=3000))
                    except Exception:
                        continue
                if not texts:
                    continue
                last_msg = texts[-1]
                msg_id = f"{chat_link}_{len(texts)}"
                fresh = not is_message_processed(msg_id)
                if fresh:
                    add_processed_message(msg_id, chat_link, last_msg)
                    await notify(
                        f"Новое сообщение: {title}\n\n{last_msg}\n"
                        f"https://hh.ru{chat_link}"
                    )
                blob = last_msg if unread_only else "\n".join(texts)
                await _open_forms(session, title, blob, notify)
            except Exception as e:
                print(f"Чат не открылся [{title}]: {e}")
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
