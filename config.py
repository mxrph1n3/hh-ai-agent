import os
from dotenv import load_dotenv

load_dotenv()

# Telegram (по умолчанию выключен)
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "false").lower() in ("1", "true", "yes")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TG_USER_ID = os.getenv("TG_USER_ID", "YOUR_USER_ID_HERE")
TG_PROXY = os.getenv("TG_PROXY", "").strip() or None

# Ollama
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", f"{OLLAMA_BASE}/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
# False — только фильтр по названию, без ИИ (если Ollama не установлена)
ENABLE_AI_FILTER = os.getenv("ENABLE_AI_FILTER", "true").lower() in ("1", "true", "yes")
# При ошибке Ollama: true = пропускать дальше, false = отклонять
AI_FAIL_OPEN = os.getenv("AI_FAIL_OPEN", "true").lower() in ("1", "true", "yes")

# --- Поиск на HH ---
SEARCH_QUERIES = [
    "Маркетолог",
]

TARGET_RESUME_NAME = "Маркетолог"

# Зарплата от 100 000 ₽, опыт 1–3 и 3–6 лет (у кандидата 3г 4м), удалёнка
HH_SEARCH_EXTRA = (
    "&experience=between1And3&experience=between3And6"
    "&salary=100000&currency_code=RUR"
)

# Только удалёнка, без area — вакансии remote по всему миру на hh.ru
SEARCH_CONFIGS = [
    {"name": "Удалёнка (весь мир)", "params": "&schedule=remote"},
]

# headless=False — HH стабильнее отдаёт выдачу в видимом браузере
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("1", "true", "yes")
# Прокси для браузера (пусто = без прокси, игнор системного)
# Пример: http://127.0.0.1:7890 или socks5://127.0.0.1:1080
BROWSER_PROXY = os.getenv("BROWSER_PROXY", "").strip() or None

# Пауза между циклами поиска (минуты)
LOOP_INTERVAL_MINUTES = int(os.getenv("LOOP_INTERVAL_MINUTES", "30"))

TITLE_ALLOW = [
    "маркетолог",
    "маркетинг",
    "marketing",
    "digital",
    "performance",
    "crm",
    "контекст",
    "таргет",
    "директ",
    "лидоген",
    "реклам",
    "growth",
    "acquisition",
]

TITLE_REJECT = [
    "стажёр", "стажер", "intern", "trainee", "стажировка",
    "начинающий", "без опыта", "с обучением", "18+",
    "junior", "джуниор", "ассистент маркетолога", "младший маркетолог",
    "бармен", "администратор", "охранник", "курьер", "водитель",
    "менеджер по продажам", "по продажам", "sales manager", "риелтор", "холодных звонков",
    "ассистент", "секретар", "рекрутер", "кадровое", "отдел кадров",
    "преподаватель", "учитель", "педагог",
    "бухгалтер", "юрист",
    "дизайнер", "designer", "рилсмейкер", "reels maker",
    "инфлюенс", "influencer", "блогер",
    # чистый SMM
    "smm", "смм", "smm-маркетолог", "smm маркетолог", "смм-маркетолог",
    "смм менеджер", "smm менеджер", "smm-менеджер", "смм-менеджер",
    "арбитраж", "сетап", "fb аккаунт", "facebook аккаунт",
    "крипт", "казино", "гембл", "betting",
    # маркетплейсы
    "маркетплейс", "маркетплейсы", "wildberries", "вайлдберриз", "вайлдберрис", "wb",
    "ozon", "озон",
    "продуктовый менеджер", "product manager", "оперативный директор",
    "senior", "сеньор",
    "трейд-маркет", "трейд-маркетолог", "trade marketing",
    "локальный маркетолог",
    "только офис", "офис обязателен",
]

