"""صفحه‌ها (منوی دکمه‌ای) و اقدام‌های جنگ/جاسوسی."""
import random
from datetime import datetime, timedelta, timezone

import config
import db
import eco
import engine as E
from config import ASSETS, B, BRANCH, ITEMS, TECH, U
from core import notify
from util import BACK, amount, bar, esc, kb, n

ALLY_MAX_VIEW = 40


def fmt_units(d):
    return " ".join(f"{U[k]['e']}{v}" for k, v in d.items() if v) or "—"


def report(r, an, dn):
    s = [f"{'🏆 پیروزی' if r['win'] else '💀 شکست'} — {esc(an)} ⚔️ {esc(dn)}",
         f"🗡 حمله {n(r['A'])} · 🛡 دفاع {n(r['D'])}"]
    if r["mis"]:
        s.append(f"🚀 {r['mis']} موشک · رهگیری {int(r['icpt'] * 100)}٪ · اصابت {r['hits']}")
    if r["destroyed"]:
        s.append("💥 تخریب: " + "، ".join(r["destroyed"]))
    s.append("☠️ تلفات مهاجم: " + fmt_units(r["la"]))
    s.append("☠️ تلفات مدافع: " + fmt_units(r["ld"]))
    if r["loot"]:
        lt = r["loot"]
        s.append(f"💰 غنیمت: {n(lt['t'])} سکه · {n(lt['f'])} غذا · {n(lt['s'])} فولاد")
    return "\n".join(s)


# ------------------------------------------------------------------ نمای فشرده (برای گروه)
def brief(c):
    d = E.derive(c)
    sh = c["shield_until"] - E.now()
    b = c["bank"]
    t = [f"🏛 <b>{esc(c['name'])}</b> · {esc(c['leader'])}",
         f"💰 {n(c['treasury'])} ({d['net']:+,.0f}/ساعت) · 🏦 {n(b['dep'])}" + (f" · 🔻وام {n(b['loan'])}" if b["loan"] > 1 else ""),
         f"👥 {n(c['pop'])} · 😊 {c['sat']:.0f} · {E.unrest_stage(c['unrest'])[2]} {c['unrest']:.0f}",
         f"🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · 🔥 {c['fx'].get('PHX', 0):,.1f} PHX",
         f"🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🏆 {n(E.score(c))}"]
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
    """یه جمله‌ی گرم درباره‌ی وضعیت فعلی کشور."""
    if c["starving"]:
        return "🍞 مردم گرسنه‌ان و چشمشون به توئه؛ زودتر یه فکری برای غذا بکن!"
    if c["treasury"] < 0:
        return "💸 خزانه منفیه، ولی نگران نباش؛ با یه کم برنامه‌ریزی درستش می‌کنیم."
    if c["unrest"] >= 50:
        return "🚨 مردم ناراحتن؛ یه سر به بخش ناآرامی بزن و دلشون رو به دست بیار."
    if d["er"] < 1:
        return "⚡ برق کم اومده؛ یه نیروگاه جدید کارتو راه میندازه."
    if c["sat"] >= 70:
        return "😍 مردم ازت راضی‌ان؛ کشورت داره می‌درخشه!"
    if d["net"] > 0:
        return "📈 درآمدت مثبته؛ آفرین، همین‌طوری ادامه بده!"
    return "🌱 کشورت آروم و پایداره؛ هر وقت خواستی یه قدم بزرگ‌تر بردار."


