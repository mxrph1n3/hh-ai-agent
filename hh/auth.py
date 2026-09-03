import os
import asyncio
from hh.browser import STATE_FILE, BrowserSession


async def ensure_logged_in(session: BrowserSession) -> bool:
    page = session.page
    print("Переходим на HH.ru для проверки авторизации...")
    try:
        await page.goto("https://hh.ru/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"❌ Не удалось открыть HH.ru: {e}")
        return False

    login_link = page.locator('a:has-text("Войти")')
    login_button = page.locator('button:has-text("Войти")')

    try:
        need_login = await login_link.count() > 0 or await login_button.count() > 0
    except Exception as e:
        print(f"❌ Ошибка проверки авторизации: {e}")
        return False

    if not need_login:
        print("Уже авторизованы.")
        return True

    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("❌ Сессия (state.json) недействительна — удалена.")

    print("=" * 40)
    print("❗ НУЖНА АВТОРИЗАЦИЯ")
    print("1. Войдите в HH.ru в открывшемся браузере")
    print("2. Нажмите ENTER в этой консоли")
    print("=" * 40)

    try:
        await asyncio.to_thread(input, "👉 ENTER когда войдёте: ")
        await asyncio.sleep(2)
        await session.save_session()
        print("✅ Сессия сохранена.")
        return True
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return False
