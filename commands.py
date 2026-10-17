"""دستورهای گروه (Command-driven): ثبت‌نام، بانک، بازار، ارز، ارتش، جنگ ...
هر دستور هم با اسلش کار می‌کنه (/bank) و هم فارسی بدون اسلش (بانک)."""
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
from core import INFO
from util import OWNER, amount, esc, kb, n

router = Router()
CMDS = {}
LAST = {}
AWAIT = {}      # (chat, uid) → زمان؛ منتظر اسم کشور
PENDING = {}    # uid → {name, chat, ts, leader}؛ منتظر انتخاب سبک

NOT_REG = "🏛 هنوز کشور نداری! بزن: <code>/register نام‌کشور</code> (یا «ثبت نام»)"


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


# ------------------------------------------------------------------ ثبت‌نام
INTRO = (f"🌍 <b>{config.BOT_NAME} — ساخت کشور</b>\n\nیه کشور کوچک تحویل می‌گیری با بسته‌ی حمایتی بانک مرکزی. "
         "اقتصاد، بانک، بازار، ارز، ارتش و جنگ دست توئه.\n\n")


async def start_pick(m, raw):
    u = m.from_user
    if not admin.SET["reg_open"] and u.id not in config.ADMINS:
        return "🔒 ثبت‌نام موقتاً بسته‌ست"
    ok, name = reg.validate_name(raw)
    if not ok:
        return "❌ " + name
    if not reg.throttle(u.id):
        return "⏳ تلاش‌های زیادی کردی؛ ۱۰ دقیقه‌ی دیگه دوباره امتحان کن"
    if await db.C.find_one({"name_key": reg.name_key(name)}, {"_id": 1}):
        return "❌ این اسم گرفته شده، یکی دیگه انتخاب کن"
    PENDING[u.id] = dict(name=name, chat=m.chat.id, ts=time.time(), leader=u.full_name[:32],
                         group=m.chat.type != "private")
    OWNER.set(u.id)
    t = [f"🏛 کشور <b>{esc(name)}</b>\nسبک شروعت رو انتخاب کن:\n"]
    rows = []
    for k, (e, nm, d) in DOCTRINES.items():
        t.append(f"{e} <b>{nm}</b> — {d}")
        rows.append([(f"{e} {nm}", f"rg:{k}")])
    return "\n".join(t), kb(rows + [[("❌ انصراف", "rg:x")]])


def welcome(c):
    st = config.STARTER
    return (f"👑 <b>{esc(c['name'])}</b> تأسیس شد!\n\n"
            f"🏦 <b>بسته‌ی حمایتی بانک مرکزی</b>\n"
            f"💰 {n(c['treasury'])} سکه · 🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · 🔥 {st['phx']:.0f} توکن PHX\n"
            f"🛡 {st['shield_h']} ساعت سپر · جایزه‌ی روزانه ×۲ تا {st['newbie_days']} روز\n\n"
            "<b>شروع سریع:</b>\n"
            "۱) /daily جایزه‌ی روزانه · /work کار\n"
            "۲) /missions ماموریت‌ها (پاداش پول و توکن)\n"
            "۳) /npcs و /attack ۱ — به کشورهای جهان حمله کن\n"
            "۴) /bank · /market · /fx · /upgrade\n"
            "۵) /menu منوی دکمه‌ای · /help همه‌ی دستورها")


@cmd("register", "ثبت نام", "ثبت‌نام", "ساخت کشور", need=False, args=True)
async def h_register(m, c, a):
    if c:
        return "✅ کشور داری:\n" + ui.brief(c)
    if await db.is_banned(m.from_user.id):
        return "🚫 دسترسیت مسدوده"
    if not a:
        AWAIT[(m.chat.id, m.from_user.id)] = time.time()
        if m.chat.type == "private":
            return INTRO + "اسم کشورت چیه؟"
        return (INTRO + "اسم کشورت رو با <b>ریپلای</b> به همین پیام بفرست 👇",
                ForceReply(selective=True, input_field_placeholder="اسم کشور"))
    return await start_pick(m, a)


@router.message(F.text, _awaiting)
async def on_name(m: Message):
    AWAIT.pop((m.chat.id, m.from_user.id), None)
    if anon(m) or await db.is_banned(m.from_user.id):
        return
    if await db.C.find_one({"_id": m.from_user.id}, {"_id": 1}):
        return await m.reply("✅ قبلاً ثبت‌نام کردی")
    await send(m, await start_pick(m, m.text))


