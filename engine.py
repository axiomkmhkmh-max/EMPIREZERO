import math
import random
import time

import config
from config import B, U, TECH, MAX_LEVEL, SHIELD_NEW_H, SHIELD_LOSS_H, BRANCH

ATK = ("inf", "tank", "jet", "ship", "sub")

# نرخ‌های بانک مرکزی (درصد در هر روز بازی) - world_loop مقدارشون رو بروز می‌کنه
RATE = {"dep": 0.01, "loan": 0.05}


def now():
    return time.time()


def lv(c, k):
    return c["buildings"].get(k, 0)


def army_size(c):
    return sum(c["units"].get(k, 0) * U[k]["size"] for k in U)


def defaults(c):
    """فیلدهای جدید رو روی کشورهای قدیمی هم می‌گذاره (مهاجرت بی‌صدا)."""
    for k, v in (("unrest", 15.0), ("stage", 0), ("reforms", 0), ("cd", {}),
                 ("upg", {"land": 0, "air": 0, "sea": 0}), ("bank", {"dep": 0.0, "loan": 0.0}),
                 ("fx", {}), ("fxcost", {}), ("st", {}), ("emblem", "🏛"), ("done", []), ("npc_cd", {}),
                 ("daily", {"last": 0.0, "streak": 0}), ("cd2", {}), ("home", None)):
        if k not in c:
            c[k] = v.copy() if isinstance(v, (dict, list)) else v
    for k in TECH:
        c["techlv"].setdefault(k, 0)
    for k in U:
        c["units"].setdefault(k, 0)
    return c


def new_country(uid, name, leader, doctrine="bal"):
    t = now()
    st = config.STARTER
    c = {
        "_id": uid, "name": name, "leader": leader, "created": t, "doctrine": doctrine,
        "treasury": 3000.0, "pop": 10000.0, "food": st["food"], "steel": st["steel"],
        "sat": 40.0, "literacy": 20.0, "health": 40.0, "security": 30.0, "weariness": 0.0,
        "tax": 25, "budget": {"edu": 8, "health": 8, "mil": 2, "sec": 4},
        "buildings": {"farm": 2, "market": 1, "school": 1, "power": 1},
        "units": {k: (100 if k == "inf" else 0) for k in U},
        "tech": 0.0, "techlv": {k: 0 for k in TECH},
        "alliance": None, "ally_bonus": 0.0,
        "shield_until": t + st["shield_h"] * 3600, "last_tick": t, "last_strike": 0.0,
        "wins": 0, "losses": 0, "gdp": 0.0, "net": 0.0, "starving": False,
        "pending": [], "drought_until": 0.0,
    }
    defaults(c)
    c["fx"]["PHX"] = st["phx"]
    c["fxcost"]["PHX"] = 0.0
    if doctrine == "eco":
        c["treasury"] = 8000.0
        c["buildings"].update(farm=3, market=2)
    elif doctrine == "mil":
        c["treasury"] = 5500.0
        c["steel"] += 120
        c["buildings"].update(police=1, barracks=1)
        c["units"]["inf"] = 250
    else:
        c["treasury"] = 6500.0
        c["buildings"].update(police=1)
    return c


# ---------------------------------------------------------------- اقتصاد
def energy(c):
    sup = lv(c, "power") * 120
    dem = sum(lv(c, k) * b["en"] for k, b in B.items())
    return sup, dem, (1.0 if dem <= 0 else min(1.0, sup / dem))


def capacity(c):
    return 12000 + 5000 * lv(c, "infra") + 800 * sum(v for k, v in c["buildings"].items() if k != "infra")


