"""دستورهای گروه (Command-driven): ثبت‌نام، بانک، بازار، ارز، ارتش، جنگ ...
هر دستور با «کلمه» کار می‌کنه (بانک، کار، روزانه ...) و اسلش هم هنوز جواب میده."""
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, ForceReply, Message
from pymongo.errors import DuplicateKeyError

import admin
import config
import db
import eco
import engine as E
import reg
import ui
from config import ASSETS, B, DOCTRINES, ITEMS, U
from core import INFO, notify
from util import OWNER, amount, esc, kb, n

router = Router()
CMDS = {}
LAST = {}
AWAIT = {}      # (chat, uid) → زمان؛ منتظر اسم کشور
PENDING = {}    # uid → {name, chat, ts, leader}؛ منتظر انتخاب سبک

NOT_REG = "🏛 هنوز کشور نداری! بنویس «<b>ثبت نام</b>» تا با هم یه کشور بسازیم 🌱"


def cmd(*names, need=True, args=False):
    """args=True یعنی دستور آرگومان می‌گیره؛ بدون‌اسلش فقط وقتی کار می‌کنه که آرگومان داشته باشه یا args=True باشه."""
    def deco(f):
        for nm in names:
            k = reg.clean(nm).lower()
            for v in {k, k.replace(" ", "_"), k.replace("_", " "), k.replace("\u200c", ""), k.replace("\u200c", " ")}:
                CMDS[v] = (f, need, args)
        return f
    return deco


def parse(m):
    t = reg.clean(m.text or "")
    if not t:
        return None
    if t.startswith("/"):
        first, _, rest = t.partition(" ")
        name = first[1:]
        if "@" in name:
            name, tgt = name.split("@", 1)
            if tgt.lower() != INFO["username"].lower():
                return None
        e = CMDS.get(name.lower())
        return (e[0], e[1], rest.strip(), False) if e else None
    if not config.BARE_WORDS:
        return None
    tk = t.split()
    if len(tk) > 6 or tk[0].isascii():
        return None
    if len(tk) >= 2:
        e = CMDS.get((tk[0] + " " + tk[1]).lower())
        if e and (e[2] or len(tk) == 2):
            return e[0], e[1], " ".join(tk[2:]), True
    e = CMDS.get(tk[0].lower())
    if e and (e[2] or len(tk) == 1):      # دستور بی‌آرگومان وسط جمله‌ی عادی فعال نمیشه
        return e[0], e[1], " ".join(tk[1:]), True
    return None


async def _parsed(m: Message):
    p = parse(m)
    return {"parsed": p} if p else False


async def _awaiting(m: Message):
    if not m.from_user or not m.text or m.text.startswith("/"):
        return False
    key = (m.chat.id, m.from_user.id)
    t = AWAIT.get(key)
    if not t:
        return False
    if time.time() - t > config.REG_PENDING_TTL:
        AWAIT.pop(key, None)
        return False
    if m.chat.type != "private":
        r = m.reply_to_message
        if not r or not r.from_user or r.from_user.id != INFO.get("id"):
            return False
    return True


async def send(m, out):
    if out is None:
        return
    text, markup = out if isinstance(out, tuple) else (out, None)
    await m.reply(text, reply_markup=markup)


def anon(m):
    return bool(m.sender_chat) or m.from_user is None or m.from_user.id == reg.ANON_ID


# ------------------------------------------------------------------ ثبت‌نام (ویزارد دکمه‌ای)
INTRO = (f"🌍 <b>به {config.BOT_NAME} خوش اومدی!</b>\n"
         "تو فرمانروای یه کشور کوچیکی که قراره امپراتوری بشه 👑 بانک مرکزی هم یه هدیه‌ی شروع برات داره 🎁\n\n")

EMBLEMS = ["🦁", "🦅", "🐺", "🐉", "🔥", "👑", "🌙", "⚔️", "🌹", "🏔"]
REG_HOME = {}     # uid → گروهی که از اونجا اومده (لینک عمیق)


def _pend(uid):
    p = PENDING.get(uid)
    if p and time.time() - p["ts"] > config.REG_PENDING_TTL:
        PENDING.pop(uid, None)
        return None
    return p


def _ensure(u, chat):
    """پیش‌نویس ثبت‌نام این کاربر رو می‌سازه/برمی‌گردونه."""
    p = _pend(u.id)
    if not p:
        group = chat.type != "private"
        p = PENDING[u.id] = dict(name=None, doctrine=None, emblem=None, leader=u.full_name[:32],
                                 home=chat.id if group else REG_HOME.get(u.id), ts=time.time())
    p["ts"] = time.time()
    return p


