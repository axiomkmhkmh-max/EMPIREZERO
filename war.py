"""سیستم جنگ بزرگ EMPIRE ZERO.

ایده‌ی کلی (سخت ولی ساده):
  ⚡ فرمان نظامی   هر حمله ۱ فرمان می‌خواد؛ فرمان‌ها کم‌کم پر میشن، پس نمیشه بی‌نهایت جنگید.
  🎖 کمپین جهانی    مرحله‌های بی‌پایان؛ دشمن هر مرحله قوی‌تره، حتی با ارتش مکس هم همیشه حریف داری.
  🗡 جنگ بازیکن‌ها  سه جبهه (هوا، دریا، زمین) + ضدیت یگان‌ها + تاکتیک + جاسوسی + انتقام + تسخیر استان.
  🌑 جنگ بزرگ      یه تهدید جهانی با HP مشترک؛ همه با هم می‌زنن و جایزه می‌گیرن.
"""
import asyncio
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
import prog
import reg
import world
from config import U
from core import log_exc, notify, tlog
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


def def_view(c, t):
    """(متن دفاع، دقیق؟)"""
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
    if BOSS["hp"] <= 0:
        txt += "\n\n🎉 <b>تهدید نابود شد!</b> جایزه‌ها در حال ارسال..."
        await boss_finish(True, cur=c)
    else:
        await boss_save()
    return txt


# ------------------------------------------------------------------ حمله به NPC و بازیکن
async def do_attack(c, tid, pct, stance="bal", conquest=False):
    t = await db.load(tid)
    if not t or t["_id"] == c["_id"]:
        return "هدف پیدا نشد"
    npc = bool(t.get("npc"))
    pct = max(10, min(100, int(pct)))
    stance = stance if stance in E.STANCES else "bal"
    if conquest and npc:
        return "🏴 تسخیر استان فقط روی بازیکن‌هاست"
    revenge = (not npc) and c["revenge"].get(str(tid), 0) > now()
    if npc:
        left = config.NPC_CD - (now() - c["npc_cd"].get(str(tid), 0))
        if left > 0:
            return f"⏳ ارتش این کشور هنوز بازسازی نشده؛ {int(left // 60) + 1} دقیقه‌ی دیگه"
    else:
        if t["shield_until"] > now():
            return "🛡 این کشور سپر داره"
        if c.get("alliance") and t.get("alliance") == c["alliance"]:
            return "🤝 هم‌پیمانته"
        if await world.has_pact(c["_id"], tid):
            return "🕊 با این کشور پیمان عدم‌تجاوز داری"
        left = config.PVP_CD - (now() - c["pvp_cd"].get(str(tid), 0))
        if left > 0 and not revenge:
            return f"⏳ تازه بهش حمله کردی؛ {prog.dur(left)} دیگه می‌تونی دوباره بزنی"
        if E.score(t) < config.BULLY_RATIO * E.score(c) and not revenge:
            return "🙅 این کشور خیلی ضعیف‌تر از توئه (کمتر از ۲۰٪ قدرتت)؛ حریف هم‌وزن پیدا کن"
        if conquest and c["land"] >= config.LAND_MAX:
            return f"🏞 بیشتر از {config.LAND_MAX} استان نمی‌تونی داشته باشی"
    need = 0 if (revenge and not conquest) else (2 if conquest else 1)
    err = check_ready(c, pct, need)
    if err:
        return err
    if need:
        E.spend_orders(c, need)
    c["treasury"] -= logi_cost(c, pct)
    rel = 1.0 if npc else max(0.3, min(1.6, math.sqrt(E.score(t) / max(1, E.score(c)))))
    r = E.battle(c, t, pct / 100, 0.0 if npc else await ally_support(t), stance, rel * (1.25 if revenge else 1.0))
    if not r:
        return "🪖 ارتش تهاجمی نداری"
    extra, crown_def = "", ""
    prog.bump(c, "attack")
    if r["win"]:
        prog.bump(c, "win")
    if npc:
        c["npc_cd"][str(tid)] = now()
        if r["win"]:
            bounty = int(t["bounty"] * events.mult("loot"))
            c["treasury"] += bounty
            c["st"]["npc_wins"] = c["st"].get("npc_wins", 0) + 1
            pts = 4 * t["tier"]
            prog.add(c, "war", pts)
            extra = f"\n🎖 غرامت جنگی: {n(bounty)} سکه · 🏆 {pts} امتیاز جنگ"
            if random.random() < 0.10 * t["tier"]:
                c["fx"]["PHX"] = c["fx"].get("PHX", 0) + 1
                extra += " · +1 ⚡زیرو"
        log_battle(c, f"🌍 {t['name']}: {'پیروزی' if r['win'] else 'شکست'}")
    else:
        c["shield_until"] = 0.0
        c["pvp_cd"][str(tid)] = now()
        if revenge:
            c["revenge"].pop(str(tid), None)
        sc_t, sc_c = E.score(t), max(1, E.score(c))
        if r["win"]:
            pts = int(20 * rel * (1.5 if sc_t >= 1.3 * sc_c else 1.0))
            prog.add(c, "war", pts)
            extra = f"\n🏆 +{pts} امتیاز جنگ"
            if revenge:
                extra += " · 💢 انتقام گرفتی!"
            if conquest and r["decisive"] and t["land"] > config.LAND_MIN and c["land"] < config.LAND_MAX:
                t["land"] -= 1
                c["land"] += 1
                extra += f"\n🏴 <b>یه استان تسخیر شد!</b> قلمروت {c['land']} استان شد (طرف مقابل {t['land']})"
                world.news(f"🏴 <b>{esc(c['name'])}</b> یه استان از <b>{esc(t['name'])}</b> تسخیر کرد!", important=True)
            elif conquest:
                extra += f"\n🏴 پیروزی قاطع نبود (نسبت {r['ratio']:.2f}؛ باید ≥ {config.CONQUEST_RATIO}) پس استانی تسخیر نشد"
            if sc_t >= 1.5 * sc_c:
                world.news(f"⚔️ <b>{esc(c['name'])}</b> کشور قوی‌تر <b>{esc(t['name'])}</b> رو شکست داد!")
            if crown.is_holder(t["_id"]):                   # 👑 امپراتور رو شکست دادی
                ex_a, crown_def = crown.seize(c, t)
                extra += ex_a
        else:
            t_pts = 8
            prog.add(t, "war", t_pts)
        t["revenge"][str(c["_id"])] = now() + config.REVENGE_H * 3600
        log_battle(c, f"⚔️ حمله به {t['name']}: {'پیروزی' if r['win'] else 'شکست'}")
        log_battle(t, f"🛡 {c['name']} حمله کرد: {'شکست خوردی' if r['win'] else 'دفاع موفق'}")
        tlog("⚔️", "حمله‌ی بازیکن", f"{esc(c['name'])} → {esc(t['name'])} · {'🏆 پیروزی' if r['win'] else '💀 شکست'}"
             + (" · 🏴 تسخیر" if conquest else ""))
    await db.save(t)
    an, dn = crown.tag(c["_id"]) + c["name"], crown.tag(t["_id"]) + t["name"]
    txt = report(r, an, dn) + extra
    cine.stash(c["_id"], cine.battle_frames(r, an, dn))
    if not npc:
        tok = OWNER.set(tid)
        try:
            mk = kb([[("💢 انتقام", f"w:pick:{c['_id']}")]])
        finally:
            OWNER.reset(tok)
        await notify(tid, "🚨 <b>به کشورت حمله شد!</b>\n" + report(r, an, dn)
                     + f"\n\n💢 {config.REVENGE_H} ساعت فرصت داری انتقام بگیری (فرمان نمی‌خواد و غنیمت ۲۵٪ بیشتره)" + crown_def, mk)
    return txt


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
             [("🕵️ جاسوسی", "s"), ("📜 گزارش نبردها", "w:log")]]
    return "\n".join(t), kb(rows + [BACK])