def dash(c):
    d = E.derive(c)
    pend = ""
    if c.get("pending"):
        pend = "\n\n📰 <b>تازه‌ترین خبرا</b>\n" + "\n".join(c["pending"])
        c["pending"] = []
    warn = []
    if c["starving"]:
        warn.append("☠️ قحطی!")
    if c["treasury"] < 0:
        warn.append("🔻 بدهی — ارتش فرار می‌کنه")
    if c["sat"] < 15:
        warn.append("🔥 خطر کودتا!")
    if c["bank"]["loan"] > E.credit_limit(c) * 1.5:
        warn.append("🏛 بانک مرکزی داره از خزانه برداشت می‌کنه!")
    sh = c["shield_until"] - E.now()
    st = E.unrest_stage(c["unrest"])
    b = c["bank"]
    t = [greeting(c), "",
         f"🏛 <b>{esc(c['name'])}</b> — {mood(c, d)}", "",
         "📊 <b>وضعیت کشور</b>",
         f"👥 جمعیت {n(c['pop'])}/{n(d['cap'])} · اشتغال {int(d['emp'] * 100)}٪",
         f"😊 رضایت {bar(c['sat'])} {c['sat']:.0f}",
         f"{st[2]} ناآرامی: {st[1]} ({c['unrest']:.0f})",
         f"🎓 سواد {c['literacy']:.0f} · 🏥 سلامت {c['health']:.0f} · 🚓 امنیت {c['security']:.0f} · ⚡ انرژی {int(d['er'] * 100)}٪", "",
         "💼 <b>موجودی</b>",
         f"💰 خزانه {n(c['treasury'])} (<b>{d['net']:+,.0f}</b> در ساعت) · GDP {n(d['gdp'])}",
         f"🏦 سپرده {n(b['dep'])}" + (f" · 🔻 وام {n(b['loan'])}" if b["loan"] > 1 else ""),
         f"🌾 غذا {n(c['food'])} · ⚙️ فولاد {n(c['steel'])} · 🔬 پژوهش {n(c['tech'])} · 🔥 {c['fx'].get('PHX', 0):,.1f} PHX", "",
         "⚔️ <b>قدرت نظامی</b>",
         f"🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🏆 امتیاز {n(E.score(c))} · برد {c['wins']} / باخت {c['losses']}"]
    t.append(f"🛡 سپر فعاله: {sh / 3600:.1f} ساعت دیگه" if sh > 0 else "🛡 سپر نداری؛ اگه نگرانی، از دکمه‌ی «سپر» بگیر")
    if warn:
        t.append("\n⚠️ " + " ".join(warn))
    text = "\n".join(t) + pend + "\n\n👇 هر بخشی رو بخوای از پایین انتخاب کن"
    rows = [[("🏗 ساختمان", "b"), ("💸 سیاست و بودجه", "p")],
            [("🪖 ارتش", "u"), ("⬆️ ارتقا نیرو", "g")],
            [("🏦 بانک", "k"), ("🏪 بازار", "t")],
            [("💱 ارز و توکن", "x"), ("🎖 ماموریت", "q")],
            [("⚔️ جنگ", "w"), ("🕵️ اطلاعات", "s")],
            [("🤝 اتحاد", "a"), ("🔬 پژوهش", "r")],
            [("🚨 ناآرامی", "o"), ("🏆 رتبه‌بندی", "top")],
            [("🎁 جایزه‌ی روزانه", "d"), ("🧳 کار", "wk")],
            [("🛡 سپر", "sh"), ("🔄 بروزرسانی", "m")]]
    if c["_id"] in config.ADMINS:
        rows.append([("🛠 پنل ادمین", "ad:home")])
    return text, kb(rows)


def s_work(c):
    left = 2 * 3600 - (E.now() - c["cd2"].get("work", 0))
    t = ["🧳 <b>کار و تجارت</b>", "",
         "یه سفر تجاری برو و برای کشورت سکه بیار؛ هر ۲ ساعت یه‌بار می‌تونی 😊",
         "✅ آماده‌ای! بزن بریم 🚀" if left <= 0 else f"☕ هنوز یه خرده خسته‌ای؛ {int(left // 60) + 1} دقیقه‌ی دیگه آماده‌ای",
         f"📈 تا حالا {c['st'].get('works', 0)} بار کار کردی · 💰 خزانه {n(c['treasury'])}"]
    if eco.newbie(c):
        t.append("🌱 چون تازه‌کاری، درآمدت ۱٫۵ برابره!")
    return "\n".join(t), kb([[("🧳 برو سر کار", "wk:go")], BACK])


def s_daily(c):
    d = c["daily"]
    left = 20 * 3600 - (E.now() - d["last"])
    streak = d["streak"] if E.now() - d["last"] < 48 * 3600 else 0
    t = ["🎁 <b>جایزه‌ی روزانه</b>", "",
         "هر روز بیای جایزه‌ت بزرگ‌تر میشه، و روز هفتم یه توکن PHX هم هدیه داری 🔥",
         "✅ جایزه‌ات آماده‌ست! بگیرش 🎉" if left <= 0 else f"⏳ جایزه‌ی بعدی {left / 3600:.1f} ساعت دیگه‌ست",
         f"🔥 پشت‌سرهم: {streak} روز"]
    if eco.newbie(c):
        t.append("🌱 تا ۷ روز اول، جایزه‌هات ۲ برابره!")
    return "\n".join(t), kb([[("🎁 دریافت جایزه", "d:go")], BACK])


