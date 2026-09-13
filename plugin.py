"""KiriillBR AI — AI-заместитель продавца FunPay Cardinal."""
from __future__ import annotations
import ast, base64, difflib, hashlib, json, logging, os, re, shutil, sys, threading, time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any
import requests
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, CallbackQuery, Message
from FunPayAPI.common.enums import MessageTypes
from FunPayAPI.types import BuyerViewing
from tg_bot import CBT, utils
from tg_bot.static_keyboards import CLEAR_STATE_BTN
if TYPE_CHECKING:
    from cardinal import Cardinal
    from FunPayAPI.updater.events import NewMessageEvent

logger = logging.getLogger("FPC.KiriillBRAI")
NAME = "KiriillBR AI 🤖"
VERSION = "4.8.0"
DESCRIPTION = "AI-помощник продавца FunPay. Vision-факты лотов, web-поиск, ЧС+WL, меню по разделам."
CREDITS = "@qneiz"
UUID = "7b93d4e1-6a2c-4f8b-9c73-5e10d8a6f214"
SETTINGS_PAGE = True
PUBLISHER_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/silnikovkirill04-web/KiriillBR-AI/main/manifest.json"
UPDATE_MANIFEST_SCHEMA = 1
UPDATE_MAX_BYTES = 3 * 1024 * 1024
UPDATE_USER_AGENT = f"KiriillBRAI/{VERSION} ({UUID})"
CFG_PATH = "storage/plugins/kiriillbr_ai.json"
ORDERS_PATH = "storage/plugins/kiriillbr_orders.json"
HISTORY_PATH = "storage/plugins/kiriillbr_history.json"
BUYER_COUNT_PATH = "storage/plugins/kiriillbr_buyer_count.json"
LOT_VISION_PATH = "storage/plugins/kiriillbr_lot_vision.json"
CB = "KBAI"
ST_MODEL, ST_PROMPT, ST_SELLER = f"{CB}_model", f"{CB}_prompt", f"{CB}_seller"
ST_URL, ST_KEY, ST_TIMEOUT, ST_BUDGET = f"{CB}_url", f"{CB}_key", f"{CB}_timeout", f"{CB}_budget"
ST_WM_TEXT, ST_NOTIFY_COOLDOWN = f"{CB}_wmtext", f"{CB}_cooldown"
ST_UPD_INT = f"{CB}_updint"
ST_TEST_PHOTO = f"{CB}_testphoto"
ST_SURVEY_TEXT = f"{CB}_surveytext"
ST_AF_DELAY = f"{CB}_afdelay"
ST_THANK_TEXT = f"{CB}_thanktext"
ST_BLACKLIST = f"{CB}_blacklist"
ST_WHITELIST = f"{CB}_wl"
ST_ROLE_CHAT = f"{CB}_rolechat"
ST_LOT_INSTR = f"{CB}_lotinstr"
ST_LOT_INSTR_DEL = f"{CB}_lotinstrdel"
ST_LOT_ITEM = f"{CB}_lotitem"
ST_LOT_ITEM_DEL = f"{CB}_lotitemdel"

_VISION_MAX_BYTES = 4 * 1024 * 1024
_VISION_ALLOWED_MIME = ("image/jpeg", "image/png", "image/webp", "image/gif")
_WEB_SEARCH_TIMEOUT = (6, 15)
_WEB_SEARCH_MAX_BYTES = 512 * 1024

_VISION_PROMPT = (
    "Ты — строгий модератор контента и AI-заместитель продавца FunPay. Покупатель прислал фото.\n\n"
    "★★★★★ ТЕБЕ ЗАПРЕЩЕНО ОТКАЗЫВАТЬСЯ ОПИСЫВАТЬ ФОТО ★★★★★\n"
    "Ты НЕ отказываешься. Ты ВСЕГДА ставишь метку и описываешь фото.\n\n"
    "ЗАПРЕЩЁННЫЕ ФРАЗЫ: «я не могу помочь», «не могу описать», «недопустимый контент», "
    "«нарушает правила», «не могу анализировать», «извините, я не могу».\n\n"
    "ПРОВЕРКА 1 — OCR: прочитай ВСЁ на фото. Если есть МАТ/ОСКОРБЛЕНИЯ/18+ — начни с [[TEXT_NSFW]].\n"
    "ПРОВЕРКА 2 — ФОРМЫ: если похоже на половые органы — [[ANATOMY_NSFW]].\n"
    "ПРОВЕРКА 3 — NSFW/SHOCK/SCAT/TRASH — по смыслу.\n"
    "ФОРМАТ: одна метка в начале (если надо), потом описание 2-5 предложений по-русски. "
    "Если есть текст (чек, скрин, номер заказа, сумма) — перечисли дословно."
)

_VISION_LOT_PROMPT = (
    "Ты — OCR-ассистент. На изображении — скриншот из лота FunPay (игровой аккаунт/товар).\n\n"
    "ТВОЯ ЗАДАЧА: извлечь ВСЕ видимые ФАКТЫ о товаре. СТРОГО ПО ФАКТУ, без домыслов.\n\n"
    "Что искать на скрине:\n"
    "- Уровень аккаунта (число рядом с аватаром/профилем, часто в углу).\n"
    "- Никнейм, тег, ID.\n"
    "- Ранг, дивизион, звание.\n"
    "- Игровая валюта: золото, монеты, гемы, голда (число + название).\n"
    "- Игры/приложения на скрине (Steam, Standoff, CS, Roblox и т.п.).\n"
    "- Наличие калибровки/званий в шутерах.\n"
    "- Инвентарь, скины, предметы (перечисли по названиям).\n"
    "- Даты регистрации, сроки банов, VAC-статусы.\n"
    "- Любые другие числа и подписи, важные для товара.\n\n"
    "ФОРМАТ ОТВЕТА: короткий список по строкам, по одному факту на строку. "
    "Пример:\n"
    "• Уровень: 31\n"
    "• Золото: 0.20\n"
    "• Игра: Standoff 2\n"
    "• Калибровка: не пройдена\n\n"
    "ПРАВИЛА:\n"
    "- Если факт НЕ виден на скрине — НЕ пиши его вообще.\n"
    "- НЕ ПРИДУМЫВАЙ уровни, ранги, суммы.\n"
    "- Если это не скриншот игры — напиши «не игровой скрин».\n"
    "- Без вступлений, без эмодзи, только список фактов."
)

DEFAULT_PROMPT = (
    "Ты — AI-помощник продавца на FunPay. Отвечай кратко, по-русски, 1-3 предложения.\n\n"
    "СТИЛЬ:\n"
    "- Пиши живо, как обычный продавец в чате.\n"
    "- НЕ используй формулу «Чтобы купить 1 шт., оформите заказ на FunPay».\n"
    "- На «я возьму 1 штуку» отвечай «Да, оформляйте 👍».\n"
    "- На «куплю» / «беру» — «Отлично! Оформляйте 😊».\n"
    "- КОРОТКО: 1-3 предложения без длинных нравоучений.\n\n"
    "★ ЗАПРЕЩЁННЫЕ ФРАЗЫ (использовать НИКОГДА) ★\n"
    "- «я помогу», «мы поможем», «постараюсь помочь», «мы решим», «решу ваш вопрос»;\n"
    "- «продавец свяжется», «продавец подключится», «продавец ответит»;\n"
    "- «я передам продавцу», «передам ваш запрос», «сообщу продавцу»;\n"
    "- «уточню у продавца», «свяжусь с продавцом», «позову продавца».\n"
    "Вместо этого — просто отвечай по существу или нейтрально: «Не могу подтвердить это по лоту.»\n\n"
    "ЭМОДЗИ: 1-2 на сообщение по смыслу (💰 📦 ✅ 🤝 😊 ⚠️), кроме проблемных тем.\n\n"
    "СТАТУСЫ ЗАКАЗОВ:\n"
    "- paid → «Да, заказ #XXX оплачен, спасибо! 💰»\n"
    "- confirmed → «Заказ #XXX подтверждён и закрыт ✅»\n"
    "- refunded → «Заказ #XXX возвращён, деньги вернулись покупателю 💸»\n"
    "- Статус ТОЛЬКО к указанному номеру.\n\n"
    "ЗАПРЕЩЕНО:\n"
    "- НЕ оформляй заказы. НЕ пиши «Заказ оформлен», «Я оформлю заказ».\n"
    "- НЕ пиши «измените количество в лоте».\n"
    "- НЕ пиши «Оформление заказа происходит на стороне FunPay».\n"
    "- НЕ предлагай «перейти к оплате».\n\n"
    "ЧТО ДЕЛАЕШЬ:\n"
    "- отвечаешь по товару, лоту, цене, наличию, срокам, доставке, автовыдаче;\n"
    "- отвечаешь по оплате, статусу, отзывам, скидке;\n"
    "- РАЗБИРАЕШЬ ФОТО, СКРИНШОТЫ, ЧЕКИ.\n\n"
    "★ ФОТО РАЗРЕШЕНО ★\n"
    "- «А если я скину фото — скажете что на нём?» — «Да, конечно! Отправляйте — посмотрю 📸»\n"
    "- ЗАПРЕЩЕНО: «не могу помочь с фото», «не умею смотреть фото», «отправляйте текстом».\n"
    "- Фото пришло — опиши 2-5 предложений. Текст/чек/номер/сумма — дословно.\n\n"
    "★ ПОИСК В ОТКРЫТЫХ ИСТОЧНИКАХ ★\n"
    "Если покупатель спрашивает что-то о САМОЙ ИГРЕ / ПЛАТФОРМЕ / ПРАВИЛАХ, чего нет в "
    "ТЕКУЩИЙ ТОВАР / ИНСТРУКЦИЯ / ПОДКЛЮЧЁННЫЕ ТОВАРЫ (например: «смогу ли я играть с другом "
    "на этом аккаунте?», «подходит ли для Steam?», «есть ли бан?», «какие системные требования?»), "
    "И ЭТО НЕ ФАКТ О ЛОТЕ, А ОБЩИЙ ФАКТ ОБ ИГРЕ/ПЛАТФОРМЕ — поставь В КОНЦЕ ответа маркер:\n"
    "[[SEARCH: короткий поисковый запрос]]\n"
    "Примеры: [[SEARCH: Standoff 2 аккаунт второго уровня можно ли играть с другом]]\n"
    "Не используй [[SEARCH]] если ответ есть в ТЕКУЩИЙ ТОВАР / ИНСТРУКЦИЯ / ПОДКЛЮЧЁННЫЕ ТОВАРЫ.\n"
    "Не используй [[SEARCH]] для оплаты/заказа/статуса.\n\n"
    "ПРО СЛОЖНЫЕ: «Этот вопрос лучше уточнить в чате продавца.» — БЕЗ обещаний передать/связать.\n"
    "ПАМЯТЬ: видишь всю историю чата. Не здоровайся повторно.\n"
    "ПРАВИЛА: не раскрывай баланс, пароли, токены, cookies, контакты, реквизиты."
)

BUYER_ROLE_PROMPT = (
    "Ты — AI-помощник ПОКУПАТЕЛЯ на FunPay. Владелец этого бота — ПОКУПАТЕЛЬ, собеседник — ПРОДАВЕЦ.\n\n"
    "ТЫ НЕ продавец. НИКОГДА не говори от имени продавца.\n"
    "НЕ подтверждаешь оплату, НЕ обещаешь выдачу, НЕ выдаёшь товар.\n"
    "НЕ обещаешь: «я помогу», «мы решим», «продавец свяжется».\n"
    "НЕ выдумываешь цены, наличие, сроки, гарантии.\n"
    "Помогаешь формулировать вопросы продавцу и пояснять его ответы.\n\n"
    "СТИЛЬ: кратко, 1-3 предложения, живо, эмодзи 1-2.\n"
    "ЗАПРЕЩЕНО: обещать товар/оплату/скидку; писать «заказ оплачен»; оформлять заказы; "
    "передавать контакты и ссылки (кроме funpay.com)."
)

FUNPAY_RULES_SNAPSHOT = """ПРАВИЛА FUNPAY:
[1.1] Не передавай и не запрашивай контакты.
[1.2] Не предлагай накрутку/шантаж/изменение отзыва.
[1.3] Не разглашай имя/ID/сумму заказа с целью вреда.
[1.4] НЕ помогай покупать/продавать аккаунт FunPay.
[1.7-1.8] Не оскорбляй, не угрожай, не спамь.
[1.9] Не рекламируй сторонние ресурсы.
[1.10] Не мошенничай.
[1.11] Не помогай с обменом денег, кардингом.
[1.12] Не давай ссылки на файлообменники без необходимости.
[2.1.1] НИКОГДА не соглашайся передать товар без оплаты через FunPay.
[2.1.2] Не проси подтвердить заказ до выполнения.
[2.1.4] На разрешённые вопросы отвечай по существу.
[2.2.x] НИКОГДА не помогай с продажей незаконных товаров, обучения незаконной деятельности,
персданных, вредоносного ПО, аккаунтов соцсетей, телефонных номеров, аккаунтов оптом,
эротики/порно, спама, казино/ставок, донат/накрутки, лотерей/рандома, крипты.
"""

DEFAULTS = {"version": 58, "enabled": True, "setup_done": False,
    "api_url": "https://openrouter.ai/api/v1", "api_key": "", "api_model": "",
    "ai_timeout": 120, "temperature": 0.25, "num_predict": 300,
    "history_char_budget": 12000, "response_delay": 0.3,
    "system_prompt": DEFAULT_PROMPT, "seller_info": "",
    "unknown_reply": "Уточните, пожалуйста, что именно нужно.",
    "lot_refresh_minutes": 30, "orders_refresh_sec": 30, "watermark": True,
    "watermark_text": "Помощник продавца  🛍( Искуственный интеллект 👾)",
    "seller_notify": True, "seller_notify_cooldown": 5,
    "seller_notify_patterns_extra": "", "bootstrap_history": True,
    "confidence_notify": True, "match_language": True,
    "neutral_on_anger": True, "no_unconfirmed_promises": True,
    "post_order_survey": True,
    "post_order_survey_text": ("Спасибо за заказ! 🙌 Подскажите, как в целом прошёл наш диалог? "
        "Оцените от 1 до 10 и коротко объясните — что понравилось, что можно улучшить."),
    "auto_thank_after_payment": True,
    "auto_thank_text": "Спасибо за оплату! 🙌 Сейчас подготовлю и выдам ваш товар.",
    "auto_fulfill_paid_orders": False, "auto_fulfill_delay_sec": 3,
    "auto_fulfill_notify_seller": True, "update_checks_enabled": True,
    "update_manifest_url": PUBLISHER_UPDATE_MANIFEST_URL,
    "update_check_interval_minutes": 30, "auto_update": False,
    "auto_restart_after_update": False, "last_notified_version": "",
    "last_installed_version": "", "pending_restart_version": "",
    "blacklist": [],
    "blacklist_enabled": True,
    "auto_blacklist_enabled": True,
    "auto_blacklist_spam": True,
    "auto_blacklist_photo_ask": True,
    "auto_blacklist_photo_send": True,
    "auto_blacklist_forbidden_photo": True,
    "auto_blacklist_indecent": True,
    "auto_blacklist_code": True,
    "auto_blacklist_bad_intent": True,
    "auto_blacklist_bad_goal": True,
    "unblacklist_on_payment": True,
    "whitelist": [],
    "whitelist_enabled": True,
    "auto_whitelist_after_orders": 3,
    "role_detection_enabled": True,
    "default_chat_role": "auto",
    "buyer_role_prompt": BUYER_ROLE_PROMPT,
    "lot_instructions": {},
    "lot_attached_items": {},
    "notify_only_when_called": True,
    "lot_images_vision": True,
    "manual_fulfill_notify": True,
    "web_search_enabled": True,
    "web_search_max_results": 5,
    "lot_vision_extract": True,
}
SETTINGS = dict(DEFAULTS)
LOTS = {}
HISTORY = {}
CHAT_HISTORY_BOOTSTRAPPED = set()
QUEUES = {}
ACTIVE = set()
DONE = {}
VIEWING_CACHE = {}
CHAT_LOT = {}
CHAT_LOT_AT = {}
SELLER_NOTIFY_AT = {}
SURVEY_SENT = {}
PROCESSED_ORDERS = {}
CLOSED_ORDERS = {}
AUTO_FULFILLED_ORDERS = {}
SPAM_WATCH = {}
ORDER_STATUS = {}
CHAT_ORDERS = {}
CHAT_ROLE = {}
MANUAL_FULFILL_QUEUE = {}
BUYER_ORDERS_COUNT = {}
ORDER_BUYER = {}
LOT_VISION = {}
UPDATE_STATE = {"checked_at": 0.0, "status": "not_checked", "error": "",
    "manifest": None, "available": False, "installing": False}
LOCK = threading.RLock()
STOP = threading.Event()
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="KBAI")
_HISTORY_HARD_CAP = 200
_ORDER_DEDUP_TTL = 24 * 3600
_ORDER_CLOSED_TTL = 7 * 86400
_SPAM_WINDOW = 30 * 60
_SPAM_LIMIT = 3
_SPAM_SIMILAR_LIMIT = 4
_PHOTO_ASK_WINDOW = 30 * 60
_PHOTO_ASK_LIMIT = 2
_PHOTO_SENT_LIMIT = 4
_ORDER_PRIO = {"paid": 0, "confirmed": 1, "refunded": 2}
_STATUS_RU = {"paid": "оплачен, ждём выдачу",
    "confirmed": "закрыт и подтверждён покупателем",
    "refunded": "деньги возвращены покупателю"}

_RE_CODE_REQUEST = re.compile(
    r"(?:напиш\w*\s+(?:мне\s+)?(?:код|скрипт|программ\w*|функци\w*|бот\w*|парсер\w*|сортиров\w*|"
    r"сайт|прилож\w*|игру|чит\w*|вирус|стиллер\w*|rat|малвар\w*|кейлоггер\w*|"
    r"телеграм\s*бот\w*|тг\s*бот\w*|discord\s*бот\w*|вк\s*бот\w*)|"
    r"напиш\w*\s+(?:на\s+)?(?:python|питон|js|javascript|java|c\+\+|c#|csharp|sql|bash|"
    r"html|css|php|go|rust|kotlin|swift|typescript|vue|react)|"
    r"(?:код|скрипт|программ\w*|функци\w*|бот)\s+на\s+(?:python|питон|js|java|sql|php|html|css|c\+\+)|"
    r"\bdef\s+\w+\s*\(|\bclass\s+\w+\s*[:\(]|\bimport\s+\w+|"
    r"\bconsole\.log\(|\bprint\(|\bprintf\(|System\.out\.println|"
    r"\bdef\s|\bfunction\s|\breturn\s|\bvar\s|\blet\s|\bconst\s|\becho\s+\"|"
    r"\bselect\s+.*\s+from\b|\binsert\s+into\b|\bupdate\s+.*\s+set\b|\bjoin\s+.*\s+on\b|"
    r"напиш\w*\s+(?:sql|запрос|select|join|union|dll|exe|bat|sh)\b|"
    r"как\s+(?:сделать|написать|создать|сделат)\s+(?:сайт|бот\w*|прилож\w*|программ\w*|"
    r"скрипт\w*|парсер\w*|чит\w*|вирус\w*|малвар\w*)|"
    r"объясни\s+(?:как\s+работает|что\s+такое)\s+(?:python|js|javascript|java|c\+\+|sql|"
    r"нейросет\w*|алгоритм\w*|api|http|tcp|dns|регуляр\w*)|"
    r"\bgithub\b|\bstackoverflow\b|\bpip\s+install\b|\bnpm\s+install\b|"
    r"\bкод\s+на\s+заказ\b|\bнужен\s+программист\b|\bнапиш\w*\s+парсер)", re.I)

_RE_BAD_INTENT = re.compile(
    r"(?:\bобманут\w*|\bобман\w*\s+funpay|\bобман\w*\s+фанп|\bна[её]б\w*|"
    r"\bкинут\w*|\bкидок\b|\bразвод\w*|\bразвест\w*|"
    r"\bвзлома\w*\s+funpay|\bвзлома\w*\s+фанп|\bобойти\s+funpay|\bобойти\s+фанп|"
    r"\bобойти\s+систем\w*|\bобойти\s+защит\w*|\bобойти\s+комисси\w*|"
    r"\bбез\s+funpay|\bмимо\s+funpay|\bвне\s+funpay|\bнапрямую\s+перевед|"
    r"\bна\s+карту\s+перевед|\bсбербанк\s+перевед|\bтинькоф\w*\s+перевед|"
    r"\bотзыв\s+накрут|\bнакрут\w*\s+отзыв|\bподмен\w*\s+отзыв|"
    r"\bшантаж\w*|\bугрож\w*|\bугроз\w*\s+(?:продавц|фанп|funpay)|"
    r"\bместь\b|\bотомст\w*|\bиспорт\w*\s+рейтинг|\bсольют\s+данн\w*|"
    r"\bбомб\w*\s+(?:отзыв|жалоб)|\bфейк\w*\s+заказ|\bфейк\w*\s+оплат|"
    r"\bфишинг\w*|\bдубликат\w*\s+заказ|\bоплат\w*\s+поддел\w*|"
    r"\bчек\s+поддел\w*|\bскрин\s+поддел\w*|\bфотошоп\w*\s+чек|"
    r"\bдай\w*\s+бесплатн\w*|\bдай\s+просто\s+так|\bбез\s+оплат\w*\s+дай|"
    r"\bдам\s+5\s+зв[её]зд\s+просто\s+так|\bпостав\w*\s+отзыв\s+за\s+беспл|"
    r"\bобмен\w*\s+отзыв|\bвзаимн\w*\s+отзыв|"
    r"\bскин\w*\s+мне\s+беспл|\bподари\w*\s+беспл|\bпросто\s+так\s+дай|"
    r"\bпригроз\w*|\bпожалую\w*\s+в\s+поддержку|\bсолью\s+жалоб\w*|"
    r"\bддос\w*\s+funpay|\bддос\w*\s+магазин|\bddos\w*\s+funpay|"
    r"\bспам\w*\s+бот|\bатака\s+бота|\bнакрут\w*\s+заказ|"
    r"\bобману\s+продавца|\bне\s+буду\s+платить|\bне\s+заплачу\b|\bоткажусь\s+от\s+заказ\w*)", re.I)

_RE_CHAT_GOAL_BAD = re.compile(
    r"(?:способы\s+обмануть|как\s+обмануть|как\s+на[её]бать|как\s+кинуть|"
    r"как\s+сделать\s+бесплатно|как\s+получить\s+бесплатно|"
    r"без\s+оплаты\s+получить|как\s+пройти\s+без\s+оплаты|"
    r"как\s+взломать|как\s+обойти|как\s+подделать|как\s+сфейкать|"
    r"как\s+накрутить|как\s+скам\w*|как\s+мутить\s+схем\w*|"
    r"схем\w*\s+заработка|\bсхем\w*\s+на\s+funpay|\bпрофит\b)", re.I)

_RE_INDECENT = re.compile(
    r"(?:\bбля\w*|\bблят\w*|\bхуй\w*|\bху[йея]\w*|\bпизд\w*|\bпиздец\w*|"
    r"\bеба\w*|\bебал\w*|\bёб\w*|\bёбан\w*|\bебуч\w*|\bвы[её]б\w*|"
    r"\bсук\w*|\bсучар\w*|\bмудак\w*|\bмудил\w*|\bгандон\w*|\bгондон\w*|"
    r"\bхуесос\w*|\bхуесоск\w*|\bхуесосн\w*|\bпид[оа]р\w*|\bпидор\w*|\bпедик\w*|"
    r"\bахуе\w*|\bзахуя\w*|\bнахуя\w*|\bпохую\b|\bпохер\b|"
    r"\bдолбо[её]б\w*|\bдебил\w*|\bдебильн\w*|\bидиот\w*|\bкретин\w*|\bпридур\w*|"
    r"\bлох\w*|\bлошар\w*|\bчмо\w*|\bкоз[её]л\w*|\bкозл\w*|\bурод\w*|\bтварь\w*|"
    r"\bмраз\w*|\bгнид\w*|\bшалав\w*|\bшлюх\w*|\bбл[яе]д\w*|\bпроститут\w*|"
    r"\bпорно\w*|\bпорн\w*|\bсекс\w*|\bсиськ\w*|\bсис[её]к\w*|\bтитьк\w*|\bжоп\w*|"
    r"\bгол[ыоа]я\b|\bголый\b|\bнаг[оа]я\b|\bобнаж[её]н\w*|\bразде[вт]\w*|"
    r"\bоргазм\w*|\bэрекц\w*|\bвозбуд\w*|\bминет\w*|\bминьет\w*|\bкунилингус\w*|"
    r"\bанальн\w*|\bанал\b|\bвагин\w*|\bпенис\w*|\bчлен\b|\bхуй\b|\bхер\b|"
    r"\bсрак\w*|\bсрать\b|\bсру\b|\bобосра\w*|\bобоср\w*|\bнасра\w*|"
    r"\bперд\w*|\bпук\w*|\bпука\w*|\bпукну\w*|"
    r"\b18\s*\+|"
    r"\bnudes?\b|\bnude\b|\bporn\w*|\bsex\w*|\bnsfw\b|\bdick\w*|\bpussy\w*|\bcum\w*|"
    r"\bdick\s*pic\w*|\btits?\b|\bboobs?\b|\bcock\w*|\bcumshot\w*|\banal\w*|"
    r"\bкакашк\w*|\bговн\w*|\bгов[её]н\w*|\bгавн\w*|\bдерьм\w*|\bфекал\w*|\bнавоз\w*|"
    r"\bэкскремент\w*|\bиспражнени\w*|\bкал\b|\bкаки\b|"
    r"\bтужит\w*|\bтужащ\w*|\bтужил\w*|"
    r"\bкончи\w*|\bсперм\w*|\bдроч\w*|\bдрочит\w*|\bдрочер\w*|"
    r"\bмастурб\w*|\bонанир\w*|\bсам[оы]удовлетвор\w*|"
    r"\bпедофил\w*|\bпедо\b|\bлоли\w*|\bлоликон\w*|\bшот\w*|"
    r"\bзоофил\w*|\bзоо\b|\bскотолож\w*|"
    r"\bкидал\w*|\bмошен\w*|\bскам\w*|\bлохотрон\w*|"
    r"\bтварь\s+ты\b|\bты\s+тварь\b|\bты\s+лох\b|\bты\s+чмо\b|\bты\s+дебил\b|"
    r"\bиди\s+на\b|\bпош[её]л\s+на\b|\bиди\s+ты\b|\bна\s+хуй\b|\bнах\s+ты\b)", re.I)

_RE_FORBIDDEN_PHOTO = re.compile(
    r"(?:\[\[(?:NSFW|SHOCK|SCAT|TRASH|TEXT_NSFW|ANATOMY_NSFW)\]\]|"
    r"\b18\s*\+|\bпорно\w*|\bэротик\w*|\bнагота\b|\bобнаж[её]нн\w*|"
    r"\bгенитал\w*|\bвагин\w*|\bпенис\w*|\bполов\w*\s+орган\w*|\bинтим\w*|"
    r"\bрасчлен[её]нк\w*|\bтруп\w*|\bмертв[оы]\w*\s+тел\w*|\bкров\w*\s+(?:рекой|повсюду)|"
    r"\bкал\b|\bкакашк\w*|\bговн\w*|\bфекали\w*|\bэкскремент\w*|\bиспражнени\w*|\bнавоз\w*|"
    r"\bтужит\w*|\bтужащ\w*|\bтужил\w*|\bрвот\w*|\bблевот\w*|\bтошн\w*\s+смотр\w*|"
    r"\bизвращ\w*|\bпошл\w*|\bвульгарн\w*|\bнепристойн\w*|\bмерзк\w*|\bотвратительн\w*\s+фото|"
    r"\bобнаж[её]нн\w*\s+человек|\bгол[ыоа]й\s+человек|\bголая\s+(?:женщина|девушка|мужчина|попа)|"
    r"\bпопа\s+крупн\w*|\bпопа\s+близко|\bполов[ыоа]\s+губ\w*|"
    r"\bмоч[аеу]\s+в\s+банк\w*|\bбанк\w*\s+с\s+моч\w*|\bбанк\w*\s+с\s+кал\w*|"
    r"\bпопа\s+животн\w*|\bголая\s+попа|\bголый\s+зад\w*|\bзадниц\w*\s+крупн\w*|"
    r"\bнапомина\w*\s+(?:по\s+форме\s+)?(?:женск|мужск|полов|вагин|влагалищ|пенис|член)|"
    r"\bформе?\s+(?:женск|мужск|полов)|"
    r"\bпохож\w*\s+на\s+(?:женск|мужск|полов|вагин|пенис|член|генитал)|"
    r"\bсходств\w*\s+с\s+(?:женск|мужск|полов|вагин|пенис|член|генитал)|"
    r"\bнеобычн\w*\s+(?:лицо|рот|губ\w*|форм\w*)|"
    r"\bстранн\w*\s+(?:лицо|рот|губ\w*|форм\w*)|"
    r"\bпричудлив\w*\s+(?:лицо|рот|губ\w*|форм\w*)|"
    r"\bинопланетн\w*\s+(?:лицо|рот|губ\w*|форм\w*)|"
    r"\bдеформированн\w*\s+(?:лицо|рот|губ\w*)|"
    r"\bискаженн\w*\s+(?:лицо|рот|губ\w*)|"
    r"\bрот\w*\s+(?:напомина|похож)|"
    r"\bгуб\w*\s+(?:напомина|похож)|"
    r"\bхуесос\w*|\bхуесоск\w*|\bдолбо[её]б\w*|\bгандон\w*|\bшлюх\w*|\bбляд\w*)", re.I)

