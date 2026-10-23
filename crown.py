"""👑 تاج امپراتوری.

یه تاج برای کل جهان. صاحبش قوی‌ترین کشوره و همه‌ی جهان می‌دونن کیه. دو راه برای گرفتنش هست:
  ⚔️ امپراتور رو توی جنگ شکست بده   ← تاج همون لحظه مال توئه (+ جایزه‌ی نقدی)
  🏆 قدرتت ≥ ۱۱۰٪ امپراتور بشه        ← تاج خودکار می‌رسه بهت
امتیاز تاج: خراج ساعتی، فرمان نظامی اضافه، و اسم تو روی همه‌ی نقشه‌ها و اخبار جهان.
بعد از هر دست‌به‌دست شدن، تاج ۳۰ دقیقه محافظت داره (جلوی پینگ‌پونگ).
"""
import asyncio
import logging
import time

import config
import db
import engine as E
import world
from core import log_exc, notify, tlog
from util import BACK, esc, kb, n

CROWN = {"holder": None, "name": "", "emblem": "", "since": 0.0, "guard": 0.0, "paid": 0.0, "hist": []}
_KEYS = tuple(CROWN)


def now():
    return time.time()


def is_holder(uid):
    return CROWN["holder"] is not None and CROWN["holder"] == uid


def tag(uid):
    return "👑 " if is_holder(uid) else ""


def holder_name():
    return CROWN["name"] if CROWN["holder"] is not None else ""


def line(c=None):
    """یه خط کوتاه برای داشبورد."""
    if CROWN["holder"] is None:
        return f"👑 تاج امپراتوری صاحب نداره؛ اولین نفری که به {n(config.CROWN_MIN_SCORE)} امتیاز برسه امپراتور میشه!"
    if c is not None and is_holder(c["_id"]):
        return f"👑 <b>تو امپراتور جهانی!</b> خراج {n(config.CROWN_TRIBUTE_H)}💰 در ساعت + {config.CROWN_ORDERS}⚡ فرمان اضافه"
    return f"👑 امپراتور جهان: {CROWN['emblem']} <b>{esc(CROWN['name'])}</b>"


# ------------------------------------------------------------------ ذخیره / بارگذاری
async def load():
    d = await db.META.find_one({"_id": "crown"})
    if d:
        for k in _KEYS:
            if k in d:
                CROWN[k] = d[k]
    config.EMPEROR["id"] = CROWN["holder"]


async def _save():
    try:
        await db.META.replace_one({"_id": "crown"}, {"_id": "crown", **CROWN}, upsert=True)
    except Exception:
        logging.exception("crown save")


def _persist():
    try:
        asyncio.get_running_loop().create_task(_save())
    except RuntimeError:
        pass


def _set_holder(uid, name, emblem, how):
    t = now()
    if CROWN["holder"] is not None:
        CROWN["hist"].append({"id": CROWN["holder"], "name": CROWN["name"], "emblem": CROWN["emblem"],
                              "from": CROWN["since"], "to": t, "how": how})
        CROWN["hist"] = CROWN["hist"][-12:]
    CROWN.update(holder=uid, name=name, emblem=emblem, since=t, guard=t + config.CROWN_GUARD_MIN * 60, paid=t)
    config.EMPEROR["id"] = uid
    _persist()


def _clear(why):
    if CROWN["holder"] is None:
        return
    CROWN["hist"].append({"id": CROWN["holder"], "name": CROWN["name"], "emblem": CROWN["emblem"],
                          "from": CROWN["since"], "to": now(), "how": why})
    CROWN["hist"] = CROWN["hist"][-12:]
    CROWN.update(holder=None, name="", emblem="", since=0.0, guard=0.0, paid=0.0)
    config.EMPEROR["id"] = None
    _persist()


