import asyncio
import logging

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import admin
import commands
import config
import db
import eco
import engine as E
import ui
from core import INFO, bot, dp, notify
from util import OWNER, esc, n

logging.basicConfig(level=logging.INFO)
GROUPS = F.chat.type.in_({"group", "supergroup"})


def arg(m):
    p = (m.text or "").split(maxsplit=1)
    return p[1].strip() if len(p) > 1 else ""


# ------------------------------------------------------------------ دکمه‌ها
@dp.callback_query()
async def on_cb(q: CallbackQuery):
    data, owner = q.data or "", None
    if "|" in data:
        data, o = data.rsplit("|", 1)
        owner = int(o) if o.lstrip("-").isdigit() else None
    if owner is not None and owner != q.from_user.id:
        return await q.answer("این منو مال تو نیست؛ برای خودت /menu بزن", show_alert=True)
    OWNER.set(q.from_user.id)
    if data.startswith("ad:"):
        return await admin.callback(q, data[3:])
    if admin.blocked(q.from_user.id):
        return await q.answer(admin.SET["maint_msg"], show_alert=True)
    if data.startswith("rg:"):
        return await commands.rg_callback(q, data[3:])
    async with db.LOCK:
        if await db.is_banned(q.from_user.id):
            return await q.answer("🚫", show_alert=True)
        c = await db.load(q.from_user.id)
        if not c:
            return await q.answer("اول /register بزن", show_alert=True)
        try:
            toast, (text, markup) = await ui.route(c, data.split(":"))
            await db.save(c)
        except Exception:
            logging.exception("cb error")
            return await q.answer("خطا", show_alert=True)
    try:
        await q.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    await q.answer(toast)


# ------------------------------------------------------------------ اتحاد (گروه)
async def refresh_ally(a):
    bonus = min(0.15, 0.01 * len(a["members"]))
    await db.C.update_many({"_id": {"$in": a["members"]}}, {"$set": {"ally_bonus": bonus, "alliance": a["_id"]}})


@dp.message(Command("alliance_create"), GROUPS)
async def a_create(m: Message):
    name = arg(m)[:24]
    if len(name) < 2:
        return await m.answer("مثال: /alliance_create نام")
    async with db.LOCK:
        c = await db.load(m.from_user.id)
        if not c:
            return await m.answer(commands.NOT_REG)
        if c.get("alliance"):
            return await m.answer("تو عضو یه اتحادی")
        if await db.A.find_one({"$or": [{"_id": m.chat.id}, {"name": name}]}):
            return await m.answer("این گروه یا این اسم قبلاً اتحاد داره")
        a = {"_id": m.chat.id, "name": name, "leader": c["_id"], "members": [c["_id"]],
             "bank": 0, "wins": 0, "losses": 0}
        await db.A.insert_one(a)
        await refresh_ally(a)
    await m.answer(f"🤝 اتحاد <b>{esc(name)}</b> ساخته شد. بقیه با /join بپیوندن.")


@dp.message(Command("join"), GROUPS)
async def a_join(m: Message):
    async with db.LOCK:
        c = await db.load(m.from_user.id)
        a = await db.A.find_one({"_id": m.chat.id})
        if not c:
            return await m.answer(commands.NOT_REG)
        if not a:
            return await m.answer("این گروه اتحادی نداره: /alliance_create")
        if c.get("alliance"):
            return await m.answer("تو عضو یه اتحادی")
        if len(a["members"]) >= config.ALLY_MAX:
            return await m.answer("ظرفیت اتحاد پره")
        await db.A.update_one({"_id": a["_id"]}, {"$addToSet": {"members": c["_id"]}})
        await refresh_ally(await db.A.find_one({"_id": a["_id"]}))
    await m.answer(f"✅ {esc(c['name'])} به {esc(a['name'])} پیوست")


@dp.message(Command("leave"), GROUPS)
async def a_leave(m: Message):
    async with db.LOCK:
        c = await db.load(m.from_user.id)
        a = await db.A.find_one({"_id": m.chat.id})
        if not c or not a or c.get("alliance") != a["_id"]:
            return await m.answer("عضو این اتحاد نیستی")
        if a["leader"] == c["_id"]:
            return await m.answer("رهبر نمی‌تونه ترک کنه")
        await db.A.update_one({"_id": a["_id"]}, {"$pull": {"members": c["_id"]}})
        await db.C.update_one({"_id": c["_id"]}, {"$set": {"alliance": None, "ally_bonus": 0.0}})
        await refresh_ally(await db.A.find_one({"_id": a["_id"]}))
    await m.answer("🚪 از اتحاد خارج شدی")


@dp.message(Command("ally_info"), GROUPS)
async def a_info(m: Message):
    OWNER.set(m.from_user.id)
    async with db.LOCK:
        c = await db.load(m.from_user.id)
        if not c:
            return await m.answer(commands.NOT_REG)
        text, _ = await ui.s_ally(c)
    await m.answer(text)


@dp.message(Command("donate"), GROUPS)
async def a_donate(m: Message):
    try:
        amt = int(arg(m))
    except ValueError:
        return await m.answer("مثال: /donate 1000")
    async with db.LOCK:
        c = await db.load(m.from_user.id)
        if not c or c.get("alliance") != m.chat.id or amt <= 0 or c["treasury"] < amt:
            return await m.answer("ممکن نیست")
        c["treasury"] -= amt
        await db.save(c)
        await db.A.update_one({"_id": m.chat.id}, {"$inc": {"bank": amt}})
    await m.answer(f"🏦 {n(amt)} سکه به بانک اتحاد اهدا شد")


