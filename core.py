"""شیء ربات و ابزارهای ارسال (جدا از بقیه تا import دوری پیش نیاد)."""
import config
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat
import asyncio
import logging
import time
import traceback
from aiogram.exceptions import TelegramRetryAfter

bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
INFO = {"username": ""}


async def notify(uid, text, markup=None):
    if uid is None or uid < 0:      # NPC
        return
    try:
        await bot.send_message(uid, text, reply_markup=markup)
    except Exception:
        pass


# منوی «/» تلگرام (نام دستور باید لاتین باشه؛ توضیح‌ها فارسی)
MENU = [
    ("start", "🌍 شروع و ثبت‌نام"), ("menu", "🏠 دنیای من (پنل کامل)"), ("me", "👤 وضعیت کشور من"),
    ("daily", "🎁 جایزه‌ی روزانه"), ("work", "🧳 کار و درآمد"), ("missions", "🎖 ماموریت‌ها"),
    ("claim", "✅ تحویل پاداش ماموریت‌ها"),
    ("bank", "🏦 بانک مرکزی"), ("deposit", "📥 سپرده‌گذاری"), ("withdraw", "📤 برداشت از بانک"),
    ("loan", "💳 گرفتن وام"), ("repay", "💸 پرداخت وام"),
    ("market", "🏪 بازار"), ("buy", "🛒 خرید کالا"), ("sell", "💰 فروش کالا"),
    ("list", "📣 ثبت آگهی در بازار آزاد"), ("take", "🧾 خرید آگهی"), ("cancel", "🗑 لغو آگهی"),
    ("fx", "💱 بازار ارز و توکن"), ("fxbuy", "📈 خرید ارز"), ("fxsell", "📉 فروش ارز"), ("shield", "🛡 سپر"),
    ("buildings", "🏗 ساختمان‌ها"), ("build", "🔨 ساخت ساختمان"),
    ("army", "🪖 ارتش"), ("train", "⚔️ آموزش یگان"), ("upgrade", "⬆️ ارتقای نیروها"),
    ("policy", "💸 سیاست و بودجه"), ("research", "🔬 پژوهش"), ("unrest", "🚨 ناآرامی"),
    ("war", "🔥 جنگ"), ("npcs", "🌍 کشورهای جهان"), ("attack", "🗡 حمله"),
    ("intel", "🕵️ سازمان اطلاعات"), ("spy", "🔍 جاسوسی"),
    ("top", "🏆 رتبه‌بندی جهان"), ("gtop", "🥇 رتبه‌ی گروه"),
    ("ally_info", "🤝 اتحاد"), ("alliance_create", "➕ ساخت اتحاد"), ("join", "🚪 پیوستن به اتحاد"),
    ("leave", "👋 ترک اتحاد"), ("donate", "🎁 اهدا به بانک اتحاد"), ("ally_war", "⚔️ جنگ اتحاد"),
    ("strike", "💥 ضربه در جنگ اتحاد"),
    ("camp", "🎖 کمپین جهانی"), ("boss", "🌑 جنگ بزرگ"), ("orders", "⚡ فرمان نظامی"),
    ("queue", "🏗 صف ساخت و آموزش"), ("invite", "🎁 دعوت دوست"), ("code", "🎟 کد هدیه"),
    ("box", "🎰 جعبه‌ی شانس"), ("event", "📜 رویداد کشور"), ("news", "📰 اخبار جهان"),
    ("boards", "🏅 برترین‌ها و فصل"), ("diplo", "🤝 دیپلماسی"),
    ("map", "🗺 نقشه‌ی زنده‌ی جهان"), ("crown", "👑 تاج امپراتوری"),
    ("help", "📖 راهنمای کلمه‌ها و دستورها"),
]
ADMIN_MENU = [("admin", "🛠 پنل مدیریت"), ("ban", "🚫 مسدود کردن"), ("unban", "✅ آزاد کردن"), ("give", "🎁 هدیه‌ی سکه")]


async def sync_commands(removed=()):
    """منوی دستورها رو توی تلگرام ست می‌کنه؛ ادمین‌ها منوی بیشتری می‌بینن."""
    import config
    try:
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in MENU])
        full = [BotCommand(command=c, description=d) for c, d in MENU + ADMIN_MENU]
        for uid in config.ADMINS:
            try:
                await bot.set_my_commands(full, scope=BotCommandScopeChat(chat_id=uid))
            except Exception:
                pass          # ادمینی که هنوز ربات رو استارت نکرده
        for uid in removed:
            try:
                await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=uid))
            except Exception:
                pass
    except Exception:
        logging.exception("sync_commands")


# ------------------------------------------------------------------ لاگ توی چنل تلگرام
LOG = {"on": True, "q": None, "warned": False}
_SEEN = {}


def tlog(emoji, title, body=""):
    """یه خط لاگ به صف چنل اضافه می‌کنه (هیچ‌وقت خطا نمی‌ده و کار اصلی رو کند نمی‌کنه)."""
    q = LOG["q"]
    if not LOG["on"] or q is None:
        return
    text = f"{emoji} <b>{title}</b>" + (f"\n{body}" if body else "")
    try:
        q.put_nowait(text[:3900])
    except asyncio.QueueFull:
        pass


def log_exc(where):
    """خطای فعلی (traceback) رو به چنل می‌فرسته؛ خطای تکراری تا ۶۰ ثانیه دوباره نمیاد."""
    import html
    tb = traceback.format_exc().strip().splitlines()
    key = where + (tb[-1] if tb else "")
    now = time.time()
    if now - _SEEN.get(key, 0) < 60:
        return
    _SEEN[key] = now
    tlog("⚠️", "خطا", f"{html.escape(where)}\n<code>{html.escape(chr(10).join(tb[-6:])[-700:])}</code>")


async def _log_worker():
    import config
    while True:
        text = await LOG["q"].get()
        try:
            await bot.send_message(config.LOG_CHANNEL, text)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            LOG["q"].put_nowait(text)
        except Exception as e:
            if not LOG["warned"]:
                LOG["warned"] = True
                logging.warning("log channel send failed (%s): %s", config.LOG_CHANNEL, e)
        await asyncio.sleep(1.1)


def start_log_worker():
    LOG["q"] = asyncio.Queue(maxsize=500)
    asyncio.create_task(_log_worker())


async def log_test():
    """تست مستقیم ارسال به چنل؛ (موفق؟، خطا)"""
    import config
    try:
        await bot.send_message(config.LOG_CHANNEL, "✅ <b>تست لاگ</b>\nاتصال ربات به چنل لاگ درسته.")
        LOG["warned"] = False
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:200]
