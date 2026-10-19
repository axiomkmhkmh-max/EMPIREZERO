"""دنیای زنده: اخبار و شایعه‌ها، جدول برترین‌ها (هفتگی/فصلی با جایزه) و دیپلماسی (پیمان، معامله، هدیه)."""
import asyncio
import logging
import random
import time

import config
import db
import engine as E
import events
import prog
from config import ASSETS, ITEMS, U
from core import bot, notify, tlog
from util import BACK, esc, kb, n

SEASON = {"wid": -1, "wend": 0.0, "sid": 1, "send": 0.0}
NEWS = {"list": [], "dirty": False}


def now():
    return time.time()


# ================================================================== اخبار و شایعه‌ها
def news(text, important=False):
    """یه خبر به فهرست اخبار جهان اضافه می‌کنه (هیچ‌وقت خطا نمیده)."""
    NEWS["list"].append({"t": now(), "x": text})
    NEWS["list"] = NEWS["list"][-40:]
    NEWS["dirty"] = True
    if important and config.NEWS_CHANNEL:
        asyncio.create_task(_post_channel(text))


async def _post_channel(text):
    try:
        await bot.send_message(config.NEWS_CHANNEL, "📰 " + text)
    except Exception:
        pass


def news_lines(k=8):
    out = []
    for x in NEWS["list"][-k:][::-1]:
        out.append(f"• {x['x']} <i>({prog.dur(now() - x['t'])} پیش)</i>")
    return out


def s_news(c=None):
    lines = news_lines(10)
    t = "📰 <b>اخبار و شایعه‌های جهان</b>\n\n" + ("\n".join(lines) if lines else "هنوز خبری نیست؛ دنیا آرومه 🌍")
    return t, kb([[("🔄 بروزرسانی", "nw")], BACK])


_RUMOR_NPC = ["امپراتوری زروان در مرزهاش نیرو جمع می‌کنه", "فدراسیون نوردلند ناوگانش رو به آب انداخت",
              "پادشاهی کالوین تازه یه پدافند جدید خریده", "اتحادیه‌ی هورمند دنبال متحد می‌گرده",
              "جمهوری آرداک بازار فولاد رو زیر نظر داره"]


async def rumor_step():
    """یه شایعه/خبر زنده از وضعیت واقعی بازیکن‌ها می‌سازه (ارتش دو برابر شده، ثروت رکورد زده ...)."""
    docs = await db.C.find({"npc": {"$ne": True}}).to_list(2000)
    if not docs:
        return
    best = None
    for d in docs:
        E.defaults(d)
        sn = d.get("snap") or {}
        army = E.army_size(d)
        if sn.get("army", 0) >= 200 and army >= sn["army"] * 1.8:
            best = f"🔥 شایعه شده کشور <b>{esc(d['name'])}</b> ارتشش رو {army / sn['army']:.1f} برابر کرده!"
            break
    if not best:
        d = random.choice(docs)
        k = random.random()
        if k < 0.35 and d["treasury"] >= 100000:
            best = f"💰 می‌گن خزانه‌ی <b>{esc(d['name'])}</b> از {int(d['treasury'] // 50000 * 50000):,} سکه گذشته"
        elif k < 0.6 and d.get("land", 5) >= 8:
            best = f"🏞 <b>{esc(d['name'])}</b> حالا {d['land']} استان داره؛ همسایه‌ها نگرانن"
        elif k < 0.8:
            best = "🗣 " + random.choice(_RUMOR_NPC)
        else:
            return
    news(best)


async def snapshot_step():
    """هر چند ساعت یه عکس از اندازه‌ی ارتش هر بازیکن می‌گیره تا افزایش ناگهانی تشخیص داده بشه."""
    async with db.LOCK:
        t = now()
        async for d in db.C.find({"npc": {"$ne": True}}, {"_id": 1, "snap": 1}):
            sn = d.get("snap") or {}
            if t - sn.get("t", 0) < 6 * 3600:
                continue
            c = await db.load(d["_id"])
            if c:
                c["snap"] = {"army": E.army_size(c), "t": t}
                await db.save(c)