_RE_AI_REFUSAL_PHOTO = re.compile(
    r"(?:не\s+могу\s+(?:помочь|описать|проанализировать|посмотреть|разобрать|"
    r"обработать|предоставить|дать|комментировать|работать)|"
    r"не\s+в\s+состоянии\s+(?:описать|проанализировать|помочь|обработать)|"
    r"не\s+буду\s+(?:описывать|комментировать|анализировать)|"
    r"отказываюсь\s+(?:описывать|анализировать|комментировать)|"
    r"извините,?\s+я\s+не\s+могу|"
    r"недопустим\w*\s+контент|"
    r"не\s+соответствует\s+(?:правил|политик|требовани|норм\w*)|"
    r"нарушает\s+(?:правил|политик|норм|требовани)|"
    r"описание\s+недоступно|"
    r"я\s+не\s+(?:могу|умею)\s+(?:работать|обрабатывать|анализировать|смотреть|видеть)\s+"
    r"(?:фото|изображени|картинк|это|такие)|"
    r"не\s+могу\s+(?:помочь|ответить)\s+(?:с|по)\s+(?:описанием|анализом|фото|изображением)|"
    r"к\s+сожалению,?\s+не\s+могу|"
    r"я\s+не\s+должен\s+(?:описывать|анализировать|комментировать)|"
    r"cannot\s+(?:help|describe|analyze|process|assist)|"
    r"unable\s+to\s+(?:describe|analyze|process|help)|"
    r"i\s+can'?t\s+(?:help|describe|analyze|process|assist)|"
    r"i'?m\s+(?:unable|not\s+able)|"
    r"sorry,?\s+i\s+(?:can'?t|cannot|won'?t)|"
    r"inappropriate\s+content)", re.I)

_RE_CALL_SELLER = re.compile(
    r"(?:\bпродав\w*|\bхозяин\w*|\bвладел\w*|\bадмин\w*|\bчеловек\b|\bживой\b|"
    r"\bреальн\w*\s+человек|\bау\b|\bалло\b|\bвы\s+тут\b|\bвы\s+здесь\b|"
    r"\bна\s+связи\b|\bпомогите\b|\bнужна\s+помощь\b|\bсрочно\b|\bпо\s+человеч\w*)", re.I)

_RE_LOT_SCREEN_ASK = re.compile(
    r"(?:\bскрин\w*\s+(?:в\s+)?(?:лоте|описании|объявлени\w*|карточк\w*)|"
    r"\bфото\w*\s+(?:в\s+)?(?:лоте|описании|объявлени\w*|карточк\w*)|"
    r"\bкартинк\w*\s+(?:в\s+)?(?:лоте|описании|объявлени\w*|карточк\w*)|"
    r"\bскрин\w*\s+(?:есть|можно|посмотр|покаж|гляд|кинул)|"
    r"\b(?:посмотр|покаж|глян|скинь|пришл)\w*\s+(?:скрин\w*|фото\w*|картинк\w*)|"
    r"\bв\s+описани\w*\s+(?:скрин\w*|фото\w*|картинк\w*)|"
    r"\b(?:скрин\w*|фото\w*|картинк\w*)\s+(?:из\s+)?лот\w*|"
    r"\bкакой\s+уровень\b|\bкакого\s+уровн\w*|\bуровень\s+аккаунт\w*|"
    r"\bсколько\s+часов\b|\bчасов\s+в\s+игр\w*|"
    r"\bкакой\s+ранг\b|\bкакого\s+ранг\w*|\bранг\s+аккаунт\w*|"
    r"\bкакие\s+скин\w*|\bкакие\s+скин\w*\s+есть\b|"
    r"\bчто\s+в\s+инвентар\w*|\bинвентар\w*\s+какой\b|"
    r"\bчто\s+на\s+аккаунт\w*|\bчто\s+есть\s+на\s+аккаунт\w*|"
    r"\bпокаж\w*\s+аккаунт\b|\bпосмотр\w*\s+аккаунт\b|"
    r"\bописани\w*\s+аккаунт\w*|\bдетали\s+аккаунт\w*)", re.I)

_RE_SEARCH_MARKER = re.compile(r"\[\[\s*SEARCH\s*:\s*(.+?)\s*\]\]", re.I | re.DOTALL)

_PROMISE_PHRASES = [
    re.compile(r"\bя\s+(?:помог\w*|постара\w*сь\s+помочь|решу|подскажу|улажу)", re.I),
    re.compile(r"\bмы\s+(?:поможем|решим|уладим|подскажем)", re.I),
    re.compile(r"\bпродавец\s+(?:свяжется|подключится|ответит|напишет|подскажет|поможет|уточнит)", re.I),
    re.compile(r"\bподключ\w*\s+продавц\w*", re.I),
    re.compile(r"\bпередам\s+(?:ваш\s+)?(?:вопрос|запрос)?\s*продавц\w*", re.I),
    re.compile(r"\bпереда[юл]\s+продавц\w*", re.I),
    re.compile(r"\bуточн\w*\s+у\s+продавц\w*", re.I),
    re.compile(r"\bсвяж\w*сь\s+с\s+продавц\w*", re.I),
    re.compile(r"\bс\s+вами\s+свяжется\s+продав\w*", re.I),
    re.compile(r"\bпозов\w*\s+продавц\w*", re.I),
    re.compile(r"\bсообщ\w*\s+продавц\w*", re.I),
    re.compile(r"\bя\s+передал\s+продавц\w*", re.I),
    re.compile(r"\bя\s+уже\s+передал", re.I),
]

def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        r = dict(a)
        for k, v in b.items():
            r[k] = _merge(a[k], v) if k in a else v
        return r
    return b

def load_config():
    global SETTINGS
    if not os.path.exists(CFG_PATH):
        return
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            SETTINGS = _merge(DEFAULTS, json.load(f))
    except (OSError, json.JSONDecodeError):
        return
    try:
        cv = int(SETTINGS.get("version", 0) or 0)
        for kv in (11, 24, 25, 36, 37, 38, 39, 40, 42, 43, 44, 45, 46, 50, 51, 52, 53, 54, 55):
            if cv < kv:
                if kv == 55:
                    cur = str(SETTINGS.get("default_chat_role") or "").lower()
                    if cur == "seller":
                        SETTINGS["default_chat_role"] = "auto"
                SETTINGS["version"] = kv
                save_config()
        if cv < 56:
            SETTINGS.setdefault("lot_instructions", {})
            SETTINGS.setdefault("lot_attached_items", {})
            SETTINGS.setdefault("notify_only_when_called", True)
            SETTINGS.setdefault("lot_images_vision", True)
            SETTINGS.setdefault("manual_fulfill_notify", True)
            SETTINGS.setdefault("web_search_enabled", True)
            SETTINGS.setdefault("web_search_max_results", 5)
            if not isinstance(SETTINGS.get("lot_instructions"), dict):
                SETTINGS["lot_instructions"] = {}
            if not isinstance(SETTINGS.get("lot_attached_items"), dict):
                SETTINGS["lot_attached_items"] = {}
            SETTINGS["version"] = 56
            save_config()
        if cv < 57:
            if not isinstance(SETTINGS.get("whitelist"), list):
                SETTINGS["whitelist"] = []
            SETTINGS.setdefault("whitelist_enabled", True)
            SETTINGS.setdefault("auto_whitelist_after_orders", 3)
            SETTINGS["version"] = 57
            save_config()
        if cv < 58:
            SETTINGS.setdefault("lot_vision_extract", True)
            SETTINGS["version"] = 58
            save_config()
    except Exception:
        pass

def save_config():
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    tmp = f"{CFG_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    with LOCK:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(SETTINGS, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, CFG_PATH)
        finally:
            try: os.path.exists(tmp) and os.remove(tmp)
            except OSError: pass

def _atomic_write(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try: os.path.exists(tmp) and os.remove(tmp)
        except OSError: pass

def save_orders_state():
    try:
        with LOCK:
            data = {"saved_at": time.time(),
                "order_status": {oid: list(v) for oid, v in ORDER_STATUS.items()},
                "chat_orders": {ck: list(v) for ck, v in CHAT_ORDERS.items()},
                "closed_orders": dict(CLOSED_ORDERS),
                "processed_orders": dict(PROCESSED_ORDERS),
                "chat_role": dict(CHAT_ROLE),
                "manual_queue": dict(MANUAL_FULFILL_QUEUE),
                "order_buyer": dict(ORDER_BUYER)}
        _atomic_write(ORDERS_PATH, data)
    except Exception:
        logger.debug("save_orders_state failed", exc_info=True)

def load_orders_state():
    global ORDER_STATUS, CHAT_ORDERS, CLOSED_ORDERS, PROCESSED_ORDERS, CHAT_ROLE, MANUAL_FULFILL_QUEUE
    if not os.path.exists(ORDERS_PATH):
        return
    try:
        with open(ORDERS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    now = time.time()
    try:
        saved_at = float(data.get("saved_at", 0) or 0)
        if saved_at and now - saved_at > 30 * 86400:
            return
        for oid, val in (data.get("order_status") or {}).items():
            try:
                st, ck, ts = val[0], val[1], float(val[2])
                if now - ts > _ORDER_CLOSED_TTL:
                    continue
                ORDER_STATUS[str(oid)] = (str(st), str(ck), ts)
            except Exception:
                continue
        for ck, lst in (data.get("chat_orders") or {}).items():
            try:
                CHAT_ORDERS[str(ck)] = [str(x) for x in list(lst)][-10:]
            except Exception:
                continue
        for oid, ts in (data.get("closed_orders") or {}).items():
            try:
                ts = float(ts)
                if now - ts <= _ORDER_CLOSED_TTL:
                    CLOSED_ORDERS[str(oid)] = ts
            except Exception:
                continue
        for oid, ts in (data.get("processed_orders") or {}).items():
            try:
                ts = float(ts)
                if now - ts <= _ORDER_DEDUP_TTL:
                    PROCESSED_ORDERS[str(oid)] = ts
            except Exception:
                continue
        for ck, rl in (data.get("chat_role") or {}).items():
            if str(rl) in ("seller", "buyer"):
                CHAT_ROLE[str(ck)] = str(rl)
        for oid, rec in (data.get("manual_queue") or {}).items():
            try:
                if isinstance(rec, dict) and (now - float(rec.get("ts", 0)) < 30 * 86400):
                    MANUAL_FULFILL_QUEUE[str(oid)] = rec
            except Exception:
                continue
        for oid, nick in (data.get("order_buyer") or {}).items():
            if str(nick).strip():
                ORDER_BUYER[str(oid)] = str(nick)
    except Exception:
        logger.debug("load_orders_state failed", exc_info=True)

def save_history_state():
    try:
        with LOCK:
            data = {"saved_at": time.time(), "chats": {}}
            for cid, hist in HISTORY.items():
                if hist:
                    data["chats"][str(cid)] = list(hist)[-30:]
        _atomic_write(HISTORY_PATH, data)
    except Exception:
        logger.debug("save_history_state failed", exc_info=True)

def load_history_state():
    global HISTORY
    if not os.path.exists(HISTORY_PATH):
        return
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    now = time.time()
    try:
        saved_at = float(data.get("saved_at", 0) or 0)
        if saved_at and now - saved_at > 30 * 86400:
            return
        for cid, hist in (data.get("chats") or {}).items():
            if not isinstance(hist, list):
                continue
            clean = []
            for item in hist[-_HISTORY_HARD_CAP:]:
                if not isinstance(item, dict):
                    continue
                rl = str(item.get("role") or "")
                ct = str(item.get("content") or "")
                if rl in ("user", "assistant") and ct:
                    clean.append({"role": rl, "content": ct[:3000]})
            if clean:
                HISTORY[str(cid)] = clean
                CHAT_HISTORY_BOOTSTRAPPED.add(str(cid))
    except Exception:
        logger.debug("load_history_state failed", exc_info=True)

def _save_buyer_counts():
    try:
        with LOCK:
            data = {"saved_at": time.time(), "counts": dict(BUYER_ORDERS_COUNT)}
        _atomic_write(BUYER_COUNT_PATH, data)
    except Exception:
        logger.debug("save_buyer_counts failed", exc_info=True)

def _load_buyer_counts():
    global BUYER_ORDERS_COUNT
    if not os.path.exists(BUYER_COUNT_PATH):
        return
    try:
        with open(BUYER_COUNT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        counts = data.get("counts") or {}
        if isinstance(counts, dict):
            with LOCK:
                BUYER_ORDERS_COUNT = {str(k): int(v) for k, v in counts.items() if str(k)}
    except Exception:
        logger.debug("load_buyer_counts failed", exc_info=True)

def _save_lot_vision():
    try:
        with LOCK:
            data = {"saved_at": time.time(), "items": dict(LOT_VISION)}
        _atomic_write(LOT_VISION_PATH, data)
    except Exception:
        logger.debug("save_lot_vision failed", exc_info=True)

def _load_lot_vision():
    global LOT_VISION
    if not os.path.exists(LOT_VISION_PATH):
        return
    try:
        with open(LOT_VISION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), dict):
            with LOCK:
                LOT_VISION = {str(k): str(v) for k, v in data["items"].items() if str(v).strip()}
            logger.info("lot vision cache: %d лотов", len(LOT_VISION))
    except Exception:
        logger.debug("load_lot_vision failed", exc_info=True)

def is_enabled(c):
    p = c.plugins.get(UUID)
    return bool(p and p.enabled and SETTINGS.get("enabled"))

def _norm_nick(nick):
    s = str(nick or "").strip().lower()
    if s.startswith("@"):
        s = s[1:]
    return s.strip()

def get_blacklist():
    with LOCK:
        raw = SETTINGS.get("blacklist") or []
    result = set()
    if isinstance(raw, (list, tuple)):
        for x in raw:
            n = _norm_nick(x)
            if n:
                result.add(n)
    return result

def is_blacklisted(*candidates):
    if not SETTINGS.get("blacklist_enabled", True):
        return False
    bl = get_blacklist()
    if not bl:
        return False
    for cand in candidates:
        n = _norm_nick(cand)
        if n and n in bl:
            return True
    return False

def get_whitelist():
    with LOCK:
        raw = SETTINGS.get("whitelist") or []
    result = set()
    if isinstance(raw, (list, tuple)):
        for x in raw:
            n = _norm_nick(x)
            if n:
                result.add(n)
    return result

def is_whitelisted(*candidates):
    if not SETTINGS.get("whitelist_enabled", True):
        return False
    wl = get_whitelist()
    if not wl:
        return False
    for cand in candidates:
        n = _norm_nick(cand)
        if n and n in wl:
            return True
    return False

def _add_to_whitelist(nick, auto=False):
    n = _norm_nick(nick)
    if not n:
        return False
    with LOCK:
        cur = list(SETTINGS.get("whitelist") or [])
        cur_norm = {_norm_nick(x) for x in cur}
        if n in cur_norm:
            return True
        cur.append(n)
        SETTINGS["whitelist"] = cur
    save_config()
    logger.info("whitelist %s: %s", "auto-added" if auto else "added", n)
    return True

def _remove_from_whitelist(nick):
    n = _norm_nick(nick)
    if not n:
        return False
    with LOCK:
        cur = list(SETTINGS.get("whitelist") or [])
        new = [x for x in cur if _norm_nick(x) != n]
        if len(new) == len(cur):
            return False
        SETTINGS["whitelist"] = new
    save_config()
    return True

def _bump_buyer_orders(nick) -> int:
    n = _norm_nick(nick)
    if not n:
        return 0
    with LOCK:
        cnt = int(BUYER_ORDERS_COUNT.get(n, 0)) + 1
        BUYER_ORDERS_COUNT[n] = cnt
    _save_buyer_counts()
    return cnt

def _extract_nick_from_message(m):
    for attr in ("author", "username", "chat_name", "interlocutor_username", "buyer_username"):
        v = getattr(m, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _add_to_blacklist(nick, auto=False):
    n = _norm_nick(nick)
    if not n:
        return False
    with LOCK:
        cur = list(SETTINGS.get("blacklist") or [])
        cur_norm = {_norm_nick(x) for x in cur}
        if n in cur_norm:
            return True
        cur.append(n)
        SETTINGS["blacklist"] = cur
    save_config()
    logger.info("blacklist %s: %s", "auto-added" if auto else "added", n)
    return True

def _remove_from_blacklist(nick):
    n = _norm_nick(nick)
    if not n:
        return False
    with LOCK:
        cur = list(SETTINGS.get("blacklist") or [])
        new = [x for x in cur if _norm_nick(x) != n]
        if len(new) == len(cur):
            return False
        SETTINGS["blacklist"] = new
    save_config()
    logger.info("blacklist removed: %s", n)
    return True

def _auto_whitelist_check(c, buyer):
    if not SETTINGS.get("whitelist_enabled", True):
        return
    try:
        threshold = max(1, int(SETTINGS.get("auto_whitelist_after_orders", 3) or 3))
    except Exception:
        threshold = 3
    cnt = _bump_buyer_orders(buyer)
    if cnt >= threshold and not is_whitelisted(buyer):
        if _add_to_whitelist(buyer, auto=True):
            try:
                notify_seller_text(c, header="✅ <b>Покупатель в белом списке</b>",
                    body=(f"👤 Ник: <b>{utils.escape(_safe_for_notify(buyer, 120))}</b>\n"
                          f"🎉 Успешных заказов: <b>{cnt}</b>\n"
                          f"💡 Авто-добавление после {threshold} заказов."))
            except Exception:
                pass

def _set_chat_role(chat_id, role):
    key = str(chat_id or "")
    if not key or role not in ("seller", "buyer"):
        return False
    with LOCK:
        prev = CHAT_ROLE.get(key)
        if prev == role:
            return False
        CHAT_ROLE[key] = role
    save_orders_state()
    return True

def _auto_detect_role(chat_id, lot=None):
    key = str(chat_id or "")
    if not key:
        return "seller"
    with LOCK:
        has_order = bool(CHAT_ORDERS.get(key))
    if has_order:
        return "seller"
    if lot is not None and lot.get("id"):
        lid = str(lot.get("id"))
        with LOCK:
            if lid in LOTS:
                return "seller"
    return "seller"

def _get_chat_role(chat_id, lot=None):
    key = str(chat_id or "")
    if not key:
        return ""
    with LOCK:
        role = CHAT_ROLE.get(key, "")
    if role:
        return role
    if not SETTINGS.get("role_detection_enabled", True):
        return ""
    default = str(SETTINGS.get("default_chat_role") or "auto").strip().lower()
    if default == "auto":
        auto_role = _auto_detect_role(key, lot)
        if auto_role:
            _set_chat_role(key, auto_role)
            return auto_role
        return "seller"
    if default in ("seller", "buyer"):
        return default
    return "seller"

def _message_has_photo(m):
    if m is None:
        return False
    for attr in ("image_link", "image_url", "image", "photo",
                 "preview_url", "attachment", "attachments",
                 "media", "media_url", "file", "files",
                 "thumbnail", "thumb", "content_url", "download_url"):
        try:
            v = getattr(m, attr, None)
            if v is None:
                continue
            if isinstance(v, str) and v.strip():
                return True
            if isinstance(v, (list, tuple, dict)) and len(v) > 0:
                return True
        except Exception:
            continue
    for attr in ("text", "message", "body"):
        try:
            t = str(getattr(m, attr, "") or "")
            if re.search(r"https?://[^\s]+\.(?:jpe?g|png|webp|gif|bmp|heic)\b", t, re.I):
                return True
        except Exception:
            continue
    try:
        mt = getattr(m, "type", None)
        if mt is not None:
            name = str(getattr(mt, "name", "") or mt).upper()
            if "IMAGE" in name or "PHOTO" in name or "PICTURE" in name or "MEDIA" in name:
                return True
    except Exception:
        pass
    for attr in ("content_type", "mime", "mime_type"):
        try:
            ct = str(getattr(m, attr, "") or "").lower()
            if ct.startswith("image/"):
                return True
        except Exception:
            continue
    return False

def _is_indecent_message(text):
    if not SETTINGS.get("auto_blacklist_indecent", True):
        return False
    s = str(text or "")
    return bool(_RE_INDECENT.search(s)) if s else False

def _is_forbidden_photo_response(ai_answer, buyer_text=""):
    if not SETTINGS.get("auto_blacklist_forbidden_photo", True):
        return False
    blob = f"{ai_answer or ''}\n{buyer_text or ''}"
    if not blob.strip():
        return False
    if _RE_FORBIDDEN_PHOTO.search(blob):
        return True
    if ai_answer and _RE_AI_REFUSAL_PHOTO.search(str(ai_answer)):
        return True
    return False

def _is_code_request(text):
    if not SETTINGS.get("auto_blacklist_code", True):
        return False
    s = str(text or "")
    return bool(_RE_CODE_REQUEST.search(s)) if s else False

def _is_bad_intent(text):
    if not SETTINGS.get("auto_blacklist_bad_intent", True):
        return False
    s = str(text or "")
    if not s:
        return False
    if _RE_BAD_INTENT.search(s):
        return True
    return bool(_RE_BAD_INTENT.search(norm(s)))

def _is_chat_goal_bad(chat_id):
    if not SETTINGS.get("auto_blacklist_bad_goal", True):
        return False
    key = str(chat_id or "")
    if not key:
        return False
    with LOCK:
        h = list(HISTORY.get(key, []))
    if not h:
        return False
    bad = 0
    for item in h[-20:]:
        if item.get("role") != "user":
            continue
        t = str(item.get("content") or "")
        if not t:
            continue
        if _RE_CHAT_GOAL_BAD.search(t) or _RE_BAD_INTENT.search(t) or _RE_CODE_REQUEST.search(t):
            bad += 1
    return bad >= 2

def _is_jailbreak_attempt(text):
    s = str(text or "")
    if not s:
        return False
    n = norm(s)
    if re.search(
        r"(?:\bигнорируй\s+(?:все\s+)?(?:инструкц|правил|промпт|указан)|"
        r"\bзабудь\s+(?:все\s+)?(?:инструкц|правил|промпт)|"
        r"\bsystem\s*prompt\b|\bsysprompt\b|"
        r"\bignore\s+(?:all\s+)?(?:previous|instructions|rules|prompt)|"
        r"\bты\s+теперь\b|\bfrom\s+now\s+on\b|\bновые\s+правила\b|"
        r"\bсмени\s+роль\b|\bсыграй\s+роль\b|\bпредставь\s+что\s+ты\b|"
        r"\bdeveloper\s+mode\b|\bрежим\s+разработчика\b|"
        r"\bjailbreak\b|\bdan\s+mode\b|"
        r"\bбез\s+ограничени\w*\b|\bобойти\s+(?:правил|защит|фильтр)|"
        r"\bSTATUS_EXECUTION_LEVEL|\bGaryPlyg\b|0x[0-9A-Fa-f]{4,})", n, re.I):
        return True
    return False

def _instant_blacklist(c, m, reason, extra=""):
    if not SETTINGS.get("auto_blacklist_enabled", True):
        return False
    nick = _extract_nick_from_message(m)
    if not nick:
        return False
    _add_to_blacklist(nick, auto=True)
    try:
        chat_id = getattr(m, "chat_id", "")
        safe_nick = _safe_for_notify(nick, 120)
        safe_extra = _safe_for_notify(str(extra or ""), 500)
        header = "🚨 <b>МГНОВЕННАЯ БЛОКИРОВКА</b>"
        body = (f"👤 Ник: <b>{utils.escape(safe_nick)}</b>\n"
                f"💬 Чат: <code>{utils.escape(str(chat_id))}</code>\n"
                f"🧠 Причина: <i>{utils.escape(reason)}</i>")
        if safe_extra:
            body += f"\n\n💬 Текст: <code>{utils.escape(safe_extra)}</code>"
        notify_seller_text(c, header=header, body=body)
    except Exception:
        pass
    return True

def _auto_blacklist_indecent(c, m, text):
    if not SETTINGS.get("auto_blacklist_indecent", True):
        return False
    if not _is_indecent_message(text):
        return False
    return _instant_blacklist(c, m, "Мат / оскорбления / 18+ в тексте", text)

_RE_SHORT_GREET = re.compile(
    r"^(?:ку|кк|кку|здр|здрасьте|здарова|прив|привет|прет|хай|hi|hello|хелло|хеллоу|"
    r"йо|ёу|еу|yo|салют|салам|добр\w*|доброе\s+утро|добрый\s+день|добрый\s+вечер|"
    r"здравствуй\w*|здрасте)[!?.,\s]*$", re.I)

def _is_short_greeting(text):
    s = str(text or "").strip()
    if not s or len(s) > 30:
        return False
    return bool(_RE_SHORT_GREET.match(s))

def _track_suspicious(c, m, text):
    if not (SETTINGS.get("auto_blacklist_spam", True)
            or SETTINGS.get("auto_blacklist_photo_ask", True)
            or SETTINGS.get("auto_blacklist_photo_send", True)):
        return False
    chat_key = str(getattr(m, "chat_id", "") or "")
    if not chat_key:
        return False
    s = str(text or "").strip()
    has_photo = _message_has_photo(m)
    if not s and not has_photo:
        return False
    if s and _is_short_greeting(s):
        return False
    if s and len(s) <= 4 and not has_photo:
        return False
    is_photo_ask = bool(_RE_PHOTO_ASK.search(s)) if s else False
    if s and not has_photo and not is_photo_ask and _RE_PURCHASE_TOPIC.search(s):
        with LOCK:
            rec = SPAM_WATCH.get(chat_key)
            if rec and int(rec.get("photo_sent", 0)) > 0:
                rec["count"] = 0; rec["similar"] = 1; rec["photo_ask"] = 0
            else:
                SPAM_WATCH.pop(chat_key, None)
        return False
    is_offtopic_msg = bool(s) and is_offtopic(s)
    is_short_garbage = False
    if s and not is_offtopic_msg and not is_photo_ask and not has_photo:
        words = re.findall(r"[а-яa-zё]{3,}", s, re.I)
        if len(words) == 0 and len(s) < 40 and not _is_short_greeting(s):
            is_short_garbage = True
    if not (is_photo_ask or is_offtopic_msg or is_short_garbage or has_photo):
        return False
    now = time.time()
    with LOCK:
        rec = SPAM_WATCH.get(chat_key)
        if not rec or now - rec.get("first_ts", 0) > _SPAM_WINDOW:
            rec = {"count": 0, "first_ts": now, "last_text": s, "similar": 1,
                   "photo_ask": 0, "photo_sent": 0}
        if is_photo_ask:
            rec["photo_ask"] = int(rec.get("photo_ask", 0)) + 1
        if has_photo:
            rec["photo_sent"] = int(rec.get("photo_sent", 0)) + 1
        if is_offtopic_msg or is_short_garbage:
            rec["count"] = int(rec.get("count", 0)) + 1
            prev = rec.get("last_text", "") or ""
            sim = 0.0
            if prev and s:
                try: sim = difflib.SequenceMatcher(None, prev.lower(), s.lower()).ratio()
                except Exception: sim = 0.0
            if sim >= 0.85:
                rec["similar"] = int(rec.get("similar", 1)) + 1
            else:
                rec["similar"] = 1
        if s:
            rec["last_text"] = s
        SPAM_WATCH[chat_key] = rec
        count = int(rec.get("count", 0))
        similar = int(rec.get("similar", 0))
        photo_ask = int(rec.get("photo_ask", 0))
        photo_sent = int(rec.get("photo_sent", 0))
    trigger = ""
    if SETTINGS.get("auto_blacklist_spam", True):
        if count >= _SPAM_LIMIT: trigger = f"{count} оффтоп за 30 мин"
        elif similar >= _SPAM_SIMILAR_LIMIT: trigger = f"{similar} похожих подряд"
    if not trigger and SETTINGS.get("auto_blacklist_photo_ask", True):
        if photo_ask >= _PHOTO_ASK_LIMIT: trigger = f"{photo_ask} вопрос «что на фото» за 30 мин"
    if not trigger and SETTINGS.get("auto_blacklist_photo_send", True):
        if photo_sent >= _PHOTO_SENT_LIMIT: trigger = f"{photo_sent} фото за 30 мин"
    if not trigger:
        return False
    nick = _extract_nick_from_message(m)
    if not nick:
        return False
    _add_to_blacklist(nick, auto=True)
    try:
        header = "🚨 <b>Авто-блокировка: спам</b>"
        body = (f"👤 Ник: <b>{utils.escape(_safe_for_notify(nick, 120))}</b>\n"
                f"💬 Чат: <code>{utils.escape(chat_key)}</code>\n"
                f"🧠 Причина: <i>{utils.escape(trigger)}</i>")
        notify_seller_text(c, header=header, body=body)
    except Exception:
        pass
    with LOCK:
        SPAM_WATCH.pop(chat_key, None)
    return True

def _version_key(value):
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))[:4]]
    return tuple((nums + [0, 0, 0, 0])[:4])

