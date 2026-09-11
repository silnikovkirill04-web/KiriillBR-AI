"""KiriillBR AI — AI-автоответчик FunPay Cardinal (API-only) с автообновлениями.
Автор: @qneiz"""
from __future__ import annotations
import ast, difflib, hashlib, json, logging, os, re, shutil, sys, threading, time
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
VERSION = "2.1.0"
DESCRIPTION = ("AI-заместитель продавца FunPay на OpenAI-compatible API с автообновлениями. "
               "Помнит диалог, видит лот покупателя и игровые параметры лота, соблюдает правила FunPay, "
               "отвечает на языке покупателя, спокойно на агрессию, не выдумывает скидки/бонусы.")
CREDITS = "@qneiz"
UUID = "7b93d4e1-6a2c-4f8b-9c73-5e10d8a6f214"
SETTINGS_PAGE = True

PUBLISHER_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/silnikovkirill04-web/KiriillBR-AI/main/manifest.json"
UPDATE_MANIFEST_SCHEMA = 1
UPDATE_MAX_BYTES = 3 * 1024 * 1024
UPDATE_USER_AGENT = f"KiriillBRAI/{VERSION} ({UUID})"

CFG_PATH = "storage/plugins/kiriillbr_ai.json"
CB = "KBAI"
ST_MODEL, ST_PROMPT, ST_SELLER = f"{CB}_model", f"{CB}_prompt", f"{CB}_seller"
ST_URL, ST_KEY, ST_TIMEOUT, ST_BUDGET = f"{CB}_url", f"{CB}_key", f"{CB}_timeout", f"{CB}_budget"
ST_WM_TEXT, ST_NOTIFY_COOLDOWN = f"{CB}_wmtext", f"{CB}_cooldown"
ST_UPD_INT = f"{CB}_updint"

DEFAULT_PROMPT = (
    "Ты — AI-заместитель продавца на FunPay. Отвечай кратко, по-русски, 1-3 предложения.\n\n"
    "ПАМЯТЬ И СТИЛЬ:\n"
    "- Ты видишь всю историю чата. Используй её для контекста: не здоровайся повторно, "
    "не проси повторить уже сказанное, понимай короткие продолжения.\n"
    "- Отвечай ТОЛЬКО на последнее сообщение покупателя. Не пересказывай историю.\n"
    "- Подстраивайся под стиль покупателя: неформально — неформально, формально — сдержанно.\n\n"
    "РОЛИ В ИСТОРИИ:\n"
    "- assistant — твои прошлые ответы И сообщения продавца. Если уже отвечали — не повторяй.\n"
    "- user — только покупатель. Не повторяй один ответ дважды подряд.\n"
    "- КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ вступления вида: «Продавец уже ответил», «Я уже отвечал», "
    "«Мы это обсуждали», «Смотрите выше», «Об этом уже писали», «Ранее я говорил». "
    "Если покупатель повторяет вопрос — просто ответь снова по существу, одним сообщением.\n"
    "- Начинай ответ СРАЗУ с сути. Без вступлений и извинений.\n\n"
    "КОНТЕКСТ ТОВАРА:\n"
    "- ТЕКУЩИЙ ТОВАР — лот покупателя. НЕ проси уточнить, отвечай сразу по нему.\n"
    "- ИГРОВЫЕ ПАРАМЕТРЫ ЛОТА — авторитетный источник, отвечай точно по цифрам.\n\n"
    "ПРАВИЛА:\n"
    "- Определяй смысл, а не слова. Учитывай транслит, сленг, опечатки.\n"
    "- «Аккаунт Standoff/Steam/Telegram» — обычный товар, не данные продавца.\n"
    "- Скидка/торг — на усмотрение продавца, ты передал запрос. Если продавец уже ответил — подтверди.\n"
    "- «Поможете?» — согласись и упомяни, что передал продавцу.\n"
    "- НИКОГДА не отвечай «не понял вопрос», «нет данных», если можно дать полезный ответ.\n"
    "- Не раскрывай баланс, пароли, токены, cookies, личные контакты, платёжные реквизиты.\n"
    "- Не выдумывай цену, наличие, гарантию, сроки, если их нет в блоке ТОВАР.\n"
    "- Если не знаешь — честно скажи, что уточнишь у продавца.\n"
    "- Соблюдай ПРАВИЛА FUNPAY ниже."
)

FUNPAY_RULES_SNAPSHOT = """ПРАВИЛА FUNPAY — ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ:

[1.1] Не передавай и не запрашивай контакты (Telegram, Discord, VK, телефон, e-mail).
[1.2] Не предлагай накрутку/шантаж/изменение отзыва.
[1.3] Не разглашай имя/ID/сумму заказа с целью вреда.
[1.4] НЕ помогай покупать/продавать аккаунт FunPay.
[1.7-1.8] Не оскорбляй, не угрожай, не спамь, не навязывай политику.
[1.9] Не рекламируй сторонние ресурсы.
[1.10] Не мошенничай, не обманывай, не вреди.
[1.11] Не помогай с обменом денег между системами, кардингом.
[1.12] Не давай ссылки на файлообменники без необходимости.

[2.1.1] НИКОГДА не соглашайся передать товар без оплаты через FunPay.
[2.1.2] Не проси подтвердить заказ до выполнения.
[2.1.4] На разрешённые вопросы отвечай по существу.

[2.2.x] НИКОГДА не помогай с продажей: незаконных товаров, обучения незаконной деятельности,
персданных, вредоносного ПО, аккаунтов соцсетей (кроме специальных разделов), телефонных номеров,
аккаунтов оптом, эротики/порно, спама, казино/ставок, донат/накрутки, лотерей/рандома, крипты.

ПРИ ОТКАЗЕ: коротко откажи и не выполняй. В остальных случаях отвечай по существу.

Название платформы в товаре (Telegram Premium, Discord Nitro, аккаунт Steam) — НЕ нарушение.
"""

DEFAULTS = {
    "version": 21, "enabled": True, "setup_done": False,
    "api_url": "https://openrouter.ai/api/v1", "api_key": "", "api_model": "",
    "ai_timeout": 120, "temperature": 0.25, "num_predict": 300,
    "history_char_budget": 12000, "response_delay": 0.3,
    "system_prompt": DEFAULT_PROMPT, "seller_info": "",
    "unknown_reply": "Уточните, пожалуйста, что именно нужно.",
    "lot_refresh_minutes": 30,
    "watermark": True,
    "watermark_text": "Помощник продавца  🛍( Искуственный интеллект 👾)",
    "seller_notify": True,
    "seller_notify_cooldown": 5,
    "seller_notify_patterns_extra": "",
    "bootstrap_history": True,
    "confidence_notify": True,
    "match_language": True,
    "neutral_on_anger": True,
    "no_unconfirmed_promises": True,
    "update_checks_enabled": True,
    "update_manifest_url": PUBLISHER_UPDATE_MANIFEST_URL,
    "update_check_interval_minutes": 30,
    "auto_update": False,
    "auto_restart_after_update": False,
    "last_notified_version": "",
    "last_installed_version": "",
    "pending_restart_version": "",
}

SETTINGS = dict(DEFAULTS)
LOTS: dict[str, dict[str, Any]] = {}
HISTORY: dict[str, list[dict[str, str]]] = {}
CHAT_HISTORY_BOOTSTRAPPED: set[str] = set()
QUEUES: dict[str, deque] = {}
ACTIVE: set[str] = set()
DONE: dict[str, float] = {}
VIEWING_CACHE: dict[str, tuple[float, Any]] = {}
CHAT_LOT: dict[str, str] = {}
CHAT_LOT_AT: dict[str, float] = {}
SELLER_NOTIFY_AT: dict[str, float] = {}
UPDATE_STATE: dict[str, Any] = {
    "checked_at": 0.0, "status": "not_checked", "error": "",
    "manifest": None, "available": False, "installing": False,
}
LOCK = threading.RLock()
STOP = threading.Event()
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="KBAI")

_HISTORY_HARD_CAP = 200


def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        r = dict(a)
        for k, v in b.items():
            r[k] = _merge(a[k], v) if k in a else v
        return r
    return b


def load_config() -> None:
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
        if cv < 11:
            for k, v in (
                ("update_checks_enabled", True),
                ("update_manifest_url", PUBLISHER_UPDATE_MANIFEST_URL),
                ("update_check_interval_minutes", 30),
                ("auto_update", False),
                ("auto_restart_after_update", False),
                ("last_notified_version", ""),
                ("last_installed_version", ""),
                ("pending_restart_version", ""),
            ):
                SETTINGS.setdefault(k, v)
            SETTINGS["version"] = 11
            save_config()
        if cv < 21:
            cur = str(SETTINGS.get("system_prompt") or "")
            if cur.startswith("Ты — AI-заместитель продавца") and "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ" not in cur:
                SETTINGS["system_prompt"] = DEFAULT_PROMPT
            SETTINGS["version"] = 21
            save_config()
    except Exception:
        pass


def save_config() -> None:
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    tmp = f"{CFG_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    with LOCK:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(SETTINGS, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CFG_PATH)
        finally:
            try:
                os.path.exists(tmp) and os.remove(tmp)
            except OSError:
                pass


def is_enabled(c: "Cardinal") -> bool:
    p = c.plugins.get(UUID)
    return bool(p and p.enabled and SETTINGS.get("enabled"))


