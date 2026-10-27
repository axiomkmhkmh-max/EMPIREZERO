"""صفحه‌ها (منوی دکمه‌ای) و اقدام‌های جنگ/جاسوسی."""
import random
from datetime import datetime, timedelta, timezone

import config
import crown
import db
import eco
import engine as E
import events
import geo
import growth
import prog
import war
import world
from config import ASSETS, B, BRANCH, ITEMS, TECH, U
from core import notify, tlog
from prog import dur
from util import BACK, amount, bar, esc, kb, n

ALLY_MAX_VIEW = 40


fmt_units = war.fmt_units
report = war.report
npc_lines = war.npc_lines
do_spy = war.do_spy
s_war = war.s_war


# ------------------------------------------------------------------ نمای فشرده (برای گروه)
def brief(c):
    d = E.derive(c)
    sh = c["shield_until"] - E.now()
    b = c["bank"]
    t = [f"{c.get('emblem', '🏛')} <b>{esc(c['name'])}</b> · {esc(c['leader'])}" + (f" · {c['titles'][-1]}" if c.get("titles") else ""),
         f"💰 {n(c['treasury'])} ({d['net']:+,.0f}/ساعت) · 🏦 {n(b['dep'])}" + (f" · 🔻وام {n(b['loan'])}" if b["loan"] > 1 else ""),
         f"👥 {n(c['pop'])} · 😊 {c['sat']:.0f} · {E.unrest_stage(c['unrest'])[2]} {c['unrest']:.0f}",
         f"🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · ⚡ {c['fx'].get('PHX', 0):,.1f} زیرو",
         f"🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🏆 {n(E.score(c))} · 🏞 {c.get('land', 5)} استان"]
    if sh > 0:
        t.append(f"🛡 سپر {sh / 3600:.1f} ساعت")
    if c.get("pending"):
        t.append(f"📰 {len(c['pending'])} خبر جدید؛ بنویس «دنیای من»")
    return "\n".join(t)


TEHRAN = timezone(timedelta(hours=3, minutes=30))     # ایران ساعت تابستانی نداره؛ آفست ثابت کافیه

# (از ساعت، ایموجی، سلام، چند جمله‌ی گرم)
GREET = [
    (0, "🌙", "نیمه‌شبه", ["هنوز بیداری؟ کشورت مراقبت می‌کنه، تو هم یه خرده استراحت کن 🤍",
                          "شب‌زنده‌دارها همیشه بهترین فرمانروا‌ان! ولی یادت نره بخوابی 😴"]),
    (4, "🌄", "سحر بخیر", ["چه سحرخیز! کشورت از همین الان خوش‌شانسه که تو رو داره ✨",
                          "هنوز همه خوابن و تو داری امپراتوری می‌سازی 💪"]),
    (6, "☀️", "صبح بخیر", ["امیدوارم صبح قشنگی داشته باشی؛ مردمت چشم‌به‌راه تصمیم‌های تو‌ان ☕",
                          "یه چای داغ بردار و بریم سراغ کارای امروز 🌿",
                          "روزت پر از خبرای خوب باشه، فرمانروا 🌸"]),
    (11, "🌤", "ظهر بخیر", ["نیمه‌ی راه روزه؛ یه نفس بگیر و ببین کشورت چه خبره 🍽",
                           "ظهرت بخیر! دستت درد نکنه که این‌قدر به فکر مردمی 🤍"]),
    (14, "🌞", "بعدازظهر بخیر", ["بعدازظهر خوبیه برای تصمیم‌های بزرگ 😉",
                                "کشورت امروز خوب داره پیش میره؛ ادامه بده! 💫"]),
    (17, "🌇", "عصر بخیر", ["عصرت بخیر! وقت خوبیه یه نگاه به حساب‌کتاب‌ها بندازی 🍂",
                           "غروب قشنگیه؛ ببینیم مردمت امروز چی کار کردن 🌆"]),
    (20, "🌃", "شب بخیر", ["شبت آروم! قبل از خواب یه سر به کشورت بزن 🌙",
                          "شب‌ها بهترین وقت فکر کردنه؛ برنامه‌ی فردا چیه؟ ✨"]),
    (23, "🌌", "شبت بخیر", ["دیروقته ها! کشورت تا صبح دووم میاره، نگران نباش 😴",
                           "یه شب آروم برات آرزو می‌کنم، فرمانروا 🤍"]),
]


def greeting(c):
    h = datetime.now(TEHRAN).hour
    _, emo, hi, lines = [g for g in GREET if g[0] <= h][-1]
    return f"{emo} <b>{hi}، {esc(c['leader'])} عزیز!</b>\n<i>{random.choice(lines)}</i>"