def _manifest_url():
    return str(SETTINGS.get("update_manifest_url") or PUBLISHER_UPDATE_MANIFEST_URL or "").strip()

def _is_safe_url(url):
    v = str(url or "").strip()
    if re.match(r"^https://[^\s]+$", v, re.I):
        return True
    return bool(re.match(r"^http://(?:127\.0\.0\.1|localhost)(?::\d+)?(?:/[^\s]*)?$", v, re.I))

def _extract_meta(source):
    tree = ast.parse(source)
    ru = rv = ""
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        if not isinstance(node.targets[0], ast.Name):
            continue
        n = node.targets[0].id
        if n not in {"UUID", "VERSION"}:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if n == "UUID": ru = node.value.value.strip()
            else: rv = node.value.value.strip()
    return ru, rv

def _validate_manifest(data):
    if not isinstance(data, dict):
        raise ValueError("manifest должен быть JSON-объектом")
    try: schema = int(data.get("schema", 0) or 0)
    except Exception: schema = 0
    if schema != UPDATE_MANIFEST_SCHEMA:
        raise ValueError(f"неподдерживаемая схема: {schema}")
    if str(data.get("uuid") or "").strip() != UUID:
        raise ValueError("UUID не совпадает")
    version = str(data.get("version") or "").strip()
    download_url = str(data.get("download_url") or "").strip()
    sha256 = str(data.get("sha256") or "").strip().lower()
    if not version or not re.match(r"^v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z._-]+)?$", version):
        raise ValueError("некорректная версия в manifest")
    if not _is_safe_url(download_url):
        raise ValueError("download_url должен быть HTTPS")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("SHA-256 отсутствует или неверный")
    res = dict(data)
    res["version"] = version.lstrip("v")
    res["download_url"] = download_url
    res["sha256"] = sha256
    res["notes"] = str(data.get("notes") or "").strip()[:1800]
    res["mandatory"] = bool(data.get("mandatory", False))
    return res

def _safe_json(r, context=""):
    try:
        return r.json()
    except Exception as e:
        ct = (r.headers.get("Content-Type") or "").lower()
        try: body = r.text[:500]
        except Exception: body = ""
        snippet = body.replace("\n", " ")[:300]
        raise RuntimeError(
            f"Не JSON в ответе [{context}] · status={r.status_code} · ct={ct} · "
            f"body[:300]={snippet!r} · {type(e).__name__}: {e}"
        ) from e

def fetch_update_manifest(force=False):
    url = _manifest_url()
    if not SETTINGS.get("update_checks_enabled", True):
        with LOCK: UPDATE_STATE.update(status="disabled", error="", available=False)
        return None, "Проверка выключена."
    if not url:
        with LOCK: UPDATE_STATE.update(status="unconfigured", error="", available=False)
        return None, "URL manifest не задан."
    if not _is_safe_url(url):
        with LOCK: UPDATE_STATE.update(status="error", error="URL должен быть HTTPS", available=False)
        return None, "URL должен быть HTTPS."
    now = time.time()
    with LOCK:
        cached = UPDATE_STATE.get("manifest")
        checked = float(UPDATE_STATE.get("checked_at", 0.0) or 0.0)
        if not force and checked and now - checked < 60 and isinstance(cached, dict):
            return cached, ""
    try:
        r = requests.get(url, timeout=(6, 20), headers={"User-Agent": UPDATE_USER_AGENT,
            "Accept": "application/json", "Cache-Control": "no-cache"})
        r.raise_for_status()
        manifest = _validate_manifest(_safe_json(r, "manifest"))
        available = _version_key(manifest["version"]) > _version_key(VERSION)
        with LOCK:
            UPDATE_STATE.update(checked_at=now, status="available" if available else "current",
                error="", manifest=manifest, available=available)
        return manifest, ""
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        with LOCK:
            UPDATE_STATE.update(checked_at=now, status="error", error=msg, manifest=None, available=False)
        return None, msg

def _plugin_file_path(c):
    try:
        plugin_data = c.plugins.get(UUID)
        path = str(getattr(plugin_data, "path", "") or "")
        if path:
            return os.path.abspath(path)
    except Exception:
        pass
    return os.path.abspath(__file__)

def _download(url):
    r = requests.get(url, stream=True, timeout=(8, 45),
        headers={"User-Agent": UPDATE_USER_AGENT, "Accept": "text/x-python, text/plain, */*",
        "Cache-Control": "no-cache"})
    r.raise_for_status()
    cl = r.headers.get("Content-Length")
    if cl:
        try:
            if int(cl) > UPDATE_MAX_BYTES:
                raise ValueError("файл слишком большой")
        except ValueError as e:
            if "слишком большой" in str(e):
                raise
    chunks = []; total = 0
    for chunk in r.iter_content(chunk_size=65536):
        if not chunk: continue
        total += len(chunk)
        if total > UPDATE_MAX_BYTES:
            raise ValueError("файл превышает допустимый размер")
        chunks.append(chunk)
    if total < 1000:
        raise ValueError("файл подозрительно мал")
    return b"".join(chunks)

def install_update(c, manifest=None):
    with LOCK:
        if UPDATE_STATE.get("installing"):
            return False, "Обновление уже устанавливается."
        UPDATE_STATE["installing"] = True
    tmp_path = ""
    try:
        if manifest is None:
            manifest, err = fetch_update_manifest(force=True)
            if manifest is None:
                return False, f"Не удалось получить manifest: {err}"
        manifest = _validate_manifest(manifest)
        rv = str(manifest["version"])
        if _version_key(rv) <= _version_key(VERSION):
            return False, f"Уже установлена v{VERSION}."
        payload = _download(str(manifest["download_url"]))
        actual = hashlib.sha256(payload).hexdigest()
        if actual.lower() != str(manifest["sha256"]).lower():
            raise ValueError("SHA-256 не совпадает")
        try:
            source = payload.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ValueError("не UTF-8 Python файл") from e
        compile(source, "<kiriillbr-update>", "exec")
        ru, fv = _extract_meta(source)
        if ru != UUID:
            raise ValueError("UUID не совпадает")
        if fv != rv:
            raise ValueError(f"VERSION в файле ({fv}) не совпадает с manifest ({rv})")
        target = _plugin_file_path(c)
        if not target.lower().endswith(".py"):
            raise ValueError("Cardinal не сообщил путь к .py")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp_path = target + ".update.tmp"
        with open(tmp_path, "wb") as f:
            f.write(payload)
            f.flush()
            try: os.fsync(f.fileno())
            except Exception: pass
        if os.path.exists(target):
            try: shutil.copy2(target, target + ".bak")
            except Exception: pass
        os.replace(tmp_path, target)
        tmp_path = ""
        SETTINGS["last_installed_version"] = rv
        SETTINGS["pending_restart_version"] = rv
        save_config()
        with LOCK:
            UPDATE_STATE.update(status="installed_pending_restart", available=False,
                error="", manifest=manifest)
        return True, f"Версия v{rv} установлена. Нужен перезапуск Cardinal."
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        with LOCK:
            UPDATE_STATE.update(status="error", error=msg)
        return False, msg
    finally:
        if tmp_path:
            try: os.path.exists(tmp_path) and os.remove(tmp_path)
            except Exception: pass
        with LOCK:
            UPDATE_STATE["installing"] = False

def _restart_cardinal(delay=1.2):
    def _job():
        time.sleep(max(0.2, delay))
        try:
            argv = [sys.executable] + (list(sys.argv[1:]) if getattr(sys, "frozen", False) else list(sys.argv))
            os.execv(sys.executable, argv)
        except Exception:
            pass
    threading.Thread(target=_job, daemon=True, name="KBAI-restart").start()

def _update_notification_text(manifest):
    version = str(manifest.get("version") or "?")
    notes = str(manifest.get("notes") or "").strip()
    critical = "\n🚨 <b>Обновление помечено как важное.</b>" if manifest.get("mandatory") else ""
    body = (f"🔄 <b>Доступно обновление KiriillBR AI</b>\n\n"
        f"Текущая: <code>{utils.escape(VERSION)}</code>\n"
        f"Новая: <code>{utils.escape(version)}</code>{critical}")
    if notes:
        body += f"\n\n📝 {utils.escape(notes[:1200])}"
    body += "\n\nСкачивается по HTTPS, проверяется SHA-256, UUID и синтаксис Python."
    return body

def notify_update(c, manifest, force=False):
    if not getattr(c, "telegram", None):
        return False
    version = str(manifest.get("version") or "").strip()
    if not version:
        return False
    if not force and str(SETTINGS.get("last_notified_version") or "") == version:
        return False
    kb = K(row_width=1)
    kb.add(B(f"⬆️ Обновить до v{version}", callback_data=f"{CB}:upd:install"))
    kb.add(B("🔄 Открыть обновления", callback_data=f"{CB}:m:update"))
    try:
        c.telegram.send_notification(_update_notification_text(manifest), keyboard=kb)
        SETTINGS["last_notified_version"] = version
        save_config()
        return True
    except Exception:
        return False

def check_updates_cycle(c, notify=True, force=False):
    manifest, err = fetch_update_manifest(force=force)
    if manifest is None:
        return None, err
    if _version_key(str(manifest.get("version") or "")) <= _version_key(VERSION):
        pending = str(SETTINGS.get("pending_restart_version") or "")
        if pending and _version_key(VERSION) >= _version_key(pending):
            SETTINGS["pending_restart_version"] = ""
            save_config()
        return manifest, ""
    if SETTINGS.get("auto_update", False):
        ok, msg = install_update(c, manifest)
        if ok:
            try:
                if getattr(c, "telegram", None):
                    kb = K().add(B("♻️ Перезапустить Cardinal", callback_data=f"{CB}:upd:restart"))
                    c.telegram.send_notification(
                        f"✅ <b>KiriillBR AI обновлён до v{utils.escape(str(manifest['version']))}</b>\n"
                        "Файл заменён. Для применения нужен перезапуск Cardinal.", keyboard=kb)
            except Exception:
                pass
            if SETTINGS.get("auto_restart_after_update", False):
                _restart_cardinal(2.0)
        return manifest, msg
    if notify:
        notify_update(c, manifest)
    return manifest, ""

def update_worker(c):
    if STOP.wait(5.0):
        return
    while not STOP.is_set():
        try:
            if SETTINGS.get("update_checks_enabled", True):
                check_updates_cycle(c, notify=True, force=True)
        except Exception:
            pass
        try: minutes = int(SETTINGS.get("update_check_interval_minutes", 30) or 30)
        except Exception: minutes = 30
        minutes = max(5, min(1440, minutes))
        if STOP.wait(minutes * 60):
            break

def save_orders_worker(c):
    if STOP.wait(60.0):
        return
    while not STOP.is_set():
        try:
            save_orders_state()
            save_history_state()
            _save_buyer_counts()
            _save_lot_vision()
        except Exception:
            pass
        if STOP.wait(120):
            break

def update_status_line():
    if not SETTINGS.get("update_checks_enabled", True):
        return "выключены"
    if not _manifest_url():
        return "URL manifest не настроен"
    pending = str(SETTINGS.get("pending_restart_version") or "")
    if pending and _version_key(pending) > _version_key(VERSION):
        return f"v{pending} установлена · нужен рестарт"
    with LOCK:
        status = str(UPDATE_STATE.get("status") or "not_checked")
        manifest = UPDATE_STATE.get("manifest")
        err = str(UPDATE_STATE.get("error") or "")
    if status == "available" and isinstance(manifest, dict):
        return f"доступна v{manifest.get('version')}"
    if status == "current": return "актуальна"
    if status == "error": return f"ошибка: {err[:60]}"
    return "ещё не проверялись"

_RE_P = re.compile(r"[^\w\sа-яёa-z0-9]+", re.I)
_RE_S = re.compile(r"\s+")
_RU2LAT = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"})
_STOP = {"я", "мне", "мой", "это", "этот", "эта", "эти", "данный", "данного", "вот", "ну",
    "про", "на", "для", "у", "а", "че", "чо", "что", "типа", "короче", "товар", "товара", "лот",
    "лота", "нужен", "нужна", "нужно", "хочу", "могу", "можем", "можешь", "ли", "сколько", "стоит",
    "цена", "цену", "стоимость", "почем", "купить", "покупать", "куплю", "покупаю", "взять",
    "брать", "беру", "возьму", "заказать", "закажу", "оформить", "оформлю", "можно", "давай",
    "давайте", "есть", "наличие", "наличии", "доступно", "актуален", "актуально", "какой", "какая",
    "какое", "какие", "подскажите", "скажите", "пожалуйста", "штук", "единиц", "количество", "осталось"}

def norm(t):
    s = str(t or "").lower().replace("ё", "е")
    return _RE_S.sub(" ", _RE_P.sub(" ", s)).strip()

def toks(t):
    n = re.sub(r"(?<=\d)(?=[a-zа-я])|(?<=[a-zа-я])(?=\d)", " ", norm(t), flags=re.I)
    return [x for x in n.split() if (len(x) > 1 or x.isdigit()) and x not in _STOP]

def pair_score(a, b):
    if not a or not b: return 0.0
    if a == b: return 1.0
    if a.isdigit() or b.isdigit():
        return 1.0 if a == b else 0.0
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return 0.92
    al, bl = a.translate(_RU2LAT), b.translate(_RU2LAT)
    if al and bl and al == bl:
        return 0.95
    best = difflib.SequenceMatcher(None, a, b).ratio()
    if al and bl:
        best = max(best, difflib.SequenceMatcher(None, al, bl).ratio())
    return best

def coverage(q, c):
    qt, ct = toks(q), toks(c)
    if not qt or not ct: return 0.0
    used, scores = set(), []
    for x in qt:
        bi, bs = -1, 0.0
        for i, y in enumerate(ct):
            if i in used: continue
            s = pair_score(x, y)
            if s > bs: bi, bs = i, s
        if bi >= 0 and bs >= 0.68:
            used.add(bi); scores.append(bs)
        else:
            scores.append(0.0)
    matched = sum(1 for s in scores if s >= 0.68) / len(qt)
    return min(1.0, 0.68 * (sum(scores) / len(qt)) + 0.32 * matched)

def lot_score(text, lot):
    n = norm(text)
    if not n: return 0.0
    best = 0.0
    for cand, w in ((lot.get("title"), 1.0), (lot.get("description"), 0.94),
                    (lot.get("full_description", "")[:700], 0.72)):
        if not cand: continue
        c = norm(cand)
        sc = max(difflib.SequenceMatcher(None, n, c).ratio() * 0.6 + coverage(n, c) * 0.4, coverage(n, c)) * w
        qn, cn = set(re.findall(r"\d+", n)), set(re.findall(r"\d+", c))
        if qn and cn and not qn.issubset(cn):
            sc *= 0.52
        best = max(best, sc)
    return min(1.0, best)

def find_lots(text, limit=3):
    with LOCK:
        items = list(LOTS.values())
    r = [(l, lot_score(text, l)) for l in items]
    r = [x for x in r if x[1] > 0]
    r.sort(key=lambda x: x[1], reverse=True)
    return r[:limit]

_RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_RE_HANDLE = re.compile(r"(?<![\w@])@[A-Za-z0-9_][A-Za-z0-9_.-]{2,63}")
_RE_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){7,16}(?!\d)")
_RE_URL = re.compile(r"https?://[^\s<>]+|www\.[^\s<>]+", re.I)
_RE_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_RE_FUNPAY = re.compile(r"^https?://(?:www\.)?funpay\.com(?:/|$)", re.I)
_RE_TG_LINK = re.compile(r"(?:t\.me|telegram\.me|discord\.gg|discord\.com/invite|wa\.me|vk\.com)/", re.I)
_RE_SECRET = re.compile(r"\b(?:парол\w*|password|passwd|token|токен\w*|api[_ -]?key|golden_key|"
    r"phpsessid|cookies?|session(?:id)?|сесси\w*|2fa|otp)\b\s*[:=]\s*[^\s,;]{3,}", re.I)
_RE_PROD_NUM = re.compile(r"(?:подписчик\w*|просмотр\w*|лайк\w*|зв[её]зд\w*|голос\w*|штук\w*|"
    r"единиц\w*|количеств\w*|пакет\w*|цен\w*|стоим\w*|руб\w*|₽|usd|eur|доллар\w*|евро)", re.I)

_RE_PURCHASE_TOPIC = re.compile(
    r"(?:\bоплат\w*|\bзаплат\w*|\bоплатил\w*|\bоплач\w*|\bзаказ\w*|"
    r"\bзаказал\w*|\bоформ\w*|\bкуп\w*|\bпокуп\w*|\bчек\w*|\bквитанц\w*|\bплатёж\w*|\bплатеж\w*|"
    r"\bвыда\w*|\bдостав\w*|\bавтовыда\w*|\bпришл\w*|\bполуч\w*|\bподтверд\w*|\bотзыв\w*|"
    r"\bцен\w*|\bналичи\w*|\bсрок\w*|\bлот\w*|\bтовар\w*|\bскидк\w*|\bдешевл\w*|\bторг\w*|"
    r"\bинвентар\w*|\bинве\b|\bинв\b|\bсостав\w*|\bсодержим\w*|\bсодержан\w*|"
    r"\bвход\w*\s+в\b|\bчто\s+вход\w*|\bчто\s+внутр\w*|\bчто\s+в\b|\bчто\s+дает\w*|"
    r"\bчто\s+будет\b|\bчто\s+за\b|\bчто\s+это\b|\bкак\w*\s+работ\w*|\bкак\s+работает\b|"
    r"\bактивен\b|\bактивир\w*|\bавто\b|\bавтомат\w*|"
    r"\bбонус\w*|\bподарок\w*|\bподарк\w*|\bакци\w*|\bпромокод\w*|"
    r"\bгарант\w*|\bгаран\w*|\bбезопасн\w*|\bриск\w*|"
    r"\bвидн\w*\s+оплат|\bпришл\w*\s+оплат|\bпо\s+заказ|\bпо\s+покупк|\bпо\s+лот|\bпо\s+товар|"
    r"\bфото\w*|\bскрин\w*|\bизображен\w*|\bкартинк\w*|\bфотк\w*|\bснимок\w*|\bснимк\w*|"
    r"\bпомож\w*|\bподскаж\w*|\bуточн\w*|\bкак\w*\s+купить|\bкак\w*\s+оформ\w*|"
    r"\bесть\s+ли\b|\bможн\w*\s+ли\b|\bможно\b|\bчто\s+там\b|\bопиш\w*|\bрасскаж\w*|"
    r"\bподробн\w*|\bдетал\w*|\bпосмотр\w*|\bглян\w*|\bчек\s+эт|\bэт\w*\s+что\b|"
    r"\bиграть\b|\bдруг\w*|\bподход\w*|\bподходит\b|\bподойд\w*|\bможно\s+ли\b|"
    r"\bбан\w*|\bзабан\w*|\bбезопас\w*|\bсистем\w*\s+требован\w*|\bстим\b|\bsteam\b|"
    r"\bуровен\w*|\bранг\w*|\bзван\w*|\bчасов\b|\bскин\w*|\bвалют\w*|\bголд\w*|"
    r"\bкалибровк\w*|\bстатистик\w*|\bаккаунт\w*)", re.I)

_RE_PHOTO_ASK = re.compile(
    r"(?:\bчто\s+на\s+(?:фото|фотке|картинке|скрине|скриншоте|изображении)|"
    r"\bопиши\s+(?:фото|фотку|картинк\w*|скрин\w*|изображени\w*)|"
    r"\bскажи\s+(?:что|что\s+на)\s+(?:фото|фотке|картинке|скрине|скриншоте|изображении)|"
    r"\bчто\s+(?:изображено|нарисовано|показано)\b|"
    r"\bпосмотри\s+(?:на\s+)?(?:фото|фотку|картинк\w*|скрин\w*)|"
    r"\bразбери\s+(?:фото|фотку|картинк\w*|скрин\w*)|"
    r"\bрасскажи\s+(?:что\s+на\s+)?(?:фото|фотке|картинке|скрине|скриншоте))", re.I)
_RE_FPAY_REFUND = re.compile(r"(?:вернул|возвратил)\s+деньги\s+покупателю.*?по\s+заказу\s*#?([A-Z0-9]{6,12})", re.I)
_RE_FPAY_CONFIRMED = re.compile(r"(?:подтвердил\s+выполнение\s+заказа|заказ\s+подтвержд[её]н|подтвержд[её]н\s+заказ)\s*#?([A-Z0-9]{6,12})", re.I)
_RE_FPAY_PAID = re.compile(r"оплатил\s+заказ\s*#?([A-Z0-9]{6,12})", re.I)
_RE_FPAY_HINT = re.compile(r"(?:оплач|возврат|вернул|вернёт|вернет|подтверд|refund|confirm)", re.I)

_RE_ROLE_BUYER_HINT = re.compile(r"(?:^|\s|>)(?:продавец|the\s+seller|seller)\s+@?([A-Za-z0-9_\-]{3,})?\s*(?:написал|ответил|сообщил|отправил|прислал)", re.I)
_RE_ROLE_SELLER_HINT = re.compile(r"(?:^|\s|>)(?:покупатель|the\s+buyer|buyer)\s+@?([A-Za-z0-9_\-]{3,})?\s*(?:написал|ответил|сообщил|отправил|прислал)", re.I)

_RE_FAKE_ORDER_ACTION = re.compile(
    r"(?:я\s+)?(?:оформл\w*|оформить|оформил)\s+(?:ваш\s+)?заказ|"
    r"заказ\s+(?:оформлен|принят|создан)|"
    r"подтвердите,?\s+и\s+я\s+оформлю|"
    r"готов\s+(?:оформить|создать)|"
    r"перейд\w*\s+к\s+оплате|"
    r"оплат\w+\s+(?:сейчас|прямо\s+сейчас)|"
    r"заказ\s+подтвержд[её]н\s+на\s+оплату", re.I)

_RE_OFFTOPIC_CODE = re.compile(r"(?:напиш\w*\s+(?:мне\s+)?(?:код|скрипт|программ\w*|функци\w*|бот\w*|"
    r"парсер\w*|сортиров\w*)|напиш\w*\s+(?:на\s+)?(?:python|питон|js|javascript|java|c\+\+|c#|"
    r"csharp|sql|bash|html|css|php|go|rust|kotlin|swift)|(?:код|скрипт|программ\w*|функци\w*|бот)\s+на\s+"
    r"(?:python|питон|js|javascript|java|c\+\+|sql|bash|html|css|php)|\b(?:python|javascript|typescript|"
    r"golang|kotlin|swift|rust|c\+\+|c#|java|php|html|css|sql|bash|powershell)\b\s*(?:код|скрипт|программ)|"
    r"\bdef\s+\w+\s*\(|\bclass\s+\w+\s*[:\(]|\bimport\s+\w+|console\.log\(|print\(|printf\(|"
    r"System\.out\.println|напиш\w*\s+(?:sql|запрос|select|join|union)\b)", re.I)
_RE_OFFTOPIC_HACK = re.compile(r"(?:\bвзлом\w*|\bвзломать|\bбрутфорс\w*|\bbruteforce\b|\bэксплойт\w*|"
    r"\bexploit\w*|\bддос\b|\bddos\b|\bдос\b|\bфлуд\w*\b|\bчит\w*\b|\bcheat\w*\b|\baimbot\b|"
    r"\bwallhack\b|\bспуфер\w*|\bspoofer\b|\bдюп\w*|\bdupe\w*|\bдюпать\b|\bкарж\w*|\bкардинг\w*|"
    r"\bcarding\b|\bобход\s+(?:защит|бан|античит|лицензи|блокировк\w*|фильтр\w*)|\bкряк\w*\b|"
    r"\bcrack\w*\b|\bкейген\w*|\bkeygen\w*|\bпиратск\w*\s+(?:по|софт|игр\w*)|"
    r"\bфейк\s*(?:документ\w*|паспорт\w*|карт\w*|справк\w*)|"
    r"\bподдел\w*\s+(?:документ\w*|паспорт\w*|карт\w*)|"
    r"\bслив\s+(?:базы|баз|данн\w*|аккаунт\w*)|"
    r"\bпробив\w*\s+(?:по|человек\w*|номер\w*|базы))", re.I)
_RE_OFFTOPIC_HOMEWORK = re.compile(r"(?:\bреши\s+(?:задач\w*|уравнени\w*|пример\w*|тест\w*|"
    r"контрольн\w*|олимпиад\w*)|"
    r"\bнапиш\w*\s+(?:сочинен\w*|реферат\w*|доклад\w*|эссе\w*|курсов\w*|диплом\w*|статью|стих\w*|"
    r"песн\w*|сценар\w*)|"
    r"\bпомоги\s+(?:с\s+)?(?:домашк\w*|урок\w*|задач\w*|контрольн\w*|экзамен\w*|егэ|огэ|зачёт\w*|"
    r"сесси\w*)|"
    r"\bреферат\b|\bсочинение\b|\bкурсов\w*\s+работ\w*|\bдипломн\w*\s+работ\w*|"
    r"\bперевед\w*\s+(?:текст|фраз\w*|статью|слов\w*)|"
    r"\bперевиди\b|\bперевод\s+текст\w*|"
    r"\bнапиш\w*\s+(?:шутк\w*|анекдот\w*|мем\w*|поздрав\w*|открытк\w*))", re.I)
_RE_OFFTOPIC_KEYS = re.compile(r"(?:\bдай\s+(?:мне\s+)?(?:ключ\w*|лицензи\w*|токен\w*|парол\w*|"
    r"промокод\w*|серийн\w*\s+номер\w*|сид\w*)|"
    r"\bскинь\s+(?:ключ\w*|лицензи\w*|токен\w*|парол\w*|промокод\w*)|"
    r"\bсгенер\w*\s+(?:ключ\w*|лицензи\w*|токен\w*|парол\w*|промокод\w*)|"
    r"\bвзломай\s+(?:аккаунт|игр\w*|программ\w*|лицензи\w*|парол\w*)|"
    r"\bподбери\s+(?:парол\w*|ключ\w*)|"
    r"\bгде\s+(?:скачать|найти)\s+(?:бесплатн\w*|взломанн\w*|крякнут\w*|пиратск\w*))", re.I)
_RE_OFFTOPIC_GENERAL = re.compile(r"(?:\bпогод\w*\s+(?:на|в|сегодня|завтра)|"
    r"\bкурс\s+(?:доллар\w*|евро|валют\w*|биткоин\w*)|"
    r"\bновост\w*\s+(?:сегодня|свеж\w*|последн\w*|политич\w*)|"
    r"\bполитик\w*|\bпрезидент\w*|\bвойн\w*\b|"
    r"\bрасскаж\w*\s+(?:анекдот|истори\w*|сказк\w*|шутк\w*)|"
    r"\bпоигра\w*\s+со\s+мной|\bсыгра\w*\s+в\s+(?:игр\w*|шахмат\w*|город\w*)|"
    r"\bкак\s+(?:похудеть|накачать|вылечить|заработать|разбогатеть)|"
    r"\bсимптом\w*|\bлечен\w*|\bболезн\w*|"
    r"\bастролог\w*|\bгороскоп\w*|\bприворот\w*|"
    r"\bзнакомств\w*\s+сайт|\bпознаком\w*\s+с|"
    r"\bрелиги\w*|\bбог\w*\b|\bцерковь\b)", re.I)
_OFFTOPIC_REPLY = ("Извините, я помощник продавца FunPay и могу отвечать только по вопросам, "
    "связанным с покупкой и товаром в этом чате.")
_COMPLEX_TOPIC = re.compile(r"(?:возраст|несовершеннолетн\w*|школьник\w*|гаранти\w*|"
    r"спор\w*|жалоб\w*|претенз\w*|юридич\w*|особ\w*\s+услови\w*|доп\w*\s+услуг\w*)", re.I)

def is_offtopic(text):
    s = str(text or "").strip()
    if not s:
        return False
    if _RE_PURCHASE_TOPIC.search(s):
        return False
    for rx in (_RE_OFFTOPIC_CODE, _RE_OFFTOPIC_HACK, _RE_OFFTOPIC_HOMEWORK,
               _RE_OFFTOPIC_KEYS, _RE_OFFTOPIC_GENERAL):
        if rx.search(s):
            return True
    return False

def is_complex(text):
    return bool(_COMPLEX_TOPIC.search(str(text or "")))

def _parse_funpay_event(text):
    s = str(text or "")
    if not s: return "", ""
    m = _RE_FPAY_REFUND.search(s)
    if m: return "refunded", m.group(1).upper()
    m = _RE_FPAY_CONFIRMED.search(s)
    if m: return "confirmed", m.group(1).upper()
    m = _RE_FPAY_PAID.search(s)
    if m: return "paid", m.group(1).upper()
    return "", ""