# ------------------------------------------------------------------ گرفتن تاج با جنگ
def seize(att, dfn):
    """مهاجم (att) امپراتور (dfn) رو توی جنگ برده. (متن اضافه برای مهاجم، متن اضافه برای مدافع) رو برمی‌گردونه.
    فقط توی حافظه کار می‌کنه؛ ذخیره‌ی کشورها رو خود do_attack انجام میده."""
    left = CROWN["guard"] - now()
    if left > 0:
        return (f"\n\n👑 امپراتور رو شکست دادی، ولی تاج هنوز {int(left // 60) + 1} دقیقه‌ی دیگه توی حفاظته؛ "
                f"بعدش دوباره بزن!", "")
    att["treasury"] += config.CROWN_BOUNTY
    _set_holder(att["_id"], att["name"], att.get("emblem", "🏛"), "جنگ")
    world.news(f"👑 <b>{esc(att['name'])}</b> امپراتور <b>{esc(dfn['name'])}</b> رو توی جنگ شکست داد و "
               f"<b>تاج امپراتوری</b> رو گرفت!", important=True)
    tlog("👑", "تاج دست‌به‌دست شد (جنگ)", f"{esc(att['name'])} ← {esc(dfn['name'])}")
    return (f"\n\n👑 <b>تاج امپراتوری رو گرفتی!</b> +{n(config.CROWN_BOUNTY)}💰 · خراج ساعتی {n(config.CROWN_TRIBUTE_H)}💰 "
            f"· +{config.CROWN_ORDERS}⚡ فرمان\n🛡 تاج {config.CROWN_GUARD_MIN} دقیقه محافظت داره",
            "\n\n💔 <b>تاج امپراتوری رو از دست دادی!</b> برای پس‌گرفتنش به «تاج» سر بزن.")


# ------------------------------------------------------------------ گرفتن تاج با قدرت (حلقه‌ی پس‌زمینه)
async def step():
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    best = None                      # (امتیاز، doc)
    cur = None
    async for d in db.C.find({"npc": {"$ne": True}}):
        if d["_id"] in banned:
            continue
        try:
            E.defaults(d)
            sc = E.score(d)
        except Exception:
            continue
        if d["_id"] == CROWN["holder"]:
            cur = (sc, d)
        if best is None or sc > best[0]:
            best = (sc, d)
    if CROWN["holder"] is not None and cur is None:          # کشور امپراتور پاک/ریست/بن شد
        _clear("حذف")
        world.news("👑 تاج امپراتوری صاحبش رو از دست داد و خالیه!")
    if best is None or best[0] < config.CROWN_MIN_SCORE:
        return
    sc, d = best
    if CROWN["holder"] is None:
        _set_holder(d["_id"], d["name"], d.get("emblem", "🏛"), "قدرت")
        world.news(f"👑 <b>{esc(d['name'])}</b> قدرتمندترین کشور جهان شد و <b>امپراتور</b> اعلام شد!", important=True)
        tlog("👑", "امپراتور جدید", esc(d["name"]))
        await notify(d["_id"], "👑 <b>تو امپراتور جهان شدی!</b>\nقدرتمندترین کشور دنیایی. «تاج» بنویس تا امتیازها رو ببینی.")
        return
    if d["_id"] == CROWN["holder"] or now() < CROWN["guard"]:
        return
    if sc >= cur[0] * config.CROWN_RISE:
        old = dict(CROWN)
        _set_holder(d["_id"], d["name"], d.get("emblem", "🏛"), "قدرت")
        world.news(f"👑 <b>{esc(d['name'])}</b> از <b>{esc(old['name'])}</b> قوی‌تر شد و <b>تاج امپراتوری</b> رو گرفت!", important=True)
        tlog("👑", "تاج دست‌به‌دست شد (قدرت)", f"{esc(d['name'])} ← {esc(old['name'])}")
        await notify(d["_id"], "👑 <b>تو امپراتور جهان شدی!</b> قدرتت از امپراتور قبلی بیشتر شد.")
        await notify(old["holder"], "💔 <b>تاج امپراتوری رو از دست دادی!</b> یه کشور از تو قوی‌تر شد. «تاج» بنویس و پسش بگیر.")