def mood(c, d):
    """یه جمله‌ی کوتاه و گرم درباره‌ی حال کشور."""
    if c["starving"]:
        return "🍞 مردم گرسنه‌ان؛ یه فکری برای غذا بکن!"
    if c["treasury"] < 0:
        return "💸 خزانه منفیه؛ با یه کم برنامه‌ریزی درست میشه."
    if c["unrest"] >= 50:
        return "🚨 مردم ناراحتن؛ دلشون رو به دست بیار."
    if d["er"] < 1:
        return "⚡ برق کمه؛ یه نیروگاه بساز."
    if c["sat"] >= 70:
        return "😍 مردم ازت راضین!"
    if d["net"] > 0:
        return "📈 درآمدت مثبته؛ آفرین!"
    return "🌱 همه‌چی آرومه؛ یه قدم بزرگ‌تر بردار."


def dash(c):
    d = E.derive(c)
    pend = ""
    if c.get("pending"):
        pend = "\n\n📰 <b>خبرای تازه</b>\n" + "\n".join(c["pending"])
        c["pending"] = []
    warn = []
    if c["starving"]:
        warn.append("☠️ قحطی!")
    if c["treasury"] < 0:
        warn.append("🔻 بدهی")
    if c["sat"] < 15:
        warn.append("🔥 خطر کودتا!")
    if c["bank"]["loan"] > E.credit_limit(c) * 1.5:
        warn.append("🏛 بانک داره از خزانه برمی‌داره!")
    sh = c["shield_until"] - E.now()
    st = E.unrest_stage(c["unrest"])
    b = c["bank"]
    t = [greeting(c), "",
         f"{c.get('emblem', '🏛')} <b>{esc(c['name'])}</b> — {mood(c, d)}", "",
         f"🟩 خزانه <b>{n(c['treasury'])}</b> ({d['net']:+,.0f}/ساعت) · 🏦 {n(b['dep'])}" + (f" · 🔻 وام {n(b['loan'])}" if b["loan"] > 1 else ""),
         f"🟩 🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · 🔬 {n(c['tech'])} · ⚡ {c['fx'].get('PHX', 0):,.1f} زیرو",
         f"🟦 👥 {n(c['pop'])} · 😊 {bar(c['sat'], 5)} {c['sat']:.0f} · {st[2]} {st[1]}",
         f"🟦 🎓 {c['literacy']:.0f} · 🏥 {c['health']:.0f} · 🚓 {c['security']:.0f} · ⚡ {int(d['er'] * 100)}٪",
         f"🟥 🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🏆 {n(E.score(c))} · ⚔️ {c['wins']}/{c['losses']}"]
    t.append(f"🛡 سپر فعاله، {sh / 3600:.1f} ساعت دیگه" if sh > 0 else "🛡 سپر نداری («سپر» بنویس)")
    if warn:
        t.append("⚠️ " + " · ".join(warn))
    t.append(f"⚡ فرمان {int(E.orders(c))}/{E.orders_max(c)} · 🏞 {c.get('land', 5)} استان · 🏰 کاخ {E.lv(c, 'palace')}")
    busy = [f"{B[j['key']]['e'] if j['kind'] == 'b' else '⬆️'} {dur(j['end'] - E.now())}" for j in c["queue"]]
    busy += [f"{U[b['k']]['e']} {dur(b['end'] - E.now())}" for b in c["tq"][:3]]
    if busy:
        t.append("🏗 در حال انجام: " + " · ".join(busy))
    t += events.banner_lines()
    if c.get("dil"):
        t.append("📜 <b>یه رویداد منتظر تصمیم توئه!</b> (دکمه‌ی «رویداد»)")
    t.append(crown.line(c))
    nl = world.news_lines(1)
    if nl:
        t.append("📰 " + nl[0])
    text = "\n".join(t) + pend + "\n\n👇 هر بخشی رو بخوای از پایین بزن"
    rows = [[("🏗 ساختمان", "b"), ("💸 سیاست و بودجه", "p")],
            [("🪖 ارتش", "u"), ("⬆️ ارتقا نیرو", "g")],
            [("🏦 بانک", "k"), ("🏪 بازار", "t")],
            [("💱 ارز و توکن", "x"), ("🎖 ماموریت", "q")],
            [("⚔️ جنگ", "w"), ("🕵️ اطلاعات", "s")],
            [("🤝 اتحاد", "a"), ("🔬 پژوهش", "r")],
            [("🚨 ناآرامی", "o"), ("🏆 رتبه‌بندی", "top")],
            [("🏅 برترین‌ها", "bd"), ("🤝 دیپلماسی", "dp")],
            [("🎰 جعبه‌ی شانس", "lb"), ("🎁 دعوت دوست", "iv")],
            [("🎁 جایزه‌ی روزانه", "d"), ("🧳 کار", "wk")],
            [("📰 اخبار", "nw"), ("🏗 صف ساخت", "sq")],
            [("🗺 نقشه‌ی جهان", "mp"), ("👑 تاج امپراتوری", "cr")]]
    if c.get("dil"):
        rows.insert(0, [("📜 رویداد جدید؛ تصمیم بگیر!", "ev")])
    rows.append([("🛡 سپر", "sh"), ("🔄 بروزرسانی", "m")])
    if c["_id"] in config.ADMINS:
        rows.append([("🛠 پنل ادمین", "ad:home")])
    return text, kb(rows)


