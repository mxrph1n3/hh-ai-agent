import aiohttp
from config import OLLAMA_URL, OLLAMA_MODEL, MY_RESUME_SUMMARY

LETTER = """Добрый день.
Более 3 лет управляю перформанс маркетингом, сквозной аналитикой и юнит экономикой. связываю рекламные каналы с crm системами, отвечаю за romi, cpl и cac, выстраиваю воронки привлечения и удержания клиентов. Активно задействую искусственный интеллект для ускорения гипотез и работы с контентом.

Основные результаты в цифрах: b2b лидогенерация: выстроил поток заявок с 20 до 280 в месяц, снизил cpl на 38 процентов до 1730 рублей, romi составил 310-360 процентов при бюджете 2 миллиона рублей в месяц.
Edtech и подписки: связал mindbox, getcourse и roistat в единую систему, поднял конверсию в оплату с 3.4 до 8.1 процента, удержание retention rate с 22 до 48 процентов, реактивация базы принесла 14 миллионов рублей за квартал. e-commerce и crm: оцифровал базу на 35000 контактов, вырастил долю crm в выручке с 8 до 21 процента, реактивация клиентов принесла 2.1 миллиона рублей.

Готов разобрать задачи вашего проекта, предложить гипотезы роста и выстроить понятную систему маркетинга под задачи бизнеса."""


async def generate_cover_letter(vacancy_title: str, vacancy_description: str) -> str:
    """Одно письмо по фиксированному шаблону."""
    return LETTER


async def is_vacancy_suitable(vacancy_title: str, vacancy_description: str) -> bool:
    prompt = f"""оцени подходит ли вакансия кандидату. ответь одним словом: YES или NO.

профиль:
{MY_RESUME_SUMMARY}

подходит YES если это:
- интернет digital performance crm маркетолог head of growth
- маркетолог с упором на трафик директ таргет лиды crm retention аналитику воронки
- руководитель маркетинга cmo head of marketing при требованиях до 3 4 лет
- удаленка remote hybrid
- зарплата от примерно 100к руб если указана сильно ниже 80к то NO

не подходит NO если:
- стажировка junior с обучением без опыта ассистент
- любая вакансия smm смм контент рилсы
- маркетплейсы wildberries wb ozon озон трейд маркетинг офлайн horeca
- продажи холодные звонки
- арбитраж гемблинг крипта
- дизайн hr админ не маркетинг
- product manager без маркетинга
- оперативный директор
- только офис без удаленки
- жестко требуют 5 плюс лет опыта или senior как жёсткий грейд без гибкости

вакансия: {vacancy_title}
описание: {vacancy_description[:3500]}

ответ одним словом: YES или NO
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": "отвечай только YES или NO.",
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()
                answer = data.get("response", "").strip().upper()
                first = answer.split()[0] if answer else ""
                if first.startswith("YES"):
                    return True
                if first.startswith("NO"):
                    return False
                return answer.startswith("YES")
    except Exception as e:
        print(f"ошибка ollama анализ: {e}")
        return False
