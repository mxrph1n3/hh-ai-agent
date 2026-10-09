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
    await page.evaluate(
        """() => {
            window.scrollTo(0, document.body.scrollHeight);
            document.querySelectorAll('main, [class*="scroll"], [class*="Scroll"], [class*="content"], [class*="Content"]').forEach((el) => {
                if (el.scrollHeight > el.clientHeight + 80) el.scrollTop = el.scrollHeight;
            });
        }"""
    )
    await asyncio.sleep(0.8)
    before = page.url
    target = await page.evaluate(
        r"""() => {
            document.querySelectorAll('[data-yandex-next]').forEach((el) => el.removeAttribute('data-yandex-next'));
            const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
            const pagerish = (el) => {
                let node = el;
                for (let i = 0; i < 6 && node; i++) {
                    const blob = ((node.className || '') + ' ' + (node.id || '') + ' ' + (node.getAttribute?.('data-qa') || '')).toString().toLowerCase();
                    if (/pager|pagination|pages|page-item|number-pages/.test(blob)) return true;
                    node = node.parentElement;
                }
                return false;
            };
            const pageNumber = (el) => {
                const text = clean(el.innerText || el.textContent || '');
                if (/^\d{1,2}$/.test(text)) return parseInt(text, 10);
                const aria = clean(el.getAttribute('aria-label') || '').toLowerCase();
                const match = aria.match(/(?:страница|page)\s*(\d{1,2})/);
                return match ? parseInt(match[1], 10) : NaN;
            };
            const nodes = [...document.querySelectorAll('a, button, [role="button"], [role="link"], span, div')];
            const pages = [];
            for (const el of nodes) {
                const n = pageNumber(el);
                if (!n || n > 40) continue;
                const tag = el.tagName;
                const clickable = tag === 'A' || tag === 'BUTTON' || el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link' || pagerish(el);
                if (!clickable) continue;
                pages.push({ el, n, href: el.href || el.getAttribute('href') || '' });
            }
            const leafs = pages.filter((p) => !pages.some((other) => other.el !== p.el && p.el.contains(other.el)));
            const debug = leafs.slice(0, 15).map((p) => `${p.n}:${p.el.tagName}`);
            const urlPage = parseInt(new URL(location.href).searchParams.get('page') || '', 10);
            const marked = document.querySelector('[aria-current="page"], [aria-current="true"]');
            let current = marked ? pageNumber(marked) : NaN;
            if (!current) {
                const active = leafs.find((p) => /current|active|selected/.test(((p.el.className || '') + ' ' + (p.el.getAttribute('aria-current') || '')).toString().toLowerCase()));
                if (active) current = active.n;
            }
            if (!current) current = urlPage > 0 ? urlPage : 1;
            const next = leafs.find((p) => p.n === current + 1);
            if (!next) return { debug, current };
            next.el.setAttribute('data-yandex-next', '1');
            return { href: next.href || '', label: String(next.n), debug, current };
        }"""
    )
    if not target or not target.get("label"):
        debug = (target or {}).get("debug") or []
        print(f"   Номера страниц не найдены: {', '.join(debug) or 'пусто'}")
        return False

    print(f"   Открываем страницу {target['label']}")
    href = target.get("href") or ""
    if href.startswith("/"):
        href = f"https://uslugi.yandex.ru{href}"
    if href and href.rstrip("/") != before.rstrip("/"):
        await page.goto(href, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(1.5)
        return True

    button = page.locator("[data-yandex-next='1']").first
    try:
        await button.scroll_into_view_if_needed(timeout=3000)
        await button.click(timeout=5000, force=True)
    except Exception:
        clicked = await page.evaluate(
            """() => {
                const el = document.querySelector("[data-yandex-next='1']");
                if (!el) return false;
                el.click();
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