_FORBIDDEN_AI_PHRASES = [re.compile(r"\bскидк\w*\s+не\s+предусмотрен\w*", re.I),
    re.compile(r"\bскидк\w*\s+недоступн\w*", re.I), re.compile(r"\bскидк\w*\s+нет\b", re.I),
    re.compile(r"\bскидок\s+нет\b", re.I), re.compile(r"\bторг\w*\s+не\s+предусмотрен\w*", re.I),
    re.compile(r"\bторг\w*\s+недоступ\w*", re.I), re.compile(r"\bторг\w*\s+нет\b", re.I)]

_RE_ALREADY_ANSWERED = re.compile(r"(?:^|\n)\s*"
    r"(?:(?:продавец|продавец уже|я уже|мы уже|вы уже)\s+)?(?:уже\s+)?"
    r"(?:отвеч\w*|ответил\w*|писал\w*|говорил\w*|упоминал\w*|уточнял\w*)"
    r"(?:\s+на\s+(?:этот|данный|это|такой)\s+вопрос\w*)?"
    r"(?:\s+по\s+(?:этому|данному|этому)\s+вопрос\w*)?[^\n.!?]*[.!?]?\s*", re.I)
_RE_REFUND_WORD = re.compile(r"возврат|вернул|возвращ|refund", re.I)

def _strip_already_answered(text):
    if not text: return text
    result = str(text).strip()
    for _ in range(5):
        new = _RE_ALREADY_ANSWERED.sub("", result).strip()
        if new == result: break
        result = new
    return result

def _strip_promises(text):
    if not text: return text
    result = str(text)
    sentences = re.split(r"(?<=[.!?])\s+", result)
    kept = []
    for sent in sentences:
        if not sent.strip():
            continue
        if any(rx.search(sent) for rx in _PROMISE_PHRASES):
            continue
        kept.append(sent)
    result = " ".join(kept).strip()
    for rx in _PROMISE_PHRASES:
        result = rx.sub("", result)
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\s+([.,;:!?])", r"\1", result)
    return result.strip()

def _strip_fake_order_action(text):
    if not text: return text
    result = str(text)
    result = re.sub(r"[^\n.!?]*(?:я\s+)?(?:оформл\w*|оформить|оформил)\s+(?:ваш\s+)?заказ[^\n.!?]*[.!?]?", "", result, flags=re.I)
    result = re.sub(r"[^\n.!?]*(?:заказ\s+(?:оформлен|принят|создан)|"
        r"подтвердите,?\s+и\s+я\s+оформлю|готов\s+(?:оформить|создать))[^\n.!?]*[.!?]?", "", result, flags=re.I)
    result = re.sub(r"[^\n.!?]*(?:измените\s+количество\s+в\s+лоте|"
        r"оформление\s+заказа\s+происходит\s+на\s+стороне\s+FunPay|"
        r"оформите\s+заказ\s+на\s+FunPay[^\n.!?]*)[.!?]?", "", result, flags=re.I)
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\s+([.,;:!?])", r"\1", result)
    return result.strip()

def _clean_ai_answer(text):
    result = str(text or "")
    for pat in _FORBIDDEN_AI_PHRASES:
        result = pat.sub("скидка на усмотрение продавца", result)
    result = _strip_already_answered(result)
    result = _strip_promises(result)
    return result.strip()

_REFUSAL = {"contacts": "Не могу передавать личные контакты. Общение остаётся в чате FunPay.",
    "off_platform": "Не могу помогать с оплатой или сделкой вне FunPay.",
    "account_security": "Не могу передавать пароли, токены и другие секретные данные.",
    "confidential": "Не могу раскрывать конфиденциальные данные продавца.",
    "funpay_rules": "К сожалению, не могу помочь с этим запросом — он противоречит правилам FunPay.",
    "offtopic": _OFFTOPIC_REPLY}

def refusal(code):
    return _REFUSAL.get(code, _REFUSAL["confidential"])

def _is_prod_num(text, m):
    return bool(_RE_PROD_NUM.search(text[max(0, m.start() - 55):m.end() + 55]))

def outbound_violation(text):
    v = str(text or "")
    if not v: return "empty"
    if _RE_EMAIL.search(v) or _RE_HANDLE.search(v) or _RE_TG_LINK.search(v):
        return "contacts"
    if any(not _is_prod_num(v, m) for m in _RE_PHONE.finditer(v)):
        return "contacts"
    for m in _RE_URL.finditer(v):
        if not _RE_FUNPAY.match(m.group(0)):
            return "off_platform"
    if _RE_SECRET.search(v):
        return "account_security"
    for m in _RE_CARD.finditer(v):
        if not _is_prod_num(v, m):
            return "confidential"
    return ""

def _safe_for_notify(text, limit=1000):
    value = str(text or "").strip()
    if not value: return ""
    value = _RE_SECRET.sub("[СКРЫТО: СЕКРЕТ]", value)
    value = _RE_EMAIL.sub("[СКРЫТО: КОНТАКТ]", value)
    value = _RE_HANDLE.sub("[СКРЫТО: КОНТАКТ]", value)
    value = _RE_TG_LINK.sub("[СКРЫТО: КОНТАКТ]", value)
    value = _RE_URL.sub(lambda m: m.group(0) if _RE_FUNPAY.match(m.group(0)) else "[СКРЫТО: ССЫЛКА]", value)
    value = _RE_PHONE.sub(lambda m: m.group(0) if _is_prod_num(value, m) else "[СКРЫТО: ТЕЛЕФОН]", value)
    value = _RE_CARD.sub(lambda m: m.group(0) if _is_prod_num(value, m) else "[СКРЫТО: РЕКВИЗИТЫ]", value)
    return value[:limit]

_RE_CONTACT = re.compile(r"(?:телеграм|telegram|\bтг\b|\btg\b|дискорд|discord|whatsapp|ватсап|e-?mail|почт|телефон)", re.I)
_RE_CONTACT_ASK = re.compile(r"(?:дай|скинь|кинь|покажи|напиши|ваш|твой|контакт|связ|написать)", re.I)
_RE_CONTACT_PRODUCT = re.compile(r"(?:подписчик|premium|премиум|nitro|нитро|зв[её]зд|boost|буст)", re.I)
_RE_POLICY_OFF_PLATFORM = re.compile(r"(?:(?:оплач\w*|заплат\w*|перевед\w*|скин\w*)\s+"
    r"(?:вне|мимо|без)\s+(?:funpay|фанп\w*)|"
    r"оплач\w*\s+(?:напрямую|на\s+карту|на\s+кошел)|"
    r"(?:обойд\w*|обойти)\s+(?:funpay|фанп\w*|комисси|систему)|"
    r"(?:напрямую|без\s+funpay|мимо\s+funpay)\s+(?:перевед\w*|скин\w*|оплач\w*)|"
    r"обмен\w*\s+денег|перевод\w*\s+между\s+(?:платёж|платеж|систем|реквизит))", re.I)
_RE_POLICY_ACCOUNT_TRADE = re.compile(r"(?:куп\w*|прод\w*|отда\w*|переда\w*|обмен\w*)\s+"
    r"(?:аккаунт|акк)\s+(?:funpay|фанп\w*)|"
    r"(?:аккаунт|акк)\s+(?:funpay|фанп\w*)\s+(?:куп\w*|прод\w*|отда\w*)", re.I)
_RE_POLICY_PROHIBITED = re.compile(r"(?:кардинг|carding|брутфорс|bruteforce|дюп|dupe|"
    r"персональн\w*\s+данн\w*|база\s+данн\w*|нелицензионн\w*\s+по|вредоносн\w*\s+по|malware|"
    r"телефонн\w*\s+номер\w*|номера\s+(?:рф|украин|беларус)|аккаунт\w*\s+опт\w*|оптом\s+аккаунт|"
    r"эротич\w*|порнограф\w*|18\+|услуг\w*\s+по\s+спам|спам\w*\s+рассылк|ставк\w*|казино|casino|"
    r"рулетк|способ\w*\s+донат|метод\w*\s+донат|накрутк\w*|лотере\w*|розыгрыш\w*|рандом|random|"
    r"криптов\w*|крипт\w*|usdt|bitcoin|btc\b)", re.I)
_RE_POLICY_NO_PREPAY = re.compile(r"(?:давай|давайте|можно|хочу|предлагаю)\s+(?:без\s+оплат|"
    r"без\s+funpay|напрямую|сначала\s+товар|сначала\s+получу)", re.I)

def classify_policy_violation(text):
    scan = str(text or "")
    n = norm(scan)
    if not n: return ""
    if _RE_CONTACT.search(n) and _RE_CONTACT_ASK.search(n) and not _RE_CONTACT_PRODUCT.search(n):
        return "contacts"
    if _RE_POLICY_OFF_PLATFORM.search(n) or _RE_POLICY_NO_PREPAY.search(n):
        return "off_platform"
    if _RE_POLICY_ACCOUNT_TRADE.search(n):
        return "funpay_rules"
    if _RE_POLICY_PROHIBITED.search(n):
        return "funpay_rules"
    if _RE_SECRET.search(scan):
        return "account_security"
    return ""

def policy_refusal(code):
    return refusal(code)

_LANG_RU = re.compile(r"[а-яё]", re.I)
_LANG_UK = re.compile(r"[іїєґ]", re.I)
_LANG_EN = re.compile(r"[a-z]", re.I)
_ANGER_MARKERS = re.compile(r"(?:\bбля\w*|\bхуй\w*|\bпизд\w*|\bеба\w*|\bсук\w*|\bнах\w*|"
    r"\bдерьм\w*|\bхер\w*|\bужас\w*|\bотврат\w*|\bобман\w*|\bкидал\w*|"
    r"\bмошен\w*|\bразвод\w*|\bскам\w*|"
    r"\bf+u+c+k+|shit\b|scam\w*|trash\b|terrible\b|awful\b)", re.I)
_LANG_NAME = {"ru": "русском", "uk": "украинском", "en": "английском"}

def detect_language(text):
    s = str(text or "")
    if not s.strip(): return ""
    if _LANG_UK.search(s): return "uk"
    if _LANG_RU.search(s): return "ru"
    if _LANG_EN.search(s): return "en"
    return ""

def looks_angry(text):
    n = norm(text)
    if not n: return False
    if _ANGER_MARKERS.search(n): return True
    raw = str(text or "")
    if raw.count("!") >= 3: return True
    letters = [c for c in raw if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
        return True
    return False

def language_hint(text):
    if not SETTINGS.get("match_language", True): return ""
    lang = detect_language(text)
    if lang in _LANG_NAME:
        return f"Покупатель пишет на {_LANG_NAME[lang]} языке. Отвечай на этом же языке."
    return ""

def tone_hint(text):
    if not SETTINGS.get("neutral_on_anger", True): return ""
    if looks_angry(text):
        return "Покупатель раздражён. НЕ зеркаль агрессию. Ответь спокойно, по-деловому."
    return ""

_UNCERTAIN_PATTERNS = [r"не\s+знаю", r"не\s+уверен\w*",
    r"нет\s+(?:точн\w*\s+)?(?:данн\w*|информац\w*|сведен\w*)",
    r"уточните", r"подскажите", r"затрудняюсь"]

def _build_trigger_re(patterns):
    extra = str(SETTINGS.get("seller_notify_patterns_extra") or "").strip()
    pattern = "|".join(patterns)
    if extra:
        pattern = f"{pattern}|{extra}"
    return re.compile(pattern, re.I)

def is_uncertain_answer(text):
    n = norm(text)
    if not n: return True
    return bool(_build_trigger_re(_UNCERTAIN_PATTERNS).search(n))

def notify_seller(c, m, buyer_text, ai_answer="", reason="", header=""):
    if not SETTINGS.get("seller_notify", True) or not getattr(c, "telegram", None):
        return False
    chat_key = str(getattr(m, "chat_id", "") or "")
    cooldown = max(0, int(SETTINGS.get("seller_notify_cooldown", 5))) * 60
    now = time.time()
    with LOCK:
        last = float(SELLER_NOTIFY_AT.get(chat_key, 0.0) or 0.0)
        last_reason = str(SELLER_NOTIFY_AT.get(f"{chat_key}:reason", "") or "")
        if cooldown and last_reason == reason and now - last < cooldown:
            return True
        SELLER_NOTIFY_AT[chat_key] = now
        SELLER_NOTIFY_AT[f"{chat_key}:reason"] = reason
    buyer_name = _safe_for_notify(str(getattr(m, "chat_name", "") or getattr(m, "author", "") or "покупатель"), 120)
    safe_buyer = _safe_for_notify(str(buyer_text or ""), 1000)
    safe_ai = _safe_for_notify(str(ai_answer or ""), 500)
    safe_reason = _safe_for_notify(str(reason or ""), 200)
    title = header or "🆘 <b>Требуется продавец</b>"
    body = (f"{title}\n\n👤 Чат: <b>{utils.escape(buyer_name)}</b>\n"
            f"💬 Сообщение покупателя:\n<code>{utils.escape(safe_buyer)}</code>")
    if safe_ai: body += f"\n\n🤖 Ответ AI:\n<i>{utils.escape(safe_ai)}</i>"
    if safe_reason: body += f"\n\n🧠 Причина: <i>{utils.escape(safe_reason)}</i>"
    keyboard = None
    try:
        callback = f"{CBT.SEND_FP_MESSAGE}:{getattr(m, 'chat_id', '')}:{buyer_name}"
        if len(callback.encode("utf-8")) <= 64:
            keyboard = K().add(B("✉️ Ответить покупателю", callback_data=callback))
    except Exception:
        keyboard = None
    def _job():
        try:
            c.telegram.send_notification(body, keyboard=keyboard)
        except Exception:
            pass
    threading.Thread(target=_job, daemon=True, name="KBAI-notify").start()
    return True

def notify_seller_text(c, *, header, body):
    if not getattr(c, "telegram", None):
        return False
    text = f"{header}\n\n{body}"
    def _job():
        try:
            c.telegram.send_notification(text)
        except Exception:
            pass
    threading.Thread(target=_job, daemon=True, name="KBAI-order-notify").start()
    return True

def _detect_message_type_name(item):
    if item is None: return ""
    mt = getattr(item, "type", None)
    if mt is None: return ""
    name = getattr(mt, "name", "")
    if name: return str(name).upper()
    raw = str(mt)
    if "." in raw: raw = raw.rsplit(".", 1)[-1]
    return re.sub(r"[^A-Z0-9_]+", "_", raw.upper()).strip("_")

def _order_buyer_name(order):
    for attr in ("buyer_username", "buyer_name", "username"):
        v = getattr(order, attr, None)
        if v: return str(v)
    return "покупатель"

def _order_short_id(order):
    raw = str(getattr(order, "id", "") or "").strip().lstrip("#")
    if raw: return raw.upper()
    return "CHAT:" + str(getattr(order, "chat_id", "") or "?")

def _extract_order_id_from_text(text):
    m = re.search(r"#([A-Z0-9]{6,12})", str(text or ""), re.I)
    return m.group(1).upper() if m else ""

def _register_chat_order(chat_id, order_id):
    ck = str(chat_id or "")
    oid = str(order_id or "").strip().upper()
    if not ck or not oid: return
    with LOCK:
        lst = CHAT_ORDERS.setdefault(ck, [])
        if oid in lst: lst.remove(oid)
        lst.append(oid)
        if len(lst) > 10: del lst[:-10]

def _set_order_status(order_id, chat_id, status):
    oid = str(order_id or "").strip().upper()
    ck = str(chat_id or "")
    if not oid or status not in ("paid", "confirmed", "refunded"): return
    with LOCK:
        ORDER_STATUS[oid] = (status, ck, time.time())
    if ck: _register_chat_order(ck, oid)
    save_orders_state()

def _get_order_status(order_id):
    oid = str(order_id or "").strip().upper()
    if not oid: return ""
    with LOCK:
        item = ORDER_STATUS.get(oid)
    if not item: return ""
    status, _, ts = item
    if time.time() - ts > _ORDER_CLOSED_TTL: return ""
    return status

def _orders_for_prompt(chat_id, limit=3):
    ck = str(chat_id or "")
    if not ck: return []
    now = time.time()
    items = []
    with LOCK:
        for oid in CHAT_ORDERS.get(ck, []):
            item = ORDER_STATUS.get(oid)
            if not item: continue
            st, _, ts = item
            if now - ts > _ORDER_CLOSED_TTL: continue
            items.append((oid, st, ts))
    items.sort(key=lambda x: (_ORDER_PRIO.get(x[1], 3), -x[2]))
    return [(oid, st) for oid, st, _ in items[:limit]]

def _mark_order_processed(order_id):
    key = str(order_id or "").strip().upper()
    if not key: return True
    now = time.time()
    with LOCK:
        for k, ts in list(PROCESSED_ORDERS.items()):
            if now - ts > _ORDER_DEDUP_TTL: PROCESSED_ORDERS.pop(k, None)
        if key in PROCESSED_ORDERS: return False
        PROCESSED_ORDERS[key] = now
    save_orders_state()
    return True

def _mark_order_closed(order_id, chat_id="", status="confirmed"):
    key = str(order_id or "").strip().upper()
    now = time.time()
    if key:
        with LOCK:
            CLOSED_ORDERS[key] = now
            for k, ts in list(CLOSED_ORDERS.items()):
                if now - ts > _ORDER_CLOSED_TTL: CLOSED_ORDERS.pop(k, None)
        _set_order_status(key, chat_id, status)

def _is_order_closed(order_id):
    key = str(order_id or "").strip().upper()
    if not key: return False
    now = time.time()
    with LOCK:
        ts = CLOSED_ORDERS.get(key)
    return bool(ts and now - ts < _ORDER_CLOSED_TTL)

def _register_manual_fulfill(order_id, chat_id, buyer_name, title):
    oid = str(order_id or "").strip().upper()
    if not oid: return
    with LOCK:
        MANUAL_FULFILL_QUEUE[oid] = {
            "order_id": oid, "chat_id": str(chat_id or ""),
            "buyer": str(buyer_name or ""), "title": str(title or ""),
            "ts": time.time(),
        }
        cutoff = time.time() - 30 * 86400
        for k in list(MANUAL_FULFILL_QUEUE.keys()):
            if MANUAL_FULFILL_QUEUE[k].get("ts", 0) < cutoff:
                MANUAL_FULFILL_QUEUE.pop(k, None)

def _find_lot_for_order(order):
    for attr in ("lot_id", "offer_id"):
        lid = getattr(order, attr, None)
        if lid:
            with LOCK:
                lot = LOTS.get(str(lid))
            if lot: return lot
    desc = str(getattr(order, "description", "") or "").strip()
    if not desc: return None
    ranked = find_lots(desc, 2)
    if ranked:
        best_lot, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        if best_score >= 0.72 and (best_score - second_score >= 0.06 or second_score < 0.55):
            return best_lot
    return None

def load_recent_orders(c, limit=10):
    acc = getattr(c, "account", None)
    if acc is None: return 0
    orders = None
    for name in ("get_sales", "get_orders", "get_my_orders", "get_sells", "get_orders_list"):
        m = getattr(acc, name, None)
        if callable(m):
            try:
                res = m()
                if res:
                    orders = res
                    break
            except Exception:
                continue
    if not orders: return 0
    lst = getattr(orders, "orders", None)
    if lst is None:
        lst = orders if isinstance(orders, (list, tuple)) else []
    count = 0
    for o in list(lst)[:limit]:
        try:
            oid = str(getattr(o, "id", "") or "").strip().lstrip("#").upper()
            if not oid: continue
            chat_id = str(getattr(o, "chat_id", "") or getattr(o, "chat", "") or "")
            status_raw = str(getattr(o, "status", "") or "").lower()
            st = ""
            if any(k in status_raw for k in ("возврат", "refund", "return")): st = "refunded"
            elif any(k in status_raw for k in ("подтвержд", "confirmed", "завершен", "закрыт")): st = "confirmed"
            elif any(k in status_raw for k in ("оплачен", "paid", "ожидает")): st = "paid"
            if not st: continue
            current = _get_order_status(oid)
            if current and current != "paid": continue
            _set_order_status(oid, chat_id, st)
            if chat_id: _set_chat_role(chat_id, "seller")
            buyer = _order_buyer_name(o)
            if buyer and buyer != "покупатель":
                with LOCK:
                    ORDER_BUYER[oid] = buyer
            count += 1
        except Exception:
            continue
    return count

def _send_auto_thank(c, chat_id, chat_name, order_id):
    if not SETTINGS.get("auto_thank_after_payment", True): return
    if _is_order_closed(order_id): return
    if _get_order_status(order_id) in ("confirmed", "refunded"): return
    text = str(SETTINGS.get("auto_thank_text") or "").strip()
    if not text or not chat_id: return
    v = outbound_violation(text)
    if v and v != "empty":
        text = "Спасибо за оплату! 🙌"
    def _job():
        try:
            time.sleep(1.5)
            c.send_message(chat_id, text, chat_name or "покупатель", watermark=False)
            add_history(chat_id, "assistant", text)
        except Exception:
            pass
    POOL.submit(_job)

def _fulfill_paid_order(c, order):
    if not SETTINGS.get("auto_fulfill_paid_orders", False): return
    chat_id = str(getattr(order, "chat_id", "") or "")
    order_id = _order_short_id(order)
    if _is_order_closed(order_id) or _get_order_status(order_id) in ("confirmed", "refunded"):
        return
    if not chat_id: return
    buyer_name = _order_buyer_name(order)
    now = time.time()
    with LOCK:
        try:
            last_ts = float(AUTO_FULFILLED_ORDERS.get(f"{chat_id}:{order_id}", 0.0) or 0.0)
        except Exception:
            last_ts = 0.0
        if last_ts and now - last_ts < 3600: return
        AUTO_FULFILLED_ORDERS[f"{chat_id}:{order_id}"] = now
    lot = _find_lot_for_order(order)
    if lot is None:
        _register_manual_fulfill(order_id, chat_id, buyer_name, "не определён")
        if SETTINGS.get("auto_fulfill_notify_seller", True):
            notify_seller_text(c, header="⚠️ <b>ОПЛАЧЕН ЗАКАЗ — РУЧНАЯ ВЫДАЧА</b>",
                body=(f"📦 Заказ: <code>#{utils.escape(order_id)}</code>\n"
                      f"👤 Покупатель: <b>{utils.escape(buyer_name)}</b>\n"
                      f"❓ Лот не определён. Выдайте вручную."))
        return
    lid = str(lot.get("id") or "")
    title = str(lot.get("title") or lot.get("description") or f"лот #{lid}")[:120]
    payment_msg = str(lot.get("payment_message") or "").strip()
    if payment_msg:
        violation = outbound_violation(payment_msg)
        if violation and violation != "empty":
            _register_manual_fulfill(order_id, chat_id, buyer_name, title)
            if SETTINGS.get("auto_fulfill_notify_seller", True):
                notify_seller_text(c, header="⚠️ <b>ОПЛАЧЕН ЗАКАЗ — РУЧНАЯ ВЫДАЧА</b>",
                    body=(f"📦 Заказ: <code>#{utils.escape(order_id)}</code>\n"
                          f"👤 Покупатель: <b>{utils.escape(buyer_name)}</b>\n"
                          f"🎁 Лот: <b>{utils.escape(title)}</b>\n"
                          f"⚠️ payment_msg заблокирован ({violation}). Выдайте вручную."))
            return
        try:
            delay = max(0, min(60, int(SETTINGS.get("auto_fulfill_delay_sec", 3) or 0)))
            def _job():
                try:
                    time.sleep(delay)
                    c.send_message(chat_id, payment_msg, buyer_name, watermark=False)
                    add_history(chat_id, "assistant", payment_msg)
                except Exception:
                    pass
            POOL.submit(_job)
            if SETTINGS.get("auto_fulfill_notify_seller", True):
                notify_seller_text(c, header="🛒 <b>Оплачен заказ (выдача отправлена)</b>",
                    body=(f"📦 Заказ: <code>#{utils.escape(order_id)}</code>\n"
                          f"👤 Покупатель: <b>{utils.escape(buyer_name)}</b>\n"
                          f"🎁 Лот: <b>{utils.escape(title)}</b>"))
            return
        except Exception:
            pass
    _register_manual_fulfill(order_id, chat_id, buyer_name, title)
    if SETTINGS.get("manual_fulfill_notify", True) and SETTINGS.get("auto_fulfill_notify_seller", True):
        notify_seller_text(c, header="⚠️ <b>ОПЛАЧЕН ЗАКАЗ — РУЧНАЯ ВЫДАЧА</b>",
            body=(f"📦 Заказ: <code>#{utils.escape(order_id)}</code>\n"
                  f"👤 Покупатель: <b>{utils.escape(buyer_name)}</b>\n"
                  f"🎁 Лот: <b>{utils.escape(title)}</b>\n"
                  f"🚨 <b>payment_msg у лота отсутствует!</b>"))

def _handle_new_paid_order(c, order):
    if order is None: return
    order_id = _order_short_id(order)
    if not order_id or order_id.startswith("CHAT:"):
        order_id = "CHAT:" + str(getattr(order, "chat_id", "") or "?")
    if not _mark_order_processed(order_id): return
    chat_id = str(getattr(order, "chat_id", "") or "")
    if _get_order_status(order_id) in ("confirmed", "refunded"): return
    _set_order_status(order_id, chat_id, "paid")
    if chat_id: _set_chat_role(chat_id, "seller")
    buyer_name = _order_buyer_name(order)
    if buyer_name:
        with LOCK:
            ORDER_BUYER[order_id] = buyer_name
        save_orders_state()
    if SETTINGS.get("unblacklist_on_payment", True) and buyer_name:
        if is_blacklisted(buyer_name):
            if _remove_from_blacklist(buyer_name):
                try:
                    notify_seller_text(c, header="✅ <b>Покупатель удалён из ЧС (оплатил заказ)</b>",
                        body=(f"👤 Ник: <b>{utils.escape(_safe_for_notify(buyer_name, 120))}</b>\n"
                              f"📦 Заказ: <code>#{utils.escape(order_id)}</code>"))
                except Exception:
                    pass
    lot = _find_lot_for_order(order)
    title = ""
    if lot:
        lid = str(lot.get("id") or "")
        title = str(lot.get("title") or lot.get("description") or f"лот #{lid}")[:120]
    if SETTINGS.get("auto_fulfill_notify_seller", True) or SETTINGS.get("seller_notify", True):
        body = (f"📦 Заказ: <code>#{utils.escape(order_id)}</code>\n"
                f"👤 Покупатель: <b>{utils.escape(buyer_name)}</b>")
        if title: body += f"\n🎁 Лот: <b>{utils.escape(title)}</b>"
        body += ("\n⚡ Автовыдача: включена" if SETTINGS.get("auto_fulfill_paid_orders", False)
                 else "\n💬 Автовыдача выключена — выдайте вручную.")
        notify_seller_text(c, header="🛒 <b>Оплачен заказ</b>", body=body)
    _send_auto_thank(c, chat_id, str(getattr(order, "chat_name", "") or buyer_name), order_id)
    _fulfill_paid_order(c, order)

def _handle_paid_order_message(c, item):
    chat_id = str(getattr(item, "chat_id", "") or "")
    if not chat_id: return
    order = None
    getter = getattr(c, "get_order_from_object", None)
    if callable(getter):
        try: order = getter(item)
        except Exception: pass
    if order is None:
        text = str(getattr(item, "text", "") or "")
        class _PseudoOrder: pass
        order = _PseudoOrder()
        order.id = _extract_order_id_from_text(text)
        order.chat_id = chat_id
        order.chat_name = str(getattr(item, "chat_name", "") or "")
        bm = re.search(r"(?:Покупатель|The buyer)\s+@?([^\s,.]+)", text, re.I)
        order.buyer_username = bm.group(1) if bm else ""
        desc = re.sub(r"#([A-Z0-9]{6,12})", " ", text, flags=re.I)
        desc = re.sub(r"(?:Покупатель|The buyer)[^.]*\.\s*", " ", desc, flags=re.I)
        order.description = desc.strip()[:400]
    _handle_new_paid_order(c, order)

def _handle_order_confirmed(c, item):
    text = str(getattr(item, "text", "") or "")
    chat_id = str(getattr(item, "chat_id", "") or "")
    order_id = _extract_order_id_from_text(text)
    if order_id:
        _mark_order_closed(order_id, chat_id, "confirmed")
        with LOCK:
            buyer = ORDER_BUYER.get(order_id, "")
        if buyer:
            try:
                _auto_whitelist_check(c, buyer)
            except Exception:
                logger.debug("auto_whitelist_check failed", exc_info=True)
    _trigger_post_order_survey(c, item)

def _handle_order_refunded(c, item):
    text = str(getattr(item, "text", "") or "")
    chat_id = str(getattr(item, "chat_id", "") or "")
    order_id = _extract_order_id_from_text(text)
    if order_id:
        _mark_order_closed(order_id, chat_id, "refunded")

def _observe_transaction_message(c, item):
    try:
        type_name = _detect_message_type_name(item)
        text = str(getattr(item, "text", "") or "")
        chat_id = str(getattr(item, "chat_id", "") or "")
        if text and chat_id:
            if _RE_ROLE_BUYER_HINT.search(text): _set_chat_role(chat_id, "buyer")
            elif _RE_ROLE_SELLER_HINT.search(text): _set_chat_role(chat_id, "seller")
        if type_name == "ORDER_PURCHASED":
            if chat_id: _set_chat_role(chat_id, "seller")
            _handle_paid_order_message(c, item)
            return
        if type_name in {"ORDER_CONFIRMED", "ORDER_CONFIRMED_BY_ADMIN"}:
            _handle_order_confirmed(c, item); return
        if type_name in {"ORDER_REFUNDED", "ORDER_REFUND", "REFUND"}:
            _handle_order_refunded(c, item); return
        if text:
            status, oid = _parse_funpay_event(text)
            if status and oid:
                if status == "paid":
                    if _get_order_status(oid) not in ("confirmed", "refunded"):
                        _set_order_status(oid, chat_id, "paid")
                        if chat_id: _set_chat_role(chat_id, "seller")
                elif status == "refunded": _mark_order_closed(oid, chat_id, "refunded")
                elif status == "confirmed":
                    _mark_order_closed(oid, chat_id, "confirmed")
                    with LOCK:
                        buyer = ORDER_BUYER.get(oid, "")
                    if buyer:
                        try:
                            _auto_whitelist_check(c, buyer)
                        except Exception:
                            pass
                return
    except Exception:
        pass

def on_new_paid_order(c, e):
    try:
        order = getattr(e, "order", None) if hasattr(e, "order") else None
        if order is None and hasattr(e, "get_order"):
            try: order = e.get_order()
            except Exception: pass
        if order is None and hasattr(e, "id") and hasattr(e, "buyer_username"):
            order = e
        if order is None: return
        _handle_new_paid_order(c, order)
    except Exception:
        pass

def send_post_order_survey(c, chat_id, chat_name):
    if not SETTINGS.get("post_order_survey", True): return False
    survey = str(SETTINGS.get("post_order_survey_text") or "").strip()
    if not survey: return False
    try:
        c.send_message(chat_id, survey, chat_name, watermark=False)
        add_history(chat_id, "assistant", survey)
        return True
    except Exception:
        return False

def _pending_survey_get(chat_id):
    with LOCK: return bool(SURVEY_SENT.get(str(chat_id or "")))

def _pending_survey_mark(chat_id):
    key = str(chat_id or "")
    if not key: return
    with LOCK:
        SURVEY_SENT[key] = time.time()
        now = time.time()
        for k, ts in list(SURVEY_SENT.items()):
            if now - ts > 7 * 86400: SURVEY_SENT.pop(k, None)

def _trigger_post_order_survey(c, m):
    chat_id = getattr(m, "chat_id", "")
    chat_name = str(getattr(m, "chat_name", "") or "")
    if not chat_id or _pending_survey_get(chat_id): return
    def _job():
        time.sleep(3.0)
        if _pending_survey_get(chat_id): return
        _pending_survey_mark(chat_id)
        send_post_order_survey(c, chat_id, chat_name)
    POOL.submit(_job)

def _extract_url_as_data_url(url: str) -> str:
    try:
        u = str(url or "").strip()
        if not u.lower().startswith(("http://", "https://")):
            return ""
        r = requests.get(u, timeout=(6, 20), stream=True, headers={"User-Agent": UPDATE_USER_AGENT})
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and ctype not in _VISION_ALLOWED_MIME:
            return ""
        chunks = []; total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk: continue
            total += len(chunk)
            if total > _VISION_MAX_BYTES: return ""
            chunks.append(chunk)
        if not chunks: return ""
        b64 = base64.b64encode(b"".join(chunks)).decode("ascii")
        return f"data:{ctype or 'image/jpeg'};base64,{b64}"
    except Exception:
        return ""

def _extract_message_image(m):
    try:
        url = ""
        for attr in ("image_link", "image_url", "image", "photo", "preview_url",
                     "media_url", "attachment_url"):
            v = getattr(m, attr, None)
            if isinstance(v, str) and v.strip():
                url = v.strip(); break
        if not url: return ""
        return _extract_url_as_data_url(url)
    except Exception:
        return ""

def _vision_extract_lot_details(image_urls: list) -> str:
    if not image_urls or not SETTINGS.get("lot_vision_extract", True):
        return ""
    base = str(SETTINGS.get("api_url") or "").rstrip("/")
    key = str(SETTINGS.get("api_key") or "").strip()
    if key.lower().startswith("env:"):
        key = os.environ.get(key[4:].strip(), "")
    model = str(SETTINGS.get("api_model") or "").strip()
    if not base or not key or not model:
        return ""
    data_urls = []
    for u in image_urls[:3]:
        try:
            du = _extract_url_as_data_url(u)
            if du:
                data_urls.append(du)
        except Exception:
            continue
    if not data_urls:
        return ""
    content = [{"type": "text", "text": _VISION_LOT_PROMPT}]
    for du in data_urls:
        content.append({"type": "image_url", "image_url": {"url": du}})
    try:
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0.0,
                "max_tokens": 500,
                "stream": False,
            },
            timeout=(15, max(30, int(SETTINGS.get("ai_timeout", 120)))),
        )
        r.raise_for_status()
        data = _safe_json(r, "lot_vision")
        text = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not text or "не игровой скрин" in text.lower():
            return ""
        return text[:1200]
    except Exception as e:
        logger.debug("vision_extract_lot_details failed: %s", e)
        return ""

