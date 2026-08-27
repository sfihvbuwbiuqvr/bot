#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
 🎬🎵  MusicFinder Bot  —  ربات دانلود ویدیو + شناسایی و دانلود موزیک
=====================================================================
امکانات:
  • دانلود از یوتیوب / اینستاگرام / تیک‌تاک / ساند‌کلود / اسپاتیفای (yt-dlp)
  • منوی انتخاب کیفیت (1080p/720p/360p/فقط صدا) قبل از دانلود
  • پشتیبانی پلی‌لیست و ست‌ها با انتخاب آیتم یا دانلود همه
  • دانلود محتوای فورواردشده از کانال‌ها (+ نسخه فایل تا 20MB)
  • شناسایی آهنگ با ShazamIO + جستجو با متن ترانه (Genius/DuckDuckGo/lrclib) + متن ترانه (lrclib) + پیش‌نمایش ویس + رینگتون
  • درج خودکار تگ ID3 و کاور داخل MP3 (mutagen)
  • جستجوی اینلاین (@BotName نام آهنگ)
  • تاریخچه دانلود (/history) + دوزبانه fa/en (/lang)
  • پنل مدیریت کامل: آمار، پیام همگانی، کانال‌های اجباری، بن/آنبن،
    حالت تعمیر، صف دانلود، شزام خودکار، وضعیت سرور
  • سیستم جوین اجباری + کول‌داون + پاکسازی خودکار فایل‌ها

نیازمندی‌ها:
  Python 3.10+  |  ffmpeg نصب‌شده روی سرور  |  cookies.txt اختیاری (فرمت Netscape)

راه‌اندازی سریع:
  1) pip install -r requirements.txt
  2) فایل .env را مثل .env.example پر کنید (یا متغیرهای محیطی ست کنید)
  3) python bot.py
=====================================================================
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yt_dlp
from shazamio import Shazam

try:
    from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1  # type: ignore
    HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    HAS_MUTAGEN = False
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

# =====================================================================
# ⚙️ تنظیمات (از متغیر محیطی یا فایل .env خوانده می‌شود)
# =====================================================================


def _load_env_file(path: str = ".env") -> None:
    """لودر سبکِ .env بدون نیاز به کتابخانه‌ی اضافه."""
    p = Path(path)
    if not p.exists():
        return
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as exc:  # pragma: no cover
        logging.warning("خطا در خواندن .env : %s", exc)


_load_env_file()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "PUT-YOUR-TOKEN-HERE")

ADMIN_IDS: List[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()
]

# کانال‌های اجباری پیش‌فرض (با اسپیس جدا شوند) — بعداً از داخل پنل هم قابل افزودن/حذف است
DEFAULT_FORCE_CHANNELS: List[str] = [
    c for c in os.getenv("FORCE_CHANNELS", "").split() if c.strip()
]

COOKIES_FILE: Path = Path(os.getenv("COOKIES_FILE", "cookies.txt"))

# کوکی به‌صورت Base64 — برای پلتفرم‌هایی مثل Railway که آپلود فایل ندارند:
# محتوای cookies.txt را base64 کن و در متغیر COOKIES_B64 بگذار؛ خودکار ساخته می‌شود.
_cookies_b64 = os.getenv("COOKIES_B64", "").strip()
if _cookies_b64 and not COOKIES_FILE.exists():
    try:
        COOKIES_FILE.write_bytes(base64.b64decode(_cookies_b64))
        logging.getLogger("musicbot").info("🍪 cookies.txt از متغیر COOKIES_B64 ساخته شد")
    except Exception as _exc:  # noqa: BLE001
        logging.getLogger("musicbot").warning("متغیر COOKIES_B64 نامعتبر بود: %s", _exc)

# نسخه‌ی «بدون VISITOR_INFO1_LIVE» از کوکی — این کوکی به session/IP مرورگر گره خورده و
# روی سرور باعث خطای «page needs to be reloaded» می‌شود؛ رانگ‌های جایگزین نردبان از آن استفاده می‌کنند.
COOKIES_NOVI_FILE: Path = COOKIES_FILE.with_suffix(".novi.txt")
if COOKIES_FILE.exists():
    try:
        _rows = COOKIES_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        _kept = [r for r in _rows if "VISITOR_INFO1_LIVE" not in r]
        if len(_kept) != len(_rows):
            COOKIES_NOVI_FILE.write_text("\n".join(_kept) + "\n", encoding="ascii", errors="ignore")
            logging.getLogger("musicbot").info(
                "🍪 نسخه‌ی بدون VISITOR_INFO1_LIVE آماده شد (%d→%d ردیف)", len(_rows), len(_kept))
        else:
            COOKIES_NOVI_FILE = COOKIES_FILE  # چیزی برای حذف نبود
    except Exception as _exc:  # noqa: BLE001
        logging.getLogger("musicbot").warning("ساخت cookies.novi.txt ناموفق: %s", _exc)
        COOKIES_NOVI_FILE = COOKIES_FILE

DOWNLOAD_DIR: Path = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
DB_PATH: Path = Path(os.getenv("DB_PATH", "bot.db"))

MAX_FILE_MB: int = int(os.getenv("MAX_FILE_MB", "48"))          # سقف ارسال به تلگرام (~50MB API)
AUDIO_BITRATE: str = os.getenv("AUDIO_BITRATE", "192")           # کیفیت mp3 خروجی
CLEAN_AFTER_MIN: int = int(os.getenv("CLEAN_AFTER_MIN", "45"))   # عمر فایل‌ها قبل از پاکسازی
JOIN_CACHE_SEC: int = int(os.getenv("JOIN_CACHE_SEC", "600"))    # کش نتیجه‌ی عضویت
COOLDOWN_SEC: int = int(os.getenv("COOLDOWN_SEC", "12"))         # فاصله‌ی بین درخواست هر کاربر
SHAZAM_SNIPPET_SEC: int = int(os.getenv("SHAZAM_SNIPPET_SEC", "95"))  # چند ثانیه صدا برای شزام

LOG_CHANNEL: str = os.getenv("LOG_CHANNEL", "").strip()          # کانال لاگ خطاها (اختیاری)
DEFAULT_LANG: str = os.getenv("DEFAULT_LANG", "fa").lower()      # زبان پیش‌فرض: fa | en
MAX_CONCURRENT_DL: int = int(os.getenv("MAX_CONCURRENT_DL", "2"))  # ظرفیت صف دانلود
PLIST_MAX_ITEMS: int = int(os.getenv("PLIST_MAX_ITEMS", "25"))   # حداکثر آیتم پلی‌لیست

UPLOAD_TIMEOUT: int = 900   # تایم‌اوت آپلود فایل حجیم به تلگرام
MB: int = 1024 * 1024
PROCESS_START: float = time.time()

# =====================================================================
# 🔤 تشخیص پلتفرم
# =====================================================================

PLATFORM_PATTERNS: List[Tuple[str, Any]] = [
    ("youtube",   re.compile(r"(youtube\.com|youtu\.be|youtube-nocookie\.com|music\.youtube)", re.I)),
    ("instagram", re.compile(r"instagram\.com", re.I)),
    ("tiktok",    re.compile(r"(tiktok\.com|vm\.tiktok|vt\.tiktok)", re.I)),
    ("spotify",   re.compile(r"open\.spotify\.com/track/", re.I)),
    ("soundcloud", re.compile(r"(soundcloud\.com|snd\.sc)", re.I)),
]
PLATFORM_FA: Dict[str, str] = {
    "youtube": "یوتیوب ▶️",
    "instagram": "اینستاگرام 📸",
    "tiktok": "تیک‌تاک 🎵",
    "spotify": "اسپاتیفای 🟢",
    "soundcloud": "ساند‌کلود ☁️",
    "other": "وب 🌐",
}
PLATFORM_EMOJI: Dict[str, str] = {
    "youtube": "▶️", "instagram": "📸", "tiktok": "🎵", "spotify": "🟢",
    "soundcloud": "☁️", "other": "🌐",
}

URL_RE = re.compile(r"https?://\S+", re.I)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTS = {".mp3", ".m4a", ".opus", ".ogg", ".wav"}

esc = html.escape

# =====================================================================
# 🌐 دوزبانه (fa / en) — متن‌های رو به کاربر
# =====================================================================

STRINGS: Dict[str, Dict[str, str]] = {
    "welcome": {
        "fa": "سلام <b>{name}</b> عزیز 👋\nبه ربات <b>دانلود ویدیو و شناسایی موزیک</b> خوش اومدی 🎶\n\n🎬 لینک از <b>یوتیوب / اینستاگرام / تیک‌تاک / ساند‌کلود</b> یا حتی <b>اسپاتیفای</b> بفرست.\n🎧 بعد از ارسال می‌تونی آهنگش رو شناسایی کنی یا MP3 کاملش رو بگیری!\n\n👇 یکی از گزینه‌های زیر رو انتخاب کن یا مستقیم لینکت رو بفرست:",
        "en": "Hi <b>{name}</b> 👋\nWelcome to the <b>Video Downloader & Music Finder</b> bot 🎶\n\n🎬 Send a link from <b>YouTube / Instagram / TikTok / SoundCloud</b> or even <b>Spotify</b>.\n🎧 After that you can identify its song or get the full MP3!\n\n👇 Pick an option below or just send your link:",
    },
    "hint": {
        "fa": "🤖 <b>راهنما:</b>\n\n1️⃣ لینک از یوتیوب، اینستاگرام، تیک‌تاک، ساند‌کلود یا اسپاتیفای کپی کن.\n2️⃣ همین‌جا بفرستش.\n3️⃣ کیفیت رو انتخاب کن و صبر کن 📥\n4️⃣ زیر فایل این دکمه‌ها هست:\n     • 🎵 شناسایی آهنگ (Shazam)\n     • 🎧 دانلود نسخه موزیک\n     • 📝 متن ترانه • ⏱ پیش‌نمایش • 🔔 رینگتون\n\n📨 پست کانال‌ها رو هم می‌تونی فوروارد بدی تا برات ذخیره‌اش کنم!\n⚠️ سقف حجم هر فایل: حدود {max} مگابایت",
        "en": "🤖 <b>Guide:</b>\n\n1️⃣ Copy a link from YouTube, Instagram, TikTok, SoundCloud or Spotify.\n2️⃣ Send it here.\n3️⃣ Choose quality and wait 📥\n4️⃣ Under every file you'll see:\n     • 🎵 Identify song (Shazam)\n     • 🎧 Download music version\n     • 📝 Lyrics • ⏱ Preview • 🔔 Ringtone\n\n📨 You can also forward channel posts and I'll save them for you!\n⚠️ Max file size: ~{max} MB",
    },
    "join": {
        "fa": "⛔️ برای استفاده از ربات ابتدا باید در کانال‌های زیر عضو بشی:\n\nبعد از عضویت روی «✅ بررسی عضویت» بزن.",
        "en": "⛔️ To use this bot you must join the following channel(s) first:\n\nAfter joining tap «✅ Check membership».",
    },
    "banned": {
        "fa": "🚫 شما از استفاده‌ی این ربات محروم شده‌اید!",
        "en": "🚫 You are banned from using this bot!",
    },
    "maint": {
        "fa": "🛠 ربات در حال <b>تعمیر</b> است! چند لحظه دیگر سر بزن 💙",
        "en": "🛠 The bot is under <b>maintenance</b>! Please come back in a few minutes 💙",
    },
    "cooldown": {
        "fa": "⏳ کمی آرام‌تر! {sec} ثانیه دیگر دوباره امتحان کن.",
        "en": "⏳ Easy there! Try again in {sec} seconds.",
    },
    "processing": {
        "fa": "{emoji} <b>در حال پردازش لینک…</b>",
        "en": "{emoji} <b>Processing link…</b>",
    },
    "queued": {
        "fa": "🕒 شما در صف دانلود هستید… نوبت: <b>{pos}</b>\nچند لحظه صبر کن ⏳",
        "en": "🕒 You are in the download queue… position: <b>{pos}</b>\nPlease wait ⏳",
    },
    "quality_prompt": {
        "fa": "{emoji} <b>{title}</b>\n\n🎯 چه کیفیتی می‌خوای؟",
        "en": "{emoji} <b>{title}</b>\n\n🎯 Which quality do you want?",
    },
    "plist_prompt": {
        "fa": "📃 این یک پلی‌لیست/ست با <b>{count}</b> آیتم است.\nکدوم رو دانلود کنم؟",
        "en": "📃 This is a playlist/set with <b>{count}</b> items.\nWhich one should I download?",
    },
    "searching_song": {
        "fa": "🎧 در حال استخراج صدا و شناسایی آهنگ با <b>Shazam</b>…\nچند لحظه صبر کن ⏳",
        "en": "🎧 Extracting audio & identifying the song with <b>Shazam</b>…\nOne moment ⏳",
    },
    "notfound": {
        "fa": "😔 متأسفانه نتونستم آهنگ این ویدیو رو شناسایی کنم!\n\n💡 معمولاً ویدیوهایی که صدای واضح و کم‌حرف دارن، نتیجه‌ی بهتری می‌دن.",
        "en": "😔 Sorry, I couldn't identify the song of this video!\n\n💡 Videos with clear music usually give better results.",
    },
    "mus_search": {
        "fa": "🔎 در حال جستجو و دانلود موزیک… ⏳",
        "en": "🔎 Searching & downloading the track… ⏳",
    },
    "err_generic": {
        "fa": "⚠️ خطایی رخ داد! لطفاً چند لحظه بعد دوباره تلاش کن.",
        "en": "⚠️ Something went wrong! Please try again in a moment.",
    },
    "hist_header": {
        "fa": "🕘 <b>آخرین دانلودهای تو:</b>\n\nبرای دریافت مجدد روی دکمه بزن:",
        "en": "🕘 <b>Your recent downloads:</b>\n\nTap a button to fetch again:",
    },
    "hist_empty": {
        "fa": "📭 هنوز چیزی دانلود نکردی!",
        "en": "📭 You haven't downloaded anything yet!",
    },
    "lang_set": {
        "fa": "✅ زبان به فارسی تغییر کرد.",
        "en": "✅ Language switched to English.",
    },
    "fwd_copied": {
        "fa": "📤 کپی شد! بدون هدر فوروارد می‌تونی ذخیره‌اش کنی.",
        "en": "📤 Copied! Save it without the forward header.",
    },
    "fwd_too_big": {
        "fa": "📦 این فایل بزرگ‌تر از ۲۰MB است و نمی‌تونم نسخه‌ی «فایل» بفرستم؛ ولی کپی بالا قابل ذخیره است.",
        "en": "📦 This file is larger than 20MB so I can't send it as a file; but the copy above is savable.",
    },
    "file_sending": {
        "fa": "📁 در حال آماده‌سازی نسخه فایل…",
        "en": "📁 Preparing file version…",
    },
    "lyrics_none": {
        "fa": "😔 برای این آهنگ متنی پیدا نکردم.",
        "en": "😔 Couldn't find lyrics for this track.",
    },
    "prev_making": {
        "fa": "⏱ در حال ساخت پیش‌نمایش ۳۰ ثانیه‌ای…",
        "en": "⏱ Making a 30s preview…",
    },
    "ring_making": {
        "fa": "🔔 در حال ساخت رینگتون…",
        "en": "🔔 Making a ringtone…",
    },
    "spot_processing": {
        "fa": "🟢 در حال پیدا کردن این ترک اسپاتیفای…",
        "en": "🟢 Looking up this Spotify track…",
    },
}

BTN: Dict[str, Dict[str, str]] = {
    "song_id": {"fa": "🎵 شناسایی آهنگ این ویدیو", "en": "🎵 Identify this song"},
    "dl_music": {"fa": "🎧 دانلود نسخهٔ موزیک", "en": "🎧 Get the music"},
    "dl_this": {"fa": "🎧 دانلود این موزیک", "en": "🎧 Download this track"},
    "dl_sc": {"fa": "☁️ دانلود از SoundCloud", "en": "☁️ Get from SoundCloud"},
    "sc_none": {"fa": "☁️ در SoundCloud پیدا نشد.", "en": "☁️ Not found on SoundCloud."},
    "search_ask": {"fa": "🔍 از کدام پلتفرم جستجو کنم؟", "en": "🔍 Search which platform?"},
    "search_btn_sc": {"fa": "☁️ SoundCloud", "en": "☁️ SoundCloud"},
    "search_btn_yt": {"fa": "▶️ YouTube", "en": "▶️ YouTube"},
    "search_none": {"fa": "🔍 چیزی پیدا نشد.", "en": "🔍 No results."},
    "search_empty": {"fa": "🔍 یک نام خواننده یا آهنگ بفرست.", "en": "🔍 Send an artist or song name."},
    "listen": {"fa": "🔗 گوش دادن آنلاین", "en": "🔗 Listen online"},
    "lyrics": {"fa": "📝 متن ترانه", "en": "📝 Lyrics"},
    "preview": {"fa": "⏱ پیش‌نمایش", "en": "⏱ Preview"},
    "ringtone": {"fa": "🔔 رینگتون", "en": "🔔 Ringtone"},
    "back": {"fa": "🔙 بازگشت", "en": "🔙 Back"},
    "check_join": {"fa": "✅ عضو شدم، بررسی کن", "en": "✅ I joined, check now"},
    "as_file": {"fa": "📁 ارسال به‌صورت فایل", "en": "📁 Send as file"},
    "lang": {"fa": "🌐 Language", "en": "🌐 زبان"},
}