def s_log(c):
    t = "📜 <b>گزارش آخرین نبردها</b>\n\n" + ("\n".join(c.get("blog", [])[::-1]) or "هنوز نبردی نداشتی")
    return t, kb([[("⚔️ جنگ", "w")], BACK])


def npc_lines(docs):
    return [f"{-d['_id']}. {esc(d['name'])} · {'⭐' * d['tier']} · دفاع ~{n(E.defense_power(d))} · جایزه {n(d['bounty'])}💰" for d in docs]


async def s_npcs(c):
    npcs = await db.C.find({"npc": True, "_id": {"$gt": -100}}).sort("_id", -1).to_list(20)
    t = ["🌍 <b>کشورهای جهان (NPC)</b> — حریف‌های آموزشی؛ برای جنگ بی‌پایان به «کمپین» برو"] + npc_lines(npcs)
    rows = [[(f"🌍 {d['name'][:14]} {'⭐' * d['tier']}", f"w:pick:{d['_id']}")] for d in npcs]
    return "\n".join(t), kb(rows + [[("⚔️ جنگ", "w")], BACK])


async def s_targets(c):
    t0 = now()
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    pacts = set()
    async for p in db.PACTS.find({"kind": "pact", "status": "active", "end": {"$gt": t0}, "$or": [{"a": c["_id"]}, {"b": c["_id"]}]}):
        pacts.add(p["b"] if p["a"] == c["_id"] else p["a"])
    docs = await db.C.find({"npc": {"$ne": True}, "_id": {"$ne": c["_id"]}, "shield_until": {"$lt": t0}}).to_list(400)
    mine, cand = max(1, E.score(c)), []
    for d in docs:
        if d["_id"] in banned or d["_id"] in pacts or (c.get("alliance") and d.get("alliance") == c["alliance"]):
            continue
        E.defaults(d)
        sc = E.score(d)
        rev = c["revenge"].get(str(d["_id"]), 0) > t0
        if sc < config.BULLY_RATIO * mine and not rev:
            continue
        cand.append((0 if rev else 1, abs(math.log(max(sc, 1) / mine)), d, sc, rev))
    cand.sort(key=lambda x: (x[0], x[1]))
    t = ["🎯 <b>هدف‌های بازیکن</b> (به قدرت تو نزدیک‌ترها)", orders_line(c), "⭐ = ارزش جایزه · 💢 = فرصت انتقام", ""]
    rows = []
    for _, _, d, sc, rev in cand[:6]:
        stars = "⭐⭐⭐" if sc >= 1.3 * mine else "⭐⭐" if sc >= 0.7 * mine else "⭐"
        view, exact = def_view(c, d)
        t.append(f"{'💢' if rev else '•'} {d.get('emblem', '🏛')} {esc(d['name'])} · 🛡 {view} · 🏞 {d.get('land', 5)} · {stars}")
        rows.append([(f"{'💢 ' if rev else ''}{d['name'][:18]} {stars}", f"w:pick:{d['_id']}")])
    if not cand:
        t.append("حریف بدون سپری پیدا نشد. به «کمپین» برو؛ همیشه دشمن داره 🎖")
    rows.append([("🔄 لیست جدید", "w:t"), ("🎖 کمپین", "w:camp")])
    return "\n".join(t), kb(rows + [[("⚔️ جنگ", "w")], BACK])