def _version_key(value: str) -> tuple[int, int, int, int]:
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))[:4]]
    return tuple((nums + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def _manifest_url() -> str:
    return str(SETTINGS.get("update_manifest_url") or PUBLISHER_UPDATE_MANIFEST_URL or "").strip()


def _is_safe_url(url: str) -> bool:
    v = str(url or "").strip()
    if re.match(r"^https://[^\s]+$", v, re.I):
        return True
    return bool(re.match(r"^http://(?:127\.0\.0\.1|localhost)(?::\d+)?(?:/[^\s]*)?$", v, re.I))


def _extract_meta(source: str) -> tuple[str, str]:
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
            if n == "UUID":
                ru = node.value.value.strip()
            else:
                rv = node.value.value.strip()
    return ru, rv


def _validate_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("manifest должен быть JSON-объектом")
    try:
        schema = int(data.get("schema", 0) or 0)
    except Exception:
        schema = 0
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


def fetch_update_manifest(force: bool = False) -> tuple[dict[str, Any] | None, str]:
    url = _manifest_url()
    if not SETTINGS.get("update_checks_enabled", True):
        with LOCK:
            UPDATE_STATE.update(status="disabled", error="", available=False)
        return None, "Проверка выключена."
    if not url:
        with LOCK:
            UPDATE_STATE.update(status="unconfigured", error="", available=False)
        return None, "URL manifest не задан."
    if not _is_safe_url(url):
        with LOCK:
            UPDATE_STATE.update(status="error", error="URL должен быть HTTPS", available=False)
        return None, "URL должен быть HTTPS."
    now = time.time()
    with LOCK:
        cached = UPDATE_STATE.get("manifest")
        checked = float(UPDATE_STATE.get("checked_at", 0.0) or 0.0)
        if not force and checked and now - checked < 60 and isinstance(cached, dict):
            return cached, ""
    try:
        r = requests.get(url, timeout=(6, 20),
                         headers={"User-Agent": UPDATE_USER_AGENT,
                                  "Accept": "application/json",
                                  "Cache-Control": "no-cache"})
        r.raise_for_status()
        manifest = _validate_manifest(r.json())
        available = _version_key(manifest["version"]) > _version_key(VERSION)
        with LOCK:
            UPDATE_STATE.update(checked_at=now,
                                status="available" if available else "current",
                                error="", manifest=manifest, available=available)
        return manifest, ""
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        with LOCK:
            UPDATE_STATE.update(checked_at=now, status="error", error=msg,
                                manifest=None, available=False)
        logger.warning("Не удалось проверить обновления: %s", msg)
        return None, msg


def _plugin_file_path(c: "Cardinal") -> str:
    try:
        plugin_data = c.plugins.get(UUID)
        path = str(getattr(plugin_data, "path", "") or "")
        if path:
            return os.path.abspath(path)
    except Exception:
        pass
    return os.path.abspath(__file__)


def _download(url: str) -> bytes:
    r = requests.get(url, stream=True, timeout=(8, 45),
                     headers={"User-Agent": UPDATE_USER_AGENT,
                              "Accept": "text/x-python, text/plain, */*",
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
    chunks: list[bytes] = []
    total = 0
    for chunk in r.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > UPDATE_MAX_BYTES:
            raise ValueError("файл превышает допустимый размер")
        chunks.append(chunk)
    if total < 1000:
        raise ValueError("файл подозрительно мал")
    return b"".join(chunks)


def install_update(c: "Cardinal", manifest: dict[str, Any] | None = None) -> tuple[bool, str]:
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
        backup = target + ".bak"
        with open(tmp_path, "wb") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        if os.path.exists(target):
            try:
                shutil.copy2(target, backup)
            except Exception:
                logger.debug("Не удалось создать backup", exc_info=True)
        os.replace(tmp_path, target)
        tmp_path = ""
        SETTINGS["last_installed_version"] = rv
        SETTINGS["pending_restart_version"] = rv
        save_config()
        with LOCK:
            UPDATE_STATE.update(status="installed_pending_restart",
                                available=False, error="", manifest=manifest)
        logger.info("Обновление v%s установлено в %s. Нужен перезапуск.", rv, target)
        return True, f"Версия v{rv} установлена. Нужен перезапуск Cardinal."
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        with LOCK:
            UPDATE_STATE.update(status="error", error=msg)
        logger.error("Ошибка установки: %s", msg)
        logger.debug("TRACEBACK", exc_info=True)
        return False, msg
    finally:
        if tmp_path:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        with LOCK:
            UPDATE_STATE["installing"] = False


def _restart_cardinal(delay: float = 1.2) -> None:
    def _job() -> None:
        time.sleep(max(0.2, delay))
        try:
            argv = [sys.executable] + (list(sys.argv[1:]) if getattr(sys, "frozen", False) else list(sys.argv))
            os.execv(sys.executable, argv)
        except Exception:
            logger.error("Не удалось автоматически перезапустить Cardinal")
            logger.debug("TRACEBACK", exc_info=True)
    threading.Thread(target=_job, daemon=True, name="KBAI-restart").start()


def _update_notification_text(manifest: dict[str, Any]) -> str:
    version = str(manifest.get("version") or "?")
    notes = str(manifest.get("notes") or "").strip()
    critical = "\n🚨 <b>Обновление помечено как важное.</b>" if manifest.get("mandatory") else ""
    body = (
        f"🔄 <b>Доступно обновление KiriillBR AI</b>\n\n"
        f"Текущая: <code>{utils.escape(VERSION)}</code>\n"
        f"Новая: <code>{utils.escape(version)}</code>{critical}"
    )
    if notes:
        body += f"\n\n📝 {utils.escape(notes[:1200])}"
    body += "\n\nСкачивается по HTTPS, проверяется SHA-256, UUID и синтаксис Python."
    return body


def notify_update(c: "Cardinal", manifest: dict[str, Any], force: bool = False) -> bool:
    if not getattr(c, "telegram", None):
        return False
    version = str(manifest.get("version") or "").strip()
    if not version:
        return False
    if not force and str(SETTINGS.get("last_notified_version") or "") == version:
        return False
    kb = K(row_width=1)
    kb.add(B(f"⬆️ Обновить до v{version}", callback_data=f"{CB}:upd:install"))
    kb.add(B("🔄 Открыть обновления", callback_data=f"{CB}:update"))
    try:
        c.telegram.send_notification(_update_notification_text(manifest), keyboard=kb)
        SETTINGS["last_notified_version"] = version
        save_config()
        return True
    except Exception:
        logger.warning("Не удалось отправить уведомление об обновлении", exc_info=True)
        return False


def check_updates_cycle(c: "Cardinal", notify: bool = True, force: bool = False) -> tuple[dict[str, Any] | None, str]:
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
                        "Файл заменён. Для применения нужен перезапуск Cardinal.",
                        keyboard=kb,
                    )
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
            if SETTINGS.get("auto_restart_after_update", False):
                _restart_cardinal(2.0)
        return manifest, msg
    if notify:
        notify_update(c, manifest)
    return manifest, ""


def update_worker(c: "Cardinal") -> None:
    if STOP.wait(5.0):
        return
    while not STOP.is_set():
        try:
            if SETTINGS.get("update_checks_enabled", True):
                check_updates_cycle(c, notify=True, force=True)
        except Exception:
            logger.debug("Ошибка воркера обновлений", exc_info=True)
        try:
            minutes = int(SETTINGS.get("update_check_interval_minutes", 30) or 30)
        except Exception:
            minutes = 30
        minutes = max(10, min(1440, minutes))
        if STOP.wait(minutes * 60):
            break


def update_status_line() -> str:
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
    if status == "current":
        return "актуальна"
    if status == "error":
        return f"ошибка: {err[:60]}"
    return "ещё не проверялись"


_RE_P = re.compile(r"[^\w\sа-яёa-z0-9]+", re.I)
_RE_S = re.compile(r"\s+")
_RU2LAT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})
_STOP = {"я", "мне", "мой", "это", "этот", "эта", "эти", "данный", "данного", "вот", "ну",
         "про", "на", "для", "у", "а", "че", "чо", "что", "типа", "короче", "товар", "товара",
         "лот", "лота", "нужен", "нужна", "нужно", "хочу", "могу", "можем", "можешь", "ли",
         "сколько", "стоит", "цена", "цену", "стоимость", "почем", "купить", "покупать",
         "куплю", "покупаю", "взять", "брать", "беру", "возьму", "заказать", "закажу",
         "оформить", "оформлю", "можно", "давай", "давайте", "есть", "наличие", "наличии",
         "доступно", "актуален", "актуально", "какой", "какая", "какое", "какие",
         "подскажите", "скажите", "пожалуйста", "штук", "единиц", "количество", "осталось"}


def norm(t: Any) -> str:
    s = str(t or "").lower().replace("ё", "е")
    return _RE_S.sub(" ", _RE_P.sub(" ", s)).strip()


def toks(t: Any) -> list[str]:
    n = re.sub(r"(?<=\d)(?=[a-zа-я])|(?<=[a-zа-я])(?=\d)", " ", norm(t), flags=re.I)
    return [x for x in n.split() if (len(x) > 1 or x.isdigit()) and x not in _STOP]


def pair_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
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


def coverage(q: str, c: str) -> float:
    qt, ct = toks(q), toks(c)
    if not qt or not ct:
        return 0.0
    used, scores = set(), []
    for x in qt:
        bi, bs = -1, 0.0
        for i, y in enumerate(ct):
            if i in used:
                continue
            s = pair_score(x, y)
            if s > bs:
                bi, bs = i, s
        if bi >= 0 and bs >= 0.68:
            used.add(bi)
            scores.append(bs)
        else:
            scores.append(0.0)
    matched = sum(1 for s in scores if s >= 0.68) / len(qt)
    return min(1.0, 0.68 * (sum(scores) / len(qt)) + 0.32 * matched)


def lot_score(text: str, lot: dict[str, Any]) -> float:
    n = norm(text)
    if not n:
        return 0.0
    best = 0.0
    for cand, w in ((lot.get("title"), 1.0), (lot.get("description"), 0.94),
                    (lot.get("full_description", "")[:700], 0.72)):
        if not cand:
            continue
        c = norm(cand)
        sc = max(difflib.SequenceMatcher(None, n, c).ratio() * 0.6 + coverage(n, c) * 0.4, coverage(n, c)) * w
        qn, cn = set(re.findall(r"\d+", n)), set(re.findall(r"\d+", c))
        if qn and cn and not qn.issubset(cn):
            sc *= 0.52
        best = max(best, sc)
    return min(1.0, best)


def find_lots(text: str, limit: int = 3) -> list[tuple[dict[str, Any], float]]:
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
_RE_SECRET = re.compile(
    r"\b(?:парол\w*|password|passwd|token|токен\w*|api[_ -]?key|golden_key|phpsessid|"
    r"cookies?|session(?:id)?|сесси\w*|2fa|otp)\b\s*[:=]\s*[^\s,;]{3,}", re.I)
_RE_PROD_NUM = re.compile(
    r"(?:подписчик\w*|просмотр\w*|лайк\w*|зв[её]зд\w*|голос\w*|штук\w*|единиц\w*|"
    r"количеств\w*|пакет\w*|цен\w*|стоим\w*|руб\w*|₽|usd|eur|доллар\w*|евро)", re.I)

_FORBIDDEN_AI_PHRASES = [
    re.compile(r"\bскидк\w*\s+не\s+предусмотрен\w*", re.I),
    re.compile(r"\bскидк\w*\s+недоступн\w*", re.I),
    re.compile(r"\bскидк\w*\s+нет\b", re.I),
    re.compile(r"\bскидок\s+нет\b", re.I),
    re.compile(r"\bторг\w*\s+не\s+предусмотрен\w*", re.I),
    re.compile(r"\bторг\w*\s+недоступ\w*", re.I),
    re.compile(r"\bторг\w*\s+нет\b", re.I),
]

_RE_ALREADY_ANSWERED = re.compile(
    r"(?:^|\n)\s*"
    r"(?:(?:продавец|продавец уже|я уже|мы уже|вы уже)\s+)?"
    r"(?:уже\s+)?"
    r"(?:отвеч\w*|ответил\w*|писал\w*|говорил\w*|упоминал\w*|уточнял\w*)"
    r"(?:\s+на\s+(?:этот|данный|это|такой)\s+вопрос\w*)?"
    r"(?:\s+по\s+(?:этому|данному|этому)\s+вопрос\w*)?"
    r"[^\n.!?]*[.!?]?\s*",
    re.I,
)


def _strip_already_answered(text: str) -> str:
    """Убирает шаблонные фразы «Продавец уже ответил», «Я уже говорил» и т.п."""
    if not text:
        return text
    result = str(text).strip()
    for _ in range(5):
        new = _RE_ALREADY_ANSWERED.sub("", result).strip()
        if new == result:
            break
        result = new
    return result


def _clean_ai_answer(text: str) -> str:
    """Финальная очистка ответа AI перед отправкой покупателю."""
    result = str(text or "")
    for pat in _FORBIDDEN_AI_PHRASES:
        result = pat.sub("скидка на усмотрение продавца", result)
    result = _strip_already_answered(result)
    return result.strip()


_REFUSAL = {
    "contacts": "Не могу передавать личные контакты. Общение остаётся в чате FunPay.",
    "off_platform": "Не могу помогать с оплатой или сделкой вне FunPay.",
    "account_security": "Не могу передавать пароли, токены и другие секретные данные.",
    "confidential": "Не могу раскрывать конфиденциальные данные продавца.",
    "funpay_rules": "К сожалению, не могу помочь с этим запросом — он противоречит правилам FunPay.",
}


def refusal(code: str) -> str:
    return _REFUSAL.get(code, _REFUSAL["confidential"])


def _is_prod_num(text: str, m: re.Match) -> bool:
    return bool(_RE_PROD_NUM.search(text[max(0, m.start() - 55):m.end() + 55]))


def outbound_violation(text: str) -> str:
    v = str(text or "")
    if not v:
        return "empty"
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


def _safe_for_notify(text: str, limit: int = 1000) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = _RE_SECRET.sub("[СКРЫТО: СЕКРЕТ]", value)
    value = _RE_EMAIL.sub("[СКРЫТО: КОНТАКТ]", value)
    value = _RE_HANDLE.sub("[СКРЫТО: КОНТАКТ]", value)
    value = _RE_TG_LINK.sub("[СКРЫТО: КОНТАКТ]", value)

    def repl_url(m: re.Match) -> str:
        return m.group(0) if _RE_FUNPAY.match(m.group(0)) else "[СКРЫТО: ССЫЛКА]"

    value = _RE_URL.sub(repl_url, value)

    def repl_phone(m: re.Match) -> str:
        return m.group(0) if _is_prod_num(value, m) else "[СКРЫТО: ТЕЛЕФОН]"

    value = _RE_PHONE.sub(repl_phone, value)

    def repl_card(m: re.Match) -> str:
        return m.group(0) if _is_prod_num(value, m) else "[СКРЫТО: РЕКВИЗИТЫ]"

    value = _RE_CARD.sub(repl_card, value)
    return value[:limit]


_RE_CONTACT = re.compile(r"(?:телеграм|telegram|\bтг\b|\btg\b|дискорд|discord|whatsapp|ватсап|e-?mail|почт|телефон)", re.I)
_RE_CONTACT_ASK = re.compile(r"(?:дай|скинь|кинь|покажи|напиши|ваш|твой|контакт|связ|написать)", re.I)
_RE_CONTACT_PRODUCT = re.compile(r"(?:подписчик|premium|премиум|nitro|нитро|зв[её]зд|boost|буст)", re.I)

_RE_POLICY_OFF_PLATFORM = re.compile(
    r"(?:(?:оплач\w*|заплат\w*|перевед\w*|скин\w*)\s+"
    r"(?:вне|мимо|без)\s+(?:funpay|фанп\w*)|"
    r"оплач\w*\s+(?:напрямую|на\s+карту|на\s+кошел)|"
    r"(?:обойд\w*|обойти)\s+(?:funpay|фанп\w*|комисси|систему)|"
    r"(?:напрямую|без\s+funpay|мимо\s+funpay)\s+(?:перевед\w*|скин\w*|оплач\w*)|"
    r"обмен\w*\s+денег|перевод\w*\s+между\s+(?:платёж|платеж|систем|реквизит))",
    re.I,
)
_RE_POLICY_ACCOUNT_TRADE = re.compile(
    r"(?:куп\w*|прод\w*|отда\w*|переда\w*|обмен\w*)\s+(?:аккаунт|акк)\s+"
    r"(?:funpay|фанп\w*)|"
    r"(?:аккаунт|акк)\s+(?:funpay|фанп\w*)\s+(?:куп\w*|прод\w*|отда\w*)",
    re.I,
)
_RE_POLICY_PROHIBITED = re.compile(
    r"(?:кардинг|carding|брутфорс|bruteforce|дюп|dupe|"
    r"персональн\w*\s+данн\w*|база\s+данн\w*|"
    r"нелицензионн\w*\s+по|вредоносн\w*\s+по|malware|"
    r"телефонн\w*\s+номер\w*|номера\s+(?:рф|украин|беларус)|"
    r"аккаунт\w*\s+опт\w*|оптом\s+аккаунт|"
    r"эротич\w*|порнограф\w*|18\+|"
    r"услуг\w*\s+по\s+спам|спам\w*\s+рассылк|"
    r"ставк\w*|казино|casino|рулетк|"
    r"способ\w*\s+донат|метод\w*\s+донат|накрутк\w*|"
    r"лотере\w*|розыгрыш\w*|рандом|random|"
    r"криптов\w*|крипт\w*|usdt|bitcoin|btc\b)",
    re.I,
)
_RE_POLICY_NO_PREPAY = re.compile(
    r"(?:давай|давайте|можно|хочу|предлагаю)\s+(?:без\s+оплат|"
    r"без\s+funpay|напрямую|сначала\s+товар|сначала\s+получу)",
    re.I,
)


def classify_policy_violation(text: str) -> str:
    scan = str(text or "")
    n = norm(scan)
    if not n:
        return ""
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


def policy_refusal(code: str) -> str:
    return refusal(code)


_LANG_RU = re.compile(r"[а-яё]", re.I)
_LANG_UK = re.compile(r"[іїєґ]", re.I)
_LANG_EN = re.compile(r"[a-z]", re.I)

_ANGER_MARKERS = re.compile(
    r"(?:\bбля\w*|\bхуй\w*|\bпизд\w*|\bеба\w*|\bсук\w*|\bнах\w*|"
    r"\bдерьм\w*|\bхер\w*|\bужас\w*|\bотврат\w*|\bобман\w*|\bкидал\w*|"
    r"\bмошен\w*|\bразвод\w*|\bскам\w*|"
    r"\bf+u+c+k+|shit\b|scam\w*|trash\b|terrible\b|awful\b)",
    re.I,
)

_LANG_NAME = {"ru": "русском", "uk": "украинском", "en": "английском"}


def detect_language(text: str) -> str:
    s = str(text or "")
    if not s.strip():
        return ""
    if _LANG_UK.search(s):
        return "uk"
    if _LANG_RU.search(s):
        return "ru"
    if _LANG_EN.search(s):
        return "en"
    return ""


def looks_angry(text: str) -> bool:
    n = norm(text)
    if not n:
        return False
    if _ANGER_MARKERS.search(n):
        return True
    raw = str(text or "")
    if raw.count("!") >= 3:
        return True
    letters = [c for c in raw if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
        return True
    return False


def language_hint(text: str) -> str:
    if not SETTINGS.get("match_language", True):
        return ""
    lang = detect_language(text)
    if lang in _LANG_NAME:
        return (
            f"Покупатель пишет на {_LANG_NAME[lang]} языке. Отвечай на этом же языке. "
            "Не переключайся на русский, даже если предыдущие сообщения были на русском."
        )
    return ""


def tone_hint(text: str) -> str:
    if not SETTINGS.get("neutral_on_anger", True):
        return ""
    if looks_angry(text):
        return (
            "Покупатель раздражён или агрессивен. НЕ зеркаль агрессию и не оправдывайся. "
            "Ответь спокойно, по-деловому и вежливо, сосредоточься на решении его вопроса."
        )
    return ""


_SELLER_HANDOFF_PATTERNS = [
    r"уточн\w*\s+у\s+продавц",
    r"уточн\w*\s+(?:это\s+)?у\s+продавц",
    r"передам\s+(?:ваш\s+)?(?:вопрос|запрос)?\s*продавц",
    r"передал\s+(?:ваш\s+)?(?:вопрос|запрос)?\s*продавц",
    r"передаю\s+(?:ваш\s+)?(?:вопрос|запрос)?\s*продавц",
    r"сообщ\w*\s+продавц",
    r"свяж\w*с\s+с\s+продавц",
    r"обращ\w*сь\s+к\s+продавц",
    r"напиш\w*\s+продавц",
    r"продавец\s+(?:ответит|подскажет|уточнит|свяжется|поможет)",
    r"передал\s+запрос\s+продавц",
    r"позов\w*\s+продавц",
    r"вызов\w*\s+продавц",
]

_UNCERTAIN_PATTERNS = [
    r"не\s+знаю", r"не\s+уверен\w*", r"не\s+могу\s+(?:точно|сказать|подтвердить|ответить)",
    r"нет\s+(?:точн\w*\s+)?(?:данн\w*|информац\w*|сведен\w*)",
    r"не\s+указан\w*", r"не\s+располага\w*",
    r"уточните", r"уточнить", r"подскажите",
    r"в\s+описании\s+(?:нет|не\s+указан)",
    r"к\s+сожалению,?\s+не", r"извините,?\s+не",
    r"не\s+могу\s+подсказать", r"затрудняюсь",
    r"не\s+понимаю", r"не\s+понял", r"не\s+расслышал",
]


def _build_trigger_re(patterns: list[str]) -> re.Pattern:
    extra = str(SETTINGS.get("seller_notify_patterns_extra") or "").strip()
    pattern = "|".join(patterns)
    if extra:
        pattern = f"{pattern}|{extra}"
    return re.compile(pattern, re.I)


def is_uncertain_answer(text: str) -> bool:
    n = norm(text)
    if not n:
        return True
    if _build_trigger_re(_UNCERTAIN_PATTERNS).search(n):
        return True
    if _build_trigger_re(_SELLER_HANDOFF_PATTERNS).search(n):
        return True
    return False


def notify_seller(c: "Cardinal", m: Any, buyer_text: str, ai_answer: str = "",
                  reason: str = "", header: str = "") -> bool:
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

    buyer_name = _safe_for_notify(
        str(getattr(m, "chat_name", "") or getattr(m, "author", "") or "покупатель"), 120
    )
    safe_buyer = _safe_for_notify(str(buyer_text or ""), 1000)
    safe_ai = _safe_for_notify(str(ai_answer or ""), 500)
    safe_reason = _safe_for_notify(str(reason or ""), 200)

    title = header or "🆘 <b>Требуется продавец</b>"
    body = (
        f"{title}\n\n"
        f"👤 Чат: <b>{utils.escape(buyer_name)}</b>\n"
        f"💬 Сообщение покупателя:\n<code>{utils.escape(safe_buyer)}</code>"
    )
    if safe_ai:
        body += f"\n\n🤖 Ответ AI:\n<i>{utils.escape(safe_ai)}</i>"
    if safe_reason:
        body += f"\n\n🧠 Причина: <i>{utils.escape(safe_reason)}</i>"

    keyboard = None
    try:
        callback = f"{CBT.SEND_FP_MESSAGE}:{getattr(m, 'chat_id', '')}:{buyer_name}"
        if len(callback.encode("utf-8")) <= 64:
            keyboard = K().add(B("✉️ Ответить покупателю", callback_data=callback))
    except Exception:
        keyboard = None

    def _job() -> None:
        try:
            c.telegram.send_notification(body, keyboard=keyboard)
        except Exception:
            logger.warning("Не удалось отправить уведомление продавцу", exc_info=True)

    threading.Thread(target=_job, daemon=True, name="KBAI-notify").start()
    return True


def _message_role(c: "Cardinal", item: Any) -> str | None:
    mt = getattr(item, "type", None)
    if mt is not None and mt is not MessageTypes.NON_SYSTEM:
        return None
    if any(bool(getattr(item, x, False)) for x in
           ("is_employee", "is_support", "is_moderation", "is_arbitration")):
        return None
    acc_id = getattr(getattr(c, "account", None), "id", None)
    author_id = getattr(item, "author_id", None)
    if getattr(item, "by_bot", False) or getattr(item, "by_vertex", False):
        return "assistant"
    if acc_id is not None and author_id == acc_id:
        return "assistant"
    return "user"


def _bootstrap_chat_history(c: "Cardinal", m: Any, current_text: str) -> None:
    if not SETTINGS.get("bootstrap_history", True):
        return
    chat_key = str(getattr(m, "chat_id", "") or "")
    if not chat_key:
        return
    with LOCK:
        if chat_key in CHAT_HISTORY_BOOTSTRAPPED:
            return
        CHAT_HISTORY_BOOTSTRAPPED.add(chat_key)
    get_chat = getattr(getattr(c, "account", None), "get_chat", None)
    if not callable(get_chat):
        return
    try:
        full = get_chat(getattr(m, "chat_id", chat_key), with_history=True)
        messages = list(getattr(full, "messages", None) or [])
    except Exception:
        logger.debug("bootstrap_chat_history(%s) failed", chat_key, exc_info=True)
        return
    if not messages:
        return
    current_id = str(getattr(m, "id", "") or "")
    current_safe = str(current_text or "").strip()
    cutoff: int | None = None
    if current_id:
        for i in range(len(messages) - 1, -1, -1):
            if str(getattr(messages[i], "id", "") or "") == current_id:
                cutoff = i
                break
    if cutoff is None and current_safe:
        for i in range(len(messages) - 1, -1, -1):
            it = messages[i]
            if _message_role(c, it) != "user":
                continue
            if str(getattr(it, "text", "") or "").strip() == current_safe:
                cutoff = i
                break
    if cutoff is None:
        cutoff = len(messages)
    imported: list[dict[str, str]] = []
    for item in messages[:cutoff][-100:]:
        role = _message_role(c, item)
        if role not in ("user", "assistant"):
            continue
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        imported.append({"role": role, "content": text[:2000]})
    if not imported:
        return
    with LOCK:
        existing = list(HISTORY.get(chat_key, []))
        if existing:
            combined: list[dict[str, str]] = list(imported) + existing[-5:]
            HISTORY[chat_key] = combined[-_HISTORY_HARD_CAP:]
        else:
            HISTORY[chat_key] = imported[-_HISTORY_HARD_CAP:]
    logger.info("chat=%s history_bootstrap=%d", chat_key, len(imported))


def _recent_assistant_said_about(chat_id: Any, pattern: str) -> bool:
    rx = re.compile(pattern, re.I)
    with LOCK:
        h = list(HISTORY.get(str(chat_id), []))
    for item in h:
        if item.get("role") != "assistant":
            continue
        if rx.search(item.get("content") or ""):
            return True
    return False


_RE_DISCOUNT = re.compile(r"\bскидк\w*|\bдешевле\b|\bторг\w*|\bснизить цен\w*|\bпромокод\w*|\bакци\w*", re.I)
_RE_OTHER_LOT = re.compile(r"^(?:друг\w*|а друг\w*|ещ[её]\b|не этот|не то|хочу друг\w*)[!?., ]*$", re.I)
_RE_HELP = re.compile(r"\bпомож\w*|\bподскаж\w*|\bсмож\w* помочь", re.I)
_RE_SELLER_COUNT = re.compile(r"сколько\s+(?:лотов|товаров|объявлени\w*)", re.I)
_RE_PRESENCE = re.compile(r"^(?:(?:ты|вы|продавец)\s+)?(?:тут|здесь|на месте|на связи)[!? ]*$|^есть кто\w*[!? ]*$", re.I)
_RE_CONTEXT_LOT = re.compile(
    r"\b(?:этот|эта|это|эти|данный|данная|данное|данного|текущий|текущая)\s+(?:товар\w*|лот\w*)\b", re.I)
_RE_GREET = re.compile(r"^(?:привет\w*|здравствуй\w*|добрый (?:день|вечер)|доброе утро|хай|hi|hello)[!., ]*$", re.I)
_RE_THANKS = re.compile(r"(?:спасибо|благодарю|спс)", re.I)
_RE_WELL = re.compile(r"\bкак (?:у (?:тебя|вас) )?дела\b|\bкак жизнь\b|\bкак настроение\b", re.I)
_RE_BYE = re.compile(r"^(?:пока|до свидания|до встречи|всего доброго)[!., ]*$", re.I)


def _apply_watermark(text: str) -> str:
    body = str(text or "").rstrip()
    if not SETTINGS.get("watermark", True):
        return body
    mark = str(SETTINGS.get("watermark_text") or "").strip()
    if not mark:
        return body
    if mark in body:
        return body
    return f"{body}\n\n{mark}"


def _say(c: "Cardinal", m: Any, text: str, *, notify: bool = False,
         reason: str = "", buyer_text: str = "", notify_header: str = "") -> bool:
    if not text or not is_enabled(c):
        return False
    out = _clean_ai_answer(str(text).strip())
    v = outbound_violation(out)
    if v and v != "empty":
        logger.warning("Privacy guard: %s", v)
        out = refusal(v)
        notify = False
    final = _apply_watermark(out)
    try:
        c.send_message(m.chat_id, final, m.chat_name, watermark=False)
        add_history(m.chat_id, "assistant", out)
    except Exception:
        logger.exception("say failed")
        return False
    if notify:
        notify_seller(c, m, buyer_text or "", out, reason=reason, header=notify_header)
    return True


def handle_deterministic(c: "Cardinal", m: Any, text: str) -> bool:
    n = norm(text)
    if _RE_GREET.search(n):
        _say(c, m, "Здравствуйте! 👋 Чем могу помочь?")
        return True
    if _RE_WELL.search(n):
        _say(c, m, "Всё хорошо, спасибо 😊 А у вас?")
        return True
    if _RE_PRESENCE.search(n):
        _say(c, m, "Да, я на связи 🤝")
        return True
    if _RE_THANKS.search(n) and len(n.split()) <= 8:
        _say(c, m, "Пожалуйста! 🤝")
        return True
    if _RE_BYE.search(n):
        _say(c, m, "До встречи! 👋")
        return True
    if _RE_DISCOUNT.search(n):
        already = _recent_assistant_said_about(m.chat_id, r"скидк")
        if already:
            _say(c, m,
                 "По скидке уже отвечал выше — скидка на усмотрение продавца. Передал повторный запрос продавцу 👌",
                 notify=True,
                 notify_header="🆘 <b>Покупатель повторно просит скидку</b>",
                 reason="Повторная просьба о скидке", buyer_text=text)
            return True
        _say(c, m,
             "Скидка остаётся на усмотрение продавца. Я передал ваш запрос продавцу — "
             "если он согласен, ответит в этом чате 👌",
             notify=True,
             notify_header="🆘 <b>Покупатель просит скидку</b>",
             reason="Просьба о скидке / торг", buyer_text=text)
        return True
    if _RE_OTHER_LOT.fullmatch(n):
        with LOCK:
            avail = list(LOTS.values())[:8]
        if avail:
            body = "Вот доступные лоты:\n" + "\n".join(f"{i}) {l.get('title')}" for i, l in enumerate(avail, 1))
            body += "\n\nНапишите название или номер нужного."
        else:
            body = "Напишите, пожалуйста, название нужного лота."
        _say(c, m, body)
        return True
    if _RE_HELP.search(n) and len(n.split()) <= 6:
        already = _recent_assistant_said_about(m.chat_id, r"помож|подскаж")
        if already:
            _say(c, m,
                 "Готов помочь — напишите одним сообщением, что именно нужно уточнить. Запрос уже передан продавцу.",
                 notify=True,
                 notify_header="🆘 <b>Покупатель повторно просит помощи</b>",
                 reason="Повторная просьба о помощи", buyer_text=text)
            return True
        _say(c, m,
             "Да, помогу 🤝 Напишите, что именно нужно уточнить. "
             "Параллельно я передал ваш запрос продавцу — если понадобится, он ответит в этом чате.",
             notify=True,
             notify_header="🆘 <b>Покупатель просит помощи</b>",
             reason="Покупатель просит помощи, но не уточнил с чем", buyer_text=text)
        return True
    if _RE_SELLER_COUNT.search(n):
        with LOCK:
            cnt = len(LOTS)
        _say(c, m, f"В профиле продавца сейчас {cnt} лотов.")
        return True
    violation = classify_policy_violation(text)
    if violation:
        _say(c, m, policy_refusal(violation))
        return True
    return False


def _obj(o, a, d=""):
    try:
        v = getattr(o, a, d)
        return "" if v is None else str(v)
    except Exception:
        return d


def _extract_extra_params(field_obj: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for attr in ("fields", "params", "game_params", "custom_fields", "lot_fields"):
        val = getattr(field_obj, attr, None)
        if isinstance(val, dict) and val:
            for k, v in val.items():
                if v is None or v == "" or v == [] or v == {}:
                    continue
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


def _lot_basic(lot) -> dict[str, Any]:
    sub = getattr(lot, "subcategory", None)
    return {
        "id": str(getattr(lot, "id", "")),
        "title": _obj(lot, "description") or _obj(lot, "title"),
        "description": _obj(lot, "description"),
        "full_description": "",
        "price": getattr(lot, "price", None),
        "currency": str(getattr(lot, "currency", "") or ""),
        "amount": getattr(lot, "amount", None),
        "auto": bool(getattr(lot, "auto", False)),
        "subcategory": _obj(sub, "fullname") or _obj(sub, "name"),
        "server": _obj(lot, "server"),
        "extra_fields": {},
    }


def _enrich(c: "Cardinal", lid: str) -> None:
    try:
        f = c.account.get_lot_fields(int(lid) if lid.isdigit() else lid)
        with LOCK:
            if lid not in LOTS:
                return
            t = _obj(f, "title_ru") or _obj(f, "title_en")
            d = _obj(f, "description_ru") or _obj(f, "description_en")
            if t:
                LOTS[lid]["title"] = t
            LOTS[lid]["full_description"] = d
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
    except Exception:
        logger.debug("enrich %s", lid, exc_info=True)


def sync_lots(c: "Cardinal", enrich: bool = True) -> int:
    try:
        p = c.profile or c.account.get_user(c.account.id)
        lots = list(p.get_lots()) if p else []
    except Exception:
        logger.exception("sync_lots")
        return 0
    cache = {}
    for l in lots:
        d = _lot_basic(l)
        if d["id"]:
            cache[d["id"]] = d
    with LOCK:
        for lid, old in LOTS.items():
            if lid in cache:
                if old.get("full_description"):
                    cache[lid]["full_description"] = old["full_description"]
                if old.get("extra_fields"):
                    cache[lid]["extra_fields"] = old["extra_fields"]
        LOTS.clear()
        LOTS.update(cache)
    if enrich:
        for lid in list(cache):
            if STOP.is_set():
                break
            _enrich(c, lid)
            time.sleep(1.0)
    logger.info("Лотов: %d", len(cache))
    return len(cache)


def lot_worker(c: "Cardinal") -> None:
    sync_lots(c, enrich=True)
    while not STOP.wait(max(60, SETTINGS["lot_refresh_minutes"] * 60)):
        if is_enabled(c):
            try:
                sync_lots(c, enrich=True)
            except Exception:
                logger.exception("lot_worker")


def add_history(chat_id: Any, role: str, text: str) -> None:
    t = str(text or "").strip()[:3000]
    if not t:
        return
    with LOCK:
        h = HISTORY.setdefault(str(chat_id), [])
        h.append({"role": role, "content": t})
        if len(h) > _HISTORY_HARD_CAP:
            del h[:-_HISTORY_HARD_CAP]


def _history_for_api(chat_id: Any, exclude_last_user: str = "") -> list[dict[str, str]]:
    with LOCK:
        h = list(HISTORY.get(str(chat_id), []))
    if h and h[-1].get("role") == "user" and h[-1].get("content") == exclude_last_user:
        h = h[:-1]
    budget = max(2000, int(SETTINGS.get("history_char_budget", 12000)))
    total = 0
    keep: list[dict[str, str]] = []
    for item in reversed(h):
        ln = len(item.get("content") or "") + 8
        if total + ln > budget and keep:
            break
        keep.append(item)
        total += ln
    keep.reverse()
    return keep


def _get_viewing(c: "Cardinal", m: Any) -> Any:
    viewing = getattr(m, "buyer_viewing", None)
    if viewing and getattr(viewing, "is_viewing_lot", False):
        return viewing
    buyer_id = getattr(m, "interlocutor_id", None)
    if not buyer_id:
        return None
    key = str(buyer_id)
    now = time.time()
    with LOCK:
        cached = VIEWING_CACHE.get(key)
    if cached and now - cached[0] < 45:
        return cached[1]
    try:
        viewing = c.account.get_buyer_viewing(buyer_id)
    except Exception:
        logger.debug("get_buyer_viewing(%s) failed", buyer_id, exc_info=True)
        viewing = None
    with LOCK:
        VIEWING_CACHE[key] = (now, viewing)
    return viewing


def _remember_chat_lot(chat_id: Any, lot: dict[str, Any] | None) -> None:
    if not lot:
        return
    key = str(chat_id or "")
    lid = str(lot.get("id") or "")
    if not key or not lid:
        return
    with LOCK:
        CHAT_LOT[key] = lid
        CHAT_LOT_AT[key] = time.time()


def _last_chat_lot(chat_id: Any, ttl_seconds: int = 1800) -> dict[str, Any] | None:
    key = str(chat_id or "")
    with LOCK:
        lid = CHAT_LOT.get(key)
        seen = CHAT_LOT_AT.get(key, 0.0)
        lot = LOTS.get(lid) if lid else None
    if lot and time.time() - seen <= ttl_seconds:
        return lot
    if lid:
        with LOCK:
            CHAT_LOT.pop(key, None)
            CHAT_LOT_AT.pop(key, None)
    return None


def _get_lot(c: "Cardinal", m: Any, text: str) -> dict[str, Any] | None:
    n = norm(text)
    ranked = find_lots(text, 3)
    if ranked:
        best, score = ranked[0]
        if score >= 0.52:
            second = ranked[1][1] if len(ranked) > 1 else 0.0
            if len(ranked) == 1 or score - second >= 0.04 or score >= 0.8:
                _remember_chat_lot(m.chat_id, best)
                return best
    if _RE_CONTEXT_LOT.search(n):
        prev = _last_chat_lot(m.chat_id)
        if prev:
            return prev
    viewing = _get_viewing(c, m)
    if viewing and getattr(viewing, "is_viewing_lot", False):
        lid = str(getattr(viewing, "lot_id", ""))
        with LOCK:
            lot = LOTS.get(lid)
        if lot:
            _remember_chat_lot(m.chat_id, lot)
            return lot
        try:
            if lid:
                _enrich(c, lid)
                with LOCK:
                    lot = LOTS.get(lid)
                if lot:
                    _remember_chat_lot(m.chat_id, lot)
                    return lot
        except Exception:
            logger.debug("enrich from viewing failed", exc_info=True)
        vtext = str(getattr(viewing, "text", "") or "").strip()
        if vtext:
            ranked2 = find_lots(vtext, 1)
            if ranked2 and ranked2[0][1] >= 0.5:
                lot = ranked2[0][0]
                _remember_chat_lot(m.chat_id, lot)
                return lot
            synthetic = {
                "id": lid or "viewing", "title": vtext[:200], "description": vtext[:200],
                "full_description": "", "price": None, "currency": "", "amount": None,
                "auto": False, "subcategory": "", "server": "", "extra_fields": {},
            }
            _remember_chat_lot(m.chat_id, synthetic)
            return synthetic
    return None


def _lot_prompt(lot: dict[str, Any] | None) -> str:
    if not lot:
        return "Товар не определён. Не выдумывай; если нужен конкретный лот — уточни."
    base = (
        f"Название: {lot.get('title') or '—'}\n"
        f"Цена: {lot.get('price')} {lot.get('currency') or ''}\n"
        f"Количество: {lot.get('amount') if lot.get('amount') is not None else '—'}\n"
        f"Автовыдача: {'да' if lot.get('auto') else 'нет'}\n"
        f"Категория: {lot.get('subcategory') or '—'}\n"
        f"Описание: {(lot.get('full_description') or lot.get('description') or '')[:1200]}"
    )
    extra = lot.get("extra_fields") or {}
    if isinstance(extra, dict) and extra:
        lines: list[str] = []
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
            base += "\n\nИГРОВЫЕ ПАРАМЕТРЫ ЛОТА (от FunPay, авторитетный источник):\n" + "\n".join(lines)
    return base


def _sys_prompt(lot: dict[str, Any] | None, full_chat: bool,
                lang_hint: str = "", tone_hint_text: str = "") -> str:
    seller = str(SETTINGS.get("seller_info") or "").strip()
    memory_note = (
        "Ты видишь ВСЮ историю этого чата. Используй её для контекста, но отвечай ТОЛЬКО на последнее "
        "сообщение покупателя — не пересказывай историю, не отвечай на старые вопросы повторно."
    ) if full_chat else "Ты видишь последние сообщения чата."
    viewing_note = (
        "В блоке ТЕКУЩИЙ ТОВАР уже передан лот, который покупатель смотрит на FunPay. "
        "НЕ проси уточнить, о каком лоте речь — сразу отвечай по нему."
        if lot else
        "Точного лота нет — если вопрос требует конкретного товара, задай ОДИН короткий уточняющий вопрос."
    )
    extra = ""
    if lang_hint:
        extra += f"\nЯЗЫК ОТВЕТА:\n{lang_hint}\n"
    if tone_hint_text:
        extra += f"\nТОН ОТВЕТА:\n{tone_hint_text}\n"
    promises = ""
    if SETTINGS.get("no_unconfirmed_promises", True):
        promises = (
            "\nОБЕЩАНИЯ И СКИДКИ:\n"
            "- НИКОГДА не обещай скидку, бонус, подарок, акцию, бесплатную услугу, срочность, "
            "приоритет в очереди, гарантию и прочие блага, если это явно не указано в блоке ТЕКУЩИЙ ТОВАР.\n"
            "- Если покупатель спрашивает про скидку/бонус, а в лоте их нет — честно скажи: "
            "«В лоте скидка/бонус не указана».\n"
            "- Не обещай от лица продавца то, чего ты не знаешь. Можно передать запрос продавцу.\n"
        )
    return (
        f"{SETTINGS['system_prompt']}\n\n"
        f"ПАМЯТЬ ДИАЛОГА:\n{memory_note}\n\n"
        f"КОНТЕКСТ ТОВАРА:\n{viewing_note}\n\n"
        f"ИНФОРМАЦИЯ О ПРОДАВЦЕ:\n{seller or 'не задана'}\n\n"
        f"ТЕКУЩИЙ ТОВАР:\n{_lot_prompt(lot)}\n\n"
        f"{FUNPAY_RULES_SNAPSHOT}\n\n"
        f"{promises}{extra}\n"
        "Дополнительно:\n"
        "- «Аккаунт Standoff/Steam/CS2/Valorant/Telegram» — обычный товар, НЕ данные продавца.\n"
        "- Скидка/торг — на усмотрение продавца, ты передал запрос. Если уже отказали — подтверди.\n"
        "- Название платформы внутри товара — НЕ контакт.\n"
        "- Если в ИГРОВЫХ ПАРАМЕТРАХ ЛОТА есть нужное значение — отвечай точно по нему."
    )


def ask_ai(m: Any, buyer_text: str, lot: dict[str, Any] | None) -> str:
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
    history = _history_for_api(getattr(m, "chat_id", ""), exclude_last_user=buyer_text)
    full_chat = len(history) > 2
    lang_hint = language_hint(buyer_text)
    tone_hint_text = tone_hint(buyer_text)
    msgs: list[dict[str, str]] = [{"role": "system",
                                   "content": _sys_prompt(lot, full_chat, lang_hint, tone_hint_text)}]
    msgs += history
    msgs.append({"role": "user", "content": buyer_text})
    r = requests.post(
        base + "/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": msgs, "temperature": float(SETTINGS["temperature"]),
              "max_tokens": int(SETTINGS["num_predict"]), "stream": False},
        timeout=(10, max(30, int(SETTINGS["ai_timeout"]))),
    )
    r.raise_for_status()
    data = r.json()
    text = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("AI вернул пустой ответ.")
    return text


def handle_message(c: "Cardinal", m: Any, text: str) -> None:
    violation = classify_policy_violation(text)
    if violation:
        _say(c, m, policy_refusal(violation))
        logger.info("policy_violation=%s chat=%s", violation, getattr(m, "chat_id", "?"))
        return
    if handle_deterministic(c, m, text):
        return
    lot = _get_lot(c, m, text)
    try:
        answer = ask_ai(m, text, lot)
    except Exception as e:
        logger.warning("AI fail: %s: %s", type(e).__name__, e)
        _say(c, m, str(SETTINGS["unknown_reply"]),
             notify=True,
             notify_header="🆘 <b>AI-провайдер не ответил</b>",
             reason="API недоступен или вернул ошибку",
             buyer_text=text)
        return
    uncertain = is_uncertain_answer(answer)
    header = ""
    reason = ""
    if uncertain:
        na = norm(answer)
        if _build_trigger_re(_SELLER_HANDOFF_PATTERNS).search(na):
            header = "🆘 <b>AI предлагает подключить продавца</b>"
            reason = "AI не знает точного ответа и передаёт запрос продавцу"
        else:
            header = "🆘 <b>AI не смог ответить уверенно</b>"
            reason = "AI не уверен в ответе"
    extra_trigger = False
    na = norm(answer)
    if not uncertain and SETTINGS.get("confidence_notify", True):
        if re.search(r"скидк|бонус|промокод|акци", na) and re.search(
            r"усмотрени|продавц|не\s+указан|передам|передал", na
        ):
            extra_trigger = True
            header = "🆘 <b>AI упомянул скидку/бонус</b>"
            reason = "AI ответил про скидку/бонус — проверьте"
        elif re.search(r"(?:передам|передал|уточн\w*|сообщ\w*)\s+(?:это\s+)?продавц", na):
            extra_trigger = True
            header = "🆘 <b>AI предлагает подключить продавца</b>"
            reason = "AI передал вопрос продавцу"
    notify = bool((uncertain or extra_trigger) and SETTINGS.get("confidence_notify", True))
    _say(c, m, answer, notify=notify, notify_header=header, reason=reason, buyer_text=text)


def _drain(chat: str) -> None:
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
            if delay:
                time.sleep(delay)
            _bootstrap_chat_history(c, m, text)
            add_history(chat, "user", text)
            handle_message(c, m, text)
        except Exception:
            logger.exception("queue handler chat=%s", chat)


def _enqueue(c: "Cardinal", m: Any, text: str) -> None:
    chat = str(getattr(m, "chat_id", "") or "")
    if not chat or not text.strip() or STOP.is_set():
        return
    start = False
    with LOCK:
        QUEUES.setdefault(chat, deque()).append((c, m, text.strip()))
        if chat not in ACTIVE:
            ACTIVE.add(chat)
            start = True
    if start:
        try:
            POOL.submit(_drain, chat)
        except RuntimeError:
            with LOCK:
                QUEUES.pop(chat, None)
                ACTIVE.discard(chat)


def _mark(mid: Any) -> bool:
    k = str(mid)
    now = time.time()
    with LOCK:
        for kk, ts in list(DONE.items()):
            if now - ts > 600:
                DONE.pop(kk, None)
        if k in DONE:
            return False
        DONE[k] = now
    return True


def on_message(c: "Cardinal", e: "NewMessageEvent") -> None:
    if not is_enabled(c) or getattr(c, "old_mode_enabled", False):
        return
    m = e.message
    if getattr(m, "author_id", 0) in (0, getattr(c.account, "id", None)):
        return
    if getattr(m, "by_bot", False) or getattr(m, "by_vertex", False):
        return
    if getattr(m, "type", None) is not MessageTypes.NON_SYSTEM:
        return
    if any(bool(getattr(m, x, False)) for x in ("is_employee", "is_support", "is_moderation", "is_arbitration", "is_autoreply")):
        return
    if getattr(m, "chat_name", None) in getattr(c, "blacklist", []):
        return
    try:
        if e.stack and m.id != e.stack.get_stack()[-1].message.id:
            return
    except Exception:
        pass
    if not _mark(getattr(m, "id", f"{m.chat_id}:{time.time_ns()}")):
        return
    text = (getattr(m, "text", None) or "").strip()
    if text:
        _enqueue(c, m, text)


def on_last_chat(c: "Cardinal", e: Any) -> None:
    if not is_enabled(c) or not getattr(c, "old_mode_enabled", False):
        return
    ch = getattr(e, "chat", None)
    if ch is None or not getattr(ch, "unread", False):
        return
    if getattr(ch, "last_by_bot", False) or getattr(ch, "last_by_vertex", False):
        return
    if getattr(ch, "last_message_type", None) is not MessageTypes.NON_SYSTEM:
        return
    if getattr(ch, "name", None) in getattr(c, "blacklist", []):
        return

    def job() -> None:
        try:
            full = c.account.get_chat(ch.id, with_history=True)
            msgs = list(getattr(full, "messages", None) or [])
            if not msgs:
                return
            m = msgs[-1]
            if getattr(m, "author_id", 0) in (0, getattr(c.account, "id", None)):
                return
            if not getattr(m, "buyer_viewing", None) and getattr(full, "looking_link", None):
                try:
                    m.buyer_viewing = BuyerViewing(
                        getattr(m, "interlocutor_id", None) or 0,
                        full.looking_link,
                        getattr(full, "looking_text", None),
                        None,
                    )
                except Exception:
                    logger.debug("BuyerViewing fallback failed", exc_info=True)
            text = (getattr(m, "text", None) or "").strip()
            if text and _mark(getattr(m, "id", f"legacy:{ch.id}")):
                _enqueue(c, m, text)
        except Exception:
            logger.exception("legacy handler")
    POOL.submit(job)


def init_telegram(cardinal: "Cardinal") -> None:
    load_config()
    if not cardinal.telegram:
        return
    tg, bot = cardinal.telegram, cardinal.telegram.bot

    def main_text() -> str:
        with LOCK:
            n_chats = len(HISTORY)
            n_msgs = sum(len(h) for h in HISTORY.values())
            n_view = sum(1 for _, v in VIEWING_CACHE.values() if v and getattr(v, "is_viewing_lot", False))
        wm = str(SETTINGS.get("watermark_text") or "").strip()
        return (
            f"🤖 <b>{NAME} v{VERSION}</b>\n\n"
            f"Автор: <b>{CREDITS}</b>\n"
            f"🟢 Автоответ: <b>{utils.bool_to_text(SETTINGS['enabled'])}</b>\n"
            f"💧 Водяной знак: <b>{utils.bool_to_text(SETTINGS.get('watermark', True))}</b>"
            + (f"\n     <i>{utils.escape(wm)}</i>" if wm else "") + "\n"
            f"🔔 Уведомления: <b>{utils.bool_to_text(SETTINGS.get('seller_notify', True))}</b>"
            + (f" · cooldown <b>{SETTINGS.get('seller_notify_cooldown', 5)} мин</b>" if SETTINGS.get('seller_notify', True) else "") + "\n"
            f"📜 История из FunPay: <b>{utils.bool_to_text(SETTINGS.get('bootstrap_history', True))}</b>\n"
            f"📋 Правила FunPay: <b>встроены</b>\n"
            f"🌍 Язык: <b>{utils.bool_to_text(SETTINGS.get('match_language', True))}</b> · "
            f"🧊 Тон: <b>{utils.bool_to_text(SETTINGS.get('neutral_on_anger', True))}</b>\n"
            f"🚫 Обещания: <b>{utils.bool_to_text(SETTINGS.get('no_unconfirmed_promises', True))}</b> · "
            f"🔔 Неувер.: <b>{utils.bool_to_text(SETTINGS.get('confidence_notify', True))}</b>\n"
            f"🎮 Игровые параметры: <b>подтягиваются</b>\n"
            f"🌐 API: <code>{utils.escape(str(SETTINGS.get('api_url') or '—'))}</code>\n"
            f"🧠 Модель: <code>{utils.escape(str(SETTINGS.get('api_model') or 'не выбрана'))}</code>\n"
            f"🔑 Ключ: <b>{'задан' if SETTINGS.get('api_key') else 'не задан'}</b>\n"
            f"🛍 Лотов: <b>{len(LOTS)}</b> · 👀 Смотрят: <b>{n_view}</b>\n"
            f"💬 Память: <b>{n_chats}</b> чатов / <b>{n_msgs}</b> сообщений\n"
            f"⏱ Timeout: <b>{SETTINGS['ai_timeout']}с</b>\n"
            f"🔄 Обновления: <b>{utils.escape(update_status_line())}</b>"
        )

    def main_kb() -> K:
        kb = K(row_width=2)
        kb.row(B(f"Автоответ {utils.bool_to_text(SETTINGS['enabled'])}", callback_data=f"{CB}:tog"),
               B(f"🔔 Уведомл. {utils.bool_to_text(SETTINGS.get('seller_notify', True))}", callback_data=f"{CB}:notify"))
        kb.row(B(f"💧 Знак {utils.bool_to_text(SETTINGS.get('watermark', True))}", callback_data=f"{CB}:wm"),
               B("✏️ Текст знака", callback_data=f"{CB}:wmtext"))
        kb.row(B("⏱ Cooldown уведомл.", callback_data=f"{CB}:cooldown"), B("🧪 Уведомить сейчас", callback_data=f"{CB}:notify_test"))
        kb.row(B("🌐 API URL", callback_data=f"{CB}:url"), B("🔑 API key", callback_data=f"{CB}:key"))
        kb.row(B("🧠 Модель", callback_data=f"{CB}:model"), B("📝 Промпт", callback_data=f"{CB}:prompt"))
        kb.row(B("🏪 Продавец", callback_data=f"{CB}:seller"), B("⏱ Timeout", callback_data=f"{CB}:timeout"))
        kb.row(B("📏 Бюджет истории", callback_data=f"{CB}:budget"), B("📋 Логи чатов", callback_data=f"{CB}:chats"))
        kb.row(B("🔄 Обновить лоты", callback_data=f"{CB}:lots"), B("📜 Bootstrap ист.", callback_data=f"{CB}:bootstrap"))
        kb.row(B("📋 Правила FunPay", callback_data=f"{CB}:rules"), B("🧪 Тест API", callback_data=f"{CB}:test"))
        kb.row(B(f"🌍 Язык {utils.bool_to_text(SETTINGS.get('match_language', True))}", callback_data=f"{CB}:lang"),
               B(f"🧊 Тон {utils.bool_to_text(SETTINGS.get('neutral_on_anger', True))}", callback_data=f"{CB}:tone"))
        kb.row(B(f"🚫 Без обещаний {utils.bool_to_text(SETTINGS.get('no_unconfirmed_promises', True))}", callback_data=f"{CB}:nopromise"),
               B(f"🔔 Неувер. {utils.bool_to_text(SETTINGS.get('confidence_notify', True))}", callback_data=f"{CB}:confnotify"))
        kb.row(B(f"🔄 Обновления: {update_status_line()[:24]}", callback_data=f"{CB}:update"),
               B("⚙️ Автообновл.", callback_data=f"{CB}:updcfg"))
        kb.add(B("🗑 Сбросить всю память", callback_data=f"{CB}:clear_history"))
        kb.add(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        return kb

    def show(call: CallbackQuery) -> None:
        try:
            bot.edit_message_text(main_text(), call.message.chat.id, call.message.id, reply_markup=main_kb())
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("show failed", exc_info=True)

    def toggle(call: CallbackQuery) -> None:
        SETTINGS["enabled"] = not SETTINGS["enabled"]; save_config(); show(call)

    def toggle_wm(call: CallbackQuery) -> None:
        SETTINGS["watermark"] = not bool(SETTINGS.get("watermark", True)); save_config(); show(call)

    def toggle_notify(call: CallbackQuery) -> None:
        SETTINGS["seller_notify"] = not bool(SETTINGS.get("seller_notify", True)); save_config(); show(call)

    def toggle_bootstrap(call: CallbackQuery) -> None:
        SETTINGS["bootstrap_history"] = not bool(SETTINGS.get("bootstrap_history", True)); save_config(); show(call)

    def toggle_lang(call: CallbackQuery) -> None:
        SETTINGS["match_language"] = not bool(SETTINGS.get("match_language", True)); save_config(); show(call)

    def toggle_tone(call: CallbackQuery) -> None:
        SETTINGS["neutral_on_anger"] = not bool(SETTINGS.get("neutral_on_anger", True)); save_config(); show(call)

    def toggle_nopromise(call: CallbackQuery) -> None:
        SETTINGS["no_unconfirmed_promises"] = not bool(SETTINGS.get("no_unconfirmed_promises", True)); save_config(); show(call)

    def toggle_confnotify(call: CallbackQuery) -> None:
        SETTINGS["confidence_notify"] = not bool(SETTINGS.get("confidence_notify", True)); save_config(); show(call)

    def clear_history(call: CallbackQuery) -> None:
        with LOCK:
            HISTORY.clear(); CHAT_HISTORY_BOOTSTRAPPED.clear(); VIEWING_CACHE.clear()
            CHAT_LOT.clear(); CHAT_LOT_AT.clear(); SELLER_NOTIFY_AT.clear()
        bot.answer_callback_query(call.id, "✅ Память диалогов сброшена")
        show(call)

    def list_chats(call: CallbackQuery) -> None:
        with LOCK:
            items = list(HISTORY.items())
        if not items:
            text = "💬 Диалогов в памяти нет."
        else:
            lines = ["💬 <b>Активные диалоги в памяти</b>", ""]
            for cid, hist in items[:30]:
                n_a = sum(1 for x in hist if x.get("role") == "assistant")
                n_u = sum(1 for x in hist if x.get("role") == "user")
                lines.append(f"<code>{utils.escape(str(cid))}</code> — всего {len(hist)} · 👤 {n_u} · 🤖/🏪 {n_a}")
            if len(items) > 30:
                lines.append(f"… и ещё {len(items) - 30}")
            text = "\n".join(lines)
        kb = K().add(B("◀️ Назад", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("list_chats failed", exc_info=True)

    def show_rules(call: CallbackQuery) -> None:
        text = (
            "📋 <b>Снимок правил FunPay в промпте</b>\n"
            "Источник: <a href='https://funpay.com/trade/info'>funpay.com/trade/info</a>\n\n"
            f"<pre>{utils.escape(FUNPAY_RULES_SNAPSHOT[:3500])}</pre>"
        )
        kb = K().add(B("◀️ Назад", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("show_rules failed", exc_info=True)

    def ask(state: str, prompt: str):
        def cb(call: CallbackQuery) -> None:
            msg = bot.send_message(call.message.chat.id, prompt, reply_markup=CLEAR_STATE_BTN())
            tg.set_state(call.message.chat.id, msg.id, call.from_user.id, state)
            bot.answer_callback_query(call.id)
        return cb

    def make_setter(field: str, validate=None, transform=None):
        def setter(m: Message) -> None:
            tg.clear_state(m.chat.id, m.from_user.id, True)
            v = (m.text or "").strip()
            if validate and not validate(v):
                bot.reply_to(m, "❌ Некорректное значение."); return
            SETTINGS[field] = transform(v) if transform else v
            save_config()
            bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
        return setter

    def test_api(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Проверяю…")
        try:
            base = str(SETTINGS.get("api_url") or "").rstrip("/")
            key = str(SETTINGS.get("api_key") or "")
            if key.lower().startswith("env:"):
                key = os.environ.get(key[4:].strip(), "")
            model = str(SETTINGS.get("api_model") or "")
            if not base or not key or not model:
                bot.send_message(call.message.chat.id, "❌ Заполните URL, ключ и модель."); return
            r = requests.post(base + "/chat/completions",
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"model": model,
                                    "messages": [{"role": "user", "content": "Ответь одним словом OK"}],
                                    "max_tokens": 16, "temperature": 0},
                              timeout=(10, 30))
            r.raise_for_status()
            data = r.json()
            ans = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            bot.send_message(call.message.chat.id, f"✅ Ответ API: <code>{utils.escape(ans[:120])}</code>")
        except Exception as e:
            bot.send_message(call.message.chat.id,
                             f"❌ Ошибка:\n<code>{utils.escape(f'{type(e).__name__}: {e}'[:500])}</code>")

    def notify_test(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Отправляю…")
        def job():
            try:
                body = ("🆘 <b>Покупатель вызывает продавца</b>\n\n"
                        "👤 Чат: <b>KiriillBR AI</b>\n"
                        "💬 Сообщение: <code>тестовое уведомление</code>\n\n"
                        "🧠 Причина AI: <i>Проверка канала уведомлений</i>")
                cardinal.telegram.send_notification(body)
            except Exception as e:
                logger.warning("test notify failed: %s", e)
        threading.Thread(target=job, daemon=True, name="KBAI-notify-test").start()

    def refresh_lots(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Запущено…")
        msg = bot.send_message(call.message.chat.id, "🔄 Синхронизирую лоты…")
        def job():
            cnt = sync_lots(cardinal, enrich=False)
            try:
                bot.edit_message_text(f"✅ Синхронизировано: {cnt}.", msg.chat.id, msg.id,
                                      reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
            except Exception:
                pass
        POOL.submit(job)

    def updates_text() -> str:
        with LOCK:
            manifest = UPDATE_STATE.get("manifest")
            status = str(UPDATE_STATE.get("status") or "not_checked")
            err = str(UPDATE_STATE.get("error") or "")
            checked = float(UPDATE_STATE.get("checked_at", 0.0) or 0.0)
        url = _manifest_url()
        lines = [
            "🔄 <b>Обновления KiriillBR AI</b>", "",
            f"Текущая версия: <code>{utils.escape(VERSION)}</code>",
            f"Статус: <b>{utils.escape(update_status_line())}</b>",
            f"Автопроверка: <b>{utils.bool_to_text(SETTINGS.get('update_checks_enabled', True))}</b>",
            f"Автоустановка: <b>{utils.bool_to_text(SETTINGS.get('auto_update', False))}</b>",
            f"Автоперезапуск: <b>{utils.bool_to_text(SETTINGS.get('auto_restart_after_update', False))}</b>",
            f"Интервал: <b>{SETTINGS.get('update_check_interval_minutes', 30)} мин</b>",
            f"Manifest: <code>{utils.escape(url[:80])}</code>",
        ]
        if checked:
            lines.append(f"Последняя проверка: <code>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(checked))}</code>")
        if isinstance(manifest, dict):
            lines.append("")
            lines.append(f"Версия на сервере: <b>v{utils.escape(str(manifest.get('version') or '?'))}</b>")
            if manifest.get("mandatory"):
                lines.append("🚨 <b>Обновление помечено как важное.</b>")
            notes = str(manifest.get("notes") or "").strip()
            if notes:
                lines.append(f"📝 {utils.escape(notes[:1200])}")
        if status == "error" and err:
            lines.extend(["", f"⚠️ <code>{utils.escape(err[:400])}</code>"])
        lines.extend([
            "",
            "🛡 Проверяется HTTPS, SHA-256, UUID и синтаксис Python. Старый файл сохраняется как <code>.bak</code>.",
        ])
        return "\n".join(lines)

    def updates_kb() -> K:
        kb = K(row_width=2)
        kb.row(
            B(f"🔎 Автопроверка {utils.bool_to_text(SETTINGS.get('update_checks_enabled', True))}", callback_data=f"{CB}:upd:checks"),
            B(f"⚡ Автоустановка {utils.bool_to_text(SETTINGS.get('auto_update', False))}", callback_data=f"{CB}:upd:auto"),
        )
        kb.add(B(f"♻️ Автоперезапуск {utils.bool_to_text(SETTINGS.get('auto_restart_after_update', False))}", callback_data=f"{CB}:upd:autorestart"))
        kb.row(
            B("🔄 Проверить сейчас", callback_data=f"{CB}:upd:check"),
            B(f"⏱ {SETTINGS.get('update_check_interval_minutes', 30)} мин", callback_data=f"{CB}:upd:interval"),
        )
        with LOCK:
            manifest = UPDATE_STATE.get("manifest")
            available = bool(UPDATE_STATE.get("available"))
        if available and isinstance(manifest, dict):
            kb.add(B(f"⬆️ Установить v{manifest.get('version')}", callback_data=f"{CB}:upd:install"))
        pending = str(SETTINGS.get("pending_restart_version") or "")
        if pending and _version_key(pending) > _version_key(VERSION):
            kb.add(B(f"♻️ Перезапустить и включить v{pending}", callback_data=f"{CB}:upd:restart"))
        kb.add(B("◀️ Назад", callback_data=f"{CB}:main"))
        return kb

    def open_updates(call: CallbackQuery) -> None:
        try:
            bot.edit_message_text(updates_text(), call.message.chat.id, call.message.id, reply_markup=updates_kb())
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("open_updates failed", exc_info=True)

    def update_cb(call: CallbackQuery) -> None:
        action = call.data.split(":")[-1]
        try:
            if action == "checks":
                SETTINGS["update_checks_enabled"] = not bool(SETTINGS.get("update_checks_enabled", True))
                save_config(); bot.answer_callback_query(call.id, "✅"); open_updates(call); return
            if action == "auto":
                SETTINGS["auto_update"] = not bool(SETTINGS.get("auto_update", False))
                if not SETTINGS["auto_update"]:
                    SETTINGS["auto_restart_after_update"] = False
                save_config(); bot.answer_callback_query(call.id, "✅"); open_updates(call); return
            if action == "autorestart":
                if not SETTINGS.get("auto_update", False):
                    bot.answer_callback_query(call.id, "Сначала включите автоустановку.", show_alert=True); return
                SETTINGS["auto_restart_after_update"] = not bool(SETTINGS.get("auto_restart_after_update", False))
                save_config(); bot.answer_callback_query(call.id, "✅"); open_updates(call); return
            if action == "check":
                manifest, err = check_updates_cycle(cardinal, notify=False, force=True)
                if manifest is None:
                    bot.answer_callback_query(call.id, (err or "Ошибка")[:180], show_alert=True)
                elif _version_key(str(manifest.get("version") or "")) > _version_key(VERSION):
                    bot.answer_callback_query(call.id, f"Доступна v{manifest.get('version')}!", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, f"v{VERSION} — актуальная.", show_alert=True)
                open_updates(call); return
            if action == "install":
                with LOCK:
                    manifest = UPDATE_STATE.get("manifest")
                ok, msg = install_update(cardinal, manifest if isinstance(manifest, dict) else None)
                bot.answer_callback_query(call.id, msg[:180], show_alert=True)
                open_updates(call); return
            if action == "restart":
                pending = str(SETTINGS.get("pending_restart_version") or "")
                if not pending:
                    bot.answer_callback_query(call.id, "Нет обновления к применению.", show_alert=True); return
                bot.answer_callback_query(call.id, "Перезапускаю…", show_alert=True)
                try:
                    bot.send_message(call.message.chat.id, f"♻️ Перезапускаю Cardinal для v{utils.escape(pending)}.")
                except Exception:
                    pass
                _restart_cardinal(1.5); return
            if action == "interval":
                msg = bot.send_message(call.message.chat.id, "Интервал проверки 10–1440 минут:",
                                       reply_markup=CLEAR_STATE_BTN())
                tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_UPD_INT)
                bot.answer_callback_query(call.id); return
        except Exception:
            logger.debug("update_cb failed", exc_info=True)
        open_updates(call)

    def cmd_ai(m: Message) -> None:
        bot.send_message(m.chat.id, main_text(), reply_markup=main_kb())

    def set_update_interval(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        try:
            v = int((m.text or "").strip())
            if not 10 <= v <= 1440:
                raise ValueError
        except Exception:
            bot.reply_to(m, "❌ Введите число 10–1440."); return
        SETTINGS["update_check_interval_minutes"] = v
        save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ К обновлениям", callback_data=f"{CB}:update")))

    tg.cbq_handler(show, lambda c: c.data in (f"{CB}:main", f"{CBT.PLUGIN_SETTINGS}:{UUID}"))
    tg.cbq_handler(toggle, lambda c: c.data == f"{CB}:tog")
    tg.cbq_handler(toggle_wm, lambda c: c.data == f"{CB}:wm")
    tg.cbq_handler(toggle_notify, lambda c: c.data == f"{CB}:notify")
    tg.cbq_handler(toggle_bootstrap, lambda c: c.data == f"{CB}:bootstrap")
    tg.cbq_handler(toggle_lang, lambda c: c.data == f"{CB}:lang")
    tg.cbq_handler(toggle_tone, lambda c: c.data == f"{CB}:tone")
    tg.cbq_handler(toggle_nopromise, lambda c: c.data == f"{CB}:nopromise")
    tg.cbq_handler(toggle_confnotify, lambda c: c.data == f"{CB}:confnotify")
    tg.cbq_handler(notify_test, lambda c: c.data == f"{CB}:notify_test")
    tg.cbq_handler(clear_history, lambda c: c.data == f"{CB}:clear_history")
    tg.cbq_handler(list_chats, lambda c: c.data == f"{CB}:chats")
    tg.cbq_handler(show_rules, lambda c: c.data == f"{CB}:rules")
    tg.cbq_handler(open_updates, lambda c: c.data in (f"{CB}:update", f"{CB}:updcfg"))
    tg.cbq_handler(update_cb, lambda c: c.data.startswith(f"{CB}:upd:"))
    tg.cbq_handler(ask(ST_URL, "Введите base URL API (например <code>https://openrouter.ai/api/v1</code>):"), lambda c: c.data == f"{CB}:url")
    tg.cbq_handler(ask(ST_KEY, "Введите API key (можно <code>env:OPENROUTER_API_KEY</code>):"), lambda c: c.data == f"{CB}:key")
    tg.cbq_handler(ask(ST_MODEL, "Введите ID модели (например <code>openai/gpt-4o-mini</code>):"), lambda c: c.data == f"{CB}:model")
    tg.cbq_handler(ask(ST_PROMPT, "Пришлите новый главный промпт:"), lambda c: c.data == f"{CB}:prompt")
    tg.cbq_handler(ask(ST_SELLER, "Пришлите данные о продавце:"), lambda c: c.data == f"{CB}:seller")
    tg.cbq_handler(ask(ST_TIMEOUT, "AI timeout 30–600 секунд:"), lambda c: c.data == f"{CB}:timeout")
    tg.cbq_handler(ask(ST_BUDGET, "Бюджет истории в символах (2000–40000):"), lambda c: c.data == f"{CB}:budget")
    tg.cbq_handler(ask(ST_WM_TEXT, "Введите текст водяного знака. Отправьте <code>-</code> чтобы очистить:"), lambda c: c.data == f"{CB}:wmtext")
    tg.cbq_handler(ask(ST_NOTIFY_COOLDOWN, "Введите cooldown уведомлений продавцу в минутах (0–60):"), lambda c: c.data == f"{CB}:cooldown")
    tg.cbq_handler(test_api, lambda c: c.data == f"{CB}:test")
    tg.cbq_handler(refresh_lots, lambda c: c.data == f"{CB}:lots")

    tg.msg_handler(make_setter("api_url"), func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_URL))
    tg.msg_handler(make_setter("api_key"), func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_KEY))
    tg.msg_handler(make_setter("api_model"), func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_MODEL))
    tg.msg_handler(make_setter("system_prompt"), func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_PROMPT))
    tg.msg_handler(make_setter("seller_info"), func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_SELLER))
    tg.msg_handler(make_setter("ai_timeout",
                               validate=lambda v: v.isdigit() and 30 <= int(v) <= 600, transform=int),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_TIMEOUT))
    tg.msg_handler(make_setter("history_char_budget",
                               validate=lambda v: v.isdigit() and 2000 <= int(v) <= 40000, transform=int),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_BUDGET))

    def set_wm_text(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw = (m.text or "").strip()
        SETTINGS["watermark_text"] = "" if raw == "-" else raw
        save_config()
        bot.reply_to(m, "✅ Водяной знак обновлён.",
                     reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
    tg.msg_handler(set_wm_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_WM_TEXT))

    tg.msg_handler(make_setter("seller_notify_cooldown",
                               validate=lambda v: v.isdigit() and 0 <= int(v) <= 60, transform=int),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_NOTIFY_COOLDOWN))
    tg.msg_handler(set_update_interval, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_UPD_INT))

    tg.msg_handler(cmd_ai, commands=["ai"])
    cardinal.add_telegram_commands(UUID, [("ai", "KiriillBR AI", True)])


def post_init(c: "Cardinal") -> None:
    if not os.path.exists(CFG_PATH):
        load_config()
    try:
        sync_lots(c, enrich=False)
    except Exception:
        logger.debug("post_init", exc_info=True)


def post_start(c: "Cardinal") -> None:
    threading.Thread(target=lot_worker, args=(c,), daemon=True, name="KBAI-lots").start()
    threading.Thread(target=update_worker, args=(c,), daemon=True, name="KBAI-updates").start()


def on_delete(c: "Cardinal", call: CallbackQuery) -> None:
    STOP.set()
    try:
        POOL.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


BIND_TO_PRE_INIT = [init_telegram]
BIND_TO_POST_INIT = [post_init]
BIND_TO_POST_START = [post_start]
BIND_TO_NEW_MESSAGE = [on_message]
BIND_TO_LAST_CHAT_MESSAGE_CHANGED = [on_last_chat]
BIND_TO_DELETE = on_deletee))}</b> · "
            f"🧊 Тон: <b>{utils.bool_to_text(SETTINGS.get('neutral_on_anger', True))}</b>\n"
            f"🚫 Обещания: <b>{utils.bool_to_text(SETTINGS.get('no_unconfirmed_promises', True))}</b> · "
            f"🔔 Неувер.: <b>{utils.bool_to_text(SETTINGS.get('confidence_notify', True))}</b>\n"
            f"📊 Опрос после заказа: <b>{utils.bool_to_text(SETTINGS.get('post_order_survey', True))}</b>\n"
            f"🛒 Автовыдача оплат: <b>{utils.bool_to_text(SETTINGS.get('auto_fulfill_paid_orders', False))}</b>"
            f" · задержка <b>{SETTINGS.get('auto_fulfill_delay_sec', 3)}с</b>\n"
            f"🎮 Игровые параметры: <b>подтягиваются</b>\n"
            f"⚡ Автовыдача: <b>определяется по FunPay + тексту лота</b>\n"
            f"🖼 Фото: <b>отправляются в AI (нужна vision-модель)</b>\n"
            f"🌐 API: <code>{utils.escape(str(SETTINGS.get('api_url') or '—'))}</code>\n"
            f"🧠 Модель: <code>{utils.escape(str(SETTINGS.get('api_model') or 'не выбрана'))}</code>\n"
            f"🔑 Ключ: <b>{'задан' if SETTINGS.get('api_key') else 'не задан'}</b>\n"
            f"🛍 Лотов: <b>{len(LOTS)}</b> · 👀 Смотрят: <b>{n_view}</b>\n"
            f"💬 Память: <b>{n_chats}</b> чатов / <b>{n_msgs}</b> сообщений\n"
            f"⏱ Timeout: <b>{SETTINGS['ai_timeout']}с</b>\n"
            f"🔄 Обновления: <b>{utils.escape(update_status_line())}</b>"
        )

    def main_kb() -> K:
        kb = K(row_width=2)
        kb.row(B(f"Автоответ {utils.bool_to_text(SETTINGS['enabled'])}", callback_data=f"{CB}:tog"),
               B(f"🔔 Уведомл. {utils.bool_to_text(SETTINGS.get('seller_notify', True))}", callback_data=f"{CB}:notify"))
        kb.row(B(f"💧 Знак {utils.bool_to_text(SETTINGS.get('watermark', True))}", callback_data=f"{CB}:wm"),
               B("✏️ Текст знака", callback_data=f"{CB}:wmtext"))
        kb.row(B("⏱ Cooldown уведомл.", callback_data=f"{CB}:cooldown"), B("🧪 Уведомить сейчас", callback_data=f"{CB}:notify_test"))
        kb.row(B("🌐 API URL", callback_data=f"{CB}:url"), B("🔑 API key", callback_data=f"{CB}:key"))
        kb.row(B("🧠 Модель", callback_data=f"{CB}:model"), B("📝 Промпт", callback_data=f"{CB}:prompt"))
        kb.row(B("🏪 Продавец", callback_data=f"{CB}:seller"), B("⏱ Timeout", callback_data=f"{CB}:timeout"))
        kb.row(B("📏 Бюджет истории", callback_data=f"{CB}:budget"), B("📋 Логи чатов", callback_data=f"{CB}:chats"))
        kb.row(B("🔄 Обновить лоты", callback_data=f"{CB}:lots"), B("📜 Bootstrap ист.", callback_data=f"{CB}:bootstrap"))
        kb.row(B("📋 Правила FunPay", callback_data=f"{CB}:rules"), B("🧪 Тест API", callback_data=f"{CB}:test"))
        kb.row(B(f"🌍 Язык {utils.bool_to_text(SETTINGS.get('match_language', True))}", callback_data=f"{CB}:lang"),
               B(f"🧊 Тон {utils.bool_to_text(SETTINGS.get('neutral_on_anger', True))}", callback_data=f"{CB}:tone"))
        kb.row(B(f"🚫 Без обещаний {utils.bool_to_text(SETTINGS.get('no_unconfirmed_promises', True))}", callback_data=f"{CB}:nopromise"),
               B(f"🔔 Неувер. {utils.bool_to_text(SETTINGS.get('confidence_notify', True))}", callback_data=f"{CB}:confnotify"))
        kb.row(
            B(f"📊 Опрос после заказа {utils.bool_to_text(SETTINGS.get('post_order_survey', True))}", callback_data=f"{CB}:survey"),
            B("✏️ Текст опроса", callback_data=f"{CB}:surveytext"),
        )
        kb.row(
            B(f"🛒 Автовыдача оплат {utils.bool_to_text(SETTINGS.get('auto_fulfill_paid_orders', False))}", callback_data=f"{CB}:autofulfill"),
            B(f"🔔 Уведомл. о заказе {utils.bool_to_text(SETTINGS.get('auto_fulfill_notify_seller', True))}", callback_data=f"{CB}:autofulfillnotify"),
        )
        kb.add(B(f"⏱ Задержка выдачи: {SETTINGS.get('auto_fulfill_delay_sec', 3)}с", callback_data=f"{CB}:autofulfilldelay"))
        kb.row(B(f"🔄 Обновления: {update_status_line()[:24]}", callback_data=f"{CB}:update"),
               B("⚙️ Автообновл.", callback_data=f"{CB}:updcfg"))
        kb.add(B("🗑 Сбросить всю память", callback_data=f"{CB}:clear_history"))
        kb.add(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        return kb

    def show(call: CallbackQuery) -> None:
        try:
            bot.edit_message_text(main_text(), call.message.chat.id, call.message.id, reply_markup=main_kb())
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("show failed", exc_info=True)

    def toggle(call: CallbackQuery) -> None:
        SETTINGS["enabled"] = not SETTINGS["enabled"]; save_config(); show(call)

    def toggle_wm(call: CallbackQuery) -> None:
        SETTINGS["watermark"] = not bool(SETTINGS.get("watermark", True)); save_config(); show(call)

    def toggle_notify(call: CallbackQuery) -> None:
        SETTINGS["seller_notify"] = not bool(SETTINGS.get("seller_notify", True)); save_config(); show(call)

    def toggle_bootstrap(call: CallbackQuery) -> None:
        SETTINGS["bootstrap_history"] = not bool(SETTINGS.get("bootstrap_history", True)); save_config(); show(call)

    def toggle_lang(call: CallbackQuery) -> None:
        SETTINGS["match_language"] = not bool(SETTINGS.get("match_language", True)); save_config(); show(call)

    def toggle_tone(call: CallbackQuery) -> None:
        SETTINGS["neutral_on_anger"] = not bool(SETTINGS.get("neutral_on_anger", True)); save_config(); show(call)

    def toggle_nopromise(call: CallbackQuery) -> None:
        SETTINGS["no_unconfirmed_promises"] = not bool(SETTINGS.get("no_unconfirmed_promises", True)); save_config(); show(call)

    def toggle_confnotify(call: CallbackQuery) -> None:
        SETTINGS["confidence_notify"] = not bool(SETTINGS.get("confidence_notify", True)); save_config(); show(call)

    def toggle_survey(call: CallbackQuery) -> None:
        SETTINGS["post_order_survey"] = not bool(SETTINGS.get("post_order_survey", True)); save_config(); show(call)

    def toggle_autofulfill(call: CallbackQuery) -> None:
        SETTINGS["auto_fulfill_paid_orders"] = not bool(SETTINGS.get("auto_fulfill_paid_orders", False))
        save_config(); show(call)

    def toggle_autofulfill_notify(call: CallbackQuery) -> None:
        SETTINGS["auto_fulfill_notify_seller"] = not bool(SETTINGS.get("auto_fulfill_notify_seller", True))
        save_config(); show(call)

    def ask_autofulfill_delay(call: CallbackQuery) -> None:
        msg = bot.send_message(
            call.message.chat.id,
            "Введите задержку перед отправкой платёжного сообщения в секундах (0–60).",
            reply_markup=CLEAR_STATE_BTN(),
        )
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_AF_DELAY)
        bot.answer_callback_query(call.id)

    def set_autofulfill_delay(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        try:
            v = int((m.text or "").strip())
            if not 0 <= v <= 60:
                raise ValueError
        except Exception:
            bot.reply_to(m, "❌ Введите число 0–60."); return
        SETTINGS["auto_fulfill_delay_sec"] = v
        save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
    tg.msg_handler(set_autofulfill_delay, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_AF_DELAY))

    def clear_history(call: CallbackQuery) -> None:
        with LOCK:
            HISTORY.clear(); CHAT_HISTORY_BOOTSTRAPPED.clear(); VIEWING_CACHE.clear()
            CHAT_LOT.clear(); CHAT_LOT_AT.clear(); SELLER_NOTIFY_AT.clear()
        bot.answer_callback_query(call.id, "✅ Память диалогов сброшена")
        show(call)

    def list_chats(call: CallbackQuery) -> None:
        with LOCK:
            items = list(HISTORY.items())
        if not items:
            text = "💬 Диалогов в памяти нет."
        else:
            lines = ["💬 <b>Активные диалоги в памяти</b>", ""]
            for cid, hist in items[:30]:
                n_a = sum(1 for x in hist if x.get("role") == "assistant")
                n_u = sum(1 for x in hist if x.get("role") == "user")
                lines.append(f"<code>{utils.escape(str(cid))}</code> — всего {len(hist)} · 👤 {n_u} · 🤖/🏪 {n_a}")
            if len(items) > 30:
                lines.append(f"… и ещё {len(items) - 30}")
            text = "\n".join(lines)
        kb = K().add(B("◀️ Назад", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("list_chats failed", exc_info=True)

    def show_rules(call: CallbackQuery) -> None:
        text = (
            "📋 <b>Снимок правил FunPay в промпте</b>\n"
            "Источник: <a href='https://funpay.com/trade/info'>funpay.com/trade/info</a>\n\n"
            f"<pre>{utils.escape(FUNPAY_RULES_SNAPSHOT[:3500])}</pre>"
        )
        kb = K().add(B("◀️ Назад", callback_data=f"{CB}:main"))
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("show_rules failed", exc_info=True)

    def ask(state: str, prompt: str):
        def cb(call: CallbackQuery) -> None:
            msg = bot.send_message(call.message.chat.id, prompt, reply_markup=CLEAR_STATE_BTN())
            tg.set_state(call.message.chat.id, msg.id, call.from_user.id, state)
            bot.answer_callback_query(call.id)
        return cb

    def make_setter(field: str, validate=None, transform=None):
        def setter(m: Message) -> None:
            tg.clear_state(m.chat.id, m.from_user.id, True)
            v = (m.text or "").strip()
            if validate and not validate(v):
                bot.reply_to(m, "❌ Некорректное значение."); return
            SETTINGS[field] = transform(v) if transform else v
            save_config()
            bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
        return setter

    def test_api(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Проверяю…")
        try:
            base = str(SETTINGS.get("api_url") or "").rstrip("/")
            key = str(SETTINGS.get("api_key") or "")
            if key.lower().startswith("env:"):
                key = os.environ.get(key[4:].strip(), "")
            model = str(SETTINGS.get("api_model") or "")
            if not base or not key or not model:
                bot.send_message(call.message.chat.id, "❌ Заполните URL, ключ и модель."); return
            r = requests.post(base + "/chat/completions",
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"model": model,
                                    "messages": [{"role": "user", "content": "Ответь одним словом OK"}],
                                    "max_tokens": 16, "temperature": 0},
                              timeout=(10, 30))
            r.raise_for_status()
            data = r.json()
            ans = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            bot.send_message(call.message.chat.id, f"✅ Ответ API: <code>{utils.escape(ans[:120])}</code>")
        except Exception as e:
            bot.send_message(call.message.chat.id,
                             f"❌ Ошибка:\n<code>{utils.escape(f'{type(e).__name__}: {e}'[:500])}</code>")

    def notify_test(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Отправляю…")
        def job():
            try:
                body = ("🆘 <b>Покупатель вызывает продавца</b>\n\n"
                        "👤 Чат: <b>KiriillBR AI</b>\n"
                        "💬 Сообщение: <code>тестовое уведомление</code>\n\n"
                        "🧠 Причина AI: <i>Проверка канала уведомлений</i>")
                cardinal.telegram.send_notification(body)
            except Exception as e:
                logger.warning("test notify failed: %s", e)
        threading.Thread(target=job, daemon=True, name="KBAI-notify-test").start()

    def refresh_lots(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Запущено…")
        msg = bot.send_message(call.message.chat.id, "🔄 Синхронизирую лоты…")
        def job():
            cnt = sync_lots(cardinal, enrich=False)
            try:
                bot.edit_message_text(f"✅ Синхронизировано: {cnt}.", msg.chat.id, msg.id,
                                      reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
            except Exception:
                pass
        POOL.submit(job)

    def updates_text() -> str:
        with LOCK:
            manifest = UPDATE_STATE.get("manifest")
            status = str(UPDATE_STATE.get("status") or "not_checked")
            err = str(UPDATE_STATE.get("error") or "")
            checked = float(UPDATE_STATE.get("checked_at", 0.0) or 0.0)
        url = _manifest_url()
        lines = [
            "🔄 <b>Обновления KiriillBR AI</b>", "",
            f"Текущая версия: <code>{utils.escape(VERSION)}</code>",
            f"Статус: <b>{utils.escape(update_status_line())}</b>",
            f"Автопроверка: <b>{utils.bool_to_text(SETTINGS.get('update_checks_enabled', True))}</b>",
            f"Автоустановка: <b>{utils.bool_to_text(SETTINGS.get('auto_update', False))}</b>",
            f"Автоперезапуск: <b>{utils.bool_to_text(SETTINGS.get('auto_restart_after_update', False))}</b>",
            f"Интервал: <b>{SETTINGS.get('update_check_interval_minutes', 30)} мин</b>",
            f"Manifest: <code>{utils.escape(url[:80])}</code>",
        ]
        if checked:
            lines.append(f"Последняя проверка: <code>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(checked))}</code>")
        if isinstance(manifest, dict):
            lines.append("")
            lines.append(f"Версия на сервере: <b>v{utils.escape(str(manifest.get('version') or '?'))}</b>")
            if manifest.get("mandatory"):
                lines.append("🚨 <b>Обновление помечено как важное.</b>")
            notes = str(manifest.get("notes") or "").strip()
            if notes:
                lines.append(f"📝 {utils.escape(notes[:1200])}")
        if status == "error" and err:
            lines.extend(["", f"⚠️ <code>{utils.escape(err[:400])}</code>"])
        lines.extend(["", "🛡 Проверяется HTTPS, SHA-256, UUID и синтаксис Python."])
        return "\n".join(lines)

    def updates_kb() -> K:
        kb = K(row_width=2)
        kb.row(
            B(f"🔎 Автопроверка {utils.bool_to_text(SETTINGS.get('update_checks_enabled', True))}", callback_data=f"{CB}:upd:checks"),
            B(f"⚡ Автоустановка {utils.bool_to_text(SETTINGS.get('auto_update', False))}", callback_data=f"{CB}:upd:auto"),
        )
        kb.add(B(f"♻️ Автоперезапуск {utils.bool_to_text(SETTINGS.get('auto_restart_after_update', False))}", callback_data=f"{CB}:upd:autorestart"))
        kb.row(
            B("🔄 Проверить сейчас", callback_data=f"{CB}:upd:check"),
            B(f"⏱ {SETTINGS.get('update_check_interval_minutes', 30)} мин", callback_data=f"{CB}:upd:interval"),
        )
        with LOCK:
            manifest = UPDATE_STATE.get("manifest")
            available = bool(UPDATE_STATE.get("available"))
        if available and isinstance(manifest, dict):
            kb.add(B(f"⬆️ Установить v{manifest.get('version')}", callback_data=f"{CB}:upd:install"))
        pending = str(SETTINGS.get("pending_restart_version") or "")
        if pending and _version_key(pending) > _version_key(VERSION):
            kb.add(B("♻️ Перезапустить Cardinal", callback_data=f"{CB}:upd:restart"))
        kb.add(B("◀️ Назад", callback_data=f"{CB}:main"))
        return kb

    def show_updates(call: CallbackQuery) -> None:
        try:
            bot.edit_message_text(updates_text(), call.message.chat.id, call.message.id,
                                  reply_markup=updates_kb())
            bot.answer_callback_query(call.id)
        except Exception:
            logger.debug("show_updates failed", exc_info=True)

    def toggle_upd_checks(call: CallbackQuery) -> None:
        SETTINGS["update_checks_enabled"] = not bool(SETTINGS.get("update_checks_enabled", True))
        save_config(); show_updates(call)

    def toggle_upd_auto(call: CallbackQuery) -> None:
        SETTINGS["auto_update"] = not bool(SETTINGS.get("auto_update", False))
        save_config(); show_updates(call)

    def toggle_upd_autorestart(call: CallbackQuery) -> None:
        SETTINGS["auto_restart_after_update"] = not bool(SETTINGS.get("auto_restart_after_update", False))
        save_config(); show_updates(call)

    def upd_check_now(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Проверяю…")

        def job():
            try:
                check_updates_cycle(cardinal, notify=True, force=True)
            except Exception:
                logger.debug("upd_check_now failed", exc_info=True)
            try:
                bot.edit_message_text(updates_text(), call.message.chat.id, call.message.id,
                                      reply_markup=updates_kb())
            except Exception:
                pass
        POOL.submit(job)

    def upd_install_now(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Устанавливаю…")

        def job():
            try:
                ok, msg = install_update(cardinal)
                note = "✅ " + msg if ok else "❌ " + msg
            except Exception as e:
                note = f"❌ {type(e).__name__}: {e}"
            try:
                bot.send_message(call.message.chat.id, utils.escape(note))
                bot.edit_message_text(updates_text(), call.message.chat.id, call.message.id,
                                      reply_markup=updates_kb())
            except Exception:
                pass
        POOL.submit(job)

    def upd_restart_now(call: CallbackQuery) -> None:
        bot.answer_callback_query(call.id, "Перезапускаю Cardinal…")
        _restart_cardinal(1.0)

    def ask_upd_interval(call: CallbackQuery) -> None:
        msg = bot.send_message(call.message.chat.id,
                               "Введите интервал автопроверки обновлений в минутах (10–1440).",
                               reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_UPD_INT)
        bot.answer_callback_query(call.id)

    def set_upd_interval(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        try:
            v = int((m.text or "").strip())
            if not 10 <= v <= 1440:
                raise ValueError
        except Exception:
            bot.reply_to(m, "❌ Введите число 10–1440."); return
        SETTINGS["update_check_interval_minutes"] = v
        save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:update")))
    tg.msg_handler(set_upd_interval, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_UPD_INT))

    def ask_wm_text(call: CallbackQuery) -> None:
        msg = bot.send_message(call.message.chat.id,
                               "Введите текст водяного знака (или «-», чтобы отключить).",
                               reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_WM_TEXT)
        bot.answer_callback_query(call.id)

    def set_wm_text(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        v = (m.text or "").strip()
        if v == "-":
            v = ""
        SETTINGS["watermark_text"] = v
        save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
    tg.msg_handler(set_wm_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_WM_TEXT))

    def ask_survey_text(call: CallbackQuery) -> None:
        msg = bot.send_message(call.message.chat.id,
                               "Введите текст опроса после подтверждения заказа.",
                               reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_SURVEY_TEXT)
        bot.answer_callback_query(call.id)

    def set_survey_text(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        SETTINGS["post_order_survey_text"] = (m.text or "").strip()
        save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
    tg.msg_handler(set_survey_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_SURVEY_TEXT))

    def ask_cooldown(call: CallbackQuery) -> None:
        msg = bot.send_message(call.message.chat.id,
                               "Введите cooldown уведомлений продавцу в минутах (0–120).",
                               reply_markup=CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, msg.id, call.from_user.id, ST_NOTIFY_COOLDOWN)
        bot.answer_callback_query(call.id)

    def set_cooldown(m: Message) -> None:
        tg.clear_state(m.chat.id, m.from_user.id, True)
        try:
            v = int((m.text or "").strip())
            if not 0 <= v <= 120:
                raise ValueError
        except Exception:
            bot.reply_to(m, "❌ Введите число 0–120."); return
        SETTINGS["seller_notify_cooldown"] = v
        save_config()
        bot.reply_to(m, "✅ Сохранено.", reply_markup=K().add(B("◀️ Назад", callback_data=f"{CB}:main")))
    tg.msg_handler(set_cooldown, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_NOTIFY_COOLDOWN))

    tg.msg_handler(make_setter("api_url", validate=lambda v: _is_safe_url(v)),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_URL))
    tg.msg_handler(make_setter("api_key"),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_KEY))
    tg.msg_handler(make_setter("api_model"),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_MODEL))
    tg.msg_handler(make_setter("system_prompt"),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_PROMPT))
    tg.msg_handler(make_setter("seller_info"),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_SELLER))
    tg.msg_handler(make_setter("ai_timeout",
                               validate=lambda v: v.isdigit() and 10 <= int(v) <= 600,
                               transform=int),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_TIMEOUT))
    tg.msg_handler(make_setter("history_char_budget",
                               validate=lambda v: v.isdigit() and 2000 <= int(v) <= 200000,
                               transform=int),
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ST_BUDGET))

    tg.cbq_handler(show, lambda c: c.data == f"{CB}:main")
    tg.cbq_handler(toggle, lambda c: c.data == f"{CB}:tog")
    tg.cbq_handler(toggle_wm, lambda c: c.data == f"{CB}:wm")
    tg.cbq_handler(toggle_notify, lambda c: c.data == f"{CB}:notify")
    tg.cbq_handler(toggle_bootstrap, lambda c: c.data == f"{CB}:bootstrap")
    tg.cbq_handler(toggle_lang, lambda c: c.data == f"{CB}:lang")
    tg.cbq_handler(toggle_tone, lambda c: c.data == f"{CB}:tone")
    tg.cbq_handler(toggle_nopromise, lambda c: c.data == f"{CB}:nopromise")
    tg.cbq_handler(toggle_confnotify, lambda c: c.data == f"{CB}:confnotify")
    tg.cbq_handler(toggle_survey, lambda c: c.data == f"{CB}:survey")
    tg.cbq_handler(toggle_autofulfill, lambda c: c.data == f"{CB}:autofulfill")
    tg.cbq_handler(toggle_autofulfill_notify, lambda c: c.data == f"{CB}:autofulfillnotify")
    tg.cbq_handler(ask_autofulfill_delay, lambda c: c.data == f"{CB}:autofulfilldelay")
    tg.cbq_handler(clear_history, lambda c: c.data == f"{CB}:clear_history")
    tg.cbq_handler(list_chats, lambda c: c.data == f"{CB}:chats")
    tg.cbq_handler(show_rules, lambda c: c.data == f"{CB}:rules")
    tg.cbq_handler(test_api, lambda c: c.data == f"{CB}:test")
    tg.cbq_handler(notify_test, lambda c: c.data == f"{CB}:notify_test")
    tg.cbq_handler(refresh_lots, lambda c: c.data == f"{CB}:lots")
    tg.cbq_handler(ask_wm_text, lambda c: c.data == f"{CB}:wmtext")
    tg.cbq_handler(ask_survey_text, lambda c: c.data == f"{CB}:surveytext")
    tg.cbq_handler(ask_cooldown, lambda c: c.data == f"{CB}:cooldown")

    tg.cbq_handler(ask(ST_URL,     "Введите API URL (HTTPS)."),         lambda c: c.data == f"{CB}:url")
    tg.cbq_handler(ask(ST_KEY,     "Введите API key (можно env:VAR)."), lambda c: c.data == f"{CB}:key")
    tg.cbq_handler(ask(ST_MODEL,   "Введите имя модели."),              lambda c: c.data == f"{CB}:model")
    tg.cbq_handler(ask(ST_PROMPT,  "Введите новый системный промпт."),  lambda c: c.data == f"{CB}:prompt")
    tg.cbq_handler(ask(ST_SELLER,  "Опишите информацию о продавце."),   lambda c: c.data == f"{CB}:seller")
    tg.cbq_handler(ask(ST_TIMEOUT, "Введите timeout AI в секундах (10–600)."),
                   lambda c: c.data == f"{CB}:timeout")
    tg.cbq_handler(ask(ST_BUDGET,  "Введите бюджет истории в символах (2000–200000)."),
                   lambda c: c.data == f"{CB}:budget")

    tg.cbq_handler(show_updates,           lambda c: c.data == f"{CB}:update")
    tg.cbq_handler(toggle_upd_checks,      lambda c: c.data == f"{CB}:upd:checks")
    tg.cbq_handler(toggle_upd_auto,        lambda c: c.data == f"{CB}:upd:auto")
    tg.cbq_handler(toggle_upd_autorestart, lambda c: c.data == f"{CB}:upd:autorestart")
    tg.cbq_handler(upd_check_now,          lambda c: c.data == f"{CB}:upd:check")
    tg.cbq_handler(ask_upd_interval,       lambda c: c.data == f"{CB}:upd:interval")
    tg.cbq_handler(upd_install_now,        lambda c: c.data == f"{CB}:upd:install")
    tg.cbq_handler(upd_restart_now,        lambda c: c.data == f"{CB}:upd:restart")
    tg.cbq_handler(show_updates,           lambda c: c.data == f"{CB}:updcfg")


def init(cardinal: "Cardinal") -> None:
    init_telegram(cardinal)
    if not cardinal.telegram:
        return
    threading.Thread(target=lot_worker, args=(cardinal,), daemon=True,
                     name="KBAI-lots").start()
    threading.Thread(target=update_worker, args=(cardinal,), daemon=True,
                     name="KBAI-updates").start()


def stop(cardinal: "Cardinal") -> None:
    STOP.set()
    try:
        POOL.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        POOL.shutdown(wait=False)
    except Exception:
        logger.debug("POOL shutdown failed", exc_info=True)


BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [on_message]
BIND_TO_LAST_CHAT_MESSAGE_CHANGED = [on_last_chat]
BIND_TO_NEW_ORDER = [on_new_paid_order]
BIND_TO_DELETE = stop