def _link(chat_id):
    uname = INFO.get("username", "")
    tag = ("n" if chat_id < 0 else "p") + str(abs(chat_id))
    return f"https://t.me/{uname}?start=reg_{tag}"


def s_reg_start(private, chat_id=0):
    t = INTRO + ("چطوری شروع کنیم؟ 👇" if private else "برای ساخت کشورت یکی از راه‌ها رو انتخاب کن 👇")
    rows = [[("🎲 اسم تصادفی بساز", "rg:rn")], [("✏️ اسم دلخواه خودم", "rg:typ")]]
    if not private and INFO.get("username"):
        rows.insert(0, [("📩 ثبت‌نام توی پیوی (پیشنهادی)", "url:" + _link(chat_id))])
    return t, rows


def s_reg_name(p, note=""):
    t = f"{note}🎲 اسم پیشنهادی: 👑 <b>{esc(p['name'])}</b>\nخوشت اومد؟"
    return t, kb([[("✅ همین باشه", "rg:use")], [("🔄 یکی دیگه", "rg:rn"), ("✏️ اسم خودم", "rg:typ")],
                  [("❌ انصراف", "rg:x")]])


def s_reg_doctrine(p):
    t = [f"🏛 <b>{esc(p['name'])}</b>\n🎯 سبک شروعت چیه؟\n"]
    rows = []
    for k, (e, nm, d) in DOCTRINES.items():
        t.append(f"{e} <b>{nm}</b> — {d}")
        rows.append([(f"{e} {nm}", f"rg:d:{k}")])
    return "\n".join(t), kb(rows + [[("✏️ تغییر اسم", "rg:typ"), ("❌ انصراف", "rg:x")]])


def s_reg_emblem(p):
    rows = [[(e, f"rg:e:{i}") for i, e in enumerate(EMBLEMS[j:j + 5], j)] for j in (0, 5)]
    t = f"🏛 <b>{esc(p['name'])}</b>\n🎭 یه نماد برای کشورت انتخاب کن ✨"
    return t, kb(rows + [[("🔙 سبک", "rg:chd"), ("❌ انصراف", "rg:x")]])


def s_reg_confirm(p):
    e, nm, d = DOCTRINES[p["doctrine"]]
    st = config.STARTER
    t = (f"📜 <b>پرونده‌ی کشورت آماده‌ست!</b>\n"
         f"{p['emblem']} <b>{esc(p['name'])}</b> · 👤 {esc(p['leader'])} · {e} {nm}\n"
         f"🎁 هدیه‌ی شروع: {st['phx']:.0f} PHX · {st['shield_h']} ساعت سپر · جایزه‌ی روزانه ۲ برابر\n"
         "همه‌چی درسته؟ بزن بریم! 🚀")
    return t, kb([[("✅ تأسیس کشور", "rg:ok")],
                  [("✏️ اسم", "rg:typ"), ("🎯 سبک", "rg:chd"), ("🎭 نماد", "rg:che")],
                  [("❌ انصراف", "rg:x")]])


async def _closed(uid):
    if not admin.SET["reg_open"] and uid not in config.ADMINS:
        return "🔒 ثبت‌نام موقتاً بسته‌ست؛ کمی بعد سر بزن 💛"
    if await db.is_banned(uid):
        return "🚫 دسترسیت مسدوده"
    return None


async def start_pick(m, raw):
    """اسم تایپ‌شده → اعتبارسنجی → رفتن به مرحله‌ی سبک."""
    u = m.from_user
    r = await _closed(u.id)
    if r:
        return r
    ok, name = reg.validate_name(raw)
    if not ok:
        AWAIT[(m.chat.id, u.id)] = time.time()
        return "❌ " + name + "\nیه اسم دیگه بفرست 😊"
    if not reg.throttle(u.id):
        return "⏳ تلاش‌های زیادی کردی؛ ۱۰ دقیقه‌ی دیگه دوباره امتحان کن"
    if await db.C.find_one({"name_key": reg.name_key(name)}, {"_id": 1}):
        AWAIT[(m.chat.id, u.id)] = time.time()
        return "❌ این اسم قبلاً گرفته شده؛ یکی دیگه بفرست 😊"
    OWNER.set(u.id)
    p = _ensure(u, m.chat)
    p["name"] = name
    return s_reg_doctrine(p)


async def _free_random():
    for _ in range(25):
        nm = reg.random_name()
        ok, nm = reg.validate_name(nm)
        if ok and not await db.C.find_one({"name_key": reg.name_key(nm)}, {"_id": 1}):
            return nm
    return None


