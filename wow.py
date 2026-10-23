"""🗺 دستور نقشه‌ی جهان و 👑 تاج (به همون CMDS و دیسپچر commands.py وصل میشه).

نقشه توی ترد جدا کشیده میشه (قفل دیتابیس رو نگه نمی‌داره) و ۶۰ ثانیه کش میشه؛ هر کاربر فقط حلقه‌ی خودش رو روش می‌بینه.
"""
import asyncio
import hashlib
import logging
import time

import config
import crown
import db
import worldmap
from commands import cmd
from core import bot, log_exc
from util import esc, n

_CACHE = {"sig": None, "lay": None, "ts": 0.0}
_SEM = asyncio.Semaphore(1)
_LAST = {}            # uid → آخرین درخواست نقشه (ضداسپم)
MAP_GAP = 15
MAP_TTL = 60


async def _seeds(ids):
    """پایتخت هر کشور برای همیشه ثابته (توی دیتابیس نگه‌داری میشه) تا نقشه‌ی بازیکن‌ها جابه‌جا نشه."""
    doc = await db.META.find_one({"_id": "mapseeds"}) or {}
    m = dict(doc.get("m", {}))
    nxt = max([int(v) for v in m.values()] + [-1]) + 1
    changed = False
    for cid in ids:
        if str(cid) not in m:
            m[str(cid)] = nxt
            nxt += 1
            changed = True
    if changed:
        await db.META.replace_one({"_id": "mapseeds"}, {"_id": "mapseeds", "m": m}, upsert=True)
    return {int(k): int(v) for k, v in m.items()}


async def _layout():
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    docs = await db.C.find({}, {"name": 1, "land": 1, "npc": 1, "created": 1, "emblem": 1}).to_list(5000)
    docs = [d for d in docs if d["_id"] not in banned]
    docs.sort(key=lambda d: (d.get("created", 0), d["_id"]))       # کشور جدیدتر = پایتخت بعدی
    cs = [dict(id=d["_id"], name=d.get("name", "?"), land=int(d.get("land", config.LAND_START)),
               npc=bool(d.get("npc")), emblem=d.get("emblem", "🏛")) for d in docs]
    sig = hashlib.md5(repr([(c["id"], c["land"], c["name"]) for c in cs]).encode()).hexdigest()
    if _CACHE["sig"] == sig and time.time() - _CACHE["ts"] < 600:
        return _CACHE["lay"]
    seeds = await _seeds([c["id"] for c in cs])
    lay = await asyncio.to_thread(worldmap.layout, cs, seeds)
    _CACHE.update(sig=sig, lay=lay, ts=time.time())
    return lay


def _caption(lay, uid):
    cs, ent = lay["cs"], lay["entries"]
    t = ["🗺 <b>نقشه‌ی جهان EMPIRE ZERO</b>"]
    if crown.CROWN["holder"] is not None:
        t.append(f"👑 امپراتور: {crown.CROWN['emblem']} <b>{esc(crown.CROWN['name'])}</b>")
    t.append(f"🏞 {lay['claimed']} استان تصرف‌شده · {len(cs)} کشور")
    t.append("")
    mine = None
    for num, c, rgb, em in worldmap.legend(lay, 10):
        crown_mark = " 👑" if crown.is_holder(c["id"]) else ""
        npc_mark = " 🤖" if c.get("npc") else ""
        me = " 📍" if c["id"] == uid else ""
        t.append(f"{num}. {em} {c.get('emblem', '🏛')} {esc(c['name'][:18])}{crown_mark}{npc_mark} — {c['land']}{me}")
        if c["id"] == uid:
            mine = True
    if not mine and uid is not None:
        for k, c in enumerate(cs):
            if c["id"] == uid:
                rank = lay["ranked"].index(k) + 1
                t.append(f"…\n📍 تو: {esc(c['name'][:18])} — {c['land']} استان · رتبه‌ی {rank} (حلقه‌ی سفید-قرمز)")
                break
    t.append("\n💡 با «تسخیر» استان بگیر؛ همین‌جا نقشه عوض میشه!")
    return "\n".join(t)[:1000]


async def make_map(uid):
    """(پیش‌نمایش JPEG، نسخه‌ی کامل PNG، کپشن). نقشه‌ی اصلی کش میشه؛ فقط حلقه‌ی «تو» برای هر نفر اضافه میشه."""
    async with _SEM:
        lay = await _layout()
        key = (_CACHE["sig"], crown.CROWN["holder"], crown.CROWN["name"])
        if _CACHE.get("key") != key:
            img, pos, S = await asyncio.to_thread(worldmap.render, lay, crown.CROWN["holder"], crown.CROWN["name"])
            _CACHE.update(key=key, img=img, pos=pos, S=S)
        img, pos, S = _CACHE["img"], _CACHE["pos"], _CACHE["S"]

        def enc():
            m = worldmap.mark(img, pos, S, uid)
            return worldmap.to_preview(m), worldmap.to_png(m)
        prev, full = await asyncio.to_thread(enc)
    return prev, full, _caption(lay, uid)


async def send_map(chat_id, uid, reply_to=None):
    from aiogram.types import BufferedInputFile
    now = time.time()
    if now - _LAST.get(uid, 0) < MAP_GAP:
        try:
            await bot.send_message(chat_id, f"🗺 نقشه رو تازه گرفتی؛ {int(MAP_GAP - (now - _LAST.get(uid, 0))) + 1} ثانیه صبر کن",
                                   reply_to_message_id=reply_to)
        except Exception:
            pass
        return
    _LAST[uid] = now
    try:
        prev, full, cap = await make_map(uid)
        msg = await bot.send_photo(chat_id, BufferedInputFile(prev, "empirezero_map.jpg"), caption=cap, reply_to_message_id=reply_to)
        await bot.send_document(chat_id, BufferedInputFile(full, "empirezero_map_FULL.png"),
                                caption="🔍 <b>نسخه‌ی کامل با کیفیت بالا</b> (برای زوم روی استان‌ها و اسم کشورها؛ این رو باز کن و زوم کن)",
                                reply_to_message_id=msg.message_id)
    except Exception:
        logging.exception("send_map")
        log_exc("نقشه‌ی جهان")
        try:
            await bot.send_message(chat_id, "⚠️ نقشه الان نتونست ساخته بشه؛ چند لحظه‌ی دیگه دوباره امتحان کن",
                                   reply_to_message_id=reply_to)
        except Exception:
            pass


# ------------------------------------------------------------------ دستورها
@cmd("map", "نقشه", "نقشه جهان", "نقشه‌ی جهان", "نقشه دنیا", need=False)
async def h_map(m, c, a):
    asyncio.create_task(send_map(m.chat.id, m.from_user.id, reply_to=m.message_id))
    return None


@cmd("crown", "تاج", "امپراتور", "تاج امپراتوری", "امپراتوری", need=True)
async def h_crown(m, c, a):
    return await crown.screen(c)