# ================================================================== جدول برترین‌ها / هفته / فصل
BOARDS = {"war": ("⚔️", "جنگ", "امتیاز جنگ این دوره"), "earn": ("💰", "ثروت", "سکه‌ی درآمد این دوره"),
          "pow": ("💪", "قدرت", "قدرت نظامی (حمله + دفاع)")}
_CACHE = {}


def board_value(d, board, scope):
    if board == "pow":
        return E.attack_power(d) + E.defense_power(d)
    return prog.stat(d, scope, board)


async def top(board, scope, k=10):
    key = (board, scope)
    hit = _CACHE.get(key)
    if hit and now() - hit[0] < 30:
        return hit[1][:k]
    docs = await db.C.find({"npc": {"$ne": True}}).to_list(5000)
    rows = []
    for d in docs:
        E.defaults(d)
        v = board_value(d, board, scope)
        if v > 0:
            rows.append((v, d["_id"], d["name"], d.get("emblem", "🏛")))
    rows.sort(reverse=True)
    _CACHE[key] = (now(), rows)
    return rows[:k]


def prize_text(scope):
    pr = config.WEEK_PRIZES if scope == "w" else config.SEASON_PRIZES
    return " · ".join(f"{['🥇', '🥈', '🥉'][i - 1]} {int(v[0] * config.PRIZE_MULT):,}💰 {int(v[1] * config.PRIZE_MULT)}⚡" for i, v in pr.items())


async def s_boards(c, board="war", scope="w"):
    board = board if board in BOARDS else "war"
    scope = scope if scope in ("w", "s") else "w"
    e, nm, desc = BOARDS[board]
    rows = await top(board, scope, 10)
    left = (SEASON["wend"] if scope == "w" else SEASON["send"]) - now()
    mine = board_value(c, board, scope)
    allrows = _CACHE[(board, scope)][1]
    rank = next((i + 1 for i, r in enumerate(allrows) if r[1] == c["_id"]), None)
    t = [f"🏅 <b>جدول برترین‌ها — {e} {nm} ({'هفتگی' if scope == 'w' else 'فصل ' + str(SEASON['sid'])})</b>",
         f"<i>{desc}</i>", f"⏳ تا پایان دوره: {prog.dur(left)}", f"🎁 جایزه‌ها: {prize_text(scope)}", ""]
    for i, r in enumerate(rows):
        t.append(f"{['🥇', '🥈', '🥉'][i] if i < 3 else str(i + 1) + '.'} {r[3]} {esc(r[2])} — {n(r[0])}")
    if not rows:
        t.append("هنوز کسی امتیاز نگرفته؛ اولین نفر باش! 💪")
    t.append(f"\n📍 تو: {n(mine)} · رتبه {rank or '—'}")
    rows_b = [[(f"{BOARDS[b][0]} {BOARDS[b][1]}", f"bd:{b}:{scope}") for b in BOARDS],
              [("📅 هفتگی", f"bd:{board}:w"), ("🏆 فصلی", f"bd:{board}:s")]]
    return "\n".join(t), kb(rows_b + [BACK])


async def init():
    """بارگذاری حالت هفته/فصل؛ باید قبل از هر load کشوری صدا زده بشه."""
    d = await db.META.find_one({"_id": "season"})
    cw = prog.calc_week()
    if not d:
        d = {"_id": "season", "wid": cw, "wend": prog.week_end_ts(cw), "sid": 1, "send": now() + config.SEASON_DAYS * 86400}
        await db.META.replace_one({"_id": "season"}, d, upsert=True)
    SEASON.update({k: d[k] for k in ("wid", "wend", "sid", "send")})
    prog.WEEK["id"] = SEASON["wid"]
    prog.SEASON["id"] = SEASON["sid"]
    # n (تعداد برندگان فصل) برای صفحه‌ی ادمین


