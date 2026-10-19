"""جذب و نگه‌داشتن بازیکن: دعوت دوست، کد هدیه، جعبه‌ی شانس، رویداد دوگزینه‌ای و آمار رشد (برای پنل ادمین)."""
import io
import logging
import random
import re
import time
from urllib.parse import quote

import config
import db
import eco
import engine as E
import events
import guard
import prog
import reg
import world
from core import INFO, notify, tlog
from util import BACK, esc, kb, n


def now():
    return time.time()


# ================================================================== فعالیت روزانه (برای نمودار رشد)
_SEEN = set()


async def touch(uid):
    """ثبت می‌کنه که این بازیکن امروز فعال بوده (هر بازیکن در روز فقط یک بار می‌نویسه)."""
    day = prog.day_id()
    if (day, uid) in _SEEN:
        return
    if len(_SEEN) > 300000:
        _SEEN.clear()
    _SEEN.add((day, uid))
    try:
        await db.ACT.update_one({"_id": f"{day}:{uid}"}, {"$set": {"d": day, "u": uid}}, upsert=True)
    except Exception:
        logging.exception("touch")


# ================================================================== دعوت دوست
def invite_link(uid):
    return f"https://t.me/{INFO.get('username', '')}?start=ref_{uid}"


async def process_referral(uid, inviter_id, username=""):
    """بعد از ساخت کشور صدا زده میشه (بدون قفل). متنی که باید به دعوت‌شده نشون داده بشه یا ''."""
    async with db.LOCK:
        c = await db.load(uid)
        if not c:
            return ""
        c["uname"], c["uname_base"] = username, guard.uname_base(username)
        await db.save(c)
    valid = None
    if inviter_id and inviter_id != uid and not c["inv"].get("by"):
        ok = await db.C.find_one({"_id": inviter_id, "npc": {"$ne": True}}, {"_id": 1})
        if ok and not await db.is_banned(inviter_id):
            valid = inviter_id
    suspect, reasons = await guard.check_registration(c, valid, username)
    if not valid:
        return ""
    day_start = now() - 86400
    today = await db.INVITES.count_documents({"by": valid, "ts": {"$gt": day_start}, "held": False})
    held = suspect or today >= config.INVITE_DAILY_CAP
    await db.INVITES.insert_one({"by": valid, "uid": uid, "ts": now(), "held": held})
    if held:
        tlog("⏸", "جایزه‌ی دعوت نگه داشته شد", f"دعوت‌کننده <code>{valid}</code> → <code>{uid}</code>\n" + (esc(" | ".join(reasons)) or "سقف روزانه"))
        return ""
    msg_inviter = None
    async with db.LOCK:
        c = await db.load(uid)
        inv = await db.load(valid)
        if not c or not inv:
            return ""
        c["inv"]["by"] = valid
        prog.give(c, dict(coins=config.INVITE_NEW_COINS, zero=config.INVITE_NEW_ZERO))
        prog.give(inv, dict(coins=config.INVITE_COINS, zero=config.INVITE_ZERO))
        inv["inv"]["n"] += 1
        k = inv["inv"]["n"]
        msg_inviter = f"🎁 دوستت {esc(c['name'])} ثبت‌نام کرد! جایزه‌ی تو: {config.INVITE_COINS:,}💰 {config.INVITE_ZERO}⚡"
        ms = config.INVITE_MILESTONES.get(k)
        if ms and k not in inv["inv"]["claimed"]:
            inv["inv"]["claimed"].append(k)
            prog.give(inv, dict(coins=ms[0], zero=ms[1]))
            msg_inviter += f"\n🏅 پاداش ویژه‌ی {k} دعوت: {ms[0]:,}💰 {ms[1]}⚡"
            if k >= 10 and "🤝 سفیر" not in inv["titles"]:
                inv["titles"].append("🤝 سفیر")
                world.news(f"🤝 <b>{esc(inv['name'])}</b> به لقب «سفیر» رسید ({k} دعوت)!")
        await db.save(c)
        await db.save(inv)
    await notify(valid, msg_inviter)
    tlog("🤝", "دعوت موفق", f"<code>{valid}</code> → <code>{uid}</code>")
    return f"\n\n🎁 <b>هدیه‌ی دعوت</b>: {config.INVITE_NEW_COINS:,}💰 {config.INVITE_NEW_ZERO}⚡ به خاطر اینکه با لینک دوستت اومدی!"


