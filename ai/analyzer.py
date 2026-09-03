import aiohttp
from config import OLLAMA_BASE, OLLAMA_MODEL, MY_RESUME_SUMMARY, AI_FAIL_OPEN

LETTER = """Добрый день.
Более 3 лет управляю перформанс маркетингом, сквозной аналитикой и юнит экономикой. связываю рекламные каналы с crm системами, отвечаю за romi, cpl и cac, выстраиваю воронки привлечения и удержания клиентов. Активно задействую искусственный интеллект для ускорения гипотез и работы с контентом.

Основные результаты в цифрах: b2b лидогенерация: выстроил поток заявок с 20 до 280 в месяц, снизил cpl на 38 процентов до 1730 рублей, romi составил 310-360 процентов при бюджете 2 миллиона рублей в месяц.
Edtech и подписки: связал mindbox, getcourse и roistat в единую систему, поднял конверсию в оплату с 3.4 до 8.1 процента, удержание retention rate с 22 до 48 процентов, реактивация базы принесла 14 миллионов рублей за квартал. e-commerce и crm: оцифровал базу на 35000 контактов, вырастил долю crm в выручке с 8 до 21 процента, реактивация клиентов принесла 2.1 миллиона рублей.

Готов разобрать задачи вашего проекта, предложить гипотезы роста и выстроить понятную систему маркетинга под задачи бизнеса."""


async def generate_cover_letter(vacancy_title: str, vacancy_description: str) -> str:
    """Одно письмо по фиксированному шаблону."""
    return LETTER


def _parse_answer(data: dict) -> str:
    if msg := data.get("message"):
        return str(msg.get("content", "")).strip()
    return str(data.get("response", "")).strip()


def _parse_bool(answer: str) -> bool | None:
    upper = answer.upper()
    first = upper.split()[0] if upper else ""
    if first.startswith("YES"):
        return True
    if first.startswith("NO"):
        return False
    return None


async def check_ollama() -> bool:
    """Проверяет, что Ollama запущена и модель скачана."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OLLAMA_BASE}/api/tags", timeout=5) as response:
                if response.status != 200:
                    print(f"⚠️ Ollama: /api/tags вернул {response.status}")
                    return False
                data = await response.json()
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                if OLLAMA_MODEL.split(":")[0] not in models:
                    print(f"⚠️ Модель «{OLLAMA_MODEL}» не найдена. Установите: ollama pull {OLLAMA_MODEL}")
                    print(f"   Доступные модели: {', '.join(models) or 'нет'}")
                    return False
                print(f"Ollama ok, модель: {OLLAMA_MODEL}")
                return True
    except Exception as e:
        print(f"⚠️ Ollama не запущена ({OLLAMA_BASE}): {e}")
        print("   Установите с https://ollama.com и выполните: ollama pull llama3")
        print("   Или в .env: ENABLE_AI_FILTER=false")
        return False


async def _ask_ollama(prompt: str, system: str) -> str:
    chat_payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    generate_payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    async with aiohttp.ClientSession() as session:
        for url, payload in (
            (f"{OLLAMA_BASE}/api/chat", chat_payload),
            (f"{OLLAMA_BASE}/api/generate", generate_payload),
        ):
            try:
                async with session.post(url, json=payload, timeout=60) as response:
                    if response.status == 404:
                        continue
                    response.raise_for_status()
                    return _parse_answer(await response.json())
            except aiohttp.ClientResponseError:
                continue
    raise ConnectionError(f"Ollama не отвечает на {OLLAMA_BASE}/api/chat или /api/generate")


async def is_vacancy_suitable(vacancy_title: str, vacancy_description: str) -> bool:
    prompt = f"""оцени подходит ли вакансия кандидату. ответь одним словом: YES или NO.

профиль:
{MY_RESUME_SUMMARY}

подходит YES если это:
- интернет digital performance crm маркетолог head of growth
- маркетолог с упором на трафик директ таргет лиды crm retention аналитику воронки
- руководитель маркетинга cmo head of marketing
- зарплата явно ниже 60000 руб без бонусов

не подходит NO если:
- стажировка junior с обучением без опыта ассистент
- чистый smm смм контент рилсы без performance
- маркетплейсы wildberries ozon как основная задача
- продажи холодные звонки без маркетинга
- арбитраж гемблинг крипта
- дизайн hr админ не маркетинг
- product manager без маркетинга
- оперативный директор

если сомневаешься между YES и NO — ответь YES

вакансия: {vacancy_title}
описание: {vacancy_description[:3500]}

ответ одним словом: YES или NO
"""

    try:
        answer = await _ask_ollama(prompt, "отвечай только YES или NO.")
        verdict = _parse_bool(answer)
        if verdict is True:
            return True
        if verdict is False:
            print(f"   ИИ: NO — {answer[:120]}")
            return False
        print(f"   ИИ: неясный ответ «{answer[:120]}» — {'пропускаем' if AI_FAIL_OPEN else 'отклоняем'}")
        return AI_FAIL_OPEN
    except Exception as e:
        print(f"⚠️ Ollama недоступна: {e}")
        if AI_FAIL_OPEN:
            print("   Пропускаем ИИ-фильтр, ориентируемся только на название.")
            return True
        return False