@cmd("register", "ثبت نام", "ثبت‌نام", "ساخت کشور", need=False, args=True)
async def h_register(m, c, a):
    if c:
        return "✅ کشور داری:\n" + ui.brief(c)
    r = await _closed(m.from_user.id)
    if r:
        return r
    if a:
        return await start_pick(m, a)
    private = m.chat.type == "private"
    _ensure(m.from_user, m.chat)
    if private:
        AWAIT[(m.chat.id, m.from_user.id)] = time.time()      # همون‌جا اسم تایپ کنه هم قبوله
    t, rows = s_reg_start(private, m.chat.id)
    return t, kb(rows)


@router.message(F.text, _awaiting)
async def on_name(m: Message):
    AWAIT.pop((m.chat.id, m.from_user.id), None)
    if anon(m):
        return
    if await db.C.find_one({"_id": m.from_user.id}, {"_id": 1}):
        return await m.reply("✅ قبلاً ثبت‌نام کردی")
    await send(m, await start_pick(m, m.text))


async def rg_callback(q: CallbackQuery, choice):
    uid = q.from_user.id
    OWNER.set(uid)
    ps = choice.split(":")
    act = ps[0]
    if act == "x":
        PENDING.pop(uid, None)
        AWAIT.pop((q.message.chat.id, uid), None)
        await q.message.edit_text("❌ ثبت‌نام لغو شد؛ هر وقت خواستی بنویس «ثبت نام» 🌱")
        return await q.answer()
    r = await _closed(uid)
    if r:
        return await q.answer(r, show_alert=True)
    if await db.C.find_one({"_id": uid}, {"_id": 1}):
        PENDING.pop(uid, None)
        return await q.answer("قبلاً ثبت‌نام کردی 😉", show_alert=True)
    p = _ensure(q.from_user, q.message.chat)
    chat = q.message.chat

    async def show(out):
        text, mk = out
        try:
            await q.message.edit_text(text, reply_markup=mk)
        except Exception:
            pass

    if act == "rn":
        nm = await _free_random()
        if not nm:
            return await q.answer("اسم آزاد پیدا نشد؛ یه اسم خودت بنویس", show_alert=True)
        p["name"] = nm
        await show(s_reg_name(p))
        return await q.answer("🎲")
    if act == "typ":
        AWAIT[(chat.id, uid)] = time.time()
        if chat.type == "private":
            await show(("✏️ <b>اسم کشورت رو بفرست</b>\n۲ تا ۲۴ حرف؛ فارسی یا انگلیسی ✨", kb([[("❌ انصراف", "rg:x")]])))
        else:
            await q.message.answer("✏️ <b>اسم کشورت رو با ریپلای روی همین پیام بفرست</b> 👇",
                                   reply_markup=ForceReply(selective=True, input_field_placeholder="اسم کشور"))
        return await q.answer()
    if act == "use":
        if not p["name"]:
            return await q.answer("اول یه اسم انتخاب کن", show_alert=True)
        await show(s_reg_doctrine(p))
        return await q.answer()
    if act == "chd":
        await show(s_reg_doctrine(p))
        return await q.answer()
    if act == "che":
        await show(s_reg_emblem(p))
        return await q.answer()
    if act == "d" and len(ps) > 1 and ps[1] in DOCTRINES and p["name"]:
        p["doctrine"] = ps[1]
        await show(s_reg_emblem(p) if not p["emblem"] else s_reg_confirm(p))
        return await q.answer()
    if act == "e" and len(ps) > 1 and ps[1].isdigit() and int(ps[1]) < len(EMBLEMS) and p["doctrine"]:
        p["emblem"] = EMBLEMS[int(ps[1])]
        await show(s_reg_confirm(p))
        return await q.answer()
    if act == "ok":
        if not (p["name"] and p["doctrine"] and p["emblem"]):
            return await q.answer("هنوز مراحل تموم نشده", show_alert=True)
        key = reg.name_key(p["name"])
        async with db.LOCK:
            if await db.is_banned(uid):
                return await q.answer("🚫 دسترسیت مسدوده", show_alert=True)
            c = E.new_country(uid, p["name"], p["leader"], p["doctrine"])
            c["name_key"], c["home"], c["emblem"] = key, p["home"], p["emblem"]
            try:
                await db.C.insert_one(c)
            except DuplicateKeyError:
                p["name"] = None
                return await q.answer("این اسم همین الان گرفته شد؛ یکی دیگه انتخاب کن", show_alert=True)
            if p["home"]:
                await db.G.update_one({"_id": p["home"]}, {"$set": {"title": getattr(chat, "title", "") or ""}}, upsert=True)
        PENDING.pop(uid, None)
        wt, wm = welcome(c)
        await show((wt, wm))
        return await q.answer("🎉")
    await q.answer("زمانش گذشته؛ دوباره بنویس «ثبت نام»", show_alert=True)