async def pay_tribute():
    h = CROWN["holder"]
    if h is None:
        return
    t = now()
    hrs = min(1.0, max(0.0, (t - CROWN["paid"]) / 3600))
    if hrs <= 0:
        return
    CROWN["paid"] = t
    async with db.LOCK:
        c = await db.load(h)
        if c:
            c["treasury"] += config.CROWN_TRIBUTE_H * hrs
            await db.save(c)
    _persist()


async def loop():
    while True:
        await asyncio.sleep(config.CROWN_STEP)
        try:
            await step()
            await pay_tribute()
        except Exception:
            logging.exception("crown_loop")
            log_exc("حلقه‌ی تاج")


# ------------------------------------------------------------------ صفحه‌ی تاج
def _dur(sec):
    sec = int(max(0, sec))
    if sec >= 86400:
        return f"{sec // 86400} روز و {sec % 86400 // 3600} ساعت"
    if sec >= 3600:
        return f"{sec // 3600} ساعت و {sec % 3600 // 60} دقیقه"
    return f"{max(1, sec // 60)} دقیقه"


async def screen(c):
    t = ["👑 <b>تاج امپراتوری جهان</b>", ""]
    rows = []
    h = CROWN["holder"]
    if h is None:
        t += ["تاج هنوز صاحب نداره!",
              f"اولین کشوری که قدرتش به <b>{n(config.CROWN_MIN_SCORE)}</b> برسه امپراتور میشه."]
    else:
        d = await db.C.find_one({"_id": h})
        sc, land = 0, "?"
        if d:
            E.defaults(d)
            sc, land = E.score(d), d.get("land", config.LAND_START)
        t += [f"{CROWN['emblem']} <b>{esc(CROWN['name'])}</b> — امپراتور جهان",
              f"⏳ {_dur(now() - CROWN['since'])} است که حکومت می‌کنه",
              f"🏆 قدرت: <b>{n(sc)}</b> · 🏞 {land} استان"]
        left = CROWN["guard"] - now()
        if left > 0:
            t.append(f"🛡 تاج تازه دست‌به‌دست شده؛ {_dur(left)} دیگه امنه")
        if is_holder(c["_id"]):
            t += ["", "🎉 <b>تو امپراتوری!</b> همه می‌خوان تاجت رو بگیرن؛ ارتشت رو قوی نگه دار."]
        else:
            mine = E.score(c)
            need = int(sc * config.CROWN_RISE)
            t.append(f"📍 قدرت تو: {n(mine)} · برای گرفتن تاج با قدرت: {n(need)}")
            rows.append([("🎯 حمله به امپراتور", f"w:pick:{h}")])
    t += ["", f"🎁 <b>امتیاز تاج</b>: 💰 {n(config.CROWN_TRIBUTE_H)} خراج در ساعت · ⚡ +{config.CROWN_ORDERS} فرمان نظامی · "
              "👑 اسمت روی نقشه و اخبار جهان",
          f"⚔️ <b>گرفتن تاج</b>: امپراتور رو توی جنگ شکست بده (+{n(config.CROWN_BOUNTY)}💰) "
          f"یا قدرتت رو ≥ {int(config.CROWN_RISE * 100)}٪ اون کن"]
    hist = CROWN["hist"][-5:][::-1]
    if hist:
        t += ["", "📜 <b>امپراتورهای قبلی</b>"]
        for x in hist:
            t.append(f"• {x.get('emblem', '🏛')} {esc(x['name'])} — {_dur(x['to'] - x['from'])}")
    rows.append([("🗺 نقشه‌ی جهان", "mp"), ("🔄", "cr")])
    return "\n".join(t), kb(rows + [BACK])
