import asyncio
import re
from urllib.parse import quote_plus
from playwright.async_api import Page


def build_search_url(query: str, extra: str, params: str) -> str:
    return (
        f"https://hh.ru/search/vacancy?text={quote_plus(query)}"
        f"&order_by=publication_time{extra}{params}"
    )


async def collect_vacancy_links(page: Page) -> list[tuple[str, str]]:
    """Собирает (название, url) со страницы поиска."""
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded")

    for _ in range(3):
        await page.mouse.wheel(0, 800)
        await asyncio.sleep(0.8)

    try:
        await page.wait_for_selector('[data-qa="vacancy-serp__vacancy"]', timeout=10000)
    except Exception:
        pass
    await asyncio.sleep(1)

    seen: set[str] = set()
    links: list[tuple[str, str]] = []

    def add(job_id: str, title: str, href: str):
        if not job_id or job_id in seen or not title.strip():
            return
        seen.add(job_id)
        if href.startswith("/"):
            href = f"https://hh.ru{href}"
        links.append((title.strip(), href))

    cards = page.locator('[data-qa="vacancy-serp__vacancy"]')
    for i in range(await cards.count()):
        card = cards.nth(i)
        link = card.locator('a[data-qa="serp-item__title"], a[href*="/vacancy/"]').first
        if not await link.count():
            continue
        href = await link.get_attribute("href") or ""
        title = (await link.inner_text()).strip()
        if not title:
            title_el = card.locator('[data-qa="serp-item__title-text"]').first
            if await title_el.count():
                title = (await title_el.inner_text()).strip()
        if m := re.search(r"/vacancy/(\d+)", href):
            add(m.group(1), title, href)

    for sel in (
        'a[data-qa="serp-item__title"]',
        'a[data-qa="vacancy-serp__vacancy-title"]',
        'h3 a[href*="/vacancy/"]',
    ):
        loc = page.locator(sel)
        for i in range(await loc.count()):
            el = loc.nth(i)
            href = await el.get_attribute("href") or ""
            title = (await el.inner_text()).strip()
            if m := re.search(r"/vacancy/(\d+)", href):
                add(m.group(1), title, href)

    return links


async def _dismiss_overlays(page: Page):
    """Закрывает чат HH и sticky-оверлеи, которые перехватывают клики."""
    await page.evaluate(
        """() => {
            document.querySelectorAll('[data-qa="chatik-root"]').forEach(el => {
                el.style.display = 'none';
                el.style.pointerEvents = 'none';
            });
            document.querySelectorAll('iframe.chatik-integration-iframe').forEach(el => {
                el.style.display = 'none';
                el.style.pointerEvents = 'none';
            });
        }"""
    )
    for sel in (
        'button[aria-label*="акрыть"]',
        'button[data-qa*="close"]',
        '[data-qa="chatik"] button',
    ):
        btn = page.locator(sel).first
        try:
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=1000, force=True)
        except Exception:
            pass


async def has_next_page(page: Page) -> bool:
    btn = page.locator('a[data-qa="pager-next"]').first
    try:
        return await btn.count() > 0 and await btn.is_visible()
    except Exception:
        return False


async def go_next_page(page: Page):
    """Переход на следующую страницу без клика по перекрытому элементу."""
    await _dismiss_overlays(page)
    btn = page.locator('a[data-qa="pager-next"]').first
    href = await btn.get_attribute("href")
    if href:
        if href.startswith("/"):
            href = f"https://hh.ru{href}"
        await page.goto(href, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        return

    try:
        await btn.click(timeout=5000, force=True)
    except Exception:
        await btn.evaluate("el => el.click()")
    await asyncio.sleep(4)
