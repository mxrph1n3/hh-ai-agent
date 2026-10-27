"""Извлечение схемы формы из DOM и заполнение по ней.

Работает по семантике страницы (label, aria-*, role), а не по классам,
поэтому один код покрывает Google Формы, Яндекс Формы и обычные HTML-формы.
Каждому полю JS ставит атрибут data-hhf="f<N>", вариантам — data-hhf-opt="f<N>:<k>",
дальше Playwright находит их по этим меткам.
"""
import re
from playwright.async_api import Page

TEXT_TYPES = ("text", "textarea", "email", "tel", "url", "number", "date", "time")

_JS_EXTRACT = r"""() => {
  const clean = t => (t || '').replace(/[ㅤ ]/g, ' ').replace(/\s+/g, ' ').trim();
  const REQ_RE = /\s*(\*|Обязательн(ое поле|ый вопрос)|Required( question)?)\s*/gi;
  const visible = el => {
    if (!el) return false;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const byIds = ids => ids.split(/\s+/).map(id => document.getElementById(id))
    .filter(Boolean).map(e => e.innerText).join(' ');

  document.querySelectorAll('[data-hhf],[data-hhf-opt],[data-hhf-in]').forEach(e => {
    e.removeAttribute('data-hhf'); e.removeAttribute('data-hhf-opt'); e.removeAttribute('data-hhf-in');
  });

  // Область поиска: форма с наибольшим числом полей, иначе вся страница
  const INPUTS = 'input,textarea,select,[role=radio],[role=checkbox],[role=listbox]';
  let scope = document.body, best = 0;
  document.querySelectorAll('form').forEach(f => {
    const n = f.querySelectorAll(INPUTS).length;
    if (n > best) { best = n; scope = f; }
  });

  // Сырой текст вопроса для элемента (с маркерами обязательности)
  const rawQuestion = el => {
    let t = '';
    const lb = el.getAttribute('aria-labelledby');
    if (lb) t = byIds(lb);
    if (!clean(t) && el.getAttribute('aria-label')) t = el.getAttribute('aria-label');
    if (!clean(t) && el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) t = l.innerText;
    }
    if (!clean(t)) { const lg = el.closest('fieldset')?.querySelector('legend'); if (lg) t = lg.innerText; }
    if (!clean(t)) {
      let p = el.parentElement;
      for (let i = 0; i < 7 && p && p !== scope.parentElement && !clean(t); i++, p = p.parentElement) {
        for (const h of p.querySelectorAll('[role=heading],h1,h2,h3,h4,h5,legend,label')) {
          if (!h.contains(el) && !el.contains(h) && clean(h.innerText)) { t = h.innerText; break; }
        }
      }
    }
    if (!clean(t)) t = el.getAttribute('placeholder') || el.getAttribute('name') || '';
    return t;
  };
  const question = el => {
    const raw = rawQuestion(el);
    const required = REQ_RE.test(raw) ||
      el.required || el.getAttribute('aria-required') === 'true' ||
      !!el.querySelector?.('[required],[aria-required=true]');
    REQ_RE.lastIndex = 0;
    // Подсказка к полю («Формат: +7911…») — через aria-describedby
    const db = el.getAttribute('aria-describedby');
    const hint = db ? clean(byIds(db)).slice(0, 300) : '';
    return { label: clean(raw.replace(REQ_RE, ' ')), required, hint };
  };
  const optionText = (el, clickable) => {
    const t = clean(
      el.getAttribute('aria-label') || el.getAttribute('data-answer-value') ||
      (clickable !== el ? clickable.innerText : '') || el.getAttribute('data-value') ||
      el.getAttribute('title') || el.value || ''
    );
    // «Другое» в Google Формах
    return t === '__other_option__' || /^(other|другое):?$/i.test(t) ? 'Другое' : t;
  };

  const fields = [];
  const nodes = {};
  const used = new Set();
  let n = 0;
  const add = (el, f) => {
    f.id = 'f' + (n++); el.setAttribute('data-hhf', f.id); nodes[f.id] = el; fields.push(f); return f;
  };

  // 1. Нативные radio/checkbox, сгруппированные по name (или по контейнеру)
  const groups = new Map();
  const boxIds = new Map();
  scope.querySelectorAll('input[type=radio],input[type=checkbox]').forEach(inp => {
    const box = inp.closest('[role=radiogroup],[role=group],fieldset') || inp;
    if (!boxIds.has(box)) boxIds.set(box, boxIds.size);
    const key = inp.type + '|' + (inp.name || 'box' + boxIds.get(box));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(inp);
  });
  for (const inputs of groups.values()) {
    const opts = inputs.map(inp => {
      const clickable = inp.closest('label') ||
        (inp.id && document.querySelector(`label[for="${CSS.escape(inp.id)}"]`)) || inp;
      return { inp, clickable };
    }).filter(o => visible(o.clickable));
    if (!opts.length) continue;
    const grouped = opts[0].inp.closest('[role=radiogroup],[role=group],fieldset');
    const box = grouped || opts[0].clickable.parentElement;
    let q;
    if (!grouped && opts.length === 1) {
      // Одиночная галочка (согласие и т.п.): вопрос — её же подпись, «*» стоит рядом
      const own = opts[0].clickable.innerText || '';
      const around = box.innerText || '';
      q = { label: clean(own).slice(0, 300), required: around.replace(own, '').includes('*'), hint: '' };
    } else {
      q = question(box);
    }
    if (opts.some(o => o.inp.required)) q.required = true;
    const f = add(box, {
      type: opts[0].inp.type, label: q.label, required: q.required, hint: q.hint || '',
      options: opts.map(o => optionText(o.inp, o.clickable)),
    });
    opts.forEach((o, k) => {
      o.clickable.setAttribute('data-hhf-opt', `${f.id}:${k}`);
      o.inp.setAttribute('data-hhf-in', `${f.id}:${k}`);
      used.add(o.inp);
    });
  }

  // 2. ARIA radio/checkbox без нативных input (Google Формы)
  const ariaGroups = new Map();
  scope.querySelectorAll('[role=radio],[role=checkbox]').forEach(el => {
    if (el.matches('input') || !visible(el)) return;
    // В Google Формах каждый вариант в своём listitem, поэтому сначала ищем саму группу
    const box = el.closest('[role=radiogroup],[role=group],[role=list]') ||
      el.closest('[role=listitem]') || el.parentElement;
    if (!ariaGroups.has(box)) ariaGroups.set(box, []);
    ariaGroups.get(box).push(el);
  });
  for (const [box, els] of ariaGroups) {
    const q = question(box);
    // Строка сетки (Google): у группы aria-label строки, вопрос — в заголовке выше
    const item = box.closest('[role=listitem]');
    const heading = item && clean(item.querySelector('[role=heading]')?.innerText || '').replace(REQ_RE, ' ');
    if (heading && box.getAttribute('aria-label') && !q.label.includes(clean(heading))) {
      q.label = clean(heading) + ': ' + q.label;
    }
    if (item?.querySelector('[aria-label*="Required"],[aria-label*="Обязательн"]')) q.required = true;
    const f = add(box, {
      type: els[0].getAttribute('role'), label: q.label, required: q.required, hint: q.hint || '',
      options: els.map(el => optionText(el, el)),
    });
    els.forEach((el, k) => {
      el.setAttribute('data-hhf-opt', `${f.id}:${k}`);
      el.setAttribute('data-hhf-in', `${f.id}:${k}`);
    });
  }

  // 3. Выпадающие списки: нативный select и ARIA listbox
  scope.querySelectorAll('select').forEach(sel => {
    if (!visible(sel)) return;
    const q = question(sel);
    add(sel, {
      type: 'select', label: q.label, required: q.required, hint: q.hint || '',
      options: [...sel.options].filter(o => o.value !== '').map(o => clean(o.text)),
    });
  });
  scope.querySelectorAll('[role=listbox]').forEach(lb => {
    if (lb.matches('select') || !visible(lb) || lb.parentElement.closest('[role=listbox]')) return;
    const q = question(lb);
    const item = lb.closest('[role=listitem]');
    if (item?.querySelector('[aria-label*="Required"],[aria-label*="Обязательн"]')) q.required = true;
    const opts = [...lb.querySelectorAll('[role=option]')]
      .map(o => clean(o.getAttribute('data-value') || o.innerText))
      .filter(t => t && !/^(выбрать|choose)$/i.test(t));
    add(lb, { type: 'listbox', label: q.label, required: q.required, hint: q.hint || '', options: [...new Set(opts)] });
  });

  // 4. Текстовые поля и файлы
  scope.querySelectorAll('input,textarea').forEach(el => {
    if (used.has(el) || el.matches('[type=radio],[type=checkbox]')) return;
    const type = el.tagName === 'TEXTAREA' ? 'textarea' : (el.getAttribute('type') || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image', 'password', 'search'].includes(type)) return;
    if (el.disabled || el.readOnly) return;
    if (type !== 'file' && !visible(el)) return;
    const q = question(el);
    const f = add(el, {
      type: type === 'datetime-local' ? 'text' : type, label: q.label, required: q.required, hint: q.hint || '',
      options: [],
    });
    if (el.maxLength > 0) f.max_length = el.maxLength;
  });

  // 5. Вопросы, у которых не нашлось поля (матрицы, нестандартные виджеты)
  const labels = fields.map(f => f.label);
  scope.querySelectorAll('[role=listitem] [role=heading], h3[id$="-label"]').forEach(h => {
    const raw = h.innerText || '';
    const label = clean(raw.replace(REQ_RE, ' '));
    REQ_RE.lastIndex = 0;
    if (!label || h.closest('[data-hhf],[data-hhf-opt]')) return;
    if (labels.some(l => l.includes(label) || label.startsWith(l))) return;
    if (!visible(h)) return;
    const id = 'f' + (n++);
    nodes[id] = h;
    fields.push({ id, type: 'unknown', label, required: REQ_RE.test(raw), options: [] });
    REQ_RE.lastIndex = 0;
  });

  // Порядок как на странице
  fields.sort((a, b) =>
    nodes[a.id].compareDocumentPosition(nodes[b.id]) & Node.DOCUMENT_POSITION_PRECEDING ? 1 : -1);

  const title = clean(document.querySelector('h1,[role=heading][aria-level="1"]')?.innerText || document.title);
  const descEl = scope.querySelector('h1 + *, [role=heading][aria-level="1"] + *');
  return {
    title,
    description: clean(descEl?.innerText || '').slice(0, 1500),
    fields,
    captcha: !!document.querySelector('iframe[src*="captcha"], iframe[src*="recaptcha"], .smart-captcha, [data-testid*="captcha"]'),
  };
}"""