def derive(c):
    jobs = sum(lv(c, k) * b["jobs"] for k, b in B.items())
    workers = max(0.0, c["pop"] * 0.6 - army_size(c))
    sup, dem, er = energy(c)
    lit, hp = c["literacy"] / 100, c["health"] / 100
    prod = ((0.6 + 0.4 * lit) * (0.7 + 0.3 * hp) * (1 + 0.1 * lv(c, "infra")) * (0.6 + 0.4 * er)
            * (0.6 + 0.4 * c["sat"] / 100) * (1 + 0.06 * c["techlv"]["eco"])
            * (1 + 0.06 * lv(c, "market")) * (1 + c.get("ally_bonus", 0))
            * (1 - min(0.4, c.get("unrest", 15.0) * 0.004)))
    formal = min(jobs, workers)
    informal = max(0.0, workers - formal) * 0.3
    gdp = formal * 2.5 * prod + informal * 0.2
    emp = (formal + informal) / workers if workers > 0 else 1.0
    revenue = gdp * c["tax"] / 100
    spend = revenue * sum(c["budget"].values()) / 100
    upkeep = (sum(lv(c, k) * b["up"] for k, b in B.items())
              + sum(c["units"].get(k, 0) * u["up"] for k, u in U.items()))
    return dict(jobs=jobs, workers=workers, er=er, sup=sup, dem=dem, prod=prod, gdp=gdp, emp=emp,
                revenue=revenue, spend=spend, upkeep=upkeep, net=revenue - spend - upkeep,
                cap=capacity(c))


def approach(cur, tgt, rate, dt):
    return cur + (tgt - cur) * min(1.0, rate * dt)


def random_event(c, d):
    keys = ["drought", "corruption", "mine", "protest", "epidemic", "boom", "scholars", "festival"]
    w = [1, 1, 1, 2 if c["sat"] < 50 else 0.5, 1, 1, 1, 1]
    k = random.choices(keys, weights=w)[0]
    if k == "drought":
        c["drought_until"] = now() + 12 * 3600
        return "🌵 خشکسالی! تولید غذا ۱۲ ساعت ۴۰٪ کمتر شد"
    if k == "corruption":
        loss = max(0, c["treasury"]) * 0.06
        c["treasury"] -= loss
        return f"🕳 رسوایی فساد مالی: {loss:,.0f} سکه از خزانه ناپدید شد"
    if k == "mine":
        c["steel"] += 120
        return "⛏ معدن جدید کشف شد: +۱۲۰ فولاد"
    if k == "protest":
        c["sat"] -= 8
        return "✊ اعتراضات خیابانی: رضایت ۸ واحد افت کرد"
    if k == "epidemic":
        c["health"] -= 15
        c["pop"] *= 0.99
        return "🦠 اپیدمی! سلامت ۱۵ واحد افت کرد و ۱٪ جمعیت از دست رفت"
    if k == "boom":
        gain = max(0, d["revenue"]) * 6
        c["treasury"] += gain
        return f"📈 رونق صادرات: {gain:,.0f} سکه درآمد اضافه"
    if k == "scholars":
        c["tech"] += 40
        return "🎓 بازگشت نخبگان: +۴۰ امتیاز پژوهش"
    c["sat"] += 6
    return "🎉 جشن ملی: رضایت مردم +۶"


# ---------------------------------------------------------------- ناآرامی
STAGES = [("آرام", "🟢"), ("اعتراض", "🟡"), ("تظاهرات گسترده", "🟠"), ("اغتشاش و شورش", "🔴"), ("قیام مسلحانه", "🏴")]
STAGE_FX = ["هیچ", "کمی افت تولید", "اعتصاب: ۵٪ درآمد مالیاتی از دست میره",
            "شورشیان ساختمان آتش می‌زنند، غارت می‌کنند و جمعیت کم میشه",
            "قیام: هر لحظه ممکنه دولت سقوط کنه"]
STAGE_UP = {1: "🟡 مردم به خیابان آمدند: اعتراضات مسالمت‌آمیز آغاز شد",
            2: "🟠 تظاهرات گسترده! کارگران اعتصاب کردند و درآمد مالیاتی افت کرد",
            3: "🔴 اغتشاش! شورشیان به اماکن عمومی و انبارها حمله می‌کنند",
            4: "🏴 قیام مسلحانه! دولت در آستانه‌ی سقوط است"}


