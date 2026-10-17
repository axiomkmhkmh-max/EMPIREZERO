import asyncio
import time

from motor.motor_asyncio import AsyncIOMotorClient

import config
import engine

cli = AsyncIOMotorClient(config.MONGO_URI)
db = cli[config.DB_NAME]
C = db.countries
A = db.alliances
W = db.wars
M = db.market        # آگهی‌های بازار آزاد
G = db.groups        # گروه‌هایی که ربات توشونه
BANS = db.bans
META = db.meta       # world / شمارنده‌ها

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
    real_h = min(config.TICK_MAX_H, (time.time() - c["last_tick"]) / 3600)
    dt = real_h * config.TIME_SCALE
    if dt > 0.002:
        if c.get("npc"):
            engine.npc_regen(c, dt)
        else:
            engine.tick(c, dt)
        c["last_tick"] = time.time()
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
    # کشورهای قدیمی name_key ندارن؛ قبل از ایندکس یکتا پرشون می‌کنیم
    async for d in C.find({"name_key": {"$exists": False}}, {"name": 1}):
        await C.update_one({"_id": d["_id"]}, {"$set": {"name_key": reg.name_key(d["name"])}})
    await C.create_index("name_key", unique=True, partialFilterExpression={"name_key": {"$type": "string"}})
    for i, spec in enumerate(config.NPCS):
        if not await C.find_one({"_id": engine.npc_id(i)}, {"_id": 1}):
            await save(engine.make_npc(i, spec))