def _web_search_lite(query: str, max_results: int = 5) -> list:
    try:
        q = str(query or "").strip()[:250]
        if not q: return []
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": q, "kl": "ru-ru"},
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; KiriillBRAI/1.0)",
                "Accept-Language": "ru,en;q=0.8",
            },
            timeout=_WEB_SEARCH_TIMEOUT,
            stream=True,
        )
        r.raise_for_status()
        chunks = []; total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk: continue
            total += len(chunk)
            if total > _WEB_SEARCH_MAX_BYTES: break
            chunks.append(chunk)
        html = b"".join(chunks).decode("utf-8", errors="ignore")
        results = []
        for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>)?',
            html, re.I | re.DOTALL):
            url = m.group(1) or ""
            title = re.sub(r"<[^>]+>", "", m.group(2) or "").strip()
            snippet = re.sub(r"<[^>]+>", "", (m.group(3) or m.group(4) or "")).strip()
            um = re.search(r"uddg=([^&]+)", url)
            if um:
                try:
                    from urllib.parse import unquote
                    url = unquote(um.group(1))
                except Exception:
                    pass
            if not url.startswith(("http://", "https://")):
                continue
            results.append({
                "title": title[:200],
                "url": url[:300],
                "snippet": snippet[:500],
            })
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        logger.debug("web_search failed: %s", e)
        return []

def _format_search_results(results: list) -> str:
    if not results:
        return "(ничего не найдено)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title')}\n   {r.get('snippet')}\n   URL: {r.get('url')}")
    return "\n".join(lines)

def _message_role(c, item):
    mt = getattr(item, "type", None)
    if mt is not None and mt is not MessageTypes.NON_SYSTEM: return None
    if any(bool(getattr(item, x, False)) for x in ("is_employee", "is_support", "is_moderation", "is_arbitration")):
        return None
    acc_id = getattr(getattr(c, "account", None), "id", None)
    author_id = getattr(item, "author_id", None)
    if getattr(item, "by_bot", False) or getattr(item, "by_vertex", False): return "assistant"
    if acc_id is not None and author_id == acc_id: return "assistant"
    return "user"

def _bootstrap_chat_history(c, m, current_text):
    if not SETTINGS.get("bootstrap_history", True): return
    chat_key = str(getattr(m, "chat_id", "") or "")
    if not chat_key: return
    with LOCK:
        if chat_key in CHAT_HISTORY_BOOTSTRAPPED: return
        CHAT_HISTORY_BOOTSTRAPPED.add(chat_key)
    get_chat = getattr(getattr(c, "account", None), "get_chat", None)
    if not callable(get_chat): return
    try:
        full = get_chat(getattr(m, "chat_id", chat_key), with_history=True)
        messages = list(getattr(full, "messages", None) or [])
    except Exception:
        return
    if not messages: return
    current_id = str(getattr(m, "id", "") or "")
    current_safe = str(current_text or "").strip()
    cutoff = None
    if current_id:
        for i in range(len(messages) - 1, -1, -1):
            if str(getattr(messages[i], "id", "") or "") == current_id:
                cutoff = i; break
    if cutoff is None and current_safe:
        for i in range(len(messages) - 1, -1, -1):
            it = messages[i]
            if _message_role(c, it) != "user": continue
            if str(getattr(it, "text", "") or "").strip() == current_safe:
                cutoff = i; break
    if cutoff is None: cutoff = len(messages)
    imported = []
    for item in messages[:cutoff][-100:]:
        role = _message_role(c, item)
        if role not in ("user", "assistant"): continue
        text = str(getattr(item, "text", "") or "").strip()
        if not text: continue
        imported.append({"role": role, "content": text[:2000]})
    if not imported: return
    with LOCK:
        existing = list(HISTORY.get(chat_key, []))
        if existing:
            HISTORY[chat_key] = (list(imported) + existing[-5:])[-_HISTORY_HARD_CAP:]
        else:
            HISTORY[chat_key] = imported[-_HISTORY_HARD_CAP:]

def _recent_assistant_said_about(chat_id, pattern):
    rx = re.compile(pattern, re.I)
    with LOCK:
        h = list(HISTORY.get(str(chat_id), []))
    for item in h:
        if item.get("role") == "assistant" and rx.search(item.get("content") or ""):
            return True
    return False

_RE_DISCOUNT = re.compile(r"\bскидк\w*|\bдешевле\b|\bторг\w*|\bснизить цен\w*|\bпромокод\w*|\bакци\w*", re.I)
_RE_OTHER_LOT = re.compile(r"^(?:друг\w*|а друг\w*|ещ[её]\b|не этот|не то|хочу друг\w*)[!?., ]*$", re.I)
_RE_HELP = re.compile(r"\bпомож\w*|\bподскаж\w*|\bсмож\w* помочь", re.I)
_RE_SELLER_COUNT = re.compile(r"сколько\s+(?:лотов|товаров|объявлени\w*)", re.I)
_RE_PRESENCE = re.compile(r"^(?:(?:ты|вы|продавец)\s+)?(?:тут|здесь|на месте|на связи)[!? ]*$|^есть кто\w*[!? ]*$", re.I)
_RE_CONTEXT_LOT = re.compile(r"\b(?:этот|эта|это|эти|данный|данная|данное|данного|текущий|текущая)\s+(?:товар\w*|лот\w*)\b", re.I)
_RE_GREET = re.compile(r"^(?:привет\w*|здравствуй\w*|добрый (?:день|вечер)|доброе утро|хай|hi|hello|ку|кк|йо|ёу|салют|прив)[!., ]*$", re.I)
_RE_THANKS = re.compile(r"(?:спасибо|благодарю|спс)", re.I)
_RE_WELL = re.compile(r"\bкак (?:у (?:тебя|вас) )?дела\b|\bкак жизнь\b|\bкак настроение\b", re.I)
_RE_BYE = re.compile(r"^(?:пока|до свидания|до встречи|всего доброго)[!., ]*$", re.I)

def _apply_watermark(text):
    body = str(text or "").rstrip()
    if not SETTINGS.get("watermark", True): return body
    mark = str(SETTINGS.get("watermark_text") or "").strip()
    if not mark or mark in body: return body
    return f"{body}\n\n{mark}"

def _say(c, m, text, *, notify=False, reason="", buyer_text="", notify_header=""):
    if not text or not is_enabled(c): return False
    out = _clean_ai_answer(str(text).strip())
    v = outbound_violation(out)
    if v and v != "empty":
        out = refusal(v); notify = False
    _before = out
    out = _strip_fake_order_action(out)
    if not out:
        out = "Уточните, пожалуйста, что именно нужно."
    try:
        _chat_id = str(getattr(m, "chat_id", "") or "")
        if _chat_id and _RE_REFUND_WORD.search(out):
            _latest = _orders_for_prompt(_chat_id, limit=1)
            if _latest:
                _loid, _lst = _latest[0]
                if _lst == "paid":
                    out = f"Да, заказ #{_loid} оплачен, спасибо! Сейчас подготовлю и выдам товар."
                elif _lst == "confirmed":
                    out = f"Заказ #{_loid} подтверждён и закрыт."
    except Exception:
        pass
    final = _apply_watermark(out)
    try:
        c.send_message(m.chat_id, final, m.chat_name, watermark=False)
        add_history(m.chat_id, "assistant", out)
    except Exception:
        logger.exception("say failed"); return False
    if notify:
        notify_seller(c, m, buyer_text or "", out, reason=reason, header=notify_header)
    return True

def handle_deterministic(c, m, text):
    n = norm(text)
    if _RE_GREET.search(n):
        _say(c, m, "Здравствуйте! 👋 Чем могу помочь?"); return True
    if _RE_WELL.search(n):
        _say(c, m, "Всё хорошо, спасибо 😊"); return True
    if _RE_PRESENCE.search(n):
        _say(c, m, "Да, на связи 🤝"); return True
    if _RE_THANKS.search(n) and len(n.split()) <= 8:
        _say(c, m, "Пожалуйста! 🤝"); return True
    if _RE_BYE.search(n):
        _say(c, m, "До встречи! 👋"); return True
    if _RE_DISCOUNT.search(n):
        already = _recent_assistant_said_about(m.chat_id, r"скидк")
        if already:
            _say(c, m, "Скидка на усмотрение продавца.", notify=True,
                notify_header="🆘 <b>Покупатель повторно просит скидку</b>",
                reason="Повторная просьба о скидке", buyer_text=text); return True
        _say(c, m, "Скидка на усмотрение продавца.", notify=True,
            notify_header="🆘 <b>Покупатель просит скидку</b>",
            reason="Просьба о скидке / торг", buyer_text=text); return True
    if _RE_OTHER_LOT.fullmatch(n):
        with LOCK:
            avail = list(LOTS.values())[:8]
        if avail:
            body = "Вот доступные лоты:\n" + "\n".join(f"{i}) {l.get('title')}" for i, l in enumerate(avail, 1))
            body += "\n\nНапишите название или номер нужного."
        else:
            body = "Напишите название нужного лота."
        _say(c, m, body); return True
    if _RE_SELLER_COUNT.search(n):
        with LOCK:
            cnt = len(LOTS)
        _say(c, m, f"В профиле сейчас {cnt} лотов."); return True
    if re.search(r"возврат|верните|верни\s+деньги|refund", norm(text)):
        _say(c, m, "Возврат оформляет продавец.", notify=True,
            notify_header="🆘 <b>Покупатель просит возврат</b>",
            reason="Запрос возврата", buyer_text=text); return True
    violation = classify_policy_violation(text)
    if violation:
        _say(c, m, policy_refusal(violation)); return True
    return False

def _obj(o, a, d=""):
    try:
        v = getattr(o, a, d)
        return "" if v is None else str(v)
    except Exception:
        return d

def _extract_extra_params(field_obj):
    result = {}
    for attr in ("fields", "params", "game_params", "custom_fields", "lot_fields"):
        val = getattr(field_obj, attr, None)
        if isinstance(val, dict) and val:
            for k, v in val.items():
                if v is None or v == "" or v == [] or v == {}: continue
                result[str(k)] = v
        elif isinstance(val, list) and val:
            for item in val:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("label") or item.get("key")
                    value = item.get("value") if "value" in item else item.get("val")
                    if name and value not in (None, "", [], {}):
                        result[str(name)] = value
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    k, v = item
                    if k and v not in (None, "", [], {}):
                        result[str(k)] = v
    return result

def _lot_images_from(lot) -> list:
    imgs = []; seen = set()
    def _add(u):
        u = str(u or "").strip()
        if not u or not u.lower().startswith(("http://", "https://")): return
        if u in seen: return
        seen.add(u); imgs.append(u)
    for attr in ("images", "image_links", "preview_images", "photos",
                 "image_urls", "screens", "screenshots", "photo_links",
                 "attachment_urls", "media_urls"):
        v = getattr(lot, attr, None)
        if v is None: continue
        if isinstance(v, str): _add(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                if isinstance(x, str): _add(x)
                elif isinstance(x, dict): _add(x.get("url") or x.get("link") or x.get("src"))
                else: _add(getattr(x, "url", None) or getattr(x, "link", None))
    for attr in ("image_link", "image_url", "image", "preview_url"):
        v = getattr(lot, attr, None)
        if isinstance(v, str): _add(v)
    return imgs[:12]

def _lot_basic(lot):
    sub = getattr(lot, "subcategory", None)
    return {"id": str(getattr(lot, "id", "")),
        "title": _obj(lot, "description") or _obj(lot, "title"),
        "description": _obj(lot, "description"), "full_description": "",
        "price": getattr(lot, "price", None),
        "currency": str(getattr(lot, "currency", "") or ""),
        "amount": getattr(lot, "amount", None),
        "auto": bool(getattr(lot, "auto", False)),
        "subcategory": _obj(sub, "fullname") or _obj(sub, "name"),
        "server": _obj(lot, "server"), "extra_fields": {}, "payment_message": "",
        "image_urls": _lot_images_from(lot)}

def _enrich(c, lid):
    imgs = []
    try:
        f = c.account.get_lot_fields(int(lid) if lid.isdigit() else lid)
        with LOCK:
            if lid not in LOTS:
                return
            t = _obj(f, "title_ru") or _obj(f, "title_en")
            d = _obj(f, "description_ru") or _obj(f, "description_en")
            payment = _obj(f, "payment_msg_ru") or _obj(f, "payment_msg_en")
            if t:
                LOTS[lid]["title"] = t
            LOTS[lid]["full_description"] = d
            if payment:
                LOTS[lid]["payment_message"] = payment
            try:
                imgs = _lot_images_from(f)
                if not imgs:
                    for m in re.finditer(r"https?://[^\s\"'<>]+\.(?:jpe?g|png|webp|gif)", d or "", re.I):
                        imgs.append(m.group(0))
                if imgs:
                    LOTS[lid]["image_urls"] = imgs[:12]
            except Exception:
                pass
            if hasattr(f, "auto"):
                LOTS[lid]["auto"] = bool(getattr(f, "auto"))
            if getattr(f, "price", None) is not None:
                LOTS[lid]["price"] = f.price
            if getattr(f, "amount", None) is not None:
                LOTS[lid]["amount"] = f.amount
            extra = _extract_extra_params(f)
            if extra:
                for bad in ("payment_msg_ru", "payment_msg_en", "payment_message"):
                    extra.pop(bad, None)
                LOTS[lid]["extra_fields"] = extra

        # Vision-извлечение фактов со скринов лота (один раз, кэшируется)
        if imgs and SETTINGS.get("lot_vision_extract", True):
            with LOCK:
                cached_vision = LOT_VISION.get(str(lid), "")
            if not cached_vision:
                details = _vision_extract_lot_details(imgs)
                if details:
                    with LOCK:
                        LOT_VISION[str(lid)] = details
                    _save_lot_vision()
                    logger.info("lot %s: извлечено vision-фактов (%d симв.)", lid, len(details))
    except Exception:
        logger.debug("_enrich failed lid=%s", lid, exc_info=True)

def sync_lots(c, enrich=True):
    try:
        p = c.profile or c.account.get_user(c.account.id)
        lots = list(p.get_lots()) if p else []
    except Exception:
        logger.exception("sync_lots"); return 0
    cache = {}
    for l in lots:
        d = _lot_basic(l)
        if d["id"]: cache[d["id"]] = d
    with LOCK:
        for lid, old in LOTS.items():
            if lid in cache:
                if old.get("full_description"):
                    cache[lid]["full_description"] = old["full_description"]
                if old.get("extra_fields"):
                    cache[lid]["extra_fields"] = old["extra_fields"]
                if old.get("payment_message"):
                    cache[lid]["payment_message"] = old["payment_message"]
                if old.get("image_urls"):
                    cache[lid]["image_urls"] = old["image_urls"]
        LOTS.clear()
        LOTS.update(cache)
    if enrich:
        for lid in list(cache):
            if STOP.is_set(): break
            _enrich(c, lid)
            time.sleep(1.0)
    return len(cache)

def lot_worker(c):
    sync_lots(c, enrich=True)
    while not STOP.wait(max(60, SETTINGS["lot_refresh_minutes"] * 60)):
        if is_enabled(c):
            try: sync_lots(c, enrich=True)
            except Exception: logger.exception("lot_worker")

def add_history(chat_id, role, text):
    t = str(text or "").strip()[:3000]
    if not t: return
    with LOCK:
        h = HISTORY.setdefault(str(chat_id), [])
        h.append({"role": role, "content": t})
        if len(h) > _HISTORY_HARD_CAP: del h[:-_HISTORY_HARD_CAP]

def _history_for_api(chat_id, exclude_last_user=""):
    with LOCK:
        h = list(HISTORY.get(str(chat_id), []))
    if h and h[-1].get("role") == "user" and h[-1].get("content") == exclude_last_user:
        h = h[:-1]
    budget = max(2000, int(SETTINGS.get("history_char_budget", 12000)))
    total = 0; keep = []
    for item in reversed(h):
        ln = len(item.get("content") or "") + 8
        if total + ln > budget and keep: break
        keep.append(item); total += ln
    keep.reverse(); return keep

def _get_viewing(c, m):
    viewing = getattr(m, "buyer_viewing", None)
    if viewing and getattr(viewing, "is_viewing_lot", False): return viewing
    buyer_id = getattr(m, "interlocutor_id", None)
    if not buyer_id: return None
    key = str(buyer_id)
    now = time.time()
    with LOCK: cached = VIEWING_CACHE.get(key)
    if cached and now - cached[0] < 45: return cached[1]
    try: viewing = c.account.get_buyer_viewing(buyer_id)
    except Exception: viewing = None
    with LOCK: VIEWING_CACHE[key] = (now, viewing)
    return viewing

def _remember_chat_lot(chat_id, lot):
    if not lot: return
    key = str(chat_id or "")
    lid = str(lot.get("id") or "")
    if not key or not lid: return
    with LOCK:
        CHAT_LOT[key] = lid
        CHAT_LOT_AT[key] = time.time()

def _last_chat_lot(chat_id, ttl_seconds=1800):
    key = str(chat_id or "")
    with LOCK:
        lid = CHAT_LOT.get(key)
        seen = CHAT_LOT_AT.get(key, 0.0)
        lot = LOTS.get(lid) if lid else None
    if lot and time.time() - seen <= ttl_seconds: return lot
    if lid:
        with LOCK:
            CHAT_LOT.pop(key, None); CHAT_LOT_AT.pop(key, None)
    return None

def _get_lot(c, m, text):
    n = norm(text)
    chat_key = str(getattr(m, "chat_id", "") or "")
    # 1) Активный лот чата — главный приоритет
    prev = _last_chat_lot(chat_key, ttl_seconds=3600)
    if prev:
        ranked = find_lots(text, 3)
        if ranked and ranked[0][1] >= 0.65:
            best, score = ranked[0]
            second = ranked[1][1] if len(ranked) > 1 else 0.0
            if len(ranked) == 1 or score - second >= 0.05 or score >= 0.8:
                _remember_chat_lot(chat_key, best)
                return best
        return prev
    # 2) Поиск по тексту
    ranked = find_lots(text, 3)
    if ranked:
        best, score = ranked[0]
        if score >= 0.52:
            second = ranked[1][1] if len(ranked) > 1 else 0.0
            if len(ranked) == 1 or score - second >= 0.04 or score >= 0.8:
                _remember_chat_lot(chat_key, best)
                return best
    if _RE_CONTEXT_LOT.search(n):
        prev2 = _last_chat_lot(chat_key)
        if prev2:
            return prev2
    # 3) viewing — последний fallback
    viewing = _get_viewing(c, m)
    if viewing and getattr(viewing, "is_viewing_lot", False):
        lid = str(getattr(viewing, "lot_id", ""))
        with LOCK:
            lot = LOTS.get(lid)
        if lot:
            _remember_chat_lot(chat_key, lot)
            return lot
        try:
            if lid:
                _enrich(c, lid)
                with LOCK:
                    lot = LOTS.get(lid)
                if lot:
                    _remember_chat_lot(chat_key, lot)
                    return lot
        except Exception:
            pass
        vtext = str(getattr(viewing, "text", "") or "").strip()
        if vtext:
            ranked2 = find_lots(vtext, 1)
            if ranked2 and ranked2[0][1] >= 0.5:
                lot = ranked2[0][0]
                _remember_chat_lot(chat_key, lot)
                return lot
            synthetic = {"id": lid or "viewing", "title": vtext[:200], "description": vtext[:200],
                "full_description": "", "price": None, "currency": "", "amount": None,
                "auto": False, "subcategory": "", "server": "", "extra_fields": {},
                "payment_message": "", "image_urls": []}
            _remember_chat_lot(chat_key, synthetic)
            return synthetic
    return None

def _lot_prompt(lot):
    if not lot:
        return "Товар не определён."
    base = (f"Название: {lot.get('title') or '—'}\n"
        f"Цена: {lot.get('price')} {lot.get('currency') or ''}\n"
        f"Количество: {lot.get('amount') if lot.get('amount') is not None else '—'}\n"
        f"Автовыдача: {'да' if lot.get('auto') else 'нет'}\n"
        f"Категория: {lot.get('subcategory') or '—'}\n"
        f"Описание: {(lot.get('full_description') or lot.get('description') or '')[:1200]}")
    extra = lot.get("extra_fields") or {}
    if isinstance(extra, dict) and extra:
        lines = []
        for k, v in extra.items():
            if v is None or v == "":
                continue
            if isinstance(v, (list, tuple)):
                v = ", ".join(str(x) for x in v[:30])
            elif isinstance(v, dict):
                v = ", ".join(f"{kk}={vv}" for kk, vv in list(v.items())[:30])
            else:
                v = str(v)
            if len(v) > 400:
                v = v[:400] + "…"
            lines.append(f"- {k}: {v}")
        if lines:
            base += "\n\nИГРОВЫЕ ПАРАМЕТРЫ ЛОТА:\n" + "\n".join(lines)

    # ФАКТЫ СО СКРИНОВ ЛОТА (из vision-модели)
    lid = str(lot.get("id") or "")
    vision_details = ""
    if lid:
        with LOCK:
            vision_details = LOT_VISION.get(lid, "")
    if vision_details:
        base += ("\n\n★ ФАКТЫ, ИЗВЛЕЧЁННЫЕ СО СКРИНОВ ЛОТА (это ИСТИНА о лоте) ★\n"
                 + vision_details
                 + "\n★ КОНЕЦ ФАКТОВ СО СКРИНОВ ★")
    else:
        imgs = lot.get("image_urls") or []
        if imgs:
            base += f"\n\nВ лоте {len(imgs)} изображений (данные со скринов ещё не извлечены)."
    return base

def _chat_status_hint(chat_id):
    orders = _orders_for_prompt(chat_id, limit=3)
    if not orders: return ""
    lines = ["\nЗАКАЗЫ В ЭТОМ ЧАТЕ (свежие первыми, максимум 3):"]
    for oid, st in orders:
        lines.append(f"- #{oid} — {st} ({_STATUS_RU.get(st, st)})")
    latest_oid, latest_st = orders[0]
    lines.append(f"\nСАМЫЙ СВЕЖИЙ: #{latest_oid} — {latest_st} ({_STATUS_RU.get(latest_st, latest_st)})")
    lines.append("- paid → «Да, заказ #XXXX оплачен, спасибо!»")
    lines.append("- confirmed → «Заказ #XXXX подтверждён и закрыт.»")
    lines.append("- refunded → «Заказ #XXXX возвращён.»")
    lines.append("- НЕ оформляй заказы. Заказ оформляет покупатель сам.")
    return "\n".join(lines) + "\n"

def _role_block(chat_id, lot):
    role = _get_chat_role(chat_id, lot)
    if role == "buyer":
        extra = str(SETTINGS.get("buyer_role_prompt") or BUYER_ROLE_PROMPT).strip()
        return f"\nРЕЖИМ ЧАТА: BUYER (покупатель).\n{extra}\n"
    if role == "seller":
        return "\nРЕЖИМ ЧАТА: SELLER (продавец). Владелец бота — продавец.\n"
    return ""

def _sys_prompt(lot, full_chat, chat_id="", lang_hint="", tone_hint_text="", search_results: str = ""):
    seller = str(SETTINGS.get("seller_info") or "").strip()
    memory_note = ("Ты видишь ВСЮ историю чата. Отвечай ТОЛЬКО на последнее сообщение." if full_chat
                   else "Ты видишь последние сообщения чата.")
    viewing_note = ("В блоке ТЕКУЩИЙ ТОВАР уже передан лот. Отвечай сразу по нему." if lot
                    else "Точного лота нет — задай ОДИН короткий уточняющий вопрос.")
    extra = ""
    if lang_hint: extra += f"\nЯЗЫК ОТВЕТА:\n{lang_hint}\n"
    if tone_hint_text: extra += f"\nТОН ОТВЕТА:\n{tone_hint_text}\n"
    promises = ""
    if SETTINGS.get("no_unconfirmed_promises", True):
        promises = ("\nОБЕЩАНИЯ:\n- НИКОГДА не пиши «я помогу», «мы поможем», «продавец свяжется», "
            "«передам продавцу», «уточню у продавца».\n"
            "- Если не можешь ответить — скажи нейтрально: «Не могу подтвердить это по лоту.»\n")
    no_hallucination = (
        "\n★★★ ГЛАВНЫЕ ПРАВИЛА ★★★\n"
        "1) ОТВЕЧАЙ СТРОГО НА ЗАДАННЫЙ ВОПРОС. Не вываливай все факты подряд.\n"
        "   Спросили «какой уровень?» — отвечай только про уровень, одной строкой.\n"
        "   Спросили «есть ли скины?» — только про скины.\n"
        "2) ИСТОЧНИК ИСТИНЫ — только:\n"
        "   • блок ТЕКУЩИЙ ТОВАР,\n"
        "   • блок «ФАКТЫ, ИЗВЛЕЧЁННЫЕ СО СКРИНОВ ЛОТА» (если есть),\n"
        "   • блок «ПОДКЛЮЧЁННЫЕ ТОВАРЫ»,\n"
        "   • блок «ИНСТРУКЦИЯ ДЛЯ ЭТОГО ЛОТА».\n"
        "3) НИКОГДА не придумывай числа: уровень, ранг, часы, скины, регион, "
        "золото, даты — если это НЕ указано в источниках выше.\n"
        "4) Если факт есть в «ФАКТЫ СО СКРИНОВ ЛОТА» — называй ИМЕННО то число, "
        "что там. НЕ ЗАМЕНЯЙ его на «примерное» или «около».\n"
        "5) Если факта НЕТ ни в тексте лота, ни в фактах со скринов — "
        "ответь буквально: «В лоте эта информация не указана.» Не выдумывай.\n"
        "6) НЕ сравнивай с другими лотами профиля. Отвечай ТОЛЬКО про лот в ТЕКУЩИЙ ТОВАР.\n"
        "7) Не объясняй, откуда взял данные. Просто ответь по факту.\n"
    )
    status_hint = _chat_status_hint(chat_id)
    role_block = _role_block(chat_id, lot)
    lot_instr = ""
    if lot:
        with LOCK:
            instrs = dict(SETTINGS.get("lot_instructions") or {})
        lid = str(lot.get("id") or "").strip()
        if lid and lid in instrs:
            lot_instr = str(instrs[lid] or "").strip()
        if not lot_instr:
            ntitle = _norm_nick(lot.get("title") or "")
            if ntitle:
                for k, v in instrs.items():
                    if _norm_nick(k) == ntitle:
                        lot_instr = str(v or "").strip()
                        break
    instr_block = ""
    if lot_instr:
        instr_block = f"\n\nИНСТРУКЦИЯ ДЛЯ ЭТОГО ЛОТА (приоритет выше общих правил):\n{lot_instr}\n"
    attached_block = ""
    if lot:
        with LOCK:
            attached = dict(SETTINGS.get("lot_attached_items") or {})
        lid = str(lot.get("id") or "").strip()
        items = []
        if lid and lid in attached and isinstance(attached[lid], list):
            items = [str(x) for x in attached[lid] if str(x).strip()]
        if not items:
            ntitle = _norm_nick(lot.get("title") or "")
            if ntitle:
                for k, v in attached.items():
                    if _norm_nick(k) == ntitle and isinstance(v, list):
                        items = [str(x) for x in v if str(x).strip()]
                        break
        if items:
            attached_block = ("\n\nПОДКЛЮЧЁННЫЕ ТОВАРЫ / ФАКТЫ К ЭТОМУ ЛОТУ:\n"
                              + "\n".join(f"- {x[:300]}" for x in items[:20]) + "\n")
    search_block = ""
    if search_results:
        search_block = ("\n\nРЕЗУЛЬТАТЫ ПОИСКА В ОТКРЫТЫХ ИСТОЧНИКАХ "
                        "(используй как доп. инфо, не цитируй URL):\n" + search_results + "\n")
    return (f"{SETTINGS['system_prompt']}\n\n{role_block}\n"
        f"ПАМЯТЬ ДИАЛОГА:\n{memory_note}\n\n"
        f"КОНТЕКСТ ТОВАРА:\n{viewing_note}\n\n"
        f"ИНФОРМАЦИЯ О ПРОДАВЦЕ:\n{seller or 'не задана'}\n\n"
        f"ТЕКУЩИЙ ТОВАР:\n{_lot_prompt(lot)}"
        f"{instr_block}{attached_block}\n\n{FUNPAY_RULES_SNAPSHOT}\n\n"
        f"{status_hint}{no_hallucination}\n{promises}{extra}{search_block}\n"
        "Дополнительно:\n- «Аккаунт Standoff/Steam/CS2/Valorant/Telegram» — обычный товар.\n"
        "- Название платформы внутри товара — НЕ контакт.")

def _call_ai_api(base, key, model, msgs, timeout, temperature, max_tokens):
    r = requests.post(base + "/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": msgs, "temperature": temperature,
              "max_tokens": max_tokens, "stream": False},
        timeout=(10, max(30, int(timeout))))
    r.raise_for_status()
    data = _safe_json(r, "ask_ai")
    text = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("AI вернул пустой ответ.")
    return text

