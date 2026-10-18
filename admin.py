"""پنل ادمین عمیق EMPIRE ZERO — فقط توی چت خصوصی با ربات (/admin).

بخش‌ها: آمار زنده · مدیریت کامل کشور (منابع، ساختمان، ارتش، ارز، سپر، بن، ریست/حذف) ·
اقتصاد جهانی (قیمت ارز/کالا، نرخ بانک مرکزی، شوک بازار) · اتحادها و جنگ‌ها · آگهی‌های بازار ·
NPCها · پیام همگانی · هدیه‌ی همگانی · مسدودها · تنظیمات زنده (حالت تعمیر، ثبت‌نام، ضرایب) ·
مدیریت ادمین‌ها · لاگ · بکاپ.

ورودی‌های متنی (مقدار، آیدی، پیام ...) با یک «حالت انتظار» ساده گرفته میشن: ST[uid]["wait"].
"""
import asyncio
import glob
import gzip
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from bson import json_util

import config
import db
import eco
import engine as E
import reg
from config import ASSETS, B, ITEMS, U
import core
from core import bot, sync_commands
from util import OWNER, digits, esc, kb, n

router = Router()
log = logging.getLogger("admin")

# ------------------------------------------------------------------ تنظیمات زنده (ذخیره توی دیتابیس)
DEFAULTS = {"maint": False, "maint_msg": "🛠 ربات در حال بروزرسانیه؛ کمی بعد برگرد.",
            "reg_open": True, "admins": [], "tun": {}, "notify_updates": True, "update_note": "", "log_on": True}
SET = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in DEFAULTS.items()}

# نام → (توضیح، نوع، حداقل، حداکثر)
TUNABLES = {
    "TIME_SCALE":    ("⏱ سرعت زمان بازی (×)", float, 0.1, 50),
    "DAILY_MULT":    ("🎁 ضریب جایزه‌ی روزانه", float, 0, 100),
    "WORK_MULT":     ("🧳 ضریب درآمد /work", float, 0, 100),
    "CMD_GAP":       ("⌛ فاصله‌ی دستورها (ثانیه)", float, 0, 30),
    "NPC_CD":        ("🌍 کولداون NPC (ثانیه)", int, 0, 86400),
    "STRIKE_CD":     ("⚔️ کولداون ضربه‌ی اتحاد (ثانیه)", int, 0, 86400),
    "ALLY_WAR_H":    ("🔥 مدت جنگ اتحاد (ساعت)", float, 0.1, 72),
    "ALLY_MAX":      ("🤝 سقف اعضای اتحاد", int, 2, 200),
    "LOAN_FEE":      ("🏛 کارمزد وام (۰ تا ۰٫۵)", float, 0, 0.5),
    "FX_FEE":        ("💱 کارمزد ارز (۰ تا ۰٫۵)", float, 0, 0.5),
    "LIST_FEE":      ("📣 کارمزد آگهی (۰ تا ۰٫۵)", float, 0, 0.5),
    "MARKET_SPREAD": ("🏪 اسپرد بازار (۰ تا ۰٫۹)", float, 0, 0.9),
    "LIST_MAX":      ("📣 سقف آگهی هر نفر", int, 1, 100),
    "DEP_MAX":       ("📥 سقف سپرده", int, 0, 10 ** 12),
    "DEP_INT_CAP":   ("📥 سقف سود سپرده", int, 0, 10 ** 12),
}
ORIG = {k: getattr(config, k) for k in TUNABLES}      # مقدار پیش‌فرض کد

# فیلد → (ایموجی، نام، حداقل، حداکثر)
FIELDS = {
    "treasury": ("💰", "خزانه", None, None), "food": ("🌾", "غذا", 0, None),
    "steel": ("⚙️", "فولاد", 0, None), "pop": ("👥", "جمعیت", 0, None),
    "tech": ("🔬", "پژوهش", 0, None), "sat": ("😊", "رضایت", 0, 100),
    "unrest": ("🚨", "ناآرامی", 0, 100), "literacy": ("🎓", "سواد", 0, 100),
    "health": ("🏥", "سلامت", 0, 100), "security": ("🚓", "امنیت", 0, 100),
    "weariness": ("🪖", "جنگ‌خستگی", 0, None), "tax": ("🧾", "مالیات٪", 0, 100),
    "bank.dep": ("📥", "سپرده", 0, None), "bank.loan": ("🔻", "وام", 0, None),
    "wins": ("🏆", "بردها", 0, None), "losses": ("💀", "باخت‌ها", 0, None),
    "reforms": ("🗳", "اصلاحات", 0, None),
}
INTS = {"wins", "losses", "tax", "reforms"}

ST = {}          # uid → {"tid", "aid", "wait", "bc", "gift", "ts"}
BG = set()       # نگه‌داشتن رفرنس تسک‌های پس‌زمینه
WAIT_TTL = 600


def st(uid):
    return ST.setdefault(uid, {"tid": None, "aid": None, "wait": None, "bc": None, "gift": None})


def is_admin(uid):
    return uid in config.ADMINS


def is_owner(uid):
    return uid == config.OWNER_ID


def blocked(uid):
    """حالت تعمیر: همه به‌جز ادمین‌ها."""
    return bool(SET["maint"]) and uid not in config.ADMINS


def rebuild_admins():
    config.ADMINS.clear()
    config.ADMINS.update(config.BASE_ADMINS)
    config.ADMINS.update(int(x) for x in SET["admins"])


def apply_settings():
    core.LOG["on"] = bool(SET.get("log_on", True))
    for k, v in SET["tun"].items():
        if k in TUNABLES:
            setattr(config, k, v)
    rebuild_admins()


async def load_settings():
    d = await db.META.find_one({"_id": "settings"}) or {}
    for k, v in DEFAULTS.items():
        SET[k] = d.get(k, v.copy() if isinstance(v, (dict, list)) else v)
    apply_settings()


async def save_settings():
    await db.META.replace_one({"_id": "settings"}, {"_id": "settings", **SET}, upsert=True)


async def alog(uid, text):
    core.tlog("🛠", "اکشن ادمین", f"<code>{uid}</code> · {esc(text)}")
    try:
        await db.db.adminlog.insert_one({"ts": time.time(), "by": uid, "text": text})
    except Exception:
        log.exception("adminlog")


