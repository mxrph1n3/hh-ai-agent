from config import STUDIO_SUMMARY, YANDEX_TIMELINE
from ai.analyzer import _ask_ollama

_FALLBACK = (
    "Здравствуйте. Студия дизайна интерьера. "
    "Можем сделать замер, планировку и дизайн-проект под вашу задачу. "
    f"Срок: {YANDEX_TIMELINE}."
)


async def is_order_suitable(title: str, description: str) -> bool:
    """Сомнение и сбой модели считаются отказом: откликов в день мало."""
    prompt = f"""оцени заказ для дизайн-студии интерьера. ответь одним словом: YES или NO.

студия:
{STUDIO_SUMMARY}

YES если заказ про:
- дизайн интерьера, дизайн-проект, планировку, 3d, комплектацию, авторский надзор
- ремонт квартиры или дома, отделку, перепланировку, если нужен дизайн или ведение ремонта

NO если это:
- сантехника, электрика, окна, кондиционеры отдельным заказом
- клининг, сборка мебели, авто, красота, юрист, репетитор, курьер, грузоперевозки
- коммерция не про жилой интерьер, если это явно не ремонт и не дизайн помещения

если сомневаешься — NO

заказ: {title}
описание: {description[:3500]}

ответ одним словом: YES или NO
"""
    try:
        answer = await _ask_ollama(prompt, "отвечай только YES или NO.")
    except Exception as e:
        print(f"   Ollama недоступна, заказ пропускаем: {e}")
        return False

    first = answer.upper().split()[0] if answer else ""
    if first.startswith("YES"):
        return True
    print(f"   ИИ: NO — {answer[:160]}")
    return False


async def generate_reply(title: str, description: str) -> str:
    prompt = f"""напиши короткий отклик дизайн-студии на заказ. 400-700 знаков.

правила:
- русский язык, обычные предложения, без списков и эмодзи
- не указывай телефон, почту, сайт, telegram, whatsapp и любые ссылки
- не выдумывай цены и метры, которых нет в заказе
- опиши, что студия возьмёт по этой задаче
- обязательно упомяни срок: {YANDEX_TIMELINE}
- в конце предложи уточнить площадь и что уже есть по планировке

студия:
{STUDIO_SUMMARY}

заказ: {title}
описание: {description[:2500]}
"""
    try:
        text = await _ask_ollama(
            prompt,
            "ты менеджер дизайн-студии. пишешь короткий отклик без контактов и ссылок.",
        )
        text = " ".join(text.split())
        if len(text) >= 80:
            return text
    except Exception as e:
        print(f"   Ollama не написала отклик: {e}")
    return _FALLBACK