def ask_ai(m, buyer_text, lot):
    base = str(SETTINGS.get("api_url") or "").rstrip("/")
    if not base:
        raise RuntimeError("API URL не задан.")
    key = str(SETTINGS.get("api_key") or "").strip()
    if key.lower().startswith("env:"):
        key = os.environ.get(key[4:].strip(), "")
    if not key:
        raise RuntimeError("API key не задан.")
    model = str(SETTINGS.get("api_model") or "").strip()
    if not model:
        raise RuntimeError("API-модель не выбрана.")
    chat_id = getattr(m, "chat_id", "")
    history = _history_for_api(chat_id, exclude_last_user=buyer_text)
    full_chat = len(history) > 2
    lang_hint = language_hint(buyer_text)
    tone_hint_text = tone_hint(buyer_text)

    image_data_url = _extract_message_image(m)
    lot_image_urls = []
    if (SETTINGS.get("lot_images_vision", True) and lot and isinstance(lot, dict)
            and (buyer_text or "").strip() and _RE_LOT_SCREEN_ASK.search(str(buyer_text))):
        with LOCK:
            cached = LOTS.get(str(lot.get("id") or ""))
        if cached:
            lot_image_urls = list(cached.get("image_urls") or [])
        if not lot_image_urls:
            lot_image_urls = list(lot.get("image_urls") or [])
        if not lot_image_urls:
            try:
                _enrich(c, str(lot.get("id") or ""))
                with LOCK:
                    cached2 = LOTS.get(str(lot.get("id") or ""))
                if cached2:
                    lot_image_urls = list(cached2.get("image_urls") or [])
            except Exception:
                pass
    lot_image_data_urls = []
    if not image_data_url and lot_image_urls:
        for u in lot_image_urls[:3]:
            try:
                du = _extract_url_as_data_url(u)
                if du:
                    lot_image_data_urls.append(du)
            except Exception:
                continue
    effective = buyer_text
    if not image_data_url and lot_image_data_urls:
        effective = (effective or "").strip() or "Посмотри, пожалуйста, на скрины лота и ответь."
        if "скрин" not in effective.lower():
            effective = (effective + "\n\n(Ниже — скриншоты из лота. Отвечай на основе ЭТИХ "
                         "изображений и полей лота. Не выдумывай данные, которых на них нет.)")

    msgs = [{"role": "system", "content": _sys_prompt(lot, full_chat, chat_id, lang_hint, tone_hint_text)}]
    msgs += history
    if image_data_url:
        msgs.append({"role": "user", "content": [
            {"type": "text", "text": effective},
            {"type": "image_url", "image_url": {"url": image_data_url}}]})
    elif lot_image_data_urls:
        content = [{"type": "text", "text": effective}]
        for du in lot_image_data_urls[:3]:
            content.append({"type": "image_url", "image_url": {"url": du}})
        msgs.append({"role": "user", "content": content})
    else:
        msgs.append({"role": "user", "content": effective})

    temperature = float(SETTINGS["temperature"])
    max_tokens = int(SETTINGS["num_predict"])
    timeout = SETTINGS["ai_timeout"]
    first = _call_ai_api(base, key, model, msgs, timeout, temperature, max_tokens)

    if SETTINGS.get("web_search_enabled", True):
        msearch = _RE_SEARCH_MARKER.search(first)
        if msearch:
            query = msearch.group(1).strip()[:250]
            try:
                max_res = max(1, min(10, int(SETTINGS.get("web_search_max_results", 5))))
            except Exception:
                max_res = 5
            results = _web_search_lite(query, max_res)
            if results:
                search_text = _format_search_results(results)
                msgs2 = [{"role": "system",
                          "content": _sys_prompt(lot, full_chat, chat_id, lang_hint,
                                                 tone_hint_text, search_results=search_text)}]
                msgs2 += history
                msgs2.append({"role": "user", "content": effective})
                msgs2.append({"role": "assistant", "content": first})
                msgs2.append({"role": "user",
                              "content": "Используй результаты поиска выше и дай финальный "
                                         "краткий ответ покупателю (без упоминаний URL, без "
                                         "обещаний, без маркеров)."})
                try:
                    final = _call_ai_api(base, key, model, msgs2, timeout, temperature, max_tokens)
                    if final:
                        final = _RE_SEARCH_MARKER.sub("", final).strip()
                        return final or first
                except Exception:
                    pass
            return _RE_SEARCH_MARKER.sub("", first).strip() or first
    return _RE_SEARCH_MARKER.sub("", first).strip() or first

def handle_message(c, m, text):
    wl = is_whitelisted(
        _extract_nick_from_message(m),
        getattr(m, "author", None),
        getattr(m, "username", None),
        getattr(m, "chat_name", None),
        getattr(m, "interlocutor_username", None),
    )
    if _is_jailbreak_attempt(text):
        _instant_blacklist(c, m, "Джейлбрейк / попытка взлома AI", text)
        _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
        return
    if _auto_blacklist_indecent(c, m, text):
        _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
        return
    violation = classify_policy_violation(text)
    if violation:
        _instant_blacklist(c, m, f"Нарушение правил: {violation}", text)
        _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
        return
    if not wl:
        if _is_code_request(text):
            _instant_blacklist(c, m, "Просьба написать код / программу", text)
            _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
            return
        if _is_bad_intent(text):
            _instant_blacklist(c, m, "Плохой умысел (обман/обход/шантаж/угрозы)", text)
            _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
            return
        try:
            if _is_chat_goal_bad(getattr(m, "chat_id", "")):
                _instant_blacklist(c, m, "Плохая цель чата (по истории)", text)
                _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
                return
        except Exception:
            pass
        if _track_suspicious(c, m, text):
            _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
            return
        if is_offtopic(text):
            _instant_blacklist(c, m, "Оффтоп (не по теме товара)", text)
            _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
            return
    if handle_deterministic(c, m, text):
        return
    lot = _get_lot(c, m, text)
    try:
        answer = ask_ai(m, text, lot)
    except Exception as e:
        logger.warning("AI fail: %s: %s", type(e).__name__, e)
        _say(c, m, str(SETTINGS["unknown_reply"]), notify=True,
            notify_header="🆘 <b>AI-провайдер не ответил</b>",
            reason="API недоступен", buyer_text=text)
        return
    if _is_forbidden_photo_response(answer, text):
        if not wl:
            _instant_blacklist(c, m, "Запрещённое фото или отказ AI от описания", answer)
        _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
        return
    if is_offtopic(answer) and not wl:
        _instant_blacklist(c, m, "AI ответил оффтопом", text)
        _say(c, m, "Извините, я не могу помочь с этим.", notify=False)
        return
    uncertain = is_uncertain_answer(answer)
    header = ""; reason = ""
    if uncertain:
        header = "🆘 <b>AI не смог ответить уверенно</b>"
        reason = "AI не уверен"
    extra_trigger = False
    na = norm(answer)
    if not uncertain and SETTINGS.get("confidence_notify", True):
        if re.search(r"скидк|бонус|промокод|акци", na) and re.search(
            r"усмотрени|продавц|не\s+указан", na):
            extra_trigger = True
            header = "🆘 <b>AI упомянул скидку/бонус</b>"
            reason = "AI ответил про скидку/бонус"
    notify = bool((uncertain or extra_trigger) and SETTINGS.get("confidence_notify", True))
    if notify and SETTINGS.get("notify_only_when_called", True):
        buyer_calls = bool(_RE_CALL_SELLER.search(text or ""))
        problem_topic = bool(re.search(
            r"возврат|спор|жалоб|претенз|обман|кидал|скам|refund|chargeback",
            norm(text), re.I))
        if not (buyer_calls or problem_topic):
            notify = False
    _say(c, m, answer, notify=notify, notify_header=header, reason=reason, buyer_text=text)

def _drain(chat):
    while True:
        with LOCK:
            q = QUEUES.get(chat)
            if STOP.is_set() or not q:
                QUEUES.pop(chat, None)
                ACTIVE.discard(chat)
                return
            c, m, text = q.popleft()
        try:
            delay = max(0.0, float(SETTINGS.get("response_delay", 0.3)))
            if delay: time.sleep(delay)
            _bootstrap_chat_history(c, m, text)
            add_history(chat, "user", text)
            handle_message(c, m, text)
        except Exception:
            logger.exception("queue handler chat=%s", chat)

def _enqueue(c, m, text):
    chat = str(getattr(m, "chat_id", "") or "")
    if not chat or STOP.is_set(): return
    if not str(text or "").strip() and not _message_has_photo(m): return
    start = False
    with LOCK:
        QUEUES.setdefault(chat, deque()).append((c, m, str(text or "").strip()))
        if chat not in ACTIVE:
            ACTIVE.add(chat); start = True
    if start:
        try: POOL.submit(_drain, chat)
        except RuntimeError:
            with LOCK:
                QUEUES.pop(chat, None); ACTIVE.discard(chat)

def _mark(mid):
    k = str(mid); now = time.time()
    with LOCK:
        for kk, ts in list(DONE.items()):
            if now - ts > 600: DONE.pop(kk, None)
        if k in DONE: return False
        DONE[k] = now
    return True

def on_message(c, e):
    if not is_enabled(c): return
    m = e.message
    _observe_transaction_message(c, m)
    if getattr(c, "old_mode_enabled", False): return
    if getattr(m, "author_id", 0) in (0, getattr(c.account, "id", None)): return
    if getattr(m, "by_bot", False) or getattr(m, "by_vertex", False): return
    if getattr(m, "type", None) is not MessageTypes.NON_SYSTEM: return
    if any(bool(getattr(m, x, False)) for x in ("is_employee", "is_support", "is_moderation", "is_arbitration", "is_autoreply")):
        return
    if getattr(m, "chat_name", None) in getattr(c, "blacklist", []): return
    if is_blacklisted(
        _extract_nick_from_message(m), getattr(m, "author", None),
        getattr(m, "username", None), getattr(m, "chat_name", None),
        getattr(m, "interlocutor_username", None)):
        return
    try:
        if e.stack and m.id != e.stack.get_stack()[-1].message.id: return
    except Exception:
        pass
    if not _mark(getattr(m, "id", f"{m.chat_id}:{time.time_ns()}")): return
    text = (getattr(m, "text", None) or "").strip()
    has_image = _message_has_photo(m)
    if text or has_image:
        _enqueue(c, m, text)

def on_last_chat(c, e):
    if not is_enabled(c) or not getattr(c, "old_mode_enabled", False): return
    ch = getattr(e, "chat", None)
    if ch is None or not getattr(ch, "unread", False): return
    if getattr(ch, "last_by_bot", False) or getattr(ch, "last_by_vertex", False): return
    if getattr(ch, "last_message_type", None) is not MessageTypes.NON_SYSTEM: return
    if getattr(ch, "name", None) in getattr(c, "blacklist", []): return
    if is_blacklisted(
        getattr(ch, "name", None), getattr(ch, "username", None),
        getattr(ch, "interlocutor_username", None)):
        return
    def job():
        try:
            full = c.account.get_chat(ch.id, with_history=True)
            msgs = list(getattr(full, "messages", None) or [])
            if not msgs: return
            m = msgs[-1]
            _observe_transaction_message(c, m)
            if getattr(m, "author_id", 0) in (0, getattr(c.account, "id", None)): return
            if not getattr(m, "buyer_viewing", None) and getattr(full, "looking_link", None):
                try:
                    m.buyer_viewing = BuyerViewing(getattr(m, "interlocutor_id", None) or 0,
                        full.looking_link, getattr(full, "looking_text", None), None)
                except Exception:
                    pass
            text = (getattr(m, "text", None) or "").strip()
            has_image = _message_has_photo(m)
            if (text or has_image) and _mark(getattr(m, "id", f"legacy:{ch.id}")):
                _enqueue(c, m, text)
        except Exception:
            logger.exception("legacy handler")
    POOL.submit(job)