def s_shield(c):
    cost, hours = config.SHIELD_PHX
    sh = c["shield_until"] - E.now()
    t = ["🛡 <b>سپر</b>", "",
         "تا وقتی سپر داری کسی نمی‌تونه بهت حمله کنه؛ ولی اگه خودت به بازیکنی حمله کنی، سپرت می‌شکنه.",
         f"🛡 الان: {'فعال، ' + format(sh / 3600, '.1f') + ' ساعت دیگه' if sh > 0 else 'سپر نداری'}",
         f"🔥 قیمت: {cost} توکن PHX برای {hours} ساعت · موجودی تو: {c['fx'].get('PHX', 0):,.1f}"]
    return "\n".join(t), kb([[(f"🛡 خرید سپر · {cost} PHX", "sh:go")], [("💱 خرید PHX", "x")], BACK])


def s_build(c):
    lines = ["🏗 <b>ساختمان‌ها</b>", f"💰 {n(c['treasury'])}", ""]
    btn = []
    for k, b in B.items():
        l = E.lv(c, k)
        lines.append(f"{b['e']} {b['n']} <b>{l}</b> — {b['d']}")
        cost = n(E.build_cost(k, l)) if l < config.MAX_LEVEL else "MAX"
        btn.append((f"{b['e']} {b['n']} ({l}) · {cost}", f"b:buy:{k}"))
    return "\n".join(lines), kb([btn[i:i + 2] for i in range(0, len(btn), 2)] + [BACK])


def s_unrest(c):
    d = E.derive(c)
    st, name, emo = E.unrest_stage(c["unrest"])
    causes, relief = E.unrest_causes(c, d)
    lines = ["🚨 <b>ناآرامی عمومی</b>", f"{emo} <b>{name}</b> · {bar(c['unrest'])} {c['unrest']:.0f}", ""]
    if causes:
        lines.append("<b>علل خشم مردم:</b>")
        lines += [f"{k}: +{v:.0f}" for k, v in sorted(causes, key=lambda x: -x[1])]
    else:
        lines.append("✅ علت جدی‌ای برای اعتراض نیست")
    lines.append(f"🛡 مهارکننده‌ها (امنیت + اصلاحات): -{relief:.0f}")
    lines.append(f"\n⚠️ اثر فعلی: {E.STAGE_FX[st]}")
    lines.append(f"📉 افت بهره‌وری: {min(0.4, c['unrest'] * 0.004) * 100:.0f}٪ · اصلاحات: {c.get('reforms', 0)}")
    lines.append("\nعلت‌ها رو ریشه‌ای حل کن (کار، غذا، مالیات)؛ این دکمه‌ها فقط موقتی آرومشون می‌کنن.")
    rows = [[("🤝 مذاکره · 400", "o:do:talk"), (f"💵 یارانه · {n(c['pop'] * 0.05)}", "o:do:subsidy")],
            [(f"🍞 غذای رایگان · {n(c['pop'] * 0.03)}", "o:do:food"), ("📺 تبلیغات · 600", "o:do:media")],
            [("👮 سرکوب پلیسی", "o:do:crack"), ("🗳 اصلاحات · 1500+40🔬", "o:do:reform")]]
    return "\n".join(lines), kb(rows + [BACK])


def s_policy(c):
    d = E.derive(c)
    names = {"edu": "🎓 آموزش", "health": "🏥 سلامت", "mil": "🪖 نظامی", "sec": "🚓 امنیت"}
    t = (f"💸 <b>سیاست‌گذاری</b>\n\nمالیات: {n(d['revenue'])}/ساعت\n"
         f"بودجه‌ها: -{n(d['spend'])}\nنگهداری: -{n(d['upkeep'])}\n"
         f"<b>خالص: {d['net']:+,.0f}</b>\n\n"
         f"مالیات بالا = پول بیشتر، رضایت کمتر.\n"
         f"بودجه‌ی کل {sum(c['budget'].values())}٪ از سقف ۷۰٪\n"
         f"🪖 بودجه نظامی = روحیه‌ی ارتش")
    rows = [[("➖", "p:tax:-5"), (f"مالیات {c['tax']}٪", "p:x"), ("➕", "p:tax:5")]]
    for k, nm in names.items():
        rows.append([("➖", f"p:bud:{k}:-5"), (f"{nm} {c['budget'][k]}٪", "p:x"), ("➕", f"p:bud:{k}:5")])
    return t, kb(rows + [BACK])


