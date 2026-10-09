import asyncio
import hashlib
import re
from playwright.async_api import Page

_ORDER_HREF = re.compile(r"/orders?(?:/|\?|$)|orderId=|order_id=", re.I)


async def collect_orders(page: Page) -> list[dict]:
    """Карточки с ленты. Пустой список — страница без заказов или другая вёрстка."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(2)

    for _ in range(3):
        await page.mouse.wheel(0, 900)
        await asyncio.sleep(0.5)
        more = page.get_by_role("button", name=re.compile(r"показать ещё|ещё заказ", re.I)).first
        try:
            if await more.count() and await more.is_visible():
                await more.click(timeout=3000)
                await asyncio.sleep(1)
        except Exception:
            pass

    raw = await page.evaluate(
        """() => {
            const cards = [];
            const seen = new Set();
            const push = (href, title, preview) => {
                href = (href || '').split('#')[0];
                const key = href || title;
                if (!key || seen.has(key)) return;
                seen.add(key);
                cards.push({
                    href,
                    title: (title || '').trim().slice(0, 300),
                    preview: (preview || '').trim().slice(0, 800),
                });
            };

            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href || '';
                if (!/order/i.test(href)) continue;
                const card = a.closest('article, li, [class*="order"], [class*="Order"], [data-qa]') || a;
                const text = (card.innerText || a.innerText || '').trim();
                const title = text.split('\\n').map(s => s.trim()).filter(Boolean)[0] || a.innerText || '';
                push(href, title, text);
            }

            return {
                url: location.href,
                snippet: (document.body.innerText || '').slice(0, 1800),
                cards,
            };
        }"""
    )

    orders: list[dict] = []
    for card in raw.get("cards") or []:
        href = card.get("href") or ""
        if href and not _ORDER_HREF.search(href) and "/order" not in href.lower():
            continue
        title = (card.get("title") or "").strip()
        preview = (card.get("preview") or "").strip()
        if not title or title.lower() in {"заказы", "поиск заказов"}:
            continue
        orders.append({
            "id": _order_id(href, title),
            "title": title,
            "preview": preview or title,
            "url": href,
        })

    if not orders:
        print("Лента пустая или вёрстка не распознана.")
        print((raw.get("snippet") or "")[:900])
        try:
            await page.screenshot(path="yandex_feed.png", full_page=True)
            print("Скрин ленты: yandex_feed.png")
        except Exception:
            pass
    return orders


def _order_id(href: str, title: str) -> str:
    match = re.search(r"/(\d{4,})", href or "")
    if match:
        return match.group(1)
    digest = hashlib.sha1(f"{href}|{title}".encode()).hexdigest()[:16]
    return digest