async def rg_callback(q: CallbackQuery, choice):
    uid = q.from_user.id
    OWNER.set(uid)
    p = PENDING.get(uid)
    if not admin.SET["reg_open"] and uid not in config.ADMINS and choice != "x":
        return await q.answer("🔒 ثبت‌نام موقتاً بسته‌ست", show_alert=True)
    if choice == "x":
        PENDING.pop(uid, None)
        await q.message.edit_text("❌ ثبت‌نام لغو شد")
        return await q.answer()
    if not p or time.time() - p["ts"] > config.REG_PENDING_TTL or choice not in DOCTRINES:
        PENDING.pop(uid, None)
        return await q.answer("زمانش گذشته؛ دوباره /register بزن", show_alert=True)
    key = reg.name_key(p["name"])
    async with db.LOCK:
        if await db.is_banned(uid):
            return await q.answer("🚫 دسترسیت مسدوده", show_alert=True)
        if await db.C.find_one({"_id": uid}, {"_id": 1}):
            PENDING.pop(uid, None)
            return await q.answer("قبلاً ثبت‌نام کردی", show_alert=True)
        c = E.new_country(uid, p["name"], p["leader"], choice)
        c["name_key"] = key
        c["home"] = p["chat"] if p["group"] else None
        try:
            await db.C.insert_one(c)
        except DuplicateKeyError:
            PENDING.pop(uid, None)
            return await q.answer("این اسم همین الان گرفته شد", show_alert=True)
        if p["group"]:
            await db.G.update_one({"_id": p["chat"]}, {"$set": {"title": getattr(q.message.chat, "title", "")}}, upsert=True)
    PENDING.pop(uid, None)
    await q.message.edit_text(welcome(c))
    await q.answer("🎉")


# ------------------------------------------------------------------ پایه
HELP = """📖 <b>راهنمای دستورها</b> (هر کدوم فارسی بدون اسلش هم کار می‌کنه)

<b>شروع</b>: /register نام · /me کشور من · /menu منو · /top رتبه · /gtop رتبه‌ی گروه
<b>درآمد</b>: /daily جایزه · /work کار · /missions ماموریت · /claim تحویل
<b>بانک</b>: /bank · /deposit مبلغ · /withdraw مبلغ · /loan مبلغ · /repay مبلغ
<b>بازار</b>: /market · /buy غذا 500 · /sell فولاد 50 · /list فولاد 100 6 · /take شماره · /cancel شماره
<b>ارز و توکن</b>: /fx · /fxbuy PHX 5 · /fxsell PHX 5 · /shield
<b>ساختن</b>: /build مزرعه · /buildings
<b>ارتش</b>: /army · /train پیاده 100 · /upgrade زمینی|هوایی|دریایی
<b>جنگ</b>: /npcs · /attack 1 [درصد] · /attack (ریپلای روی بازیکن) · /spy نام [scout|sabotage|steal]
<b>اتحاد</b>: /alliance_create نام · /join · /leave · /ally_info · /donate · /ally_war · /strike"""


@cmd("start", need=False)
async def h_start(m, c, a):
    if m.chat.type != "private":
        return "سلام! 🌍 برای شروع: <code>/register</code> · راهنما: /help"
    if c:
        t, mk = ui.dash(c)
        return t, mk
    AWAIT[(m.chat.id, m.from_user.id)] = time.time()
    return INTRO + "اسم کشورت چیه؟"


@cmd("help", "راهنما", need=False)
async def h_help(m, c, a):
    return HELP


@cmd("me", "کشور من", "کشورمن", "پروفایل")
async def h_me(m, c, a):
    return ui.brief(c)


@cmd("menu", "منو")
async def h_menu(m, c, a):
    return ui.dash(c)


@cmd("daily", "روزانه", "جایزه")
async def h_daily(m, c, a):
    return eco.daily(c)[1]


@cmd("work", "کار کن")
async def h_work(m, c, a):
    return eco.work(c)[1]


@cmd("missions", "ماموریت", "ماموریت‌ها", "ماموریتها")
async def h_missions(m, c, a):
    return ui.s_missions(c)


@cmd("claim", "تحویل")
async def h_claim(m, c, a):
    return eco.claim(c)[1]


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


cmd("deposit", "سپرده", "واریز", args=True)(_bank_cmd(eco.bank_deposit, lambda c: c["treasury"], "/deposit 5000"))
cmd("withdraw", "برداشت", args=True)(_bank_cmd(eco.bank_withdraw, lambda c: c["bank"]["dep"], "/withdraw 2000"))
cmd("loan", "وام", args=True)(_bank_cmd(eco.bank_borrow, lambda c: E.credit_limit(c) - c["bank"]["loan"], "/loan 3000"))
cmd("repay", "بازپرداخت", "پرداخت وام", args=True)(_bank_cmd(eco.bank_repay, lambda c: c["bank"]["loan"], "/repay همه"))


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
        text += "\n\n📣 <b>آگهی‌های آزاد</b> (/take شماره [تعداد])\n" + "\n".join(
            f"#{d['_id']} {ITEMS[d['item']][0]} {d['qty']:,} × {d['price']} سکه" for d in docs)
    return text, mk


@cmd("buy", "خرید", args=True)
async def h_buy(m, c, a):
    it, q = _item_qty(a)
    if not it or not q:
        return "مثال: <code>/buy غذا 500</code> یا <code>/buy steel 50</code>"
    r = eco.global_buy(c, it, q)
    await eco.save_world()
    return r[1]


