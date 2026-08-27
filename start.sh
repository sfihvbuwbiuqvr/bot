#!/bin/sh
# راه‌اندازی کانتینر: اول سرور PO-Token (bgutil) در پس‌زمینه، بعد خودِ ربات.
# اگر سرور توکن به هر دلیلی بالا نیاید، ربات بدون آن هم کار می‌کند (گرس‌مود yt-dlp).

if [ -f /opt/pot/server/src/main.ts ]; then
    deno run --allow-env --allow-net --allow-ffi=/app/node_modules \
        --allow-read=/app/node_modules \
        /opt/pot/server/src/main.ts >/tmp/pot.log 2>&1 &
    echo "[start.sh] bgutil PO-token provider started (deno, port 4416)"
else
    echo "[start.sh] WARNING: pot provider server missing — continuing without it"
fi

exec python bot.py