async def _save_state():
    await db.META.replace_one({"_id": "season"}, {"_id": "season", **{k: SEASON[k] for k in ("wid", "wend", "sid", "send")}}, upsert=True)


async def _award(uid, scope, rank, board):
    pr = config.WEEK_PRIZES if scope == "w" else config.SEASON_PRIZES
    coins, zero = pr[rank]
    coins, zero = int(coins * config.PRIZE_MULT), int(zero * config.PRIZE_MULT)
    upd = {"$inc": {"treasury": coins, "fx.PHX": zero}}
    if scope == "s" and rank == 1:
        upd["$push"] = {"titles": f"👑 قهرمان فصل {SEASON['sid']} ({BOARDS[board][1]})"}
    await db.C.update_one({"_id": uid}, upd)
    return coins, zero


async def finalize(scope):
    """پایان هفته یا فصل: جایزه به سه نفر اول هر جدول، خبر و اعلام برندگان."""
    async with db.LOCK:
        _CACHE.clear()
        lines = []
        for board, (e, nm, _) in BOARDS.items():
            rows = await top(board, scope, 3)
            for i, r in enumerate(rows, 1):
                coins, zero = await _award(r[1], scope, i, board)
                lines.append(f"{['🥇', '🥈', '🥉'][i - 1]} {e} {nm}: {r[3]} {esc(r[2])} ({n(r[0])})")
                await notify(r[1], f"🏆 <b>تبریک!</b> رتبه‌ی {i} جدول {e} {nm} {'این هفته' if scope == 'w' else 'این فصل'}\n"
                                   f"🎁 جایزه: {coins:,}💰 {zero}⚡")
        _CACHE.clear()
        if scope == "w":
            cw = max(SEASON["wid"] + 1, prog.calc_week())
            SEASON["wid"], SEASON["wend"] = cw, prog.week_end_ts(cw)
            prog.WEEK["id"] = cw
            title = "🏅 برندگان هفته"
        else:
            SEASON["sid"] += 1
            SEASON["send"] = now() + config.SEASON_DAYS * 86400
            prog.SEASON["id"] = SEASON["sid"]
            title = f"🏆 برندگان فصل {SEASON['sid'] - 1}"
        await _save_state()
    text = f"<b>{title}</b>\n" + ("\n".join(lines) if lines else "این دوره کسی امتیاز نگرفت.")
    news(title + ": " + (lines[0] if lines else "—"), important=True)
    tlog("🏅", title, text)
    return text


async def season_loop():
    while True:
        await asyncio.sleep(60)
        try:
            if now() >= SEASON["wend"]:
                txt = await finalize("w")
                await broadcast_players("🏅 <b>هفته تموم شد!</b>\n" + txt)
            if now() >= SEASON["send"]:
                txt = await finalize("s")
                await broadcast_players("🏆 <b>فصل تموم شد؛ فصل جدید شروع شد!</b>\n" + txt)
            if NEWS["dirty"]:
                NEWS["dirty"] = False
                await db.META.replace_one({"_id": "news"}, {"_id": "news", "list": NEWS["list"]}, upsert=True)
        except Exception:
            logging.exception("season_loop")
            from core import log_exc
            log_exc("حلقه‌ی هفته و فصل")


async def load_news():
    d = await db.META.find_one({"_id": "news"}) or {}
    NEWS["list"] = d.get("list", [])


async def broadcast_players(text, only_active_days=30):
    """پیام به همه‌ی بازیکن‌های فعال (پس‌زمینه، با رعایت محدودیت تلگرام)."""
    since = now() - only_active_days * 86400
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    ids = [d["_id"] async for d in db.C.find({"npc": {"$ne": True}, "last_tick": {"$gt": since}}, {"_id": 1}) if d["_id"] not in banned]

    async def run():
        for uid in ids:
            await notify(uid, text)
            await asyncio.sleep(0.05)
    asyncio.create_task(run())
    return len(ids)