def welcome(c):
    st = config.STARTER
    t = (f"🎉 <b>تبریک {esc(c['leader'])} عزیز!</b>\n"
         f"{c.get('emblem', '🏛')} <b>{esc(c['name'])}</b> تأسیس شد و مردمت چشم‌به‌راهتن 💛\n\n"
         f"🏦 هدیه‌ی بانک مرکزی:\n"
         f"💰 {n(c['treasury'])} · 🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · 🔥 {st['phx']:.0f} PHX\n"
         f"🛡 {st['shield_h']} ساعت سپر · جایزه‌ی روزانه ۲ برابر تا {st['newbie_days']} روز\n\n"
         "✨ فقط کلمه بنویس:\n"
         "«<b>دنیای من</b>» پنل کشور · «<b>روزانه</b>» جایزه · «<b>کار</b>» درآمد\n"
         "«<b>ماموریت</b>» پاداش · «<b>جنگ</b>» حمله · «<b>راهنما</b>» همه‌ی کلمه‌ها\n\n"
         "موفق باشی فرمانروا! 🚀")
    return t, kb([[("🌍 باز کردن دنیای من", "m")]])


# ------------------------------------------------------------------ پایه
HELP = """📖 <b>راهنما</b> — کلمه رو بنویس، پنلش باز میشه 🌟

🌍 <b>شروع</b>: دنیای من · کشور من · رتبه · رتبه گروه
🎁 <b>درآمد</b>: روزانه · کار · ماموریت · تحویل
🏗 <b>ساخت</b>: ساختمان · ساخت مزرعه
💸 <b>سیاست</b>: سیاست · ناآرامی · پژوهش
🏦 <b>بانک</b>: بانک · سپرده 5000 · برداشت 2000 · وام 3000 · بازپرداخت همه
🏪 <b>بازار</b>: بازار · خرید غذا 500 · فروش فولاد 50 · آگهی فولاد 100 6 · خرید آگهی 12 · لغو آگهی 12
💱 <b>ارز و توکن</b>: ارز · خرید ارز PHX 5 · فروش ارز PHX 5 · سپر
🪖 <b>ارتش</b>: ارتش · آموزش پیاده 100 · ارتقا · ارتقا زمینی
⚔️ <b>جنگ</b>: جنگ · کشورها · حمله 1 · حمله 3 50 · حمله (ریپلای روی بازیکن) · اطلاعات · جاسوسی اسم‌کشور
🤝 <b>اتحاد</b> (توی گروه): اتحاد · ساخت اتحاد نام · پیوستن · ترک اتحاد · اهدا 1000 · جنگ اتحاد نام · ضربه"""


@cmd("start", need=False)
async def h_start(m, c, a):
    if c:
        return ui.dash(c) if m.chat.type == "private" else "سلام فرمانروا! 🌍 برای باز کردن پنلت بنویس «دنیای من»"
    if m.chat.type != "private":
        return "سلام! 🌍 برای شروع بنویس «<b>ثبت نام</b>» · لیست کلمه‌ها: «راهنما»"
    mt = re.fullmatch(r"reg_([np])(\d+)", (a or "").strip())
    if mt:                                       # از لینک عمیق گروه اومده
        REG_HOME[m.from_user.id] = -int(mt.group(2)) if mt.group(1) == "n" else int(mt.group(2))
    return await h_register(m, c, "")


@cmd("help", "راهنما", need=False)
async def h_help(m, c, a):
    return HELP


@cmd("me", "کشور من", "کشورمن", "پروفایل")
async def h_me(m, c, a):
    return ui.brief(c)


@cmd("menu", "منو", "دنیای من", "دنیایمن", "دنیا", "world")
async def h_menu(m, c, a):
    return ui.dash(c)


@cmd("daily", "روزانه", "جایزه")
async def h_daily(m, c, a):
    return ui.s_daily(c)


@cmd("work", "کار", "کار کن")
async def h_work(m, c, a):
    return ui.s_work(c)


@cmd("missions", "ماموریت", "ماموریت‌ها", "ماموریتها")
async def h_missions(m, c, a):
    return ui.s_missions(c)


@cmd("claim", "تحویل")
async def h_claim(m, c, a):
    ok, msg = eco.claim(c)
    text, mk = ui.s_missions(c)
    return msg + "\n\n" + text, mk


# ------------------------------------------------------------------ بانک
@cmd("bank", "بانک")
async def h_bank(m, c, a):
    return ui.s_bank(c)


def _bank_cmd(fn, maxf, usage):
    async def h(m, c, a):
        v = amount(a, maxf(c))
        if not v:
            return f"مبلغ معتبر بنویس (یا «همه»). مثال: <code>{usage}</code>"
        return fn(c, v)[1]
    return h