@cmd("sell", "فروش", args=True)
async def h_sell(m, c, a):
    it, q = _item_qty(a)
    if not it or not q:
        return "مثال: <code>/sell فولاد 50</code>"
    r = eco.global_sell(c, it, q)
    await eco.save_world()
    return r[1]


@cmd("list", "آگهی", args=True)
async def h_list(m, c, a):
    tk = a.split()
    it = ITEM_ALIAS.get(tk[0].lower()) if tk else None
    q, p = (amount(tk[1]), amount(tk[2])) if len(tk) >= 3 else (None, None)
    if not it or not q or not p:
        return "مثال: <code>/list فولاد 100 6</code> (۱۰۰ فولاد، هر واحد ۶ سکه)"
    return (await eco.list_create(c, it, q, p))[1]


@cmd("take", "خرید آگهی", args=True)
async def h_take(m, c, a):
    tk = a.lstrip("#").split()
    lid = amount(tk[0]) if tk else None
    if not lid:
        return "مثال: <code>/take 12</code> یا <code>/take 12 50</code>"
    ok, r = await eco.list_take(c, lid, amount(tk[1]) if len(tk) > 1 else None)
    if not ok:
        return r
    msg, seller, got = r
    from core import notify
    await notify(seller, f"💰 آگهی‌ات فروش رفت: +{got:,} سکه")
    return msg


@cmd("cancel", "لغو", args=True)
async def h_cancel(m, c, a):
    lid = amount(a.lstrip("#"))
    return (await eco.list_cancel(c, lid))[1] if lid else "مثال: <code>/cancel 12</code>"


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
            return "مثال: <code>/fxbuy PHX 5</code> · نمادها: " + " ".join(ASSETS)
        r = fn(c, sym, q)
        await eco.save_world()
        return r[1]
    return h


cmd("fxbuy", "خرید ارز", args=True)(_fx_cmd(eco.fx_buy))
cmd("fxsell", "فروش ارز", args=True)(_fx_cmd(eco.fx_sell))


@cmd("shield", "سپر")
async def h_shield(m, c, a):
    return eco.buy_shield(c)[1]


# ------------------------------------------------------------------ ساخت و ارتش
BUILD_ALIAS = {k: k for k in B} | {b["n"]: k for k, b in B.items()}
UNIT_ALIAS = {k: k for k in U} | {u["n"]: k for k, u in U.items()} | {"پیاده": "inf", "جنگنده": "jet"}
BR_ALIAS = {"land": "land", "زمینی": "land", "air": "air", "هوایی": "air", "sea": "sea", "دریایی": "sea"}


@cmd("buildings", "ساختمان‌ها", "ساختمانها")
async def h_buildings(m, c, a):
    return ui.s_build(c)


@cmd("build", "بساز", "ساخت", args=True)
async def h_build(m, c, a):
    k = BUILD_ALIAS.get(reg.clean(a).lower())
    if not k:
        return "مثال: <code>/build مزرعه</code> · نام‌ها: " + "، ".join(b["n"] for b in B.values())
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
        return "مثال: <code>/train پیاده 100</code> · یگان‌ها: " + "، ".join(u["n"] for u in U.values())
    return E.buy_unit(c, k, q)[1]


@cmd("upgrade", "ارتقا", "ارتقاء", args=True)
async def h_upgrade(m, c, a):
    br = BR_ALIAS.get(reg.clean(a).lower())
    if not a:
        return ui.s_upgrade(c)
    if not br:
        return "مثال: <code>/upgrade زمینی</code> (زمینی / هوایی / دریایی)"
    return E.upgrade(c, br)[1]


# ------------------------------------------------------------------ جنگ و جاسوسی
@cmd("npcs", "کشورها", "جهان")
async def h_npcs(m, c, a):
    docs = await db.C.find({"npc": True}).sort("_id", -1).to_list(20)
    return "🌍 <b>کشورهای جهان</b>\n" + "\n".join(ui.npc_lines(docs)) + "\n\n<code>/attack ۱</code> یا <code>/attack ۳ ۵۰</code>"


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
        return "هدف پیدا نشد. <code>/npcs</code> رو ببین، یا روی پیام یه بازیکن ریپلای کن و /attack بزن"
    return await ui.do_attack(c, tid, pct)


@cmd("spy", "جاسوسی", args=True)
async def h_spy(m, c, a):
    ops = {"scout": "scout", "sabotage": "sabotage", "steal": "steal", "جاسوسی": "scout", "خرابکاری": "sabotage", "سرقت": "steal"}
    tk, op = a.split(), "scout"
    if tk and tk[-1].lower() in ops:
        op = ops[tk.pop().lower()]
    tid = await resolve(m, tk)
    if tid is None:
        return "هدف پیدا نشد. مثال: <code>/spy نام‌کشور scout</code>"
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