# ================================================================== دیپلماسی
RES = {"coins": ("💰", "سکه", "treasury", 1.0), "food": ("🌾", "غذا", "food", 1.2),
       "steel": ("⚙️", "فولاد", "steel", 5.5), "zero": ("⚡", "زیرو", "PHX", 100.0)}
RES_ALIAS = {"سکه": "coins", "coin": "coins", "coins": "coins", "غذا": "food", "food": "food",
             "فولاد": "steel", "steel": "steel", "زیرو": "zero", "zero": "zero"}


def _get(c, r):
    f = RES[r][2]
    return c["fx"].get("PHX", 0.0) if f == "PHX" else c[f]


def _put(c, r, v):
    f = RES[r][2]
    if f == "PHX":
        c["fx"]["PHX"] = max(0.0, c["fx"].get("PHX", 0.0) + v)
    else:
        c[f] += v


def value_of(r, amt):
    return amt * RES[r][3]


async def has_pact(a, b):
    return await db.PACTS.find_one({"kind": "pact", "status": "active", "end": {"$gt": now()},
                                    "$or": [{"a": a, "b": b}, {"a": b, "b": a}]}) is not None


async def pact_propose(c, tid, hours):
    if tid == c["_id"] or tid < 0:
        return False, "با خودت یا NPC که نمی‌شه پیمان بست"
    t = await db.C.find_one({"_id": tid}, {"_id": 1, "name": 1})
    if not t:
        return False, "کشور مقابل پیدا نشد"
    if hours not in config.PACT_HOURS:
        return False, "مدت پیمان باید یکی از اینا باشه: " + "، ".join(str(h) for h in config.PACT_HOURS) + " ساعت"
    if await has_pact(c["_id"], tid):
        return False, "بینتون همین الان پیمان فعاله"
    if await db.PACTS.find_one({"kind": "pact", "status": "pending", "a": c["_id"], "b": tid}):
        return False, "پیشنهاد قبلی هنوز منتظر جواب مونده"
    pid = await db.next_id("pact")
    await db.PACTS.insert_one({"_id": pid, "kind": "pact", "a": c["_id"], "b": tid, "hours": hours, "status": "pending",
                               "created": now(), "end": 0})
    prog.bump(c, "diplo")
    from util import OWNER
    tok = OWNER.set(tid)
    try:
        mk = kb([[("✅ قبول", f"dp:y:{pid}"), ("❌ رد", f"dp:n:{pid}")]])
    finally:
        OWNER.reset(tok)
    await notify(tid, f"🤝 <b>پیشنهاد پیمان عدم‌تجاوز</b>\n{esc(c['name'])} می‌خواد {hours} ساعت با هم نجنگید.", mk)
    return True, f"🤝 پیشنهاد پیمان {hours} ساعته برای {esc(t['name'])} فرستاده شد"


async def pact_answer(c, pid, yes):
    p = await db.PACTS.find_one({"_id": pid, "kind": "pact", "status": "pending", "b": c["_id"]})
    if not p:
        return False, "این پیشنهاد دیگه معتبر نیست"
    if not yes:
        await db.PACTS.update_one({"_id": pid}, {"$set": {"status": "declined"}})
        await notify(p["a"], f"❌ {esc(c['name'])} پیشنهاد پیمانت رو رد کرد")
        return True, "❌ پیشنهاد رد شد"
    await db.PACTS.update_one({"_id": pid}, {"$set": {"status": "active", "end": now() + p["hours"] * 3600, "start": now()}})
    a = await db.C.find_one({"_id": p["a"]}, {"name": 1})
    an = a["name"] if a else "؟"
    prog.bump(c, "diplo")
    await notify(p["a"], f"✅ {esc(c['name'])} پیمان رو قبول کرد؛ {p['hours']} ساعت صلح 🕊")
    news(f"🤝 پیمان عدم‌تجاوز بین <b>{esc(an)}</b> و <b>{esc(c['name'])}</b> بسته شد ({p['hours']} ساعت)", important=True)
    return True, f"✅ پیمان با {esc(an)} فعال شد ({p['hours']} ساعت)"