def L(uid: int, key: str, **kwargs) -> str:
    """متن دوزبانه برای کاربر."""
    lang = get_lang(uid)
    tpl = STRINGS.get(key, {}).get(lang) or STRINGS.get(key, {}).get("fa") or key
    if kwargs:
        try:
            return tpl.format(**kwargs)
        except Exception:
            return tpl
    return tpl


def B(uid: int, key: str) -> str:
    """برچسب دکمه‌ی دوزبانه."""
    return BTN.get(key, {}).get(get_lang(uid)) or BTN.get(key, {}).get("fa", key)

# =====================================================================
# 🪵 لاگ
# =====================================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("musicbot")


def log_exc(err: BaseException, where: str) -> None:
    log.error("[%s] %s\n%s", where, err, "".join(traceback.format_exception_only(type(err), err)).rstrip())


# =====================================================================
# 💾 دیتابیس SQLite
# =====================================================================

_db_lock = threading.Lock()
_db: Optional[sqlite3.Connection] = None


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        _db = conn
    return _db


def db_init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock:
        c = db()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                joined_at  TEXT,
                last_seen  TEXT,
                banned     INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS stats (
                key   TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        # --- مهاجرت‌های سبک (اگر ستون/جدول قبلاً هست، خطا نادیده گرفته می‌شود) ---
        try:
            c.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'fa';")
        except sqlite3.OperationalError:
            pass
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER,
                platform TEXT,
                kind     TEXT,
                title    TEXT,
                url      TEXT,
                ts       TEXT
            )
            """
        )
        c.commit()


def db_exec(sql: str, params: Tuple = ()) -> None:
    with _db_lock:
        db().execute(sql, params)
        db().commit()


def db_one(sql: str, params: Tuple = ()) -> Optional[Tuple]:
    with _db_lock:
        cur = db().execute(sql, params)
        return cur.fetchone()


def db_all(sql: str, params: Tuple = ()) -> List[Tuple]:
    with _db_lock:
        cur = db().execute(sql, params)
        return cur.fetchall()


def upsert_user(user) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    db_exec(
        """
        INSERT INTO users (user_id, username, first_name, joined_at, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_seen = excluded.last_seen
        """,
        (user.id, user.username or "", user.first_name or "", now, now),
    )


def set_banned(uid: int, banned: bool) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    db_exec(
        """
        INSERT INTO users (user_id, joined_at, last_seen, banned) VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET banned = excluded.banned
        """,
        (uid, now, now, 1 if banned else 0),
    )


def is_banned_uid(uid: int) -> bool:
    row = db_one("SELECT banned FROM users WHERE user_id = ?", (uid,))
    return bool(row and row[0])


def all_active_ids() -> List[int]:
    return [r[0] for r in db_all("SELECT user_id FROM users WHERE banned = 0")]


def bump_stat(key: str, delta: int = 1) -> None:
    db_exec(
        """
        INSERT INTO stats (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = value + excluded.value
        """,
        (key, delta),
    )


def stat_value(key: str) -> int:
    row = db_one("SELECT value FROM stats WHERE key = ?", (key,))
    return int(row[0]) if row else 0


def settings_get(key: str) -> Optional[str]:
    row = db_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row[0] if row else None


def settings_set(key: str, value: str) -> None:
    db_exec(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_force_channels() -> List[str]:
    chans: List[str] = list(DEFAULT_FORCE_CHANNELS)
    raw = settings_get("force_channels")
    if raw:
        try:
            for ch in json.loads(raw):
                if ch and ch not in chans:
                    chans.append(ch)
        except Exception:
            pass
    return chans


def add_force_channel(ref: str) -> bool:
    chans = get_force_channels()
    if ref in chans:
        return False
    chans.append(ref)
    extra = [c for c in chans if c not in DEFAULT_FORCE_CHANNELS]
    settings_set("force_channels", json.dumps(extra, ensure_ascii=False))
    return True


def remove_force_channel(ref: str) -> bool:
    chans = get_force_channels()
    if ref not in chans:
        return False
    chans.remove(ref)
    extra = [c for c in chans if c not in DEFAULT_FORCE_CHANNELS]
    settings_set("force_channels", json.dumps(extra, ensure_ascii=False))
    return True


# --- سوییچ‌های پنل (تعمیر / صف / شزام خودکار) ---

def setting_on(key: str) -> bool:
    return settings_get(key) == "1"


def toggle_setting(key: str) -> bool:
    new_val = "0" if setting_on(key) else "1"
    settings_set(key, new_val)
    return new_val == "1"


def maintenance_on() -> bool:
    return setting_on("maintenance")


def queue_on() -> bool:
    return setting_on("queue_on")


def auto_shazam_on() -> bool:
    return setting_on("auto_shazam")


# --- تاریخچه‌ی دانلود ---

def add_history(uid: int, platform: str, kind: str, title: str, url: str) -> None:
    try:
        db_exec(
            "INSERT INTO history (user_id, platform, kind, title, url, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, platform, kind, title[:200], url[:500], datetime.now().isoformat(timespec="seconds")),
        )
    except Exception as exc:
        log.warning("add_history failed: %s", exc)


def get_history(uid: int, limit: int = 8) -> List[Tuple]:
    return db_all(
        "SELECT id, platform, kind, title, url FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (uid, limit),
    )


# --- زبان کاربر ---

_LANG_CACHE: Dict[int, str] = {}


def get_lang(uid: int) -> str:
    if uid in _LANG_CACHE:
        return _LANG_CACHE[uid]
    try:
        row = db_one("SELECT lang FROM users WHERE user_id = ?", (uid,))
        lang = (row[0] if row and row[0] else DEFAULT_LANG).lower()
    except Exception:
        lang = DEFAULT_LANG
    if lang not in ("fa", "en"):
        lang = "fa"
    _LANG_CACHE[uid] = lang
    return lang


def set_lang(uid: int, lang: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    db_exec(
        """
        INSERT INTO users (user_id, joined_at, last_seen, lang) VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET lang = excluded.lang
        """,
        (uid, now, now, lang),
    )
    _LANG_CACHE[uid] = lang


# =====================================================================
# 🧰 ابزارهای کوچک
# =====================================================================


def fmt_size(num_bytes: float) -> str:
    try:
        num_bytes = float(num_bytes)
    except Exception:
        num_bytes = 0.0
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{int(num_bytes)} B"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def fmt_dur(seconds: Optional[float]) -> str:
    try:
        s = int(seconds or 0)
    except Exception:
        s = 0
    if s <= 0:
        return "-"
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def make_bar(pct: float, width: int = 16) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100 * width)
    return "▰" * filled + "▱" * (width - filled)


def detect_platform(url: str) -> str:
    for key, pattern in PLATFORM_PATTERNS:
        if pattern.search(url):
            return key
    return "other"


NOISE_BRACKETS = re.compile(r"[([{][^)\]}]*[)\]}]")
NOISE_WORDS = re.compile(
    r"\b(official\s+(music\s+)?(video|audio)|lyrics?\s*(video)?|mv|visualizer|"
    r"hd|4k|teaser|trailer|full\s+video|m\/v)\b",
    re.I,
)


def clean_title(title: str) -> str:
    t = NOISE_BRACKETS.sub(" ", title or "")
    t = NOISE_WORDS.sub(" ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—|·")
    return t[:80]


def reg_token_add(**kwargs) -> str:
    """ثبت یک توکن جدید در رجیستری درون‌حافظه‌ای (برای callback_data های کوتاه)."""
    tok = secrets.token_hex(4)
    while tok in REGISTRY:
        tok = secrets.token_hex(4)
    kwargs["exp"] = time.time() + REG_TTL
    REGISTRY[tok] = kwargs
    REG_ORDER.append(tok)
    while len(REG_ORDER) > REG_MAX:
        old = REG_ORDER.pop(0)
        REGISTRY.pop(old, None)
    return tok


REGISTRY: Dict[str, Dict[str, Any]] = {}
REG_ORDER: List[str] = []
REG_TTL: int = 45 * 60     # اعتبار دکمه‌ها: ۴۵ دقیقه
REG_MAX: int = 400

JOIN_OK: Dict[int, float] = {}          # user_id -> تا چه زمانی عضویت معتبر فرض شود
CHAT_LINKS: Dict[str, Tuple[float, str]] = {}
LAST_REQ: Dict[int, float] = {}
BCAST_RUNNING: bool = False


def cooldown_left(uid: int) -> int:
    """اگر کاربر زوده، ثانیه‌ی باقی‌مانده؛ وگرنه درخواست ثبت و صفر برمی‌گردد."""
    if uid in ADMIN_IDS:
        return 0
    now = time.time()
    left = int(COOLDOWN_SEC - (now - LAST_REQ.get(uid, 0)))
    if left > 0:
        return left
    LAST_REQ[uid] = now
    return 0


async def safe_delete(msg: Optional[Message]) -> None:
    if msg is None:
        return
    try:
        await msg.delete()
    except TelegramError:
        pass


async def run_bg(coro) -> None:
    try:
        await coro
    except Exception as exc:
        log_exc(exc, "background-task")


# تسک‌های پس‌زمینه‌ی زنده — مرجع قوی تا GC وسط کار آن‌ها را جمع نکند
_BG_TASKS: set = set()


def _spawn(coro) -> asyncio.Task:
    """تسک پس‌زمینه با نگه‌داشتن مرجع قوی + پاکسازی خودکار پس از پایان."""
    t = asyncio.create_task(coro)
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)
    return t


# =====================================================================
# 🔒 جوین اجباری
# =====================================================================


async def resolve_join_link(context: ContextTypes.DEFAULT_TYPE, ref: str) -> str:
    """لینک عضویت کانال: یوزرنیم عمومی → t.me ، خصوصی → invite_link (با کش)."""
    cached = CHAT_LINKS.get(ref)
    if cached and cached[0] > time.time():
        return cached[1]
    link = ""
    if ref.startswith("@"):
        link = f"https://t.me/{ref[1:]}"
    else:
        try:
            chat = await context.bot.get_chat(ref)
            if getattr(chat, "username", None):
                link = f"https://t.me/{chat.username}"
            elif getattr(chat, "invite_link", None):
                link = chat.invite_link or ""
        except TelegramError as exc:
            log.warning("get_chat(%s) failed: %s", ref, exc)
    CHAT_LINKS[ref] = (time.time() + 1800, link)
    return link


async def is_member_of(context: ContextTypes.DEFAULT_TYPE, ref: str, user_id: int) -> bool:
    try:
        cm = await context.bot.get_chat_member(ref, user_id)
        status = getattr(cm, "status", "")
        if status in ("member", "administrator", "creator"):
            return True
        if status == "restricted" and getattr(cm, "is_member", False):
            return True
        return False
    except Forbidden:
        # ربات دسترسی به کانال ندارد → محدودیت اعمال نمی‌کنیم که بقیه بلاک نشوند
        log.warning("ربات عضو/ادمین %s نیست؛ چک عضویت رد شد.", ref)
        return True
    except BadRequest as exc:
        log.warning("get_chat_member(%s): %s", ref, exc)
        return True
    except TelegramError as exc:
        log.warning("get_chat_member(%s): %s", ref, exc)
        return True


async def get_missing_channels(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> List[Tuple[str, str]]:
    """لیست کانال‌هایی که کاربر عضو نیست: [(ref, join_link)]"""
    if JOIN_OK.get(user_id, 0) > time.time():
        return []
    missing: List[Tuple[str, str]] = []
    for ref in get_force_channels():
        link = await resolve_join_link(context, ref)
        if not link:
            continue  # کانال خراب/خصوصی بدون لینک → نادیده گرفته می‌شود
        if not await is_member_of(context, ref, user_id):
            missing.append((ref, link))
    if not missing:
        JOIN_OK[user_id] = time.time() + JOIN_CACHE_SEC
    return missing


def join_keyboard(missing: List[Tuple[str, str]], uid: int = 0) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for ref, link in missing:
        name = ref if ref.startswith("@") else ("channel" if get_lang(uid) == "en" else "کانال")
        rows.append([InlineKeyboardButton(f"🔔 {name}", url=link)])
    rows.append([InlineKeyboardButton(B(uid, "check_join"), callback_data="join:chk")])
    return InlineKeyboardMarkup(rows)


# =====================================================================
# ⌨️ منوها و متن‌ها (متن‌های دوزبانه‌ی کاربر در STRINGS بالای فایل هستند)
# =====================================================================

ERR_GENERIC_TXT = "⚠️ خطایی رخ داد! لطفاً چند لحظه بعد دوباره تلاش کن."

BANNED_TXT = "🚫 شما از استفاده‌ی این ربات محروم شده‌اید!"

ADM_PANEL_TXT = (
    "🛠 <b>پنل مدیریت</b>\n\n"
    "از دکمه‌های زیر استفاده کن:\n"
    "• 📊 آمار → تعداد کاربران و دانلودها\n"
    "• 🖥 وضعیت سرور → CPU / RAM / دیسک\n"
    "• 📢 ارسال همگانی → پیام به همه‌ی اعضا\n"
    "• 🔒 کانال‌های اجباری → افزودن / حذف\n"
    "• 🚫 بن / ♻️ آنبن → مدیریت کاربران"
)


def main_menu_kb(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🎬 دانلود ویدیو", callback_data="menu:dl"),
            InlineKeyboardButton("🎧 شناسایی موزیک", callback_data="menu:song"),
        ],
        [InlineKeyboardButton("🕘 تاریخچه", callback_data="cmd:hist"),
         InlineKeyboardButton("ℹ️ راهنما", callback_data="menu:help")],
        [InlineKeyboardButton(B(uid, "lang"), callback_data="menu:lang")],
    ]
    if uid in ADMIN_IDS:
        rows.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="adm:panel")])
    return InlineKeyboardMarkup(rows)


def history_keyboard(rows_db: List[Tuple], uid: int) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for hid, platform, kind, title, url in rows_db:
        icon = {"youtube": "▶️", "instagram": "📸", "tiktok": "🎵",
                "spotify": "🟢", "soundcloud": "☁️", "channel": "📨"}.get(platform, "🌐")
        label = f"{icon} {clean_title(title)[:28]}"
        tok = reg_token_add(kind="hist", owner=uid, url=url, htype=kind)
        rows.append([InlineKeyboardButton(label, callback_data=f"rh:{tok}")])
    return InlineKeyboardMarkup(rows)


def video_keyboard(tok: str, uid: int = 0) -> InlineKeyboardMarkup:
    # دکمه‌های زیر ویدیو (استایل نمایشی دکمه‌ها را کلاینت تلگرام تعیین می‌کند؛
    # برچسب‌ها طوری طراحی شده‌اند که حس دکمه‌ی شیشه‌ای/مینیمال بدهند.)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(B(uid, "song_id"), callback_data=f"s:{tok}")],
            [InlineKeyboardButton(B(uid, "dl_music"), callback_data=f"v:{tok}")],
        ]
    )


def track_keyboard(qtok: str, listen_url: str = "", uid: int = 0) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(B(uid, "dl_this"), callback_data=f"q:{qtok}")]]
    # دکمه‌ی جایگزین: دانلود از SoundCloud (اگر یوتیوب در دسترس نبود)
    rows.append([InlineKeyboardButton(B(uid, "dl_sc"), callback_data=f"sc:{qtok}")])
    extra = [
        InlineKeyboardButton(B(uid, "lyrics"), callback_data=f"ly:{qtok}"),
        InlineKeyboardButton(B(uid, "preview"), callback_data=f"pv:{qtok}"),
        InlineKeyboardButton(B(uid, "ringtone"), callback_data=f"rg:{qtok}"),
    ]
    rows.append(extra)
    if listen_url:
        rows.append([InlineKeyboardButton(B(uid, "listen"), url=listen_url)])
    return InlineKeyboardMarkup(rows)


def quality_keyboard(tok: str, uid: int, include_audio: bool = True) -> InlineKeyboardMarkup:
    """دکمه‌های انتخاب کیفیت قبل از دانلود."""
    order = ["1080", "720", "360"]
    rows: List[List[InlineKeyboardButton]] = []
    for q in order:
        rows.append([InlineKeyboardButton(QUALITY_LABELS[q][get_lang(uid)], callback_data=f"f:{tok}:{q}")])
    if include_audio:
        rows.append([InlineKeyboardButton(QUALITY_LABELS["aud"][get_lang(uid)], callback_data=f"f:{tok}:aud")])
    return InlineKeyboardMarkup(rows)


def playlist_keyboard(jtok: str, entries: List[Dict[str, Any]], uid: int) -> InlineKeyboardMarkup:
    """گرید شماره‌ی آیتم‌های پلی‌لیست + دکمه دانلود همه."""
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for i, e in enumerate(entries, 1):
        dur = f" [{fmt_dur(e.get('duration'))}]" if e.get("duration") else ""
        row.append(InlineKeyboardButton(f"{i}{dur}", callback_data=f"pl:{jtok}:{i - 1}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬇️ دانلود همه (تا %d)" % len(entries), callback_data=f"pl:{jtok}:all")])
    return InlineKeyboardMarkup(rows)


def admin_panel_kb() -> InlineKeyboardMarkup:
    mnt = "🟢 روشن" if maintenance_on() else "🔴 خاموش"
    q = "🟢 روشن" if queue_on() else "🔴 خاموش"
    az = "🟢 روشن" if auto_shazam_on() else "🔴 خاموش"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 آمار ربات", callback_data="adm:stats"),
                InlineKeyboardButton("🖥 وضعیت سرور", callback_data="adm:srv"),
            ],
            [
                InlineKeyboardButton("📢 ارسال همگانی", callback_data="adm:bcast"),
                InlineKeyboardButton("🔒 کانال‌های اجباری", callback_data="adm:chans"),
            ],
            [
                InlineKeyboardButton("🚫 بن کاربر", callback_data="adm:ban"),
                InlineKeyboardButton("♻️ رفع بن", callback_data="adm:unban"),
            ],
            [InlineKeyboardButton(f"🛠 حالت تعمیر: {mnt}", callback_data="adm:mnt")],
            [InlineKeyboardButton(f"🕒 صف دانلود: {q}", callback_data="adm:queue")],
            [InlineKeyboardButton(f"🤖 شزام خودکار: {az}", callback_data="adm:ashz")],
        ]
    )


def back_kb(cb: str = "menu:back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=cb)]])


# =====================================================================
# 📥 yt-dlp (هماهنگ، در Thread اجرا می‌شود)
# =====================================================================


def _ydl_base_opts() -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": False,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 25,
        "concurrent_fragment_downloads": 4,
        "noplaylist": True,
        "playlist_items": "1",
        "outtmpl": str(DOWNLOAD_DIR / "%(extractor_key)s_%(id)s.%(ext)s"),
        "geo_bypass": True,
    }
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE.resolve())
    return opts


# هر زنجیره باید با /best تمام شود تا هیچ‌وقت «Requested format is not available» نگیریم.
# محدودیت حجم را به‌جای داخل فرمت، با opts["max_filesize"] اعمال می‌کنیم (گرم‌تر و مطمئن‌تر).

# انتخاب کیفیت توسط کاربر (دکمه‌های 360/720/1080).
# فرمت‌ها «پیش‌رونده» هستند تا هم در DASH (وب) و هم در HLS (mweb) کار کنند.
# زنجیره همیشه با /worst تمام می‌شود تا حتی در بدترین حالت (ویدیوهایی که best
# یا progressive ترکیبی ندارند) یک فرمت برگردد و «Requested format is not available»
# نگیریم. کیفیت در بدترین حالت پایین می‌آید ولی دانلود انجام می‌شود.
FORMAT_VIDEO = "best[height<=1080]/b/best/worst"
QUALITY_FORMATS: Dict[str, str] = {
    "360": "best[height<=360]/b/best/worst",
    "720": "best[height<=720]/b/best/worst",
    "1080": "best[height<=1080]/b/best/worst",
}

# --- نردبان تلاش یوتیوب: اگر یک کلاینت شکست خورد با بعدی امتحان می‌کنیم ---
# آی‌پی دیتاسنتر روی کلاینت وبِ پیش‌فرض به «Sign in / page needs to be reloaded»
# می‌خورد؛ ترکیب‌های جایگزین (tv/mweb، کوکی بدون VISITOR_INFO1_LIVE و بدون کوکی)
# معمولاً عبور می‌دهند. اگر افزونه‌ی PO-Token (bgutil) نصب باشد خودکار هم استفاده می‌شود.
_YT_FB_LADDER: List[Dict[str, Any]] = [
    {},                                              # 1) پیش‌فرض + کوکی اصلی
    {"player_client": "tv"},                         # 2) TV + کوکی اصلی
    {"player_client": "mweb"},                       # 3) mweb + کوکی اصلی
    {"player_client": "mweb", "novi": True},         # 4) mweb + کوکی بدون VISITOR
    {"novi": True},                                  # 5) پیش‌فرض + کوکی بدون VISITOR
    {"player_client": "tv_embedded", "noc": True},   # 6) embedded بدون کوکی
    {"noc": True},                                   # 7) پیش‌فرض بدون کوکی
]
_YT_TRANSIENT_RE = re.compile(
    r"sign in|not a bot|needs to be reload|confirm you|login required|"
    r"requested format|unable to extract player", re.I)


def _extract_with_fallback(url: str, base_opts: Dict[str, Any], *, download: bool = True) -> Any:
    """extract_info با نردبان کلاینت‌ها؛ خطاهای گذرا → رانگ بعدی، بقیه → raise فوری."""
    had_cookies = "cookiefile" in base_opts
    novi_ready = COOKIES_NOVI_FILE != COOKIES_FILE and COOKIES_NOVI_FILE.exists()
    last_exc: Optional[Exception] = None
    for rung in _YT_FB_LADDER:
        opts = dict(base_opts)
        ea = dict(opts.get("extractor_args") or {})
        pc = rung.get("player_client")
        if pc:
            yargs = dict(ea.get("youtube") or {})
            yargs["player_client"] = [pc]
            ea["youtube"] = yargs
        if ea:
            opts["extractor_args"] = ea
        if rung.get("noc") and had_cookies:
            opts.pop("cookiefile", None)
        elif rung.get("novi") and had_cookies and novi_ready:
            opts["cookiefile"] = str(COOKIES_NOVI_FILE.resolve())
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            if not _YT_TRANSIENT_RE.search(msg):
                raise  # لینک خراب/خصوصی/ژئو… → بی‌خود نگرد
            last_exc = exc
            log.warning("yt-fallback[%s] failed: %s", pc or ("" if not rung.get("noc") else "no-cookie"), msg[:140])
    assert last_exc is not None
    raise last_exc
QUALITY_LABELS: Dict[str, Dict[str, str]] = {
    "360": {"fa": "🎬 کیفیت ۳۶۰p", "en": "🎬 360p"},
    "720": {"fa": "🎬 کیفیت ۷۲۰p", "en": "🎬 720p"},
    "1080": {"fa": "🎬 کیفیت ۱۰۸۰p", "en": "🎬 1080p"},
    "aud": {"fa": "🎧 فقط صدا (MP3)", "en": "🎧 Audio only (MP3)"},
}

# --- صف دانلود ---
_DL_SEM: Optional[asyncio.Semaphore] = None
_DL_WAITING: int = 0


def _get_sem() -> asyncio.Semaphore:
    global _DL_SEM
    if _DL_SEM is None:
        _DL_SEM = asyncio.Semaphore(max(1, MAX_CONCURRENT_DL))
    return _DL_SEM


async def queue_acquire(status_msg: Message, uid: int) -> bool:
    """اگر صف روشن باشد نوبت می‌گیرد؛ True یعنی «در صف بودی و الان نوبتت شد»."""
    global _DL_WAITING
    if not queue_on():
        return False
    _DL_WAITING += 1
    try:
        await status_msg.edit_text(L(uid, "queued", pos=_DL_WAITING), parse_mode=ParseMode.HTML)
    except TelegramError:
        pass
    await _get_sem().acquire()
    _DL_WAITING -= 1
    return True


def queue_release() -> None:
    try:
        _get_sem().release()
    except Exception:
        pass


def find_downloaded_file(info: Dict[str, Any], prefer_ext: Optional[str] = None) -> Optional[Path]:
    """پیدا کردن مسیر واقعی فایل دانلودشده (روش‌های مختلف + fallback)."""
    try:
        for rd in info.get("requested_downloads") or []:
            fp = rd.get("filepath") or rd.get("filename")
            if fp:
                p = Path(fp)
                if prefer_ext and p.suffix.lower() != prefer_ext:
                    alt = p.with_suffix(prefer_ext)
                    if alt.exists():
                        return alt
                if p.exists():
                    return p
    except Exception:
        pass
    cand = info.get("filepath") or info.get("filename")
    if cand and Path(cand).exists():
        return Path(cand)
    try:
        vid_id = str(info.get("id") or "").strip()
        files = sorted(
            (f for f in DOWNLOAD_DIR.glob("*") if f.is_file()),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if prefer_ext:
            files = [f for f in files if f.suffix.lower() == prefer_ext] or files
        # اگر id داریم، فقط فایلی که نامش شامل همان id است بپذیر —
        # تا fallback «جدیدترین فایل» فایل دانلودِ همزمانِ کاربر دیگری را برنگرداند.
        if vid_id and vid_id.lower() not in ("na", "none"):
            id_hits = [f for f in files if vid_id in f.name]
            if id_hits:
                return id_hits[0]
            return None
        if files and (time.time() - files[0].stat().st_mtime) < 900:
            return files[0]
    except Exception:
        pass
    return None


def dl_video_sync(url: str, prog: Dict[str, Any], platform: str = "other", download: bool = True,
                  quality: str = "best") -> Tuple[Dict[str, Any], Optional[Path]]:
    """دانلود ویدیو/صوت (sync — داخل thread صدا زده می‌شود).

    quality: 360 / 720 / 1080 / best — یا برای ساند‌کلود همیشه MP3.
    """

    def hook(d: Dict[str, Any]) -> None:
        try:
            pct_s = (d.get("_percent_str") or "").strip().replace("%", "")
            prog["pct_num"] = float(pct_s) if pct_s else prog.get("pct_num", 0.0)
            prog["percent"] = (d.get("_percent_str") or "").strip()
            prog["speed"] = (d.get("_speed_str") or "").strip() or "~"
            prog["eta"] = (d.get("_eta_str") or "").strip() or "--"
        except Exception:
            pass

    opts = _ydl_base_opts()
    opts["progress_hooks"] = [hook]
    if platform == "soundcloud" or quality == "aud":
        # فقط صدا → مستقیم MP3
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": AUDIO_BITRATE,
                    }
                ],
            }
        )
    else:
        fmt = FORMAT_VIDEO if quality not in QUALITY_FORMATS else QUALITY_FORMATS[quality]
        opts.update(
            {
                "format": fmt,
                # mp4 ترجیح است ولی اگر کدک‌ها اجازه ندهند mkv/webm — به‌جای کرش
                "merge_output_format": "mp4/mkv/webm",
                "max_filesize": MAX_FILE_MB * MB,
            }
        )
    info = _extract_with_fallback(url, opts, download=download)
    if not download:
        return info or {}, None
    if info and info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise RuntimeError("محتوایی برای دانلود پیدا نشد.")
        info = entries[0]
    path = find_downloaded_file(info)
    if not path:
        raise RuntimeError("فایل دانلودشده پیدا نشد!")
    return info, path


def dl_audio_sync(query: str, download: bool = True, search: str = "ytsearch1") -> Tuple[Dict[str, Any], Optional[Path]]:
    """جستجو + دانلود صوت mp3 (sync). search: ytsearch1 | scsearch1 | ..."""
    opts = _ydl_base_opts()
    opts.pop("playlist_items", None)
    opts.update(
        {
            "format": "bestaudio/best",
            "default_search": search,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": AUDIO_BITRATE,
                }
            ],
        }
    )
    info = _extract_with_fallback(query, opts, download=download)
    if not download:
        return info or {}, None
    if info and info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise RuntimeError("موزیکی پیدا نشد.")
        info = entries[0]
    path = find_downloaded_file(info, prefer_ext=".mp3")
    if not path:
        raise RuntimeError("فایل موزیک پیدا نشد!")
    return info, path


def friendly_dl_error(exc: BaseException) -> str:
    s = str(exc)
    low = s.lower()
    if "larger than max-filesize" in low:
        return f"📦 حجم این فایل بیشتر از حد مجاز ({MAX_FILE_MB}MB) است!"
    if "sign in to confirm" in low or ("age" in low and "restrict" in low):
        return "🔞 این محتوا محدودیت سنی/ورود دارد؛ باید کوکی معتبر حساب یوتیوب را در سرور قرار دهی."
    if "private" in low:
        return "🔒 این محتوا خصوصی است و قابل دانلود نیست."
    if "rate-limit" in low or "429" in low or "login required" in low or "checkpoint" in low:
        return "⏳ سایت مقصد محدودیت زده! کوکی معتبر لازم است یا کمی بعد دوباره امتحان کن."
    if "unsupported url" in low:
        return "🚫 این لینک پشتیبانی نمی‌شود. لینک مستقیم پست/ویدیو را بفرست."
    if "not available" in low or "removed" in low or "unavailable" in low or "404" in low:
        return "❌ این محتوا در دسترس نیست یا حذف شده است."
    tail = esc(s[-200:])
    return f"⚠️ دانلود ناموفق بود!\n<pre>{tail}</pre>"


async def _monitor_progress(status_msg: Message, prog: Dict[str, Any]) -> None:
    last = ""
    while not prog.get("done"):
        pct = prog.get("pct_num") or 0.0
        text = (
            f"{make_bar(pct)}  <b>{prog.get('percent', '…')}</b>\n"
            f"⚡ سرعت: <code>{prog.get('speed', '~')}</code>   ⏱ مانده: <code>{prog.get('eta', '--')}</code>"
        )
        if text != last:
            try:
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
                last = text
            except TelegramError:
                pass
        await asyncio.sleep(3)


# =====================================================================
# 🎵 ShazamIO — استخراج صدا + شناسایی
# =====================================================================

_shazam_client: Optional[Shazam] = None


async def extract_audio_snippet(video_path: Path) -> Path:
    """۹۵ ثانیه‌ی اول صدا را با ffmpeg به mp3/m4a تبدیل می‌کند."""
    attempts = [
        (DOWNLOAD_DIR / f"snap_{secrets.token_hex(4)}.mp3",
         ["-c:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", "-ac", "2"]),
        (DOWNLOAD_DIR / f"snap_{secrets.token_hex(4)}.m4a",
         ["-c:a", "aac", "-b:a", "160k"]),
    ]
    base = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path), "-vn", "-map", "a:0",
        "-t", str(SHAZAM_SNIPPET_SEC),
    ]
    ffmpeg_missing = False
    for out_path, codec_args in attempts:
        cmd = base + codec_args + [str(out_path)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            ffmpeg_missing = True
            break
        except OSError:
            continue
        try:
            await asyncio.wait_for(proc.communicate(), timeout=240)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            continue
        if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 2048:
            return out_path
    if ffmpeg_missing:
        raise RuntimeError("ffmpeg روی سرور نصب نیست!")
    raise RuntimeError("استخراج صدا از ویدیو ناموفق بود.")


async def recognize_file(path: Path) -> Dict[str, Any]:
    global _shazam_client
    if _shazam_client is None:
        _shazam_client = Shazam()
    fn = getattr(_shazam_client, "recognize_song", None) or _shazam_client.recognize
    return await fn(str(path))


def parse_shazam_result(res: Any) -> Optional[Dict[str, str]]:
    if not isinstance(res, dict):
        return None
    track = res.get("track")
    if not isinstance(track, dict):
        return None
    title = track.get("title") or ""
    if not title:
        return None
    artist = track.get("subtitle") or ""

    meta: Dict[str, str] = {}

    def feed(md_list: Any) -> None:
        for md in md_list or []:
            try:
                t = md.get("title")
                v = md.get("text")
                if t and v and t not in meta:
                    meta[str(t)] = str(v)
            except Exception:
                pass

    feed(track.get("metadata"))
    listen_url = ""
    for sec in track.get("sections") or []:
        feed(sec.get("metadata"))
        for md in sec.get("metadata") or []:
            try:
                tl = (md.get("title") or "").lower()
                v = md.get("text") or ""
                if isinstance(v, str) and v.startswith("http"):
                    if not listen_url and any(k in tl for k in ("applemusic", "spotify", "listen")):
                        listen_url = v
            except Exception:
                pass

    artists = ""
    arts = track.get("artists")
    if isinstance(arts, list) and arts:
        names = [a.get("name", "") for a in arts if isinstance(a, dict)]
        artists = ", ".join(n for n in names if n)
    if not artists:
        artists = artist

    share = track.get("share") or {}
    images = track.get("images") or {}
    genres = ""
    g = track.get("genres")
    if isinstance(g, dict):
        genres = g.get("primary") or ""

    return {
        "title": str(title),
        "artist": str(artists),
        "album": meta.get("Album", ""),
        "year": meta.get("Released", "") or track.get("releasedate") or "",
        "genre": str(genres),
        "label": meta.get("Label", ""),
        "cover": images.get("coverarthq") or images.get("coverart") or "",
        "shazam_url": share.get("link") or "",
        "listen_url": listen_url,
    }


async def fetch_thumb(url: str) -> Optional[Path]:
    """دانلود کاور/تامبنیل برای پیوست کردن به send_audio."""
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as cli:
            r = await cli.get(url)
            if r.status_code != 200 or len(r.content) < 1024:
                return None
            p = DOWNLOAD_DIR / f"thumb_{secrets.token_hex(4)}.jpg"
            p.write_bytes(r.content)
            return p
    except Exception:
        return None


# =====================================================================
# 🎼 ابزارهای موزیک: تگ MP3 / متن ترانه / اسپاتیفای
# =====================================================================


def tag_mp3(
    path: Path,
    title: str,
    artist: str,
    album: str = "",
    year: str = "",
    genre: str = "",
    cover_path: Optional[Path] = None,
) -> None:
    """درج ID3 (عنوان/خواننده/کاور...) داخل فایل MP3 — اگر mutagen نبود، بی‌صدا رد می‌شود."""
    if not HAS_MUTAGEN or not path.exists() or path.suffix.lower() != ".mp3":
        return
    try:
        audio = ID3(str(path))
    except Exception:
        audio = ID3()
    try:
        audio.setall("TIT2", [TIT2(encoding=3, text=title[:120] if title else "")])
        audio.setall("TPE1", [TPE1(encoding=3, text=artist[:120] if artist else "")])
        if album:
            audio.setall("TALB", [TALB(encoding=3, text=album[:120])])
        if year:
            audio.setall("TDRC", [TDRC(encoding=3, text=year[:16])])
        if genre:
            audio.setall("TCON", [TCON(encoding=3, text=genre[:60])])
        if cover_path and Path(cover_path).exists():
            with open(cover_path, "rb") as fc:
                audio.setall("APIC", [APIC(
                    encoding=3, mime="image/jpeg", type=3, desc="Cover", data=fc.read(),
                )])
        audio.save(str(path), v2_version=3)
    except Exception as exc:
        log.warning("tag_mp3 failed for %s: %s", path.name, exc)


async def fetch_lyrics(artist: str, title: str) -> Optional[str]:
    """متن ترانه از lrclib.net (رایگان و بدون کلید)."""
    query = f"{artist} {title}".strip()
    if not query:
        return None
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as cli:
            r = await cli.get(
                "https://lrclib.net/api/search",
                params={"q": query, "limit": 1},
                headers={"User-Agent": "TelegramMusicFinderBot/2.0"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, list) and data:
                plain = data[0].get("plainLyrics") or ""
                return plain.strip() or None
    except Exception as exc:
        log.warning("fetch_lyrics failed: %s", exc)
    return None


async def search_song_by_lyrics(query: str) -> Optional[Dict[str, str]]:
    """جستجوی آهنگ از طریق «متن ترانه» (بدون نیاز به نام خواننده).

    چند موتور پشت هم امتحان می‌شوند:
      1) Genius (جستجوی غیررسمی — محتوای متن ترانه را ایندکس می‌کند)
      2) DuckDuckGo (لاتین: «عبارت» + lyrics؛ فارسی/عربی: «متن آهنگ …»)
      3) lrclib.net (اگر متن شامل نام آهنگ/خواننده باشد)
    در صورت موفقیت dict با کلیدهای artist/title/source برمی‌گردد
    (برای نتایج فارسی ممکن است artist خالی باشد و title همان کوئری کامل باشد).
    """
    snippet = _clean_lyric_snippet(query)
    if len(snippet) < 4:
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as cli:
            for backend in (_genius_by_lyrics, _ddg_by_lyrics, _lrclib_by_name):
                try:
                    hit = await backend(cli, snippet)
                except Exception as exc:  # noqa: BLE001
                    log.warning("lyrics backend %s failed: %s", backend.__name__, exc)
                    hit = None
                if hit:
                    log.info("lyrics-hit[%s]: %s — %s", hit.get("source"), hit.get("artist"), hit.get("title"))
                    return hit
    except Exception as exc:  # noqa: BLE001
        log.warning("search_song_by_lyrics failed: %s", exc)
    return None


def looks_like_lyrics(text: str) -> bool:
    """حدس می‌زند متن ارسال‌شده «تکه‌ای از ترانه» است تا نام آهنگ."""
    t = (text or "").strip()
    if len(t) < 25:
        return False
    words = len(t.split())
    lines = len([ln for ln in t.splitlines() if ln.strip()])
    return lines >= 2 or words >= 8 or len(t) >= 80


LYRICS_TAG_NOISE = re.compile(
    r"^\s*(\[\d{1,2}:\d{2}(?::\d{2})?\]|\[\s*(?:verse|chorus|hook|bridge|intro|outro|pre-?chorus)[^\]]*\])\s*$",
    re.I | re.M,
)


def _clean_lyric_snippet(text: str, limit: int = 220) -> str:
    """حذف برچسب‌های [Verse]/[0:12] و فشرده‌سازی فاصله‌ها برای ارسال به موتورهای جستجو."""
    t = LYRICS_TAG_NOISE.sub(" ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit].strip()


WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


async def _genius_by_lyrics(cli: httpx.AsyncClient, snippet: str) -> Optional[Dict[str, str]]:
    """جستجوی غیررسمی Genius — محتوای ترانه را می‌شناسد (بدون کلید API)."""
    r = await cli.get(
        "https://genius.com/api/search/multi",
        params={"q": snippet, "per_page": 5, "text_format": "plain", "page": 1},
        headers={"User-Agent": WEB_UA, "Accept": "application/json"},
    )
    if r.status_code != 200:
        return None
    data = r.json()
    if not isinstance(data, dict):
        return None
    for sec in (data.get("sections") or []):
        for hit in (sec.get("hits") or []):
            res = hit.get("result") or {}
            if res.get("type") not in (None, "song"):
                continue
            title = (res.get("title") or "").strip()
            artist = ((res.get("primary_artist") or {}).get("name") or "").strip()
            if title:
                return {"artist": artist, "title": title, "source": "Genius"}
    return None


DDG_SITE_SUFFIX = re.compile(
    r"\s*(?:\||[-–—])\s*(?:genius lyrics|genius|musixmatch|azlyrics(?:\.com)?|lyrics\.com|"
    r"songlyrics(?:\.com)?|elyrics(?:\.net)?|releaselyrics|paroles|youtube|fandom)\s*$", re.I)

FA_LYRICS_PREFIX = re.compile(
    r"^\s*(?:متن\s+(?:آهنگ|ترانه|سروده|غزل)|دانلود\s+(?:آهنگ|آهنگک)|آهنگک|آهنگ)\s+", re.I)

NON_LATIN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def _ddg_titles(body: str, limit: int = 8) -> List[str]:
    """عنوان نتایج صفحه‌ی HTML داکی‌داکی‌گو را بیرون می‌کشد."""
    out: List[str] = []
    for raw in re.findall(r'class="result__a"[^>]*>(.*?)</a>', body, re.S)[:limit]:
        t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            out.append(t)
    return out


def _parse_artist_title(t: str) -> Optional[Tuple[str, str]]:
    """از عنوانهایی مثل «Queen – Bohemian Rhapsody Lyrics» خواننده و نام را درمی‌آورد."""
    t = DDG_SITE_SUFFIX.sub("", t).strip()
    m = re.match(r"Lyrics of (.+?) by (.+)", t, re.I)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    m = re.match(r"(.+?)\s[-–—]\s(.+?)\s*[\(\[]?\s*[Ll]yrics?\s*[\)\]]?\s*$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"(.+?)\s*[\(\[]?\s*[Ll]yrics?\s*[\)\]]?\s*[-–—]\s*(.+)$", t)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return None


async def _ddg_by_lyrics(cli: httpx.AsyncClient, snippet: str) -> Optional[Dict[str, str]]:
    """جستجوی DuckDuckGo روی متن ترانه.

    • لاتین: عبارت دقیق داخل گیومه + «lyrics» و استخراج «خواننده - آهنگ» از عنوان نتایج.
    • فارسی/عربی: الگوی «متن آهنگ <تکه>» نتیجه می‌دهد؛ عنوان برتر (که معمولاً
      «نام آهنگ + خواننده» است) بدون تفکیک به‌عنوان کوئری جستجو برگردانده می‌شود.
    """
    queries: List[str] = []
    if NON_LATIN_RE.search(snippet):
        queries.append(f"متن آهنگ {snippet[:100]}")
        queries.append(f'"{snippet[:150]}" lyrics')
    else:
        queries.append(f'"{snippet[:150]}" lyrics')
    for q in queries:
        try:
            r = await cli.post("https://html.duckduckgo.com/html/",
                               data={"q": q, "kl": "wt-wt"},
                               headers={"User-Agent": WEB_UA})
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        titles = _ddg_titles(r.text)
        if q.startswith("متن آهنگ"):
            for t in titles:
                core = FA_LYRICS_PREFIX.sub("", t).split("|")[0].strip(" -–—")
                if len(core) >= 4:
                    return {"artist": "", "title": core, "source": "DuckDuckGo"}
        else:
            for t in titles:
                hit = _parse_artist_title(t)
                if hit:
                    return {"artist": hit[0], "title": hit[1], "source": "DuckDuckGo"}
    return None


async def _lrclib_by_name(cli: httpx.AsyncClient, snippet: str) -> Optional[Dict[str, str]]:
    """lrclib فقط نام آهنگ/خواننده/آلبوم را می‌گردد — به‌عنوان آخرین تلاش."""
    r = await cli.get(
        "https://lrclib.net/api/search",
        params={"q": snippet, "limit": 1},
        headers={"User-Agent": "TelegramMusicFinderBot/2.0"},
    )
    if r.status_code != 200:
        return None
    data = r.json()
    if not isinstance(data, list) or not data:
        return None
    top = data[0]
    artist = (top.get("artistName") or "").strip()
    title = (top.get("trackName") or "").strip()
    if not (artist and title):
        return None
    return {"artist": artist, "title": title, "source": "LRClib"}


async def spotify_track_info(url: str) -> Optional[Dict[str, str]]:
    """مشخصات ترک اسپاتیفای از oEmbed عمومی (رایگان، بدون لاگین)."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as cli:
            r = await cli.get(
                "https://open.spotify.com/oembed",
                params={"url": url},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                return None
            d = r.json()
            title = d.get("title") or ""
            if not title:
                return None
            return {
                "title": title,
                "thumb": d.get("thumbnail_url") or "",
            }
    except Exception as exc:
        log.warning("spotify_track_info failed: %s", exc)
        return None


def probe_link_sync(url: str) -> Dict[str, Any]:
    """بررسی سریع لینک: پلی‌لیست است یا تک؟ (بدون دانلود، flat و سبک)"""
    opts = _ydl_base_opts()
    opts.pop("playlist_items", None)
    # format صریحِ همیشه‌موفق — چون فقط متادیتا می‌خواهیم و برخی ویدیوها
    # فقط HLS دارند و سِلکتور پیش‌فرض bv*+ba روی آن‌ها خطای not available می‌دهد.
    opts.update({"extract_flat": "in_playlist", "skip_download": True, "format": "best/worst"})
    info = _extract_with_fallback(url, opts, download=False)
    if info and info.get("_type") == "playlist":
        entries = []
        for e in (info.get("entries") or [])[:PLIST_MAX_ITEMS]:
            if isinstance(e, dict):
                entries.append({
                    "title": e.get("title") or "?",
                    "id": e.get("id") or "",
                    "url": e.get("url") or e.get("webpage_url") or "",
                    "duration": e.get("duration"),
                })
        return {"playlist": True, "title": info.get("title") or "", "entries": entries}
    return {
        "playlist": False,
        "title": (info or {}).get("title") or "",
        "duration": (info or {}).get("duration"),
    }


# =====================================================================
# 👤 هندلرهای اصلی کاربر
# =====================================================================


async def banned_guard(update: Update) -> bool:
    u = update.effective_user
    msg = update.effective_message
    if u and is_banned_uid(u.id):
        if msg:
            try:
                await msg.reply_text(BANNED_TXT)
            except TelegramError:
                pass
        return True
    return False


async def require_joined(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True اگر کاربر عضو همه‌ی کانال‌های اجباری باشد؛ وگرنه پیام عضویت می‌فرستد."""
    u = update.effective_user
    missing = await get_missing_channels(context, u.id)
    if not missing:
        return True
    try:
        await update.effective_message.reply_html(L(u.id, "join"), reply_markup=join_keyboard(missing, u.id))
    except TelegramError:
        pass
    return False


async def send_welcome(msg: Message, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    name = esc(user.first_name or ("my friend" if get_lang(user.id) == "en" else "دوست من"))
    try:
        await msg.reply_html(
            L(user.id, "welcome", name=name),
            reply_markup=main_menu_kb(user.id),
        )
    except TelegramError:
        pass


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return
    upsert_user(update.effective_user)
    if await banned_guard(update):
        return
    if not await require_joined(update, context):
        return
    await send_welcome(update.effective_message, context, update.effective_user)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return
    u = update.effective_user
    upsert_user(u)
    if await banned_guard(update):
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(B(u.id, "back"), callback_data="menu:back"),
        InlineKeyboardButton(B(u.id, "lang"), callback_data="menu:lang"),
    ]])
    await update.effective_message.reply_html(L(u.id, "hint", max=MAX_FILE_MB), reply_markup=kb)


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return
    u = update.effective_user
    new_lang = "en" if get_lang(u.id) == "fa" else "fa"
    set_lang(u.id, new_lang)
    await send_welcome(update.effective_message, context, u)


async def show_history(msg: Message, user) -> None:
    rows_db = get_history(user.id)
    if not rows_db:
        try:
            await msg.reply_text(L(user.id, "hist_empty"))
        except TelegramError:
            pass
        return
    try:
        await msg.reply_html(L(user.id, "hist_header"), reply_markup=history_keyboard(rows_db, user.id))
    except TelegramError:
        pass


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return
    u = update.effective_user
    upsert_user(u)
    if await banned_guard(update):
        return
    await show_history(update.effective_message, u)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return
    ud = context.user_data
    had_pending = bool(ud.pop("pending", None))
    ud.pop("bc_msg", None)
    txt = "✅ عملیات فعلی لغو شد." if had_pending else "چیزی برای لغو وجود نداشت."
    await update.effective_message.reply_text(txt)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    msg = update.effective_message
    if u is None or msg is None:
        return
    upsert_user(u)
    if u.id not in ADMIN_IDS:
        await msg.reply_text("⛔️ این بخش فقط برای مدیران است!")
        return
    await msg.reply_html(ADM_PANEL_TXT, reply_markup=admin_panel_kb())


# ---------------------------------------------------------------------
# دریافت محتوای آزاد: pending ادمین یا لینک دانلود
# ---------------------------------------------------------------------


async def gate_check(update: Update, context: ContextTypes.DEFAULT_TYPE, user, msg: Message) -> bool:
    """گیت‌های مشترک: تعمیر / بن / جوین اجباری. False = متوقف شو."""
    if user.id not in ADMIN_IDS and maintenance_on():
        await safe_reply(msg, L(user.id, "maint"))
        return False
    if is_banned_uid(user.id):
        await safe_reply(msg, L(user.id, "banned"))
        return False
    if not await require_joined(update, context):
        return False
    return True


def cooldown_check_or_notice(uid: int, reply_coro_factory) -> bool:
    """True اگر مجاز باشد (و نوبت ثبت شود)."""
    left = cooldown_left(uid)
    if left > 0:
        asyncio.ensure_future(reply_coro_factory(L(uid, "cooldown", sec=left)))
        return False
    return True


async def safe_reply(msg: Message, text: str) -> None:
    try:
        await msg.reply_html(text, disable_web_page_preview=True)
    except TelegramError:
        pass


async def notify_log_channel(bot, title: str, detail: str) -> None:
    """گزارش خطا به کانال لاگ خصوصی ادمین (اگر تنظیم شده باشد)."""
    if not LOG_CHANNEL:
        return
    try:
        await bot.send_message(
            LOG_CHANNEL,
            f"🐞 <b>{esc(title)}</b>\n<pre>{esc(detail[-800:])}</pre>",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass


async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: Message, user) -> None:
    """پست فورواردشده‌ی حاوی مدیا → کپی بدون هدر فوروارد (+ نسخه فایل برای ویدیو)."""
    has_media = any([msg.video, msg.photo, msg.audio, msg.document, msg.voice, msg.animation])
    if not has_media:
        return
    if not cooldown_check_or_notice(user.id, lambda txt: msg.reply_text(txt)):
        return
    try:
        sent = await msg.copy(chat_id=msg.chat_id)
        bump_stat("dl_channel")
        add_history(user.id, "channel", "copy", "forwarded media", "forward://")
        try:
            if sent is not None and hasattr(sent, "edit_reply_markup"):
                kb = None
                if msg.video:
                    tok = reg_token_add(kind="chanfile", owner=user.id, file_id=msg.video.file_id)
                    size = getattr(msg.video, "file_size", 0) or 0
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                        B(user.id, "as_file"),
                        callback_data=f"cf:{tok}" if size <= 20 * MB else "cf:no",
                    )]])
                elif msg.audio or msg.document or msg.voice:
                    tok = reg_token_add(kind="chanfile", owner=user.id,
                                        file_id=(msg.audio or msg.document or msg.voice).file_id)
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(B(user.id, "as_file"), callback_data=f"cf:{tok}")]])
                if kb:
                    try:
                        await sent.edit_reply_markup(reply_markup=kb)
                    except TelegramError:
                        pass
        except Exception:
            pass
    except TelegramError as exc:
        log_exc(exc, "handle_forwarded")
        await safe_reply(msg, L(user.id, "err_generic"))


async def submit_url(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, url: str) -> None:
    """نقطه‌ی ورود مشترک لینک (پیام مستقیم / تاریخچه / اینلاین): پروب → پلی‌لیست یا انتخاب کیفیت."""
    if not cooldown_check_or_notice(user.id, lambda txt: _send_html(context, chat_id, txt)):
        return
    platform = detect_platform(url)
    emoji = PLATFORM_EMOJI.get(platform, "🌐")

    # اسپاتیفای: فقط صوت، بدون منوی کیفیت
    if platform == "spotify":
        status = await _send_html(context, chat_id, L(user.id, "spot_processing"))
        meta = await spotify_track_info(url)
        query = (meta or {}).get("title") or ""
        if not query:
            await safe_delete(status)
            await _send_html(context, chat_id, L(user.id, "err_generic"))
            return
        await send_music_by_query(context, chat_id, f"{query} song",
                                  requester_id=user.id, status_msg=status,
                                  thumb_url=(meta or {}).get("thumb") or "",
                                  source_title=query, platform="spotify")
        return

    # ساند‌کلود: اول پروب (ست یا ترکِ تکی؟) — تک‌ترک بدون منو دانلود می‌شود
    if platform == "soundcloud":
        status = await _send_html(context, chat_id, L(user.id, "processing", emoji=emoji))
        try:
            probe = await asyncio.to_thread(probe_link_sync, url)
        except Exception as exc:
            await safe_delete(status)
            log_exc(exc, f"probe:{platform}")
            await _send_html(context, chat_id, friendly_dl_error(exc))
            await notify_log_channel(context.bot, f"probe:{platform}", f"user={user.id} url={url}\n{exc}")
            return
        if not probe.get("playlist"):
            await safe_delete(status)
            await start_download(context, chat_id, user, url, platform, quality="best")
            return
        # ست/پلی‌لیست → ادامه به مسیر عمومی زیر (status دوباره ساخته نمی‌شود؛ ادامه با همین)
    else:
        status = await _send_html(context, chat_id, L(user.id, "processing", emoji=emoji))

    try:
        probe = await asyncio.to_thread(probe_link_sync, url) if platform != "soundcloud" else probe
    except Exception as exc:
        await safe_delete(status)
        log_exc(exc, f"probe:{platform}")
        err_txt = friendly_dl_error(exc)
        await _send_html(context, chat_id, err_txt)
        await notify_log_channel(context.bot, f"probe:{platform}", f"user={user.id} url={url}\n{exc}")
        return
    await safe_delete(status)

    if probe.get("playlist"):
        entries = probe.get("entries") or []
        if not entries:
            await _send_html(context, chat_id, L(user.id, "err_generic"))
            return
        jtok = reg_token_add(kind="plist", owner=user.id, url=url, platform=platform,
                             count=len(entries), entries=entries)
        try:
            await context.bot.send_message(
                chat_id,
                L(user.id, "plist_prompt", count=len(entries)),
                parse_mode=ParseMode.HTML,
                reply_markup=playlist_keyboard(jtok, entries, user.id),
            )
        except TelegramError:
            pass
        return

    # تک‌محتوا → منوی کیفیت
    title = probe.get("title") or "…"
    ftok = reg_token_add(kind="quality", owner=user.id, url=url, platform=platform, title=title)
    try:
        await context.bot.send_message(
            chat_id,
            L(user.id, "quality_prompt", emoji=emoji, title=esc(title)),
            parse_mode=ParseMode.HTML,
            reply_markup=quality_keyboard(ftok, user.id),
            disable_web_page_preview=True,
        )
    except TelegramError:
        pass


async def _send_html(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> Optional[Message]:
    """ارسال پیام HTML امن (هرگز exception پخش نمی‌کند)."""
    try:
        return await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML,
                                              disable_web_page_preview=True)
    except TelegramError as exc:
        log.warning("_send_html failed: %s", exc)
        return None


async def start_download(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, url: str,
                         platform: str, quality: str = "best") -> None:
    """اجرای کامل یک دانلود: صف → دانلود → ارسال. از مسیر کیفیت/پلی‌لیست/اینلاین/تاریخچه صدا زده می‌شود."""
    emoji = PLATFORM_EMOJI.get(platform, "🌐")
    status = await context.bot.send_message(chat_id, L(user.id, "processing", emoji=emoji),
                                            parse_mode=ParseMode.HTML)
    in_queue = await queue_acquire(status, user.id)
    prog: Dict[str, Any] = {"done": False}
    monitor = asyncio.create_task(_monitor_progress(status, prog))
    try:
        try:
            await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
        except TelegramError:
            pass
        try:
            info, path = await asyncio.to_thread(dl_video_sync, url, prog, platform, True, quality)
        except Exception as exc:
            log_exc(exc, f"download:{platform}")
            prog["done"] = True
            try:
                await monitor
            except Exception:
                pass
            await safe_delete(status)
            await notify_log_channel(context.bot, f"download:{platform}", f"user={user.id} url={url}\n{exc}")
            await context.bot.send_message(chat_id, friendly_dl_error(exc),
                                           parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return

        prog["done"] = True
        try:
            await monitor
        except Exception:
            pass
        await safe_delete(status)

        await deliver_media(context, None, user, info, path, url, platform, emoji,
                            chat_id=chat_id, quality=quality)
    except Exception as exc:  # سپر نهایی
        prog["done"] = True
        log_exc(exc, "start_download")
        await safe_delete(status)
        await notify_log_channel(context.bot, "start_download", f"user={user.id} url={url}\n{exc}")
        try:
            await context.bot.send_message(chat_id, L(user.id, "err_generic"))
        except TelegramError:
            pass
    finally:
        if in_queue:
            queue_release()


async def on_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if msg is None or user is None:
        return
    upsert_user(user)

    ud = context.user_data
    pending: Optional[Dict[str, Any]] = ud.get("pending")

    # ۱) اگر pending داریم، فقط اگر واقعاً مربوط به ادمین است هندل کن
    #    در غیر این صورت پاکش کن تا مسیر جستجو بلاک نشود
    if pending and user.id in ADMIN_IDS and pending.get("act") in ("addc", "ban", "unban", "bcast1", "bcast2"):
        await handle_admin_input(update, context, pending)
        return
    if pending and (user.id not in ADMIN_IDS or pending.get("act") not in ("addc", "ban", "unban", "bcast1", "bcast2")):
        ud.pop("pending", None)
        pending = None

    # ۲) گیت‌ها: تعمیر / بن / جوین اجباری / کول‌داون
    if not await gate_check(update, context, user, msg):
        return

    # ۳) پست فورواردشده با مدیا → ذخیره‌ی محتوا
    if msg.forward_origin:
        await handle_forwarded(update, context, msg, user)
        return

    text = (msg.text or msg.caption or "").strip()

    # ۴) اگر متنی فرستاده شده که لینک ندارد → جستجوی موزیک
    if not URL_RE.search(text):
        if text and msg.text:
            # اگر در حالت pending دکمه‌ای منتظر انتخاب پلتفرم است
            if ud.get("pending", {}).get("act") == "search":
                platform = ud["pending"].get("platform")
                ud.pop("pending", None)
                await run_music_search(context, msg.chat_id, user, text, platform)
                return
            # در غیر این صورت: پیشنهاد جستجو
            ud["pending"] = {"act": "search", "query": text}
            shown = text if len(text) <= 300 else text[:300] + "…"
            await msg.reply_html(
                f"🔍 «<b>{esc(shown)}</b>»\n\n{L(user.id, 'search_ask')}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(B(user.id, "search_btn_sc"), callback_data="qry:sc"),
                    InlineKeyboardButton(B(user.id, "search_btn_yt"), callback_data="qry:yt"),
                ]]),
            )
        elif msg.text:
            await msg.reply_html(L(user.id, "hint", max=MAX_FILE_MB), reply_markup=back_kb())
        return

    # ۵) مسیر مشترک لینک
    url = URL_RE.search(text).group(0).rstrip(").,;،")
    await submit_url(context, msg.chat_id, user, url)


# ---------------------------------------------------------------------
# 🔍 جستجوی موزیک در SoundCloud/YouTube (متن ساده از کاربر)
# ---------------------------------------------------------------------


def search_sync(query: str, platform: str, limit: int = 8) -> List[Dict[str, Any]]:
    """جستجوی فقط متادیتا (بدون دانلود). platform: 'soundcloud' | 'youtube'."""
    search_prefix = "scsearch10" if platform == "soundcloud" else "ytsearch10"
    opts = _ydl_base_opts()
    opts.pop("playlist_items", None)
    opts.update({
        "extract_flat": "discard_in_response",
        "skip_download": True,
        "format": "best/worst",
        "default_search": search_prefix,
    })
    try:
        info = _extract_with_fallback(f"{search_prefix}:{query}", opts, download=False)
    except Exception as exc:
        log.warning("search_sync failed: %s", exc)
        return []
    entries = (info or {}).get("entries") or []
    out: List[Dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        url = e.get("url") or e.get("webpage_url") or ""
        if not url:
            continue
        if platform == "soundcloud" and "soundcloud.com" not in url:
            url = e.get("webpage_url") or url
        out.append({
            "id": (e.get("id") or "")[:40],
            "title": (e.get("title") or "?").strip(),
            "uploader": (e.get("uploader") or e.get("channel") or e.get("artist") or "").strip(),
            "duration": e.get("duration") or 0,
            "url": url,
        })
        if len(out) >= limit:
            break
    return out


async def run_music_search(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                           user, query: str, platform: str) -> None:
    """جستجو و نمایش لیست نتایج به‌صورت دکمه‌های اینلاین.

    اگر متن ورودی شبیه «متن ترانه» باشد، با موتورهای Genius/DuckDuckGo/lrclib
    نام آهنگ و خواننده استخراج می‌شود و نتایجِ آن بالای لیست پین می‌گردد؛
    اگر هیچ‌کدام جواب نداد و کاربر SoundCloud را انتخاب کرده بود، خودِ متن
    در یوتیوب هم جستجو می‌شود (یوتیوب متن ترانه را خیلی بهتر پیدا می‌کند).
    """
    shown = query if len(query) <= 120 else query[:120] + "…"
    notice = await context.bot.send_message(chat_id, f"🔍 «{esc(shown)}»…",
                                            parse_mode=ParseMode.HTML)

    # ۱) جستجوی مستقیم در پلتفرم انتخابی
    try:
        direct_results = await asyncio.to_thread(search_sync, query, platform, 8)
        for r in direct_results:
            r["engine"] = platform
    except Exception as exc:
        log_exc(exc, "run_music_search")
        direct_results = []

    # ۲) تلاش برای تشخیص نام آهنگ از متن ترانه (بدون نیاز به اسم خواننده)
    lyrics_hit: Optional[Dict[str, str]] = None
    lyrics_results: List[Dict[str, Any]] = []
    if len(query.strip()) >= 4:
        try:
            lyrics_hit = await search_song_by_lyrics(query)
        except Exception as exc:
            log_exc(exc, "lyrics-search")
        if lyrics_hit:
            refined = " - ".join(x for x in (lyrics_hit.get("artist"), lyrics_hit.get("title")) if x)
            try:
                lyrics_results = await asyncio.to_thread(search_sync, refined, platform, 3)
                for r in lyrics_results:
                    r["engine"] = platform
                # اگر پلتفرم انتخابی چیزی نداد، با همان نام در یوتیوب امتحان کن
                if not lyrics_results and platform == "soundcloud":
                    lyrics_results = await asyncio.to_thread(search_sync, refined, "youtube", 3)
                    for r in lyrics_results:
                        r["engine"] = "youtube"
            except Exception as exc:
                log_exc(exc, "search_sync(lyrics)")

    # ۳) متن شبیه ترانه بود ولی هیچ نتیجه‌ای نگرفتیم → یوتیوب با خودِ متن
    #    (یوتیوب متن ترانه را خیلی بهتر از SoundCloud می‌فهمد)
    if not (lyrics_results or direct_results) and looks_like_lyrics(query):
        tries: List[str] = []
        if platform != "youtube":
            tries.append(query)
        short = _clean_lyric_snippet(query, 80)
        if short and short != query:
            tries.append(short)
        for tq in tries:
            try:
                yt_fb = await asyncio.to_thread(search_sync, tq, "youtube", 8)
                for r in yt_fb:
                    r["engine"] = "youtube"
                if yt_fb:
                    direct_results = yt_fb
                    break
            except Exception as exc:
                log_exc(exc, "run_music_search(yt-fallback)")

    await safe_delete(notice)

    # ترکیب نتایج با حذف تکراری (بر اساس URL)
    combined: List[Dict[str, Any]] = []
    seen_urls: set = set()
    for r in (lyrics_results + direct_results):
        u = r.get("url") or ""
        if u and u not in seen_urls:
            seen_urls.add(u)
            combined.append(r)
        elif not u:
            combined.append(r)

    if not combined:
        await context.bot.send_message(chat_id, L(user.id, "search_none"))
        return

    rows: List[List[InlineKeyboardButton]] = []
    header_lines = [f"🔍 <b>{esc(shown)}</b>\n"]
    if lyrics_hit:
        hit_label = esc(lyrics_hit["title"])
        if lyrics_hit.get("artist"):
            hit_label += f" — {esc(lyrics_hit['artist'])}"
        header_lines.append(
            f"🔤 <i>تشخیص از متن ترانه ({esc(lyrics_hit.get('source') or '')}):</i> "
            f"<b>{hit_label}</b>\n"
        )
    engines = {r.get("engine") or platform for r in combined}
    if engines == {"soundcloud"}:
        header_lines.append("☁️ نتایج SoundCloud:\n")
    elif engines == {"youtube"}:
        header_lines.append("▶️ نتایج YouTube:\n")
    else:
        header_lines.append("🎵 نتایج:\n")
    header = "\n".join(header_lines)

    for i, r in enumerate(combined, 1):
        title = clean_title(r["title"])
        if r.get("uploader") and r["uploader"].lower() not in title.lower():
            title = f"{title} — {r['uploader']}"
        title = title[:60]
        dur = fmt_dur(r.get("duration")) if r.get("duration") else ""
        label = f"{i}. {title}" + (f"  ({dur})" if dur else "")
        eng = r.get("engine") or platform
        prefix = "scs" if eng == "soundcloud" else "yt"
        tok = reg_token_add(kind=prefix, owner=user.id, url=r["url"],
                            title=r["title"], platform=eng)
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}:{tok}")])
    try:
        await context.bot.send_message(chat_id, header, parse_mode=ParseMode.HTML,
                                       reply_markup=InlineKeyboardMarkup(rows))
    except TelegramError as exc:
        log_exc(exc, "search-results")
        await context.bot.send_message(chat_id, L(user.id, "err_generic"))


async def deliver_media(
    context: ContextTypes.DEFAULT_TYPE,
    src_msg: Optional[Message],
    user,
    info: Dict[str, Any],
    path: Path,
    url: str,
    platform: str,
    emoji: str,
    chat_id: Optional[int] = None,
    quality: str = "best",
) -> None:
    cid = chat_id or (src_msg.chat_id if src_msg else user.id)
    size = path.stat().st_size
    if size > MAX_FILE_MB * MB:
        try:
            await context.bot.send_message(
                cid,
                f"📦 حجم فایل ({fmt_size(size)}) بیشتر از حد مجاز تلگرام ({MAX_FILE_MB}MB) است!",
            )
        except TelegramError:
            pass
        return

    title = info.get("title") or path.stem
    tok = reg_token_add(kind="video", owner=user.id, path=str(path), title=title, url=url)

    async def _note(txt: str) -> None:
        try:
            await context.bot.send_message(cid, txt)
        except TelegramError:
            pass

    caption = (
        f"{emoji} <b>{esc(title)}</b>\n"
        f"📦 حجم: <code>{fmt_size(size)}</code>\n"
        f"⏱ مدت: <code>{fmt_dur(info.get('duration'))}</code>\n"
        f"🔗 منبع: {PLATFORM_FA.get(platform, 'سایت')}\n"
        f"👤 {user.mention_html()}"
    )
    kb = video_keyboard(tok, user.id)
    suffix = path.suffix.lower()
    sent_any = False

    try:
        await context.bot.send_chat_action(cid, ChatAction.UPLOAD_VIDEO)
    except TelegramError:
        pass

    if suffix in IMAGE_EXTS:
        try:
            with path.open("rb") as fimg:
                await context.bot.send_photo(
                    cid, photo=fimg, caption=caption,
                    parse_mode=ParseMode.HTML, reply_markup=kb,
                    read_timeout=UPLOAD_TIMEOUT, write_timeout=UPLOAD_TIMEOUT,
                )
            sent_any = True
        except TelegramError as exc:
            log_exc(exc, "send_photo")
    elif suffix in AUDIO_EXTS or (info.get("ext") or "").lower() in {"mp3", "m4a", "opus", "ogg"}:
        # فایل صوتی (ساند‌کلود / فقط صدا) → send_audio با تگ ID3
        a_title = clean_title(info.get("track") or info.get("title") or path.stem)
        a_artist = clean_title(info.get("artist") or "") or clean_title(info.get("uploader") or "")
        cap_lines = [f"{emoji} <b>{esc(a_title)}</b>"]
        if a_artist:
            cap_lines.append(f"🎤 {esc(a_artist)}")
        cap_lines.append(f"📦 حجم: <code>{fmt_size(size)}</code>")
        cap_lines.append(f"🔗 منبع: {PLATFORM_FA.get(platform, 'سایت')}")
        cap_lines.append(f"👤 {user.mention_html()}")
        audio_caption = "\n".join(cap_lines)
        thumb_p = await fetch_thumb(info.get("thumbnail") or "")
        tag_mp3(path, a_title, a_artist,
                album=clean_title(info.get("album") or ""),
                year=str(info.get("release_year") or info.get("upload_date") or "")[:4],
                cover_path=thumb_p)
        thumb_handle = open(thumb_p, "rb") if thumb_p else None
        try:
            with path.open("rb") as faud:
                await context.bot.send_audio(
                    cid, audio=faud,
                    title=(a_title or "Music")[:64],
                    performer=(a_artist[:64] if a_artist else None),
                    duration=int(info.get("duration") or 0) or None,
                    thumbnail=thumb_handle,
                    caption=audio_caption, parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                    read_timeout=UPLOAD_TIMEOUT, write_timeout=UPLOAD_TIMEOUT,
                )
            sent_any = True
            add_history(user.id, platform, "audio", a_title, url)
        except TelegramError as exc:
            log_exc(exc, "send_audio")
            await _note(L(user.id, "err_generic"))
        finally:
            if thumb_handle:
                thumb_handle.close()
    else:
        try:
            with path.open("rb") as fvid:
                await context.bot.send_video(
                    cid, video=fvid, caption=caption,
                    parse_mode=ParseMode.HTML,
                    width=info.get("width"), height=info.get("height"),
                    duration=int(info.get("duration") or 0) or None,
                    supports_streaming=True, reply_markup=kb,
                    read_timeout=UPLOAD_TIMEOUT, write_timeout=UPLOAD_TIMEOUT,
                )
            sent_any = True
            add_history(user.id, platform, quality, title, url)
        except TelegramError as exc:
            log_exc(exc, "send_video→document")
            try:
                with path.open("rb") as fdoc:
                    await context.bot.send_document(
                        cid, document=fdoc,
                        caption=f"📄 <b>{esc(title)}</b>",
                        parse_mode=ParseMode.HTML, reply_markup=kb,
                        read_timeout=UPLOAD_TIMEOUT, write_timeout=UPLOAD_TIMEOUT,
                    )
                sent_any = True
                add_history(user.id, platform, "file", title, url)
            except TelegramError as exc2:
                log_exc(exc2, "send_document")
                await _note(L(user.id, "err_generic"))

    if sent_any:
        bump_stat(f"dl_{platform}")
        # 🤖 شزام خودکار: اگر در پنل فعال باشد، بدون کلیک شناسایی کن
        if auto_shazam_on() and suffix not in AUDIO_EXTS and suffix not in IMAGE_EXTS:
            ent = REGISTRY.get(tok) or {}
            _spawn(run_bg(do_song_search(context, cid, ent, user)))


# ---------------------------------------------------------------------
# 🎧 ارسال موزیک کامل (جستجو در یوتیوب + دانلود MP3)
# ---------------------------------------------------------------------


async def send_music_by_query(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    query: str,
    requester_id: int,
    status_msg: Optional[Message] = None,
    thumb_url: str = "",
    source_title: str = "",
    platform: str = "youtube",
) -> None:
    """جستجو + دانلود MP3 + درج تگ/کاور + ارسال. (مسیر موزیکِ همه‌ی پلتفرم‌ها)"""
    status = status_msg
    audio_path: Optional[Path] = None
    thumb_path: Optional[Path] = None
    try:
        if status is None:
            status = await context.bot.send_message(chat_id, L(requester_id, "mus_search"),
                                                    parse_mode=ParseMode.HTML)
        # انتخاب موتور جستجو بر اساس پلتفرم
        search_prefix = "scsearch1" if platform == "soundcloud" else "ytsearch1"
        info, audio_path = await asyncio.to_thread(dl_audio_sync, query, True, search_prefix)

        size = audio_path.stat().st_size
        if size > MAX_FILE_MB * MB:
            await context.bot.send_message(
                chat_id,
                f"📦 حجم موزیک ({fmt_size(size)}) بیشتر از حد مجاز تلگرام است!",
            )
            return

        a_title = clean_title(source_title or info.get("track") or info.get("title") or query)
        a_artist = clean_title(info.get("artist") or "") or clean_title(info.get("uploader") or "")
        thumb_path = await fetch_thumb(thumb_url or (info.get("thumbnail") or ""))

        # 🏷 درج تگ و کاور داخل خود فایل MP3
        tag_mp3(
            audio_path, a_title, a_artist,
            album=clean_title(info.get("album") or ""),
            year=str(info.get("release_year") or info.get("upload_date") or "")[:4],
            genre=clean_title((info.get("genres") or [""])[0] if isinstance(info.get("genres"), list) else ""),
            cover_path=thumb_path,
        )

        caption = f"🎧 <b>{esc(a_title)}</b>"
        if a_artist:
            caption += f"\n🎤 {esc(a_artist)}"
        caption += f"\n📦 {fmt_size(size)} • MP3 {AUDIO_BITRATE}k"

        thumb_handle = open(thumb_path, "rb") if thumb_path else None
        try:
            with audio_path.open("rb") as fa:
                await context.bot.send_audio(
                    chat_id,
                    audio=fa,
                    title=(a_title or "Music")[:64],
                    performer=(a_artist[:64] if a_artist else None),
                    duration=int(info.get("duration") or 0) or None,
                    thumbnail=thumb_handle,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    read_timeout=UPLOAD_TIMEOUT,
                    write_timeout=UPLOAD_TIMEOUT,
                )
        finally:
            if thumb_handle:
                thumb_handle.close()
        bump_stat("music_sent")
        bump_stat(f"dl_{platform}")
        add_history(requester_id, platform, "music", a_title, f"search://{query}")
    except Exception as exc:
        log_exc(exc, "send_music_by_query")
        # اگر SoundCloud چیزی پیدا نکرد، پیام دوستانه‌تر نشان بده
        if platform == "soundcloud" and isinstance(exc, RuntimeError) and "موزیکی پیدا نشد" in str(exc):
            note = L(requester_id, "sc_none")
        else:
            note = friendly_dl_error(exc) if isinstance(exc, yt_dlp.utils.DownloadError) else L(requester_id, "err_generic")
        await notify_log_channel(context.bot, "send_music_by_query", f"user={requester_id} q={query}\n{exc}")
        try:
            await context.bot.send_message(chat_id, note, parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
    finally:
        await safe_delete(status)
        if audio_path:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass
        if thumb_path:
            try:
                thumb_path.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------
# 🔍 شناسایی آهنگ با Shazam
# ---------------------------------------------------------------------


async def do_song_search(context: ContextTypes.DEFAULT_TYPE, chat_id: int, ent: Dict[str, Any], user) -> None:
    video_path = Path(ent.get("path") or "")
    notice: Optional[Message] = None
    snippet: Optional[Path] = None
    ent["busy"] = True
    try:
        if not video_path.exists():
            await context.bot.send_message(chat_id, L(user.id, "err_generic"))
            return
        notice = await context.bot.send_message(chat_id, L(user.id, "searching_song"), parse_mode=ParseMode.HTML)
        try:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        except TelegramError:
            pass

        snippet = await extract_audio_snippet(video_path)
        result = await recognize_file(snippet)
        trk = parse_shazam_result(result)

        if not trk:
            await context.bot.send_message(chat_id, L(user.id, "notfound"))
            return

        qtok = reg_token_add(
            kind="track",
            owner=user.id,
            query=f"{trk['artist']} {trk['title']}".strip(),
            artist=trk["artist"],
            title=trk["title"],
        )
        lines = [f"🎧 <b>{esc(trk['title'])}</b>"]
        if trk["artist"]:
            lines.append(f"🎤 هنرمند: {esc(trk['artist'])}")
        if trk["album"]:
            lines.append(f"💿 آلبوم: {esc(trk['album'])}")
        tags = []
        if trk["year"]:
            tags.append(f"📅 {esc(trk['year'])}")
        if trk["genre"]:
            tags.append(f"🏷 {esc(trk['genre'])}")
        if tags:
            lines.append("   ".join(tags))
        if trk["label"]:
            lines.append(f"🏢 ناشر: {esc(trk['label'])}")
        if trk["shazam_url"]:
            lines.append(f"\n🔗 <a href=\"{trk['shazam_url']}\">مشاهده در Shazam</a>")
        caption = "\n".join(lines)
        kb = track_keyboard(qtok, trk.get("listen_url") or "", user.id)

        sent = False
        if trk["cover"]:
            try:
                await context.bot.send_photo(
                    chat_id, photo=trk["cover"], caption=caption,
                    parse_mode=ParseMode.HTML, reply_markup=kb,
                )
                sent = True
            except (TelegramError, BadRequest) as exc:
                log_exc(exc, "send_photo(shazam)")
        if not sent:
            await context.bot.send_message(chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=kb)
        bump_stat("shazam_ok")
    except Exception as exc:
        log_exc(exc, "do_song_search")
        await notify_log_channel(context.bot, "do_song_search", f"user={user.id}\n{exc}")
        try:
            await context.bot.send_message(chat_id, L(user.id, "err_generic"))
        except TelegramError:
            pass
    finally:
        ent["busy"] = False
        await safe_delete(notice)
        if snippet:
            try:
                snippet.unlink(missing_ok=True)
            except OSError:
                pass


# =====================================================================
# 🔁 روتر CallbackQuery ها
# =====================================================================


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q is None:
        return
    data = q.data or ""
    user = q.from_user
    upsert_user(user)
    try:
        await q.answer()
    except TelegramError:
        pass

    # ---------- گیت‌های عمومی (غیر ادمین) ----------
    if not data.startswith("adm:") and user.id not in ADMIN_IDS:
        if maintenance_on():
            try:
                await q.answer("🛠 " + STRINGS["maint"]["fa"], show_alert=True)
            except TelegramError:
                pass
            return
        if is_banned_uid(user.id):
            return

    # ---------- جوین اجباری ----------
    if data == "join:chk":
        JOIN_OK.pop(user.id, None)
        missing = await get_missing_channels(context, user.id)
        if missing:
            try:
                await q.edit_message_text(L(user.id, "join"), reply_markup=join_keyboard(missing, user.id))
            except TelegramError:
                pass
        else:
            await send_welcome(q.message, context, user)
        return

    # ---------- منو ----------
    if data.startswith("menu:"):
        sub = data.split(":", 1)[1]
        if sub == "back":
            await send_welcome(q.message, context, user)
            return
        if sub == "lang":
            new_lang = "en" if get_lang(user.id) == "fa" else "fa"
            set_lang(user.id, new_lang)
            await send_welcome(q.message, context, user)  # خوش‌آمد با زبان جدید + دکمه بازگشت
            return
        texts = {
            "dl": ("🎬 <b>دانلود</b>\n\nلینک (یوتیوب / اینستاگرام / تیک‌تاک / ساند‌کلود / اسپاتیفای) رو بفرست، یا پست کانال‌ها رو فوروارد کن! 📥",
                   "🎬 <b>Download</b>\n\nSend a link (YouTube / Instagram / TikTok / SoundCloud / Spotify), or forward a channel post! 📥"),
            "song": ("🎧 <b>شناسایی موزیک</b>\n\nاول لینک ویدیو رو بفرست؛ بعد روی «🎵 شناسایی آهنگ این ویدیو» بزن تا با Shazam پیدا کنم!",
                     "🎧 <b>Music finder</b>\n\nFirst send a video link; then tap «🎵 Identify this song» and I'll find it with Shazam!"),
            "help": (L(user.id, "hint", max=MAX_FILE_MB), L(user.id, "hint", max=MAX_FILE_MB)),
        }
        item = texts.get(sub)
        lang = get_lang(user.id)
        idx = 0 if lang == "fa" else 1
        if item:
            try:
                await q.edit_message_text(item[idx], parse_mode=ParseMode.HTML,
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton(B(user.id, "back"), callback_data="menu:back"),
                                              InlineKeyboardButton(B(user.id, "lang"), callback_data="menu:lang"),
                                          ]]))
            except TelegramError:
                pass
        return

    # ---------- تاریخچه از منو ----------
    if data == "cmd:hist":
        chat_id = q.message.chat_id if isinstance(q.message, Message) and hasattr(q.message, "chat_id") else user.id
        rows_db = get_history(user.id)
        if not rows_db:
            try:
                await context.bot.send_message(chat_id, L(user.id, "hist_empty"))
            except TelegramError:
                pass
            return
        try:
            await context.bot.send_message(chat_id, L(user.id, "hist_header"),
                                           parse_mode=ParseMode.HTML,
                                           reply_markup=history_keyboard(rows_db, user.id))
        except TelegramError:
            pass
        return

    # ---------- توکن‌های ساده (s/v/q/ly/pv/rg/f/pl/cf/iv/rh) ----------
    # شاخه‌ی ویژه: qry: از pending استفاده می‌کند، نه REGISTRY
    if data == "qry:sc" or data == "qry:yt":
        platform = "soundcloud" if data == "qry:sc" else "youtube"
        query = (context.user_data or {}).get("pending", {}).get("query") or ""
        chat_id = user.id
        if not query:
            try:
                await q.answer(L(user.id, "search_empty"), show_alert=True)
            except TelegramError:
                pass
            return
        try:
            await run_music_search(context, chat_id, user, query, platform)
        except Exception as exc:
            log_exc(exc, "qry_handler")
            try:
                await q.answer(L(user.id, "err_generic"), show_alert=True)
            except TelegramError:
                pass
        return

    parts = data.split(":")
    head = parts[0] if parts else ""

    simple_heads = ("s:", "sc:", "v:", "q:", "ly:", "pv:", "rg:", "cf:", "f:", "pl:", "rh:",
                   "scs:", "yt:")
    matched = next((h for h in simple_heads if data.startswith(h)), None)
    if matched:
        tok = data[len(matched):]
        # f: و pl: شناسه‌ی اضافه دارند → فقط بخش توکن
        if matched in ("f:", "pl:"):
            seg = tok.split(":")
            tok = seg[0]
        ent = REGISTRY.get(tok)
        expired_msg = {
            "fa": "⌛️ این دکمه منقضی شده! لطفاً لینک را دوباره بفرست.",
            "en": "⌛️ This button expired! Please send the link again.",
        }[get_lang(user.id)]
        if not ent or ent.get("exp", 0) < time.time():
            REGISTRY.pop(tok, None)
            try:
                await q.answer(expired_msg, show_alert=True)
            except TelegramError:
                pass
            return
        if user.id != ent.get("owner") and user.id not in ADMIN_IDS:
            try:
                await q.answer("🚫 This button belongs to another user!", show_alert=True)
            except TelegramError:
                pass
            return

        chat_id = q.message.chat_id if isinstance(q.message, Message) and hasattr(q.message, "chat_id") else user.id

        # --- شناسایی آهنگ ---
        if matched == "s:":
            if ent.get("kind") != "video":
                return
            if ent.get("busy"):
                return
            if not Path(ent.get("path") or "").exists():
                try:
                    await q.answer("🗑 File purged from server — please resend the link!", show_alert=True)
                except TelegramError:
                    pass
                return
            await do_song_search(context, chat_id, ent, user)
            return

        # --- دانلود نسخه موزیک از ویدیو ---
        if matched == "v:":
            if ent.get("kind") != "video":
                return
            query = clean_title(ent.get("title") or "") or ent.get("title") or "music"
            await send_music_by_query(context, chat_id, f"{query} song", user.id)
            return

        # --- دانلود موزیک نتیجه‌ی شزام ---
        if matched == "q:":
            if ent.get("kind") != "track":
                return
            await send_music_by_query(context, chat_id, f"{ent.get('query')} song", user.id)
            return

        # --- دانلود از SoundCloud (جایگزین یوتیوب) ---
        if matched == "sc:":
            if ent.get("kind") != "track":
                return
            await send_music_by_query(context, chat_id, f"{ent.get('query')} song", user.id,
                                       platform="soundcloud")
            return

        # --- دانلود یک نتیجه‌ی انتخاب‌شده از جستجو ---
        if matched in ("scs:", "yt:"):
            if ent.get("kind") not in ("scs", "yt"):
                return
            url = ent.get("url") or ""
            platform = ent.get("platform") or ("soundcloud" if matched == "scs:" else "youtube")
            title = ent.get("title") or ""
            await send_music_by_query(context, chat_id, url, user.id,
                                       source_title=title, platform=platform)
            return

        # --- متن ترانه ---
        if matched == "ly:":
            if ent.get("kind") != "track":
                return
            artist = ent.get("artist") or ""
            title = ent.get("title") or ent.get("query") or ""
            notice = await context.bot.send_message(chat_id, "📝 Lyrics…")
            text = await fetch_lyrics(artist, title)
            await safe_delete(notice)
            if not text:
                await context.bot.send_message(chat_id, L(user.id, "lyrics_none"))
                return
            header = f"📝 <b>{esc(title)}</b>"
            if len(text) > 3500:
                fp = DOWNLOAD_DIR / f"lyr_{secrets.token_hex(3)}.txt"
                fp.write_text(f"{artist} - {title}\n\n{text}", encoding="utf-8")
                with fp.open("rb") as ft:
                    await context.bot.send_document(chat_id, document=ft, caption=header,
                                                    parse_mode=ParseMode.HTML)
                try:
                    fp.unlink()
                except OSError:
                    pass
            else:
                await context.bot.send_message(
                    chat_id, f"{header}\n\n<pre>{esc(text)}</pre>",
                    parse_mode=ParseMode.HTML,
                )
            return

        # --- پیش‌نمایش ۳۰ ثانیه‌ای (ویس) ---
        if matched == "pv:":
            if ent.get("kind") != "track":
                return
            _spawn(run_bg(make_preview_or_ringtone(
                context, chat_id, ent.get("query") or "", user.id, mode="preview")))
            return

        # --- رینگتون ---
        if matched == "rg:":
            if ent.get("kind") != "track":
                return
            _spawn(run_bg(make_preview_or_ringtone(
                context, chat_id, ent.get("query") or "", user.id, mode="ringtone")))
            return

        # --- انتخاب کیفیت → شروع دانلود ---
        if matched == "f:":
            extra = data.split(":")[2] if data.count(":") >= 2 else "best"
            url = ent.get("url") or ""
            platform = ent.get("platform") or detect_platform(url)
            await start_download(context, chat_id, user, url, platform, quality=extra)
            return

        # --- پلی‌لیست: یک آیتم یا همه ---
        if matched == "pl:":
            tail = data.split(":", 2)[2] if data.count(":") >= 2 else ""
            entries = ent.get("entries") or []
            platform = ent.get("platform") or "other"
            if tail == "all":
                total = min(len(entries), PLIST_MAX_ITEMS)
                await context.bot.send_message(chat_id, f"⬇️ {total} items queued…")
                for i, e in enumerate(entries[:PLIST_MAX_ITEMS], 1):
                    e_url = e.get("url") or ""
                    if not e_url:
                        continue
                    await start_download(context, chat_id, user, e_url, platform, quality="best")
                    await asyncio.sleep(1.5)
                return
            try:
                idx_i = int(tail)
                entry = entries[idx_i]
            except (ValueError, IndexError):
                return
            e_url = entry.get("url") or ""
            if not e_url:
                return
            await start_download(context, chat_id, user, e_url, platform, quality="best")
            return

        # --- ارسال فوروارد به‌صورت فایل ---
        if matched == "cf:":
            if tok == "no":
                try:
                    await q.answer(L(user.id, "fwd_too_big"), show_alert=True)
                except TelegramError:
                    pass
                return
            file_id = ent.get("file_id") or ""
            if not file_id:
                return
            notice = await context.bot.send_message(chat_id, L(user.id, "file_sending"))
            local: Optional[Path] = None
            try:
                tg_file = await context.bot.get_file(file_id)
                local = DOWNLOAD_DIR / f"fwd_{secrets.token_hex(4)}_{Path(tg_file.file_path or 'f.bin').name}"
                await tg_file.download_to_drive(custom_path=str(local))
                with local.open("rb") as fd:
                    await context.bot.send_document(chat_id, document=fd,
                                                    caption="📨 📁", read_timeout=UPLOAD_TIMEOUT,
                                                    write_timeout=UPLOAD_TIMEOUT)
                bump_stat("dl_channel")
            except TelegramError as exc:
                log_exc(exc, "chanfile")
                await context.bot.send_message(chat_id, L(user.id, "fwd_too_big"))
            finally:
                await safe_delete(notice)
                if local is not None:
                    try:
                        local.unlink(missing_ok=True)
                    except OSError:
                        pass
            return

        # --- دریافت مجدد از تاریخچه ---
        if matched == "rh:":
            url2 = ent.get("url") or ""
            kind2 = ent.get("htype") or ent.get("kind") or ""
            if kind2 == "music" and str(url2).startswith("search://"):
                await send_music_by_query(context, chat_id, str(url2).replace("search://", ""), user.id)
                return
            if not URL_RE.search(url2):
                return
            try:
                await submit_url(context, chat_id, user, URL_RE.search(url2).group(0))
            except Exception as exc:
                log_exc(exc, "history-replay")
            return

    # ---------- دانلود سریع از نتایج اینلاین (گیت جوین؛ کول‌داون در submit_url) ----------
    if data.startswith("iv:"):
        vid = data[3:]
        url = f"https://www.youtube.com/watch?v={vid}"
        chat_id = q.message.chat_id if isinstance(q.message, Message) and hasattr(q.message, "chat_id") else user.id
        # گیت جوین اجباری — چون اینلاین از خارجِ /start می‌آید
        missing = await get_missing_channels(context, user.id)
        if missing:
            try:
                await context.bot.send_message(chat_id, L(user.id, "join"),
                                               parse_mode=ParseMode.HTML,
                                               reply_markup=join_keyboard(missing, user.id))
            except TelegramError:
                pass
            return
        try:
            await submit_url(context, chat_id, user, url)
        except Exception as exc:
            log_exc(exc, "inline-dl")
        return

    # ---------- پنل ادمین ----------
    if data.startswith("adm:"):
        if user.id not in ADMIN_IDS:
            try:
                await q.answer("⛔️ فقط مدیر!", show_alert=True)
            except TelegramError:
                pass
            return
        await admin_callback(update, context, data)


async def make_preview_or_ringtone(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                                   query: str, uid: int, mode: str = "preview") -> None:
    """دانلود سریع بهترین صدا و برش ۳۰ ثانیه: preview → ویس (با fallback به MP3) | ringtone → MP3."""
    audio_path: Optional[Path] = None
    out_path: Optional[Path] = None
    status: Optional[Message] = None
    ffmpeg_missing = False
    try:
        status = await context.bot.send_message(chat_id, L(uid, "prev_making" if mode == "preview" else "ring_making"))
        info, audio_path = await asyncio.to_thread(dl_audio_sync, query)
        dur = int(info.get("duration") or 0) or 60
        title = clean_title(info.get("track") or info.get("title") or query)
        artist = clean_title(info.get("artist") or "") or clean_title(info.get("uploader") or "")

        # تلاش اول/دوم: برای preview اوپس (ویس) و در نبود libopus → mp3
        attempts: List[Tuple[List[str], str]] = []
        if mode == "preview":
            attempts.append((["-t", "30", "-c:a", "libopus", "-b:a", "64k"], ".ogg"))
            attempts.append((["-t", "30", "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE + "k"], ".mp3"))
        else:
            start = max(0, int(dur * 0.30))
            attempts.append((
                ["-ss", str(start), "-t", "30",
                 "-af", "afade=t=in:d=1,afade=t=out:st=28.5:d=1.5",
                 "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE + "k"],
                ".mp3",
            ))

        ok = False
        for extra_args, ext in attempts:
            out_path = DOWNLOAD_DIR / f"{mode[:2]}_{secrets.token_hex(4)}{ext}"
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-i", str(audio_path)] + list(extra_args) + [str(out_path)]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            except FileNotFoundError:
                ffmpeg_missing = True
                raise RuntimeError("ffmpeg not installed")
            try:
                await asyncio.wait_for(proc.communicate(), timeout=180)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                continue
            if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 2048:
                ok = True
                break
            # تلاش بعدی
        if not ok or out_path is None:
            raise RuntimeError("audio cut failed")

        if mode == "preview" and out_path.suffix == ".ogg":
            with out_path.open("rb") as fv:
                await context.bot.send_voice(
                    chat_id, voice=fv, caption=f"⏱ {esc(title)}",
                    parse_mode=ParseMode.HTML, duration=30,
                    read_timeout=UPLOAD_TIMEOUT, write_timeout=UPLOAD_TIMEOUT)
        else:
            label = f"{title} [Ringtone]" if mode == "ringtone" else f"{title} [Preview]"
            tag_mp3(out_path, label, artist)
            with out_path.open("rb") as fa:
                await context.bot.send_audio(
                    chat_id, audio=fa, title=label[:64],
                    performer=(artist[:64] if artist else None), duration=30,
                    caption="🔔" if mode == "ringtone" else "⏱",
                    read_timeout=UPLOAD_TIMEOUT, write_timeout=UPLOAD_TIMEOUT)
        bump_stat("ringtone" if mode == "ringtone" else "preview")
    except Exception as exc:
        log_exc(exc, f"make_{mode}")
        if ffmpeg_missing:
            await notify_log_channel(context.bot, "ffmpeg-missing", str(exc))
        try:
            await context.bot.send_message(chat_id, L(uid, "err_generic"))
        except TelegramError:
            pass
    finally:
        await safe_delete(status)
        for p in (audio_path, out_path):
            if p:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass


# =====================================================================
# 🛠 پنل ادمین
# =====================================================================


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    global BCAST_RUNNING
    q = update.callback_query
    ud = context.user_data

    if data == "adm:panel":
        try:
            await q.edit_message_text(ADM_PANEL_TXT, parse_mode=ParseMode.HTML, reply_markup=admin_panel_kb())
        except TelegramError:
            pass
        return

    if data in ("adm:mnt", "adm:queue", "adm:ashz"):
        key = {"adm:mnt": "maintenance", "adm:queue": "queue_on", "adm:ashz": "auto_shazam"}[data]
        now_on = toggle_setting(key)
        if key == "maintenance" and not now_on:
            JOIN_OK.clear()
        try:
            await q.answer("✅ روشن شد." if now_on else "⛔️ خاموش شد.")
        except TelegramError:
            pass
        try:
            await q.edit_message_text(ADM_PANEL_TXT, parse_mode=ParseMode.HTML, reply_markup=admin_panel_kb())
        except TelegramError:
            pass
        return

    if data == "adm:stats":
        total = db_one("SELECT COUNT(*) FROM users")[0]
        banned_n = db_one("SELECT COUNT(*) FROM users WHERE banned = 1")[0]
        today = datetime.now().strftime("%Y-%m-%d")
        new_today = db_one("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (today + "%",))[0]
        active_today = db_one("SELECT COUNT(*) FROM users WHERE last_seen LIKE ?", (today + "%",))[0]
        dl_rows = {
            "▶️ یوتیوب": stat_value("dl_youtube"),
            "📸 اینستاگرام": stat_value("dl_instagram"),
            "🎵 تیک‌تاک": stat_value("dl_tiktok"),
            "☁️ ساند‌کلود": stat_value("dl_soundcloud"),
            "🟢 اسپاتیفای": stat_value("dl_spotify"),
            "📨 کانال": stat_value("dl_channel"),
            "🌐 سایر": stat_value("dl_other"),
        }
        dl_txt = "\n".join(f"   • {k}: <b>{v}</b>" for k, v in dl_rows.items())
        txt = (
            f"📊 <b>آمار ربات</b>\n\n"
            f"👥 کل کاربران: <b>{total}</b>\n"
            f"🆕 امروز: <b>{new_today}</b>\n"
            f"🟢 فعال امروز: <b>{active_today}</b>\n"
            f"🚫 بن‌شده: <b>{banned_n}</b>\n\n"
            f"📥 <b>دانلود ویدیوها:</b>\n{dl_txt}\n"
            f"🔍 شناسایی موفق Shazam: <b>{stat_value('shazam_ok')}</b>\n"
            f"🎧 موزیک ارسال‌شده: <b>{stat_value('music_sent')}</b>"
        )
        try:
            await q.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=back_kb("adm:panel"))
        except TelegramError:
            pass
        return

    if data == "adm:srv":
        up = int(time.time() - PROCESS_START)
        h, rem = divmod(up, 3600)
        m, _s = divmod(rem, 60)
        files_n = 0
        files_size = 0
        try:
            for f in DOWNLOAD_DIR.glob("*"):
                if f.is_file():
                    files_n += 1
                    files_size += f.stat().st_size
        except OSError:
            pass
        disk_total, disk_used, disk_free = shutil.disk_usage(DOWNLOAD_DIR.anchor or ".")
        cpu_line = ram_line = ""
        try:
            import psutil  # optional
            cpu_line = f"\n🧠 CPU: <b>{psutil.cpu_percent(interval=0.2):.0f}%</b>"
            vm = psutil.virtual_memory()
            ram_line = f"\n💾 RAM: <b>{fmt_size(vm.used)}</b> / {fmt_size(vm.total)} ({vm.percent:.0f}%)"
        except ImportError:
            pass
        cookies_state = "✅ موجود" if COOKIES_FILE.exists() else "❌ پیدا نشد"
        ffmpeg_state = "✅ نصب" if shutil.which("ffmpeg") else "❌ نصب نیست!"
        ch_count = len(get_force_channels())
        mutag = "✅" if HAS_MUTAGEN else "❌ (pip install mutagen)"
        q_on = "🟢 روشن" if queue_on() else "🔴 خاموش"
        mnt_on = "🟢 روشن" if maintenance_on() else "🔴 خاموش"
        az_on = "🟢 روشن" if auto_shazam_on() else "🔴 خاموش"
        txt = (
            f"🖥 <b>وضعیت سرور</b>\n\n"
            f"⏱ آپتایم: <b>{h}ساعت و {m}دقیقه</b>\n"
            f"📁 فایل‌های موقت: <b>{files_n}</b> ({fmt_size(files_size)})\n"
            f"🗄 دیسک: <b>{fmt_size(disk_used)}</b> مصرف / {fmt_size(disk_free)} آزاد\n"
            f"{cpu_line}{ram_line}\n"
            f"ffmpeg: {ffmpeg_state}   |   mutagen: {mutag}\n"
            f"cookies.txt: {cookies_state} (<code>{esc(COOKIES_FILE.name)}</code>)\n"
            f"🔒 کانال‌های اجباری: <b>{ch_count}</b>\n"
            f"🛠 حالت تعمیر: {mnt_on}\n"
            f"🕒 صف دانلود: {q_on} (ظرفیت همزمان: {MAX_CONCURRENT_DL}، در انتظار: {_DL_WAITING})\n"
            f"🤖 شزام خودکار: {az_on}\n"
            f"📨 کانال لاگ خطا: <code>{esc(LOG_CHANNEL) if LOG_CHANNEL else '— تنظیم نشده —'}</code>"
        )
        try:
            await q.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=back_kb("adm:panel"))
        except TelegramError:
            pass
        return

    if data == "adm:chans":
        await render_channels(q)
        return

    if data.startswith("adm:rmc:"):
        try:
            ref = base64.b64decode(data.split(":", 2)[2]).decode("utf-8")
        except Exception:
            ref = ""
        if ref:
            ok = remove_force_channel(ref)
            try:
                await q.answer("✅ حذف شد." if ok else "⚠️ پیدا نشد.")
            except TelegramError:
                pass
        await render_channels(q)
        return

    if data == "adm:addc":
        ud["pending"] = {"act": "addc"}
        try:
            await q.message.reply_html(
                "➕ <b>افزودن کانال جوین اجباری</b>\n\n"
                "آیدی عمومی (@channel) یا آیدی عددی (-100...) کانال را بفرست.\n"
                "⚠️ ربات باید در آن کانال <b>ادمین</b> باشد.\n\n"
                "❌ برای لغو: /cancel"
            )
        except TelegramError:
            pass
        return

    if data == "adm:ban":
        ud["pending"] = {"act": "ban"}
        try:
            await q.message.reply_html("🚫 <b>بن کاربر</b>\n\n🔢 <b>آیدی عددی</b> کاربر را بفرست.\n❌ لغو: /cancel")
        except TelegramError:
            pass
        return

    if data == "adm:unban":
        ud["pending"] = {"act": "unban"}
        try:
            await q.message.reply_html("♻️ <b>رفع بن</b>\n\n🔢 <b>آیدی عددی</b> کاربر را بفرست.\n❌ لغو: /cancel")
        except TelegramError:
            pass
        return

    if data == "adm:bcast":
        if BCAST_RUNNING:
            try:
                await q.answer("📡 یک ارسال همگانی در حال اجراست! صبر کن تموم بشه.", show_alert=True)
            except TelegramError:
                pass
            return
        ud["pending"] = {"act": "bcast1"}
        try:
            await q.message.reply_html(
                "📢 <b>ارسال همگانی</b>\n\n"
                "پیامی که می‌خواهی برای <b>همه‌ی کاربران</b> ارسال شود را بفرست "
                "(متن، عکس، ویدیو، فوروارد... همه قبول است).\n\n❌ لغو: /cancel"
            )
        except TelegramError:
            pass
        return

    if data == "adm:bcy":
        src: Optional[Message] = ud.get("bc_msg")
        ud.pop("pending", None)
        ud.pop("bc_msg", None)
        if src is None:
            try:
                await q.edit_message_text("⚠️ پیامی برای ارسال ذخیره نشده بود!")
            except TelegramError:
                pass
            return
        if BCAST_RUNNING:
            try:
                await q.answer("📡 قبلاً شروع شده!", show_alert=True)
            except TelegramError:
                pass
            return
        BCAST_RUNNING = True
        status_msg = q.message
        ids = all_active_ids()
        try:
            await q.edit_message_text(f"📡 ارسال همگانی به <b>{len(ids)}</b> کاربر شروع شد…", parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
        _spawn(run_broadcast(context.bot, src, status_msg, len(ids)))
        return

    if data == "adm:bcn":
        ud.pop("pending", None)
        ud.pop("bc_msg", None)
        try:
            await q.edit_message_text("❌ ارسال همگانی لغو شد.")
        except TelegramError:
            pass
        return


async def render_channels(q) -> None:
    chans = get_force_channels()
    if not chans:
        txt = "🔒 <b>کانال‌های جوین اجباری</b>\n\nهنوز کانالی تنظیم نشده است."
    else:
        lines = ["🔒 <b>کانال‌های جوین اجباری:</b>\n"]
        for i, ch in enumerate(chans, 1):
            lines.append(f"{i}. <code>{esc(ch)}</code>")
        txt = "\n".join(lines) + "\n\n🗑 برای حذف روی دکمه‌ی کانال بزن."
    rows: List[List[InlineKeyboardButton]] = []
    for ch in chans:
        token = base64.b64encode(ch.encode("utf-8")).decode("ascii")[:44]
        rows.append([InlineKeyboardButton(f"🗑 {ch}", callback_data=f"adm:rmc:{token}")])
    rows.append([InlineKeyboardButton("➕ افزودن کانال", callback_data="adm:addc")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adm:panel")])
    try:
        await q.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))
    except TelegramError:
        pass


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: Dict[str, Any]) -> None:
    msg = update.effective_message
    ud = context.user_data
    user = update.effective_user
    if msg is None or user is None or user.id not in ADMIN_IDS:
        return
    act = pending.get("act")

    if act == "addc":
        ref = (msg.text or "").strip()
        try:
            chat = await context.bot.get_chat(ref)
        except TelegramError as exc:
            await msg.reply_html(f"❌ کانال پیدا نشد!\n<code>{esc(str(exc)[:150])}</code>")
            return
        try:
            me = await context.bot.get_me()
            cm = await context.bot.get_chat_member(chat.id, me.id)
            if getattr(cm, "status", "") not in ("administrator", "creator"):
                await msg.reply_text("⚠️ ربات در این کانال ادمین نیست! اول ربات را ادمین کنید بعد دوباره امتحان کنید.")
                return
        except TelegramError as exc:
            await msg.reply_html(f"❌ ربات دسترسی لازم را در کانال ندارد!\n<code>{esc(str(exc)[:150])}</code>")
            return
        canonical = f"@{chat.username}" if getattr(chat, "username", None) else str(chat.id)
        added = add_force_channel(canonical)
        JOIN_OK.clear()
        ud.pop("pending", None)
        state = "✅ اضافه شد!" if added else "ℹ️ این کانال قبلاً اضافه شده بود."
        await msg.reply_html(f"{state}\n🔒 کانال: <b>{esc(canonical)}</b>")

    elif act in ("ban", "unban"):
        raw = (msg.text or "").strip().lstrip("#")
        if not raw.lstrip("-").isdigit():
            await msg.reply_text("❌ لطفاً فقط آیدی عددی بفرست! مثال: <code>123456789</code>", parse_mode=ParseMode.HTML)
            return
        uid = int(raw)
        set_banned(uid, act == "ban")
        ud.pop("pending", None)
        if act == "ban":
            await msg.reply_html(f"🚫 کاربر <code>{uid}</code> بن شد.")
        else:
            await msg.reply_html(f"♻️ بن کاربر <code>{uid}</code> برداشته شد.")

    elif act == "bcast1":
        ud["bc_msg"] = msg
        ud["pending"] = {"act": "bcast2"}
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ ارسال کن", callback_data="adm:bcy"),
                    InlineKeyboardButton("❌ لغو", callback_data="adm:bcn"),
                ]
            ]
        )
        await msg.reply_html("👆 این پیام برای همه ارسال شود؟ مطمئنی؟", reply_markup=kb)

    elif act == "bcast2":
        ud["pending"] = {"act": "bcast1"}
        await msg.reply_text("لطفاً اول روی تأیید/لغو در پیام قبلی بزن، یا پیام جدیدی بفرست تا جایگزین شود.")


async def run_broadcast(bot, src: Message, status: Message, total: int) -> None:
    global BCAST_RUNNING
    start_t = time.time()
    ok = fail = blocked = 0
    try:
        for i, uid in enumerate(all_active_ids(), 1):
            try:
                await src.copy(chat_id=uid)
                ok += 1
            except RetryAfter as exc:
                await asyncio.sleep(getattr(exc, "retry_after", 5) + 1)
                try:
                    await src.copy(chat_id=uid)
                    ok += 1
                except TelegramError:
                    fail += 1
            except Forbidden:
                blocked += 1
            except TelegramError:
                fail += 1
            if i % 25 == 0:
                try:
                    await status.edit_text(
                        f"📡 در حال ارسال… {i}/{total}\n✅ {ok}   ❌ {fail}   🚫 {blocked}",
                        parse_mode=ParseMode.HTML,
                    )
                except TelegramError:
                    pass
            await asyncio.sleep(0.05)
        took = int(time.time() - start_t)
        await safe_edit(
            status,
            f"🏁 <b>ارسال همگانی تمام شد!</b>\n\n"
            f"✅ موفق: <b>{ok}</b>\n🚫 بلاک‌شده: <b>{blocked}</b>\n❌ ناموفق: <b>{fail}</b>\n"
            f"⏱ مدت: {took} ثانیه",
        )
    except Exception as exc:
        log_exc(exc, "run_broadcast")
    finally:
        BCAST_RUNNING = False


async def safe_edit(msg: Optional[Message], text: str) -> None:
    if msg is None:
        return
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML)
    except TelegramError:
        pass


# =====================================================================
# 🔎 جستجوی اینلاین (@BotName query)
# =====================================================================


def inline_search_sync(query: str) -> List[Dict[str, Any]]:
    """جستجوی سبک یوتیوب (flat، بدون فرمت‌ها) برای نتایج اینلاین."""
    opts = _ydl_base_opts()
    opts.pop("playlist_items", None)
    opts.update({"extract_flat": "discard_in_response", "skip_download": True, "format": "best/worst"})
    info = _extract_with_fallback(f"ytsearch6:{query}", opts, download=False)
    entries = (info or {}).get("entries") or []
    out: List[Dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        vid = e.get("id") or ""
        url = e.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        if not url:
            continue
        out.append({
            "id": vid,
            "title": e.get("title") or "?",
            "url": url,
            "duration": e.get("duration"),
        })
    return out


async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    iq = update.inline_query
    if iq is None:
        return
    user = iq.from_user
    query = (iq.query or "").strip()
    if len(query) < 3:
        try:
            await iq.answer(
                results=[],
                cache_time=5,
                switch_pm_text="🎵 یک نام آهنگ بنویس…",
                switch_pm_parameter="start",
            )
        except TelegramError:
            pass
        return

    def build(results: List[Dict[str, Any]]):
        from telegram import (
            InlineQueryResultArticle,
            InputTextMessageContent,
        )
        items = []
        for r in results[:6]:
            rid = str(r.get("id") or "").strip() or secrets.token_hex(4)
            rtitle = (r.get("title") or "بدون عنوان")[:120]
            thumb = f"https://i.ytimg.com/vi/{rid}/hqdefault.jpg"
            dur = fmt_dur(r.get("duration")) if r.get("duration") else ""
            desc = f"⏱ {dur}" if dur else "YouTube"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📥 دانلود", callback_data=f"iv:{rid}"),
            ]])
            items.append(InlineQueryResultArticle(
                id=rid[:64],
                title=rtitle,
                description=desc,
                thumbnail_url=thumb,
                input_message_content=InputTextMessageContent(
                    f"https://www.youtube.com/watch?v={rid}"),
                reply_markup=kb,
            ))
        return items

    try:
        # کش سبک در حافظه تا تایپ‌های پیاپی سرور را اذیت نکند
        cached = INLINE_CACHE.get((user.id, query.lower()))
        if cached and cached[0] > time.time():
            results = cached[1]
        else:
            results = await asyncio.to_thread(inline_search_sync, query)
            INLINE_CACHE[(user.id, query.lower())] = (time.time() + 180, results)
            while len(INLINE_CACHE) > 300:
                INLINE_CACHE.pop(next(iter(INLINE_CACHE)))
        await iq.answer(results=build(results), cache_time=60)
    except Exception as exc:
        log_exc(exc, "inline")
        try:
            await iq.answer(results=[], cache_time=10)
        except TelegramError:
            pass


INLINE_CACHE: Dict[Tuple[int, str], Tuple[float, List[Dict[str, Any]]]] = {}


# =====================================================================
# 🧹 نگهداری خودکار (پاکسازی فایل‌ها و توکن‌ها)
# =====================================================================


async def janitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    cutoff = time.time() - CLEAN_AFTER_MIN * 60
    removed = 0
    try:
        for f in DOWNLOAD_DIR.glob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    # پاکسازی تاریخچه‌های قدیمی‌تر از ۷ روز
    try:
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat(timespec="seconds")
        db_exec("DELETE FROM history WHERE ts < ?", (cutoff_iso,))
    except Exception:
        pass
    now = time.time()
    for tok in list(REG_ORDER):
        ent = REGISTRY.get(tok)
        if not ent or ent.get("exp", 0) < now:
            REGISTRY.pop(tok, None)
            try:
                REG_ORDER.remove(tok)
            except ValueError:
                pass
    stale_users = [u for u, exp in JOIN_OK.items() if exp < now]
    for u in stale_users:
        JOIN_OK.pop(u, None)
    # کول‌داون‌های قدیمی‌تر از ۲۴ ساعت — جلوگیری از هرزشدگی حافظه
    stale_req = [u for u, ts in LAST_REQ.items() if now - ts > 86400]
    for u in stale_req:
        LAST_REQ.pop(u, None)
    if removed:
        log.info("🧹 janitor: %s فایل قدیمی پاک شد.", removed)


# =====================================================================
# ❗️ هندلر خطا
# =====================================================================


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    exc = context.error
    if isinstance(exc, Exception):
        log_exc(exc, "dispatcher")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(ERR_GENERIC_TXT)
        except TelegramError:
            pass


# =====================================================================
# 🚀 راه‌اندازی
# =====================================================================


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    log.info("🤖 Bot @%s started successfully!", me.username)
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "شروع / منوی اصلی"),
                BotCommand("help", "راهنما"),
                BotCommand("history", "تاریخچه دانلودها"),
                BotCommand("lang", "تغییر زبان / Language"),
                BotCommand("admin", "پنل مدیریت"),
                BotCommand("cancel", "لغو عملیات فعلی"),
            ]
        )
    except TelegramError as exc:
        log.warning("set_my_commands failed: %s", exc)
    for aid in ADMIN_IDS:
        try:
            await app.bot.send_message(aid, "✅ ربات روشن شد و آماده‌ی کار است! 🎬🎵")
        except TelegramError:
            pass


def _start_health_server() -> None:
    """وب‌سرور مینیاتوری برای Healthcheck پلتفرم‌ها (Railway و…).

    فقط وقتی متغیر PORT ست شده باشد فعال می‌شود؛ روی / یک JSON وضعیت برمی‌گرداند.
    """
    port_s = os.getenv("PORT", "").strip()
    if not port_s:
        return
    try:
        port = int(port_s)
    except ValueError:
        log.warning("PORT نامعتبر است: %r — healthcheck غیرفعال ماند", port_s)
        return
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = (
                '{"status":"ok","service":"music-video-bot","uptime":'
                + str(int(time.time() - PROCESS_START)) + "}"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # بی‌صدا
            pass

    try:
        srv = HTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True, name="healthz").start()
        log.info("✅ healthcheck روی پورت %s فعال شد (GET /)", port)
    except OSError as exc:
        log.warning("health server راه نیفتاد: %s", exc)


def _validate_env_or_exit() -> None:
    """قبل از ران، متغیرهای ضروری را چک می‌کند؛ اگر نباشد با راهنمای دقیق خارج می‌شود.

    این همان «سوال‌پرسیدنِ» Railway است: تا Variables را در پنل نگذاری، دیپلوی
    fail می‌شود و لاگ دقیقاً می‌گوید چه چیزی باید اضافه شود.
    """
    missing: List[str] = []
    if not BOT_TOKEN or BOT_TOKEN == "PUT-YOUR-TOKEN-HERE":
        missing.append("BOT_TOKEN")
    if not ADMIN_IDS:
        missing.append("ADMIN_IDS")

    if missing:
        lines = [
            "",
            "╔══════════════════════════════════════════════════════════╗",
            "║   ⚠️  متغیرهای ضروری تنظیم نشده‌اند — Required Variables  ║",
            "╚══════════════════════════════════════════════════════════╝",
            "",
            "در پنل Railway → سرویس بات → تب **Variables** اضافه کن:",
            "",
        ]
        if "BOT_TOKEN" in missing:
            lines.append("   BOT_TOKEN=123456789:AA...      ← توکن از @BotFather")
        if "ADMIN_IDS" in missing:
            lines.append("   ADMIN_IDS=123456789            ← آیدی عددی ادمین (با کاما جدا کن)")
        lines += [
            "",
            "اختیاری ولی توصیه‌شده:",
            "   FORCE_CHANNELS=@yourchannel    ← جوین اجباری (با اسپیس چندتا)",
            "   LOG_CHANNEL=@yourlog           ← کانال گزارش خطاها",
            "",
            "بعد از ذخیره، Railway خودکار دوباره دیپلوی می‌کند ✅",
            "─" * 58,
        ]
        print("\n".join(lines), flush=True)
        raise SystemExit(1)

    # هشدارهای غیرفاجعه‌بار
    if not DEFAULT_FORCE_CHANNELS:
        log.warning("⚠️ FORCE_CHANNELS خالی است — جوین اجباری فعلاً خاموش است (از پنل ادمین هم قابل افزودن است).")
    if not LOG_CHANNEL:
        log.warning("⚠️ LOG_CHANNEL خالی است — خطاها فقط در لاگ سرور ثبت می‌شوند.")
    if shutil.which("ffmpeg") is None and not os.getenv("RAILWAY_ENVIRONMENT"):
        log.warning("⚠️ ffmpeg پیدا نشد! شناسایی آهنگ (Shazam) کار نخواهد کرد.")


def build_app(token: str) -> Application:
    """ساخت و پیکربندی کامل اپلیکیشن (جدا از اجرا — برای تست هم استفاده می‌شود)."""
    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # --- Commands ---
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # --- Inline (@BotName query) ---
    app.add_handler(InlineQueryHandler(on_inline))

    # --- Callbacks ---
    app.add_handler(CallbackQueryHandler(on_callback))

    # --- Free content (links / admin inputs) — فقط پیام‌های جدید، نه ویرایش‌ها ---
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & ~filters.COMMAND, on_content))

    # --- Errors ---
    app.add_error_handler(on_error)

    # --- Jobs ---
    if app.job_queue is not None:
        app.job_queue.run_once(janitor, 15)
        app.job_queue.run_repeating(janitor, interval=300)
    else:  # pragma: no cover
        log.warning("⚠️ JobQueue در دسترس نیست! `pip install \"python-telegram-bot[job-queue]\"` را نصب کنید.")
    return app


def main() -> None:
    # --- چک متغیرهای ضروری (Railway: تا Variables را نگذاری، دیپلوی fail می‌شود) ---
    _validate_env_or_exit()

    logging.getLogger(__name__).info("🔧 initializing…")

    db_init()
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if COOKIES_FILE.exists():
        log.info("🍪 cookies found: %s", COOKIES_FILE.resolve())
    else:
        log.info("🍪 cookies.txt پیدا نشد (اختیاری). برای یوتیوب/اینستاگرام محدودشده لازم است.")

    if not ADMIN_IDS:  # pragma: no cover — بالاتر exit شده
        log.warning("⚠️ ADMIN_IDS خالی است! پنل مدیریت غیرفعال خواهد بود.")

    if os.getenv("RAILWAY_ENVIRONMENT"):
        log.info("🚂 Railway detected — env=%s", os.getenv("RAILWAY_ENVIRONMENT"))

    _start_health_server()

    app = build_app(BOT_TOKEN)
    log.info("🚀 polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