# ------------------------------------------------------------------ ابزارها
def fdate(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else "—"


def parse_num(s):
    """'5000' یا '+5k' → اضافه · '-200' → کم · '=1000' → مقدار دقیق. نامعتبر → None"""
    s = digits(s).replace(",", "").replace("٬", "").replace("٫", ".").strip().lower()
    mode = "add"
    if s.startswith("="):
        mode, s = "set", s[1:].strip()
    mult = 1
    if s[-1:] in ("k", "m", "b"):
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[s[-1]]
        s = s[:-1]
    try:
        v = float(s) * mult
    except ValueError:
        return None
    return (mode, v) if v == v and abs(v) < 1e15 else None


def _get(c, k):
    cur = c
    for p in k.split("."):
        cur = cur.get(p, 0) if isinstance(cur, dict) else 0
    return cur


def _set(c, k, v):
    ps = k.split(".")
    cur = c
    for p in ps[:-1]:
        cur = cur.setdefault(p, {})
    cur[ps[-1]] = v


def clampv(v, lo, hi):
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def apply_field(c, key, mode, v):
    _, _, lo, hi = FIELDS[key]
    old = _get(c, key)
    new = clampv(v if mode == "set" else old + v, lo, hi)
    if key in INTS:
        new = int(new)
    _set(c, key, new)
    return old, new


async def mutate(tid, fn):
    """کشور رو زیر قفل می‌خونه، fn روش اجرا می‌کنه و ذخیره می‌کنه. کشور نبود → None"""
    async with db.LOCK:
        c = await db.load(tid)
        if not c:
            return None
        r = fn(c)
        await db.save(c)
    return r


def pager(page, total, per, make):
    pages = max(1, (total + per - 1) // per)
    row = []
    if page > 0:
        row.append(("⬅️", make(page - 1)))
    row.append((f"{page + 1}/{pages}", "ad:noop"))
    if page < pages - 1:
        row.append(("➡️", make(page + 1)))
    return row


def grid(btns, k=2):
    return [btns[i:i + k] for i in range(0, len(btns), k)]


HOME = [("🛠 پنل", "ad:home")]


def cancel_row(back="ad:home"):
    return [("❌ انصراف", back)]


def note_(note):
    return f"{note}\n\n" if note else ""


def spawn(coro):
    t = asyncio.create_task(coro)
    BG.add(t)
    t.add_done_callback(BG.discard)


# ------------------------------------------------------------------ صفحه‌ی اصلی و آمار
async def s_home(note=""):
    now = E.now()
    users = await db.C.count_documents({"npc": {"$ne": True}})
    act = await db.C.count_documents({"npc": {"$ne": True}, "last_tick": {"$gt": now - 86400}})
    bans = await db.BANS.count_documents({})
    t = [f"{note_(note)}🛠 <b>پنل مدیریت {config.BOT_NAME}</b>", "",
         f"👥 بازیکن: <b>{n(users)}</b> · فعال ۲۴ ساعت: <b>{n(act)}</b> · 🚫 مسدود: <b>{bans}</b>",
         f"🔧 حالت تعمیر: {'🔴 روشن' if SET['maint'] else '🟢 خاموش'} · ثبت‌نام: {'🟢 باز' if SET['reg_open'] else '🔴 بسته'}",
         f"⏱ سرعت زمان: ×{config.TIME_SCALE:g} · 🎁 جایزه ×{config.DAILY_MULT:g}"]
    rows = [[("📊 آمار زنده", "ad:stats"), ("👤 کشورها", "ad:cl:0:s")],
            [("🔎 جستجوی بازیکن", "ad:find"), ("🌐 اقتصاد جهانی", "ad:w")],
            [("🤝 اتحادها", "ad:al:0"), ("⚔️ جنگ‌ها", "ad:wr")],
            [("🏪 آگهی‌ها", "ad:ls:0"), ("🌍 NPCها", "ad:np")],
            [("📣 پیام همگانی", "ad:bc"), ("🎁 هدیه‌ی همگانی", "ad:gf")],
            [("🚫 مسدودها", "ad:bn:0"), ("⚙️ تنظیمات", "ad:st")],
            [("🛡 ادمین‌ها", "ad:am"), ("📜 لاگ", "ad:lg")],
            [("💾 بکاپ", "ad:bk"), ("🔄 رفرش", "ad:home")],
            [("🔙 منوی بازی", "m")]]
    return "\n".join(t), kb(rows)


async def players(limit=3000):
    docs = await db.C.find({"npc": {"$ne": True}}).to_list(limit)
    for d in docs:
        E.defaults(d)
    return docs


async def s_stats():
    now = E.now()
    P = {"npc": {"$ne": True}}
    users = await db.C.count_documents(P)
    new24 = await db.C.count_documents({**P, "created": {"$gt": now - 86400}})
    new7 = await db.C.count_documents({**P, "created": {"$gt": now - 7 * 86400}})
    act1 = await db.C.count_documents({**P, "last_tick": {"$gt": now - 3600}})
    act24 = await db.C.count_documents({**P, "last_tick": {"$gt": now - 86400}})
    shield = await db.C.count_documents({**P, "shield_until": {"$gt": now}})
    agg = await db.C.aggregate([{"$match": P}, {"$group": {
        "_id": None, "t": {"$sum": "$treasury"}, "p": {"$sum": "$pop"}, "f": {"$sum": "$food"},
        "s": {"$sum": "$steel"}, "dep": {"$sum": "$bank.dep"}, "loan": {"$sum": "$bank.loan"},
        "phx": {"$sum": "$fx.PHX"}, "w": {"$sum": "$wins"}, "l": {"$sum": "$losses"}}}]).to_list(1)
    a = agg[0] if agg else {}
    g = await db.G.count_documents({})
    al = await db.A.count_documents({})
    wars = await db.W.count_documents({"active": True})
    ls = await db.M.count_documents({})
    rich = await db.C.find(P).sort("treasury", -1).limit(5).to_list(5)
    pw = sorted(await players(), key=E.score, reverse=True)[:5]
    w = eco.WORLD
    t = ["📊 <b>آمار زنده</b>", "",
         f"👥 بازیکن {n(users)} · جدید ۲۴ساعت {n(new24)} · ۷روز {n(new7)}",
         f"🟢 فعال ۱ساعت {n(act1)} · ۲۴ساعت {n(act24)} · 🛡 دارای سپر {n(shield)}",
         f"💬 گروه {n(g)} · 🤝 اتحاد {n(al)} · 🔥 جنگ فعال {wars} · 📣 آگهی {ls}", "",
         "<b>اقتصاد کل بازیکن‌ها</b>",
         f"💰 خزانه {n(a.get('t', 0))} · 🏦 سپرده {n(a.get('dep', 0))} · 🔻 وام {n(a.get('loan', 0))}",
         f"👥 جمعیت {n(a.get('p', 0))} · 🌾 {n(a.get('f', 0))} · ⚙️ {n(a.get('s', 0))}",
         f"🔥 PHX در دست مردم {a.get('phx', 0):,.1f} · ⚔️ جنگ‌ها {n(a.get('w', 0))}/{n(a.get('l', 0))}",
         f"🏛 نرخ بانک مرکزی {w.get('rate', 0) * 100:.1f}٪{' (قفل)' if w.get('rate_lock') is not None else ''} · ذخیره‌ی کارمزدها {n(w.get('reserve', 0))}", ""]
    t.append("<b>💰 ثروتمندترین‌ها</b>")
    t += [f"{i + 1}. {esc(d['name'])} — {n(d['treasury'])}" for i, d in enumerate(rich)]
    t.append("\n<b>🏆 قدرتمندترین‌ها</b>")
    t += [f"{i + 1}. {esc(d['name'])} — {E.score(d):,}" for i, d in enumerate(pw)]
    return "\n".join(t), kb([[("🔄 رفرش", "ad:stats")], HOME])


# ------------------------------------------------------------------ لیست و جستجوی کشورها
SORTS = {"s": ("🏆 قدرت", lambda d: -E.score(d)), "t": ("💰 ثروت", lambda d: -d["treasury"]),
         "n": ("🆕 جدیدترین", lambda d: -d["created"]), "a": ("🟢 فعال‌ترین", lambda d: -d["last_tick"]),
         "p": ("👥 جمعیت", lambda d: -d["pop"])}
PER = 8


async def s_clist(page, sort):
    sort = sort if sort in SORTS else "s"
    docs = sorted(await players(), key=SORTS[sort][1])
    total = len(docs)
    page = max(0, min(page, max(0, (total - 1) // PER)))
    sub = docs[page * PER:(page + 1) * PER]
    t = [f"👤 <b>کشورها</b> ({n(total)}) · مرتب‌سازی: {SORTS[sort][0]}"]
    rows = [[(f"{d['name'][:18]} · {E.score(d):,}", f"ad:c:{d['_id']}")] for d in sub]
    rows.append(pager(page, total, PER, lambda p: f"ad:cl:{p}:{sort}"))
    rows += grid([(nm, f"ad:cl:0:{k}") for k, (nm, _) in SORTS.items()], 3)
    return "\n".join(t), kb(rows + [HOME])


async def find_targets(m, txt):
    fo = getattr(m, "forward_origin", None)
    u = getattr(fo, "sender_user", None) if fo else None
    if u:
        return [u.id]
    t = digits(txt).strip()
    if t.lstrip("-").isdigit():
        return [int(t)]
    if t.startswith("@") and len(t) > 2:
        try:
            ch = await bot.get_chat(t)
            return [ch.id]
        except Exception:
            pass
    k = reg.name_key(t)
    if not k:
        return []
    ex = await db.C.find_one({"name_key": k}, {"_id": 1})
    if ex:
        return [ex["_id"]]
    rx = re.escape(t)
    docs = await db.C.find({"$or": [{"name_key": {"$regex": re.escape(k)}}, {"leader": {"$regex": rx, "$options": "i"}}]},
                           {"_id": 1}).limit(8).to_list(8)
    return [d["_id"] for d in docs]


async def s_found(ids):
    if len(ids) == 1:
        return await s_country(ids[0])
    docs = await db.C.find({"_id": {"$in": ids}}, {"name": 1, "leader": 1}).to_list(10)
    rows = [[(f"{d['name'][:20]} · {d['leader'][:12]}", f"ad:c:{d['_id']}")] for d in docs]
    return f"🔎 {len(docs)} نتیجه:", kb(rows + [HOME])


# ------------------------------------------------------------------ کشور
def line_units(c):
    return " ".join(f"{U[k]['e']}{v:,}" for k, v in c["units"].items() if v) or "—"


async def s_country(tid, note=""):
    async with db.LOCK:
        c = await db.load(tid)
    banned = await db.is_banned(tid)
    if not c:
        t = (f"{note_(note)}👤 <b>کاربر بدون کشور</b>\n🆔 <code>{tid}</code>\n"
             f"{'🚫 مسدوده' if banned else '✅ آزاده'}")
        return t, kb([[("✅ آزاد کردن" if banned else "🚫 مسدود کردن", "ad:cban")], [("✉️ پیام", "ad:cdm")], HOME])
    d = E.derive(c)
    sh = c["shield_until"] - E.now()
    al = ""
    if c.get("alliance"):
        a = await db.A.find_one({"_id": c["alliance"]}, {"name": 1})
        al = f" · 🤝 {esc(a['name']) if a else c['alliance']}"
    bld = " ".join(f"{B[k]['e']}{v}" for k, v in c["buildings"].items() if v and k in B) or "—"
    fx = " ".join(f"{ASSETS[k]['e']}{v:,.1f}" for k, v in c["fx"].items() if v and k in ASSETS) or "—"
    npc = c.get("npc")
    t = [f"{note_(note)}🛠 <b>{esc(c['name'])}</b>{' 🤖 NPC' if npc else ''}{' 🚫' if banned else ''}",
         f"🆔 <code>{tid}</code> · {esc(c['leader'])} · سبک {c.get('doctrine', '—')}{al}",
         f"📅 تأسیس {fdate(c['created'])} · آخرین فعالیت {fdate(c['last_tick'])}", "",
         f"💰 خزانه {n(c['treasury'])} ({d['net']:+,.0f}/ساعت) · GDP {n(d['gdp'])}",
         f"🏦 سپرده {n(c['bank']['dep'])} · 🔻 وام {n(c['bank']['loan'])} (سقف {n(E.credit_limit(c))})",
         f"👥 {n(c['pop'])}/{n(d['cap'])} · اشتغال {int(d['emp'] * 100)}٪ · 🧾 مالیات {c['tax']}٪",
         f"😊 {c['sat']:.0f} · 🚨 {c['unrest']:.0f} · 🎓 {c['literacy']:.0f} · 🏥 {c['health']:.0f} · 🚓 {c['security']:.0f}",
         f"🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · 🔬 {n(c['tech'])} · ⚡ {int(d['er'] * 100)}٪",
         f"🏗 {bld}", f"🪖 {line_units(c)} (ظرفیت {E.army_size(c)}/{E.lv(c, 'barracks') * 1500})",
         f"💱 {fx}",
         f"🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🏆 {n(E.score(c))} · ⚔️ {c['wins']}/{c['losses']}",
         f"🛡 سپر: {sh / 3600:.1f} ساعت" if sh > 0 else "🛡 بدون سپر"]
    if c["bank"]["loan"] > 1 and not npc:
        t.append("⚠️ وام داره")
    rows = [[("💰 منابع و شاخص‌ها", "ad:cm"), ("🏗 ساختمان‌ها", "ad:cb")],
            [("🪖 یگان‌ها", "ad:cu"), ("💱 ارز و توکن", "ad:cf")],
            [("🛡 سپر", "ad:csm"), ("🧰 ابزارها", "ad:ct")],
            [("✉️ پیام به کشور", "ad:cdm"), ("✏️ تغییر نام", "ad:crn")]]
    if not npc:
        rows.append([("✅ آزاد کردن" if banned else "🚫 مسدود کردن", "ad:cban"), ("☠️ ریست / حذف", "ad:cdanger")])
    rows.append([("🔄 رفرش", f"ad:c:{tid}"), ("🔙 لیست", "ad:cl:0:s")])
    return "\n".join(t), kb(rows + [HOME])


async def s_resources(tid, note=""):
    async with db.LOCK:
        c = await db.load(tid)
    if not c:
        return "کشور پیدا نشد", kb([HOME])
    btns = [(f"{e} {nm}: {_get(c, k):,.0f}", f"ad:ce:{k}") for k, (e, nm, _, _) in FIELDS.items()]
    t = (f"{note_(note)}💰 <b>منابع و شاخص‌ها — {esc(c['name'])}</b>\n"
         "روی هر مورد بزن؛ بعد عدد بفرست:\n"
         "• <code>5000</code> یا <code>+5k</code> → اضافه\n• <code>-200</code> → کم\n• <code>=1000</code> → مقدار دقیق")
    return t, kb(grid(btns, 2) + [[("🔙 کشور", f"ad:c:{tid}")]])


async def s_buildings(tid, note=""):
    async with db.LOCK:
        c = await db.load(tid)
    if not c:
        return "کشور پیدا نشد", kb([HOME])
    btns = [(f"{b['e']} {b['n']} ({E.lv(c, k)})", f"ad:cbs:{k}") for k, b in B.items()]
    t = f"{note_(note)}🏗 <b>ساختمان‌ها — {esc(c['name'])}</b>\nسطح مجاز ۰ تا {config.MAX_LEVEL}. بعد از انتخاب عدد بفرست (<code>=5</code> یا <code>+2</code>)."
    return t, kb(grid(btns, 2) + [[("⬆️ همه MAX", "ad:cx:maxb"), ("🗑 همه ۰", "ad:cx:zerob")], [("🔙 کشور", f"ad:c:{tid}")]])


async def s_units(tid, note=""):
    async with db.LOCK:
        c = await db.load(tid)
    if not c:
        return "کشور پیدا نشد", kb([HOME])
    btns = [(f"{u['e']} {u['n']} ({c['units'].get(k, 0):,})", f"ad:cus:{k}") for k, u in U.items()]
    t = (f"{note_(note)}🪖 <b>یگان‌ها — {esc(c['name'])}</b>\nظرفیت: {E.army_size(c)}/{E.lv(c, 'barracks') * 1500} "
         "(ادمین محدودیت پادگان نداره)\nبعد از انتخاب عدد بفرست (<code>=500</code> یا <code>+100</code>).")
    return t, kb(grid(btns, 2) + [[("🗑 حذف کل ارتش", "ad:cx:wipeu")], [("🔙 کشور", f"ad:c:{tid}")]])


async def s_fx(tid, note=""):
    async with db.LOCK:
        c = await db.load(tid)
    if not c:
        return "کشور پیدا نشد", kb([HOME])
    btns = [(f"{a['e']} {s} ({c['fx'].get(s, 0):,.1f})", f"ad:cfs:{s}") for s, a in ASSETS.items()]
    t = f"{note_(note)}💱 <b>ارز و توکن — {esc(c['name'])}</b>\nارزش پرتفوی: {n(eco.fx_value(c))}"
    return t, kb(grid(btns, 2) + [[("🔙 کشور", f"ad:c:{tid}")]])


def s_shield(tid):
    rows = [[("+۶ ساعت", f"ad:cs:6"), ("+۲۴ ساعت", "ad:cs:24"), ("+۷۲ ساعت", "ad:cs:72")],
            [("+۱ هفته", "ad:cs:168"), ("❌ حذف سپر", "ad:cs:0")], [("🔙 کشور", f"ad:c:{tid}")]]
    return "🛡 <b>سپر</b> — مدت رو انتخاب کن:", kb(rows)


def s_tools(tid):
    rows = [[("⏳ ریست کولداون‌ها", "ad:cx:cd"), ("📰 پاک‌کردن اخبار", "ad:cx:news")],
            [("🧾 پاک‌کردن وام", "ad:cx:debt"), ("💚 شاخص‌ها ۱۰۰٪", "ad:cx:heal")],
            [("🎖 تکمیل ماموریت‌ها", "ad:cx:mis"), ("↩️ ریست ماموریت‌ها", "ad:cx:mis0")],
            [("📈 ارتقای نیرو MAX", "ad:cx:upgmax"), ("🔬 فناوری MAX", "ad:cx:techmax")],
            [("🧹 پاک‌کردن ارزها", "ad:cx:fx0"), ("🕊 ناآرامی ۰", "ad:cx:calm")],
            [("🔙 کشور", f"ad:c:{tid}")]]
    return "🧰 <b>ابزارهای سریع</b>", kb(rows)


def apply_tool(c, act):
    if act == "cd":
        c["daily"] = {"last": 0.0, "streak": c["daily"].get("streak", 0)}
        c["cd2"], c["npc_cd"], c["last_strike"] = {}, {}, 0.0
        return "کولداون‌ها ریست شد"
    if act == "news":
        c["pending"] = []
        return "اخبار پاک شد"
    if act == "debt":
        c["bank"]["loan"] = 0.0
        return "وام صفر شد"
    if act == "heal":
        for k in ("sat", "literacy", "health", "security"):
            c[k] = 100.0
        c["unrest"], c["weariness"], c["starving"] = 0.0, 0.0, False
        return "شاخص‌ها ۱۰۰٪ شد"
    if act == "mis":
        c["done"] = [mid for mid, *_ in eco.MISSIONS]
        return "همه‌ی ماموریت‌ها علامت تحویل خورد (بدون پاداش)"
    if act == "mis0":
        c["done"] = []
        return "ماموریت‌ها ریست شد"
    if act == "upgmax":
        c["upg"] = {k: config.MAX_LEVEL for k in c["upg"]}
        return "ارتقای نیروها MAX شد"
    if act == "techmax":
        c["techlv"] = {k: 10 for k in c["techlv"]}
        return "فناوری‌ها سطح ۱۰ شد"
    if act == "fx0":
        c["fx"], c["fxcost"] = {}, {}
        return "ارزها پاک شد"
    if act == "calm":
        c["unrest"], c["stage"] = 0.0, 0
        return "ناآرامی صفر شد"
    if act == "maxb":
        for k in B:
            c["buildings"][k] = config.MAX_LEVEL
        return "همه‌ی ساختمان‌ها MAX شد"
    if act == "zerob":
        c["buildings"] = {}
        return "همه‌ی ساختمان‌ها صفر شد"
    if act == "wipeu":
        c["units"] = {k: 0 for k in U}
        return "ارتش پاک شد"
    return None


# ------------------------------------------------------------------ حذف / ریست (فقط مالک)
async def _refresh_ally(aid):
    a = await db.A.find_one({"_id": aid})
    if a:
        bonus = min(0.15, 0.01 * len(a["members"]))
        await db.C.update_many({"_id": {"$in": a["members"]}}, {"$set": {"ally_bonus": bonus, "alliance": aid}})


async def _detach(uid):
    c = await db.C.find_one({"_id": uid}, {"alliance": 1})
    aid = c.get("alliance") if c else None
    a = await db.A.find_one({"_id": aid}) if aid else None
    if not a:
        return
    members = [x for x in a["members"] if x != uid]
    if not members:
        await db.A.delete_one({"_id": aid})
        return
    upd = {"members": members}
    if a["leader"] == uid:
        upd["leader"] = members[0]
    await db.A.update_one({"_id": aid}, {"$set": upd})
    await _refresh_ally(aid)


async def _drop_alliance(aid):
    a = await db.A.find_one({"_id": aid})
    if not a:
        return False
    await db.C.update_many({"_id": {"$in": a["members"]}}, {"$set": {"alliance": None, "ally_bonus": 0.0}})
    await db.W.update_many({"active": True, "$or": [{"a": aid}, {"b": aid}]}, {"$set": {"active": False}})
    await db.A.delete_one({"_id": aid})
    return True


async def do_reset(tid):
    async with db.LOCK:
        old = await db.C.find_one({"_id": tid})
        if not old or old.get("npc"):
            return False
        await _detach(tid)
        c = E.new_country(tid, old["name"], old["leader"], old.get("doctrine", "bal"))
        c["name_key"], c["home"] = old.get("name_key"), old.get("home")
        await db.save(c)
    return True


async def do_delete(tid):
    async with db.LOCK:
        old = await db.C.find_one({"_id": tid})
        if not old or old.get("npc"):
            return False
        await _detach(tid)
        await db.M.delete_many({"seller": tid})
        await db.C.delete_one({"_id": tid})
    return True


# ------------------------------------------------------------------ اقتصاد جهانی
def s_world(note=""):
    w = eco.WORLD
    lock = w.get("rate_lock")
    t = [f"{note_(note)}🌐 <b>اقتصاد جهانی</b>", "",
         f"🏛 نرخ پایه {w['rate'] * 100:.2f}٪ · {'🔒 قفل روی ' + format(lock * 100, '.2f') + '٪' if lock is not None else '🔓 خودکار'}"
         f" · سپرده {E.RATE['dep'] * 100:.2f}٪ · وام {E.RATE['loan'] * 100:.2f}٪",
         f"💼 ذخیره‌ی کارمزدها {n(w.get('reserve', 0))}", ""]
    rows = []
    for k, (e, nm) in ITEMS.items():
        b, s = eco.prices(k)
        t.append(f"{e} {nm}: mid {w['mid'][k]:.2f} (خرید {b:.2f} · فروش {s:.2f})")
        rows.append([(f"{e} {nm} 📈", f"ad:wev:{k}:up"), (f"{e} {nm} 📉", f"ad:wev:{k}:dn"), ("✏️", f"ad:wm:{k}")])
    t.append("")
    for sym, a in ASSETS.items():
        f = w["fx"][sym]
        t.append(f"{a['e']} {sym} {f['p']:,.2f} ({eco.fx_change(sym):+.1f}٪) {eco.spark(f['h'])}")
        rows.append([(f"{sym} 📈", f"ad:wev:{sym}:up"), (f"{sym} 📉", f"ad:wev:{sym}:dn"), ("✏️", f"ad:wp:{sym}")])
    if w["news"]:
        t.append("\n📰 " + "\n📰 ".join(w["news"][-3:]))
    rows += [[("🏛 قفل/آزاد نرخ", "ad:wrl"), ("📰 خبر دلخواه", "ad:wnews")],
             [("♻️ ریست همه‌ی قیمت‌ها", "ad:wreset")], HOME]
    return "\n".join(t), kb(rows)


def shock(key, up):
    w = eco.WORLD
    f = 1.15 if up else 0.85
    if key in ITEMS:
        base = config.MID0[key]
        w["mid"][key] = clampv(w["mid"][key] * f, base * 0.4, base * 3)
        nm, e = ITEMS[key][1], ITEMS[key][0]
        new = w["mid"][key]
    else:
        a = ASSETS[key]
        w["fx"][key]["p"] = clampv(w["fx"][key]["p"] * f, a["p0"] * 0.15, a["p0"] * 6)
        w["fx"][key]["h"] = (w["fx"][key]["h"] + [w["fx"][key]["p"]])[-48:]
        nm, e = a["n"], a["e"]
        new = w["fx"][key]["p"]
    w["news"] = (w["news"] + [("📈 جهش" if up else "📉 سقوط") + f" {e} {nm}: {'+' if up else '-'}۱۵٪ (دخالت مدیریت)"])[-5:]
    return new


# ------------------------------------------------------------------ اتحاد، جنگ، آگهی، NPC
async def s_alist(page):
    docs = await db.A.find().sort("name", 1).to_list(500)
    page = max(0, min(page, max(0, (len(docs) - 1) // PER)))
    sub = docs[page * PER:(page + 1) * PER]
    rows = [[(f"{a['name'][:18]} · {len(a['members'])} عضو", f"ad:a:{a['_id']}")] for a in sub]
    rows.append(pager(page, len(docs), PER, lambda p: f"ad:al:{p}"))
    return f"🤝 <b>اتحادها</b> ({len(docs)})", kb(rows + [HOME])


async def s_ally(aid, note=""):
    a = await db.A.find_one({"_id": aid})
    if not a:
        return "اتحاد پیدا نشد", kb([[("🔙", "ad:al:0")], HOME])
    docs = await db.C.find({"_id": {"$in": a["members"]}}, {"name": 1, "leader": 1}).to_list(60)
    nm = {d["_id"]: d["name"] for d in docs}
    w = await db.W.find_one({"active": True, "$or": [{"a": aid}, {"b": aid}]})
    t = [f"{note_(note)}🤝 <b>{esc(a['name'])}</b>", f"🆔 <code>{aid}</code> · رهبر: {esc(nm.get(a['leader'], a['leader']))}",
         f"🏦 بانک {n(a.get('bank', 0))} · برد {a.get('wins', 0)} · باخت {a.get('losses', 0)}",
         f"👥 {len(a['members'])} عضو: " + "، ".join(esc(nm.get(m, m)) for m in a["members"][:15])]
    if w:
        t.append("🔥 درگیر جنگ فعال")
    rows = [[("🏦 ویرایش بانک", "ad:ab"), ("🚪 اخراج عضو", "ad:ak")],
            [("👑 تغییر رهبر", "ad:ald"), ("🗑 حذف اتحاد", "ad:ask:adel")],
            [("🔙 لیست", "ad:al:0")]]
    return "\n".join(t), kb(rows + [HOME])


async def s_wars():
    ws = await db.W.find({"active": True}).to_list(30)
    t = [f"⚔️ <b>جنگ‌های فعال</b> ({len(ws)})", ""]
    rows = []
    for w in ws:
        a, b = await db.A.find_one({"_id": w["a"]}), await db.A.find_one({"_id": w["b"]})
        left = max(0, w["end"] - E.now()) / 60
        t.append(f"• {esc(a['name']) if a else '؟'} ⚔️ {esc(b['name']) if b else '؟'} — {w['score']['a']}:{w['score']['b']} · {left:.0f} دقیقه")
        rows.append([("⏩ پایان فوری", f"ad:we:{w['_id']}"), ("⏹ لغو بدون جایزه", f"ad:wx:{w['_id']}")])
    if not ws:
        t.append("جنگی فعال نیست.")
    return "\n".join(t), kb(rows + [[("🔄", "ad:wr")], HOME])


async def s_listings(page):
    docs = await db.M.find().sort("_id", -1).to_list(500)
    page = max(0, min(page, max(0, (len(docs) - 1) // 10)))
    sub = docs[page * 10:(page + 1) * 10]
    t = [f"📣 <b>آگهی‌های بازار آزاد</b> ({len(docs)})", ""]
    rows = []
    for d in sub:
        e, nm = ITEMS[d["item"]]
        t.append(f"#{d['_id']} {e} {d['qty']:,} × {d['price']} · فروشنده <code>{d['seller']}</code>")
        rows.append([(f"🗑 حذف #{d['_id']} (برگشت کالا)", f"ad:lx:{d['_id']}")])
    rows.append(pager(page, len(docs), 10, lambda p: f"ad:ls:{p}"))
    return "\n".join(t), kb(rows + [HOME])


async def s_npcs(note=""):
    docs = await db.C.find({"npc": True}).sort("_id", -1).to_list(20)
    t = [f"{note_(note)}🌍 <b>NPCها</b>", ""]
    rows = []
    for d in docs:
        E.defaults(d)
        t.append(f"{-d['_id']}. {esc(d['name'])} {'⭐' * d['tier']} · 🛡 {n(E.defense_power(d))} · 💰 {n(d['treasury'])} · {line_units(d)}")
        rows.append([(f"♻️ ریست {d['name'][:16]}", f"ad:npr:{-d['_id'] - 1}")])
    rows += [[("♻️ ریست همه‌ی NPCها", "ad:npa"), ("⏳ پاک‌کردن کولداون حمله به NPC (همه)", "ad:npcd")]]
    return "\n".join(t), kb(rows + [HOME])


# ------------------------------------------------------------------ بن، ادمین، تنظیمات، لاگ
async def s_bans(page):
    docs = await db.BANS.find().sort("ts", -1).to_list(1000)
    page = max(0, min(page, max(0, (len(docs) - 1) // PER)))
    sub = docs[page * PER:(page + 1) * PER]
    names = {d["_id"]: d["name"] for d in await db.C.find({"_id": {"$in": [b["_id"] for b in sub]}}, {"name": 1}).to_list(PER)}
    t = [f"🚫 <b>مسدودها</b> ({len(docs)})", ""]
    rows = []
    for b in sub:
        t.append(f"<code>{b['_id']}</code> {esc(names.get(b['_id'], ''))} · {fdate(b.get('ts'))}")
        rows.append([(f"✅ آزاد {b['_id']}", f"ad:ub:{b['_id']}")])
    rows.append(pager(page, len(docs), PER, lambda p: f"ad:bn:{p}"))
    rows.append([("➕ مسدود کردن با آیدی", "ad:bnadd")])
    return "\n".join(t), kb(rows + [HOME])


def s_settings(note=""):
    t = [f"{note_(note)}⚙️ <b>تنظیمات زنده</b> (ذخیره و بعد از ری‌استارت هم می‌مونه)", "",
         f"🔧 حالت تعمیر: {'🔴 روشن — فقط ادمین‌ها' if SET['maint'] else '🟢 خاموش'}",
         f"📝 پیام تعمیر: {esc(SET['maint_msg'])}",
         f"🆕 ثبت‌نام: {'🟢 باز' if SET['reg_open'] else '🔴 بسته'}",
         f"🚀 اعلان خودکار آپدیت به بازیکن‌ها: {'🟢 روشن' if SET['notify_updates'] else '🔴 خاموش'}",
         f"📝 متن آپدیت: {esc(SET['update_note']) or '—'}",
         f"📜 لاگ چنل ({esc(config.LOG_CHANNEL)}): {'🟢 روشن' if SET['log_on'] else '🔴 خاموش'}"]
    rows = [[("🔧 تعمیر " + ("خاموش" if SET["maint"] else "روشن"), "ad:stm"),
             ("🆕 ثبت‌نام " + ("ببند" if SET["reg_open"] else "باز کن"), "ad:str")],
            [("📝 پیام تعمیر", "ad:stmm"), ("🎛 ضرایب و نرخ‌ها", "ad:tn")],
            [("🚀 اعلان آپدیت " + ("خاموش" if SET["notify_updates"] else "روشن"), "ad:stn"), ("📝 متن آپدیت", "ad:stu")],
            [("📜 لاگ چنل " + ("خاموش" if SET["log_on"] else "روشن"), "ad:stl"), ("🧪 تست لاگ چنل", "ad:stlt")],
            [("📣 ارسال اعلان آپدیت همین الان", "ad:stgo")], HOME]
    return "\n".join(t), kb(rows)


def s_tun(note=""):
    t = [f"{note_(note)}🎛 <b>ضرایب و نرخ‌ها</b> (روی هرکدوم بزن و مقدار جدید بفرست)", ""]
    rows = []
    for k, (nm, tp, lo, hi) in TUNABLES.items():
        v = getattr(config, k)
        mark = "" if v == ORIG[k] else " ✱"
        rows.append([(f"{nm}: {v:g}{mark}", f"ad:tns:{k}")])
    t.append("✱ = با پیش‌فرض کد فرق داره")
    rows += [[("♻️ بازگشت همه به پیش‌فرض", "ad:tnr")], [("🔙", "ad:st")]]
    return "\n".join(t), kb(rows)


def s_admins(note=""):
    t = [f"{note_(note)}🛡 <b>ادمین‌ها</b>", "", f"👑 مالک: <code>{config.OWNER_ID}</code>"]
    extra = sorted(config.ADMINS - {config.OWNER_ID})
    for x in extra:
        src = "ENV" if x in config.BASE_ADMINS else "پنل"
        t.append(f"• <code>{x}</code> ({src})")
    rows = [[(f"🗑 {x}", f"ad:amdel:{x}")] for x in extra if x in SET["admins"]]
    rows += [[("➕ افزودن ادمین", "ad:amadd")], HOME]
    return "\n".join(t), kb(rows)


async def s_log():
    docs = await db.db.adminlog.find().sort("ts", -1).limit(20).to_list(20)
    t = ["📜 <b>لاگ ادمین (۲۰ مورد آخر)</b>", ""]
    for d in docs:
        t.append(f"<code>{fdate(d['ts'])}</code> <code>{d['by']}</code> {esc(d['text'])[:120]}")
    if not docs:
        t.append("خالیه.")
    return "\n".join(t)[:3900], kb([[("🔄", "ad:lg")], HOME])


# ------------------------------------------------------------------ پیام و هدیه‌ی همگانی
async def audience(aud, me):
    if aud == "t":
        return [me]
    ids = []
    if aud in ("u", "a"):
        ids += [d["_id"] async for d in db.C.find({"npc": {"$ne": True}}, {"_id": 1})]
    if aud in ("g", "a"):
        ids += [d["_id"] async for d in db.G.find({}, {"_id": 1})]
        ids += [d["_id"] async for d in db.A.find({}, {"_id": 1})]
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    return list(dict.fromkeys(i for i in ids if i not in banned))


AUD = {"u": "👥 همه‌ی بازیکن‌ها (پیوی)", "g": "💬 گروه‌ها", "a": "🌍 هر دو", "t": "🧪 تست (فقط خودم)"}


def s_bc():
    rows = [[(nm, f"ad:bca:{k}")] for k, nm in AUD.items()]
    return ("📣 <b>پیام همگانی</b>\nمخاطب رو انتخاب کن؛ بعد پیامت رو (متن، عکس، ویدیو، فایل ... هرچی) بفرست. "
            "پیش‌نمایش می‌گیری و بعد تأیید می‌کنی."), kb(rows + [HOME])


async def _bcast(admin_id, ids, from_chat, mid):
    ok = fail = 0
    for cid in ids:
        for attempt in (0, 1):
            try:
                await bot.copy_message(cid, from_chat, mid)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                fail += 1
                break
        await asyncio.sleep(0.05)
    try:
        await bot.send_message(admin_id, f"📣 ارسال تموم شد: ✅ {ok} موفق · ❌ {fail} ناموفق")
    except Exception:
        pass


GIFT = {"treasury": ("💰", "سکه"), "food": ("🌾", "غذا"), "steel": ("⚙️", "فولاد"),
        "fx.PHX": ("🔥", "توکن PHX"), "tech": ("🔬", "پژوهش"), "shield": ("🛡", "ساعت سپر")}


def s_gift():
    rows = grid([(f"{e} {nm}", f"ad:gfr:{k}") for k, (e, nm) in GIFT.items()], 2)
    return ("🎁 <b>هدیه‌ی همگانی</b>\nبه همه‌ی بازیکن‌ها (غیر NPC) اضافه میشه و بهشون پیام میره. "
            "نوعش رو انتخاب کن:"), kb(rows + [HOME])


async def _gift_notify(ids, text):
    for uid in ids:
        try:
            await bot.send_message(uid, text)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception:
            pass
        await asyncio.sleep(0.05)


# ------------------------------------------------------------------ اعلان آپدیت
def source_hash():
    """اثر انگشت کد ربات؛ هر وقت فایل‌ها عوض بشن (آپدیت/دیپلوی) تغییر می‌کنه."""
    h = hashlib.sha1()
    for p in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "*.py"))):
        with open(p, "rb") as f:
            h.update(os.path.basename(p).encode() + f.read())
    return h.hexdigest()[:10]


async def _announce(admin_id, ids, note):
    from util import OWNER as _OWN
    body = (f"🚀 <b>{config.BOT_NAME} آپدیت شد!</b>\nنسخه‌ی تازه آماده‌ست و چیزای جدیدی اومده ✨\n"
            + (f"\n📝 {esc(note)}\n" if note else "")
            + "\n👇 برای اینکه همه‌چی درست کار کنه، یه بار منوی جدید رو باز کن (یا بنویس «دنیای من»)")
    ok = fail = 0
    for uid in ids:
        _OWN.set(uid)
        try:
            await bot.send_message(uid, body, reply_markup=kb([[("🔄 باز کردن منوی جدید", "m")]]))
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    if admin_id:
        try:
            await bot.send_message(admin_id, f"🚀 اعلان آپدیت تموم شد: ✅ {ok} · ❌ {fail}")
        except Exception:
            pass


async def announce_update(admin_id=None):
    """به همه‌ی بازیکن‌های فعال (۴۵ روز اخیر، غیر مسدود) پیام آپدیت می‌فرسته. تعداد مخاطب رو برمی‌گردونه."""
    since = E.now() - 45 * 86400
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    ids = [d["_id"] async for d in db.C.find({"npc": {"$ne": True}, "last_tick": {"$gt": since}}, {"_id": 1})
           if d["_id"] not in banned]
    spawn(_announce(admin_id, ids, SET["update_note"]))
    return len(ids)


async def check_release():
    """موقع بالا اومدن ربات: اگه کد عوض شده باشه، به بازیکن‌ها خبر آپدیت میره."""
    ver = source_hash()
    d = await db.META.find_one({"_id": "release"})
    if d and d.get("ver") == ver:
        return
    await db.META.replace_one({"_id": "release"}, {"_id": "release", "ver": ver, "ts": time.time()}, upsert=True)
    if SET["notify_updates"]:
        cnt = await announce_update(config.OWNER_ID)
        log.info("update announced to %s players (version %s)", cnt, ver)


# ------------------------------------------------------------------ بکاپ
async def do_backup(chat_id):
    data = {}
    for nm, col in (("countries", db.C), ("alliances", db.A), ("wars", db.W), ("market", db.M),
                    ("groups", db.G), ("bans", db.BANS), ("meta", db.META)):
        data[nm] = await col.find().to_list(None)
    raw = json_util.dumps(data, ensure_ascii=False, indent=1).encode()
    name = "empirezero-backup-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    if len(raw) > 15_000_000:
        raw, name = gzip.compress(raw), name + ".json.gz"
    else:
        name += ".json"
    await bot.send_document(chat_id, BufferedInputFile(raw, filename=name),
                            caption=f"💾 بکاپ کامل · {len(data['countries'])} کشور · {len(raw) / 1024:.0f}KB")


# ------------------------------------------------------------------ ورود به پنل
ENTRY = {"admin", "panel", "adminpanel", "پنل", "پنل ادمین", "پنل_ادمین", "پنل مدیریت", "مدیریت", "ادمین"}


async def _entry(m: Message):
    if not m.from_user or not m.text or not is_admin(m.from_user.id):
        return False
    t = reg.clean(m.text).lower()
    slash = t.startswith("/")
    if slash:
        t = t[1:].split(" ")[0].split("@")[0]
    elif m.chat.type != "private":
        return False
    return t in ENTRY


@router.message(F.text, _entry)
async def on_entry(m: Message):
    OWNER.set(m.from_user.id)
    if m.chat.type != "private":
        return await m.reply("🛠 پنل ادمین فقط توی چت خصوصی با ربات باز میشه.")
    S = st(m.from_user.id)
    S["wait"] = None
    text, markup = await s_home()
    await m.answer(text, reply_markup=markup)


async def show(q, text, markup):
    try:
        await q.message.edit_text(text[:4000], reply_markup=markup)
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ دکمه‌ها
async def callback(q: CallbackQuery, data):
    uid = q.from_user.id
    OWNER.set(uid)
    if not is_admin(uid):
        return await q.answer("⛔ دسترسی نداری", show_alert=True)
    if not q.message or q.message.chat.type != "private":
        return await q.answer("پنل ادمین فقط توی چت خصوصی با ربات باز میشه", show_alert=True)
    S = st(uid)
    S["wait"] = None
    try:
        toast, scr = await route(uid, S, data.split(":"))
    except Exception:
        log.exception("admin cb")
        core.log_exc("پنل ادمین: " + ":".join(p))
        return await q.answer("⚠️ خطا (لاگ سرور رو ببین)", show_alert=True)
    if scr:
        await show(q, *scr)
    await q.answer((toast or "")[:190] or None)


def ask(S, wait, text, back):
    S["wait"] = dict(wait, ts=time.time())
    return None, (text + "\n\n<i>برای انصراف «لغو» بفرست یا دکمه رو بزن.</i>", kb([cancel_row(back)]))


async def route(uid, S, p):
    t = p[0]
    tid = S["tid"]
    owner_only = {"ask", "ok", "st", "stm", "str", "stmm", "tn", "tns", "tnr", "am", "amadd", "amdel", "bk", "stn", "stu", "stgo", "stl", "stlt"}
    if t in owner_only and not is_owner(uid):
        return "⛔ فقط مالک ربات", None
    if t == "noop":
        return None, None
    if t == "home":
        return None, await s_home()
    if t == "stats":
        return None, await s_stats()

    # --- کشورها
    if t == "cl":
        return None, await s_clist(int(p[1]), p[2] if len(p) > 2 else "s")
    if t == "find":
        return ask(S, {"act": "find"}, "🔎 اسم کشور، آیدی عددی یا @یوزرنیم رو بفرست (یا یه پیام از کاربر فوروارد کن):", "ad:home")
    if t == "c":
        S["tid"] = int(p[1])
        return None, await s_country(S["tid"])
    if tid is None and t[0] == "c":
        return "اول یه کشور انتخاب کن", await s_home()
    if t == "cm":
        return None, await s_resources(tid)
    if t == "ce":
        k = p[1]
        if k not in FIELDS:
            return "؟", None
        e, nm, _, _ = FIELDS[k]
        return ask(S, {"act": "field", "key": k}, f"{e} <b>{nm}</b> — مقدار؟\n<code>5000</code> اضافه · <code>-200</code> کم · <code>=1000</code> دقیق", "ad:cm")
    if t == "cb":
        return None, await s_buildings(tid)
    if t == "cbs":
        k = p[1]
        return ask(S, {"act": "bld", "key": k}, f"{B[k]['e']} <b>{B[k]['n']}</b> — سطح؟ (<code>=5</code> دقیق · <code>+1</code> اضافه · ۰ تا {config.MAX_LEVEL})", "ad:cb")
    if t == "cu":
        return None, await s_units(tid)
    if t == "cus":
        k = p[1]
        return ask(S, {"act": "unit", "key": k}, f"{U[k]['e']} <b>{U[k]['n']}</b> — تعداد؟ (<code>=500</code> دقیق · <code>+100</code> اضافه · <code>-50</code> کم)", "ad:cu")
    if t == "cf":
        return None, await s_fx(tid)
    if t == "cfs":
        k = p[1]
        return ask(S, {"act": "fx", "key": k}, f"{ASSETS[k]['e']} <b>{k}</b> — مقدار؟ (<code>=10</code> دقیق · <code>+5</code> اضافه · <code>-2</code> کم)", "ad:cf")
    if t == "csm":
        return None, s_shield(tid)
    if t == "cs":
        h = int(p[1])

        def f(c):
            c["shield_until"] = 0.0 if h == 0 else max(E.now(), c["shield_until"]) + h * 3600
            return True
        if await mutate(tid, f) is None:
            return "کشور پیدا نشد", None
        await alog(uid, f"سپر {h}h برای {tid}")
        return "✅ انجام شد", await s_country(tid, "🛡 سپر بروز شد")
    if t == "ct":
        return None, s_tools(tid)
    if t == "cx":
        r = await mutate(tid, lambda c: apply_tool(c, p[1]))
        if r is None:
            return "ناموفق", None
        await alog(uid, f"{p[1]} روی {tid}")
        return "✅", await s_country(tid, "✅ " + r)
    if t == "cdm":
        return ask(S, {"act": "dm"}, "✉️ متن پیام به این کاربر:", f"ad:c:{tid}")
    if t == "crn":
        return ask(S, {"act": "rename"}, "✏️ اسم جدید کشور:", f"ad:c:{tid}")
    if t == "cban":
        if tid in config.ADMINS:
            return "⛔ ادمین رو نمی‌شه بن کرد", None
        if await db.is_banned(tid):
            await db.BANS.delete_one({"_id": tid})
            await alog(uid, f"آزاد {tid}")
            return "✅ آزاد شد", await s_country(tid, "✅ آزاد شد")
        await db.BANS.update_one({"_id": tid}, {"$set": {"ts": time.time(), "by": uid}}, upsert=True)
        await alog(uid, f"بن {tid}")
        return "🚫 مسدود شد", await s_country(tid, "🚫 مسدود شد")
    if t == "cdanger":
        if not is_owner(uid):
            return "⛔ فقط مالک ربات", None
        rows = [[("♻️ ریست کشور (از اول)", "ad:ask:reset")], [("🗑 حذف کامل کشور", "ad:ask:delete")], [("🔙 کشور", f"ad:c:{tid}")]]
        return None, ("☠️ <b>عملیات خطرناک</b>\nریست: کشور با همون اسم و سبک از نو ساخته میشه.\nحذف: کشور و آگهی‌هاش پاک میشه (کاربر می‌تونه دوباره ثبت‌نام کنه).", kb(rows))
    if t == "ask":
        what = p[1]
        if what == "adel":
            if not S["aid"]:
                return "اتحاد انتخاب نشده", None
            back, msg = f"ad:a:{S['aid']}", f"🗑 اتحاد <code>{S['aid']}</code> حذف بشه؟ اعضا آزاد میشن."
        else:
            if tid is None:
                return "اول یه کشور انتخاب کن", None
            back = f"ad:c:{tid}"
            msg = f"{'♻️ ریست' if what == 'reset' else '🗑 حذف'} کشور <code>{tid}</code>؟ برگشت‌پذیر نیست."
        return None, (f"⚠️ <b>تأیید</b>\n{msg}", kb([[("✅ بله، انجام بده", f"ad:ok:{what}")], [("❌ نه", back)]]))
    if t == "ok":
        what = p[1]
        if what in ("reset", "delete") and tid is None:
            return "اول یه کشور انتخاب کن", None
        if what == "reset":
            ok = await do_reset(tid)
            await alog(uid, f"ریست کشور {tid}")
            return "✅" if ok else "ناموفق", await s_country(tid, "♻️ کشور ریست شد" if ok else "ناموفق")
        if what == "delete":
            ok = await do_delete(tid)
            await alog(uid, f"حذف کشور {tid}")
            S["tid"] = None
            return "✅" if ok else "ناموفق", await s_clist(0, "s")
        if what == "adel":
            if not S["aid"]:
                return "اتحاد انتخاب نشده", None
            async with db.LOCK:
                ok = await _drop_alliance(S["aid"])
            await alog(uid, f"حذف اتحاد {S['aid']}")
            return "✅" if ok else "ناموفق", await s_alist(0)
        return "؟", None

    # --- اقتصاد جهانی
    if t == "w":
        return None, s_world()
    if t == "wp":
        a = ASSETS[p[1]]
        return ask(S, {"act": "price", "key": p[1]}, f"{a['e']} <b>{p[1]}</b> قیمت جدید؟ (الان {eco.fx_price(p[1]):,.2f} · بازه {a['p0'] * 0.15:g} تا {a['p0'] * 6:g})", "ad:w")
    if t == "wm":
        k = p[1]
        return ask(S, {"act": "mid", "key": k}, f"{ITEMS[k][0]} <b>{ITEMS[k][1]}</b> قیمت mid جدید؟ (الان {eco.WORLD['mid'][k]:.2f})", "ad:w")
    if t == "wev":
        async with db.LOCK:
            new = shock(p[1], p[2] == "up")
            await eco.save_world()
        await alog(uid, f"شوک {p[2]} روی {p[1]}")
        return f"✅ قیمت جدید {new:,.2f}", s_world()
    if t == "wrl":
        return ask(S, {"act": "rate"}, "🏛 نرخ پایه‌ی بانک مرکزی به درصد (مثلاً <code>3.5</code>) یا <code>auto</code> برای حالت خودکار:", "ad:w")
    if t == "wnews":
        return ask(S, {"act": "news"}, "📰 متن خبر برای بخش اخبار بازار ارز:", "ad:w")
    if t == "wreset":
        async with db.LOCK:
            for k, a in ASSETS.items():
                eco.WORLD["fx"][k] = {"p": a["p0"], "h": [a["p0"]]}
            eco.WORLD["mid"] = dict(config.MID0)
            await eco.save_world()
        await alog(uid, "ریست قیمت‌ها")
        return "♻️ قیمت‌ها ریست شد", s_world()

    # --- اتحاد و جنگ
    if t == "al":
        return None, await s_alist(int(p[1]))
    if t == "a":
        S["aid"] = int(p[1])
        return None, await s_ally(S["aid"])
    if t in ("ab", "ak", "ald") and not S["aid"]:
        return "اول یه اتحاد انتخاب کن", None
    if t == "ab":
        return ask(S, {"act": "abank"}, "🏦 بانک اتحاد: <code>=5000</code> دقیق · <code>+1000</code> اضافه · <code>-500</code> کم", f"ad:a:{S['aid']}")
    if t == "ak":
        return ask(S, {"act": "akick"}, "🚪 آیدی عددی عضوی که اخراج بشه:", f"ad:a:{S['aid']}")
    if t == "ald":
        return ask(S, {"act": "aleader"}, "👑 آیدی عددی رهبر جدید (باید عضو باشه):", f"ad:a:{S['aid']}")
    if t == "wr":
        return None, await s_wars()
    if t in ("we", "wx"):
        from bson import ObjectId
        wid = ObjectId(p[1])
        if t == "we":
            await db.W.update_one({"_id": wid}, {"$set": {"end": E.now() - 1}})
            msg = "⏩ تا ۶۰ ثانیه‌ی دیگه نتیجه اعلام میشه"
        else:
            await db.W.update_one({"_id": wid}, {"$set": {"active": False}})
            msg = "⏹ جنگ لغو شد"
        await alog(uid, f"{t} جنگ {p[1]}")
        return msg, await s_wars()

    # --- آگهی و NPC
    if t == "ls":
        return None, await s_listings(int(p[1]))
    if t == "lx":
        lid = int(p[1])
        async with db.LOCK:
            li = await db.M.find_one({"_id": lid})
            if li:
                s = await db.load(li["seller"])
                if s:
                    s[li["item"]] += li["qty"]
                    await db.save(s)
                await db.M.delete_one({"_id": lid})
        await alog(uid, f"حذف آگهی {lid}")
        return "🗑 حذف شد و کالا برگشت", await s_listings(0)
    if t == "np":
        return None, await s_npcs()
    if t in ("npr", "npa"):
        idx = [int(p[1])] if t == "npr" else list(range(len(config.NPCS)))
        async with db.LOCK:
            for i in idx:
                if 0 <= i < len(config.NPCS):
                    await db.save(E.make_npc(i, config.NPCS[i]))
        await alog(uid, f"ریست NPC {idx}")
        return "♻️ انجام شد", await s_npcs("♻️ NPC ریست شد")
    if t == "npcd":
        async with db.LOCK:
            await db.C.update_many({"npc": {"$ne": True}}, {"$set": {"npc_cd": {}}})
        await alog(uid, "پاک‌کردن کولداون NPC همه")
        return "✅", await s_npcs("⏳ کولداون‌ها پاک شد")

    # --- پیام و هدیه
    if t == "bc":
        return None, s_bc()
    if t == "bca":
        return ask(S, {"act": "bc", "aud": p[1]}, f"📣 مخاطب: {AUD[p[1]]}\nپیامت رو بفرست:", "ad:bc")
    if t == "bcgo":
        b = S.get("bc")
        if not b:
            return "پیامی آماده نیست", None
        ids = await audience(b["aud"], uid)
        spawn(_bcast(uid, ids, b["chat"], b["mid"]))
        await alog(uid, f"پیام همگانی ({b['aud']}) به {len(ids)} مخاطب")
        S["bc"] = None
        return "🚀 ارسال شروع شد", (f"🚀 ارسال به {len(ids)} مخاطب شروع شد؛ وقتی تموم شد خبرت می‌کنم.", kb([HOME]))
    if t == "gf":
        return None, s_gift()
    if t == "gfr":
        e, nm = GIFT[p[1]]
        return ask(S, {"act": "gift", "key": p[1]}, f"{e} <b>{nm}</b> — مقدار برای هر بازیکن؟ (عدد مثبت)", "ad:gf")
    if t == "gfgo":
        g = S.get("gift")
        if not g:
            return "هدیه‌ای آماده نیست", None
        S["gift"] = None
        k, amt = g["key"], g["amt"]
        now = E.now()
        async with db.LOCK:
            if k == "shield":
                r = await db.C.update_many({"npc": {"$ne": True}}, [{"$set": {"shield_until": {"$add": [
                    {"$max": ["$shield_until", now]}, amt * 3600]}}}])
            else:
                r = await db.C.update_many({"npc": {"$ne": True}}, {"$inc": {k: amt}})
        e, nm = GIFT[k]
        ids = await audience("u", uid)
        spawn(_gift_notify(ids, f"🎁 <b>هدیه‌ی مدیریت {config.BOT_NAME}!</b>\n{e} {amt:g} {nm} به کشورت اضافه شد."))
        await alog(uid, f"هدیه همگانی {amt:g} {k} → {r.modified_count} کشور")
        return "🎁 داده شد", (f"🎁 {amt:g} {nm} به {r.modified_count} کشور داده شد.", kb([HOME]))

    # --- بن‌ها
    if t == "bn":
        return None, await s_bans(int(p[1]))
    if t == "ub":
        await db.BANS.delete_one({"_id": int(p[1])})
        await alog(uid, f"آزاد {p[1]}")
        return "✅ آزاد شد", await s_bans(0)
    if t == "bnadd":
        return ask(S, {"act": "banid"}, "🚫 آیدی عددی کاربر:", "ad:bn:0")

    # --- تنظیمات
    if t == "st":
        return None, s_settings()
    if t == "stm":
        SET["maint"] = not SET["maint"]
        await save_settings()
        await alog(uid, f"حالت تعمیر {SET['maint']}")
        return "✅", s_settings()
    if t == "str":
        SET["reg_open"] = not SET["reg_open"]
        await save_settings()
        await alog(uid, f"ثبت‌نام {SET['reg_open']}")
        return "✅", s_settings()
    if t == "stmm":
        return ask(S, {"act": "maintmsg"}, "📝 متن پیام حالت تعمیر:", "ad:st")
    if t == "stn":
        SET["notify_updates"] = not SET["notify_updates"]
        await save_settings()
        await alog(uid, f"اعلان آپدیت {SET['notify_updates']}")
        return "✅", s_settings()
    if t == "stl":
        SET["log_on"] = not SET["log_on"]
        core.LOG["on"] = SET["log_on"]
        await save_settings()
        return "✅", s_settings()
    if t == "stlt":
        ok, err = await core.log_test()
        return ("✅ تست به چنل فرستاده شد" if ok else "❌ نشد: " + err), s_settings(
            "✅ تست به چنل رسید" if ok else f"❌ ارسال به چنل نشد: <code>{esc(err)}</code>\nمطمئن شو ربات توی چنل ادمینه و اجازه‌ی ارسال پیام داره.")
    if t == "stu":
        return ask(S, {"act": "upnote"}, "📝 متن کوتاه «چی جدیده؟» برای اعلان آپدیت (یا <code>-</code> برای خالی کردن):", "ad:st")
    if t == "stgo":
        cnt = await announce_update(uid)
        await alog(uid, f"ارسال اعلان آپدیت به {cnt}")
        return f"🚀 برای {cnt} نفر در حال ارسال", s_settings(f"🚀 اعلان برای {cnt} بازیکن فرستاده میشه")
    if t == "tn":
        return None, s_tun()
    if t == "tns":
        k = p[1]
        nm, tp, lo, hi = TUNABLES[k]
        return ask(S, {"act": "tun", "key": k}, f"{nm}\nالان: <b>{getattr(config, k):g}</b> · پیش‌فرض {ORIG[k]:g} · بازه {lo:g} تا {hi:g}", "ad:tn")
    if t == "tnr":
        for k, v in ORIG.items():
            setattr(config, k, v)
        SET["tun"] = {}
        await save_settings()
        await alog(uid, "بازگشت ضرایب به پیش‌فرض")
        return "♻️ انجام شد", s_tun()
    if t == "am":
        return None, s_admins()
    if t == "amadd":
        return ask(S, {"act": "admadd"}, "🛡 آیدی عددی ادمین جدید:", "ad:am")
    if t == "amdel":
        x = int(p[1])
        if x in SET["admins"]:
            SET["admins"].remove(x)
        rebuild_admins()
        await save_settings()
        spawn(sync_commands(removed=[x]))
        await alog(uid, f"حذف ادمین {x}")
        return "✅", s_admins()
    if t == "lg":
        return None, await s_log()
    if t == "bk":
        await q_backup(uid)
        await alog(uid, "بکاپ")
        return "💾 فایل بکاپ فرستاده شد", None
    return None, await s_home()


async def q_backup(uid):
    await do_backup(uid)


# ------------------------------------------------------------------ ورودی‌های متنی
async def _waiting(m: Message):
    u = m.from_user
    if not u or m.chat.type != "private" or not is_admin(u.id):
        return False
    w = (ST.get(u.id) or {}).get("wait")
    if not w or time.time() - w.get("ts", 0) > WAIT_TTL:
        return False
    return not (m.text or "").startswith("/")


def retry(S, w, msg):
    S["wait"] = dict(w, ts=time.time())
    return f"❌ {msg}\nدوباره بفرست یا «لغو».", kb([cancel_row()])


@router.message(_waiting)
async def on_input(m: Message):
    uid = m.from_user.id
    OWNER.set(uid)
    S = st(uid)
    w, S["wait"] = S["wait"], None
    txt = (m.text or m.caption or "").strip()
    if txt in ("لغو", "انصراف", "cancel"):
        return await m.reply("↩️ لغو شد", reply_markup=kb([HOME]))
    try:
        text, markup = await handle_input(m, S, w, txt, uid)
    except Exception:
        log.exception("admin input")
        text, markup = "⚠️ خطا؛ لاگ سرور رو ببین", kb([HOME])
    await m.reply(text[:4000], reply_markup=markup)


async def handle_input(m, S, w, txt, uid):
    act, tid = w["act"], S["tid"]

    if act == "find":
        ids = await find_targets(m, txt)
        if not ids:
            return retry(S, w, "چیزی پیدا نشد")
        if len(ids) == 1:
            S["tid"] = ids[0]
        return await s_found(ids)

    if act == "bc":
        S["bc"] = {"aud": w["aud"], "chat": m.chat.id, "mid": m.message_id}
        cnt = len(await audience(w["aud"], uid))
        return (f"👆 پیش‌نمایش همین پیامه.\nارسال به <b>{cnt}</b> مخاطب ({AUD[w['aud']]})؟",
                kb([[("🚀 ارسال", "ad:bcgo")], [("❌ انصراف", "ad:bc")]]))

    pn = parse_num(txt) if act in ("field", "bld", "unit", "fx", "abank", "gift", "price", "mid", "rate", "tun") else None
    if act in ("field", "bld", "unit", "fx", "abank", "gift", "price", "mid", "tun") and not pn:
        return retry(S, w, "عدد معتبر بفرست")

    if act == "field":
        key = w["key"]
        r = await mutate(tid, lambda c: apply_field(c, key, *pn))
        if r is None:
            return "کشور پیدا نشد", kb([HOME])
        await alog(uid, f"{key} کشور {tid}: {r[0]:,.0f} → {r[1]:,.0f}")
        return await s_resources(tid, f"✅ {FIELDS[key][1]}: {n(r[0])} → <b>{n(r[1])}</b>")

    if act == "bld":
        key, (mode, v) = w["key"], pn

        def f(c):
            old = E.lv(c, key)
            new = int(clampv(v if mode == "set" else old + v, 0, config.MAX_LEVEL))
            c["buildings"][key] = new
            return old, new
        r = await mutate(tid, f)
        if r is None:
            return "کشور پیدا نشد", kb([HOME])
        await alog(uid, f"ساختمان {key} کشور {tid}: {r[0]} → {r[1]}")
        return await s_buildings(tid, f"✅ {B[key]['n']}: {r[0]} → <b>{r[1]}</b>")

    if act == "unit":
        key, (mode, v) = w["key"], pn

        def f(c):
            old = c["units"].get(key, 0)
            new = int(max(0, v if mode == "set" else old + v))
            c["units"][key] = new
            return old, new
        r = await mutate(tid, f)
        if r is None:
            return "کشور پیدا نشد", kb([HOME])
        await alog(uid, f"یگان {key} کشور {tid}: {r[0]} → {r[1]}")
        return await s_units(tid, f"✅ {U[key]['n']}: {r[0]:,} → <b>{r[1]:,}</b>")

    if act == "fx":
        key, (mode, v) = w["key"], pn

        def f(c):
            old = c["fx"].get(key, 0.0)
            new = max(0.0, v if mode == "set" else old + v)
            c["fx"][key] = new
            c["fxcost"].setdefault(key, eco.fx_price(key))
            return old, new
        r = await mutate(tid, f)
        if r is None:
            return "کشور پیدا نشد", kb([HOME])
        await alog(uid, f"ارز {key} کشور {tid}: {r[0]:,.2f} → {r[1]:,.2f}")
        return await s_fx(tid, f"✅ {key}: {r[0]:,.1f} → <b>{r[1]:,.1f}</b>")

    if act == "dm":
        try:
            await bot.send_message(tid, f"📨 <b>پیام مدیریت {config.BOT_NAME}</b>\n\n{esc(txt)}")
            res = "✅ پیام فرستاده شد"
        except Exception as e:
            res = f"❌ ارسال نشد ({type(e).__name__}) — احتمالاً ربات رو استارت نکرده"
        await alog(uid, f"پیام به {tid}")
        return await s_country(tid, res)

    if act == "rename":
        name = reg.clean(txt)
        if not 2 <= len(name) <= 32:
            return retry(S, w, "اسم باید ۲ تا ۳۲ حرف باشه")
        async with db.LOCK:
            c = await db.load(tid)
            if not c:
                return "کشور پیدا نشد", kb([HOME])
            if not c.get("npc"):
                k = reg.name_key(name)
                dup = await db.C.find_one({"name_key": k, "_id": {"$ne": tid}}, {"_id": 1})
                if dup:
                    return retry(S, w, "این اسم قبلاً گرفته شده")
                c["name_key"] = k
            old, c["name"] = c["name"], name
            await db.save(c)
        await alog(uid, f"تغییر نام {tid}: {old} → {name}")
        return await s_country(tid, f"✅ نام تغییر کرد: {esc(old)} → <b>{esc(name)}</b>")

    if act == "price":
        key, (mode, v) = w["key"], pn
        a = ASSETS[key]
        async with db.LOCK:
            f = eco.WORLD["fx"][key]
            f["p"] = clampv(v if mode == "set" else f["p"] + v, a["p0"] * 0.15, a["p0"] * 6)
            f["h"] = (f["h"] + [f["p"]])[-48:]
            await eco.save_world()
        await alog(uid, f"قیمت {key} → {f['p']:.2f}")
        return s_world(f"✅ قیمت {key}: {f['p']:,.2f}")

    if act == "mid":
        key, (mode, v) = w["key"], pn
        base = config.MID0[key]
        async with db.LOCK:
            cur = eco.WORLD["mid"][key]
            eco.WORLD["mid"][key] = clampv(v if mode == "set" else cur + v, base * 0.4, base * 3)
            await eco.save_world()
        await alog(uid, f"mid {key} → {eco.WORLD['mid'][key]:.2f}")
        return s_world(f"✅ قیمت {key}: {eco.WORLD['mid'][key]:.2f}")

    if act == "rate":
        async with db.LOCK:
            if txt.lower() in ("auto", "خودکار"):
                eco.WORLD["rate_lock"] = None
                res = "🔓 نرخ خودکار شد (از دور بعدی بروز میشه)"
            elif pn:
                eco.WORLD["rate_lock"] = clampv(pn[1] / 100, 0.0, 0.5)
                eco.WORLD["rate"] = eco.WORLD["rate_lock"]
                eco.apply_rates()
                res = f"🔒 نرخ روی {eco.WORLD['rate'] * 100:.2f}٪ قفل شد"
            else:
                return retry(S, w, "عدد درصد یا auto")
            await eco.save_world()
        await alog(uid, res)
        return s_world(res)

    if act == "news":
        async with db.LOCK:
            eco.WORLD["news"] = (eco.WORLD["news"] + ["📢 " + txt[:150]])[-5:]
            await eco.save_world()
        await alog(uid, "خبر بازار")
        return s_world("✅ خبر ثبت شد")

    aid = S["aid"]
    if act == "abank":
        mode, v = pn
        a = await db.A.find_one({"_id": aid})
        if not a:
            return "اتحاد پیدا نشد", kb([HOME])
        new = int(max(0, v if mode == "set" else a.get("bank", 0) + v))
        await db.A.update_one({"_id": aid}, {"$set": {"bank": new}})
        await alog(uid, f"بانک اتحاد {aid} → {new}")
        return await s_ally(aid, f"✅ بانک: {n(new)}")

    if act in ("akick", "aleader"):
        if not digits(txt).strip().lstrip("-").isdigit():
            return retry(S, w, "آیدی عددی بفرست")
        x = int(digits(txt).strip())
        a = await db.A.find_one({"_id": aid})
        if not a or x not in a["members"]:
            return retry(S, w, "این آیدی عضو اتحاد نیست")
        if act == "aleader":
            await db.A.update_one({"_id": aid}, {"$set": {"leader": x}})
            await alog(uid, f"رهبر اتحاد {aid} → {x}")
            return await s_ally(aid, "✅ رهبر عوض شد")
        if len(a["members"]) <= 1:
            return retry(S, w, "آخرین عضو رو نمی‌شه اخراج کرد؛ اتحاد رو حذف کن")
        async with db.LOCK:
            await _detach(x)
            await db.C.update_one({"_id": x}, {"$set": {"alliance": None, "ally_bonus": 0.0}})
        await alog(uid, f"اخراج {x} از اتحاد {aid}")
        return await s_ally(aid, "✅ اخراج شد")

    if act == "gift":
        key, amt = w["key"], pn[1]
        if amt <= 0:
            return retry(S, w, "عدد باید مثبت باشه")
        S["gift"] = {"key": key, "amt": amt}
        cnt = await db.C.count_documents({"npc": {"$ne": True}})
        e, nm = GIFT[key]
        return (f"🎁 {e} <b>{amt:g} {nm}</b> به <b>{cnt}</b> بازیکن داده بشه؟",
                kb([[("✅ تأیید و ارسال", "ad:gfgo")], [("❌ انصراف", "ad:gf")]]))

    if act == "banid":
        x = digits(txt).strip()
        if not x.lstrip("-").isdigit():
            return retry(S, w, "آیدی عددی بفرست")
        x = int(x)
        if x in config.ADMINS:
            return "⛔ ادمین رو نمی‌شه بن کرد", kb([HOME])
        await db.BANS.update_one({"_id": x}, {"$set": {"ts": time.time(), "by": uid}}, upsert=True)
        await alog(uid, f"بن {x}")
        return await s_bans(0)

    if act == "upnote":
        SET["update_note"] = "" if txt == "-" else txt[:400]
        await save_settings()
        await alog(uid, "متن آپدیت عوض شد")
        return s_settings("✅ ذخیره شد")

    if act == "maintmsg":
        SET["maint_msg"] = txt[:300]
        await save_settings()
        await alog(uid, "پیام تعمیر عوض شد")
        return s_settings("✅ ذخیره شد")

    if act == "tun":
        key = w["key"]
        nm, tp, lo, hi = TUNABLES[key]
        v = clampv(pn[1], lo, hi)
        v = int(v) if tp is int else float(v)
        setattr(config, key, v)
        SET["tun"][key] = v
        await save_settings()
        await alog(uid, f"{key} = {v}")
        return s_tun(f"✅ {nm} → {v:g}")

    if act == "admadd":
        x = digits(txt).strip()
        if not x.isdigit():
            return retry(S, w, "آیدی عددی بفرست")
        if int(x) not in SET["admins"]:
            SET["admins"].append(int(x))
        rebuild_admins()
        await save_settings()
        spawn(sync_commands())
        await alog(uid, f"افزودن ادمین {x}")
        return s_admins(f"✅ {x} ادمین شد")

    return "؟", kb([HOME])