async def pact_break(c, pid):
    p = await db.PACTS.find_one({"_id": pid, "kind": "pact", "status": "active", "$or": [{"a": c["_id"]}, {"b": c["_id"]}]})
    if not p:
        return False, "پیمان پیدا نشد"
    other = p["b"] if p["a"] == c["_id"] else p["a"]
    fee = min(20000, int(max(0, c["treasury"]) * config.PACT_BREAK_FEE))
    c["treasury"] -= fee
    await db.C.update_one({"_id": other}, {"$inc": {"treasury": fee}})
    await db.PACTS.update_one({"_id": pid}, {"$set": {"status": "ended", "end": now()}})
    await notify(other, f"💔 {esc(c['name'])} پیمان رو شکست و {fee:,} سکه غرامت داد")
    news(f"💔 <b>{esc(c['name'])}</b> پیمان عدم‌تجاوز رو شکست!", important=True)
    return True, f"💔 پیمان شکسته شد (غرامت {fee:,} سکه به طرف مقابل)"


async def offer_create(c, tid, give, ask):
    """پیشنهاد معامله‌ی دوطرفه؛ کالای خودت همون لحظه بلوکه میشه تا کلاهبرداری نشه."""
    (gr, ga), (ar, aa) = give, ask
    if tid == c["_id"] or tid < 0:
        return False, "هدف معتبر نیست"
    t = await db.C.find_one({"_id": tid}, {"name": 1})
    if not t:
        return False, "کشور مقابل پیدا نشد"
    if ga <= 0 or aa <= 0 or gr == ar:
        return False, "مثال: معامله نام‌کشور فولاد 100 غذا 500"
    if _get(c, gr) < ga:
        return False, f"{RES[gr][1]} کافی نداری"
    _put(c, gr, -ga)
    oid = await db.next_id("pact")
    await db.PACTS.insert_one({"_id": oid, "kind": "trade", "a": c["_id"], "b": tid, "give": [gr, ga], "ask": [ar, aa],
                               "status": "pending", "created": now()})
    prog.bump(c, "diplo")
    from util import OWNER
    tok = OWNER.set(tid)
    try:
        mk = kb([[("✅ قبول", f"dp:ty:{oid}"), ("❌ رد", f"dp:tn:{oid}")]])
    finally:
        OWNER.reset(tok)
    await notify(tid, f"🤝 <b>پیشنهاد معامله از {esc(c['name'])}</b>\nمی‌ده: {RES[gr][0]} {ga:,} {RES[gr][1]}\n"
                      f"می‌خواد: {RES[ar][0]} {aa:,} {RES[ar][1]}", mk)
    return True, f"📨 پیشنهاد معامله فرستاده شد (کالات تا جواب بلوکه‌ست؛ {config.OFFER_TTL // 3600} ساعت اعتبار)"


