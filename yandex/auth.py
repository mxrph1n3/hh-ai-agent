import asyncio
import re
from yandex.browser import BrowserSession


async def needs_login(page) -> bool:
    url = page.url or ""
    if "passport.yandex" in url:
        return True
    try:
        text = (await page.locator("body").inner_text())[:4000]
    except Exception:
        text = ""
    if "Зарегистрируйтесь как исполнитель" in text:
        return True
    login = page.get_by_role("link", name=re.compile(r"войти", re.I)).first
    try:
        if await login.count() and await login.is_visible():
            return True
    except Exception:
        pass
    button = page.get_by_role("button", name=re.compile(r"войти", re.I)).first
    try:
        if await button.count() and await button.is_visible():
            return True
    except Exception:
        pass
    return False


async def ensure_logged_in(session: BrowserSession, orders_url: str) -> bool:
    page = session.page
    print("Открываем ленту заказов Яндекс Исполнителей...")
    try:
        await page.goto(orders_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"❌ Не удалось открыть {orders_url}: {e}")
        return False

    if not await needs_login(page):
        print("Уже авторизованы.")
        await session.save_session()
        return True

    print("=" * 40)
    print("❗ НУЖНА АВТОРИЗАЦИЯ")
    print("1. Войдите в аккаунт исполнителя в открывшемся браузере")
    print("2. Дождитесь ленты заказов")
    print("3. Нажмите ENTER в этой консоли")
    print("=" * 40)
    try:
        await asyncio.to_thread(input, "👉 ENTER когда войдёте: ")
        await page.goto(orders_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        if await needs_login(page):
            print("❌ Вход не подтвердился. Откройте ленту заказов и запустите снова.")
            return False
        await session.save_session()
        print("✅ Сессия сохранена в state_yandex.json")
        return True
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return False