def s_invite(c):
    link = invite_link(c["_id"])
    k = c["inv"]["n"]
    nxt = next((m for m in sorted(config.INVITE_MILESTONES) if m > k), None)
    t = ["🎁 <b>دعوت دوست</b>",
         f"هر دوستی با لینک تو ثبت‌نام کنه، <b>هر دو</b> جایزه می‌گیرید:",
         f"👤 تو: {config.INVITE_COINS:,}💰 + {config.INVITE_ZERO}⚡ · 👥 دوستت: {config.INVITE_NEW_COINS:,}💰 + {config.INVITE_NEW_ZERO}⚡", "",
         f"🔗 لینک تو:\n<code>{link}</code>", "", f"👥 تا حالا {k} دوست آوردی"]
    if nxt:
        ms = config.INVITE_MILESTONES[nxt]
        t.append(f"🏅 پاداش ویژه‌ی دعوت شماره‌ی {nxt}: {ms[0]:,}💰 {ms[1]}⚡ ({nxt - k} دعوت مونده)")
    t.append(f"ℹ️ سقف {config.INVITE_DAILY_CAP} دعوت در روز؛ حساب‌های چندگانه جایزه نمی‌گیرن.")
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('بیا با هم امپراتوری بسازیم! 👑')}"
    return "\n".join(t), kb([[("📤 ارسال به دوستان", "url:" + share)], BACK])


# ================================================================== کد هدیه (سمت بازیکن)
def code_text(rew, hours=0):
    t = prog.rew_text(rew)
    if rew.get("shield"):
        t += f" 🛡{rew['shield']}h"
    return t or "—"


async def redeem(c, raw):
    code = re.sub(r"\s", "", reg.clean(raw or "")).upper()
    if not code:
        return "مثال: <code>کد EMPIRE100</code>"
    if not reg.throttle(c["_id"], "code", config.CODE_TRIES):
        return "⏳ تلاش‌های زیادی کردی؛ ۱۰ دقیقه‌ی دیگه دوباره امتحان کن"
    d = await db.CODES.find_one({"_id": code})
    if not d or not d.get("active", True):
        return "❌ این کد وجود نداره یا غیرفعاله"
    if d.get("exp") and d["exp"] < now():
        return "⌛ مهلت این کد تموم شده"
    if code in c["codes"] or c["_id"] in d.get("users", []):
        return "🙅 قبلاً از این کد استفاده کردی"
    if d.get("used", 0) >= d.get("max", 1):
        return "😅 ظرفیت این کد پر شده"
    rew = d.get("rew", {})
    prog.give(c, rew)
    if rew.get("shield"):
        c["shield_until"] = max(now(), c["shield_until"]) + rew["shield"] * 3600
    c["codes"].append(code)
    await db.CODES.update_one({"_id": code}, {"$inc": {"used": 1}, "$push": {"users": c["_id"]}})
    tlog("🎟", "کد هدیه استفاده شد", f"<code>{esc(code)}</code> · {esc(c['name'])} · {d.get('used', 0) + 1}/{d.get('max', 1)}")
    return f"🎟 کد <b>{esc(code)}</b> فعال شد!\n🎁 {code_text(rew)}"


# ================================================================== جعبه‌ی شانس
_MULTS = ((0.35, 0.5), (0.65, 0.9), (0.85, 1.5), (0.97, 3.0), (1.01, 8.0))
_PARTS = (("coins", "💰", 1.0), ("food", "🌾", 1.2), ("steel", "⚙️", 5.5), ("tech", "🔬", 4.0))