def unrest_stage(u):
    i = 0 if u < 25 else 1 if u < 50 else 2 if u < 70 else 3 if u < 90 else 4
    return i, STAGES[i][0], STAGES[i][1]


def unrest_causes(c, d):
    causes = [
        ("🚷 بیکاری", (1 - d["emp"]) * 40),
        ("🍞 قحطی / کمبود غذا", 25 if c["starving"] else (8 if c["food"] < c["pop"] * 0.06 else 0)),
        ("💸 مالیات سنگین", max(0, c["tax"] - 30) * 1.2),
        ("🔻 بدهی و ورشکستگی", 15 if c["treasury"] < 0 else 0),
        ("⚡ خاموشی", (1 - d["er"]) * 15),
        ("😠 نارضایتی عمومی", max(0, 50 - c["sat"]) * 0.5),
        ("🪖 جنگ‌خستگی", min(40, c["weariness"]) * 0.5),
    ]
    relief = c["security"] * 0.15 + 2 * min(5, c.get("reforms", 0))
    return [(k, v) for k, v in causes if v > 0.5], relief


def damage_building(c):
    pool = [k for k, v in c["buildings"].items() if v > 0]
    if not pool:
        return None
    k = random.choice(pool)
    c["buildings"][k] -= 1
    return B[k]["n"]


def riot_incident(c):
    r = random.random()
    if r < 0.4:
        nm = damage_building(c)
        if nm:
            return f"🔥 شورشیان {nm} را به آتش کشیدند (سطح -۱)"
    if r < 0.7:
        loot = max(0, c["treasury"]) * 0.03
        c["treasury"] -= loot
        return f"🏴 غارت بانک‌ها و مغازه‌ها: {loot:,.0f} سکه"
    if r < 0.9:
        c["food"] *= 0.9
        return "🛒 انبارهای غذا غارت شد (۱۰٪ ذخیره)"
    c["units"]["inf"] = int(c["units"].get("inf", 0) * 0.97)
    return "⚔️ درگیری خونین با نیروهای امنیتی: تلفات پیاده‌نظام"


def uprising(c):
    if c["treasury"] > 0:
        c["treasury"] *= 0.7
    for k in c["units"]:
        c["units"][k] = int(c["units"][k] * 0.75)
    lost = [x for x in (damage_building(c), damage_building(c)) if x]
    c["unrest"], c["sat"] = 55.0, 25.0
    return "🏴 قیام سراسری! ۳۰٪ خزانه، ۲۵٪ ارتش و ساختمان‌ها (" + "، ".join(lost) + ") از دست رفت"


def credit_limit(c):
    return int(max(3000, c.get("gdp", 0) * 10))


def bank_step(c, dt):
    b = c.setdefault("bank", {"dep": 0.0, "loan": 0.0})
    if b["dep"] > 0:
        b["dep"] += min(b["dep"], config.DEP_INT_CAP) * RATE["dep"] * dt / 24
    if b["loan"] > 0:
        b["loan"] += b["loan"] * RATE["loan"] * dt / 24
        # وام از سقف خیلی بالاتر رفته: بانک مرکزی از خزانه برداشت اجباری می‌کنه
        if b["loan"] > credit_limit(c) * 1.5 and c["treasury"] > 0:
            take = min(c["treasury"], b["loan"]) * min(0.5, 0.05 * dt)
            c["treasury"] -= take
            b["loan"] -= take
            c["sat"] = max(0.0, c["sat"] - 0.3 * dt)