async def offer_answer(c, oid, yes):
    o = await db.PACTS.find_one({"_id": oid, "kind": "trade", "status": "pending", "b": c["_id"]})
    if not o:
        return False, "این پیشنهاد دیگه معتبر نیست"
    a = await db.load(o["a"])
    (gr, ga), (ar, aa) = o["give"], o["ask"]
    if not yes or not a:
        if a:
            _put(a, gr, ga)
            await db.save(a)
        await db.PACTS.update_one({"_id": oid}, {"$set": {"status": "declined"}})
        if a:
            await notify(a["_id"], f"❌ {esc(c['name'])} معامله رو رد کرد؛ کالات برگشت")
        return True, "❌ رد شد"
    if _get(c, ar) < aa:
        return False, f"{RES[ar][1]} کافی نداری"
    fee_g, fee_a = int(ga * config.TRADE_FEE), int(aa * config.TRADE_FEE)
    _put(c, ar, -aa)
    _put(c, gr, ga - fee_g)
    _put(a, ar, aa - fee_a)
    await db.save(a)
    await db.PACTS.update_one({"_id": oid}, {"$set": {"status": "done", "end": now()}})
    prog.bump(c, "diplo")
    from guard import record_transfer
    await record_transfer(a, c, value_of(gr, ga) + value_of(ar, aa), "trade")
    await notify(a["_id"], f"✅ {esc(c['name'])} معامله رو قبول کرد: گرفتی {RES[ar][0]} {aa - fee_a:,} {RES[ar][1]}")
    return True, f"✅ معامله انجام شد: گرفتی {RES[gr][0]} {ga - fee_g:,} {RES[gr][1]} (کارمزد {int(config.TRADE_FEE * 100)}٪)"


async def gift_send(c, tid, res, amt):
    if tid == c["_id"] or tid < 0:
        return False, "هدف معتبر نیست"
    if res not in RES or amt <= 0:
        return False, "مثال: هدیه نام‌کشور فولاد 100"
    if now() - c["created"] < config.GIFT_MIN_AGE_H * 3600:
        return False, f"کشورت باید حداقل {config.GIFT_MIN_AGE_H} ساعت از تأسیسش گذشته باشه"
    if _get(c, res) < amt:
        return False, f"{RES[res][1]} کافی نداری"
    day = prog.day_id()
    g = c["gifted"]
    if g.get("d") != day:
        g["d"], g["amt"] = day, 0
    val = value_of(res, amt)
    if g["amt"] + val > config.GIFT_DAILY_CAP:
        return False, f"سقف هدیه‌ی روزانه {config.GIFT_DAILY_CAP:,} (به ارزش سکه) پر شده"
    t = await db.load(tid)
    if not t:
        return False, "کشور مقابل پیدا نشد"
    fee = int(amt * config.GIFT_FEE)
    _put(c, res, -amt)
    _put(t, res, amt - fee)
    g["amt"] += val
    await db.save(t)
    prog.bump(c, "diplo")
    from guard import record_transfer
    await record_transfer(c, t, val, "gift")
    await notify(tid, f"🎁 {esc(c['name'])} بهت هدیه داد: {RES[res][0]} {amt - fee:,} {RES[res][1]}")
    return True, f"🎁 {amt:,} {RES[res][1]} برای {esc(t['name'])} فرستاده شد (کارمزد {fee:,})"