cmd("deposit", "سپرده", "واریز", args=True)(_bank_cmd(eco.bank_deposit, lambda c: c["treasury"], "سپرده 5000"))
cmd("withdraw", "برداشت", args=True)(_bank_cmd(eco.bank_withdraw, lambda c: c["bank"]["dep"], "برداشت 2000"))
cmd("loan", "وام", args=True)(_bank_cmd(eco.bank_borrow, lambda c: E.credit_limit(c) - c["bank"]["loan"], "وام 3000"))
cmd("repay", "بازپرداخت", "پرداخت وام", args=True)(_bank_cmd(eco.bank_repay, lambda c: c["bank"]["loan"], "بازپرداخت همه"))


# ------------------------------------------------------------------ بازار
ITEM_ALIAS = {"food": "food", "غذا": "food", "steel": "steel", "فولاد": "steel"}


def _item_qty(a):
    tk = a.split()
    if len(tk) < 2 or tk[0].lower() not in ITEM_ALIAS:
        return None, None
    return ITEM_ALIAS[tk[0].lower()], amount(tk[1])


@cmd("market", "بازار")
async def h_market(m, c, a):
    text, mk = ui.s_trade(c)
    docs = await db.M.find().sort("price", 1).limit(10).to_list(10)
    if docs:
        text += "\n\n📣 <b>آگهی‌های آزاد</b> (بنویس «خرید آگهی شماره»)\n" + "\n".join(
            f"#{d['_id']} {ITEMS[d['item']][0]} {d['qty']:,} × {d['price']} سکه" for d in docs)
    return text, mk


@cmd("buy", "خرید", args=True)
async def h_buy(m, c, a):
    it, q = _item_qty(a)
    if not it or not q:
        return "مثال: <code>خرید غذا 500</code> یا <code>خرید فولاد 50</code>"
    r = eco.global_buy(c, it, q)
    await eco.save_world()
    return r[1]


@cmd("sell", "فروش", args=True)
async def h_sell(m, c, a):
    it, q = _item_qty(a)
    if not it or not q:
        return "مثال: <code>فروش فولاد 50</code>"
    r = eco.global_sell(c, it, q)
    await eco.save_world()
    return r[1]


@cmd("list", "آگهی", args=True)
async def h_list(m, c, a):
    tk = a.split()
    it = ITEM_ALIAS.get(tk[0].lower()) if tk else None
    q, p = (amount(tk[1]), amount(tk[2])) if len(tk) >= 3 else (None, None)
    if not it or not q or not p:
        return "مثال: <code>آگهی فولاد 100 6</code> (۱۰۰ فولاد، هر واحد ۶ سکه)"
    return (await eco.list_create(c, it, q, p))[1]


@cmd("take", "خرید آگهی", args=True)
async def h_take(m, c, a):
    tk = a.lstrip("#").split()
    lid = amount(tk[0]) if tk else None
    if not lid:
        return "مثال: <code>خرید آگهی 12</code> یا <code>خرید آگهی 12 50</code>"
    ok, r = await eco.list_take(c, lid, amount(tk[1]) if len(tk) > 1 else None)
    if not ok:
        return r
    msg, seller, got = r
    from core import notify
    await notify(seller, f"💰 آگهی‌ات فروش رفت: +{got:,} سکه")
    return msg


@cmd("cancel", "لغو آگهی", args=True)
async def h_cancel(m, c, a):
    lid = amount(a.lstrip("#"))
    return (await eco.list_cancel(c, lid))[1] if lid else "مثال: <code>لغو آگهی 12</code>"


# ------------------------------------------------------------------ ارز و توکن
@cmd("fx", "ارز", "توکن", "token")
async def h_fx(m, c, a):
    return ui.s_fx(c)


def _fx_cmd(fn):
    async def h(m, c, a):
        tk = a.split()
        sym = tk[0].upper() if tk else ""
        mx = int(c["fx"].get(sym, 0))
        q = amount(tk[1], mx) if len(tk) > 1 else None
        if sym not in ASSETS or not q:
            return "مثال: <code>خرید ارز PHX 5</code> · نمادها: " + " ".join(ASSETS)
        r = fn(c, sym, q)
        await eco.save_world()
        return r[1]
    return h


cmd("fxbuy", "خرید ارز", args=True)(_fx_cmd(eco.fx_buy))
cmd("fxsell", "فروش ارز", args=True)(_fx_cmd(eco.fx_sell))


@cmd("shield", "سپر")
async def h_shield(m, c, a):
    return ui.s_shield(c)


@cmd("buyshield", "خرید سپر")
async def h_buyshield(m, c, a):
    return eco.buy_shield(c)[1]