def s_units(c):
    cap = E.lv(c, "barracks") * 1500
    lines = ["🪖 <b>ارتش</b>", f"ظرفیت: {E.army_size(c)}/{cap} · ⚙️ {n(c['steel'])} · 💰 {n(c['treasury'])}", ""]
    rows = []
    for k, u in U.items():
        lines.append(f"{u['e']} {u['n']}: <b>{c['units'].get(k, 0)}</b> — {u['cost']}💰 {u['steel']}⚙️")
        q = (50, 500) if k == "inf" else (1, 5)
        rows.append([(f"{u['e']} +{x}", f"u:buy:{k}:{x}") for x in q])
    lines.append("\n🚀 موشک ساختمان‌ها رو می‌زنه، 📡 پدافند رهگیری می‌کنه، 🚢 ناو و 🤿 زیردریایی نیروی دریایی‌ان (بندر لازمه)")
    return "\n".join(lines), kb(rows + [BACK])


def s_upgrade(c):
    lines = ["⬆️ <b>ارتقای نیروها</b> (هر سطح +۱۰٪ قدرت آن شاخه)", f"💰 {n(c['treasury'])} · ⚙️ {n(c['steel'])}", ""]
    rows = []
    for br, (e, nm, need) in BRANCH.items():
        l = c["upg"].get(br, 0)
        if l >= config.MAX_LEVEL:
            lines.append(f"{e} {nm}: سطح <b>MAX</b>")
            continue
        coin, steel = E.upg_cost(l)
        lines.append(f"{e} {nm}: سطح <b>{l}</b> → {l + 1} · {n(coin)}💰 {steel}⚙️ · نیاز {B[need]['n']} {(l + 2) // 2}")
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
    t = (f"🏦 <b>بانک مرکزی</b>\n💰 خزانه {n(c['treasury'])}\n\n"
         f"📥 سپرده: <b>{n(b['dep'])}</b> (سود {E.RATE['dep'] * 100:.1f}٪ در هر روز بازی · از غارت امنه)\n"
         f"🔻 وام: <b>{n(b['loan'])}</b> (بهره {E.RATE['loan'] * 100:.1f}٪ در روز بازی)\n"
         f"📊 سقف اعتبار: {n(lim)} · نرخ پایه‌ی بانک مرکزی {eco.WORLD['rate'] * 100:.1f}٪\n\n"
         "نرخ‌ها با نسبت وام به سپرده‌ی کل دنیا عوض میشن. اگه وامت از ۱٫۵ برابر سقف بره، بانک از خزانه‌ت برداشت اجباری می‌کنه.\n"
         "با کلمه هم می‌تونی: «سپرده 5000» · «برداشت 2000» · «وام 3000» · «بازپرداخت همه»")
    rows = [[("📥 سپرده ۱٬۰۰۰", "k:dep:1000"), ("📥 سپرده ۵٬۰۰۰", "k:dep:5000")],
            [("📤 برداشت همه", "k:wd:all"), ("🏛 وام ۵٬۰۰۰", "k:loan:5000")],
            [("✅ پرداخت وام (همه)", "k:rep:all")]]
    return t, kb(rows + [BACK])


def s_trade(c):
    t = [f"🏪 <b>بازار</b>\n💰 {n(c['treasury'])} · 🌾 {n(c['food'])} · ⚙️ {n(c['steel'])}\n"]
    for k, (e, nm) in ITEMS.items():
        b, s = eco.prices(k)
        t.append(f"{e} {nm}: خرید {b:.2f} · فروش {s:.2f} (هر واحد)")
    t.append("\nقیمت‌ها با خرید و فروش همه‌ی بازیکن‌ها بالا و پایین میشه.\nبازار آزاد بین بازیکن‌ها: «بازار» ، «آگهی» ، «خرید آگهی»")
    rows = [[("🌾 خرید ۱۰۰۰", "t:buy:food:1000"), ("🌾 فروش ۱۰۰۰", "t:sell:food:1000")],
            [("⚙️ خرید ۵۰", "t:buy:steel:50"), ("⚙️ فروش ۵۰", "t:sell:steel:50")]]
    return "\n".join(t), kb(rows + [BACK])