NEXT_RE = re.compile(r"^\s*(далее|дальше|next|продолжить|следующ)", re.I)
SUBMIT_RE = re.compile(r"(отправить|submit|send|завершить|готово)", re.I)


async def prepare_page(page: Page):
    """Прокрутка вниз и обратно — подгружает ленивые блоки."""
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(400)
    except Exception:
        pass


OTHER_FIELD_RE = re.compile(r"^(other response|другой ответ|другое|свой вариант)$", re.I)


async def extract_form(page: Page) -> dict:
    """{title, description, fields: [{id, type, label, required, options}], captcha}."""
    info = await page.evaluate(_JS_EXTRACT)
    # Поле «свой вариант» относится к вопросу перед ним
    fields = info["fields"]
    for prev, field in zip(fields, fields[1:]):
        if field["type"] in TEXT_TYPES and OTHER_FIELD_RE.match(field["label"]):
            field["label"] = f"{prev['label']} — свой вариант (только если выбрано «Другое»)"
    return info


def _to_iso_date(value: str) -> str:
    m = re.match(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*$", value)
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else value


async def fill_field(page: Page, field: dict, value) -> str | None:
    """Вписывает значение. Возвращает текст ошибки или None."""
    fid, ftype = field["id"], field["type"]
    if value in (None, "", []):
        return None
    try:
        if ftype in TEXT_TYPES:
            text = str(value)
            if ftype == "date":
                text = _to_iso_date(text)
            await page.locator(f'[data-hhf="{fid}"]').fill(text, timeout=5000)
        elif ftype == "select":
            await page.locator(f'[data-hhf="{fid}"]').select_option(label=str(value), timeout=5000)
        elif ftype == "radio":
            idx = field["options"].index(value)
            await page.locator(f'[data-hhf-opt="{fid}:{idx}"]').click(timeout=5000)
        elif ftype == "checkbox":
            wanted = set(value if isinstance(value, list) else [value])
            for idx, opt in enumerate(field["options"]):
                checked = await page.evaluate(
                    """sel => { const e = document.querySelector(sel);
                        return !!e && (e.matches('input') ? e.checked : e.getAttribute('aria-checked') === 'true'); }""",
                    f'[data-hhf-in="{fid}:{idx}"]',
                )
                if (opt in wanted) != checked:
                    await page.locator(f'[data-hhf-opt="{fid}:{idx}"]').click(timeout=5000)
        elif ftype == "listbox":
            await page.locator(f'[data-hhf="{fid}"]').click(timeout=5000)
            await page.wait_for_timeout(600)
            option = page.locator('[role=option]:visible').filter(has_text=str(value)).first
            await option.click(timeout=5000)
            await page.wait_for_timeout(400)
        else:
            return f"тип поля {ftype} не поддерживается"
    except Exception as e:
        return str(e).splitlines()[0][:200]
    return None


async def find_nav_button(page: Page) -> tuple[str, object] | tuple[None, None]:
    """('next'|'submit', locator) — кнопка перехода/отправки формы."""
    candidates = page.locator('button, [role=button], input[type=submit]')
    found_submit = None
    for i in range(await candidates.count()):
        btn = candidates.nth(i)
        try:
            if not await btn.is_visible():
                continue
            text = (await btn.inner_text() or await btn.get_attribute("value") or
                    await btn.get_attribute("aria-label") or "").strip()
        except Exception:
            continue
        if NEXT_RE.search(text):
            return "next", btn
        if SUBMIT_RE.search(text) and found_submit is None:
            found_submit = btn
    if found_submit is not None:
        return "submit", found_submit
    return None, None


async def collect_errors(page: Page) -> list[str]:
    """Тексты ошибок валидации, видимые на странице."""
    try:
        return await page.evaluate("""() => [...new Set(
            [...document.querySelectorAll('[role=alert], [aria-live] , [aria-invalid=true] ~ *')]
              .filter(e => e.offsetParent !== null)
              .map(e => e.innerText.replace(/\\s+/g, ' ').trim())
              .filter(t => t && t.length < 200)
        )].slice(0, 10)""")
    except Exception:
        return []