async def s_diplo(c):
    me = c["_id"]
    pacts = await db.PACTS.find({"kind": "pact", "status": "active", "end": {"$gt": now()}, "$or": [{"a": me}, {"b": me}]}).to_list(10)
    inbox = await db.PACTS.find({"status": "pending", "b": me}).to_list(10)
    out = await db.PACTS.find({"status": "pending", "a": me}).to_list(10)
    ids = {x["a"] for x in pacts + inbox + out} | {x["b"] for x in pacts + inbox + out}
    nm = {d["_id"]: d["name"] async for d in db.C.find({"_id": {"$in": list(ids)}}, {"name": 1})}
    t = ["🤝 <b>دیپلماسی</b>", ""]
    rows = []
    for p in pacts:
        o = p["b"] if p["a"] == me else p["a"]
        t.append(f"🕊 پیمان با {esc(nm.get(o, '؟'))} — {prog.dur(p['end'] - now())} مانده")
        rows.append([(f"💔 شکستن پیمان با {nm.get(o, '؟')[:14]}", f"dp:x:{p['_id']}")])
    for p in inbox:
        if p["kind"] == "pact":
            t.append(f"📨 پیشنهاد پیمان {p['hours']}ساعته از {esc(nm.get(p['a'], '؟'))}")
            rows.append([("✅ قبول", f"dp:y:{p['_id']}"), ("❌ رد", f"dp:n:{p['_id']}")])
        else:
            t.append(f"📨 معامله از {esc(nm.get(p['a'], '؟'))}: می‌ده {RES[p['give'][0]][0]}{p['give'][1]:,} · می‌خواد {RES[p['ask'][0]][0]}{p['ask'][1]:,}")
            rows.append([("✅ قبول معامله", f"dp:ty:{p['_id']}"), ("❌ رد", f"dp:tn:{p['_id']}")])
    for p in out:
        t.append(f"⏳ منتظر جواب {esc(nm.get(p['b'], '؟'))} ({'پیمان' if p['kind'] == 'pact' else 'معامله'})")
        rows.append([(f"🗑 پس گرفتن #{p['_id']}", f"dp:c:{p['_id']}")])
    if len(t) == 2:
        t.append("هنوز پیمان یا پیشنهادی نداری.")
    t += ["", "📜 <b>کلمه‌ها</b> (روی پیام بازیکن ریپلای کن یا اسم کشور رو بنویس):",
          "<code>پیمان نام‌کشور 24</code> — عدم‌تجاوز ۱۲/۲۴/۷۲/۱۶۸ ساعته",
          "<code>هدیه نام‌کشور فولاد 100</code> — هدیه (کارمزد ۵٪)",
          "<code>معامله نام‌کشور فولاد 100 غذا 500</code> — می‌دی فولاد، می‌خوای غذا"]
    return "\n".join(t), kb(rows + [BACK])


async def offer_cancel(c, oid):
    o = await db.PACTS.find_one({"_id": oid, "status": "pending", "a": c["_id"]})
    if not o:
        return False, "پیدا نشد"
    if o["kind"] == "trade":
        _put(c, o["give"][0], o["give"][1])
    await db.PACTS.update_one({"_id": oid}, {"$set": {"status": "cancelled"}})
    return True, "🗑 پس گرفته شد"


async def diplo_route(c, p):
    """p = ['dp', act, id]"""
    act = p[1] if len(p) > 1 else ""
    toast = None
    if len(p) > 2 and p[2].lstrip("-").isdigit():
        pid = int(p[2])
        if act in ("y", "n"):
            toast = (await pact_answer(c, pid, act == "y"))[1]
        elif act == "x":
            toast = (await pact_break(c, pid))[1]
        elif act in ("ty", "tn"):
            toast = (await offer_answer(c, pid, act == "ty"))[1]
        elif act == "c":
            toast = (await offer_cancel(c, pid))[1]
    return toast, await s_diplo(c)


async def diplo_loop():
    """پیشنهادهای بی‌جواب رو منقضی می‌کنه (کالای بلوکه برمی‌گرده) و پایان پیمان‌ها رو اعلام می‌کنه."""
    while True:
        await asyncio.sleep(300)
        try:
            async with db.LOCK:
                t = now()
                async for o in db.PACTS.find({"status": "pending", "created": {"$lt": t - config.OFFER_TTL}}):
                    if o["kind"] == "trade":
                        a = await db.load(o["a"])
                        if a:
                            _put(a, o["give"][0], o["give"][1])
                            await db.save(a)
                    await db.PACTS.update_one({"_id": o["_id"]}, {"$set": {"status": "expired"}})
                async for p in db.PACTS.find({"kind": "pact", "status": "active", "end": {"$lte": t}}):
                    await db.PACTS.update_one({"_id": p["_id"]}, {"$set": {"status": "ended"}})
                    for x in (p["a"], p["b"]):
                        await notify(x, "🕊 پیمان عدم‌تجاوز تموم شد؛ دوباره همه‌چی آزاده")
        except Exception:
            logging.exception("diplo_loop")