def s_fx(c):
    t = ["💱 <b>بازار ارز و توکن</b>", f"💰 {n(c['treasury'])} · ارزش پرتفوی {n(eco.fx_value(c))}", ""]
    rows = []
    for sym, a in ASSETS.items():
        f = eco.WORLD["fx"][sym]
        t.append(f"{a['e']} <b>{sym}</b> {f['p']:,.2f} ({eco.fx_change(sym):+.1f}٪) {eco.spark(f['h'])}\n   داری: {c['fx'].get(sym, 0):,.0f}")
        rows.append([(f"{sym} +1", f"x:b:{sym}:1"), (f"{sym} +10", f"x:b:{sym}:10"), (f"{sym} فروش همه", f"x:s:{sym}:all")])
    if eco.WORLD["news"]:
        t.append("\n📰 " + "\n📰 ".join(eco.WORLD["news"][-3:]))
    t.append(f"\n🔥 PHX توکن ویژه‌ی EMPIRE ZERO: با {config.SHIELD_PHX[0]} تا ازش، با «سپر» یه سپر {config.SHIELD_PHX[1]} ساعته می‌خری. کارمزد {config.FX_FEE * 100:.0f}٪")
    return "\n".join(t), kb(rows + [BACK])


def s_missions(c):
    t = ["🎖 <b>ماموریت‌ها</b> (⬜ مانده · ✅ آماده‌ی تحویل · 🎖 تحویل‌شده)", ""] + eco.missions_text(c)
    return "\n".join(t), kb([[("🎁 تحویل همه", "q:claim")], BACK])


def npc_lines(docs):
    out = []
    for d in docs:
        idx = -d["_id"]
        out.append(f"{idx}. {esc(d['name'])} · {'⭐' * d['tier']} · دفاع ~{n(E.defense_power(d))} · جایزه {n(d['bounty'])}💰")
    return out


async def s_war(c):
    now = E.now()
    npcs = await db.C.find({"npc": True}).sort("_id", -1).to_list(20)
    docs = await db.C.aggregate([{"$match": {"_id": {"$ne": c["_id"]}, "npc": {"$ne": True}, "shield_until": {"$lt": now}}},
                                 {"$sample": {"size": 5}}]).to_list(5)
    docs = [d for d in docs if not (c.get("alliance") and d.get("alliance") == c["alliance"])]
    sh = c["shield_until"] - now
    t = ["⚔️ <b>جنگ</b>", f"🗡 {n(E.attack_power(c))} · 🛡 {n(E.defense_power(c))} · 🚀 {c['units'].get('missile', 0)}"]
    if sh > 0:
        t.append(f"🛡 سپر فعال ({sh / 3600:.1f}h) — حمله به بازیکن سپرت رو می‌شکنه (حمله به NPC نمی‌شکنه)")
    t.append("\n🌍 <b>کشورهای جهان (NPC)</b>")
    t += npc_lines(npcs)
    t.append("\nهدف بازیکن‌های بدون سپر:" if docs else "\nبازیکن بدون سپری پیدا نشد.")
    rows = [[(f"🌍 {d['name'][:14]} {'⭐' * d['tier']}", f"w:pick:{d['_id']}")] for d in npcs]
    rows += [[(f"⚔️ {d['name'][:16]} · دفاع ~{n(E.defense_power(d) * random.uniform(.8, 1.2))}", f"w:pick:{d['_id']}")] for d in docs]
    return "\n".join(t), kb(rows + [[("🔄 لیست جدید", "w")], BACK])


async def s_pick(c, tid):
    t = await db.C.find_one({"_id": tid})
    if not t:
        return "هدف پیدا نشد", kb([BACK])
    est = E.defense_power(t) * random.uniform(.8, 1.2)
    text = (f"🎯 <b>{esc(t['name'])}</b>\nدفاع تخمینی ~{n(est)}\n"
            f"قدرت حمله‌ی تو: {n(E.attack_power(c))} · 🚀 {c['units'].get('missile', 0)}\n\nچند درصد ارتش؟")
    return text, kb([[(f"{p}٪", f"w:go:{tid}:{p}") for p in (30, 60, 100)], [("🔙", "w")]])


