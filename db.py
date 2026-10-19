import asyncio
import time

from motor.motor_asyncio import AsyncIOMotorClient

import config
import engine
import events

cli = AsyncIOMotorClient(config.MONGO_URI)
db = cli[config.DB_NAME]
C = db.countries
A = db.alliances
W = db.wars
M = db.market        # آگهی‌های بازار آزاد
G = db.groups        # گروه‌هایی که ربات توشونه
BANS = db.bans
META = db.meta       # world / شمارنده‌ها
PACTS = db.pacts     # پیمان‌ها و پیشنهادهای معامله (دیپلماسی)
CODES = db.codes     # کدهای هدیه
ACT = db.activity    # فعالیت روزانه‌ی بازیکن‌ها (برای آمار رشد)
FLAGS = db.flags     # هشدارهای ضدتقلب
INVITES = db.invites # سابقه‌ی دعوت‌ها
TRF = db.transfers   # هدیه/معامله‌ی بین بازیکن‌ها (برای ردیابی تقلب)

# همه‌ی عملیات‌های تغییردهنده زیر این قفل اجرا می‌شن (جلوگیری از race)
LOCK = asyncio.Lock()


async def save(c):
    await C.replace_one({"_id": c["_id"]}, c, upsert=True)


async def load(uid):
    """کشور رو می‌خونه و زمان سپری‌شده رو روش شبیه‌سازی می‌کنه."""
    c = await C.find_one({"_id": uid})
    if not c:
        return None
    engine.defaults(c)
    t = time.time()
    real_h = min(config.TICK_MAX_H, (t - c["last_tick"]) / 3600)
    dt = real_h * config.TIME_SCALE
    dirty = False
    if dt > 0.002:
        if c.get("npc"):
            engine.npc_regen(c, dt)
        else:
            engine.EV["income"] = events.weighted("income", c["last_tick"], t)
            engine.EV["research"] = events.weighted("research", c["last_tick"], t)
            engine.tick(c, dt)
        c["last_tick"] = t
        dirty = True
    if engine.settle(c):          # ساخت/آموزش تمام‌شده و رویدادهای منقضی
        dirty = True
    if dirty:
        await save(c)
    return c


async def is_banned(uid):
    return await BANS.find_one({"_id": uid}) is not None


async def next_id(name):
    from pymongo import ReturnDocument
    d = await META.find_one_and_update({"_id": "seq_" + name}, {"$inc": {"v": 1}},
                                       upsert=True, return_document=ReturnDocument.AFTER)
    return d["v"]


async def setup():
    """ایندکس‌ها، مهاجرت کشورهای قدیمی، ساخت NPCها."""
    import reg
    await A.create_index("name")
    await C.create_index("name")
    await C.create_index("home")
    await M.create_index([("item", 1), ("price", 1)])
    await ACT.create_index("d")
    await PACTS.create_index([("a", 1), ("b", 1)])
    await FLAGS.create_index("ts")
    await INVITES.create_index("by")
    await TRF.create_index("to")
    # کشورهای قدیمی name_key ندارن؛ قبل از ایندکس یکتا پرشون می‌کنیم
    async for d in C.find({"name_key": {"$exists": False}}, {"name": 1}):
        await C.update_one({"_id": d["_id"]}, {"$set": {"name_key": reg.name_key(d["name"])}})
    await C.create_index("name_key", unique=True, partialFilterExpression={"name_key": {"$type": "string"}})
    for i, spec in enumerate(config.NPCS):
        if not await C.find_one({"_id": engine.npc_id(i)}, {"_id": 1}):
            await save(engine.make_npc(i, spec))
