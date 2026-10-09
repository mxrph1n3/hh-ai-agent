import asyncio
import re
from playwright.async_api import Page

from config import YANDEX_DRY_RUN, YANDEX_TIMELINE
from yandex.text import sanitize_reply


async def send_reply(page: Page, comment: str, source_text: str) -> tuple[bool, str]:
    """Заполняет форму отклика. В dry-run не нажимает отправку.

    Возвращает (отправлено, описание цены).
    """
    comment = sanitize_reply(comment)
    if YANDEX_TIMELINE.lower() not in comment.lower():
        comment = sanitize_reply(f"{comment}\n\nСрок: {YANDEX_TIMELINE}.")

    opened = await _open_form(page)
    if await _looks_sent(page):
        print("   Сайт уже засчитал отклик на этом шаге")
        return True, "без цены"
    if not opened:
        print("   Кнопка «Откликнуться» не найдена")
        await _shot(page)
        return False, "без цены"

    filled = await _fill_comment(page, comment)
    if not filled:
        print("   Поле комментария не найдено")
        await _shot(page)
        return False, "без цены"

    print("   Цену не указываем")

    print(f"   Текст:\n{comment}")
    await _shot(page, "yandex_reply_preview.png")

    if YANDEX_DRY_RUN:
        print("   DRY RUN: отклик не отправлен")
        return False, "без цены"

    sent = await _submit(page)
    if sent:
        print("   Отклик отправлен")
    else:
        print("   Кнопка отправки не найдена")
        await _shot(page)
    return sent, "без цены"


async def _open_form(page: Page) -> bool:
    if await _comment_box(page) is not None:
        return True
    button = page.get_by_role("button", name=re.compile(r"откликнуться", re.I)).first
    link = page.get_by_role("link", name=re.compile(r"откликнуться", re.I)).first
    for target in (button, link):
        try:
            if await target.count() and await target.is_visible():
                await target.click(timeout=5000)
                await asyncio.sleep(1.2)
                return True
        except Exception:
            continue
    text_btn = page.locator("button, a").filter(has_text=re.compile(r"откликнуться", re.I)).first
    try:
        if await text_btn.count() and await text_btn.is_visible():
            await text_btn.click(timeout=5000)
            await asyncio.sleep(1.2)
            return True
    except Exception:
        pass
    return await _comment_box(page) is not None


async def _comment_box(page: Page):
    for sel in ("textarea", "[contenteditable='true']"):
        box = page.locator(sel).first
        try:
            if await box.count() and await box.is_visible():
                return box
        except Exception:
            continue
    return None


async def _fill_comment(page: Page, comment: str) -> bool:
    box = await _comment_box(page)
    if box is None:
        return False
    try:
        await box.fill(comment)
        return True
    except Exception:
        try:
            await box.click()
            await page.keyboard.insert_text(comment)
            return True
        except Exception:
            return False


async def _submit(page: Page) -> bool:
    for pattern in (r"отправить отклик", r"отправить", r"откликнуться"):
        button = page.get_by_role("button", name=re.compile(pattern, re.I)).last
        try:
            if await button.count() and await button.is_visible():
                await button.click(timeout=5000)
                await asyncio.sleep(2)
                return True
        except Exception:
            continue
    return False


async def _looks_sent(page: Page) -> bool:
    """Только явное подтверждение, не вкладка «Вы откликнулись» в меню."""
    loc = page.get_by_text("Отклик отправлен", exact=True).first
    try:
        return await loc.count() > 0 and await loc.is_visible()
    except Exception:
        return False


async def _shot(page: Page, path: str = "yandex_reply_preview.png") -> None:
    try:
        await page.screenshot(path=path)
    except Exception:
        pass


async def read_order_text(page: Page) -> str:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(1.5)
    try:
        text = await page.locator("body").inner_text()
    except Exception:
        return ""
    return text.replace("\u00a0", " ").strip()[:5000]