def lucky_state(c):
    lk = c["lucky"]
    day = prog.day_id()
    if lk.get("d") != day:
        lk.update(d=day, free=False, paid=0)
    lk.setdefault("bonus", 0)
    return lk


def box_next(c):
    """(نوع، هزینه‌ی زیرو) یا (None, None) اگه امروز تموم شده."""
    lk = lucky_state(c)
    if lk["bonus"] > 0:
        return "bonus", 0
    if not lk["free"]:
        return "free", 0
    if lk["paid"] < len(config.LUCKY_PAID):
        return "paid", config.LUCKY_PAID[lk["paid"]]
    return None, None


def open_box(c):
    kind, cost = box_next(c)
    if kind is None:
        return False, "🎰 امروز دیگه جعبه‌ای نمونده؛ فردا برگرد"
    lk = lucky_state(c)
    price = max(10.0, eco.fx_price("PHX")) if eco.WORLD else 100.0
    if kind == "paid":
        if c["fx"].get("PHX", 0) < cost:
            return False, f"⚡ {cost} زیرو لازمه"
        c["fx"]["PHX"] -= cost
        lk["paid"] += 1
        budget = cost * price * 0.8
    else:
        if kind == "bonus":
            lk["bonus"] -= 1
        else:
            lk["free"] = True
        budget = 600 + c.get("gdp", 0) * 0.6
    r, mult = random.random(), 1.0
    for edge, m in _MULTS:
        if r < edge:
            mult = m
            break
    budget *= mult
    rew, left = {}, budget
    picks = random.sample(_PARTS, 2 if mult >= 0.9 else 1)
    for i, (key, _, val) in enumerate(picks):
        share = left if i == len(picks) - 1 else left * random.uniform(0.4, 0.7)
        rew[key] = max(1, int(share / val))
        left -= share
    extra = []
    if kind != "paid" and random.random() < 0.04:
        rew["zero"] = 1
    if random.random() < 0.03:
        c["shield_until"] = max(now(), c["shield_until"]) + 6 * 3600
        extra.append("🛡 +۶ ساعت سپر")
    prog.give(c, rew)
    prog.bump(c, "lucky")
    face = "🎰💥 جکپات!" if mult >= 8 else "🎰✨ شانس آوردی!" if mult >= 3 else "🎰"
    if mult >= 8:
        world.news(f"🎰 <b>{esc(c['name'])}</b> جکپات جعبه‌ی شانس رو برد!", important=True)
    return True, f"{face} {prog.rew_text(rew)}" + (" · " + " · ".join(extra) if extra else "")


def s_lucky(c):
    lk = lucky_state(c)
    kind, cost = box_next(c)
    t = ["🎰 <b>جعبه‌ی شانس</b>", "هر روز یه جعبه‌ی رایگان؛ با زیرو می‌تونی بیشتر باز کنی (هر بار گرون‌تر).", ""]
    t.append(f"🎁 رایگان امروز: {'✅ باز شد' if lk['free'] else '🟢 آماده'}")
    if lk["bonus"]:
        t.append(f"🎫 جعبه‌ی هدیه: {lk['bonus']}")
    t.append(f"⚡ بازهای زیرویی امروز: {lk['paid']}/{len(config.LUCKY_PAID)}")
    t.append(f"⚡ موجودی تو: {c['fx'].get('PHX', 0):,.1f} زیرو")
    rows = []
    if kind in ("free", "bonus"):
        rows.append([("🎁 باز کردن" + (" (رایگان)" if kind == "free" else " (جعبه‌ی هدیه)"), "lb:open")])
    elif kind == "paid":
        rows.append([(f"⚡ باز کردن · {cost} زیرو", "lb:open")])
    else:
        t.append("امروز دیگه جعبه‌ای نمونده 😴")
    rows.append([("💱 خرید زیرو", "x")])
    return "\n".join(t), kb(rows + [BACK])


