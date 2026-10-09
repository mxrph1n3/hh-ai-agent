import asyncio
import hashlib
import re
from urllib.parse import parse_qs, urlparse
from playwright.async_api import Page

_ORDER_ID_IN_PATH = re.compile(r"/orders?/\d+", re.I)


async def collect_orders(page: Page) -> list[dict]:
    """Карточки с ленты. Пустой список — страница без заказов или другая вёрстка."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(2)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(0.8)

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
        if not _is_order_link(href):
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


def _is_order_link(href: str) -> bool:
    """Ссылка на заказ, а не на страницу ленты и не на номер пагинации."""
    if not href:
        return False
    lowered = href.lower()
    if "orderid=" in lowered or "order_id=" in lowered:
        return True
    path = urlparse(href).path.rstrip("/")
    if _ORDER_ID_IN_PATH.search(path):
        return True
    if "/order/" in path and not path.endswith("/orders"):
        query = parse_qs(urlparse(href).query)
        if "page" in query and path.endswith("/orders"):
            return False
        return True
    return False


async def go_next_feed_page(page: Page) -> bool:
    """Открывает следующую страницу ленты. False — страниц больше нет."""
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(0.6)
    before = page.url
    target = await page.evaluate(
        """() => {
            const textOf = (el) => ((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || ''))
                .replace(/\\s+/g, ' ').trim().toLowerCase();
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            const nodes = [...document.querySelectorAll('a[href], button')].filter(visible);
            const labeled = nodes.find((el) => /следующ|дальше|вперёд|вперед|показать ещё|показать еще/.test(textOf(el)));
            if (labeled) {
                const disabled = labeled.getAttribute('aria-disabled') === 'true' || labeled.hasAttribute('disabled');
                return { href: labeled.href || labeled.getAttribute('href') || '', disabled };
            }
            const currentEl = document.querySelector('[aria-current="page"], [aria-current="true"]');
            const current = currentEl ? parseInt((currentEl.innerText || '').trim(), 10) : NaN;
            if (current) {
                const link = nodes.find((el) => (el.innerText || '').trim() === String(current + 1) && el.href);
                if (link) return { href: link.href, disabled: false };
            }
            return null;
        }"""
    )
    if not target or target.get("disabled"):
        return False

    href = target.get("href") or ""
    if href.startswith("/"):
        href = f"https://uslugi.yandex.ru{href}"
    if href and href != before:
        await page.goto(href, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(1.5)
        return page.url.rstrip("/") != before.rstrip("/")

    clicked = await page.evaluate(
        """() => {
            const textOf = (el) => ((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || ''))
                .replace(/\\s+/g, ' ').trim().toLowerCase();
            const nodes = [...document.querySelectorAll('a, button')];
            const labeled = nodes.find((el) => /следующ|дальше|показать ещё|показать еще/.test(textOf(el)));
            if (!labeled) return false;
            labeled.click();
            return true;
        }"""
    )
    if not clicked:
        return False
    await asyncio.sleep(1.5)
    return True


def _order_id(href: str, title: str) -> str:
    match = re.search(r"/(\d{4,})", href or "")
    if match:
        return match.group(1)
    digest = hashlib.sha1(f"{href}|{title}".encode()).hexdigest()[:16]
    return digest
