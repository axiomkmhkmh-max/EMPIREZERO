import asyncio
import logging

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import admin
import cine
import commands
import commands_ext  # noqa: F401  (ثبت دستورهای تازه روی همون دیسپچر)
import feats  # noqa: F401  (استان‌ها و دستاوردها)
import config
import crown
import db
import eco
import engine as E
import events
import growth
import ui
import war
import webapp
import wow  # noqa: F401  (دستورهای نقشه و تاج)
import world
from core import INFO, bot, dp, notify, sync_commands, log_exc, start_log_worker, tlog
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
        return await q.answer("این منو مال تو نیست؛ برای خودت بنویس «دنیای من»", show_alert=True)
    OWNER.set(q.from_user.id)
    if data.startswith("ad:"):
        return await admin.callback(q, data[3:])
    if admin.blocked(q.from_user.id):
        return await q.answer(admin.SET["maint_msg"], show_alert=True)
    if data.startswith("rg:"):
        return await commands.rg_callback(q, data[3:])
    await growth.touch(q.from_user.id)
    if data in ("mp", "mpi"):                           # 🗺 نقشه (مینی‌اپ یا تصویر؛ قفل بازی رو نگه نمی‌داره)
        img = data == "mpi" or not config.WEBAPP_URL
        await q.answer("🗺 دارم نقشه رو می‌کشم…" if img else "🗺")
        asyncio.create_task(wow.send_map(q.message.chat.id, q.from_user.id,
                                         private=q.message.chat.type == "private", image=data == "mpi"))
        return
    async with db.LOCK:
        if await db.is_banned(q.from_user.id):
            return await q.answer("🚫", show_alert=True)
        c = await db.load(q.from_user.id)
        if not c:
            return await q.answer("اول بنویس «ثبت نام»", show_alert=True)
        try:
            toast, (text, markup) = await ui.route(c, data.split(":"))
            await db.save(c)
        except Exception:
            logging.exception("cb error")
            log_exc("دکمه: " + (q.data or "")[:60])
            return await q.answer("خطا", show_alert=True)
    frames = cine.take(q.from_user.id)                  # 🎬 نبرد زنده (بعد از آزاد شدن قفل)
    if frames:
        await q.answer(toast)
        return await cine.play(q.message, frames, text, markup)
    try:
        await q.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    await q.answer(toast)


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
            tlog("🔥", "پایان جنگ اتحادها", msg)


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
                    if c and c.get("dil") and not c["dil"].get("sent"):      # رویداد دوگزینه‌ای تازه
                        c["dil"]["sent"] = True
                        await db.save(c)
                        tok = OWNER.set(uid)
                        try:
                            text, mk = growth.s_event(c)
                        finally:
                            OWNER.reset(tok)
                        await notify(uid, "📜 <b>اتفاق تازه‌ای افتاد!</b>\n\n" + text, mk)
        except Exception:
            logging.exception("world_loop")
            log_exc("حلقه‌ی اخبار کشور")


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
            log_exc("حلقه‌ی بازار")


async def war_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await finish_wars()
        except Exception:
            logging.exception("war_loop")
            log_exc("حلقه‌ی جنگ")


async def rumor_loop():
    while True:
        await asyncio.sleep(25 * 60)
        try:
            await world.rumor_step()
        except Exception:
            logging.exception("rumor_loop")


async def snapshot_loop():
    while True:
        await asyncio.sleep(3 * 3600)
        try:
            await world.snapshot_step()
        except Exception:
            logging.exception("snapshot_loop")


async def main():
    await db.setup()
    await events.load()
    await world.init()          # هفته/فصل رسمی؛ قبل از هر load کشوری
    await world.load_news()
    await war.boss_load()
    await crown.load()
    await eco.init_world()
    await admin.load_settings()
    start_log_worker()
    await sync_commands()
    await admin.check_release()
    tlog("🟢", "ربات بالا اومد", f"نسخه <code>{admin.source_hash()}</code> · @{INFO['username']}")
    me = await bot.get_me()
    INFO["username"], INFO["id"] = me.username or "", me.id
    dp.include_router(admin.router)         # پنل ادمین باید قبل از دستورهای عادی بیاد
    dp.include_router(commands.router)      # بعد از هندلرهای بالا ثبت میشه
    asyncio.create_task(world_loop())
    asyncio.create_task(war_loop())
    asyncio.create_task(market_loop())
    asyncio.create_task(world.season_loop())
    asyncio.create_task(world.diplo_loop())
    asyncio.create_task(war.boss_loop())
    asyncio.create_task(crown.loop())
    asyncio.create_task(rumor_loop())
    asyncio.create_task(snapshot_loop())
    await webapp.start(bot)                 # 🌐 مینی‌اپ: نقشه‌ی زنده + فروشگاه
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
