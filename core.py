"""شیء ربات و ابزارهای ارسال (جدا از بقیه تا import دوری پیش نیاد)."""
import config
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat
import logging

bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
INFO = {"username": ""}


async def notify(uid, text):
    if uid is None or uid < 0:      # NPC
        return
    try:
        await bot.send_message(uid, text)
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