def _step(c, dt):
    ev = []
    d = derive(c)
    c["treasury"] += d["net"] * dt
    c["gdp"], c["net"] = d["gdp"], d["net"]
    lit = c["literacy"] / 100
    bank_step(c, dt)

    # غذا
    weather = 0.6 if c.get("drought_until", 0) > now() else 1.0
    c["food"] += (lv(c, "farm") * 120 * (0.6 + 0.4 * lit) * weather - c["pop"] * 0.01) * dt
    c["starving"] = False
    if c["food"] < 0:
        c["food"], c["starving"] = 0.0, True
        c["pop"] *= 1 - 0.01 * dt

    c["steel"] += lv(c, "factory") * 40 * d["er"] * dt
    c["tech"] += (1 + 8 * lv(c, "university")) * (0.3 + lit) * dt

    # شاخص‌های اجتماعی
    bd = c["budget"]
    c["literacy"] = approach(c["literacy"], min(100, 15 + 10 * lv(c, "school") + 8 * lv(c, "university") + bd["edu"]), 0.03, dt)
    c["health"] = approach(c["health"], min(100, 20 + 12 * lv(c, "hospital") + bd["health"]), 0.05, dt)
    c["security"] = approach(c["security"], min(100, 20 + 12 * lv(c, "police") + bd["sec"]), 0.06, dt)
    c["weariness"] = max(0.0, c["weariness"] - 2 * dt)

    # ناآرامی
    causes, relief = unrest_causes(c, d)
    tgt = max(0.0, sum(v for _, v in causes) - relief)
    c["unrest"] = max(0.0, min(100.0, approach(c.get("unrest", 15.0), tgt, 0.2, dt)))

    # رضایت مردم
    tax = c["tax"]
    target = (15 + 28 * d["emp"] + 0.18 * c["health"] + 0.14 * c["literacy"] + 0.14 * c["security"]
              - max(0, tax - 25) * 1.1 + max(0, 25 - tax) * 0.4 - min(40, c["weariness"])
              - (25 if c["starving"] else 0) - (15 if c["treasury"] < 0 else 0) - c["unrest"] * 0.15)
    c["sat"] = approach(c["sat"], max(0, min(100, target)), 0.15, dt)

    # اثرات مرحله‌ی ناآرامی
    st = unrest_stage(c["unrest"])[0]
    old = c.get("stage", 0)
    if st > old:
        ev.append(STAGE_UP[st])
    elif st < old:
        ev.append("🟢 آرامش به خیابان‌ها برگشت" if st == 0 else f"🕊 ناآرامی فروکش کرد ({STAGES[st][0]})")
    c["stage"] = st
    if st >= 2:
        c["treasury"] -= max(0, d["revenue"]) * 0.05 * dt
    if st >= 3:
        c["pop"] *= 1 - 0.002 * dt
        c["sat"] -= 1.0 * dt
        if random.random() < min(0.9, 0.5 * dt):
            ev.append(riot_incident(c))
    if st >= 4 and random.random() < min(0.9, 0.3 * dt):
        ev.append(uprising(c))

    # جمعیت
    cap = d["cap"]
    if c["sat"] < 20:
        c["pop"] *= 1 - 0.003 * dt
    elif not c["starving"]:
        c["pop"] += c["pop"] * 0.004 * dt * (0.5 + c["health"] / 100) * max(0.0, 1 - c["pop"] / cap)
    if c["pop"] > cap:
        c["pop"] -= (c["pop"] - cap) * 0.02 * dt

    # بدهی
    if c["treasury"] < 0:
        c["treasury"] *= 1 + 0.005 * dt
        for k in c["units"]:
            c["units"][k] = int(c["units"][k] * (1 - 0.01 * dt))

    # کودتا
    if c["sat"] < 12 and random.random() < min(0.9, 0.15 * dt):
        if c["treasury"] > 0:
            c["treasury"] *= 0.7
        for k in c["units"]:
            c["units"][k] = int(c["units"][k] * 0.8)
        c["sat"] = 28.0
        ev.append("🔥 کودتا! ۳۰٪ خزانه و ۲۰٪ ارتش از دست رفت")

    if random.random() < min(0.9, 0.05 * dt):
        ev.append(random_event(c, d))

    for k in ("sat", "literacy", "health", "security"):
        c[k] = max(0.0, min(100.0, c[k]))
    return ev


