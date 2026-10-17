"""شیء ربات و ابزارهای ارسال (جدا از بقیه تا import دوری پیش نیاد)."""
import config
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

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