# ------------------------------------------------------------------ پنل‌های کلمه‌ای
@cmd("war", "جنگ")
async def h_war(m, c, a):
    return await ui.s_war(c)


@cmd("intel", "اطلاعات", "سازمان اطلاعات")
async def h_intel(m, c, a):
    return await ui.s_spy(c)


@cmd("research", "پژوهش")
async def h_research(m, c, a):
    return ui.s_research(c)


@cmd("unrest", "ناآرامی")
async def h_unrest(m, c, a):
    return ui.s_unrest(c)


@cmd("policy", "سیاست", "بودجه", "مالیات")
async def h_policy(m, c, a):
    return ui.s_policy(c)


# ------------------------------------------------------------------ اتحاد (فقط توی گروه)
GROUP_ONLY = "🤝 اتحاد یعنی یه گروه! منو ببر توی گروهت و همونجا بنویس."


async def _refresh_ally(aid):
    a = await db.A.find_one({"_id": aid})
    if not a:
        return 0.0
    bonus = min(0.15, 0.01 * len(a["members"]))
    await db.C.update_many({"_id": {"$in": a["members"]}}, {"$set": {"ally_bonus": bonus, "alliance": aid}})
    return bonus


@cmd("ally_info", "اتحاد", "اطلاعات اتحاد")
async def h_ally(m, c, a):
    return await ui.s_ally(c)


@cmd("alliance_create", "ساخت اتحاد", args=True)
async def h_ally_create(m, c, a):
    if m.chat.type == "private":
        return GROUP_ONLY + " مثال: <code>ساخت اتحاد شیرها</code>"
    name = reg.clean(a)[:24]
    if len(name) < 2:
        return "اسم اتحادت رو هم بنویس 😊 مثال: <code>ساخت اتحاد شیرها</code>"
    if c.get("alliance"):
        return "تو همین الان عضو یه اتحادی 🤝"
    if await db.A.find_one({"$or": [{"_id": m.chat.id}, {"name": name}]}):
        return "این گروه یا این اسم قبلاً اتحاد داره"
    await db.A.insert_one({"_id": m.chat.id, "name": name, "leader": c["_id"], "members": [c["_id"]],
                           "bank": 0, "wins": 0, "losses": 0})
    c["alliance"], c["ally_bonus"] = m.chat.id, await _refresh_ally(m.chat.id)
    return f"🤝 اتحاد <b>{esc(name)}</b> ساخته شد! به بقیه بگو بنویسن «<b>پیوستن</b>» تا عضو بشن 💪"


@cmd("join", "پیوستن", "عضویت")
async def h_join(m, c, a):
    if m.chat.type == "private":
        return GROUP_ONLY
    al = await db.A.find_one({"_id": m.chat.id})
    if not al:
        return "این گروه هنوز اتحادی نداره؛ اولین نفر بنویسه «ساخت اتحاد نام» 🌱"
    if c.get("alliance"):
        return "تو همین الان عضو یه اتحادی 🤝"
    if len(al["members"]) >= config.ALLY_MAX:
        return "ظرفیت اتحاد پره 😅"
    await db.A.update_one({"_id": al["_id"]}, {"$addToSet": {"members": c["_id"]}})
    c["alliance"], c["ally_bonus"] = al["_id"], await _refresh_ally(al["_id"])
    return f"✅ {esc(c['name'])} به اتحاد {esc(al['name'])} پیوست؛ خوش اومدی! 🎉"


@cmd("leave", "ترک اتحاد", "خروج از اتحاد")
async def h_leave(m, c, a):
    if m.chat.type == "private":
        return GROUP_ONLY
    al = await db.A.find_one({"_id": m.chat.id})
    if not al or c.get("alliance") != al["_id"]:
        return "تو عضو این اتحاد نیستی"
    if al["leader"] == c["_id"]:
        return "رهبر نمی‌تونه اتحاد رو ترک کنه 👑"
    await db.A.update_one({"_id": al["_id"]}, {"$pull": {"members": c["_id"]}})
    c["alliance"], c["ally_bonus"] = None, 0.0
    await _refresh_ally(al["_id"])
    return "🚪 از اتحاد خارج شدی"


@cmd("donate", "اهدا", args=True)
async def h_donate(m, c, a):
    amt = amount(a, c["treasury"])
    if not amt:
        return "مثال: <code>اهدا 1000</code> (به بانک اتحاد)"
    if m.chat.type == "private" or c.get("alliance") != m.chat.id:
        return "این کار رو باید توی گروهِ اتحاد خودت انجام بدی"
    if c["treasury"] < amt:
        return "💸 پول کافی نیست"
    c["treasury"] -= amt
    await db.A.update_one({"_id": m.chat.id}, {"$inc": {"bank": amt}})
    return f"🏦 {n(amt)} سکه به بانک اتحاد اهدا شد؛ دمت گرم! 💛"