def tick(c, dt):
    steps = max(1, math.ceil(dt))
    h = dt / steps
    ev = []
    for _ in range(steps):
        ev += _step(c, h)
    c["pending"] = (c.get("pending", []) + ev)[-8:]
    return ev


# ---------------------------------------------------------------- اقدام‌ها
def build_cost(k, l):
    return int(B[k]["cost"] * 1.55 ** l)


def build(c, k):
    if k not in B:
        return False, "؟"
    l = lv(c, k)
    if l >= MAX_LEVEL:
        return False, "حداکثر سطح"
    for r, rl in B[k]["req"].items():
        if lv(c, r) < rl:
            return False, f"نیاز: {B[r]['n']} سطح {rl}"
    cost = build_cost(k, l)
    if c["treasury"] < cost:
        return False, "💸 پول کافی نیست"
    c["treasury"] -= cost
    c["buildings"][k] = l + 1
    return True, f"✅ {B[k]['n']} → سطح {l + 1}"


def buy_unit(c, k, n):
    if k not in U or n <= 0:
        return False, "؟"
    u = U[k]
    for r, rl in u["req"].items():
        if lv(c, r) < rl:
            return False, f"نیاز: {B[r]['n']} سطح {rl}"
    if army_size(c) + n * u["size"] > lv(c, "barracks") * 1500:
        return False, "🏕 ظرفیت پادگان کافی نیست"
    if c["treasury"] < u["cost"] * n:
        return False, "💸 پول کافی نیست"
    if c["steel"] < u["steel"] * n:
        return False, "⚙️ فولاد کافی نیست"
    c["treasury"] -= u["cost"] * n
    c["steel"] -= u["steel"] * n
    c["units"][k] = c["units"].get(k, 0) + n
    return True, f"✅ {n} {u['n']} آماده شد"


def research(c, k):
    if k not in TECH:
        return False, "؟"
    l = c["techlv"][k]
    cost = 60 * (l + 1) ** 2
    if l >= 10:
        return False, "حداکثر سطح"
    if c["tech"] < cost:
        return False, f"🔬 امتیاز کافی نیست ({cost:,})"
    c["tech"] -= cost
    c["techlv"][k] = l + 1
    return True, f"✅ فناوری {TECH[k][1]} → سطح {l + 1}"


def trade(c, k):
    if k == "buyfood":
        if c["treasury"] < 1500:
            return False, "💸 پول کافی نیست"
        c["treasury"] -= 1500
        c["food"] += 1000
        return True, "🌾 +۱۰۰۰ غذا"
    if k == "buysteel":
        if c["treasury"] < 400:
            return False, "💸 پول کافی نیست"
        c["treasury"] -= 400
        c["steel"] += 50
        return True, "⚙️ +۵۰ فولاد"
    if k == "sellsteel":
        if c["steel"] < 50:
            return False, "⚙️ فولاد کافی نیست"
        c["steel"] -= 50
        c["treasury"] += 150
        return True, "💰 +۱۵۰ سکه"
    return False, "؟"


def set_tax(c, d):
    c["tax"] = max(5, min(60, c["tax"] + d))
    return f"مالیات {c['tax']}٪"


def set_budget(c, k, d):
    if k not in c["budget"]:
        return "؟"
    cur = c["budget"][k]
    new = max(0, min(40, cur + d))
    if sum(c["budget"].values()) - cur + new > 70:
        return "سقف کل بودجه ۷۰٪ است"
    c["budget"][k] = new
    return f"بودجه {new}٪"


# ---------------------------------------------------------------- نظامی
def morale(c):
    return min(1.2, 0.6 + 0.4 * c["sat"] / 100 + min(0.15, c["budget"]["mil"] * 0.005))


def brm(c, k):
    """ضریب ارتقای شاخه‌ی یگان (هر سطح +۱۰٪)."""
    return 1 + 0.10 * c.get("upg", {}).get(U[k]["br"], 0)