def s_work(c):
    left = 2 * 3600 - (E.now() - c["cd2"].get("work", 0))
    state = "✅ آماده‌ای، بزن بریم!" if left <= 0 else f"☕ {int(left // 60) + 1} دقیقه‌ی دیگه آماده‌ای"
    t = (f"🧳 <b>کار و تجارت</b>\nهر ۲ ساعت یه سفر تجاری و یه کیسه سکه 😊\n{state}\n"
         f"📈 {c['st'].get('works', 0)} بار کار کردی · 💰 {n(c['treasury'])}")
    if eco.newbie(c):
        t += "\n🌱 تازه‌کاری؛ درآمدت ۱٫۵ برابره!"
    return t, kb([[("🧳 برو سر کار", "wk:go")], BACK])


def s_daily(c):
    d = c["daily"]
    left = 20 * 3600 - (E.now() - d["last"])
    streak = d["streak"] if E.now() - d["last"] < 48 * 3600 else 0
    state = "✅ جایزه‌ات آماده‌ست!" if left <= 0 else f"⏳ {left / 3600:.1f} ساعت دیگه"
    t = (f"🎁 <b>جایزه‌ی روزانه</b>\nهر روز بیای بزرگ‌تر میشه؛ روز هفتم یه زیرو ⚡ هم داره\n"
         f"{state} · 🔥 {streak} روز پشت‌سرهم")
    if eco.newbie(c):
        t += "\n🌱 تا ۷ روز اول ۲ برابره!"
    return t, kb([[("🎁 دریافت جایزه", "d:go")], BACK])


def s_shield(c):
    cost, hours = config.SHIELD_PHX
    sh = c["shield_until"] - E.now()
    t = (f"🛡 <b>سپر</b>\nتا وقتی سپر داری کسی بهت حمله نمی‌کنه (حمله‌ی خودت به بازیکن، سپرت رو می‌شکنه).\n"
         f"الان: {'فعال، ' + format(sh / 3600, '.1f') + ' ساعت دیگه' if sh > 0 else 'سپر نداری'}\n"
         f"⚡ قیمت: {cost} زیرو برای {hours} ساعت · موجودی تو: {c['fx'].get('PHX', 0):,.1f}")
    return t, kb([[(f"🛡 خرید سپر · {cost} زیرو", "sh:go")], [("💱 خرید زیرو", "x")], BACK])


def queue_lines(c):
    out = []
    for j in c["queue"]:
        if j["kind"] == "b":
            out.append(f"{B[j['key']]['e']} {B[j['key']]['n']} → سطح {j['to']} · {dur(j['end'] - E.now())}")
        else:
            e, nm, _ = BRANCH[j["key"]]
            out.append(f"⬆️ نیروی {nm} {e} → سطح {j['to']} · {dur(j['end'] - E.now())}")
    for b in c["tq"]:
        out.append(f"🪖 {b['n']:,} {U[b['k']]['n']} · {dur(b['end'] - E.now())}")
    return out