@dp.message(Command("ally_war"), GROUPS)
async def a_war(m: Message):
    name = arg(m)
    async with db.LOCK:
        a = await db.A.find_one({"_id": m.chat.id})
        if not a or a["leader"] != m.from_user.id:
            return await m.answer("فقط رهبر اتحاد می‌تونه اعلام جنگ کنه")
        b = await db.A.find_one({"name": name})
        if not b or b["_id"] == a["_id"]:
            return await m.answer("مثال: /ally_war نام‌اتحاد‌دشمن")
        if await ui.active_war(a["_id"]) or await ui.active_war(b["_id"]):
            return await m.answer("یکی از اتحادها درگیر جنگه")
        await db.W.insert_one({"a": a["_id"], "b": b["_id"], "start": E.now(),
                               "end": E.now() + config.ALLY_WAR_H * 3600,
                               "score": {"a": 0, "b": 0}, "active": True})
    msg = (f"🔥 <b>جنگ اتحادها!</b>\n{esc(a['name'])} ⚔️ {esc(b['name'])}\n"
           f"{config.ALLY_WAR_H} ساعت فرصت. هر عضو با /strike (یا دکمه‌ی اتحاد) هر ۳۰ دقیقه ضربه می‌زنه.\n"
           "برنده بانک بازنده رو ۲۵٪ غارت می‌کنه.")
    await m.answer(msg)
    await notify(b["_id"], msg)


@dp.message(Command("strike"), GROUPS)
async def a_strike(m: Message):
    async with db.LOCK:
        c = await db.load(m.from_user.id)
        if not c:
            return await m.answer(commands.NOT_REG)
        txt = await ui.do_strike(c)
        await db.save(c)
    await m.answer(txt)


# ------------------------------------------------------------------ حلقه‌های پس‌زمینه
async def finish_wars():
    async with db.LOCK:
        async for w in db.W.find({"active": True, "end": {"$lte": E.now()}}):
            await db.W.update_one({"_id": w["_id"]}, {"$set": {"active": False}})
            a, b = await db.A.find_one({"_id": w["a"]}), await db.A.find_one({"_id": w["b"]})
            if not a or not b:
                continue
            sa, sb = w["score"]["a"], w["score"]["b"]
            if sa == sb:
                msg = f"🤝 جنگ {esc(a['name'])} و {esc(b['name'])} مساوی شد ({sa}:{sb})"
            else:
                win, lose = (a, b) if sa > sb else (b, a)
                prize = int(lose.get("bank", 0) * 0.25)
                await db.A.update_one({"_id": win["_id"]}, {"$inc": {"bank": prize, "wins": 1}})
                await db.A.update_one({"_id": lose["_id"]}, {"$inc": {"bank": -prize, "losses": 1}})
                await db.C.update_many({"_id": {"$in": win["members"]}}, {"$inc": {"tech": 50, "sat": 10}})
                await db.C.update_many({"_id": {"$in": lose["members"]}}, {"$inc": {"sat": -5}})
                msg = (f"🏆 <b>{esc(win['name'])}</b> جنگ رو برد! ({max(sa, sb)}:{min(sa, sb)})\n"
                       f"غنیمت بانک: {n(prize)} · برندگان +۵۰ پژوهش و +۱۰ رضایت")
            await notify(a["_id"], msg)
            await notify(b["_id"], msg)


async def world_loop():
    while True:
        await asyncio.sleep(600)
        try:
            ids = [d["_id"] async for d in db.C.find({"npc": {"$ne": True}}, {"_id": 1})]
            for uid in ids:
                async with db.LOCK:
                    c = await db.load(uid)
                    if c and c.get("pending"):
                        txt = "📰 <b>اخبار کشور</b>\n" + "\n".join(c["pending"])
                        c["pending"] = []
                        await db.save(c)
                        await notify(uid, txt)
        except Exception:
            logging.exception("world_loop")


async def market_loop():
    """قیمت ارزها/کالاها + سیاست پولی بانک مرکزی."""
    while True:
        await asyncio.sleep(config.FX_STEP)
        try:
            agg = await db.C.aggregate([{"$match": {"npc": {"$ne": True}}},
                                        {"$group": {"_id": None, "dep": {"$sum": "$bank.dep"},
                                                    "loan": {"$sum": "$bank.loan"}}}]).to_list(1)
            dep, loan = (agg[0]["dep"], agg[0]["loan"]) if agg else (0.0, 0.0)
            async with db.LOCK:
                eco.world_step(dep, loan)
                await eco.save_world()
        except Exception:
            logging.exception("market_loop")


async def war_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await finish_wars()
        except Exception:
            logging.exception("war_loop")


async def main():
    await db.setup()
    await eco.init_world()
    await admin.load_settings()
    me = await bot.get_me()
    INFO["username"], INFO["id"] = me.username or "", me.id
    dp.include_router(admin.router)         # پنل ادمین باید قبل از دستورهای عادی بیاد
    dp.include_router(commands.router)      # بعد از هندلرهای بالا ثبت میشه
    asyncio.create_task(world_loop())
    asyncio.create_task(war_loop())
    asyncio.create_task(market_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