MY_RESUME_SUMMARY = """
кулаков денис александрович performance и crm маркетолог head of growth.
москва. контакт: +7 958 8036198 d3sxmxrphine@gmail.com.
опыт: 3 года 4 месяца. образование: мгу ломоносова менеджмент 2029.
желаемая должность: маркетолог интернет маркетолог performance crm head of growth.
формат поиска агента: удаленка по всему миру. не готов к переезду и командировкам.

профиль:
ведущий crm и performance маркетолог. строю сквозную аналитику crm retention и платный трафик.
работаю с бюджетами до 5.5 млн руб в месяц. фокус на cpl cac ltv romi retention sql mql cjm rfm.
стек: яндекс директ рся telegram ads vk ads getcourse senler bitrix24 amocrm calltouch roistat
яндекс метрика google sheets unisender bothelp марквиз chatgpt claude.

кейсы:
1) академия системного бизнеса янв 2025 июл 2026 ведущий crm performance head of growth.
бюджет 3.5 5.5 млн руб в месяц.
построил crm и retention на getcourse senler bitrix24. rfm и когортный анализ базы 40000 плюс.
запустил 20 плюс каскадных сценариев email telegram whatsapp vk senler.
вел директ telegram ads vk ads. сквозная аналитика roistat bitrix24 метрика google sheets.
ltv плюс 45 процентов. конверсия регистрация в оплату с 3.4 до 8.1 процентов.
доля повторных продаж с 22 до 48 процентов плюс 14 млн руб выручки в квартал без роста бюджета.
cac минус 32 процента при росте трафика в 2 раза. romi 360 420 процентов.

2) промупак трейд ноя 2023 дек 2024 performance product маркетолог.
бюджет 1.2 2 млн руб в месяц.
яндекс директ поиск рся мастер кампаний авито яндекс карты 2гис.
сквозная аналитика calltouch amocrm метрика. 25 плюс custdev. 10 плюс квиз воронок марквиз. seo топ 5.
перевел с холодных звонков на поток заявок: с 20 до 280 плюс b2b заявок в месяц.
cpl минус 38 процентов с 2800 до 1730 руб. cr сайта с 1.2 до 4.4 процентов. romi 310 360 процентов.

3) студия декор сервис апр 2023 окт 2023 crm digital маркетолог.
crm рассылки unisender bothelp telegram. rfm сегментация базы 35000 плюс.
open rate с 12 до 25.8 процентов. ctr с 1.6 до 5.2 процентов.
реактивировал 13 процентов спящих клиентов плюс 2.1 млн руб выручки.
доля crm в обороте с 8 до 21 процентов. дрр crm 3.9 процента.

навыки: яндекс директ яндекс метрика vk ads telegram ads авито seo рся bitrix24 amocrm
crm маркетинг a b тесты лидогенерация b2b b2c сквозная аналитика unit экономика.

не интересны: стажировки junior чистый smm маркетплейсы wildberries ozon продажи арбитраж.
"""

# --- Яндекс Исполнители (дизайн-студия) ---
YANDEX_ORDERS_URL = os.getenv("YANDEX_ORDERS_URL", "https://uslugi.yandex.ru/orders")
YANDEX_DRY_RUN = os.getenv("YANDEX_DRY_RUN", "true").lower() in ("1", "true", "yes")
YANDEX_MAX_REPLIES = int(os.getenv("YANDEX_MAX_REPLIES", "7"))
YANDEX_MIN_BUDGET = int(os.getenv("YANDEX_MIN_BUDGET", "0"))
YANDEX_OFFER_PRICE = int(os.getenv("YANDEX_OFFER_PRICE", "0"))
YANDEX_CITY = os.getenv("YANDEX_CITY", "Москва")
YANDEX_TIMELINE = os.getenv(
    "YANDEX_TIMELINE",
    "замер в течение 2 дней, дизайн-проект от 2 недель",
)
# Короче, чем у HH: заказы на Яндексе разбирают быстро
YANDEX_LOOP_MINUTES = int(os.getenv("YANDEX_LOOP_MINUTES", "5"))

STUDIO_SUMMARY = """
мы дизайн-студия интерьера, не частный мастер. город: {city}.
откликаемся на все заказы про ремонт и интерьер: ремонт квартир и домов под ключ,
черновая и чистовая отделка, перепланировка, санузлы, дизайн интерьера, дизайн-проект,
планировка, 3d, комплектация, авторский надзор.
смежные работы внутри ремонта тоже берём: сантехника, электрика, окна, потолки, полы, плитка.
срок: {timeline}.
не берём заказы не про помещение: клининг, авто, красоту, юристов, репетиторов, курьеров, грузоперевозки.
берём только заказы за деньги. сотрудничество, бартер, бесплатная работа и работа за отзыв не подходят.
в отклике говорим только «мы» и «студия». нельзя указывать телефон, почту, сайт и мессенджеры.
""".format(city=YANDEX_CITY, timeline=YANDEX_TIMELINE)