@cmd("ally_war", "جنگ اتحاد", args=True)
async def h_ally_war(m, c, a):
    if m.chat.type == "private":
        return GROUP_ONLY
    al = await db.A.find_one({"_id": m.chat.id})
    if not al or al["leader"] != c["_id"]:
        return "فقط رهبر اتحاد می‌تونه اعلام جنگ کنه 👑"
    b = await db.A.find_one({"name": reg.clean(a)[:24]})
    if not b or b["_id"] == al["_id"]:
        return "مثال: <code>جنگ اتحاد نام‌اتحاد‌دشمن</code>"
    if await ui.active_war(al["_id"]) or await ui.active_war(b["_id"]):
        return "یکی از اتحادها الان درگیر جنگه"
    await db.W.insert_one({"a": al["_id"], "b": b["_id"], "start": E.now(),
                           "end": E.now() + config.ALLY_WAR_H * 3600, "score": {"a": 0, "b": 0}, "active": True})
    msg = (f"🔥 <b>جنگ اتحادها!</b>\n{esc(al['name'])} ⚔️ {esc(b['name'])}\n"
           f"{config.ALLY_WAR_H:g} ساعت فرصت داریم. هر عضو با نوشتن «<b>ضربه</b>» هر ۳۰ دقیقه یه ضربه می‌زنه.\n"
           "برنده ۲۵٪ بانک بازنده رو غارت می‌کنه.")
    await notify(b["_id"], msg)
    return msg


@cmd("strike", "ضربه")
async def h_strike(m, c, a):
    return await ui.do_strike(c)


# ------------------------------------------------------------------ ساخت و ارتش
BUILD_ALIAS = {k: k for k in B} | {b["n"]: k for k, b in B.items()}
UNIT_ALIAS = {k: k for k in U} | {u["n"]: k for k, u in U.items()} | {"پیاده": "inf", "جنگنده": "jet"}
BR_ALIAS = {"land": "land", "زمینی": "land", "air": "air", "هوایی": "air", "sea": "sea", "دریایی": "sea"}


@cmd("buildings", "ساختمان", "ساختمان‌ها", "ساختمانها")
async def h_buildings(m, c, a):
    return ui.s_build(c)


@cmd("build", "بساز", "ساخت", args=True)
async def h_build(m, c, a):
    k = BUILD_ALIAS.get(reg.clean(a).lower())
    if not k:
        return "مثال: <code>ساخت مزرعه</code> · نام‌ها: " + "، ".join(b["n"] for b in B.values())
    return E.build(c, k)[1]


@cmd("army", "ارتش")
async def h_army(m, c, a):
    return ui.s_units(c)


@cmd("train", "آموزش", "استخدام", args=True)
async def h_train(m, c, a):
    tk = a.split()
    k = UNIT_ALIAS.get(tk[0].lower()) if tk else None
    q = amount(tk[1]) if len(tk) > 1 else None
    if not k or not q:
        return "مثال: <code>آموزش پیاده 100</code> · یگان‌ها: " + "، ".join(u["n"] for u in U.values())
    return E.buy_unit(c, k, q)[1]


@cmd("upgrade", "ارتقا", "ارتقاء", args=True)
async def h_upgrade(m, c, a):
    br = BR_ALIAS.get(reg.clean(a).lower())
    if not a:
        return ui.s_upgrade(c)
    if not br:
        return "مثال: <code>ارتقا زمینی</code> (زمینی / هوایی / دریایی)"
    return E.upgrade(c, br)[1]


# ------------------------------------------------------------------ جنگ و جاسوسی
@cmd("npcs", "کشورها", "جهان")
async def h_npcs(m, c, a):
    docs = await db.C.find({"npc": True}).sort("_id", -1).to_list(20)
    return "🌍 <b>کشورهای جهان</b>\n" + "\n".join(ui.npc_lines(docs)) + "\n\nمثال: <code>حمله 1</code> یا <code>حمله 3 50</code>"


async def resolve(m, tokens):
    r = m.reply_to_message
    if r and r.from_user and not r.from_user.is_bot and r.from_user.id != m.from_user.id:
        d = await db.C.find_one({"_id": r.from_user.id}, {"_id": 1})
        return d["_id"] if d else None
    key = " ".join(tokens)
    if not key:
        return None
    if key.isdigit() and 1 <= int(key) <= len(config.NPCS):
        return E.npc_id(int(key) - 1)
    k = reg.name_key(key)
    d = await db.C.find_one({"name_key": k}, {"_id": 1}) or await db.C.find_one(
        {"name_key": {"$regex": "^" + re.escape(k)}, "npc": {"$ne": True}}, {"_id": 1})
    return d["_id"] if d else None


