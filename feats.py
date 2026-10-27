"""قابلیت‌های ساده‌ی تازه: 🏞 استان‌ها (هدف‌یاب تسخیر NPC) و 🏅 دستاوردها (جایزه‌ی یک‌باره)."""
import math

import config
import db
import engine as E
import geo
from commands import cmd
from util import BACK, esc, kb, n

# (id، ایموجی، عنوان، تابع شرط، جایزه‌ی سکه)
ACH = [
    ("land7", "🏞", "قلمرو ۷ استانی", lambda c: c.get("land", 5) >= 7, 1500),
    ("land12", "🗺", "قلمرو ۱۲ استانی", lambda c: c.get("land", 5) >= 12, 6000),
    ("npc1", "⚔️", "اولین پیروزی روی NPC", lambda c: c["st"].get("npc_wins", 0) >= 1, 500),
    ("npc10", "🎖", "۱۰ پیروزی روی NPC", lambda c: c["st"].get("npc_wins", 0) >= 10, 3000),
    ("npc50", "🏆", "۵۰ پیروزی روی NPC", lambda c: c["st"].get("npc_wins", 0) >= 50, 12000),
    ("score5k", "⭐", "قدرت ۵٬۰۰۰", lambda c: E.score(c) >= 5000, 2000),
    ("score50k", "🌟", "قدرت ۵۰٬۰۰۰", lambda c: E.score(c) >= 50000, 15000),
    ("army1k", "🪖", "ارتش ۱٬۰۰۰ نفری", lambda c: E.army_size(c) >= 1000, 2500),
]


def _progress(c):
    return {a[0]: bool(a[3](c)) for a in ACH}


def s_ach(c):
    got = c.setdefault("ach", [])
    new = []
    for aid, em, title, ok, rew in ACH:
        if aid not in got and ok(c):
            got.append(aid)
            c["treasury"] += rew
            new.append(f"{em} <b>{title}</b> · +{n(rew)}💰")
    lines = ["🏅 <b>دستاوردها</b>"]
    if new:
        lines += ["", "🎉 <b>دستاورد تازه!</b>"] + new + [""]
    for aid, em, title, ok, rew in ACH:
        lines.append(f"{'✅' if aid in got else '🔒'} {em} {title}" + ("" if aid in got else f" · جایزه {n(rew)}💰"))
    lines.append(f"\n{len(got)} از {len(ACH)} دستاورد")
    return "\n".join(lines), kb([BACK])


async def s_provinces(c):
    npcs = await db.C.find({"npc": True, "_id": {"$gt": -100}}).sort("_id", -1).to_list(20)
    my = E.attack_power(c)
    lines = [f"🏞 <b>استان‌ها</b> — قلمروی تو: <b>{c.get('land', 5)}</b> استان (سقف با جمعیتت: {E.land_cap(c)})",
             f"🏴 «تسخیر» فقط روی <b>همسایه‌ها</b> ممکنه، ۲ فرمان می‌خواد و با پیروزی قاطع (نسبت ≥ {config.CONQUEST_RATIO}) یه استان می‌گیری. استان NPC هر {config.NPC_LAND_REGEN_H} ساعت یکی بازسازی میشه.",
             "🏕 زمین خالی هم هست: «استعمار» با هزینه و زمان زیاد یه استان تازه می‌سازه.", ""]
    best, rows = None, []
    for d in npcs:
        cd = config.NPC_CD - (E.now() - c["npc_cd"].get(str(d["_id"]), 0))
        ready = cd <= 0 and d.get("land", 5) > config.LAND_MIN
        dfn = E.defense_power(d)
        fit = abs(math.log(max(1.0, dfn) / max(1.0, my)))
        lines.append(f"{'🟢' if ready else '⏳'} {-d['_id']}. {esc(d['name'])} {'⭐' * d['tier']} · 🏞 {d.get('land', 5)} · دفاع ~{n(dfn)}")
        if ready and dfn <= my * 0.9 and (best is None or fit < best[0]):
            best = (fit, d)
        rows.append([(f"🏴 {d['name'][:16]} · {d.get('land', 5)}🏞", f"w:pick:{d['_id']}")])
    lines.append("")
    lines.append(f"🎯 بهترین هدف تسخیر الان: <b>{esc(best[1]['name'])}</b>" if best else "😴 الان NPC آماده‌ی تسخیری نیست؛ ارتشت رو قوی‌تر کن یا صبر کن.")
    if best:
        rows.insert(0, [(f"🎯 تسخیر {best[1]['name'][:14]}", f"w:pick:{best[1]['_id']}")])
    rows.append([("🏕 استعمار زمین خالی", "cl"), ("🤝 همسایه‌ها", "w:nb")])
    return "\n".join(lines), kb(rows + [BACK])


async def s_colony(c, msg=""):
    await geo.refresh(need=c["_id"])
    free = geo.free_cells()
    coins, steel, food = E.colony_cost(c)
    secs = E.colony_secs(c)
    jobs = c.get("colony", [])
    t = ["🏕 <b>استعمار — آباد کردن زمین خالی</b>"]
    if msg:
        t += [msg, ""]
    t += [f"🏞 قلمروی تو: <b>{c.get('land', config.LAND_START)}</b> استان (سقف با جمعیتت: {E.land_cap(c)}) · 🗺 زمین خالی نقشه: {free:,} خونه",
          f"📦 هزینه‌ی استان بعدی: 💰 {coins:,} · ⚙️ {steel:,} · 🌾 {food:,}",
          f"⏱ زمان ساخت: <b>{_dur(secs)}</b>",
          f"🏰 شرط: کاخ سطح {config.COLONY_MIN_PALACE}+ (الان {E.lv(c, 'palace')}) · ظرفیت هم‌زمان {E.colony_slots(c)} (کاخ ۵ = دومی)",
          "💡 هر استان بعدی گرون‌تر و کندتره. سقف استان‌ها به جمعیتت بستگی داره (۵ استان با ۱۰ هزار نفر، بعدش هر ۲٬۵۰۰ نفر یکی).",
          f"🗺 نقشه خودکار با تعداد کشورها بزرگ میشه و همیشه زمین خالی داره"]
    for j in jobs:
        t.append(f"🏗 در حال آباد شدن: {_dur(j['end'] - E.now())} دیگه")
    rows = [[("🏕 شروع استعمار", "cl:go")], [("🏞 استان‌ها", "pv")]]
    return "\n".join(t), kb(rows + [BACK])


def _dur(s):
    import prog
    return prog.dur(s)


@cmd("colonize", "استعمار", "آبادسازی", "آباد سازی", args=True)
async def h_colonize(m, c, a):
    if a and a.split()[0] in ("شروع", "تایید", "تأیید", "go"):
        await geo.refresh(need=c["_id"])
        ok, msg = E.colony_start(c, geo.free_cells())
        return await s_colony(c, msg)
    return await s_colony(c)


@cmd("achievements", "دستاورد", "دستاوردها", "مدال")
async def h_ach(m, c, a):
    return s_ach(c)


@cmd("provinces", "استان", "استان‌ها", "استانها")
async def h_prov(m, c, a):
    return await s_provinces(c)
