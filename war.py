"""سیستم جنگ بزرگ EMPIRE ZERO.

ایده‌ی کلی (سخت ولی ساده):
  ⚡ فرمان نظامی   هر حمله ۱ فرمان می‌خواد؛ فرمان‌ها کم‌کم پر میشن، پس نمیشه بی‌نهایت جنگید.
  🎖 کمپین جهانی    مرحله‌های بی‌پایان؛ دشمن هر مرحله قوی‌تره، حتی با ارتش مکس هم همیشه حریف داری.
  🗡 جنگ بازیکن‌ها  سه جبهه (هوا، دریا، زمین) + ضدیت یگان‌ها + تاکتیک + جاسوسی + انتقام + تسخیر استان.
  🌑 جنگ بزرگ      یه تهدید جهانی با HP مشترک؛ همه با هم می‌زنن و جایزه می‌گیرن.
"""
import asyncio
import copy
import logging
import math
import random
import time

import cine
import config
import crown
import db
import engine as E
import events
import geo
import prog
import reg
import world
from config import U
from core import bot, log_exc, notify, tlog
from util import BACK, OWNER, bar, esc, kb, n

ATK = E.ATK


def now():
    return time.time()


# ------------------------------------------------------------------ نمایش
def fmt_units(d):
    return " ".join(f"{U[k]['e']}{v}" for k, v in d.items() if v) or "—"


def report(r, an, dn):
    st = E.STANCES.get(r.get("stance", "bal"), E.STANCES["bal"])
    s = [f"{'🏆 پیروزی' if r['win'] else '💀 شکست'} — {esc(an)} ⚔️ {esc(dn)}",
         f"{st['e']} تاکتیک: {st['n']} · 🗡 حمله {n(r['A'])} · 🛡 دفاع {n(r['D'])}"]
    for e, nm, a, d, w in r.get("fronts", []):
        s.append(f"{e} جبهه‌ی {nm}: 🗡{n(a)} ⚔️ 🛡{n(d)} {'✅' if w else '❌' if w is False else '➖'}")
    if r.get("air") == "att":
        s.append("✈️ آسمون دست مهاجم بود (+۱۰٪ به دریا و زمین)")
    elif r.get("air") == "def":
        s.append("📡 مدافع آسمون رو کنترل کرد (مهاجم −۸٪)")
    if r["mis"]:
        s.append(f"🚀 {r['mis']} موشک · رهگیری {int(r['icpt'] * 100)}٪ · اصابت {r['hits']}")
    if r["destroyed"]:
        s.append("💥 تخریب: " + "، ".join(r["destroyed"]))
    s.append("☠️ تلفات مهاجم: " + fmt_units(r["la"]) + (f" (🏥 {r['back_a']} برگشتن)" if r.get("back_a") else ""))
    s.append("☠️ تلفات مدافع: " + fmt_units(r["ld"]) + (f" (🏥 {r['back_d']} برگشتن)" if r.get("back_d") else ""))
    if r["loot"]:
        lt = r["loot"]
        s.append(f"💰 غنیمت: {n(lt['t'])} سکه · {n(lt['f'])} غذا · {n(lt['s'])} فولاد")
    return "\n".join(s)


def _raw(r):
    """خروجی engine.battle رو برای مینی‌اپ JSON-پذیر می‌کنه (جبهه‌ها لیست میشن)."""
    keys = ("win", "A", "D", "la", "ld", "loot", "destroyed", "hits", "mis", "icpt", "air", "stance", "ratio", "decisive", "back_a", "back_d")
    out = {k: r.get(k) for k in keys}
    out["fronts"] = [list(f) for f in r.get("fronts", [])]
    return out


def log_battle(c, text):
    c.setdefault("blog", []).append(text[:170])
    c["blog"] = c["blog"][-8:]


def orders_line(c):
    cur, mx = E.orders(c), E.orders_max(c)
    w = E.order_wait(c)
    return f"⚡ فرمان <b>{int(cur)}/{mx}</b>" + (f" (بعدی {prog.dur(w)} دیگه)" if w > 0 else "")


def stance_rows(make):
    """سه ردیف تاکتیک × سه درصد ارتش. make(pct, stance) → callback_data"""
    return [[(f"{st['e']} {p}٪", make(p, sk)) for p in (30, 60, 100)] for sk, st in E.STANCES.items()]


STANCE_LEGEND = "⚔️ متعادل · 🔥 یورش (قدرت +۲۰٪، تلفات +۴۰٪، غنیمت +۲۵٪) · 🛡 محتاطانه (قدرت −۱۰٪، تلفات −۴۰٪)"


def sent_size(c, pct):
    return sum(int(c["units"].get(k, 0) * pct / 100) * U[k]["size"] for k in ATK)


def logi_cost(c, pct):
    return int(sent_size(c, pct) * config.LOGI_COIN)


def has_army(c, pct):
    return sum(int(c["units"].get(k, 0) * pct / 100) for k in ATK) > 0 or int(c["units"].get("missile", 0) * pct / 100) > 0


def check_ready(c, pct, orders=1):
    """(پیام خطا یا None) برای فرمان، ارتش و هزینه‌ی بسیج."""
    if not has_army(c, pct):
        return "🪖 ارتش تهاجمی نداری"
    if E.orders(c) + 1e-9 < orders:
        return f"⚡ فرمان کافی نیست ({orders} لازمه)؛ {prog.dur(E.order_wait(c))} دیگه یکی پر میشه"
    cost = logi_cost(c, pct)
    if c["treasury"] < cost:
        return f"💸 بسیج ارتش {cost:,} سکه هزینه داره"
    return None


# ------------------------------------------------------------------ جاسوسی و مه جنگ
def intel_of(c, tid):
    r = c.get("intel", {}).get(str(tid))
    return r if r and now() - r["ts"] <= config.INTEL_TTL else None


def fog(c, tid, value):
    rnd = random.Random(f"{c['_id']}:{tid}:{int(now() // 900)}")
    return value * rnd.uniform(0.7, 1.3)


def est_sent(c, t, pct, mode="all", support=0.0, ok=None, stance="bal"):
    """(قدرت حمله، دفاع، شانس) برای pct٪ ارتش در حالت mode؛ ok = شاخه‌هایی که به مقصد می‌رسن (نباشه همه)."""
    ok = ok if ok is not None else {"land", "sea", "air"}
    sent = geo.pick_sent(c, pct, mode, ok)
    satk = {k: v for k, v in sent.items() if k != "missile"}
    if not satk:
        return 0.0, E.defense_power(t), 0.0
    return E.estimate(c, t, 0, stance, support, mode, satk)


def best_pct(c, t, support=0.0, mode="all", ok=None):
    """کمترین درصد ارتش که شانس بردش ≥ ۷۵٪ باشه. برمی‌گردونه (درصد، شانس، لیست [(درصد، شانس)])."""
    res = []
    for p in (30, 40, 50, 60, 70, 80, 90, 100):
        pr = est_sent(c, t, p, mode, support, ok)[2]
        res.append((p, pr))
        if pr >= 0.75:
            return p, pr, res
    return 100, res[-1][1], res


def def_view(c, t):
    """(متن دفاع، دقیق؟) — NPCها حریف آموزشی‌ان، پس مه جنگ ندارن."""
    if t.get("npc"):
        return f"{n(E.defense_power(t))}", True
    i = intel_of(c, t["_id"])
    if i:
        return f"{n(i['dfn'])}", True
    return f"~{n(fog(c, t['_id'], E.defense_power(t)))} (±۳۰٪)", False


async def ally_support(t):
    if not t.get("alliance"):
        return 0.0
    a = await db.A.find_one({"_id": t["alliance"]})
    if not a:
        return 0.0
    tot = 0.0
    for uid in a["members"][:config.ALLY_MAX]:
        if uid != t["_id"]:
            m = await db.C.find_one({"_id": uid})
            if m:
                E.defaults(m)
                tot += E.defense_power(m)
    return tot * 0.1


async def do_spy(c, tid, op):
    t = await db.load(tid)
    if not t:
        return "هدف پیدا نشد"
    if op != "scout" and not t.get("npc") and await world.has_pact(c["_id"], tid):
        return "🕊 با این کشور پیمان عدم‌تجاوز داری؛ خرابکاری و سرقت ممنوعه"
    ok, txt, caught = E.spy(c, t, op)
    if ok and op != "scout":
        await db.save(t)
        await notify(tid, "🚨 کشورت هدف خرابکاری/سرقت اطلاعاتی قرار گرفت!")
    if caught:
        await notify(tid, f"🕵️ عوامل کشور «{esc(c['name'])}» در خاکت دستگیر شدند!")
    return txt