@cmd("attack", "حمله", args=True)
async def h_attack(m, c, a):
    tk, pct = a.split(), 60
    if tk and re.fullmatch(r"\d{1,3}%?", tk[-1]) and (len(tk) > 1 or m.reply_to_message):
        pct = max(10, min(100, int(tk.pop().rstrip("%"))))
    tid = await resolve(m, tk)
    if tid is None:
        return "هدف پیدا نشد. «کشورها» رو ببین، یا روی پیام یه بازیکن ریپلای کن و بنویس «حمله»"
    return await ui.do_attack(c, tid, pct)


@cmd("spy", "جاسوسی", args=True)
async def h_spy(m, c, a):
    ops = {"scout": "scout", "sabotage": "sabotage", "steal": "steal", "جاسوسی": "scout", "خرابکاری": "sabotage", "سرقت": "steal"}
    tk, op = a.split(), "scout"
    if tk and tk[-1].lower() in ops:
        op = ops[tk.pop().lower()]
    tid = await resolve(m, tk)
    if tid is None:
        return "هدف پیدا نشد. مثال: <code>جاسوسی نام‌کشور</code>"
    return await ui.do_spy(c, tid, op)


@cmd("top", "رتبه", "رتبه‌بندی")
async def h_top(m, c, a):
    return await ui.s_top(c)


@cmd("gtop", "رتبه گروه", "رتبه‌ی گروه")
async def h_gtop(m, c, a):
    home = m.chat.id if m.chat.type != "private" else c.get("home")
    if not home:
        return "این دستور توی گروه کار می‌کنه"
    return await ui.s_top(c, home)


# ------------------------------------------------------------------ ادمین
async def _target(m, a):
    r = m.reply_to_message
    if r and r.from_user:
        return r.from_user.id
    v = amount(a.split()[0].lstrip("-")) if a else None
    return v


@cmd("ban", need=False)
async def h_ban(m, c, a):
    if m.from_user.id not in config.ADMINS:
        return None
    t = await _target(m, a)
    if not t:
        return "ریپلای یا آیدی عددی"
    await db.BANS.update_one({"_id": t}, {"$set": {"ts": time.time()}}, upsert=True)
    return f"🚫 {t} مسدود شد"


@cmd("unban", need=False)
async def h_unban(m, c, a):
    if m.from_user.id not in config.ADMINS:
        return None
    t = await _target(m, a)
    if not t:
        return "ریپلای یا آیدی عددی"
    await db.BANS.delete_one({"_id": t})
    return f"✅ {t} آزاد شد"


@cmd("give", need=False)
async def h_give(m, c, a):
    if m.from_user.id not in config.ADMINS:
        return None
    tk = a.split()
    v = amount(tk[-1]) if tk else None
    r = m.reply_to_message
    t = r.from_user.id if r and r.from_user else (amount(tk[0]) if len(tk) > 1 else None)
    if not v or not t:
        return "مثال: ریپلای + <code>/give 5000</code>"
    d = await db.load(t)
    if not d:
        return "کشور پیدا نشد"
    d["treasury"] += v
    await db.save(d)
    return f"✅ {v:,} سکه به {esc(d['name'])} داده شد"


# ------------------------------------------------------------------ دیسپچر
@router.message(F.text, _parsed)
async def dispatch(m: Message, parsed):
    func, need, args, bare = parsed
    if anon(m):
        if m.sender_chat is None and m.from_user and m.from_user.id == reg.ANON_ID:
            await m.reply("🕶 ادمین ناشناس نمی‌تونه بازی کنه؛ حالت ناشناس رو خاموش کن")
        return
    u = m.from_user
    if u.is_bot:
        return
    now = time.time()
    if now - LAST.get(u.id, 0) < config.CMD_GAP:
        return
    LAST[u.id] = now
    OWNER.set(u.id)
    if await db.is_banned(u.id):
        return await m.reply("🚫 دسترسیت مسدوده")
    if admin.blocked(u.id):
        return await m.reply(admin.SET["maint_msg"])
    try:
        async with db.LOCK:
            c = await db.load(u.id)
            if need and not c:
                return None if bare else await m.reply(NOT_REG)    # توی چت عادی مزاحم نشو
            out = await func(m, c, args)
            if c:
                await db.save(c)
    except Exception:
        logging.exception("cmd error")
        return await m.reply("⚠️ خطای داخلی؛ یه بار دیگه امتحان کن")
    await send(m, out)