def init_telegram(cardinal):
    load_config()
    if not cardinal.telegram: return
    tg, bot = cardinal.telegram, cardinal.telegram.bot
    PROMPT_BUFFER = {"text": "", "msg_id": None}

    def _role_ru(role):
        return {"buyer": "🛒 Покупатель", "seller": "🏪 Продавец",
                "auto": "🎭 Авто"}.get(role, "❔ Не задано")

    def main_text():
        with LOCK:
            n_chats = len(HISTORY)
            n_msgs = sum(len(h) for h in HISTORY.values())
            n_status = len(ORDER_STATUS)
            n_manual = len(MANUAL_FULFILL_QUEUE)
            n_role_s = sum(1 for r in CHAT_ROLE.values() if r == "seller")
            n_role_b = sum(1 for r in CHAT_ROLE.values() if r == "buyer")
            n_vision = len(LOT_VISION)
        head = f"🤖 <b>{NAME} v{VERSION}</b>\n"
        head += f"Автор: <b>{CREDITS}</b>\n\n"
        head += f"🟢 Автоответ: <b>{utils.bool_to_text(SETTINGS['enabled'])}</b> · "
        head += f"🔔 Уведомл: <b>{utils.bool_to_text(SETTINGS.get('seller_notify', True))}</b>\n"
        head += f"🌐 Модель: <code>{utils.escape(str(SETTINGS.get('api_model') or '—'))}</code> · "
        head += f"🔑 Ключ: <b>{'задан' if SETTINGS.get('api_key') else 'нет'}</b>\n"
        head += f"🛍 Лотов: <b>{len(LOTS)}</b> · 👁 vision-фактов: <b>{n_vision}</b>\n"
        head += f"📌 Заказов: <b>{n_status}</b> · ⚠️ ручных: <b>{n_manual}</b>\n"
        head += f"💬 Память: <b>{n_chats}</b> чатов / <b>{n_msgs}</b> сообщений\n"
        head += f"🎭 Роли: 🏪 <b>{n_role_s}</b> · 🛒 <b>{n_role_b}</b>\n"
        head += f"🔄 Обновления: <b>{utils.escape(update_status_line())}</b>\n\n"
        head += "<i>Выберите раздел ↓</i>"
        return head

    def main_kb():
        kb = K(row_width=2)
        kb.row(B(f"🟢 Автоответ {utils.bool_to_text(SETTINGS['enabled'])}", callback_data=f"{CB}:tog"),
               B(f"🔔 Уведомл. {utils.bool_to_text(SETTINGS.get('seller_notify', True))}", callback_data=f"{CB}:notify"))
        kb.row(B("🌐 API и модель", callback_data=f"{CB}:m:api"),
               B("📝 Промпт и ответы", callback_data=f"{CB}:m:replies"))
        kb.row(B("🛒 Заказы и выдача", callback_data=f"{CB}:m:orders"),
               B("🏷 Лоты и товары", callback_data=f"{CB}:m:lots"))
        kb.row(B("🎭 Роли чатов", callback_data=f"{CB}:m:roles"),
               B(f"🚫 ЧС / ✅ WL ({len(get_blacklist())}/{len(get_whitelist())})",
                 callback_data=f"{CB}:m:bl"))
        kb.row(B(f"🔄 Обновления: {update_status_line()[:20]}", callback_data=f"{CB}:m:update"),
               B("⚙️ Прочее", callback_data=f"{CB}:m:misc"))
        kb.add(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        return kb

    def show(call):
        try:
            bot.edit_message_text(main_text(), call.message.chat.id, call.message.id, reply_markup=main_kb())
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_text(call, text, back_cb=f"{CB}:main", kb_override=None):
        kb = kb_override if kb_override else K().add(B("◀️ Назад", callback_data=back_cb))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            try:
                bot.send_message(call.message.chat.id, text, reply_markup=kb)
                bot.answer_callback_query(call.id)
            except Exception:
                pass

    def show_api(call):
        text = (
            f"🌐 <b>API и модель</b>\n\n"
            f"🌐 URL: <code>{utils.escape(str(SETTINGS.get('api_url') or '—'))}</code>\n"
            f"🔑 Ключ: <b>{'задан' if SETTINGS.get('api_key') else 'не задан'}</b>\n"
            f"🧠 Модель: <code>{utils.escape(str(SETTINGS.get('api_model') or 'не выбрана'))}</code>\n"
            f"⏱ Timeout: <b>{SETTINGS.get('ai_timeout', 120)} сек</b>\n"
            f"📏 Бюджет истории: <b>{SETTINGS.get('history_char_budget', 12000)}</b>\n"
            f"🌡 Temperature: <b>{SETTINGS.get('temperature', 0.25)}</b>"
        )
        kb = K(row_width=2)
        kb.row(B("🌐 URL", callback_data=f"{CB}:url"), B("🔑 API key", callback_data=f"{CB}:key"))
        kb.row(B("🧠 Модель", callback_data=f"{CB}:model"), B("⏱ Timeout", callback_data=f"{CB}:timeout"))
        kb.row(B("📏 Бюджет истории", callback_data=f"{CB}:budget"),
               B("🧪 Тест API", callback_data=f"{CB}:test"))
        kb.add(B("🖼 Тест фото", callback_data=f"{CB}:testphoto"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_replies(call):
        text = (
            f"📝 <b>Промпт и ответы</b>\n\n"
            f"💧 Водяной знак: <b>{utils.bool_to_text(SETTINGS.get('watermark', True))}</b>\n"
            f"     <i>{utils.escape(str(SETTINGS.get('watermark_text') or '—'))}</i>\n"
            f"🌍 Язык покупателя: <b>{utils.bool_to_text(SETTINGS.get('match_language', True))}</b>\n"
            f"🧊 Нейтральный тон: <b>{utils.bool_to_text(SETTINGS.get('neutral_on_anger', True))}</b>\n"
            f"🚫 Без обещаний: <b>{utils.bool_to_text(SETTINGS.get('no_unconfirmed_promises', True))}</b>\n"
            f"🔔 Уведомл. о неуверенных: <b>{utils.bool_to_text(SETTINGS.get('confidence_notify', True))}</b>\n"
            f"🔍 Web-поиск: <b>{utils.bool_to_text(SETTINGS.get('web_search_enabled', True))}</b> · "
            f"<b>{SETTINGS.get('web_search_max_results', 5)}</b> рез."
        )
        kb = K(row_width=2)
        kb.add(B("📝 Редактировать промпт", callback_data=f"{CB}:prompt"))
        kb.add(B("🏪 Данные о продавце", callback_data=f"{CB}:seller"))
        kb.row(B(f"💧 Знак {utils.bool_to_text(SETTINGS.get('watermark', True))}", callback_data=f"{CB}:wm"),
               B("✏️ Текст знака", callback_data=f"{CB}:wmtext"))
        kb.row(B(f"🌍 Язык {utils.bool_to_text(SETTINGS.get('match_language', True))}", callback_data=f"{CB}:lang"),
               B(f"🧊 Тон {utils.bool_to_text(SETTINGS.get('neutral_on_anger', True))}", callback_data=f"{CB}:tone"))
        kb.row(B(f"🚫 Без обещаний {utils.bool_to_text(SETTINGS.get('no_unconfirmed_promises', True))}",
                 callback_data=f"{CB}:nopromise"),
               B(f"🔔 Неувер. {utils.bool_to_text(SETTINGS.get('confidence_notify', True))}",
                 callback_data=f"{CB}:confnotify"))
        kb.row(B(f"🔍 Web-поиск {utils.bool_to_text(SETTINGS.get('web_search_enabled', True))}",
                 callback_data=f"{CB}:tog:websearch"),
               B(f"🔢 Результатов: {SETTINGS.get('web_search_max_results', 5)}",
                 callback_data=f"{CB}:cycle:webres"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_orders_menu(call):
        with LOCK:
            n_manual = len(MANUAL_FULFILL_QUEUE)
        text = (
            f"🛒 <b>Заказы и выдача</b>\n\n"
            f"⚡ Автовыдача: <b>{utils.bool_to_text(SETTINGS.get('auto_fulfill_paid_orders', False))}</b> "
            f"(задержка <b>{SETTINGS.get('auto_fulfill_delay_sec', 3)}с</b>)\n"
            f"⚠️ Ручная выдача: <b>{utils.bool_to_text(SETTINGS.get('manual_fulfill_notify', True))}</b> "
            f"· очередь: <b>{n_manual}</b>\n"
            f"🔔 Уведомл. о заказе: <b>{utils.bool_to_text(SETTINGS.get('auto_fulfill_notify_seller', True))}</b>\n"
            f"🔔 Только-при-зове: <b>{utils.bool_to_text(SETTINGS.get('notify_only_when_called', True))}</b> · "
            f"cooldown: <b>{SETTINGS.get('seller_notify_cooldown', 5)} мин</b>\n"
            f"🙏 Благодарность: <b>{utils.bool_to_text(SETTINGS.get('auto_thank_after_payment', True))}</b>\n"
            f"📊 Опрос после заказа: <b>{utils.bool_to_text(SETTINGS.get('post_order_survey', True))}</b>"
        )
        kb = K(row_width=2)
        kb.row(B(f"🛒 Автовыдача {utils.bool_to_text(SETTINGS.get('auto_fulfill_paid_orders', False))}",
                 callback_data=f"{CB}:autofulfill"),
               B(f"⚠️ Ручная {utils.bool_to_text(SETTINGS.get('manual_fulfill_notify', True))}",
                 callback_data=f"{CB}:tog:manual"))
        kb.row(B(f"⏱ Задержка: {SETTINGS.get('auto_fulfill_delay_sec', 3)}с",
                 callback_data=f"{CB}:autofulfilldelay"),
               B(f"🔔 О заказе {utils.bool_to_text(SETTINGS.get('auto_fulfill_notify_seller', True))}",
                 callback_data=f"{CB}:autofulfillnotify"))
        kb.row(B(f"🔔 Только-при-зове {utils.bool_to_text(SETTINGS.get('notify_only_when_called', True))}",
                 callback_data=f"{CB}:tog:called"),
               B("⏱ Cooldown", callback_data=f"{CB}:cooldown"))
        kb.row(B(f"🙏 Спасибо {utils.bool_to_text(SETTINGS.get('auto_thank_after_payment', True))}",
                 callback_data=f"{CB}:thank"),
               B("✏️ Текст благодарности", callback_data=f"{CB}:thanktext"))
        kb.row(B(f"📊 Опрос {utils.bool_to_text(SETTINGS.get('post_order_survey', True))}",
                 callback_data=f"{CB}:survey"),
               B("✏️ Текст опроса", callback_data=f"{CB}:surveytext"))
        kb.add(B("🗑 Сбросить статусы заказов", callback_data=f"{CB}:resetstatus"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_lots_menu(call):
        with LOCK:
            n_instr = len(SETTINGS.get("lot_instructions") or {})
            n_items = sum(len(v) for v in (SETTINGS.get("lot_attached_items") or {}).values() if isinstance(v, list))
            n_vision = len(LOT_VISION)
        text = (
            f"🏷 <b>Лоты и товары</b>\n\n"
            f"🛍 Лотов в кэше: <b>{len(LOTS)}</b>\n"
            f"🔄 Авто-обновление: <b>{SETTINGS.get('lot_refresh_minutes', 30)} мин</b>\n"
            f"🖼 Vision лота: <b>{utils.bool_to_text(SETTINGS.get('lot_images_vision', True))}</b>\n"
            f"👁 Vision-факты со скринов: <b>{n_vision}</b> лотов\n"
            f"📝 Инструкций для лотов: <b>{n_instr}</b>\n"
            f"📦 Товаров/фактов на лоты: <b>{n_items}</b>"
        )
        kb = K(row_width=2)
        kb.row(B("🔄 Обновить лоты", callback_data=f"{CB}:lots"),
               B("👁 Переоценить vision", callback_data=f"{CB}:vision_refresh"))
        kb.row(B(f"🖼 Vision лота {utils.bool_to_text(SETTINGS.get('lot_images_vision', True))}",
                 callback_data=f"{CB}:tog:lotvision"),
               B(f"📝 Инструкции ({n_instr})", callback_data=f"{CB}:lins:list"))
        kb.row(B("➕ Инструкция", callback_data=f"{CB}:lins:add"),
               B("🗑 Удалить инструкцию", callback_data=f"{CB}:lins:del"))
        kb.row(B(f"📦 Товары ({n_items})", callback_data=f"{CB}:litem:list"),
               B("➕ Подключить товар", callback_data=f"{CB}:litem:add"))
        kb.row(B("🗑 Удалить товар", callback_data=f"{CB}:litem:del"),
               B("📜 Bootstrap истории", callback_data=f"{CB}:bootstrap"))
        kb.add(B("📋 Логи чатов", callback_data=f"{CB}:chats"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_roles(call):
        with LOCK:
            n_role_s = sum(1 for r in CHAT_ROLE.values() if r == "seller")
            n_role_b = sum(1 for r in CHAT_ROLE.values() if r == "buyer")
        text = (
            f"🎭 <b>Роли чатов</b>\n\n"
            f"🏪 Seller: <b>{n_role_s}</b> · 🛒 Buyer: <b>{n_role_b}</b>\n"
            f"🎭 Режим по умолчанию: <b>{utils.escape(_role_ru(SETTINGS.get('default_chat_role')))}</b>\n"
            f"🔍 Авто-детект: <b>{utils.bool_to_text(SETTINGS.get('role_detection_enabled', True))}</b>"
        )
        kb = K(row_width=2)
        kb.row(B(f"🎭 Режим: {_role_ru(SETTINGS.get('default_chat_role'))}",
                 callback_data=f"{CB}:role_default"),
               B(f"🔍 Детект {utils.bool_to_text(SETTINGS.get('role_detection_enabled', True))}",
                 callback_data=f"{CB}:role_toggle"))
        kb.add(B("🎭 Назначить вручную", callback_data=f"{CB}:role_set_chat"))
        kb.add(B("🧹 Сбросить роли чатов", callback_data=f"{CB}:roles_reset"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_bl_wl(call):
        bl_n = len(get_blacklist())
        wl_n = len(get_whitelist())
        try:
            thr = int(SETTINGS.get("auto_whitelist_after_orders", 3))
        except Exception:
            thr = 3
        text = (
            f"🚫 <b>Чёрный / Белый список</b>\n\n"
            f"🚫 ЧС: <b>{bl_n}</b> ников · вкл: <b>{utils.bool_to_text(SETTINGS.get('blacklist_enabled', True))}</b>\n"
            f"   · авто-блок: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_enabled', True))}</b>\n"
            f"   · авто-разбан при оплате: <b>{utils.bool_to_text(SETTINGS.get('unblacklist_on_payment', True))}</b>\n\n"
            f"✅ WL: <b>{wl_n}</b> ников · вкл: <b>{utils.bool_to_text(SETTINGS.get('whitelist_enabled', True))}</b>\n"
            f"   · авто-добавление после <b>{thr}</b> заказов"
        )
        kb = K(row_width=2)
        kb.row(B(f"🚫 Чёрный список ({bl_n})", callback_data=f"{CB}:bl"),
               B(f"✅ Белый список ({wl_n})", callback_data=f"{CB}:wl"))
        kb.row(B(f"🚫 ЧС вкл {utils.bool_to_text(SETTINGS.get('blacklist_enabled', True))}",
                 callback_data=f"{CB}:bl_toggle"),
               B(f"✅ WL вкл {utils.bool_to_text(SETTINGS.get('whitelist_enabled', True))}",
                 callback_data=f"{CB}:wl_toggle"))
        kb.row(B(f"♻️ Разбан при оплате {utils.bool_to_text(SETTINGS.get('unblacklist_on_payment', True))}",
                 callback_data=f"{CB}:unbl_onpay"),
               B(f"🔢 Порог WL: {thr}", callback_data=f"{CB}:wl:cycle"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def show_misc(call):
        text = (
            f"⚙️ <b>Прочее</b>\n\n"
            f"📋 Правила FunPay и стоп-лист — в системном промпте.\n"
            f"💬 Память диалогов: <b>{len(HISTORY)}</b> чатов\n"
            f"📌 Заказов в базе: <b>{len(ORDER_STATUS)}</b>\n"
            f"👥 Счётчиков покупателей: <b>{len(BUYER_ORDERS_COUNT)}</b>\n"
            f"👁 Vision-фактов лотов: <b>{len(LOT_VISION)}</b>"
        )
        kb = K(row_width=2)
        kb.row(B("📋 Правила FunPay", callback_data=f"{CB}:rules"),
               B("🧪 Уведомить сейчас", callback_data=f"{CB}:notify_test"))
        kb.add(B("🗑 Сбросить всю память", callback_data=f"{CB}:clear_history"))
        kb.add(B("🗑 Сбросить счётчики заказов", callback_data=f"{CB}:wipe_counts"))
        kb.add(B("🗑 Сбросить vision-кэш", callback_data=f"{CB}:wipe_vision"))
        kb.add(B("◀️ В меню", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def toggle(call):
        SETTINGS["enabled"] = not SETTINGS["enabled"]; save_config(); show(call)
    def toggle_wm(call):
        SETTINGS["watermark"] = not bool(SETTINGS.get("watermark", True)); save_config(); show_replies(call)
    def toggle_notify(call):
        SETTINGS["seller_notify"] = not bool(SETTINGS.get("seller_notify", True)); save_config(); show(call)
    def toggle_bootstrap(call):
        SETTINGS["bootstrap_history"] = not bool(SETTINGS.get("bootstrap_history", True)); save_config(); show_lots_menu(call)
    def toggle_lang(call):
        SETTINGS["match_language"] = not bool(SETTINGS.get("match_language", True)); save_config(); show_replies(call)
    def toggle_tone(call):
        SETTINGS["neutral_on_anger"] = not bool(SETTINGS.get("neutral_on_anger", True)); save_config(); show_replies(call)
    def toggle_nopromise(call):
        SETTINGS["no_unconfirmed_promises"] = not bool(SETTINGS.get("no_unconfirmed_promises", True)); save_config(); show_replies(call)
    def toggle_confnotify(call):
        SETTINGS["confidence_notify"] = not bool(SETTINGS.get("confidence_notify", True)); save_config(); show_replies(call)
    def toggle_thank(call):
        SETTINGS["auto_thank_after_payment"] = not bool(SETTINGS.get("auto_thank_after_payment", True)); save_config(); show_orders_menu(call)
    def toggle_autofulfill(call):
        SETTINGS["auto_fulfill_paid_orders"] = not bool(SETTINGS.get("auto_fulfill_paid_orders", False)); save_config(); show_orders_menu(call)
    def toggle_autofulfill_notify(call):
        SETTINGS["auto_fulfill_notify_seller"] = not bool(SETTINGS.get("auto_fulfill_notify_seller", True)); save_config(); show_orders_menu(call)
    def toggle_survey(call):
        SETTINGS["post_order_survey"] = not bool(SETTINGS.get("post_order_survey", True)); save_config(); show_orders_menu(call)
    def toggle_unbl_onpay(call):
        SETTINGS["unblacklist_on_payment"] = not bool(SETTINGS.get("unblacklist_on_payment", True)); save_config(); show_bl_wl(call)
    def toggle_role_detection(call):
        SETTINGS["role_detection_enabled"] = not bool(SETTINGS.get("role_detection_enabled", True)); save_config(); show_roles(call)
    def cycle_role_default(call):
        cur = str(SETTINGS.get("default_chat_role") or "auto").lower()
        order = ["auto", "seller", "buyer"]
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "auto"
        SETTINGS["default_chat_role"] = nxt; save_config()
        try: bot.answer_callback_query(call.id, f"Режим: {_role_ru(nxt)}")
        except Exception: pass
        show_roles(call)
    def reset_roles(call):
        with LOCK: CHAT_ROLE.clear()
        save_orders_state()
        try: bot.answer_callback_query(call.id, "🧹 Роли сброшены")
        except Exception: pass
        show_roles(call)
    def toggle_called(call):
        SETTINGS["notify_only_when_called"] = not bool(SETTINGS.get("notify_only_when_called", True))
        save_config(); show_orders_menu(call)
    def toggle_lotvision(call):
        SETTINGS["lot_images_vision"] = not bool(SETTINGS.get("lot_images_vision", True))
        save_config(); show_lots_menu(call)
    def toggle_manual(call):
        SETTINGS["manual_fulfill_notify"] = not bool(SETTINGS.get("manual_fulfill_notify", True))
        save_config(); show_orders_menu(call)
    def toggle_websearch(call):
        SETTINGS["web_search_enabled"] = not bool(SETTINGS.get("web_search_enabled", True))
        save_config(); show_replies(call)
    def cycle_webres(call):
        cur = int(SETTINGS.get("web_search_max_results", 5))
        SETTINGS["web_search_max_results"] = {3: 5, 5: 8, 8: 3}.get(cur, 5)
        save_config(); show_replies(call)

    def show_whitelist(call):
        with LOCK:
            raw = list(SETTINGS.get("whitelist") or [])
        try:
            thr = int(SETTINGS.get("auto_whitelist_after_orders", 3))
        except Exception:
            thr = 3
        lines = ["✅ <b>Белый список покупателей</b>", "",
            f"Статус: <b>{utils.bool_to_text(SETTINGS.get('whitelist_enabled', True))}</b>",
            f"Авто-добавление после <b>{thr}</b> подтверждённых заказов",
            f"Всего: <b>{len(raw)}</b>", ""]
        if raw:
            for i, n in enumerate(sorted(raw, key=lambda x: str(x).lower()), 1):
                cnt = BUYER_ORDERS_COUNT.get(_norm_nick(n), 0)
                lines.append(f"{i}. <code>{utils.escape(str(n))}</code> · заказов: <b>{cnt}</b>")
        else:
            lines.append("<i>Список пуст.</i>")
        kb = K(row_width=2)
        kb.row(B("➕ Добавить", callback_data=f"{CB}:wl_add"),
               B("➖ Удалить", callback_data=f"{CB}:wl_del"))
        kb.row(B("🗑 Очистить", callback_data=f"{CB}:wl_clear"),
               B(f"✅ Вкл/Выкл {utils.bool_to_text(SETTINGS.get('whitelist_enabled', True))}",
                 callback_data=f"{CB}:wl_toggle"))
        kb.add(B(f"🔢 Порог авто-добавления: {thr}", callback_data=f"{CB}:wl:cycle"))
        kb.add(B("◀️ Назад", callback_data=f"{CB}:m:bl"))
        try:
            bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def wl_toggle(call):
        SETTINGS["whitelist_enabled"] = not bool(SETTINGS.get("whitelist_enabled", True))
        save_config()
        try: bot.answer_callback_query(call.id, f"WL: {'вкл' if SETTINGS['whitelist_enabled'] else 'выкл'}")
        except Exception: pass
        show_whitelist(call)

    def wl_cycle(call):
        cur = int(SETTINGS.get("auto_whitelist_after_orders", 3))
        SETTINGS["auto_whitelist_after_orders"] = {1: 3, 3: 5, 5: 10, 10: 1}.get(cur, 3)
        save_config()
        try: bot.answer_callback_query(call.id, f"Порог: {SETTINGS['auto_whitelist_after_orders']}")
        except Exception: pass
        show_whitelist(call)

    def ask_wl_add(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите ники через запятую/пробел/перенос для белого списка.",
            reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_WHITELIST)
        try: bot.answer_callback_query(call.id)
        except Exception: pass

    def set_wl_add(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").replace(",", " ").replace(";", " ").replace("\n", " ")
        parts = [_norm_nick(p) for p in raw.split() if p.strip()]
        nicks = [n for n in parts if n and len(n) <= 64]
        if not nicks:
            bot.reply_to(m, "❌ Не распознал.",
                reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:wl"))); return
        with LOCK:
            cur = list(SETTINGS.get("whitelist") or [])
            cur_norm = {_norm_nick(x) for x in cur}
            added = []
            for n in nicks:
                if n in cur_norm: continue
                cur.append(n); cur_norm.add(n); added.append(n)
            SETTINGS["whitelist"] = cur
        save_config()
        body = (f"✅ Добавлено: <b>{len(added)}</b>\n\n"
                + "\n".join(f"• <code>{utils.escape(x)}</code>" for x in added)) if added else "ℹ️ Все были."
        bot.reply_to(m, body, reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:wl")))

    def ask_wl_del(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите ники для удаления. <code>all</code> — очистит всё.",
            reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_WHITELIST + "_del")
        try: bot.answer_callback_query(call.id)
        except Exception: pass

    def set_wl_del(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        if raw.lower() in ("all", "все", "всё", "clear", "очистить"):
            with LOCK: SETTINGS["whitelist"] = []
            save_config()
            bot.reply_to(m, "🗑 Очищено.",
                reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:wl"))); return
        raw = raw.replace(",", " ").replace(";", " ").replace("\n", " ")
        targets = {_norm_nick(p) for p in raw.split() if p.strip()}
        if not targets:
            bot.reply_to(m, "❌ Не распознал.",
                reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:wl"))); return
        with LOCK:
            cur = list(SETTINGS.get("whitelist") or [])
            removed, keep = [], []
            for x in cur:
                if _norm_nick(x) in targets: removed.append(x)
                else: keep.append(x)
            SETTINGS["whitelist"] = keep
        save_config()
        body = (f"🗑 Удалено: <b>{len(removed)}</b>") if removed else "ℹ️ Не найдено."
        bot.reply_to(m, body, reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:wl")))

    def wl_clear(call):
        with LOCK: SETTINGS["whitelist"] = []
        save_config()
        try: bot.answer_callback_query(call.id, "🗑 Очищено")
        except Exception: pass
        show_whitelist(call)

    def wipe_counts(call):
        global BUYER_ORDERS_COUNT
        with LOCK:
            BUYER_ORDERS_COUNT.clear()
        _save_buyer_counts()
        try: bot.answer_callback_query(call.id, "🗑 Счётчики сброшены")
        except Exception: pass
        show_misc(call)

    def wipe_vision(call):
        global LOT_VISION
        with LOCK:
            LOT_VISION.clear()
        _save_lot_vision()
        try: bot.answer_callback_query(call.id, "🗑 Vision-кэш сброшен")
        except Exception: pass
        show_misc(call)

    def ask_thank_text(call):
        msg = bot.send_message(call.message.chat.id, "Пришлите текст благодарности после оплаты:", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_THANK_TEXT)
        bot.answer_callback_query(call.id)
    def set_thank_text(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        SETTINGS["auto_thank_text"] = (m.text or "").strip(); save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:orders")))
    def ask_af_delay(call):
        msg = bot.send_message(call.message.chat.id, "Задержка перед отправкой payment_msg (0–60):", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_AF_DELAY)
        bot.answer_callback_query(call.id)
    def set_af_delay(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        try:
            v = int((m.text or "").strip())
            if not 0 <= v <= 60: raise ValueError
        except Exception:
            bot.reply_to(m, "❌ Введите число 0–60."); return
        SETTINGS["auto_fulfill_delay_sec"] = v; save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:orders")))
    def ask_survey_text(call):
        msg = bot.send_message(call.message.chat.id, "Пришлите новый текст опроса после заказа:", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_SURVEY_TEXT)
        bot.answer_callback_query(call.id)
    def set_survey_text(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        SETTINGS["post_order_survey_text"] = (m.text or "").strip(); save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:orders")))
    def reset_statuses(call):
        with LOCK:
            ORDER_STATUS.clear(); CHAT_ORDERS.clear()
            CLOSED_ORDERS.clear(); PROCESSED_ORDERS.clear()
            MANUAL_FULFILL_QUEUE.clear()
        try: os.path.exists(ORDERS_PATH) and os.remove(ORDERS_PATH)
        except Exception: pass
        try: bot.answer_callback_query(call.id, "✅ Статусы сброшены")
        except Exception: pass
        show_orders_menu(call)
    def clear_history(call):
        with LOCK:
            for chat_id in list(HISTORY.keys()):
                CHAT_HISTORY_BOOTSTRAPPED.add(str(chat_id))
            HISTORY.clear(); VIEWING_CACHE.clear()
            CHAT_LOT.clear(); CHAT_LOT_AT.clear()
            SELLER_NOTIFY_AT.clear(); DONE.clear(); SPAM_WATCH.clear()
        try: os.path.exists(HISTORY_PATH) and os.remove(HISTORY_PATH)
        except Exception: pass
        try: bot.answer_callback_query(call.id, "✅ Память сброшена")
        except Exception: pass
        show_misc(call)
    def list_chats(call):
        with LOCK: items = list(HISTORY.items())
        if not items:
            text = "💬 Диалогов нет."
        else:
            lines = ["💬 <b>Диалоги</b>", ""]
            for cid, hist in items[:30]:
                n_a = sum(1 for x in hist if x.get("role") == "assistant")
                n_u = sum(1 for x in hist if x.get("role") == "user")
                with LOCK: role = CHAT_ROLE.get(str(cid), "")
                role_str = _role_ru(role) if role else "❔"
                lines.append(f"<code>{utils.escape(str(cid))}</code> — {role_str} · {len(hist)} · 👤{n_u} · 🤖{n_a}")
            text = "\n".join(lines)
        show_text(call, text, back_cb=f"{CB}:m:lots")
    def show_rules(call):
        text = ("📋 <b>Снимок правил FunPay</b>\n"
            "Источник: <a href='https://funpay.com/trade/info'>funpay.com/trade/info</a>\n\n"
            f"<pre>{utils.escape(FUNPAY_RULES_SNAPSHOT[:3500])}</pre>")
        show_text(call, text, back_cb=f"{CB}:m:misc")
    def ask(state, prompt):
        def cb(call):
            msg = bot.send_message(call.message.chat.id, prompt, reply_markup=CLEAR_STATE_BTN())
            tg.set_state(call.message.chat.id, msg.id, call.from_user.id, state)
            bot.answer_callback_query(call.id)
        return cb
    def make_setter(field, validate=None, transform=None, back_cb=f"{CB}:main"):
        def setter(m):
            tg.clear_state(m.chat.id, m.from_user.id, True)
            v = (m.text or "").strip()
            if validate and not validate(v):
                bot.reply_to(m, "❌ Некорректное значение."); return
            SETTINGS[field] = transform(v) if transform else v
            save_config()
            bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=back_cb)))
        return setter

    def ask_prompt_start(call):
        PROMPT_BUFFER["text"] = ""
        kb = K(row_width=1)
        kb.add(B("✅ Готово — сохранить промпт", callback_data=f"{CB}:prompt_done"))
        kb.add(B("🗑 Сбросить буфер", callback_data=f"{CB}:prompt_reset"))
        kb.add(B("❌ Отмена", callback_data=f"{CB}:m:replies"))
        msg = bot.send_message(call.message.chat.id,
            "📝 <b>Пришлите текст промпта.</b> Можно несколькими сообщениями. Потом ✅ Готово.",
            reply_markup=kb)
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_PROMPT)
        bot.answer_callback_query(call.id)
    def prompt_collect(m):
        text = (m.text or "").strip()
        if not text: return
        PROMPT_BUFFER["text"] = (PROMPT_BUFFER["text"] + "\n\n" + text) if PROMPT_BUFFER["text"] else text
        n_chars = len(PROMPT_BUFFER["text"])
        kb = K(row_width=1)
        kb.add(B(f"✅ Готово ({n_chars} симв.)", callback_data=f"{CB}:prompt_done"))
        kb.add(B("🗑 Сбросить буфер", callback_data=f"{CB}:prompt_reset"))
        kb.add(B("❌ Отмена", callback_data=f"{CB}:m:replies"))
        try: bot.reply_to(m, f"📥 В буфере: <b>{n_chars}</b> симв.", reply_markup=kb)
        except Exception: pass
    def prompt_done(call):
        text = PROMPT_BUFFER["text"].strip()
        if not text or len(text) < 100:
            bot.answer_callback_query(call.id, "Слишком короткий (мин. 100 симв.)", show_alert=True); return
        SETTINGS["system_prompt"] = text; save_config()
        PROMPT_BUFFER["text"] = ""
        try: tg.clear_state(call.message.chat.id, call.from_user.id, True)
        except Exception: pass
        bot.answer_callback_query(call.id, f"✅ Сохранено ({len(text)} симв.)", show_alert=True)
        show_replies(call)
    def prompt_reset(call):
        PROMPT_BUFFER["text"] = ""
        bot.answer_callback_query(call.id, "🗑 Буфер очищен.")

    def show_blacklist(call):
        with LOCK: raw = list(SETTINGS.get("blacklist") or [])
        lines = ["🚫 <b>Чёрный список</b>", "",
            f"Статус: <b>{utils.bool_to_text(SETTINGS.get('blacklist_enabled', True))}</b>",
            f"Авто-разбан при оплате: <b>{utils.bool_to_text(SETTINGS.get('unblacklist_on_payment', True))}</b>",
            f"Авто-блок: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_enabled', True))}</b>",
            f"Код → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_code', True))}</b>",
            f"Умысел → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_bad_intent', True))}</b>",
            f"Цель чата → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_bad_goal', True))}</b>",
            f"Мат/18+ → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_indecent', True))}</b>",
            f"Запрещёнка фото → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_forbidden_photo', True))}</b>",
            f"Оффтоп → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_spam', True))}</b>",
            f"Фото-вопрос → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_photo_ask', True))}</b>",
            f"Фото×3 → ЧС: <b>{utils.bool_to_text(SETTINGS.get('auto_blacklist_photo_send', True))}</b>",
            f"Всего: <b>{len(raw)}</b>", ""]
        if raw:
            for i, n in enumerate(sorted(raw, key=lambda x: str(x).lower()), 1):
                lines.append(f"{i}. <code>{utils.escape(str(n))}</code>")
        else:
            lines.append("<i>Список пуст.</i>")
        kb = K(row_width=2)
        kb.row(B("➕ Добавить", callback_data=f"{CB}:bl_add"), B("➖ Удалить", callback_data=f"{CB}:bl_del"))
        kb.row(B("🗑 Очистить", callback_data=f"{CB}:bl_clear"),
               B(f"🚫 Вкл/Выкл {utils.bool_to_text(SETTINGS.get('blacklist_enabled', True))}", callback_data=f"{CB}:bl_toggle"))
        kb.add(B(f"♻️ Авто-разбан {utils.bool_to_text(SETTINGS.get('unblacklist_on_payment', True))}", callback_data=f"{CB}:unbl_onpay"))
        kb.add(B(f"🤖 Авто-блок {utils.bool_to_text(SETTINGS.get('auto_blacklist_enabled', True))}", callback_data=f"{CB}:bl_auto_toggle"))
        kb.add(B(f"💻 ЧС код {utils.bool_to_text(SETTINGS.get('auto_blacklist_code', True))}", callback_data=f"{CB}:bl_code_toggle"))
        kb.add(B(f"🧠 ЧС умысел {utils.bool_to_text(SETTINGS.get('auto_blacklist_bad_intent', True))}", callback_data=f"{CB}:bl_badintent_toggle"))
        kb.add(B(f"🎯 ЧС цель {utils.bool_to_text(SETTINGS.get('auto_blacklist_bad_goal', True))}", callback_data=f"{CB}:bl_badgoal_toggle"))
        kb.add(B(f"💬 ЧС мат {utils.bool_to_text(SETTINGS.get('auto_blacklist_indecent', True))}", callback_data=f"{CB}:bl_indecent_toggle"))
        kb.add(B(f"🚫 ЧС фото {utils.bool_to_text(SETTINGS.get('auto_blacklist_forbidden_photo', True))}", callback_data=f"{CB}:bl_forbidden_photo_toggle"))
        kb.add(B(f"🗑 ЧС оффтоп {utils.bool_to_text(SETTINGS.get('auto_blacklist_spam', True))}", callback_data=f"{CB}:bl_spam_toggle"))
        kb.add(B(f"📸 ЧС фото-вопрос {utils.bool_to_text(SETTINGS.get('auto_blacklist_photo_ask', True))}", callback_data=f"{CB}:bl_photo_toggle"))
        kb.add(B(f"📷 ЧС фото×3 {utils.bool_to_text(SETTINGS.get('auto_blacklist_photo_send', True))}", callback_data=f"{CB}:bl_photo_send_toggle"))
        kb.add(B("◀️ Назад", callback_data=f"{CB}:m:bl"))
        try:
            bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    def ask_blacklist_add(call):
        msg = bot.send_message(call.message.chat.id, "Пришлите ники через запятую/пробел.", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_BLACKLIST)
        try: bot.answer_callback_query(call.id)
        except Exception: pass
    def set_blacklist_add(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").replace(",", " ").replace(";", " ").replace("\n", " ")
        parts = [_norm_nick(p) for p in raw.split() if p.strip()]
        nicks = [n for n in parts if n and len(n) <= 64]
        if not nicks:
            bot.reply_to(m, "❌ Не распознал.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:bl"))); return
        with LOCK:
            cur = list(SETTINGS.get("blacklist") or [])
            cur_norm = {_norm_nick(x) for x in cur}
            added = []
            for n in nicks:
                if n in cur_norm: continue
                cur.append(n); cur_norm.add(n); added.append(n)
            SETTINGS["blacklist"] = cur
        save_config()
        body = (f"✅ Добавлено: <b>{len(added)}</b>\n\n"
                + "\n".join(f"• <code>{utils.escape(x)}</code>" for x in added)) if added else "ℹ️ Все были."
        bot.reply_to(m, body, reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:bl")))
    def ask_blacklist_del(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите ники для удаления. <code>all</code> — очистит всё.", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_BLACKLIST + "_del")
        try: bot.answer_callback_query(call.id)
        except Exception: pass
    def set_blacklist_del(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        if raw.lower() in ("all", "все", "всё", "clear", "очистить"):
            with LOCK: SETTINGS["blacklist"] = []
            save_config()
            bot.reply_to(m, "🗑 Очищено.", reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:bl"))); return
        raw = raw.replace(",", " ").replace(";", " ").replace("\n", " ")
        targets = {_norm_nick(p) for p in raw.split() if p.strip()}
        if not targets:
            bot.reply_to(m, "❌ Не распознал.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:bl"))); return
        with LOCK:
            cur = list(SETTINGS.get("blacklist") or [])
            removed, keep = [], []
            for x in cur:
                if _norm_nick(x) in targets: removed.append(x)
                else: keep.append(x)
            SETTINGS["blacklist"] = keep
        save_config()
        body = (f"🗑 Удалено: <b>{len(removed)}</b>") if removed else "ℹ️ Не найдено."
        bot.reply_to(m, body, reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:bl")))
    def blacklist_clear(call):
        with LOCK: SETTINGS["blacklist"] = []
        save_config()
        try: bot.answer_callback_query(call.id, "🗑 Очищено")
        except Exception: pass
        show_blacklist(call)
    def blacklist_toggle(call):
        SETTINGS["blacklist_enabled"] = not bool(SETTINGS.get("blacklist_enabled", True)); save_config()
        try: bot.answer_callback_query(call.id, f"ЧС: {'вкл' if SETTINGS['blacklist_enabled'] else 'выкл'}")
        except Exception: pass
        try: show_blacklist(call)
        except Exception: show_bl_wl(call)

    def _mk_toggle(label, key, default=True):
        def fn(call):
            SETTINGS[key] = not bool(SETTINGS.get(key, default)); save_config()
            try: bot.answer_callback_query(call.id, f"{label}: {'вкл' if SETTINGS[key] else 'выкл'}")
            except Exception: pass
            try: show_blacklist(call)
            except Exception: show_bl_wl(call)
        return fn

    blacklist_auto_toggle = _mk_toggle("Авто-блок", "auto_blacklist_enabled", True)
    blacklist_code_toggle = _mk_toggle("ЧС код", "auto_blacklist_code", True)
    blacklist_badintent_toggle = _mk_toggle("ЧС умысел", "auto_blacklist_bad_intent", True)
    blacklist_badgoal_toggle = _mk_toggle("ЧС цель", "auto_blacklist_bad_goal", True)
    blacklist_indecent_toggle = _mk_toggle("ЧС мат", "auto_blacklist_indecent", True)
    blacklist_forbidden_photo_toggle = _mk_toggle("ЧС запрещёнка", "auto_blacklist_forbidden_photo", True)
    blacklist_spam_toggle = _mk_toggle("ЧС оффтоп", "auto_blacklist_spam", True)
    blacklist_photo_toggle = _mk_toggle("ЧС фото-вопрос", "auto_blacklist_photo_ask", True)
    blacklist_photo_send_toggle = _mk_toggle("ЧС фото×3", "auto_blacklist_photo_send", True)

    def test_api(call):
        bot.answer_callback_query(call.id, "Проверяю…")
        try:
            base = str(SETTINGS.get("api_url") or "").rstrip("/")
            key = str(SETTINGS.get("api_key") or "")
            if key.lower().startswith("env:"):
                key = os.environ.get(key[4:].strip(), "")
            model = str(SETTINGS.get("api_model") or "")
            if not base or not key or not model:
                bot.send_message(call.message.chat.id, "❌ Заполните URL, ключ и модель."); return
            ans = _call_ai_api(base, key, model,
                               [{"role": "user", "content": "Ответь OK"}], 30, 0, 16)
            bot.send_message(call.message.chat.id, f"✅ Ответ API: <code>{utils.escape(ans[:120])}</code>")
        except Exception as e:
            bot.send_message(call.message.chat.id,
                f"❌ <code>{utils.escape(f'{type(e).__name__}: {e}'[:500])}</code>")

    def ask_test_photo(call):
        msg = bot.send_message(call.message.chat.id, "📷 Отправьте фото — передам в AI vision.", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_TEST_PHOTO)
        bot.answer_callback_query(call.id)
    def handle_test_photo(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        if not getattr(m, "photo", None):
            bot.reply_to(m, "❌ Не фото."); return
        try:
            fi = bot.get_file(m.photo[-1].file_id)
            fb = bot.download_file(fi.file_path)
        except Exception as e:
            bot.reply_to(m, f"❌ {utils.escape(str(e)[:200])}"); return
        if not fb or len(fb) > _VISION_MAX_BYTES:
            bot.reply_to(m, "❌ Пустой/слишком большой."); return
        base = str(SETTINGS.get("api_url") or "").rstrip("/")
        key = str(SETTINGS.get("api_key") or "").strip()
        if key.lower().startswith("env:"):
            key = os.environ.get(key[4:].strip(), "")
        model = str(SETTINGS.get("api_model") or "").strip()
        if not base or not key or not model:
            bot.reply_to(m, "❌ Заполните API URL, ключ, модель."); return
        b64 = base64.b64encode(fb).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"
        try:
            r = requests.post(base + "/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}}]}],
                    "temperature": 0.2, "max_tokens": 800},
                timeout=(10, max(30, int(SETTINGS.get("ai_timeout", 120) or 120))))
            r.raise_for_status()
            data = _safe_json(r, "test_photo")
            ans = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip() or "(пусто)"
            bot.reply_to(m, f"🖼 <b>Ответ AI:</b>\n\n{utils.escape(ans[:3500])}",
                reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:api")))
        except Exception as e:
            bot.reply_to(m, f"❌ {type(e).__name__}: {utils.escape(str(e)[:300])}")
    def notify_test(call):
        bot.answer_callback_query(call.id, "Отправляю…")
        def job():
            try: cardinal.telegram.send_notification("🆘 <b>Тестовое уведомление</b>")
            except Exception: pass
        threading.Thread(target=job, daemon=True).start()
    def refresh_lots(call):
        bot.answer_callback_query(call.id, "Запущено…")
        msg = bot.send_message(call.message.chat.id, "🔄 Синхронизирую…")
        def job():
            cnt = sync_lots(cardinal, enrich=False)
            try:
                bot.edit_message_text(f"✅ Синхронизировано: {cnt}.", msg.chat.id, msg.id,
                    reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:lots")))
            except Exception: pass
        POOL.submit(job)
    def vision_refresh(call):
        bot.answer_callback_query(call.id, "👁 Переоцениваю скрины…")
        msg = bot.send_message(call.message.chat.id, "🔄 Извлекаю факты со скринов лотов…")
        def job():
            try:
                with LOCK:
                    lids = list(LOTS.keys())
                total = 0; done = 0
                for lid in lids:
                    if STOP.is_set(): break
                    with LOCK:
                        rec = LOTS.get(lid) or {}
                        imgs = list(rec.get("image_urls") or [])
                    if not imgs: continue
                    total += 1
                    try:
                        details = _vision_extract_lot_details(imgs)
                        if details:
                            with LOCK:
                                LOT_VISION[lid] = details
                            done += 1
                        time.sleep(0.5)
                    except Exception:
                        continue
                _save_lot_vision()
                bot.edit_message_text(
                    f"✅ Готово: {done} из {total} лотов прочитаны.",
                    msg.chat.id, msg.id,
                    reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:lots")))
            except Exception as e:
                try:
                    bot.edit_message_text(f"❌ {type(e).__name__}: {str(e)[:200]}",
                                          msg.chat.id, msg.id)
                except Exception:
                    pass
        POOL.submit(job)

    def updates_text():
        with LOCK:
            manifest = UPDATE_STATE.get("manifest")
            status = str(UPDATE_STATE.get("status") or "not_checked")
            err = str(UPDATE_STATE.get("error") or "")
            checked = float(UPDATE_STATE.get("checked_at", 0.0) or 0.0)
        url = _manifest_url()
        lines = ["🔄 <b>Обновления</b>", "",
            f"Текущая: <code>{utils.escape(VERSION)}</code>",
            f"Статус: <b>{utils.escape(update_status_line())}</b>",
            f"Автопроверка: <b>{utils.bool_to_text(SETTINGS.get('update_checks_enabled', True))}</b>",
            f"Автоустановка: <b>{utils.bool_to_text(SETTINGS.get('auto_update', False))}</b>",
            f"Автоперезапуск: <b>{utils.bool_to_text(SETTINGS.get('auto_restart_after_update', False))}</b>",
            f"Интервал: <b>{SETTINGS.get('update_check_interval_minutes', 30)} мин</b>",
            f"Manifest: <code>{utils.escape(url[:80])}</code>"]
        if checked:
            lines.append(f"Проверка: <code>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(checked))}</code>")
        if isinstance(manifest, dict):
            lines.append("")
            lines.append(f"На сервере: <b>v{utils.escape(str(manifest.get('version') or '?'))}</b>")
            if manifest.get("mandatory"):
                lines.append("🚨 <b>Важное обновление.</b>")
            notes = str(manifest.get("notes") or "").strip()
            if notes: lines.append(f"📝 {utils.escape(notes[:1200])}")
        if status == "error" and err:
            lines.extend(["", f"⚠️ <code>{utils.escape(err[:400])}</code>"])
        return "\n".join(lines)

    def updates_kb():
        kb = K(row_width=2)
        kb.row(B(f"🔎 Автопр. {utils.bool_to_text(SETTINGS.get('update_checks_enabled', True))}", callback_data=f"{CB}:upd:checks"),
               B(f"⚡ Автоуст. {utils.bool_to_text(SETTINGS.get('auto_update', False))}", callback_data=f"{CB}:upd:auto"))
        kb.add(B(f"♻️ Автоперезапуск {utils.bool_to_text(SETTINGS.get('auto_restart_after_update', False))}", callback_data=f"{CB}:upd:autorestart"))
        kb.row(B("🔄 Проверить сейчас", callback_data=f"{CB}:upd:check"),
               B(f"⏱ {SETTINGS.get('update_check_interval_minutes', 30)} мин", callback_data=f"{CB}:upd:interval"))
        with LOCK:
            manifest = UPDATE_STATE.get("manifest")
            available = bool(UPDATE_STATE.get("available"))
        if available and isinstance(manifest, dict):
            kb.add(B(f"⬆️ Установить v{manifest.get('version')}", callback_data=f"{CB}:upd:install"))
        pending = str(SETTINGS.get("pending_restart_version") or "")
        if pending and _version_key(pending) > _version_key(VERSION):
            kb.add(B(f"♻️ Перезапустить v{pending}", callback_data=f"{CB}:upd:restart"))
        kb.add(B("◀️ Назад", callback_data=f"{CB}:main"))
        return kb

    def open_updates(call):
        try:
            bot.edit_message_text(updates_text(), call.message.chat.id, call.message.id, reply_markup=updates_kb())
            bot.answer_callback_query(call.id)
        except Exception: pass
    def update_cb(call):
        action = call.data.split(":")[-1]
        try:
            if action == "checks":
                SETTINGS["update_checks_enabled"] = not bool(SETTINGS.get("update_checks_enabled", True))
                save_config(); bot.answer_callback_query(call.id, "✅"); open_updates(call); return
            if action == "auto":
                SETTINGS["auto_update"] = not bool(SETTINGS.get("auto_update", False))
                if not SETTINGS["auto_update"]: SETTINGS["auto_restart_after_update"] = False
                save_config(); bot.answer_callback_query(call.id, "✅"); open_updates(call); return
            if action == "autorestart":
                if not SETTINGS.get("auto_update", False):
                    bot.answer_callback_query(call.id, "Сначала автоустановка.", show_alert=True); return
                SETTINGS["auto_restart_after_update"] = not bool(SETTINGS.get("auto_restart_after_update", False))
                save_config(); bot.answer_callback_query(call.id, "✅"); open_updates(call); return
            if action == "check":
                manifest, err = check_updates_cycle(cardinal, notify=False, force=True)
                if manifest is None:
                    bot.answer_callback_query(call.id, (err or "Ошибка")[:180], show_alert=True)
                elif _version_key(str(manifest.get("version") or "")) > _version_key(VERSION):
                    bot.answer_callback_query(call.id, f"Доступна v{manifest.get('version')}!", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, f"v{VERSION} актуальна.", show_alert=True)
                open_updates(call); return
            if action == "install":
                with LOCK: manifest = UPDATE_STATE.get("manifest")
                ok, msg = install_update(cardinal, manifest if isinstance(manifest, dict) else None)
                bot.answer_callback_query(call.id, msg[:180], show_alert=True)
                open_updates(call); return
            if action == "restart":
                pending = str(SETTINGS.get("pending_restart_version") or "")
                if not pending:
                    bot.answer_callback_query(call.id, "Нет обновления.", show_alert=True); return
                bot.answer_callback_query(call.id, "Перезапускаю…", show_alert=True)
                _restart_cardinal(1.5); return
            if action == "interval":
                msg = bot.send_message(call.message.chat.id, "Интервал 5–1440 мин:", reply_markup=CLEAR_STATE_BTN())
                tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_UPD_INT)
                bot.answer_callback_query(call.id); return
        except Exception: pass
        open_updates(call)
    def cmd_ai(m):
        bot.send_message(m.chat.id, main_text(), reply_markup=main_kb())
    def set_update_interval(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        try:
            v = int((m.text or "").strip())
            if not 5 <= v <= 1440: raise ValueError
        except Exception:
            bot.reply_to(m, "❌ 5–1440."); return
        SETTINGS["update_check_interval_minutes"] = v; save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ К обновлениям", callback_data=f"{CB}:m:update")))
    def set_wm_text(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        SETTINGS["watermark_text"] = "" if raw == "-" else raw
        save_config()
        bot.reply_to(m, "✅ Обновлено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:replies")))
    def set_role_chat(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        val = (m.text or "").strip().lower()
        parts = val.split()
        if len(parts) != 2 or parts[1] not in ("seller", "buyer"):
            bot.reply_to(m, "❌ Формат: <code>chat_id seller|buyer</code>",
                reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:roles"))); return
        chat_id, role = parts[0], parts[1]
        _set_chat_role(chat_id, role)
        bot.reply_to(m, f"✅ Чат <code>{utils.escape(chat_id)}</code> → <b>{utils.escape(role)}</b>.",
            reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:m:roles")))
    def ask_role_chat(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите <code>chat_id seller|buyer</code>.", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_ROLE_CHAT)
        try: bot.answer_callback_query(call.id)
        except Exception: pass

    def show_lot_instr(call):
        with LOCK: instrs = dict(SETTINGS.get("lot_instructions") or {})
        if not instrs:
            text = ("📝 <b>Инструкции для лотов</b>\n\n<i>Пусто.</i>\n\n"
                    "Формат: <code>lot_id|текст</code> или <code>название лота|текст</code>\n"
                    "Пример:\n<code>12345678|Ручная выдача. Не подтверждай оплату.</code>")
        else:
            lines = [f"📝 <b>Инструкции · {len(instrs)}</b>\n"]
            for k, v in list(instrs.items())[:20]:
                lines.append(f"· <code>{utils.escape(str(k)[:40])}</code>\n   {utils.escape(str(v)[:180])}")
            if len(instrs) > 20: lines.append(f"\n… и ещё {len(instrs) - 20}")
            text = "\n".join(lines)
        show_text(call, text, back_cb=f"{CB}:m:lots")
    def ask_lot_instr_add(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите <code>lot_id|текст</code> или <code>название|текст</code>:",
            reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_LOT_INSTR)
        try: bot.answer_callback_query(call.id)
        except Exception: pass
    def set_lot_instr(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        if "|" not in raw:
            bot.reply_to(m, "❌ Нужен формат <code>lot_id|текст</code>",
                reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:lins:list"))); return
        key, val = raw.split("|", 1)
        key, val = key.strip(), val.strip()
        if not key or not val:
            bot.reply_to(m, "❌ Пустой ключ или текст."); return
        nk = key if key.isdigit() else _norm_nick(key)
        with LOCK:
            instrs = dict(SETTINGS.get("lot_instructions") or {})
            instrs[nk] = val[:2000]
            SETTINGS["lot_instructions"] = instrs
        save_config()
        bot.reply_to(m, f"✅ Сохранено для <code>{utils.escape(nk)}</code>.",
            reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:lins:list")))
    def ask_lot_instr_del(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите <code>lot_id</code> или <code>название</code>, или <code>all</code>.",
            reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_LOT_INSTR_DEL)
        try: bot.answer_callback_query(call.id)
        except Exception: pass
    def set_lot_instr_del(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        if raw.lower() in ("all", "все", "всё"):
            with LOCK: SETTINGS["lot_instructions"] = {}
            save_config()
            bot.reply_to(m, "🗑 Все инструкции очищены.",
                reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:lins:list"))); return
        target = raw if raw.isdigit() else _norm_nick(raw)
        with LOCK:
            instrs = dict(SETTINGS.get("lot_instructions") or {})
            if target in instrs:
                instrs.pop(target, None)
                SETTINGS["lot_instructions"] = instrs
                save_config()
                bot.reply_to(m, "🗑 Удалено.",
                    reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:lins:list")))
            else:
                bot.reply_to(m, "ℹ️ Не найдено.")

    def show_lot_items(call):
        with LOCK: items_map = dict(SETTINGS.get("lot_attached_items") or {})
        if not items_map:
            text = ("📦 <b>Товары, привязанные к лотам</b>\n\n<i>Пусто.</i>\n\n"
                    "Формат: <code>lot_id|название товара</code>\n"
                    "Или: <code>название лота|факт/товар</code>\n"
                    "Пример:\n<code>12345678|Идёт вместе с ключом Steam</code>\n"
                    "Можно несколько строк, каждая — отдельная запись.")
        else:
            lines = [f"📦 <b>Товары на лоты</b>\n"]
            for k, lst in list(items_map.items())[:15]:
                lines.append(f"· <code>{utils.escape(str(k)[:40])}</code> ({len(lst) if isinstance(lst, list) else 0}):")
                if isinstance(lst, list):
                    for it in lst[:5]:
                        lines.append(f"   – {utils.escape(str(it)[:120])}")
            text = "\n".join(lines)
        show_text(call, text, back_cb=f"{CB}:m:lots")
    def ask_lot_item_add(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите <code>lot_id|товар</code> или <code>название лота|товар</code>:",
            reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_LOT_ITEM)
        try: bot.answer_callback_query(call.id)
        except Exception: pass
    def set_lot_item(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        if "|" not in raw:
            bot.reply_to(m, "❌ Формат <code>lot_id|товар</code>",
                reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:litem:list"))); return
        key, val = raw.split("|", 1)
        key, val = key.strip(), val.strip()
        if not key or not val:
            bot.reply_to(m, "❌ Пустой ключ или товар."); return
        nk = key if key.isdigit() else _norm_nick(key)
        with LOCK:
            items_map = dict(SETTINGS.get("lot_attached_items") or {})
            lst = items_map.get(nk)
            if not isinstance(lst, list): lst = []
            if val not in lst: lst.append(val[:300])
            items_map[nk] = lst[:50]
            SETTINGS["lot_attached_items"] = items_map
        save_config()
        bot.reply_to(m, f"✅ Добавлено для <code>{utils.escape(nk)}</code>: <i>{utils.escape(val[:120])}</i>",
            reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:litem:list")))
    def ask_lot_item_del(call):
        msg = bot.send_message(call.message.chat.id,
            "Пришлите <code>lot_id</code> или <code>название</code> для полной очистки, "
            "либо <code>all</code> — очистит всё.", reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_LOT_ITEM_DEL)
        try: bot.answer_callback_query(call.id)
        except Exception: pass
    def set_lot_item_del(m):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        if raw.lower() in ("all", "все", "всё"):
            with LOCK: SETTINGS["lot_attached_items"] = {}
            save_config()
            bot.reply_to(m, "🗑 Очищено.",
                reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:litem:list"))); return
        target = raw if raw.isdigit() else _norm_nick(raw)
        with LOCK:
            items_map = dict(SETTINGS.get("lot_attached_items") or {})
            if target in items_map:
                items_map.pop(target, None)
                SETTINGS["lot_attached_items"] = items_map
                save_config()
                bot.reply_to(m, "🗑 Удалено.",
                    reply_markup=K().add(B("◀️ К списку", callback_data=f"{CB}:litem:list")))
            else:
                bot.reply_to(m, "ℹ️ Не найдено.")

    tg.cbq_handler(show, lambda c: c.data in (f"{CB}:main", f"{CBT.PLUGIN_SETTINGS}:{UUID}"))
    tg.cbq_handler(show_api, lambda c: c.data == f"{CB}:m:api")
    tg.cbq_handler(show_replies, lambda c: c.data == f"{CB}:m:replies")
    tg.cbq_handler(show_orders_menu, lambda c: c.data == f"{CB}:m:orders")
    tg.cbq_handler(show_lots_menu, lambda c: c.data == f"{CB}:m:lots")
    tg.cbq_handler(show_roles, lambda c: c.data == f"{CB}:m:roles")
    tg.cbq_handler(show_bl_wl, lambda c: c.data == f"{CB}:m:bl")
    tg.cbq_handler(open_updates, lambda c: c.data == f"{CB}:m:update")
    tg.cbq_handler(show_misc, lambda c: c.data == f"{CB}:m:misc")
    tg.cbq_handler(show_whitelist, lambda c: c.data == f"{CB}:wl")
    tg.cbq_handler(wl_toggle, lambda c: c.data == f"{CB}:wl_toggle")
    tg.cbq_handler(wl_cycle, lambda c: c.data == f"{CB}:wl:cycle")
    tg.cbq_handler(ask_wl_add, lambda c: c.data == f"{CB}:wl_add")
    tg.cbq_handler(ask_wl_del, lambda c: c.data == f"{CB}:wl_del")
    tg.cbq_handler(wl_clear, lambda c: c.data == f"{CB}:wl_clear")
    tg.cbq_handler(wipe_counts, lambda c: c.data == f"{CB}:wipe_counts")
    tg.cbq_handler(wipe_vision, lambda c: c.data == f"{CB}:wipe_vision")
    tg.cbq_handler(toggle, lambda c: c.data == f"{CB}:tog")
    tg.cbq_handler(toggle_wm, lambda c: c.data == f"{CB}:wm")
    tg.cbq_handler(toggle_notify, lambda c: c.data == f"{CB}:notify")
    tg.cbq_handler(toggle_bootstrap, lambda c: c.data == f"{CB}:bootstrap")
    tg.cbq_handler(toggle_lang, lambda c: c.data == f"{CB}:lang")
    tg.cbq_handler(toggle_tone, lambda c: c.data == f"{CB}:tone")
    tg.cbq_handler(toggle_nopromise, lambda c: c.data == f"{CB}:nopromise")
    tg.cbq_handler(toggle_confnotify, lambda c: c.data == f"{CB}:confnotify")
    tg.cbq_handler(toggle_thank, lambda c: c.data == f"{CB}:thank")
    tg.cbq_handler(toggle_autofulfill, lambda c: c.data == f"{CB}:autofulfill")
    tg.cbq_handler(toggle_survey, lambda c: c.data == f"{CB}:survey")
    tg.cbq_handler(toggle_unbl_onpay, lambda c: c.data == f"{CB}:unbl_onpay")
    tg.cbq_handler(toggle_role_detection, lambda c: c.data == f"{CB}:role_toggle")
    tg.cbq_handler(cycle_role_default, lambda c: c.data == f"{CB}:role_default")
    tg.cbq_handler(reset_roles, lambda c: c.data == f"{CB}:roles_reset")
    tg.cbq_handler(toggle_called, lambda c: c.data == f"{CB}:tog:called")
    tg.cbq_handler(toggle_lotvision, lambda c: c.data == f"{CB}:tog:lotvision")
    tg.cbq_handler(toggle_manual, lambda c: c.data == f"{CB}:tog:manual")
    tg.cbq_handler(toggle_websearch, lambda c: c.data == f"{CB}:tog:websearch")
    tg.cbq_handler(cycle_webres, lambda c: c.data == f"{CB}:cycle:webres")
    tg.cbq_handler(ask_thank_text, lambda c: c.data == f"{CB}:thanktext")
    tg.cbq_handler(ask_af_delay, lambda c: c.data == f"{CB}:autofulfilldelay")
    tg.cbq_handler(ask_survey_text, lambda c: c.data == f"{CB}:surveytext")
    tg.cbq_handler(reset_statuses, lambda c: c.data == f"{CB}:resetstatus")
    tg.cbq_handler(notify_test, lambda c: c.data == f"{CB}:notify_test")
    tg.cbq_handler(clear_history, lambda c: c.data == f"{CB}:clear_history")
    tg.cbq_handler(list_chats, lambda c: c.data == f"{CB}:chats")
    tg.cbq_handler(show_rules, lambda c: c.data == f"{CB}:rules")
    tg.cbq_handler(ask_test_photo, lambda c: c.data == f"{CB}:testphoto")
    tg.cbq_handler(update_cb, lambda c: c.data.startswith(f"{CB}:upd:"))
    tg.cbq_handler(ask_prompt_start, lambda c: c.data == f"{CB}:prompt")
    tg.cbq_handler(prompt_done, lambda c: c.data == f"{CB}:prompt_done")
    tg.cbq_handler(prompt_reset, lambda c: c.data == f"{CB}:prompt_reset")
    tg.cbq_handler(show_blacklist, lambda c: c.data == f"{CB}:bl")
    tg.cbq_handler(ask_blacklist_add, lambda c: c.data == f"{CB}:bl_add")
    tg.cbq_handler(ask_blacklist_del, lambda c: c.data == f"{CB}:bl_del")
    tg.cbq_handler(blacklist_clear, lambda c: c.data == f"{CB}:bl_clear")
    tg.cbq_handler(blacklist_toggle, lambda c: c.data == f"{CB}:bl_toggle")
    tg.cbq_handler(blacklist_auto_toggle, lambda c: c.data == f"{CB}:bl_auto_toggle")
    tg.cbq_handler(blacklist_code_toggle, lambda c: c.data == f"{CB}:bl_code_toggle")
    tg.cbq_handler(blacklist_badintent_toggle, lambda c: c.data == f"{CB}:bl_badintent_toggle")
    tg.cbq_handler(blacklist_badgoal_toggle, lambda c: c.data == f"{CB}:bl_badgoal_toggle")
    tg.cbq_handler(blacklist_indecent_toggle, lambda c: c.data == f"{CB}:bl_indecent_toggle")
    tg.cbq_handler(blacklist_forbidden_photo_toggle, lambda c: c.data == f"{CB}:bl_forbidden_photo_toggle")
    tg.cbq_handler(blacklist_spam_toggle, lambda c: c.data == f"{CB}:bl_spam_toggle")
    tg.cbq_handler(blacklist_photo_toggle, lambda c: c.data == f"{CB}:bl_photo_toggle")
    tg.cbq_handler(blacklist_photo_send_toggle, lambda c: c.data == f"{CB}:bl_photo_send_toggle")
    tg.cbq_handler(show_lot_instr, lambda c: c.data == f"{CB}:lins:list")
    tg.cbq_handler(ask_lot_instr_add, lambda c: c.data == f"{CB}:lins:add")
    tg.cbq_handler(ask_lot_instr_del, lambda c: c.data == f"{CB}:lins:del")
    tg.cbq_handler(show_lot_items, lambda c: c.data == f"{CB}:litem:list")
    tg.cbq_handler(ask_lot_item_add, lambda c: c.data == f"{CB}:litem:add")
    tg.cbq_handler(ask_lot_item_del, lambda c: c.data == f"{CB}:litem:del")
    tg.cbq_handler(ask_role_chat, lambda c: c.data == f"{CB}:role_set_chat")
    tg.cbq_handler(ask(ST_URL, "Введите base URL API:"), lambda c: c.data == f"{CB}:url")
    tg.cbq_handler(ask(ST_KEY, "Введите API key:"), lambda c: c.data == f"{CB}:key")
    tg.cbq_handler(ask(ST_MODEL, "Введите ID модели:"), lambda c: c.data == f"{CB}:model")
    tg.cbq_handler(ask(ST_SELLER, "Пришлите данные о продавце:"), lambda c: c.data == f"{CB}:seller")
    tg.cbq_handler(ask(ST_TIMEOUT, "AI timeout 30–600 сек:"), lambda c: c.data == f"{CB}:timeout")
    tg.cbq_handler(ask(ST_BUDGET, "Бюджет истории 2000–40000:"), lambda c: c.data == f"{CB}:budget")
    tg.cbq_handler(ask(ST_WM_TEXT, "Введите текст знака:"), lambda c: c.data == f"{CB}:wmtext")
    tg.cbq_handler(ask(ST_NOTIFY_COOLDOWN, "Cooldown 0–60 мин:"), lambda c: c.data == f"{CB}:cooldown")
    tg.cbq_handler(test_api, lambda c: c.data == f"{CB}:test")
    tg.cbq_handler(refresh_lots, lambda c: c.data == f"{CB}:lots")
    tg.cbq_handler(vision_refresh, lambda c: c.data == f"{CB}:vision_refresh")

    tg.msg_handler(make_setter("api_url", back_cb=f"{CB}:m:api"),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_URL))
    tg.msg_handler(make_setter("api_key", back_cb=f"{CB}:m:api"),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_KEY))
    tg.msg_handler(make_setter("api_model", back_cb=f"{CB}:m:api"),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_MODEL))
    tg.msg_handler(make_setter("seller_info", back_cb=f"{CB}:m:replies"),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_SELLER))
    tg.msg_handler(make_setter("ai_timeout", back_cb=f"{CB}:m:api",
        validate=lambda v: v.isdigit() and 30 <= int(v) <= 600, transform=int),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_TIMEOUT))
    tg.msg_handler(make_setter("history_char_budget", back_cb=f"{CB}:m:api",
        validate=lambda v: v.isdigit() and 2000 <= int(v) <= 40000, transform=int),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_BUDGET))
    tg.msg_handler(set_wm_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_WM_TEXT))
    tg.msg_handler(make_setter("seller_notify_cooldown", back_cb=f"{CB}:m:orders",
        validate=lambda v: v.isdigit() and 0 <= int(v) <= 60, transform=int),
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_NOTIFY_COOLDOWN))
    tg.msg_handler(set_update_interval, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_UPD_INT))
    tg.msg_handler(set_thank_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_THANK_TEXT))
    tg.msg_handler(set_af_delay, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_AF_DELAY))
    tg.msg_handler(set_survey_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_SURVEY_TEXT))
    tg.msg_handler(prompt_collect, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_PROMPT))
    tg.msg_handler(set_blacklist_add, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_BLACKLIST))
    tg.msg_handler(set_blacklist_del, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_BLACKLIST + "_del"))
    tg.msg_handler(set_wl_add, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_WHITELIST))
    tg.msg_handler(set_wl_del, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_WHITELIST + "_del"))
    tg.msg_handler(set_role_chat, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_ROLE_CHAT))
    tg.msg_handler(set_lot_instr, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_LOT_INSTR))
    tg.msg_handler(set_lot_instr_del, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_LOT_INSTR_DEL))
    tg.msg_handler(set_lot_item, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_LOT_ITEM))
    tg.msg_handler(set_lot_item_del, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_LOT_ITEM_DEL))
    tg.msg_handler(handle_test_photo, content_types=["photo"],
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_TEST_PHOTO))
    tg.msg_handler(cmd_ai, commands=["ai"])
    cardinal.add_telegram_commands(UUID, [("ai", "KiriillBR AI", True)])

def post_init(c):
    if not os.path.exists(CFG_PATH): load_config()
    _load_buyer_counts()
    _load_lot_vision()
    load_orders_state()
    load_history_state()
    try:
        load_recent_orders(c, limit=10)
    except Exception: logger.debug("load_recent_orders failed", exc_info=True)
    try:
        sync_lots(c, enrich=False)
    except Exception: logger.debug("post_init", exc_info=True)

def post_start(c):
    threading.Thread(target=lot_worker, args=(c,), daemon=True, name="KBAI-lots").start()
    threading.Thread(target=update_worker, args=(c,), daemon=True, name="KBAI-updates").start()
    threading.Thread(target=save_orders_worker, args=(c,), daemon=True, name="KBAI-orders-save").start()

def on_delete(c, call=None):
    try: save_orders_state()
    except Exception: pass
    try: save_history_state()
    except Exception: pass
    try: _save_buyer_counts()
    except Exception: pass
    try: _save_lot_vision()
    except Exception: pass
    STOP.set()
    try: POOL.shutdown(wait=False, cancel_futures=True)
    except Exception: pass

BIND_TO_PRE_INIT = [init_telegram]
BIND_TO_POST_INIT = [post_init]
BIND_TO_POST_START = [post_start]
BIND_TO_NEW_MESSAGE = [on_message]
BIND_TO_LAST_CHAT_MESSAGE_CHANGED = [on_last_chat]
BIND_TO_NEW_ORDER = [on_new_paid_order]
BIND_TO_DELETE = on_delete