# ------------------------------------------------------------------ کمپین جهانی
THEMES = [("پیاده‌نظام انبوه", {"inf": 1.0}), ("لشکر زرهی", {"inf": .4, "tank": .6}),
          ("ناوگان دریایی", {"inf": .3, "ship": .4, "sub": .3}), ("نیروی هوایی", {"inf": .3, "jet": .4, "ad": .3}),
          ("ارتش ترکیبی", {"inf": .35, "tank": .25, "jet": .15, "ship": .1, "ad": .15})]


def camp_target(stage):
    boss = stage % config.CAMP_BOSS_EVERY == 0
    return (config.CAMP_BASE_DEF * config.CAMP_GROWTH ** (min(stage, 30) - 1)
            * config.CAMP_GROWTH2 ** max(0, stage - 30) * (1.35 if boss else 1.0))


def camp_enemy(stage):
    """دشمن این مرحله (برای همه یکسانه چون با seed ثابت ساخته میشه)."""
    r = random.Random(stage * 7919)
    boss = stage % config.CAMP_BOSS_EVERY == 0
    theme = THEMES[0] if stage <= 2 else r.choice(THEMES[:3] if stage < 6 else THEMES)
    target = camp_target(stage)
    e = E.new_country(-1000 - stage, ("فرمانده‌ی " if boss else "") + f"{r.choice(reg._NA)} {r.choice(reg._NB)}", "NPC")
    e["npc"], e["camp"], e["tag"] = True, True, theme[0]
    e["treasury"], e["food"], e["steel"], e["shield_until"], e["sat"] = 0.0, 0.0, 0.0, 0.0, 55.0
    e["techlv"]["def"], e["techlv"]["mil"] = min(10, stage // 6), min(10, stage // 8)
    e["upg"] = {b: min(10, stage // 8) for b in ("land", "air", "sea")}
    e["buildings"]["police"] = stage // 8
    units = {k: 0 for k in U}
    for k, w in theme[1].items():
        units[k] = max(1, int(target * w / (U[k]["dfn"] * E.brm(e, k))))
    e["units"] = units
    cur = E.defense_power(e)
    f = target / cur if cur > 0 else 1.0
    for k in units:
        if units[k]:
            units[k] = max(1, int(units[k] * f))
    return e


def camp_reward(stage):
    boss = stage % config.CAMP_BOSS_EVERY == 0
    coins = int(config.CAMP_COIN0 * config.CAMP_COIN_GROWTH ** (min(stage, 45) - 1) * (2.5 if boss else 1) * events.mult("loot"))
    return dict(coins=coins, steel=3 * stage + (20 if boss else 0), zero=(1 + stage // 10) if boss else 0,
                pts=10 + stage * (2 if boss else 1), boss=boss)


def difficulty(p):
    return "🟢 آسون" if p >= 0.8 else "🟡 برابر" if p >= 0.45 else "🟠 سخت" if p >= 0.15 else "🔴 خیلی سخت"


def s_camp(c):
    stage = c["camp"]["stage"]
    e = camp_enemy(stage)
    rw = camp_reward(stage)
    A, D, p = E.estimate(c, e, 1.0, "bal")
    t = [f"🎖 <b>کمپین جهانی — مرحله‌ی {stage}</b>" + (" 👑 <b>نبرد فرمانده</b>" if rw["boss"] else ""),
         f"🌍 دشمن: <b>{esc(e['name'])}</b> · {e['tag']}", f"🛡 قدرت دفاع: <b>{n(D)}</b> · {fmt_units(e['units'])}",
         f"🗡 قدرت تو (با ۱۰۰٪ ارتش): <b>{n(A)}</b> · 🎲 شانس ~{int(p * 100)}٪ {difficulty(p)}",
         "🎁 جایزه: " + prog.rew_text(rw) + f" · 🏆 {rw['pts']} امتیاز جنگ" + (" · 🏞 +۱ استان" if rw["boss"] else ""),
         orders_line(c) + f" · 🪖 بسیج ۶۰٪ ≈ {n(logi_cost(c, 60))}💰",
         f"🏅 رکورد تو: مرحله‌ی {c['camp'].get('best', 0)} · بردها {c['camp'].get('wins', 0)}", "", STANCE_LEGEND]
    return "\n".join(t), kb(stance_rows(lambda p, s: f"w:cg:{p}:{s}") + [[("🔄", "w:camp"), ("⚔️ جنگ", "w")], BACK])


def do_camp(c, pct, stance):
    pct = max(10, min(100, pct))
    stance = stance if stance in E.STANCES else "bal"
    err = check_ready(c, pct)
    if err:
        return err
    stage = c["camp"]["stage"]
    e = camp_enemy(stage)
    E.spend_orders(c, 1)
    c["treasury"] -= logi_cost(c, pct)
    sent = {k: int(c["units"].get(k, 0) * pct / 100) for k in ATK}
    r = E.battle(c, e, pct / 100, 0.0, stance, 0.0)
    if not r:
        return "🪖 ارتش تهاجمی نداری"
    prog.bump(c, "camp")
    an = crown.tag(c["_id"]) + c["name"]
    cine.stash(c["_id"], cine.battle_frames(r, an, e["name"]))
    txt = report(r, an, e["name"])
    if r["win"]:
        rw = camp_reward(stage)
        prog.give(c, rw)
        prog.add(c, "war", rw["pts"])
        prog.bump(c, "win")
        c["camp"]["stage"] = stage + 1
        c["camp"]["wins"] = c["camp"].get("wins", 0) + 1
        c["camp"]["best"] = max(c["camp"].get("best", 0), stage)
        extra = f"\n\n🎖 <b>مرحله‌ی {stage} فتح شد!</b> جایزه: {prog.rew_text(rw)} · 🏆 {rw['pts']} امتیاز"
        if rw["boss"]:
            if c["land"] < config.LAND_MAX:
                c["land"] += 1
                extra += "\n🏞 یه استان جدید به قلمروت اضافه شد!"
            world.news(f"🎖 <b>{esc(c['name'])}</b> فرمانده‌ی مرحله‌ی {stage} کمپین رو شکست داد!", important=stage >= 10)
        log_battle(c, f"🎖 کمپین {stage}: پیروزی ({prog.rew_text(rw)})")
        extra += f"\n➡️ مرحله‌ی بعد: {stage + 1}"
    else:
        extra = f"\n\n💀 مرحله‌ی {stage} رو نتونستی بگیری؛ ارتش رو تقویت کن یا تاکتیک رو عوض کن."
        log_battle(c, f"🎖 کمپین {stage}: شکست")
    cine.record(c["_id"], dict(kind="camp", an=c["name"], dn=e["name"], ae=c.get("emblem", "🏛"), de="👑" if stage % config.CAMP_BOSS_EVERY == 0 else "🌍",
                               sent=sent, extra=extra, stage=stage, pct=pct, **_raw(r)))
    return txt + extra


# ------------------------------------------------------------------ جنگ بزرگ (تهدید جهانی)
BOSS = {}
BOSS_NAMES = ["لژیون تاریکی", "ابرقدرت زره‌پوش", "ناوگان شبح", "هیولای آتشین", "اژدهای خاکستری", "امپراتوری سایه"]


async def boss_load():
    d = await db.META.find_one({"_id": "boss"}) or {}
    BOSS.clear()
    BOSS.update(d)


async def boss_save():
    await db.META.replace_one({"_id": "boss"}, {"_id": "boss", **{k: v for k, v in BOSS.items() if k != "_id"}}, upsert=True)


def boss_active():
    return bool(BOSS.get("active")) and BOSS.get("end", 0) > now() and BOSS.get("hp", 0) > 0


async def boss_start(hours=24, hp=None, by=0):
    if boss_active():
        return False, "یه جنگ بزرگ همین الان فعاله"
    if hp is None:
        docs = await db.C.find({"npc": {"$ne": True}, "last_tick": {"$gt": now() - 7 * 86400}}).to_list(5000)
        tot = 0.0
        for d in docs:
            E.defaults(d)
            tot += E.attack_power(d)
        hp = max(config.BOSS_HP_MIN, tot * config.BOSS_HP_FACTOR)
    hp = float(hp)
    BOSS.clear()
    BOSS.update({"active": True, "name": random.choice(BOSS_NAMES), "hp_max": hp, "hp": hp, "start": now(),
                 "end": now() + hours * 3600, "dmg": {}, "hits": {}, "atk": hp * 0.02, "by": by})
    await boss_save()
    events.start("war", hours, by)
    await events.save()
    msg = (f"🌑 <b>جنگ بزرگ شروع شد!</b>\n«{BOSS['name']}» به جهان حمله کرده!\n"
           f"❤️ HP مشترک: {n(hp)} · ⏳ {hours:g} ساعت فرصت داریم.\n"
           "همه با هم بزنیم 💥 جایزه‌ی هر نفر + جایزه‌ی ویژه برای ۳ نفر اول!\nبنویس «جنگ بزرگ» یا از منوی جنگ وارد شو.")
    world.news(f"🌑 جنگ بزرگ شروع شد: «{BOSS['name']}» با {n(hp)} HP به جهان حمله کرد!", important=True)
    tlog("🌑", "جنگ بزرگ شروع شد", f"{BOSS['name']} · HP {n(hp)} · {hours:g}h")
    await world.broadcast_players(msg)
    return True, f"🌑 جنگ بزرگ شروع شد (HP {n(hp)})"


async def boss_finish(killed, cur=None):
    """پایان جنگ بزرگ: جایزه برای همه‌ی شرکت‌کننده‌ها. cur = کشوری که الان توی حافظه دست کالره (دوباره لود/ذخیره‌ش نکن)."""
    if not BOSS.get("active"):
        return
    BOSS["active"] = False
    dmg = {int(k): v for k, v in BOSS.get("dmg", {}).items()}
    ranked = sorted(dmg.items(), key=lambda x: -x[1])
    tot = sum(dmg.values()) or 1.0
    k = 1.0 if killed else 0.5
    msgs, top_lines = [], []
    for i, (uid, dm) in enumerate(ranked):
        d = cur if cur is not None and cur["_id"] == uid else await db.load(uid)
        if not d:
            continue
        coins = int((config.BOSS_COINS * 0.5 + config.BOSS_COINS * 4 * dm / tot) * k)
        zero = (config.BOSS_PART_ZERO if killed else 0) + (config.BOSS_ZERO[i] if i < len(config.BOSS_ZERO) else 0)
        prog.give(d, dict(coins=coins, zero=zero))
        if d is not cur:
            await db.save(d)
        if i < 3:
            top_lines.append(f"{['🥇', '🥈', '🥉'][i]} {esc(d['name'])} — {n(dm)}")
        msgs.append((uid, f"{'🏆 جنگ بزرگ برده شد!' if killed else '⌛ جنگ بزرگ تموم شد (دشمن نابود نشد)'}\n"
                          f"📍 رتبه‌ی تو: {i + 1} · 💥 {n(dm)} آسیب\n🎁 جایزه: {coins:,}💰 {zero}⚡"))
    BOSS["killed"] = bool(killed)
    await boss_save()
    events.stop("war")
    await events.save()
    title = f"🌑 جنگ بزرگ {'پیروز شد' if killed else 'تموم شد'}: «{BOSS.get('name')}»"
    world.news(title + (" · " + top_lines[0] if top_lines else ""), important=True)
    tlog("🌑", title, "\n".join(top_lines))

    async def run():
        for uid, m in msgs:
            await notify(uid, m)
            await asyncio.sleep(0.05)
    asyncio.create_task(run())


async def boss_loop():
    while True:
        await asyncio.sleep(30)
        try:
            if BOSS.get("active") and (BOSS["end"] <= now() or BOSS["hp"] <= 0):
                async with db.LOCK:
                    await boss_finish(BOSS["hp"] <= 0)
        except Exception:
            logging.exception("boss_loop")
            log_exc("حلقه‌ی جنگ بزرگ")


async def s_boss(c):
    if not BOSS.get("name"):
        return "🌑 هنوز جنگ بزرگی در کار نبوده؛ وقتی ادمین شروعش کنه همه خبردار میشن.", kb([[("⚔️ جنگ", "w")], BACK])
    act = boss_active()
    hp, mx = max(0.0, BOSS["hp"]), BOSS["hp_max"]
    dmg = {int(k): v for k, v in BOSS.get("dmg", {}).items()}
    ranked = sorted(dmg.items(), key=lambda x: -x[1])
    mine = dmg.get(c["_id"], 0.0)
    rank = next((i + 1 for i, (u, _) in enumerate(ranked) if u == c["_id"]), None)
    names = {d["_id"]: d["name"] async for d in db.C.find({"_id": {"$in": [u for u, _ in ranked[:5]]}}, {"name": 1})}
    t = [f"🌑 <b>{BOSS['name']}</b> — تهدید جهانی" + ("" if act else (" · ✅ نابود شد" if BOSS.get("killed") else " · ⌛ تموم شد")),
         f"❤️ {bar(hp / mx * 100, 10)} {n(hp)}/{n(mx)}"]
    if act:
        t.append(f"⏳ {prog.dur(BOSS['end'] - now())} مانده")
        A = E.attack_power(c, {k: int(c['units'].get(k, 0)) for k in ATK})
        t.append(f"🗡 ضربه‌ی تو با ۱۰۰٪ ارتش ≈ {n(A)} ({A / mx * 100:.1f}٪ HP)")
        t.append(orders_line(c) + f" · 🪖 بسیج ۶۰٪ ≈ {n(logi_cost(c, 60))}💰")
    t.append(f"💥 آسیب تو: {n(mine)}" + (f" · رتبه {rank}" if rank else ""))
    if ranked:
        t.append("\n🏆 <b>برترین‌ها</b>")
        t += [f"{i + 1}. {esc(names.get(u, '؟'))} — {n(d)}" for i, (u, d) in enumerate(ranked[:5])]
    t.append(f"\n🎁 جایزه: سکه بر اساس سهم آسیب + {config.BOSS_ZERO[0]}/{config.BOSS_ZERO[1]}/{config.BOSS_ZERO[2]}⚡ برای ۳ نفر اول")
    t.append("⚠️ دشمن تلافی می‌کنه؛ هرچی دفاعت قوی‌تر، تلفاتت کمتر.")
    rows = [[(f"💥 {p}٪", f"w:bh:{p}") for p in (30, 60, 100)]] if act else []
    return "\n".join(t), kb(rows + [[("🔄", "w:boss"), ("⚔️ جنگ", "w")], BACK])


async def boss_hit(c, pct):
    if not boss_active():
        return "🌑 الان تهدید جهانی فعالی نیست"
    pct = max(10, min(100, pct))
    err = check_ready(c, pct)
    if err:
        return err
    sent = {k: int(c["units"].get(k, 0) * pct / 100) for k in ATK}
    dmg = E.attack_power(c, sent) * random.uniform(0.9, 1.1)
    if dmg <= 0:
        return "🪖 ارتش تهاجمی نداری"
    E.spend_orders(c, 1)
    c["treasury"] -= logi_cost(c, pct)
    risk = max(0.03, min(0.18, 0.06 * BOSS["atk"] / (E.defense_power(c) + 1)))
    lost = {}
    for k in ATK:
        lo = int(sent[k] * risk)
        c["units"][k] -= lo
        lost[k] = lo
    c["weariness"] = min(40.0, c["weariness"] + 3)
    BOSS["hp"] -= dmg
    u = str(c["_id"])
    BOSS["dmg"][u] = BOSS["dmg"].get(u, 0.0) + dmg
    BOSS["hits"][u] = BOSS["hits"].get(u, 0) + 1
    pts = max(5.0, dmg / BOSS["hp_max"] * 500)
    prog.add(c, "war", pts)
    prog.bump(c, "boss")
    txt = (f"💥 ضربه‌ی تو {n(dmg)} آسیب زد! ({dmg / BOSS['hp_max'] * 100:.1f}٪ HP)\n"
           f"☠️ تلافی دشمن: {fmt_units(lost)} · 🏆 +{pts:.0f} امتیاز جنگ\n❤️ HP مانده: {n(max(0, BOSS['hp']))}")
    log_battle(c, f"🌑 ضربه به {BOSS['name']}: {n(dmg)} آسیب")
    cine.stash(c["_id"], cine.boss_frames(BOSS["name"], dmg, dmg / BOSS["hp_max"] * 100))
    cine.record(c["_id"], dict(kind="boss", an=c["name"], dn=BOSS["name"], ae=c.get("emblem", "🏛"), de="🌑", sent=sent, dmg=dmg, lost=lost, pct=pct,
                               hp=max(0.0, BOSS["hp"]), hp_max=BOSS["hp_max"], killed=BOSS["hp"] <= 0, extra=""))
    if BOSS["hp"] <= 0:
        txt += "\n\n🎉 <b>تهدید نابود شد!</b> جایزه‌ها در حال ارسال..."
        await boss_finish(True, cur=c)
    else:
        await boss_save()
    return txt


# ------------------------------------------------------------------ 🧭 لشکرکشی (حمله به NPC و بازیکن)
# حمله دیگه آنی نیست: لشکر راه میفته، به‌اندازه‌ی فاصله و مقدار و نوع ارتش زمان و هزینه‌ی حمل‌ونقل داره،
# وسط راه از دفاع خودت کم میشه، و موقع رسیدن نبرد اجرا میشه (loop هر ۱۵ ثانیه). هر نبرد روی «کپی» سند اجرا میشه
# و فقط اگه کامل تموم شد اعمال میشه → هیچ حالت نصفه‌ای (مثلاً استان از قربانی کم و به مهاجم اضافه نشده) نمی‌مونه.
def _mode(mode):
    return config.norm_mode(mode)


def mode_tag(mode):
    return config.mode_title(mode)


def march_cap(c):
    return config.MARCH_MAX + E.lv(c, "palace") // 2


def launch_cost(plan):
    return int(plan["size"] * config.LOGI_COIN) + plan["transport"]


async def locate(c, tid):
    """(فاصله به خونه، هم‌قاره؟، همسایه؟) یا None اگه جای کشور روی نقشه معلوم نیست."""
    await geo.refresh(need=c["_id"])
    if tid not in geo.CACHE["pos"]:
        await geo.refresh(force=True)
    d = geo.dist(c["_id"], tid)
    if d is None:
        return None
    return d, geo.same_continent(c["_id"], tid), geo.is_neighbor(c["_id"], tid)


def check_launch(c, plan, orders):
    if len(c.get("marches", [])) >= march_cap(c):
        return f"🧭 همین الان {len(c['marches'])} لشکر در راهه (سقف {march_cap(c)}؛ با ارتقای کاخ بیشتر میشه)"
    if E.orders(c) + 1e-9 < orders:
        return f"⚡ فرمان کافی نیست ({orders} لازمه)؛ {prog.dur(E.order_wait(c))} دیگه یکی پر میشه"
    cost = launch_cost(plan)
    if c["treasury"] < cost:
        return f"💸 این لشکرکشی {cost:,} سکه هزینه داره (بسیج {int(plan['size'] * config.LOGI_COIN):,} + حمل‌ونقل {plan['transport']:,})"
    return None


async def do_attack(c, tid, pct, stance="bal", conquest=False, mode="all"):
    """شروع لشکرکشی؛ نتیجه‌ی نبرد وقتی لشکر برسه برات میاد. برمی‌گردونه متن (خطا یا گزارش حرکت)."""
    t = await db.load(tid)
    if not t or t["_id"] == c["_id"]:
        return "هدف پیدا نشد"
    npc = bool(t.get("npc"))
    pct = max(10, min(100, int(pct)))
    stance = stance if stance in E.STANCES else "bal"
    mode = _mode(mode)
    t0 = now()
    loc = await locate(c, tid)
    if not loc:
        return "🗺 جای این کشور روی نقشه پیدا نشد؛ چند لحظه‌ی دیگه دوباره امتحان کن"
    d, same, neigh = loc
    revenge = (not npc) and c["revenge"].get(str(tid), 0) > t0
    liberate = bool(conquest) and c.get("lost_to", {}).get(str(tid), 0) > 0      # قبلاً ازش استان از دست دادی → آزادسازی
    if conquest:
        if "land" not in config.mode_branches(mode):
            return "🏴 تسخیر نیروی زمینی می‌خواد؛ نوع حمله باید «زمینی» رو شامل بشه"
        if not neigh:
            return (f"🏴 تسخیر فقط روی کشورهای <b>همسایه</b> ممکنه؛ «{esc(t['name'])}» {d:.0f} خونه دوره.\n"
                    "لیست همسایه‌هات: «همسایه‌ها» — حمله‌ی معمولی به کشورهای دور آزاده (با هزینه و زمان بیشتر).")
        if c.get("land", config.LAND_START) >= E.land_cap(c):
            return "🏞 " + E.land_cap_msg(c)
        if t.get("land", 0) <= config.LAND_MIN:
            return ("🏞 این NPC دیگه استان اضافه نداره؛ چند ساعت صبر کن تا بازسازی بشه" if npc
                    else "🏞 این کشور به حداقل استانش رسیده و استانی برای تسخیر نداره")
    if npc:
        left = config.NPC_CD - (t0 - c["npc_cd"].get(str(tid), 0))
        if left > 0:
            return f"⏳ ارتش این کشور هنوز بازسازی نشده؛ {int(left // 60) + 1} دقیقه‌ی دیگه"
    else:
        if t["shield_until"] > t0:
            return "🛡 این کشور سپر داره"
        if c.get("alliance") and t.get("alliance") == c["alliance"]:
            return "🤝 هم‌پیمانته"
        if await world.has_pact(c["_id"], tid):
            return "🕊 با این کشور پیمان عدم‌تجاوز داری"
        left = config.PVP_CD - (t0 - c["pvp_cd"].get(str(tid), 0))
        if left > 0 and not revenge:
            return f"⏳ تازه بهش حمله کردی؛ {prog.dur(left)} دیگه می‌تونی دوباره بزنی"
        if E.score(t) < config.BULLY_RATIO * E.score(c) and not revenge:
            return "🙅 این کشور خیلی ضعیف‌تر از توئه (کمتر از ۲۰٪ قدرتت)؛ حریف هم‌وزن پیدا کن"
        if conquest and not (revenge or liberate):
            if E.score(t) < config.CONQUEST_MIN_RATIO * E.score(c):
                return f"🙅 تسخیر فقط روی حریفی با حداقل {int(config.CONQUEST_MIN_RATIO * 100)}٪ قدرت خودته (جلوی لخت‌کردن ضعیف‌ترها)؛ حمله‌ی معمولی آزاده"
            if t.get("cq_prot", 0) > t0:
                return f"🛡 این کشور تازه استان از دست داده؛ {prog.dur(t['cq_prot'] - t0)} دیگه از تسخیر در امانه (حمله‌ی معمولی آزاده)"
            cl = config.CONQUEST_CD_H * 3600 - (t0 - c.get("cq_cd", {}).get(str(tid), 0))
            if cl > 0:
                return f"⏳ تازه روش تسخیر زدی؛ {prog.dur(cl)} دیگه می‌تونی دوباره تسخیر کنی"
    plan, err = geo.plan(c, pct, mode, d, same)
    if err:
        return err
    if conquest and not any(U[k]["br"] == "land" for k in plan["sent"]):
        return "🏴 تسخیر نیروی زمینی می‌خواد؛ یگان زمینی (🪖🥷🚜…) نداری یا همه‌شون اعزام نمیشن"
    need = 0 if (revenge and not conquest) else (2 if conquest else 1)
    err = check_launch(c, plan, need)
    if err:
        return err
    if npc:                                   # جلوی خودکشی‌ی بی‌خبر رو می‌گیریم (هیچ فرمان و سکه‌ای خرج نمیشه)
        satk = {k: v for k, v in plan["sent"].items() if k != "missile"}
        pr = E.estimate(c, t, 0, stance, 0.0, mode, satk)[2]
        if pr < 0.08:
            bp, bpr, _ = best_pct(c, t, 0.0, mode)
            my, df = E.attack_power(c), E.defense_power(t)
            if bpr >= 0.15 and bp > pct:
                return (f"⚠️ با {pct}٪ ارتش شانس بردت فقط حدود {int(pr * 100)}٪ هست (حمله {n(my * pct / 100)} در برابر دفاع {n(df)}).\n"
                        f"با {bp}٪ شانست حدود {int(bpr * 100)}٪ میشه؛ از دکمه‌ی 🎯 حمله‌ی هوشمند استفاده کن.")
            return (f"⚠️ فعلاً ارتشت برای «{esc(t['name'])}» کمه (حمله‌ی کامل تو {n(my)} در برابر دفاع {n(df)}).\n"
                    "ارتش/ارتقا رو قوی‌تر کن یا یه NPC ضعیف‌تر (⭐ کمتر) رو بزن.")
    # ---- همه‌ی بررسی‌ها گذشت؛ لشکر راه میفته
    if need:
        E.spend_orders(c, need)
    cost = launch_cost(plan)
    c["treasury"] -= cost
    for k, v in plan["sent"].items():
        c["units"][k] = c["units"].get(k, 0) - v
    secs = plan["secs"] if config.BUILD_TIME_MULT > 0 else 0
    m = dict(id=E._jid(c), tid=tid, name=t["name"], npc=npc, mode=mode, sent=plan["sent"], stance=stance, conquest=bool(conquest),
             revenge=revenge, liberate=liberate, pct=pct, depart=t0, arrive=t0 + max(secs, 1), dist=round(d, 1), cost=cost, fails=0)
    c.setdefault("marches", []).append(m)
    prog.bump(c, "attack")
    if npc:
        c["npc_cd"][str(tid)] = t0
    else:
        c["shield_until"] = 0.0
        c["pvp_cd"][str(tid)] = t0
        if revenge:
            c["revenge"].pop(str(tid), None)
        if conquest:
            c.setdefault("cq_cd", {})[str(tid)] = t0
        tok = OWNER.set(tid)
        try:
            mk = kb([[("🧭 وضع من", "w")]])
        finally:
            OWNER.reset(tok)
        await notify(tid, f"🚨 <b>هشدار لشکرکشی!</b>\nارتش {crown.tag(c['_id'])}<b>{esc(c['name'])}</b> ({mode_tag(mode)}) به‌سمت کشورت راه افتاده؛ "
                          f"{prog.dur(secs)} دیگه می‌رسه." + ("\\n🏴 هدفشون تسخیر استانه!" if conquest else "")
                     + "\\n💡 تا اون موقع ارتشت رو قوی کن یا هم‌پیمان‌هات رو خبر کن.", mk)
    drop = ""
    if plan["dropped"]:
        drop = "\\n⚠️ شاخه‌ی بی‌برد/نامناسب اعزام نشد: " + "، ".join({"land": "زمینی", "sea": "دریایی", "air": "هوایی"}[b] for b in plan["dropped"])
    return (f"🧭 <b>لشکرکشی به {esc(t['name'])} شروع شد</b> ({mode_tag(mode)}{' · 🏴 تسخیر' if conquest else ''})\n"
            f"📍 {d:.0f} خونه · ⏱ {prog.dur(secs)} تا رسیدن\n"
            f"🪖 اعزامی: {fmt_units(plan['sent'])}\n"
            f"💰 هزینه: بسیج {int(plan['size'] * config.LOGI_COIN):,} + حمل‌ونقل {plan['transport']:,} = <b>{cost:,}</b>" + drop +
            "\n🏠 تا رسیدن لشکر، این یگان‌ها از دفاع خودت کم شدن · «لشکرها» برای دیدن و فراخوانی")


async def resolve_march(c0, m):
    """رسیدن یه لشکر. روی کپی کار می‌کنه و فقط با موفقیت کامل روی c0 و هدف اعمال میشه. dict نتیجه برمی‌گردونه."""
    tid, npc = m["tid"], bool(m.get("npc"))
    t = await db.load(tid)
    uid = c0["_id"]
    if not t:
        for k, v in m["sent"].items():
            c0["units"][k] = c0["units"].get(k, 0) + v
        return dict(uid=uid, txt=f"↩️ لشکرت به «{esc(m.get('name', '?'))}» رسید ولی اون کشور دیگه وجود نداره؛ نیروها برگشتن", frames=None)
    c = copy.deepcopy(c0)
    for k, v in m["sent"].items():
        c["units"][k] = c["units"].get(k, 0) + v
    mode, stance = _mode(m.get("mode")), m.get("stance", "bal")
    revenge, conquest = bool(m.get("revenge")), bool(m.get("conquest"))
    note = ""
    if conquest and (t.get("land", 0) <= config.LAND_MIN or c.get("land", config.LAND_START) >= E.land_cap(c)):
        conquest, note = False, "\n🏞 تا رسیدن لشکر شرایط تسخیر از بین رفت؛ فقط حمله‌ی معمولی شد"
    liberate = conquest and c.get("lost_to", {}).get(str(tid), 0) > 0
    rel = 1.0 if npc else max(0.3, min(1.6, math.sqrt(E.score(t) / max(1, E.score(c)))))
    support = 0.0 if npc else await ally_support(t)
    r = E.battle(c, t, 0.0, support, stance, rel * (1.25 if revenge else 1.0), sent=dict(m["sent"]), mode=mode,
                 conquest_ratio=config.CONQUEST_LIBERATE if liberate else None)
    if not r:
        for k, v in m["sent"].items():
            c0["units"][k] = c0["units"].get(k, 0) + v
        return dict(uid=uid, txt="🪖 لشکرت رسید ولی نیروی تهاجمی‌ای توش نبود؛ برگشتن", frames=None)
    extra, crown_def = note, ""
    if r["win"]:
        prog.bump(c, "win")

    def take_province(who_name):
        nonlocal extra
        t["land"] -= 1
        c["land"] += 1
        if not npc:
            t["cq_prot"] = t0 + config.CONQUEST_PROTECT_H * 3600
            lt = t.setdefault("lost_to", {})
            lt[str(c["_id"])] = lt.get(str(c["_id"]), 0) + 1
            mine = c.setdefault("lost_to", {})
            if mine.get(str(tid), 0) > 0:                      # 🕊 استانِ از دست رفته رو پس گرفتی
                mine[str(tid)] -= 1
                if mine[str(tid)] <= 0:
                    mine.pop(str(tid), None)
                extra += "\n🕊 <b>آزادسازی!</b> استانِ از دست‌رفته‌ات رو پس گرفتی"
        extra += f"\n🏴 <b>یه استان از {esc(t['name'])} تسخیر شد!</b> قلمروت {c['land']} استان شد (طرف مقابل: {t['land']})"
        world.news(f"🏴 <b>{esc(c['name'])}</b> یه استان از <b>{esc(t['name'])}</b> تسخیر کرد!", important=True)

    def conquest_note():
        nonlocal extra
        if not conquest:
            return
        if not r["win"]:
            extra += "\n🏴 شکست خوردی؛ استانی تسخیر نشد"
        else:
            need_r = config.CONQUEST_LIBERATE if liberate else config.CONQUEST_RATIO
            extra += f"\n🏴 پیروزی قاطع نبود (نسبت {r['ratio']:.2f}؛ باید ≥ {need_r}) پس استانی تسخیر نشد"

    t0 = now()
    if npc:
        if r["win"]:
            bounty = int(t["bounty"] * events.mult("loot"))
            c["treasury"] += bounty
            c["st"]["npc_wins"] = c["st"].get("npc_wins", 0) + 1
            pts = 4 * t["tier"]
            prog.add(c, "war", pts)
            extra += f"\n🎖 غرامت جنگی: {n(bounty)} سکه · 🏆 {pts} امتیاز جنگ"
            if random.random() < 0.10 * t["tier"]:
                c["fx"]["PHX"] = c["fx"].get("PHX", 0) + 1
                extra += " · +1 ⚡زیرو"
            if conquest and r["decisive"]:
                take_province(t["name"])
            else:
                conquest_note()
        else:
            conquest_note()
        log_battle(c, f"🌍 {t['name']}: {'پیروزی' if r['win'] else 'شکست'}")
    else:
        sc_t, sc_c = E.score(t), max(1, E.score(c))
        if r["win"]:
            pts = int(20 * rel * (1.5 if sc_t >= 1.3 * sc_c else 1.0))
            prog.add(c, "war", pts)
            extra += f"\n🏆 +{pts} امتیاز جنگ" + (" · 💢 انتقام گرفتی!" if revenge else "")
            if conquest and r["decisive"]:
                take_province(t["name"])
            else:
                conquest_note()
            import social                                  # (import تنبل؛ social خودش commands رو import می‌کنه)
            got, btxt = social.claim_bounty(c, t)          # 🎯 سرجایزه
            if got:
                extra += btxt
                world.news(f"🎯 <b>{esc(c['name'])}</b> سرجایزه‌ی <b>{esc(t['name'])}</b> ({n(got)}💰) رو گرفت!")
            if sc_t >= 1.5 * sc_c:
                world.news(f"⚔️ <b>{esc(c['name'])}</b> کشور قوی‌تر <b>{esc(t['name'])}</b> رو شکست داد!")
            if crown.is_holder(t["_id"]):                   # 👑 امپراتور رو شکست دادی
                ex_a, crown_def = crown.seize(c, t)
                extra += ex_a
        else:
            conquest_note()
            prog.add(t, "war", 8)
        t["revenge"][str(c["_id"])] = t0 + config.REVENGE_H * 3600
        log_battle(c, f"⚔️ حمله به {t['name']}: {'پیروزی' if r['win'] else 'شکست'}")
        log_battle(t, f"🛡 {c['name']} حمله کرد: {'شکست خوردی' if r['win'] else 'دفاع موفق'}")
        tlog("⚔️", "حمله‌ی بازیکن", f"{esc(c['name'])} → {esc(t['name'])} · {'🏆 پیروزی' if r['win'] else '💀 شکست'}"
             + (" · 🏴 تسخیر" if conquest else "") + f" · {mode_tag(mode)} · {m.get('dist', 0):.0f} خونه")
    an, dn = crown.tag(c["_id"]) + c["name"], crown.tag(t["_id"]) + t["name"]
    head = f"🧭 <b>لشکر {mode_tag(mode)} به {esc(t['name'])} رسید</b>\n"
    txt = head + report(r, an, dn) + extra
    # ---- موفق: اعمال روی سند اصلی و ذخیره‌ی هدف
    c0.clear()
    c0.update(c)
    await db.save(t)
    res = dict(uid=uid, txt=txt, frames=cine.battle_frames(r, an, dn), target=None)
    if not npc:
        tok = OWNER.set(tid)
        try:
            mk = kb([[("💢 انتقام", f"w:pick:{uid}")]])
        finally:
            OWNER.reset(tok)
        res["target"] = (tid, "🚨 <b>به کشورت حمله شد!</b>\n" + report(r, an, dn)
                         + f"\n\n💢 {config.REVENGE_H} ساعت فرصت داری انتقام بگیری (فرمان نمی‌خواد و غنیمت ۲۵٪ بیشتره)" + crown_def
                         + ("\n🕊 اگه همین حالا ضدحمله‌ی قاطع بزنی «آزادسازی» حساب میشه (شرط قاطع‌بودن آسون‌تره)" if conquest and r["win"] and r["decisive"] else ""), mk)
    return res


async def deliver(res):
    """گزارش نبرد برای مهاجم (با انیمیشن) و هشدار برای مدافع؛ بیرون از قفل."""
    uid = res["uid"]
    tok = OWNER.set(uid)
    try:
        mk = kb([[("🎯 هدف دیگه", "w:t")], [("⚔️ جنگ", "w")], BACK])
    finally:
        OWNER.reset(tok)
    try:
        fr = res.get("frames")
        if fr:
            msg = await bot.send_message(uid, fr[0])
            await cine.play(msg, fr[1:], res["txt"], mk)
        else:
            await notify(uid, res["txt"], mk)
    except Exception:
        log_exc("march deliver")
        await notify(uid, res["txt"], mk)
    if res.get("target"):
        await notify(*res["target"])


async def march_tick():
    """لشکرهایی که رسیدن رو اجرا می‌کنه. هر نبرد زیر قفلِ همون کشور؛ تحویل گزارش بیرون از قفل."""
    t0 = now()
    due = [d["_id"] async for d in db.C.find({"marches.arrive": {"$lte": t0}}, {"_id": 1})]
    out = []
    for uid in due:
        async with db.LOCK:
            c = await db.load(uid)
            if not c:
                continue
            for m in [x for x in c.get("marches", []) if x["arrive"] <= t0]:
                try:
                    res = await resolve_march(c, m)
                    c["marches"] = [x for x in c["marches"] if x["id"] != m["id"]]
                    out.append(res)
                except Exception:
                    log_exc(f"march {m.get('id')}")
                    m["fails"] = m.get("fails", 0) + 1
                    if m["fails"] >= 3:                  # خرابیِ مداوم → لشکر برمی‌گرده تا چیزی گیر نکنه
                        for k, v in m["sent"].items():
                            c["units"][k] = c["units"].get(k, 0) + v
                        c["marches"] = [x for x in c["marches"] if x["id"] != m["id"]]
                        out.append(dict(uid=uid, txt="⚠️ لشکرت به‌خاطر یه خطای فنی برگشت؛ نیروها سالم برگشتن", frames=None))
            await db.save(c)
    for res in out:
        await deliver(res)


async def march_loop():
    while True:
        await asyncio.sleep(15)
        try:
            await march_tick()
        except Exception:
            log_exc("march_loop")


def recall(c, mid):
    """فراخوانی لشکر وسط راه: نیروها برمی‌گردن ولی هزینه‌ی حمل‌ونقل پس داده نمیشه."""
    m = next((x for x in c.get("marches", []) if str(x["id"]) == str(mid)), None)
    if not m:
        return "این لشکر دیگه نیست (شاید رسیده)"
    if now() >= m["arrive"]:
        return "لشکر همین الان رسیده؛ دیگه نمیشه فراخوند"
    for k, v in m["sent"].items():
        c["units"][k] = c["units"].get(k, 0) + v
    c["marches"] = [x for x in c["marches"] if x is not m]
    return f"↩️ لشکر به «{esc(m['name'])}» فراخونده شد؛ نیروها برگشتن (هزینه‌ی حمل‌ونقل پس داده نمیشه)"


def s_marches(c):
    ms = c.get("marches", [])
    t = [f"🧭 <b>لشکرها</b> ({len(ms)}/{march_cap(c)})"]
    rows = []
    if not ms:
        t.append("\nالان لشکری در راه نیست. از «جنگ ← هدف» لشکرکشی کن.")
    for m in ms:
        left = m["arrive"] - now()
        t.append(f"\n{mode_tag(m['mode'])}{' 🏴' if m.get('conquest') else ''} → <b>{esc(m['name'])}</b> · 📍 {m['dist']:.0f} خونه · ⏱ {prog.dur(left)} دیگه\n"
                 f"   🪖 {fmt_units(m['sent'])}")
        rows.append([(f"↩️ فراخوانی · {m['name'][:16]}", f"w:rc:{m['id']}")])
    t.append("\n💡 زمان و هزینه به فاصله، مقدار و نوع ارتش بستگی داره؛ زمینی فقط روی یه قاره، دریایی با بندر، هوایی با کارخانه‌ی قوی‌تر بُرد بیشتر میشن.")
    return "\n".join(t), kb(rows + [[("⚔️ جنگ", "w")], BACK])


# ------------------------------------------------------------------ صفحه‌ها
def s_war(c):
    sh = c["shield_until"] - now()
    land = c.get("land", config.LAND_START)
    t = ["⚔️ <b>مرکز فرماندهی جنگ</b>",
         f"🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🚀 {c['units'].get('missile', 0)} · 🏞 {land} استان",
         orders_line(c),
         f"🏆 امتیاز جنگ این هفته: {n(prog.stat(c, 'w', 'war'))} · ⚔️ {c['wins']}/{c['losses']}"]
    if sh > 0:
        t.append(f"🛡 سپر فعال ({sh / 3600:.1f}h) — حمله به بازیکن سپرت رو می‌شکنه")
    if c.get("marches"):
        nxt = min(m["arrive"] for m in c["marches"]) - now()
        t.append(f"🧭 {len(c['marches'])} لشکر در راهه (اولی {prog.dur(nxt)} دیگه می‌رسه)")
    if c.get("colony"):
        t.append(f"🏕 {len(c['colony'])} استعمار در حال انجام")
    live = [k for k, v in c["revenge"].items() if v > now()]
    if live:
        t.append(f"💢 {len(live)} نفر بهت حمله کردن و فرصت انتقام داری")
    ev = events.banner_lines()
    if ev:
        t += [""] + ev
    if c.get("blog"):
        t.append("\n📜 <b>آخرین نبردها</b>\n" + "\n".join(c["blog"][-3:]))
    t.append(f"\n🎖 کمپین: مرحله‌ی {c['camp']['stage']}")
    rows = [[(f"🎖 کمپین · مرحله {c['camp']['stage']}", "w:camp")]]
    if boss_active():
        rows.append([(f"🌑 جنگ بزرگ · {BOSS['name']}", "w:boss")])
    rows += [[("🎯 جنگ با بازیکن‌ها", "w:t"), ("🌍 NPCها", "w:npc")],
             [(f"🧭 لشکرها ({len(c.get('marches', []))})", "w:mar"), ("🤝 همسایه‌ها", "w:nb")],
             [("🏕 استعمار زمین خالی", "cl"), ("🏞 استان‌ها", "pv")],
             [("🕵️ جاسوسی", "s"), ("📜 گزارش نبردها", "w:log")]]
    return "\n".join(t), kb(rows + [BACK])


def s_log(c):
    t = "📜 <b>گزارش آخرین نبردها</b>\n\n" + ("\n".join(c.get("blog", [])[::-1]) or "هنوز نبردی نداشتی")
    return t, kb([[("⚔️ جنگ", "w")], BACK])


def _dist_tag(c, tid):
    """«📍۱۸🤝» برای فاصله‌ی من تا کشور tid (اگه موقعیت‌ها توی کش باشن)."""
    if c is None:
        return ""
    d = geo.dist(c["_id"], tid)
    if d is None:
        return ""
    return f" · 📍{d:.0f}" + ("🤝" if geo.is_neighbor(c["_id"], tid) else "")


def npc_lines(docs, c=None):
    return [f"{-d['_id']}. {esc(d['name'])} · {'⭐' * d['tier']} · دفاع ~{n(E.defense_power(d))} · جایزه {n(d['bounty'])}💰{_dist_tag(c, d['_id'])}" for d in docs]


async def s_npcs(c):
    await geo.refresh(need=c["_id"])
    npcs = await db.C.find({"npc": True, "_id": {"$gt": -100}}).sort("_id", -1).to_list(20)
    t = ["🌍 <b>کشورهای جهان (NPC)</b> — حریف‌های آموزشی (📍 فاصله · 🤝 همسایه)؛ برای جنگ بی‌پایان به «کمپین» برو"] + npc_lines(npcs, c)
    rows = [[(f"🌍 {d['name'][:14]} {'⭐' * d['tier']}", f"w:pick:{d['_id']}")] for d in npcs]
    return "\n".join(t), kb(rows + [[("⚔️ جنگ", "w")], BACK])


async def s_targets(c):
    t0 = now()
    await geo.refresh(need=c["_id"])
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    pacts = set()
    async for p in db.PACTS.find({"kind": "pact", "status": "active", "end": {"$gt": t0}, "$or": [{"a": c["_id"]}, {"b": c["_id"]}]}):
        pacts.add(p["b"] if p["a"] == c["_id"] else p["a"])
    docs = await db.C.find({"npc": {"$ne": True}, "_id": {"$ne": c["_id"]}}).to_list(600)
    mine = max(1, E.score(c))
    cand, shielded, why, total = [], [], {"pact": 0, "ally": 0, "weak": 0}, 0
    for d in docs:
        if d["_id"] in banned:
            continue
        total += 1
        E.defaults(d)
        if d["_id"] in pacts:
            why["pact"] += 1
            continue
        if c.get("alliance") and d.get("alliance") == c["alliance"]:
            why["ally"] += 1
            continue
        sc = E.score(d)
        rev = c["revenge"].get(str(d["_id"]), 0) > t0
        if sc < config.BULLY_RATIO * mine and not rev:
            why["weak"] += 1
            continue
        if d["shield_until"] > t0:
            shielded.append((d["shield_until"] - t0, d, sc))
            continue
        cand.append((0 if rev else 1, abs(math.log(max(sc, 1) / mine)) + 0.012 * (geo.dist(c["_id"], d["_id"]) or 0), d, sc, rev))
    cand.sort(key=lambda x: (x[0], x[1]))
    t = ["🎯 <b>هدف‌های بازیکن</b> (به قدرت تو نزدیک‌ترها)", orders_line(c), "⭐ = ارزش جایزه · 💢 = فرصت انتقام · 📍 فاصله (خونه) · 🤝 همسایه", f"👥 {total} بازیکن دیگه توی جهانن", ""]
    rows = []
    for _, _, d, sc, rev in cand[:6]:
        stars = "⭐⭐⭐" if sc >= 1.3 * mine else "⭐⭐" if sc >= 0.7 * mine else "⭐"
        view, exact = def_view(c, d)
        t.append(f"{'💢' if rev else '•'} {d.get('emblem', '🏛')} {esc(d['name'])} · 🛡 {view} · 🏞 {d.get('land', 5)} · {stars}{_dist_tag(c, d['_id'])}")
        rows.append([(f"{'💢 ' if rev else ''}{d['name'][:18]} {stars}", f"w:pick:{d['_id']}")])
    if shielded:
        shielded.sort(key=lambda x: x[0])
        t.append("\n🛡 <b>سپردارها</b> (تا سپرشون تموم نشه نمیشه زدشون):")
        for left, d, sc in shielded[:4]:
            t.append(f"• {d.get('emblem', '🏛')} {esc(d['name'])} · {prog.dur(left)} دیگه · 🏞 {d.get('land', 5)}")
    if not cand:
        bits = []
        if shielded:
            bits.append(f"🛡 {len(shielded)} نفر سپر دارن")
        if why["pact"]:
            bits.append(f"🕊 {why['pact']} نفر پیمان داری")
        if why["ally"]:
            bits.append(f"🤝 {why['ally']} نفر هم‌پیمانتن")
        if why["weak"]:
            bits.append(f"🙅 {why['weak']} نفر خیلی ضعیف‌ترن")
        t.append("\n😴 الان هدف قابل‌حمله‌ای نیست" + (": " + " · ".join(bits) if bits else "") + "\nتا اون موقع بزن به NPC یا کمپین 👇")
        npcs = await db.C.find({"npc": True, "_id": {"$gt": -100}}).to_list(20)
        my_atk = max(1.0, E.attack_power(c))
        npcs.sort(key=lambda d: abs(math.log(max(1.0, E.defense_power(d)) / my_atk)))
        for d in npcs[:3]:
            rows.append([(f"🌍 {d['name'][:16]} {'⭐' * d['tier']}", f"w:pick:{d['_id']}")])
    rows.append([("🔄 لیست جدید", "w:t"), ("🎖 کمپین", "w:camp")])
    return "\n".join(t), kb(rows + [[("⚔️ جنگ", "w")], BACK])


def _mode_row(c, d, same, md, pct=60):
    """یه خط خلاصه برای هر نوع حمله: زمان و هزینه یا دلیل نشدن."""
    br = config.mode_branches(md)
    rg = geo.ranges(c)
    if len(br) == 1:
        b0 = br[0]
        if b0 == "land" and not same:
            return f"{mode_tag(md)}: ✖ قاره‌ی دیگه"
        if d > rg[b0]:
            return f"{mode_tag(md)}: ✖ بُرد {rg[b0]} خونه"
    plan, err = geo.plan(c, pct, md, d, same)
    if not plan:
        return f"{mode_tag(md)}: ✖ " + ("بُرد/قاره" if err and "📏" in err else "یگان نداری")
    return f"{mode_tag(md)}: ⏱ {prog.dur(plan['secs'])} · 💰 {launch_cost(plan):,}"


async def s_pick(c, tid, mode="all"):
    t = await db.load(tid)
    if not t:
        return "هدف پیدا نشد", kb([BACK])
    mode = _mode(mode)
    npc = bool(t.get("npc"))
    view, exact = def_view(c, t)
    rev = (not npc) and c["revenge"].get(str(tid), 0) > now()
    loc = await locate(c, tid)
    lines = [f"🎯 <b>{esc(t['name'])}</b> {t.get('emblem', '')}" + (f" · {'⭐' * t['tier']}" if npc else f" · 🏞 {t.get('land', 5)} استان")]
    ok = None
    if loc:
        d, same, neigh = loc
        ok = geo.reachable(c, d, same)
        lines.append(f"📍 {d:.0f} خونه · {'🤝 همسایه (تسخیر ممکنه)' if neigh else '🌐 دور (فقط حمله‌ی معمولی)'} · {'همین قاره' if same else '🌊 قاره‌ی دیگه'}")
    lines += [f"🛡 دفاع: <b>{view}</b>" + (" ✅ دقیق (جاسوسی)" if exact else " — برای عدد دقیق جاسوسی کن"),
              f"🗡 قدرت تو: {n(E.attack_power(c))} · {orders_line(c)}"]
    if loc:
        lines.append("\n🧭 <b>انواع حمله</b> (۶۰٪ ارتش):")
        lines += [_mode_row(c, d, same, md) for md in ("all", "land", "sea", "air")]
        if len(config.mode_branches(mode)) == 2:
            lines.append(_mode_row(c, d, same, mode) + "  ← ترکیب انتخابی")
        lines.append(f"انتخاب فعلی: <b>{mode_tag(mode)}</b> (با دکمه‌های پایین هر ترکیبی از ۳ شاخه رو انتخاب کن)")
    if exact:
        sup = 0.0 if npc else await ally_support(t)
        ch = {pp: est_sent(c, t, pp, mode, sup, ok)[2] for pp in (30, 60, 100)}
        lines.append("🎲 شانس پیروزی: " + " · ".join(f"{pp}٪ ارتش ← ~{int(v * 100)}٪" for pp, v in ch.items()) + f" {difficulty(ch[100])}")
        bp, bpr, _ = best_pct(c, t, sup, mode, ok)
        lines.append(f"🎯 پیشنهاد: {bp}٪ ارتش (شانس ~{int(bpr * 100)}٪)" if bpr >= 0.5 else "🎯 با این نوع حمله و ارتش فعلی‌ات این حریف سخته؛ اول تقویت شو یا نوع دیگه‌ای بزن")
        if npc:
            u = " ".join(f"{U[k]['e']}{v}" for k, v in t["units"].items() if v)
            lines.append(f"🪖 {u or '—'} · غرامت برد: {n(t['bounty'])}💰")
        else:
            i = intel_of(c, tid)
            if i:
                u = " ".join(f"{U[k]['e']}{v}" for k, v in i["units"].items() if v)
                lines.append(f"🪖 {u or '—'} · غنیمت ≈ ۱۲٪ از {n(max(0, i['treasury']))}💰")
    if crown.is_holder(tid):
        lines.append(f"👑 <b>امپراتور جهانه!</b> اگه ببریش تاج و {n(config.CROWN_BOUNTY)}💰 جایزه مال توئه")
    if rev:
        lines.append("💢 فرصت انتقام داری: بدون فرمان و با غنیمت ۲۵٪ بیشتر")
    lines.append("⚙️ دفاع مدافع به نوع حمله بستگی داره: زمینی بیشتر با ارتش زمینی‌ش می‌جنگی، هوایی با پدافند و جنگنده، دریایی با ناوگان")
    if loc and neigh:
        lines.append(f"🏴 «تسخیر» ۲ فرمان می‌خواد؛ پیروزی قاطع (نسبت ≥ {config.CONQUEST_RATIO}) یه استان می‌گیری"
                     + (f" · 🏞 این NPC الان {t.get('land', 5)} استان داره" if npc else ""))
    lines += ["", STANCE_LEGEND]
    cur = set(config.mode_branches(mode))
    tog = []
    for b_ in config.BRANCH_ORDER:                              # هر دکمه یه شاخه رو روشن/خاموش می‌کنه (ترکیب دلخواه)
        nxt = (cur - {b_}) if b_ in cur else (cur | {b_})
        nxt = nxt or {b_}
        tog.append((("✅ " if b_ in cur else "▫️ ") + config.BRANCH_E[b_] + config.BRANCH_N[b_], f"w:pick:{tid}:{config.norm_mode('+'.join(nxt))}"))
    modes = [tog, [(("✅ " if len(cur) == 3 else "") + "🌐 همه‌جانبه", f"w:pick:{tid}:all")]]
    rows = modes + ([[("🎯 حمله‌ی هوشمند (کمترین ارتشِ لازم)", f"w:auto:{tid}:{mode}")]] if exact else []) \
        + stance_rows(lambda p, s: f"w:go:{tid}:{p}:{s}:{mode}")
    if loc and neigh and "land" in config.mode_branches(mode):
        rows.append([("🏴 تسخیر ۶۰٪", f"w:cq:{tid}:60:{mode}"), ("🏴 تسخیر ۱۰۰٪", f"w:cq:{tid}:100:{mode}")])
    rows.append([("🕵️ جاسوسی · ۵۰۰", f"w:spy:{tid}"), ("🔙", "w:npc" if npc else "w:t")])
    return "\n".join(lines), kb(rows)


async def s_neighbors(c):
    await geo.refresh(need=c["_id"])
    nb = geo.neighbors(c["_id"])
    ids = sorted(nb, key=nb.get)[:12]
    docs = {d["_id"]: d async for d in db.C.find({"_id": {"$in": ids}})}
    me = geo.CACHE["pos"].get(c["_id"])
    t = ["🤝 <b>همسایه‌های من</b> — «تسخیر» فقط روی این کشورها ممکنه",
         f"📍 پایتخت تو روی نقشه ثبت شده · {len(nb)} همسایه" if me else "📍 هنوز روی نقشه جاگذاری نشدی", ""]
    rows = []
    for tid in ids:
        d = docs.get(tid)
        if not d:
            continue
        E.defaults(d)
        sh = " 🛡" if d["shield_until"] > now() else ""
        t.append(f"• {d.get('emblem', '🏛')} {esc(d['name'])}{' 🤖' if d.get('npc') else ''} · 📍{nb[tid]:.0f} · 🏞 {d.get('land', 5)} · 🛡 {def_view(c, d)[0]}{sh}")
        rows.append([(f"{d['name'][:20]} · 📍{nb[tid]:.0f}", f"w:pick:{tid}")])
    if not ids:
        t.append("هنوز همسایه‌ای نداری؛ با ثبت‌نام بازیکن‌های بیشتر یا آباد کردن زمین‌های خالی (استعمار) نقشه شلوغ‌تر میشه.")
    t.append("\n🌐 به کشورهای دور هم می‌تونی حمله‌ی معمولی بزنی (زمان و هزینه‌ی حمل‌ونقل بیشتر).")
    return "\n".join(t), kb(rows + [[("⚔️ جنگ", "w")], BACK])


# ------------------------------------------------------------------ مسیریابی دکمه‌ها
def _i(p, k, d=0):
    try:
        return int(p[k])
    except (IndexError, ValueError):
        return d


async def route(c, p):
    """p = ['w', زیرصفحه, ...] → (toast، (متن، کیبورد))"""
    sub = p[1] if len(p) > 1 else ""
    after = kb([[("🎯 هدف دیگه", "w:t")], [("⚔️ جنگ", "w")], BACK])
    if sub == "pick" and len(p) > 2:
        return None, await s_pick(c, _i(p, 2), p[3] if len(p) > 3 else "all")
    if sub == "go" and len(p) > 3:
        return None, (await do_attack(c, _i(p, 2), _i(p, 3, 60), p[4] if len(p) > 4 else "bal", False, p[5] if len(p) > 5 else "all"), after)
    if sub == "mar":
        return None, s_marches(c)
    if sub == "rc" and len(p) > 2:
        txt = recall(c, p[2])
        text, mk = s_marches(c)
        return None, (txt + "\n\n" + text, mk)
    if sub == "nb":
        return None, await s_neighbors(c)
    if sub == "auto" and len(p) > 2:
        tid = _i(p, 2)
        t = await db.load(tid)
        if not t:
            return None, ("هدف پیدا نشد", after)
        if not t.get("npc") and not intel_of(c, tid):
            return None, ("🕵️ حمله‌ی هوشمند عدد دقیق دفاع رو لازم داره؛ اول «جاسوسی» کن", after)
        md = _mode(p[3] if len(p) > 3 else "all")
        loc = await locate(c, tid)
        ok = geo.reachable(c, loc[0], loc[1]) if loc else None
        bp, bpr, _ = best_pct(c, t, 0.0 if t.get("npc") else await ally_support(t), md, ok)
        return None, (await do_attack(c, tid, bp, "bal", False, md), after)
    if sub == "cq" and len(p) > 3:
        return None, (await do_attack(c, _i(p, 2), _i(p, 3, 60), "bal", True, p[4] if len(p) > 4 else "all"), after)
    if sub == "spy" and len(p) > 2:
        txt = await do_spy(c, _i(p, 2), "scout")
        text, mk = await s_pick(c, _i(p, 2))
        return None, (txt + "\n\n" + text, mk)
    if sub == "camp":
        return None, s_camp(c)
    if sub == "cg" and len(p) > 2:
        txt = do_camp(c, _i(p, 2, 60), p[3] if len(p) > 3 else "bal")
        return None, (txt, kb([[("🎖 مرحله‌ی بعد", "w:camp")], [("⚔️ جنگ", "w")], BACK]))
    if sub == "boss":
        return None, await s_boss(c)
    if sub == "bh" and len(p) > 2:
        txt = await boss_hit(c, _i(p, 2, 60))
        return None, (txt, kb([[("💥 ضربه‌ی دیگه", "w:boss")], [("⚔️ جنگ", "w")], BACK]))
    if sub == "t":
        return None, await s_targets(c)
    if sub == "npc":
        return None, await s_npcs(c)
    if sub == "log":
        return None, s_log(c)
    return None, s_war(c)