def attack_power(c, units=None):
    u = units if units is not None else c["units"]
    base = sum(u.get(k, 0) * U[k]["atk"] * brm(c, k) for k in ATK)
    return base * (1 + 0.08 * c["techlv"]["mil"]) * morale(c)


def defense_power(c):
    base = sum(c["units"].get(k, 0) * U[k]["dfn"] * brm(c, k) for k in U)
    return base * (1 + 0.08 * c["techlv"]["def"]) * morale(c) * (1 + 0.03 * lv(c, "police"))


def score(c):
    return int(c.get("gdp", 0) * 2 + attack_power(c) + defense_power(c) + c["pop"] / 20)


def battle(att, dfn, frac, support=0.0):
    sent = {k: int(att["units"].get(k, 0) * frac) for k in ATK}
    mis = int(att["units"].get("missile", 0) * frac)
    A = attack_power(att, sent) * random.uniform(0.85, 1.15)
    if A <= 0 and mis <= 0:
        return None
    D = (defense_power(dfn) + support) * random.uniform(0.85, 1.15)

    icpt = min(0.9, dfn["units"].get("ad", 0) * 0.04)
    hits = int(mis * (1 - icpt))
    att["units"]["missile"] = att["units"].get("missile", 0) - mis
    D *= 1 - min(0.3, hits * 0.01)
    destroyed = []
    for _ in range(hits // 6):
        pool = [k for k, v in dfn["buildings"].items() if v > 0]
        if not pool:
            break
        k = random.choice(pool)
        dfn["buildings"][k] -= 1
        destroyed.append(B[k]["n"])

    win = A > D
    r_loser = 0.25 + random.random() * 0.1
    r_winner = 0.05 + 0.12 * min(1.0, D / max(A, 1))
    ra, rd = (r_winner, r_loser) if win else (r_loser, r_winner)
    la, ld = {}, {}
    for k in ATK:
        l = int(sent[k] * ra)
        att["units"][k] -= l
        la[k] = l
    for k in U:
        if k == "missile":
            continue
        l = int(dfn["units"].get(k, 0) * rd)
        dfn["units"][k] = dfn["units"].get(k, 0) - l
        ld[k] = l

    loot = {}
    if win:
        t, f, s = max(0, dfn["treasury"]) * 0.12, dfn["food"] * 0.1, dfn["steel"] * 0.1
        dfn["treasury"] -= t
        dfn["food"] -= f
        dfn["steel"] -= s
        att["treasury"] += t
        att["food"] += f
        att["steel"] += s
        dfn["pop"] *= 0.98
        dfn["sat"] = max(0.0, dfn["sat"] - 8)
        att["sat"] = min(100.0, att["sat"] + 6)
        att["wins"] += 1
        dfn["losses"] += 1
        dfn["unrest"] = min(100.0, dfn.get("unrest", 15.0) + 5)
        dfn["shield_until"] = now() + SHIELD_LOSS_H * 3600
        loot = dict(t=t, f=f, s=s)
    else:
        att["sat"] = max(0.0, att["sat"] - 10)
        att["unrest"] = min(100.0, att.get("unrest", 15.0) + 8)
        att["losses"] += 1
        dfn["wins"] += 1
    att["weariness"] = min(40.0, att["weariness"] + 6)
    return dict(win=win, A=A, D=D, la=la, ld=ld, loot=loot, destroyed=destroyed,
                hits=hits, mis=mis, icpt=icpt)


# ---------------------------------------------------------------- جاسوسی
def spy(att, tgt, op):
    """برمی‌گردونه (موفق، متن، لو_رفت)"""
    lvl = lv(att, "intel")
    if lvl < 1:
        return False, "🕵️ سازمان اطلاعات نداری", False
    if att["treasury"] < 500:
        return False, "💸 عملیات ۵۰۰ سکه هزینه داره", False
    att["treasury"] -= 500
    chance = max(0.1, min(0.9, 0.35 + 0.1 * lvl - 0.08 * lv(tgt, "intel") - tgt["security"] / 400))
    if random.random() > chance:
        att["sat"] = max(0.0, att["sat"] - 2)
        return False, "🚨 عملیات لو رفت و عوامل دستگیر شدند", True
    if op == "scout":
        u = " ".join(f"{U[k]['e']}{tgt['units'].get(k, 0)}" for k in U)
        return True, (f"🔍 <b>گزارش اطلاعاتی</b>\n💰 {tgt['treasury']:,.0f} · 👥 {tgt['pop']:,.0f}\n"
                      f"😊 رضایت {tgt['sat']:.0f} · 🌾 {tgt['food']:,.0f} · ⚙️ {tgt['steel']:,.0f}\n"
                      f"🗡 {attack_power(tgt):,.0f} · 🛡 {defense_power(tgt):,.0f}\n{u}"), False
    if op == "sabotage":
        tgt["food"] *= 0.8
        tgt["steel"] *= 0.8
        tgt["sat"] = max(0.0, tgt["sat"] - 4)
        tgt["unrest"] = min(100.0, tgt.get("unrest", 15.0) + 6)
        return True, "💣 خرابکاری موفق: ۲۰٪ غذا و فولاد دشمن نابود شد و ناآرامی توی کشورش بالا رفت", False
    if op == "steal":
        s = tgt["tech"] * 0.15
        tgt["tech"] -= s
        att["tech"] += s
        return True, f"📡 {s:,.0f} امتیاز پژوهش دزدیده شد", False
    return False, "؟", False


# ---------------------------------------------------------------- مهار ناآرامی
CALM = {"talk": 900, "subsidy": 1800, "food": 1200, "crack": 1200, "media": 1200, "reform": 6 * 3600}


def calm(c, op):
    if op not in CALM:
        return False, "؟"
    left = CALM[op] - (now() - c["cd"].get(op, 0))
    if left > 0:
        return False, f"⏳ {int(left // 60) + 1} دقیقه‌ی دیگه"
    u = c["unrest"]
    stage = unrest_stage(u)[0]
    if op == "talk":
        if c["treasury"] < 400:
            return False, "💸 ۴۰۰ سکه لازمه"
        c["treasury"] -= 400
        drop = 12 if stage <= 2 else 6
        c["unrest"] = max(0.0, u - drop)
        msg = f"🤝 نمایندگان معترضان پذیرفته شدند (-{drop} ناآرامی)" + ("" if stage <= 2 else "\nدر شورش مذاکره اثر کمی دارد")
    elif op == "subsidy":
        cost = int(c["pop"] * 0.05)
        if c["treasury"] < cost:
            return False, f"💸 {cost:,} سکه لازمه"
        c["treasury"] -= cost
        c["unrest"] = max(0.0, u - 15)
        c["sat"] = min(100.0, c["sat"] + 3)
        msg = "💵 یارانه‌ی نقدی پخش شد (-۱۵ ناآرامی، رضایت +۳)"
    elif op == "food":
        cost = int(c["pop"] * 0.03)
        if c["food"] < cost:
            return False, f"🌾 {cost:,} غذا لازمه"
        c["food"] -= cost
        c["unrest"] = max(0.0, u - 10)
        msg = "🍞 غذای رایگان بین مردم پخش شد (-۱۰ ناآرامی)"
    elif op == "media":
        if c["treasury"] < 600:
            return False, "💸 ۶۰۰ سکه لازمه"
        c["treasury"] -= 600
        c["unrest"] = max(0.0, u - 8)
        c["literacy"] = max(0.0, c["literacy"] - 1)
        msg = "📺 کمپین رسانه‌ای و سانسور (-۸ ناآرامی، سواد -۱)"
    elif op == "reform":
        if c["treasury"] < 1500 or c["tech"] < 40:
            return False, "نیاز: ۱۵۰۰ سکه و ۴۰ امتیاز پژوهش"
        c["treasury"] -= 1500
        c["tech"] -= 40
        c["reforms"] = c.get("reforms", 0) + 1
        c["unrest"] = max(0.0, u - 20)
        c["sat"] = min(100.0, c["sat"] + 5)
        msg = f"🗳 اصلاحات سیاسی! (-۲۰ ناآرامی، رضایت +۵، اصلاحات دائمی: {c['reforms']})"
    else:  # crack
        if lv(c, "police") < 1:
            return False, "👮 نیاز به پلیس داری"
        if c["units"].get("inf", 0) < 50:
            return False, "🪖 حداقل ۵۰ پیاده لازمه"
        c["units"]["inf"] = int(c["units"]["inf"] * 0.99)
        if random.random() < 0.1 + max(0, u - 50) / 200:
            c["unrest"] = min(100.0, u + 15)
            c["pop"] *= 0.995
            c["sat"] = max(0.0, c["sat"] - 8)
            msg = "🩸 سرکوب خونین شد! خشم مردم بیشتر شد (+۱۵ ناآرامی، رضایت -۸)"
        else:
            c["unrest"] = max(0.0, u - 25)
            c["sat"] = max(0.0, c["sat"] - 6)
            msg = "👮 خیابان‌ها پاکسازی شد (-۲۵ ناآرامی، رضایت -۶)"
    c["cd"][op] = now()
    return True, msg


# ---------------------------------------------------------------- ارتقای شاخه‌ها
def upg_cost(l):
    return int(1500 * (l + 1) ** 1.7), 30 * (l + 1)


def upgrade(c, br):
    if br not in BRANCH:
        return False, "؟ (land / air / sea)"
    l = c["upg"].get(br, 0)
    if l >= MAX_LEVEL:
        return False, "حداکثر سطح"
    e, nm, need = BRANCH[br]
    need_lv = (l + 2) // 2
    if lv(c, need) < need_lv:
        return False, f"نیاز: {B[need]['n']} سطح {need_lv}"
    coin, steel = upg_cost(l)
    if c["treasury"] < coin:
        return False, f"💸 {coin:,} سکه لازمه"
    if c["steel"] < steel:
        return False, f"⚙️ {steel:,} فولاد لازمه"
    c["treasury"] -= coin
    c["steel"] -= steel
    c["upg"][br] = l + 1
    return True, f"✅ نیروی {nm} {e} → سطح {l + 1} (+{(l + 1) * 10}٪ قدرت)"


# ---------------------------------------------------------------- کشورهای NPC
def npc_id(i):
    return -(i + 1)          # ایندکس ۰ → id -1


def make_npc(i, spec):
    c = new_country(npc_id(i), spec["name"], "NPC")
    c["npc"], c["tier"], c["bounty"] = True, spec["tier"], spec["bounty"]
    c["units"] = {k: spec["units"].get(k, 0) for k in U}
    c["treasury"], c["pop"], c["food"], c["steel"] = float(spec["treasury"]), 12000.0 + 4000 * spec["tier"], 3000.0, 400.0 * spec["tier"]
    c["sat"], c["shield_until"] = 55.0, 0.0
    c["buildings"].update(police=spec["tier"] // 2)
    c["name_key"] = "npc%d" % (i + 1)
    c["base"] = dict(units=dict(c["units"]), treasury=c["treasury"], pop=c["pop"], food=c["food"], steel=c["steel"])
    return c


def npc_regen(c, dt):
    b = c["base"]
    for k, v in b["units"].items():
        c["units"][k] = int(approach(c["units"].get(k, 0), v, 0.08, dt) + 0.5)
    for k in ("treasury", "pop", "food", "steel"):
        c[k] = approach(c[k], b[k], 0.05, dt)
    c["sat"] = approach(c["sat"], 55.0, 0.1, dt)
    c["unrest"] = approach(c.get("unrest", 0.0), 0.0, 0.1, dt)
    c["shield_until"] = 0.0