async def s_spy(c):
    docs = await db.C.aggregate([{"$match": {"_id": {"$ne": c["_id"]}}}, {"$sample": {"size": 5}}]).to_list(5)
    t = (f"🕵️ <b>سازمان اطلاعات</b> (سطح {E.lv(c, 'intel')})\n"
         "هر عملیات ۵۰۰ سکه. شانس موفقیت با سطح اطلاعات و امنیت هدف عوض میشه.\n"
         "اگر لو بری، دشمن خبردار میشه.")
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
        return ("🤝 <b>اتحاد</b>\n\nاتحاد = یک گروه تلگرام.\nربات رو توی گروهت اضافه کن و بزن:\n"
                "<code>ساخت اتحاد نام</code>\nبقیه با نوشتن <code>پیوستن</code> عضو میشن.\n\n"
                "مزایا: بونوس بهره‌وری، دفاع مشترک، جنگ اتحاد با اتحاد."), kb([BACK])
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
                tot += E.defense_power(m)
    return tot * 0.1


async def do_attack(c, tid, pct):
    t = await db.load(tid)
    if not t or t["_id"] == c["_id"]:
        return "هدف پیدا نشد"
    npc = bool(t.get("npc"))
    if npc:
        left = config.NPC_CD - (E.now() - c["npc_cd"].get(str(tid), 0))
        if left > 0:
            return f"⏳ ارتش این کشور هنوز بازسازی نشده؛ {int(left // 60) + 1} دقیقه‌ی دیگه"
    else:
        if t["shield_until"] > E.now():
            return "🛡 این کشور سپر داره"
        if c.get("alliance") and t.get("alliance") == c["alliance"]:
            return "🤝 هم‌پیمانته"
    r = E.battle(c, t, pct / 100, 0.0 if npc else await ally_support(t))
    if not r:
        return "ارتش تهاجمی نداری"
    extra = ""
    if npc:
        c["npc_cd"][str(tid)] = E.now()
        if r["win"]:
            c["treasury"] += t["bounty"]
            c["st"]["npc_wins"] = c["st"].get("npc_wins", 0) + 1
            extra = f"\n🎖 غرامت جنگی: {n(t['bounty'])} سکه"
            if random.random() < 0.10 * t["tier"]:
                c["fx"]["PHX"] = c["fx"].get("PHX", 0) + 1
                extra += " · +1 🔥PHX"
    else:
        c["shield_until"] = 0.0
    await db.save(t)
    txt = report(r, c["name"], t["name"]) + extra
    if not npc:
        await notify(tid, "🚨 <b>به کشورت حمله شد!</b>\n" + txt)
    return txt


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


async def do_spy(c, tid, op):
    t = await db.load(tid)
    if not t:
        return "هدف پیدا نشد"
    ok, txt, caught = E.spy(c, t, op)
    if ok and op != "scout":
        await db.save(t)
        await notify(tid, "🚨 کشورت هدف خرابکاری/سرقت اطلاعاتی قرار گرفت!")
    if caught:
        await notify(tid, f"🕵️ عوامل کشور «{esc(c['name'])}» در خاکت دستگیر شدند!")
    return txt


# ------------------------------------------------------------------ مسیریابی دکمه‌ها
async def route(c, p):
    import inspect
    t, toast, scr = p[0], None, None
    back_war = kb([[("⚔️ جنگ", "w")], BACK])
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
    elif t == "w" and len(p) > 2:
        if p[1] == "pick":
            scr = await s_pick(c, int(p[2]))
        elif p[1] == "go":
            scr = (await do_attack(c, int(p[2]), int(p[3])), back_war)
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
    if scr is None:
        f = {"b": s_build, "p": s_policy, "u": s_units, "g": s_upgrade, "r": s_research, "t": s_trade,
             "k": s_bank, "x": s_fx, "q": s_missions, "w": s_war, "s": s_spy, "a": s_ally,
             "o": s_unrest, "top": s_top, "wk": s_work, "d": s_daily, "sh": s_shield}.get(t, dash)
        scr = f(c)
        if inspect.isawaitable(scr):
            scr = await scr
    return toast, scr
