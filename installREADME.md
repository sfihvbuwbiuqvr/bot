# 🚀 راهنمای نصب کامل ربات روی سرور تازه

این راهنما، تمام مراحل نصب، پیکربندی و اجرای ربات را در یک سرور تازه (Debian/Ubuntu/Kali) شرح می‌دهد.

---

## 📋 پیش‌نیاز

- سرور تازه با Debian 12+، Ubuntu 22+ یا Kali Rolling
- دسترسی root (یا `sudo`)
- اتصال اینترنت
- یک اکانت تلگرام برای ساخت ربات از [@BotFather](https://t.me/BotFather)
- آیدی عددی تلگرام خودتان (از [@userinfobot](https://t.me/userinfobot) بگیرید)

---

## ۱. نصب پکیج‌های سیستمی

```bash
apt update && apt install -y \
  python3-pip python3-venv ffmpeg git curl unzip ca-certificates \
  build-essential pkg-config libasound2-dev
```

> - `python3-venv` → ساخت محیط مجازی
> - `ffmpeg` → تبدیل صدا، برش، و Shazam
> - `build-essential`, `pkg-config`, `libasound2-dev` → کامپایل `shazamio-core` (هسته‌ی شزام)

---

## ۲. نصب Deno (JS runtime برای yt-dlp و bgutil)

```bash
curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /tmp/d.zip
unzip /tmp/d.zip -d /usr/local/bin
chmod +x /usr/local/bin/deno
deno --version
```

---

## ۳. نصب `uv` (مدیر بسته‌ی سریع پایتون)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv python install 3.12
```

> `uv python install 3.12` نسخه‌ی ۳.۲ پایتون را به‌صورت باینری دانلود می‌کند (بدون نیاز به کامپایل).

---

## ۴. کلون ریپوی پروژه

```bash
cd /
git clone https://github.com/esinveivnwwnvqni/bot.git /bot
cd /bot
```

> اگر ریپو خصوصی است و احراز هویت نیاز دارد، ابتدا توکن GitHub خود را در `git clone https://<TOKEN>@github.com/...` بگذارید.

---

## ۵. ساخت venv با Python 3.12 و نصب پکیج‌ها

```bash
cd /bot
uv venv --python 3.12 .venv
source .venv/bin/activate
python --version   # باید Python 3.12.x بگوید
uv pip install --python .venv/bin/python -r requirements.txt
```

**نصب‌های معمول:**
- `python-telegram-bot[job-queue]` (با job-queue برای janitor)
- `yt-dlp`
- `shazamio`
- `httpx`
- `mutagen` (تگ‌گذاری MP3)
- `bgutil-ytdlp-pot-provider` (PO-Token)

---

## ۶. ساخت فایل `.env`

```bash
cat > /bot/.env <<'EOF'
BOT_TOKEN=7012345678:AAH_your_token_here
ADMIN_IDS=123456789
COOKIES_B64=پایه۶۴_کوکی_یوتیوب
DB_PATH=/bot/data/bot.db
DOWNLOAD_DIR=/bot/data/downloads
EOF
```

**متغیرها:**
| متغیر | توضیح | مثال |
|---|---|---|
| `BOT_TOKEN` | توکن ربات از BotFather | `7012345678:AAH_...` |
| `ADMIN_IDS` | آیدی عددی ادمین(ها) با کاما | `123456789` یا `111,222` |
| `COOKIES_B64` | متن پایه۶۴ کوکی یوتیوب | (مرحله ۷) |
| `DB_PATH` | مسیر دیتابیس SQLite | `/bot/data/bot.db` |
| `DOWNLOAD_DIR` | پوشه‌ی فایل‌های دانلودی | `/bot/data/downloads` |

ساخت پوشه‌ی داده:
```bash
mkdir -p /bot/data/downloads
```

---

## ۷. گرفتن کوکی یوتیوب (روی کامپیوتر شخصی)

### ۷.۱. نصب افزونه‌ی مرورگر

- **Chrome / Edge / Brave**: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Firefox**: همان افزونه در [AMO](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)

### ۷.۲. گرفتن کوکی

1. در مرورگر وارد `https://www.youtube.com` شو (حتماً لاگین باش)
2. افزونه را باز کن
3. **Export Current Site** (یا **Export** اگر فقط Current Site نیست)
4. فایل `cookies.txt` (یا `www.youtube.com_cookies.txt`) را ذخیره کن

> ⚠️ **مهم**: بعد از Export، در همان مرورگر **دیگر به youtube.com نرو و Logout نکن** — گوگل توکن‌ها را عوض می‌کند و کوکی نامعتبر می‌شود.

### ۷.۳. تبدیل به Base64 (در ویندوز PowerShell)

در PowerShell ویندوز، فایل را Base64 کن. متن طولانی تولید می‌شود؛ آن را در کلیپ‌برد کپی کن:

```powershell
# اگر فایل در مسیر پیش‌فرض مرورگر باشد (Downloads):
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\www.youtube.com_cookies.txt")) | Set-Clipboard
```

اگر فایل در جای دیگر است، مسیر را عوض کن:
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("G:\github\matin\www.youtube.com_cookies.txt")) | Set-Clipboard
```

حالا در فایل `.env` سرور، مقدار `COOKIES_B64=` را Paste کن.

### ۷.۴. یا: انتقال فایل مستقیم به سرور (بدون Base64)

اگر فایل را مستقیم روی سرور گذاشتی:
```bash
# فایل را در /bot/cookies.txt بگذار (روش ساده‌تر، بدون Base64)
nano /bot/cookies.txt
# سپس محتوای فایل را paste کن و Ctrl+O ذخیره
```

ربات هر دو روش (`COOKIES_B64` در env و `cookies.txt` در `/bot`) را پشتیبانی می‌کند.

---

## ۸. اجرای ربات

```bash
pkill -f 'python bot.py' 2>/dev/null
sleep 3
nohup bash -c 'while true; do .venv/bin/python bot.py; sleep 5; done' > /tmp/bot.log 2>&1 &
disown
sleep 3
tail -10 /tmp/bot.log
```

**اگر همه چیز درست باشد، در لاگ این‌ها را می‌بینی:**
```
🤖 Bot @Serverlinuxsphbot started successfully!
✅ healthcheck روی پورت 8080
🍪 cookies found: /bot/cookies.txt
```

> `nohup ... & disown` تضمین می‌کند که ربات حتی پس از خروج SSH زنده بماند. حلقه‌ی `while true` نیز اگر ربات کرش کند، آن را خودکار دوباره راه‌اندازی می‌کند.

---

## ۹. تست در تلگرام

به ربات `/start` بزنید و این‌ها را امتحان کنید:

| دستور / عمل | نتیجه |
|---|---|
| `/start` | منوی اصلی |
| `Eminem` (متن ساده) | پیشنهاد جستجو با دکمه‌ی `☁️ SoundCloud` و `▶️ YouTube` |
| **چند خط از متن آهنگ** (بدون اسم خواننده) | 🔤 بدون پرسیدن پلتفرم، نام آهنگ از متن تشخیص داده می‌شود و نتایج پین‌شده می‌آید |
| یک لینک SoundCloud/Instagram/TikTok | دانلود و ارسال |
| ویدیو بفرست + دکمه‌ی 🎵 شناسایی | Shazam آهنگ را پیدا می‌کند |
| `/admin` (فقط برای ADMIN_IDS) | پنل مدیریت |

---

## ۹.۱ 🔤 جستجوی آهنگ با متن ترانه (بدون نام خواننده)

وقتی کاربر **تکه‌ای از متن آهنگ** را (فارسی یا انگلیسی) بدون نام خواننده می‌فرستد،
ربات با یک زنجیره‌ی ۴ لایه‌ای نام آهنگ را پیدا می‌کند:

| # | موتور | روش | کاربرد |
|---|---|---|---|
| ۱ | **Genius** (`genius.com/api/search/multi`) | ایندکس محتوای متن ترانه | آهنگ‌های انگلیسی/جهانی — دقیق‌ترین |
| ۲ | **DuckDuckGo** (`html.duckduckgo.com`) | لاتین: `«عبارت» + lyrics` و استخراج «خواننده – آهنگ» از عنوان نتایج / فارسی-عربی: `متن آهنگ <تکه>` | همه‌ی زبان‌ها، از جمله آهنگ‌های ایرانی |
| ۳ | **lrclib.net** | جستجوی نام (fallback) | اگر متن شامل خودِ نام آهنگ باشد |
| ۴ | **YouTube raw search** | خودِ متن ترانه مستقیم در یوتیوب جستجو می‌شود | فالبک نهایی وقتی ۱–۳ جواب ندادند |

**نحوه‌ی نمایش در چت:**
- اگر کاربر **چند خط از متن ترانه** بفرستد (متن بلند/چندخطی)، ربات **بدون پرسیدن پلتفرم** مستقیم روی YouTube جستجو و تشخیص می‌کند.
- اگر نام کوتاه بفرستد (مثل `Eminem`)، دکمه‌ی انتخاب پلتفرم نمایش داده می‌شود.
- اگر نام آهنگ تشخیص داده شود، بالای نتایج این خط می‌آید:
  `🔤 تشخیص از متن ترانه (DuckDuckGo): دلم برات تنگ شده — محسن یاحقی`
- نتایجِ آهنگِ تشخیص‌داده‌شده **پین‌شده** در ابتدای لیست دکمه‌ها قرار می‌گیرند.
- اگر کاربر SoundCloud را انتخاب کرده باشد و آنجا چیزی پیدا نشود، همان آهنگ خودکار در YouTube هم جستجو می‌شود (نتایج ترکیبی با برچسب ▶️/☁️).

**نکات فنی:**
- هیچ پکیج جدیدی لازم نیست — همه‌چیز با `httpx` (از قبل در `requirements.txt`) و `yt-dlp` کار می‌کند.
- تشخیص «متن ترانه بودن» ورودی با `looks_like_lyrics` است: ≥۲ خط، یا ≥۸ کلمه، یا ≥۸۰ کاراکتر.
- **یکدست‌سازی فارسی** قبل از ارسال به موتورها: `ي→ی`، `ك→ک`، حذف نیم‌فاصله («می‌رم» ← «میرم») — چون املای کاربران با سایت‌های متن آهنگ فرق دارد.
- **فالبک نهایی همیشه فعال است:** اگر هیچ لایه‌ای نتیجه نداد، خودِ متن در YouTube جستجو می‌شود (برای آهنگ‌های ایرانی و املای محاوره‌ای مثل «امشو میرم محلشان» حیاتی است).
- برچسب‌های `[Verse]` / `[0:12]` قبل از ارسال به موتورها حذف می‌شوند.
- لاگ‌های مربوطه در `/tmp/bot.log`:
  - موفقیت: `lyrics-hit[DuckDuckGo]: محسن یاحقی — دلم برات تنگ شده`
  - خطای یک موتور (ادامه به موتور بعدی): `lyrics backend _genius_by_lyrics failed: ...`

---

## ۱۰. دستورات مفید (مرجع سریع)

### دیدن لاگ زنده
```bash
tail -f /tmp/bot.log
```

### بررسی اینکه ربات زنده است
```bash
ps aux | grep bot.py | grep -v grep
```

### بستن و راه‌اندازی مجدد
```bash
pkill -f 'python bot.py'
sleep 3
cd /bot
nohup bash -c 'while true; do .venv/bin/python bot.py; sleep 5; done' > /tmp/bot.log 2>&1 &
disown
```

### به‌روزرسانی کد (هر وقت کد در GitHub عوض شد)
```bash
pkill -f 'python bot.py' 2>/dev/null
sleep 3
cd /bot
git pull
nohup bash -c 'while true; do .venv/bin/python bot.py; sleep 5; done' > /tmp/bot.log 2>&1 &
disown
sleep 3
tail -10 /tmp/bot.log
```

### دیدن حجم پوشه‌ی دانلود
```bash
du -sh /bot/data/downloads
ls -la /bot/data/downloads
```

### پاک کردن فایل‌های قدیمی (janitor خودکار انجام می‌دهد، ولی دستی):
```bash
find /bot/data/downloads -type f -mmin +45 -delete
```

### دیدن وضعیت دیتابیس
```bash
sqlite3 /bot/data/bot.db "SELECT COUNT(*) FROM users;"
sqlite3 /bot/data/bot.db "SELECT key, value FROM stats;"
```

### گرفتن بکاپ دیتابیس
```bash
cp /bot/data/bot.db /tmp/bot.db.bak.$(date +%F)
```

---

## ۱۱. ساخت سرویس systemd (اختیاری، برای اجرای دائمی)

**توجه:** اگر سرور systemd ندارد (مثل Kali یا بسیاری از کانتینرهای Docker)، این مرحله را رد کن و از `nohup` مرحله‌ی ۸ استفاده کن.

```bash
cat > /etc/systemd/system/matinbot.service <<'EOF'
[Unit]
Description=Matin Music Bot
After=network.target

[Service]
WorkingDirectory=/bot
ExecStart=/bot/.venv/bin/python bot.py
EnvironmentFile=/bot/.env
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now matinbot
systemctl status matinbot
```

دیدن لاگ:
```bash
journalctl -u matinbot -f
```

---

## ۱۲. عیب‌یابی (Troubleshooting)

### ربات بالا نمی‌آید

```bash
tail -30 /tmp/bot.log
# یا
journalctl -u matinbot -n 50
```

خطاهای معمول:
- `ModuleNotFoundError: No module named '...'` ← `uv pip install` را دوباره اجرا کن
- `Address already in use` ← پورت ۸۰۸۰ اشغال است. یک پروسه‌ی دیگر (ربات قدیمی) را با `pkill` بکش
- `Conflict: terminated by other getUpdates` ← **دو نمونه ربات با یک توکن** روشن است. سرور Railway یا نمونه‌ی لوکال دیگر را خاموش کن

### YouTube خطای `Sign in to confirm` می‌دهد

- کوکی rotate شده. دوباره Export بگیر
- کوکی از مرورگری است که **بعد از Export** در آن به YouTube رفته‌ای. از Export تا Paste در `.env` مرورگر را نبند

### YouTube خطای `Requested format is not available` می‌دهد

- `bgutil` (PO-Token) بالا نیامده. دلیل: اکثر آی‌پی‌های دیتاسنتر توسط YouTube بلاک شده‌اند. **SoundCloud** را امتحان کن (معمولاً کار می‌کند).

### ربات به پیام‌های متنی جواب نمی‌دهد ولی `/start` کار می‌کند

- `pending` در `user_data` از قبل مانده. `/cancel` بزنید یا چند دقیقه صبر کنید.
- یا `Pending` به‌علت `/admin` باقی مانده که با `/cancel` پاک می‌شود.

### جستجوی «متن ترانه» نتیجه نمی‌دهد (search_none)

اول لاگ را ببینید:
```bash
grep -E "lyrics-hit|lyrics backend|search_sync" /tmp/bot.log | tail -20
```

- `lyrics backend _genius_by_lyrics failed: HTTP 403` ← **طبیعی است.** آی‌پی دیتاسنترها معمولاً توسط Genius بلاک‌اند؛ ربات خودکار به DuckDuckGo و بقیه لایه‌ها می‌رود.
- `lyrics backend _ddg_by_lyrics failed` یا پاسخ ۲۰۲/anomaly ← DuckDuckGo این IP را **rate-limit** کرده. چند دقیقه تا چند ساعت صبر کنید؛ در این فاصله لایه‌ی ۴ (جستجوی یوتیوب با خودِ متن) جواب را می‌دهد.
- هیچ `lyrics-hit` در لاگ نیست ولی جستجوی مستقیم هم خالی بود ← احتمالاً کوکی یوتیوب منقضی شده و لایه‌ی فالبک یوتیوب هم کار نمی‌کند؛ کوکی را Refresh کنید (مرحله ۷).
- برای فارسی حتماً **چند خط کامل** بفرستید (نه یک تکه‌ی ۳-۴ کلمه‌ای)؛ تشخیص به متن طولانی‌تر خیلی بهتر جواب می‌دهد.
- تست سریع سلامت موتورها روی سرور:
```bash
curl -s -A "Mozilla/5.0" "https://lrclib.net/api/search?q=shape+of+you+ed+sheeran" | head -c 200; echo
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0" "https://html.duckduckgo.com/html/?q=test"
```
خروجی سالم: خط اول JSON پر، خط دوم `200` (اگر `403`/`202` داد یعنی DDG موقتاً این IP را محدود کرده).

---

## ۱۳. خلاصه‌ی یک‌خطی (برای حرفه‌ای‌ها 😎)

**نصب اول:**
```bash
apt update && apt install -y python3-pip python3-venv ffmpeg git curl unzip ca-certificates build-essential pkg-config libasound2-dev && curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip | gunzip > /usr/local/bin/deno && chmod +x /usr/local/bin/deno && curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env && uv python install 3.12 && cd / && git clone https://github.com/esinveivnwwnvqni/bot.git /bot && cd /bot && uv venv --python 3.12 .venv && source .venv/bin/activate && uv pip install --python .venv/bin/python -r requirements.txt
```

**ساخت `.env`:**
```bash
cat > /bot/.env <<'EOF'
BOT_TOKEN=YOUR_TOKEN
ADMIN_IDS=YOUR_ID
COOKIES_B64=
DB_PATH=/bot/data/bot.db
DOWNLOAD_DIR=/bot/data/downloads
EOF
mkdir -p /bot/data/downloads
```

**اجرا:**
```bash
pkill -f 'python bot.py' 2>/dev/null; sleep 3
nohup bash -c 'while true; do .venv/bin/python bot.py; sleep 5; done' > /tmp/bot.log 2>&1 &
disown
sleep 3
tail -10 /tmp/bot.log
```

---

## 📞 پشتیبانی

- لاگ‌ها همیشه اولین جا برای عیب‌یابی هستند: `tail -f /tmp/bot.log`
- اگر باگی در کد پیدا شد، در GitHub Issue بگذارید
- قبل از گزارش باگ، مطمئن شوید `git pull` کرده‌اید و `requirements.txt` به‌روز است