def s_queue(c):
    lines = [f"🏗 <b>صف ساخت و آموزش</b>", f"کارگاه‌ها: {len(c['queue'])}/{E.slots(c)} (با ارتقای کاخ بیشتر میشه)", ""]
    rows = []
    for j in c["queue"]:
        cost = max(1, -(-int(j['end'] - E.now()) // config.SPEEDUP_SECS))
        nm = f"{B[j['key']]['e']} {B[j['key']]['n']}" if j["kind"] == "b" else f"⬆️ {BRANCH[j['key']][1]}"
        lines.append(f"{nm} → سطح {j['to']} · {dur(j['end'] - E.now())}")
        rows.append([(f"⚡ تسریع {nm} · {cost} زیرو", f"sq:sp:{j['id']}")])
    for b in c["tq"]:
        cost = max(1, -(-int(b['end'] - E.now()) // config.SPEEDUP_SECS))
        lines.append(f"🪖 {b['n']:,} {U[b['k']]['n']} · {dur(b['end'] - E.now())}")
        rows.append([(f"⚡ تسریع {U[b['k']]['e']}{b['n']} · {cost} زیرو", f"sq:sp:{b['id']}")])
    if not c["queue"] and not c["tq"]:
        lines.append("چیزی در حال ساخت یا آموزش نیست.")
    lines.append(f"\n⚡ موجودی زیرو: {c['fx'].get('PHX', 0):,.1f} · هر ۱ زیرو = {config.SPEEDUP_SECS // 60} دقیقه تسریع")
    return "\n".join(lines), kb(rows + [[("🏗 ساختمان", "b"), ("🪖 ارتش", "u")], BACK])


def s_build(c):
    cap = E.level_cap(c)
    lines = ["🏗 <b>ساختمان‌ها</b>", f"💰 {n(c['treasury'])} · 🏰 کاخ {E.lv(c, 'palace')} → سقف سطح ساختمان‌ها {cap} · کارگاه {len(c['queue'])}/{E.slots(c)}"]
    q = queue_lines(c)
    if q:
        lines += ["⏳ <b>در حال ساخت</b>"] + q
    lines.append("")
    btn = []
    for k, b in B.items():
        l = E.lv(c, k)
        lines.append(f"{b['e']} {b['n']} <b>{l}</b> — {b['d']}")
        mx = E.bmax(k)
        if l >= mx:
            cost = "MAX"
        elif k != "palace" and l >= cap:
            cost = "🏰"
        else:
            cost = f"{n(E.build_cost(k, l))} · {dur(E.build_secs(k, l))}"
        btn.append((f"{b['e']} {b['n']} ({l}) · {cost}", f"b:buy:{k}"))
    return "\n".join(lines)[:4000], kb([btn[i:i + 2] for i in range(0, len(btn), 2)] + [[("🏗 صف ساخت", "sq")], BACK])


def s_unrest(c):
    d = E.derive(c)
    st, name, emo = E.unrest_stage(c["unrest"])
    causes, relief = E.unrest_causes(c, d)
    lines = [f"🚨 <b>ناآرامی</b> · {emo} {name} · {bar(c['unrest'], inv=True)} {c['unrest']:.0f}"]
    if causes:
        lines.append("علت‌ها: " + " · ".join(f"{k} {v:.0f}" for k, v in sorted(causes, key=lambda x: -x[1])))
    else:
        lines.append("✅ مردم دلیلی برای اعتراض ندارن")
    lines.append(f"🛡 مهارکننده‌ها -{relief:.0f} · 📉 افت بهره‌وری {min(0.4, c['unrest'] * 0.004) * 100:.0f}٪ · 🗳 اصلاحات {c.get('reforms', 0)}")
    lines.append("💡 دکمه‌ها فقط موقتی آرومشون می‌کنن؛ ریشه‌ی علت‌ها رو حل کن.")
    rows = [[("🤝 مذاکره · 400", "o:do:talk"), (f"💵 یارانه · {n(c['pop'] * 0.05)}", "o:do:subsidy")],
            [(f"🍞 غذای رایگان · {n(c['pop'] * 0.03)}", "o:do:food"), ("📺 تبلیغات · 600", "o:do:media")],
            [("👮 سرکوب پلیسی", "o:do:crack"), ("🗳 اصلاحات · 1500+40🔬", "o:do:reform")]]
    return "\n".join(lines), kb(rows + [BACK])


def s_policy(c):
    d = E.derive(c)
    cs = d["costs"]
    base = E.tax_base(c)
    t = [f"💸 <b>سیاست و بودجه</b>",
         f"💰 مالیات <b>{n(d['revenue'])}</b> − بودجه <b>{n(d['spend'])}</b> − نگهداری <b>{n(d['upkeep'])}</b> = <b>{d['net']:+,.0f}</b> در ساعت",
         f"🧾 مالیات = {c['tax']}٪ × پایه‌ی {n(base)} (نصف تولید + {config.TAX_CAPITA} سکه به‌ازای هر نفر): جمعیت بیشتر = درآمد بیشتر حتی با نرخ کم",
         f"👥 جمعیت {n(c['pop'])} · 🏞 {c.get('land', config.LAND_START)} استان · مجموع بودجه {sum(c['budget'].values())}/{config.BUDGET_CAP} واحد", ""]
    rows = [[("➖", "p:tax:-5"), (f"مالیات {c['tax']}٪", "p:x"), ("➕", "p:tax:5")]]
    for k, nm in config.BUDGET_NAMES.items():
        pts = c["budget"].get(k, 0)
        t.append(f"{nm}: <b>{pts}</b> واحد × {E.budget_unit_cost(c, k):,.1f} = {cs[k]:,.0f}💰/ساعت · هزینه با <b>{config.BUDGET_FACTOR[k]}</b>")
        rows.append([("➖", f"p:bud:{k}:-5"), (f"{nm} {pts}", "p:x"), ("➕", f"p:bud:{k}:5")])
    t.append("\n🎓 آموزش→سواد · 🏥 سلامت→رشد جمعیت · 🚓 امنیت→آرامش · 🤲 رفاه→رضایت و کاهش ناآرامی · 🪖 نظامی→روحیه‌ی ارتش · 🛣 زیرساخت→بهره‌وری و سرعت لشکر")
    t.append("💡 آموزش، سلامت، امنیت و رفاه با جمعیت گرون میشن؛ نظامی و زیرساخت با تعداد استان‌ها (نه جمعیت)")
    return "\n".join(t), kb(rows + [BACK])


def s_units(c):
    cap = E.army_cap(c)
    lines = ["🪖 <b>ارتش</b>", f"ظرفیت: {E.army_size(c)} (+{E.queued_size(c)} در آموزش)/{cap} · ⚙️ {n(c['steel'])} · 💰 {n(c['treasury'])}"]
    lines += [f"🪖 {b['n']:,} {U[b['k']]['n']} · {dur(b['end'] - E.now())}" for b in c["tq"]]
    rows = []
    for br, title in (("land", "🪖 زمینی"), ("air", "✈️ هوایی"), ("sea", "🚢 دریایی")):
        lines.append(f"\n<b>{title}</b>")
        for k, u in U.items():
            if u["br"] != br:
                continue
            req = " ".join(f"{B[b]['n']}{lv}" for b, lv in u["req"].items())
            lines.append(f"{u['e']} {u['n']}: <b>{c['units'].get(k, 0)}</b> — {u['cost']}💰 {u['steel']}⚙️ · 🗡{u['atk']} 🛡{u['dfn']} · ظرفیت {u['size']} · سرعت {u['spd']}x" + (f" · نیاز: {req}" if req else ""))
            q = (50, 500) if u["cost"] <= 100 else (10, 50) if u["cost"] <= 500 else (1, 5)
            rows.append([(f"{u['e']} +{x}", f"u:buy:{k}:{x}") for x in q])
    lines.append("\n🚀 موشک ساختمان‌ها رو می‌زنه، 📡 پدافند رهگیری می‌کنه · 🥷 کماندو سریع، 💣 توپخانه ضدِ پیاده، 🛡 تانک سنگین زره‌دار، 🔱 ناوشکن و 🛳 ناو هواپیمابر ناوگان سنگین، 🛸 پهپاد ارزون و سریع، 🛩 بمب‌افکن ضربه‌ی هوایی")
    return "\n".join(lines)[:4000], kb(rows + [BACK])


def s_upgrade(c):
    lines = ["⬆️ <b>ارتقای نیروها</b> (هر سطح +۱۰٪ قدرت آن شاخه)", f"💰 {n(c['treasury'])} · ⚙️ {n(c['steel'])}", ""]
    rows = []
    for br, (e, nm, need) in BRANCH.items():
        l = c["upg"].get(br, 0)
        if l >= config.MAX_LEVEL:
            lines.append(f"{e} {nm}: سطح <b>MAX</b>")
            continue
        coin, steel = E.upg_cost(l)
        lines.append(f"{e} {nm}: سطح <b>{l}</b> → {l + 1} · {n(coin)}💰 {steel}⚙️ · ⏳ {dur(E.upg_secs(l))} · نیاز {B[need]['n']} {(l + 2) // 2}")
        rows.append([(f"{e} ارتقای {nm} → {l + 1}", f"g:up:{br}")])
    return "\n".join(lines), kb(rows + [BACK])


def s_research(c):
    lines = ["🔬 <b>پژوهش</b>", f"امتیاز: {n(c['tech'])} (دانشگاه سرعتش رو بالا می‌بره)", ""]
    rows = []
    for k, (e, nm, d) in TECH.items():
        l = c["techlv"][k]
        cost = 60 * (l + 1) ** 2
        lines.append(f"{e} {nm} <b>{l}</b> — {d}")
        rows.append([(f"{e} {nm} → {l + 1} · {n(cost)}", f"r:up:{k}")])
    return "\n".join(lines), kb(rows + [BACK])


def s_bank(c):
    b, lim = c["bank"], E.credit_limit(c)
    t = (f"🏦 <b>بانک مرکزی</b> · 💰 خزانه {n(c['treasury'])}\n"
         f"📥 سپرده <b>{n(b['dep'])}</b> · سود {E.RATE['dep'] * 100:.1f}٪ در روز (از غارت امنه)\n"
         f"🔻 وام <b>{n(b['loan'])}</b> · بهره {E.RATE['loan'] * 100:.1f}٪ در روز · سقف {n(lim)}\n"
         "💡 اگه وامت از ۱٫۵ برابر سقف بره، بانک از خزانه‌ت برمی‌داره.\n"
         "کلمه‌ها: <code>سپرده 5000</code> · <code>برداشت 2000</code> · <code>وام 3000</code> · <code>بازپرداخت همه</code>")
    rows = [[("📥 سپرده ۱٬۰۰۰", "k:dep:1000"), ("📥 سپرده ۵٬۰۰۰", "k:dep:5000")],
            [("📤 برداشت همه", "k:wd:all"), ("🏛 وام ۵٬۰۰۰", "k:loan:5000")],
            [("✅ پرداخت وام (همه)", "k:rep:all")]]
    return t, kb(rows + [BACK])


def s_trade(c):
    t = [f"🏪 <b>بازار</b> · 💰 {n(c['treasury'])} · 🌾 {n(c['food'])} · ⚙️ {n(c['steel'])}"]
    for k, (e, nm) in ITEMS.items():
        b, s = eco.prices(k)
        t.append(f"{e} {nm}: خرید {b:.2f} · فروش {s:.2f}")
    t.append("💡 قیمت‌ها با خرید و فروش بازیکن‌ها تکون می‌خوره. بازار آزاد: «آگهی» و «خرید آگهی»")
    rows = [[("🌾 خرید ۱۰۰۰", "t:buy:food:1000"), ("🌾 فروش ۱۰۰۰", "t:sell:food:1000")],
            [("⚙️ خرید ۵۰", "t:buy:steel:50"), ("⚙️ فروش ۵۰", "t:sell:steel:50")]]
    return "\n".join(t), kb(rows + [BACK])


def s_fx(c):
    t = ["💱 <b>بازار ارز و توکن</b>", f"💰 {n(c['treasury'])} · ارزش پرتفوی {n(eco.fx_value(c))}"]
    rows = []
    for sym, a in ASSETS.items():
        f = eco.WORLD["fx"][sym]
        t.append(f"{a['e']} <b>{config.sym_name(sym)}</b> {f['p']:,.2f} ({eco.fx_change(sym):+.1f}٪) {eco.spark(f['h'])} · داری {c['fx'].get(sym, 0):,.0f}")
        rows.append([(f"{config.sym_name(sym)} +1", f"x:b:{sym}:1"), (f"{config.sym_name(sym)} +10", f"x:b:{sym}:10"), (f"{config.sym_name(sym)} فروش همه", f"x:s:{sym}:all")])
    if eco.WORLD["news"]:
        t.append("\n📰 " + "\n📰 ".join(eco.WORLD["news"][-3:]))
    t.append(f"\n⚡ با {config.SHIELD_PHX[0]} زیرو می‌تونی «سپر» {config.SHIELD_PHX[1]} ساعته بخری · کارمزد {config.FX_FEE * 100:.0f}٪")
    return "\n".join(t), kb(rows + [BACK])


def s_missions(c):
    dl, wl = prog.status_lines(c)
    t = ["🎖 <b>ماموریت‌ها</b> (⬜ مانده · ✅ آماده · 🎖 تحویل‌شده)", "",
         f"📅 <b>روزانه</b> (امشب ریست میشه · همه رو بزنی {prog.rew_text(prog.DAILY_ALL)})"] + dl + [
         "", f"🗓 <b>هفتگی</b> (تا {dur(world.SEASON['wend'] - E.now())} دیگه · همه رو بزنی {prog.rew_text(prog.WEEKLY_ALL)})"] + wl + [
         "", "🏆 <b>دائمی</b>"] + eco.missions_text(c)
    return "\n".join(t)[:4000], kb([[("🎁 تحویل همه", "q:claim")], BACK])


async def s_spy(c):
    docs = await db.C.aggregate([{"$match": {"_id": {"$ne": c["_id"]}}}, {"$sample": {"size": 5}}]).to_list(5)
    t = (f"🕵️ <b>سازمان اطلاعات</b> (سطح {E.lv(c, 'intel')})\n"
         "هر عملیات ۵۰۰ سکه؛ اگه لو بری دشمن خبردار میشه 🤫")
    rows = [[(f"🎯 {d['name'][:20]}", f"s:pick:{d['_id']}")] for d in docs]
    return t, kb(rows + [[("🔄 لیست جدید", "s")], BACK])


def s_spy_ops(tid):
    return "چه عملیاتی؟", kb([[("🔍 جاسوسی", f"s:go:{tid}:scout")],
                              [("💣 خرابکاری", f"s:go:{tid}:sabotage")],
                              [("📡 سرقت فناوری", f"s:go:{tid}:steal")], [("🔙", "s")]])


async def active_war(aid):
    return await db.W.find_one({"active": True, "$or": [{"a": aid}, {"b": aid}]})


async def s_ally(c):
    aid = c.get("alliance")
    a = await db.A.find_one({"_id": aid}) if aid else None
    if not a:
        c["alliance"], c["ally_bonus"] = None, 0.0
        return ("🤝 <b>اتحاد</b> = یه گروه تلگرام.\nربات رو بیار توی گروهت و بنویس:\n"
                "<code>ساخت اتحاد نام</code>\nبقیه با نوشتن <code>پیوستن</code> عضو میشن.\n\n"
                "مزایا: بونوس بهره‌وری، دفاع مشترک و جنگ اتحادها."), kb([BACK])
    docs = await db.C.find({"_id": {"$in": a["members"]}}).to_list(ALLY_MAX_VIEW)
    docs.sort(key=E.score, reverse=True)
    lines = [f"🤝 <b>{esc(a['name'])}</b> · {len(a['members'])} عضو · بونوس +{int(c['ally_bonus'] * 100)}٪",
             f"🏦 بانک {n(a['bank'])} · برد {a.get('wins', 0)} · باخت {a.get('losses', 0)}", ""]
    for d in docs[:8]:
        lines.append(f"• {esc(d['name'])} — {E.score(d):,}")
    rows = [[("💰 اهدا ۱۰۰۰", "a:donate:1000"), ("💰 اهدا ۵۰۰۰", "a:donate:5000")]]
    w = await active_war(aid)
    if w:
        me, foe = ("a", "b") if w["a"] == aid else ("b", "a")
        fa = await db.A.find_one({"_id": w[foe]})
        left = max(0, w["end"] - E.now()) / 60
        lines.append(f"\n🔥 <b>جنگ با {esc(fa['name']) if fa else '؟'}</b>\n"
                     f"امتیاز {w['score'][me]} : {w['score'][foe]} · {left:.0f} دقیقه مانده")
        rows.append([("⚔️ ضربه به دشمن", "a:strike")])
    return "\n".join(lines), kb(rows + [BACK])


async def s_top(c, home=None):
    q = {"npc": {"$ne": True}}
    if home:
        q["home"] = home
    docs = await db.C.find(q).to_list(1000)
    docs.sort(key=E.score, reverse=True)
    rank = next((i + 1 for i, d in enumerate(docs) if d["_id"] == c["_id"]), "؟")
    lines = ["🏆 <b>قدرتمندترین کشورهای " + ("این گروه" if home else "جهان") + "</b>", ""]
    for i, d in enumerate(docs[:10]):
        lines.append(f"{i + 1}. {esc(d['name'])} — {E.score(d):,}")
    lines.append(f"\nرتبه‌ی تو: {rank}")
    return "\n".join(lines), kb([BACK])


# ------------------------------------------------------------------ اقدام‌های جنگی
ally_support = war.ally_support


async def do_strike(c):
    aid = c.get("alliance")
    if not aid:
        return "عضو اتحاد نیستی"
    w = await active_war(aid)
    if not w:
        return "اتحادت الان درگیر جنگ نیست"
    left = config.STRIKE_CD - (E.now() - c["last_strike"])
    if left > 0:
        return f"⏳ {int(left // 60) + 1} دقیقه‌ی دیگه"
    side = "a" if w["a"] == aid else "b"
    ea = await db.A.find_one({"_id": w["b"] if side == "a" else w["a"]})
    mem = list(ea["members"]) if ea else []
    random.shuffle(mem)
    e = None
    for uid in mem:
        e = await db.load(uid)
        if e:
            break
    if not e:
        return "هدفی پیدا نشد"
    if not E.spend_orders(c, 1):
        return f"⚡ فرمان کافی نیست؛ {dur(E.order_wait(c))} دیگه"
    r = E.battle(c, e, 0.5, await ally_support(e))
    if not r:
        return "ارتش تهاجمی نداری"
    c["last_strike"] = E.now()
    if r["win"]:
        pts, key = 10 + min(20, int(r["A"] / max(r["D"], 1) * 5)), f"score.{side}"
    else:
        pts, key = 4, f"score.{'b' if side == 'a' else 'a'}"
    await db.W.update_one({"_id": w["_id"]}, {"$inc": {key: pts}})
    await db.save(e)
    txt = report(r, c["name"], e["name"]) + f"\n\n🎖 {pts} امتیاز برای {'اتحاد تو' if r['win'] else 'دشمن'}"
    await notify(e["_id"], "🔥 <b>ضربه‌ی اتحاد دشمن!</b>\n" + txt)
    return txt


# ------------------------------------------------------------------ مسیریابی دکمه‌ها
async def route(c, p):
    import inspect
    t, toast, scr = p[0], None, None
    if t == "b" and len(p) > 2:
        toast = E.build(c, p[2])[1]
    elif t == "p" and len(p) > 2:
        toast = E.set_tax(c, int(p[2])) if p[1] == "tax" else E.set_budget(c, p[2], int(p[3]))
    elif t == "u" and len(p) > 3:
        toast = E.buy_unit(c, p[2], int(p[3]))[1]
    elif t == "g" and len(p) > 2:
        toast = E.upgrade(c, p[2])[1]
    elif t == "r" and len(p) > 2:
        toast = E.research(c, p[2])[1]
    elif t == "k" and len(p) > 2:
        b = c["bank"]
        mx = {"dep": c["treasury"], "wd": b["dep"], "loan": E.credit_limit(c) - b["loan"], "rep": b["loan"]}.get(p[1], 0)
        v = amount(p[2], mx)
        fn = {"dep": eco.bank_deposit, "wd": eco.bank_withdraw, "loan": eco.bank_borrow, "rep": eco.bank_repay}.get(p[1])
        toast = fn(c, v)[1] if fn and v else "ممکن نیست"
    elif t == "t" and len(p) > 3:
        v = amount(p[3])
        toast = (eco.global_buy if p[1] == "buy" else eco.global_sell)(c, p[2], v or 0)[1]
        await eco.save_world()
    elif t == "x" and len(p) > 3:
        v = amount(p[3], int(c["fx"].get(p[2], 0)))
        toast = (eco.fx_buy if p[1] == "b" else eco.fx_sell)(c, p[2], v or 0)[1]
        await eco.save_world()
    elif t == "q" and len(p) > 1:
        toast = eco.claim(c)[1]
    elif t == "sh":
        toast = eco.buy_shield(c)[1] if len(p) > 1 else None
    elif t == "d":
        toast = eco.daily(c)[1] if len(p) > 1 else None
    elif t == "wk":
        toast = eco.work(c)[1] if len(p) > 1 else None
    elif t == "o" and len(p) > 2:
        toast = E.calm(c, p[2])[1]
    elif t == "w":
        toast, scr = await war.route(c, p)
    elif t in ("iv", "lb", "ev"):
        toast, scr = await growth.route(c, p)
    elif t == "dp":
        toast, scr = await world.diplo_route(c, p)
    elif t == "bd":
        scr = await world.s_boards(c, p[1] if len(p) > 1 else "war", p[2] if len(p) > 2 else "w")
    elif t == "nw":
        scr = world.s_news(c)
    elif t == "cr":
        scr = await crown.screen(c)
    elif t == "sq":
        if len(p) > 2 and p[1] == "sp" and p[2].isdigit():
            toast = E.speedup(c, int(p[2]))[1]
    elif t == "s" and len(p) > 2:
        if p[1] == "pick":
            scr = s_spy_ops(int(p[2]))
        elif p[1] == "go":
            scr = (await do_spy(c, int(p[2]), p[3]), kb([[("🕵️ اطلاعات", "s")], BACK]))
    elif t == "a" and len(p) > 1:
        if p[1] == "strike":
            scr = (await do_strike(c), kb([[("🤝 اتحاد", "a")], BACK]))
        elif p[1] == "donate":
            amt = int(p[2])
            if c.get("alliance") and c["treasury"] >= amt:
                c["treasury"] -= amt
                await db.A.update_one({"_id": c["alliance"]}, {"$inc": {"bank": amt}})
                toast = f"🏦 {amt} سکه به بانک اتحاد رفت"
            else:
                toast = "ممکن نیست"
    elif t == "cl":                              # 🏕 استعمار
        import feats
        if len(p) > 1 and p[1] == "go":
            await geo.refresh(need=c["_id"])
            ok_, msg_ = E.colony_start(c, geo.free_cells())
            scr = await feats.s_colony(c, msg_)
        else:
            scr = await feats.s_colony(c)
    elif t == "pv":
        import feats
        scr = await feats.s_provinces(c)
    if scr is None:
        f = {"b": s_build, "p": s_policy, "u": s_units, "g": s_upgrade, "r": s_research, "t": s_trade,
             "k": s_bank, "x": s_fx, "q": s_missions, "w": s_war, "s": s_spy, "a": s_ally,
             "o": s_unrest, "top": s_top, "wk": s_work, "d": s_daily, "sh": s_shield, "sq": s_queue}.get(t, dash)
        scr = f(c)
        if inspect.isawaitable(scr):
            scr = await scr
    return toast, scr