async def s_pick(c, tid):
    t = await db.load(tid)
    if not t:
        return "هدف پیدا نشد", kb([BACK])
    npc = bool(t.get("npc"))
    view, exact = def_view(c, t)
    rev = (not npc) and c["revenge"].get(str(tid), 0) > now()
    lines = [f"🎯 <b>{esc(t['name'])}</b> {t.get('emblem', '')}" + (f" · {'⭐' * t['tier']}" if npc else f" · 🏞 {t.get('land', 5)} استان"),
             f"🛡 دفاع: <b>{view}</b>" + (" ✅ دقیق (جاسوسی)" if exact else " — برای عدد دقیق جاسوسی کن"),
             f"🗡 قدرت تو: {n(E.attack_power(c))} · {orders_line(c)}"]
    if exact:
        A, D, p = E.estimate(c, t, 1.0, "bal", 0.0 if npc else await ally_support(t))
        lines.append(f"🎲 شانس پیروزی با ۱۰۰٪ ارتش: ~{int(p * 100)}٪ {difficulty(p)}")
        i = intel_of(c, tid)
        if i:
            u = " ".join(f"{U[k]['e']}{v}" for k, v in i["units"].items() if v)
            lines.append(f"🪖 {u or '—'} · غنیمت ≈ ۱۲٪ از {n(max(0, i['treasury']))}💰")
    if crown.is_holder(tid):
        lines.append(f"👑 <b>امپراتور جهانه!</b> اگه ببریش تاج و {n(config.CROWN_BOUNTY)}💰 جایزه مال توئه")
    lines.append(f"🪖 بسیج ۶۰٪ ارتش ≈ {n(logi_cost(c, 60))}💰")
    if rev:
        lines.append("💢 فرصت انتقام داری: بدون فرمان و با غنیمت ۲۵٪ بیشتر")
    if not npc:
        lines.append(f"🏴 «تسخیر» ۲ فرمان می‌خواد؛ با پیروزی قاطع (نسبت ≥ {config.CONQUEST_RATIO}) یه استان می‌گیری")
    lines += ["", STANCE_LEGEND]
    rows = stance_rows(lambda p, s: f"w:go:{tid}:{p}:{s}")
    if not npc:
        rows.append([("🏴 تسخیر ۶۰٪", f"w:cq:{tid}:60"), ("🏴 تسخیر ۱۰۰٪", f"w:cq:{tid}:100")])
    rows.append([(f"🕵️ جاسوسی · ۵۰۰", f"w:spy:{tid}"), ("🔙", "w:npc" if npc else "w:t")])
    return "\n".join(lines), kb(rows)


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
        return None, await s_pick(c, _i(p, 2))
    if sub == "go" and len(p) > 3:
        return None, (await do_attack(c, _i(p, 2), _i(p, 3, 60), p[4] if len(p) > 4 else "bal"), after)
    if sub == "cq" and len(p) > 3:
        return None, (await do_attack(c, _i(p, 2), _i(p, 3, 60), "bal", True), after)
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
