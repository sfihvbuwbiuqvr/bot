# ============================================================
#  ربات دانلود ویدیو/موزیک — ایمیج سبک برای Railway / هر سرور داکری
#  ffmpeg داخل ایمیج نصب می‌شود (هم ffmpeg هم ffprobe)
# ============================================================
FROM python:3.12-slim

# این خط فقط برای شکستن کش بیلد است تا هر بار از نو ساخته شود و خطای واقعی
# بیلدِ bgutil (که قبلاً silent شکست می‌خورد) در لاگ بیاید.
ARG CACHEBUST=1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg: تبدیل صدا/برش | Deno: JS-runtime yt-dlp | git: کلون bgutil
# (node/npm بعداً جداگانه از NodeSource ورژن ۲۰ نصب می‌شود — debian 12 ورژن ۱۸ دارد که برای bgutil ۲۰۲۶ کافی نیست)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        unzip \
        git \
    && curl -fsSL -o /tmp/deno.zip \
        https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip \
    && unzip -q /tmp/deno.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/deno \
    && rm -rf /tmp/deno.zip /var/lib/apt/lists/* \
    && deno --version

# Node.js 20 (bgutil به آن نیاز دارد؛ debian 12 فقط 18 دارد)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && node --version && npm --version

# سرور PO-Token (bgutil) با Deno — نسخه‌ی ۲۰۲۶ دیگر npm script «build» ندارد؛
# سرورش با deno اجرا می‌شود (deno را قبلاً در مرحله‌ی بالا نصب کردیم).
# --omit=dev فقط دپندنسی‌های تولید را نصب می‌کند؛ سپس deno cache پکیج‌های TS را.
RUN git clone --depth=1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/pot \
    && cd /opt/pot/server \
    && npm install --no-audit --no-fund --omit=dev --legacy-peer-deps \
    && deno cache --frozen src/main.ts \
    || (echo "===== POT-BUILD-FAILED =====" \
        && echo "deno: $(deno --version 2>/dev/null | head -1)" \
        && ls -la /opt/pot/server 2>/dev/null)

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot.py .env.example README.md start.sh ./
RUN chmod +x start.sh

# مسیر داده‌ها: در Railway یک Volume روی همین /data مونت کن
# تا دیتابیس (bot.db) بعد از هر ری‌دیپلوی از دست نرود.
ENV DB_PATH=/data/bot.db \
    DOWNLOAD_DIR=/data/downloads
RUN mkdir -p /data/downloads

CMD ["/bin/sh", "/app/start.sh"]