# ================================================================== رویداد دوگزینه‌ای (تصمیم بازیکن)
def s_event(c, note=None):
    txt = events.dil_text(c)
    if not txt:
        return (note + "\n\n" if note else "") + "📜 الان رویدادی منتظر تصمیم تو نیست؛ هر از گاهی یه اتفاق تازه میفته 🌍", kb([BACK])
    a, b = events.dil_options(c)
    return (note + "\n\n" if note else "") + txt, kb([[("🅰️ " + a[:30], "ev:a")], [("🅱️ " + b[:30], "ev:b")], BACK])


# ================================================================== مسیریابی دکمه‌ها
async def route(c, p):
    t = p[0]
    if t == "iv":
        return None, s_invite(c)
    if t == "lb":
        toast = None
        if len(p) > 1 and p[1] == "open":
            ok, toast = open_box(c)
            if ok:
                text, mk = s_lucky(c)
                return None, (toast + "\n\n" + text, mk)
        return toast, s_lucky(c)
    if t == "ev":
        if len(p) > 1 and p[1] in ("a", "b"):
            r = events.resolve(c, p[1])
            return None, s_event(c, r or "این رویداد دیگه معتبر نیست")
        return None, s_event(c)
    return None, s_invite(c)


# ================================================================== آمار رشد (برای پنل ادمین)
async def series(days=14):
    """[{d, new, act}] از قدیمی به جدید."""
    t = now()
    ids = [prog.day_id(t - i * 86400) for i in range(days - 1, -1, -1)]
    new = {i: 0 for i in ids}
    async for d in db.C.find({"npc": {"$ne": True}, "created": {"$gt": t - days * 86400 - 86400}}, {"created": 1}):
        k = prog.day_id(d["created"])
        if k in new:
            new[k] += 1
    act = {i: 0 for i in ids}
    async for g in db.ACT.aggregate([{"$match": {"d": {"$gte": ids[0]}}}, {"$group": {"_id": "$d", "n": {"$sum": 1}}}]):
        if g["_id"] in act:
            act[g["_id"]] = g["n"]
    return [{"d": i, "new": new[i], "act": act[i]} for i in ids]


async def retention(days=7):
    """بازگشت روز بعد (D1) برای ثبت‌نام‌های چند روز اخیر: [(روز، تعداد، درصد)]"""
    t = now()
    out = []
    for i in range(days, 0, -1):
        day, nxt = prog.day_id(t - i * 86400), prog.day_id(t - (i - 1) * 86400)
        ids = [d["_id"] async for d in db.C.find({"npc": {"$ne": True}}, {"_id": 1, "created": 1})
               if prog.day_id(d["created"]) == day]
        if not ids:
            out.append((day, 0, 0.0))
            continue
        back = await db.ACT.count_documents({"d": nxt, "u": {"$in": ids}})
        out.append((day, len(ids), back / len(ids) * 100))
    return out


def text_chart(rows, key, width=12):
    mx = max([r[key] for r in rows] + [1])
    return "\n".join(f"<code>{r['d'][5:]}</code> {'█' * max(1 if r[key] else 0, int(r[key] / mx * width))} {r[key]}" for r in rows)


def chart_png(rows):
    """نمودار تصویری (نیاز به matplotlib؛ اگه نصب نبود None). برچسب‌ها لاتین‌ان تا مشکل فونت فارسی نباشه."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    xs = [r["d"][5:] for r in rows]
    ax.bar(xs, [r["new"] for r in rows], color="#2e8b57", label="New players")
    ax.plot(xs, [r["act"] for r in rows], color="#1f6feb", marker="o", label="Active (DAU)")
    ax.set_title("EMPIRE ZERO - growth")
    ax.legend()
    ax.grid(alpha=.3)
    plt.xticks(rotation=45, fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
