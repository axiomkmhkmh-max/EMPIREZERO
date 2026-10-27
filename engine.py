import math
import random
import time

import config
import events
import prog
from config import B, U, TECH, MAX_LEVEL, SHIELD_NEW_H, SHIELD_LOSS_H, BRANCH
from prog import dur

ATK = tuple(k for k, u in U.items() if u["atk"] > 0)     # همه‌ی یگان‌های تهاجمی (پدافند و موشک جدان)

# ضریب‌های رویداد روی درآمد/پژوهش؛ db.load قبل از هر tick مقدارشون رو (وزنی بر اساس بازه) می‌گذاره
EV = {"income": 1.0, "research": 1.0}

# نرخ‌های بانک مرکزی (درصد در هر روز بازی) - world_loop مقدارشون رو بروز می‌کنه
RATE = {"dep": 0.01, "loan": 0.05}


def now():
    return time.time()


def lv(c, k):
    return c["buildings"].get(k, 0)


def army_size(c):
    """اندازه‌ی کل ارتش؛ یگان‌های توی لشکرکشی هم حساب میشن (وگرنه موقع اعزام می‌شد ظرفیت پادگان رو دور زد)."""
    away = sum(v * U[k]["size"] for m in c.get("marches", []) for k, v in m["sent"].items() if k in U)
    return sum(c["units"].get(k, 0) * U[k]["size"] for k in U) + away


def defaults(c):
    """فیلدهای جدید رو روی کشورهای قدیمی هم می‌گذاره (مهاجرت بی‌صدا)."""
    for k, v in (("unrest", 15.0), ("stage", 0), ("reforms", 0), ("cd", {}),
                 ("upg", {"land": 0, "air": 0, "sea": 0}), ("bank", {"dep": 0.0, "loan": 0.0}),
                 ("fx", {}), ("fxcost", {}), ("st", {}), ("emblem", "🏛"), ("done", []), ("npc_cd", {}),
                 ("daily", {"last": 0.0, "streak": 0}), ("cd2", {}), ("home", None),
                 # --- سیستم جنگ بزرگ و رشد
                 ("queue", []), ("tq", []), ("jid", 0), ("land", config.LAND_START),
                 ("camp", {"stage": 1, "wins": 0, "best": 0}), ("revenge", {}), ("intel", {}), ("pvp_cd", {}),
                 ("lucky", {"d": "", "free": False, "paid": 0, "bonus": 0}), ("dil", None),
                 ("inv", {"by": None, "n": 0, "claimed": []}), ("codes", []), ("titles", []),
                 ("gifted", {"d": "", "amt": 0}), ("snap", {}), ("blog", [])):
        if k not in c:
            c[k] = v.copy() if isinstance(v, (dict, list)) else v
    for k in TECH:
        c["techlv"].setdefault(k, 0)
    for k in U:
        c["units"].setdefault(k, 0)
    for k in config.BUDGET_COST:                  # بودجه‌های تازه (رفاه، زیرساخت) روی کشورهای قدیمی هم
        c["budget"].setdefault(k, 0)
    c.setdefault("marches", [])
    c.setdefault("colony", [])
    if "palace" not in c["buildings"]:           # کشورهای قدیمی: کاخی که سطح فعلی‌شون رو نگه می‌داره
        mx = max([v for k, v in c["buildings"].items() if k != "palace"] or [0])
        c["buildings"]["palace"] = max(1, math.ceil((mx - 1) / 2))
    if not c.get("orders"):
        c["orders"] = {"n": float(config.ORDERS_MAX + c["buildings"]["palace"]), "t": now()}
    prog.roll(c)
    return c


def bmax(k):
    return B[k].get("max", MAX_LEVEL)


def level_cap(c):
    """سقف سطح ساختمان‌ها (غیر از خود کاخ) بر اساس سطح کاخ."""
    return min(MAX_LEVEL, 2 * lv(c, "palace") + 1)


def slots(c):
    """تعداد کارگاه‌های همزمان ساخت/ارتقا."""
    p = lv(c, "palace")
    return 1 + (p >= 3) + (p >= 5)


# ---------------------------------------------------------------- فرمان نظامی (انرژی حمله)
def orders_max(c):
    emp = config.CROWN_ORDERS if config.EMPEROR.get("id") == c.get("_id") else 0     # 👑 امتیاز تاج
    return config.ORDERS_MAX + lv(c, "palace") + emp


def orders(c):
    o = c.get("orders") or {"n": float(orders_max(c)), "t": now()}
    return min(float(orders_max(c)), o["n"] + (now() - o["t"]) / max(1, config.ORDER_REGEN))


def spend_orders(c, k=1):
    cur = orders(c)
    if cur + 1e-9 < k:
        return False
    c["orders"] = {"n": cur - k, "t": now()}
    return True


def order_wait(c):
    """ثانیه تا فرمان بعدی."""
    cur = orders(c)
    if cur >= orders_max(c):
        return 0
    return (1 - (cur - math.floor(cur))) * config.ORDER_REGEN


def new_country(uid, name, leader, doctrine="bal"):
    t = now()
    st = config.STARTER
    c = {
        "_id": uid, "name": name, "leader": leader, "created": t, "doctrine": doctrine,
        "treasury": 3000.0, "pop": 10000.0, "food": st["food"], "steel": st["steel"],
        "sat": 40.0, "literacy": 20.0, "health": 40.0, "security": 30.0, "weariness": 0.0,
        "tax": 25, "budget": {"edu": 8, "health": 8, "mil": 2, "sec": 4, "welfare": 0, "infra": 0},
        "buildings": {"farm": 2, "market": 1, "school": 1, "power": 1, "palace": 1},
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
    return 12000 + 5000 * lv(c, "infra") + 800 * sum(v for k, v in c["buildings"].items() if k != "infra") \
        + 600 * (c.get("land", config.LAND_START) - config.LAND_START)


def tax_base(c, gdp=None):
    """پایه‌ی مالیات = سهمی از تولید + درآمد سرانه‌ی جمعیت (جمعیت بیشتر = مالیات بیشتر حتی با درصد کم)."""
    g = c.get("gdp", 0.0) if gdp is None else gdp
    return g * config.TAX_GDP_SHARE + c["pop"] * config.TAX_CAPITA


def budget_factor(c, kind):
    return c["pop"] / 10000.0 if kind == "pop" else float(c.get("land", config.LAND_START))


def budget_unit_cost(c, k):
    """هزینه‌ی هر واحد بودجه‌ی k در ساعت بازی؛ بسته به عامل (جمعیت یا استان)."""
    kind, rate = config.BUDGET_COST[k]
    if kind == "pop":
        return rate * c["pop"]
    return rate * c.get("land", config.LAND_START)


def budget_costs(c):
    return {k: budget_unit_cost(c, k) * c["budget"].get(k, 0) for k in config.BUDGET_COST}


def derive(c):
    jobs = sum(lv(c, k) * b["jobs"] for k, b in B.items())
    workers = max(0.0, c["pop"] * 0.6 - army_size(c))
    sup, dem, er = energy(c)
    lit, hp = c["literacy"] / 100, c["health"] / 100
    prod = ((0.6 + 0.4 * lit) * (0.7 + 0.3 * hp) * (1 + 0.1 * lv(c, "infra")) * (0.6 + 0.4 * er)
            * (0.6 + 0.4 * c["sat"] / 100) * (1 + 0.06 * c["techlv"]["eco"])
            * (1 + 0.06 * lv(c, "market")) * (1 + c.get("ally_bonus", 0))
            * (1 - min(0.4, c.get("unrest", 15.0) * 0.004))
            * (1 + 0.02 * (c.get("land", config.LAND_START) - config.LAND_START)))
    formal = min(jobs, workers)
    informal = max(0.0, workers - formal) * 0.3
    gdp = formal * 2.5 * prod + informal * 0.2
    emp = (formal + informal) / workers if workers > 0 else 1.0
    revenue = tax_base(c, gdp) * c["tax"] / 100
    costs = budget_costs(c)
    spend = sum(costs.values())
    upkeep = (sum(lv(c, k) * b["up"] for k, b in B.items())
              + sum(c["units"].get(k, 0) * u["up"] for k, u in U.items()))
    return dict(jobs=jobs, workers=workers, er=er, sup=sup, dem=dem, prod=prod, gdp=gdp, emp=emp,
                revenue=revenue, spend=spend, costs=costs, upkeep=upkeep, net=revenue - spend - upkeep,
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
    relief = c["security"] * 0.15 + 2 * min(5, c.get("reforms", 0)) + 0.25 * c["budget"].get("welfare", 0)
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
    net = d["net"]
    inc = net * EV["income"] if net > 0 else net
    c["treasury"] += inc * dt
    if net > 0:
        prog.add(c, "earn", inc * dt)
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
    c["tech"] += (1 + 8 * lv(c, "university")) * (0.3 + lit) * dt * EV["research"]

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
              - (25 if c["starving"] else 0) - (15 if c["treasury"] < 0 else 0) - c["unrest"] * 0.15
              + 0.3 * c["budget"].get("welfare", 0))
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
    if not c.get("dil") and random.random() < min(0.5, 0.03 * dt):      # رویداد دوگزینه‌ای (باید خودت تصمیم بگیری)
        c["dil"] = {"id": events.pick(c), "ts": now(), "sent": False}

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


def build_secs(k, l):
    t = config.BUILD_T0 * config.BUILD_GROWTH ** l * (2 if k == "palace" else 1)
    return t * config.BUILD_TIME_MULT * events.mult("build")


def _jid(c):
    c["jid"] = c.get("jid", 0) + 1
    return c["jid"]


def build(c, k):
    if k not in B:
        return False, "؟"
    l = lv(c, k)
    if l >= bmax(k):
        return False, "حداکثر سطح"
    if k != "palace" and l >= level_cap(c):
        return False, f"🏰 برای رفتن بالاتر از سطح {l} باید کاخ رو ارتقا بدی"
    for r, rl in B[k]["req"].items():
        if lv(c, r) < rl:
            return False, f"نیاز: {B[r]['n']} سطح {rl}"
    if any(j["kind"] == "b" and j["key"] == k for j in c["queue"]):
        return False, "⏳ این ساختمان همین الان در حال ساخته"
    if len(c["queue"]) >= slots(c):
        return False, f"🏗 همه‌ی {slots(c)} کارگاه مشغوله؛ صبر کن یا با زیرو تسریع کن"
    cost = build_cost(k, l)
    if c["treasury"] < cost:
        return False, "💸 سکه‌ت کافی نیست"
    c["treasury"] -= cost
    prog.bump(c, "build")
    secs = build_secs(k, l)
    if secs < 1:
        c["buildings"][k] = l + 1
        return True, f"✅ {B[k]['n']} شد سطح {l + 1} 🎉"
    c["queue"].append({"id": _jid(c), "kind": "b", "key": k, "to": l + 1, "start": now(), "end": now() + secs})
    return True, f"🔨 ساخت {B[k]['n']} سطح {l + 1} شروع شد؛ {dur(secs)} دیگه آماده‌ست"


def army_cap(c):
    return lv(c, "barracks") * 1500 + config.LAND_ARMY * max(0, c.get("land", config.LAND_START) - config.LAND_START)


def queued_size(c):
    return sum(b["n"] * U[b["k"]]["size"] for b in c.get("tq", []))


def train_secs(c, k, n):
    return n * U[k]["t"] * config.TRAIN_TIME_MULT * events.mult("build") / (1 + 0.12 * lv(c, "barracks"))


def max_buy(c, k):
    """بیشترین تعداد یگان k که الان می‌تونی بخری (سکه، فولاد و ظرفیت پادگان)."""
    if k not in U:
        return 0
    u = U[k]
    room = army_cap(c) - army_size(c) - queued_size(c)
    lim = [room // u["size"], int(c["treasury"] // u["cost"]) if u["cost"] else 10 ** 9,
           int(c["steel"] // u["steel"]) if u["steel"] else 10 ** 9]
    return max(0, min(lim))


def buy_unit(c, k, n):
    if k not in U:
        return False, "؟"
    if n == "max":
        n = max_buy(c, k)
    if n <= 0:
        return False, "💸 الان برای این یگان سکه، فولاد یا ظرفیت پادگان نداری"
    u = U[k]
    for r, rl in u["req"].items():
        if lv(c, r) < rl:
            return False, f"نیاز: {B[r]['n']} سطح {rl}"
    if army_size(c) + queued_size(c) + n * u["size"] > army_cap(c):
        return False, "🏕 ظرفیت پادگان کافی نیست"
    pend = [b for b in c["tq"] if U[b["k"]]["br"] == u["br"]]
    if len(pend) >= config.TRAIN_QUEUE_MAX:
        return False, "⏳ صف آموزش این شاخه پره؛ کمی صبر کن"
    if c["treasury"] < u["cost"] * n:
        return False, "💸 سکه‌ت کافی نیست"
    if c["steel"] < u["steel"] * n:
        return False, "⚙️ فولاد کافی نیست"
    c["treasury"] -= u["cost"] * n
    c["steel"] -= u["steel"] * n
    prog.bump(c, "train", n)
    secs = train_secs(c, k, n)
    if secs < 1:
        c["units"][k] = c["units"].get(k, 0) + n
        return True, f"✅ {n} {u['n']} آماده‌ی نبرده 💪"
    st = max([now()] + [b["end"] for b in pend])
    last = max(pend, key=lambda b: b["end"]) if pend else None
    if last and last["k"] == k:              # خرید پشت‌سرهم از یه یگان توی همون دسته ادغام میشه (صف پر نمیشه)
        last["n"] += n
        last["end"] += secs
        return True, f"🪖 آموزش {n} {u['n']} به صف اضافه شد؛ {dur(last['end'] - now())} دیگه آماده‌ست"
    c["tq"].append({"id": _jid(c), "k": k, "n": n, "end": st + secs})
    return True, f"🪖 آموزش {n} {u['n']} شروع شد؛ {dur(st + secs - now())} دیگه آماده‌ست"


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
            return False, "💸 سکه‌ت کافی نیست"
        c["treasury"] -= 1500
        c["food"] += 1000
        return True, "🌾 +۱۰۰۰ غذا"
    if k == "buysteel":
        if c["treasury"] < 400:
            return False, "💸 سکه‌ت کافی نیست"
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
    if k not in config.BUDGET_COST:
        return "؟"
    cur = c["budget"].get(k, 0)
    new = max(0, min(40, cur + d))
    if sum(c["budget"].values()) - cur + new > config.BUDGET_CAP:
        return f"سقف کل بودجه {config.BUDGET_CAP} واحده"
    c["budget"][k] = new
    return f"{config.BUDGET_NAMES[k]} {new} واحد · {budget_unit_cost(c, k) * new:,.0f} سکه/ساعت"


# ---------------------------------------------------------------- نظامی
def morale(c):
    return min(1.2, 0.6 + 0.4 * c["sat"] / 100 + min(0.15, c["budget"].get("mil", 0) * 0.005))


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
    return int(c.get("gdp", 0) * 2 + attack_power(c) + defense_power(c) + c["pop"] / 20 + 60 * c.get("land", config.LAND_START))


STANCES = {
    "bal": dict(n="متعادل", e="⚔️", atk=1.0, loss=1.0, loot=1.0, d="ضرایب عادی"),
    "all": dict(n="یورش تهاجمی", e="🔥", atk=1.2, loss=1.4, loot=1.25, d="قدرت و غنیمت بیشتر، تلفات بیشتر"),
    "safe": dict(n="محتاطانه", e="🛡", atk=0.9, loss=0.6, loot=0.8, d="تلفات کمتر، قدرت و غنیمت کمتر"),
}
FRONTS = (("air", "✈️", "هوایی"), ("sea", "🚢", "دریایی"), ("land", "🪖", "زمینی"))
FRONT_OF = {k: u["br"] for k, u in U.items()}
LIGHT, ARMOR = ("inf", "cmd"), ("tank", "htank")                  # پیاده‌های سبک / زره‌پوش‌ها
SURF = ("ship", "corvette", "destroyer", "carrier")               # ناوهای سطحی (زیردریایی جدا)


def _share(u, a, b):
    """سهم گروه a در مجموع گروه‌های a و b (بر اساس ظرفیت). a و b یه کلید یا چندتا کلیدن."""
    a, b = (a,) if isinstance(a, str) else a, (b,) if isinstance(b, str) else b
    x, y = sum(u.get(k, 0) * U[k]["size"] for k in a), sum(u.get(k, 0) * U[k]["size"] for k in b)
    return x / (x + y) if x + y > 0 else 0.0


def _fronts(att, dfn, sent, mode="all"):
    """قدرت خام هر جبهه (مهاجم، مدافع) با ضدیت یگان‌ها: زره>پیاده‌ی سبک، توپخانه>پیاده‌ی سبک، زیردریایی>ناو، ناو>زیردریایی."""
    ua, ud = sent, dfn["units"]
    tank_a = 1.25 if _share(ud, LIGHT, ARMOR) >= 0.55 else 1.0
    arty_a = 1.2 if _share(ud, LIGHT, ARMOR) >= 0.55 else 1.0
    inf_d = 0.85 if _share(ua, ARMOR, LIGHT) >= 0.55 else 1.0
    sub_a = 1.3 if _share(ud, SURF, "sub") >= 0.55 else 1.0
    ship_a = 1.2 if _share(ud, "sub", SURF) >= 0.55 else 1.0
    ship_d = 1.2 if _share(ua, "sub", SURF) >= 0.55 else 1.0
    sub_d = 1.3 if _share(ua, SURF, "sub") >= 0.55 else 1.0

    def ma(k):
        return tank_a if k in ARMOR else arty_a if k == "arty" else sub_a if k == "sub" else ship_a if k in SURF else 1.0

    def md(k):
        return inf_d if k in LIGHT else ship_d if k in SURF else sub_d if k == "sub" else 1.0
    out = {}
    for f in ("air", "sea", "land"):
        a = sum(ua.get(k, 0) * u["atk"] * brm(att, k) * ma(k) for k, u in U.items() if u["br"] == f and u["atk"] > 0)
        d = sum(ud.get(k, 0) * u["dfn"] * brm(dfn, k) * md(k) for k, u in U.items() if u["br"] == f and u["dfn"] > 0)
        out[f] = (a, d)
    return out


def calc(att, dfn, frac, stance="bal", support=0.0, rnd=None, sent=None, mode="all"):
    """محاسبه‌ی نبرد سه‌جبهه‌ای؛ اول هوا، برنده‌ی آسمون به دریا و زمین بونوس می‌ده.
    mode = نوع حمله (all/land/sea/air): دفاع هر جبهه‌ی مدافع به‌اندازه‌ی وزنش (MODE_DEF_W) حساب میشه.
    sent = یگان‌های اعزامی (لشکرکشی)؛ نباشه frac از ارتش فعلی."""
    st = STANCES.get(stance, STANCES["bal"])
    if sent is None:
        sent = {k: int(att["units"].get(k, 0) * frac) for k in ATK}
    w = config.def_weights(mode)
    ga = (1 + 0.08 * att["techlv"]["mil"]) * morale(att) * st["atk"]
    gd = (1 + 0.08 * dfn["techlv"]["def"]) * morale(dfn) * (1 + 0.03 * lv(dfn, "police"))
    raw = _fronts(att, dfn, sent, mode)
    fa = {f: raw[f][0] * ga for f in raw}
    fd = {f: raw[f][1] * gd * w[f] for f in raw}
    ra, rd = (rnd(), rnd()) if rnd else (1.0, 1.0)
    air = None
    if fa["air"] > 0 and fa["air"] * ra > fd["air"] * rd:
        air = "att"
    elif fd["air"] > 0:
        air = "def"
    ma, md = (1.10, 0.95) if air == "att" else (0.92, 1.04) if air == "def" else (1.0, 1.0)
    for f in ("sea", "land"):
        fa[f] *= ma
        fd[f] *= md
    fronts = {f: (fa[f], fd[f], None if fa[f] <= 0 else fa[f] * ra > fd[f] * rd) for f in raw}
    return dict(sent=sent, A=sum(fa.values()) * ra, D=(sum(fd.values()) + support) * rd, fronts=fronts, air=air, st=st, w=w)


def estimate(att, dfn, frac, stance="bal", support=0.0, mode="all", sent=None):
    """(قدرت حمله، قدرت دفاع، شانس پیروزی) بدون تصادف؛ برای نمایش قبل از حمله."""
    r = calc(att, dfn, frac, stance, support, None, sent, mode)
    A, D = r["A"], r["D"]
    if A <= 0:
        return 0.0, D, 0.0
    p = sum(1 for _ in range(300) if A * random.uniform(0.85, 1.15) > D * random.uniform(0.85, 1.15)) / 300
    return A, D, p


def battle(att, dfn, frac, support=0.0, stance="bal", loot_mult=1.0, sent=None, mode="all", conquest_ratio=None):
    r = calc(att, dfn, frac, stance, support, lambda: random.uniform(0.85, 1.15), sent, mode)
    sent, A, D, st, fr, wm = r["sent"], r["A"], r["D"], r["st"], r["fronts"], r["w"]
    if "missile" in sent or "air" in config.mode_branches(mode):
        mis = int(sent["missile"]) if "missile" in sent else int(att["units"].get("missile", 0) * frac)
    else:
        mis = 0
    mis = min(mis, int(att["units"].get("missile", 0)))
    if A <= 0 and mis <= 0:
        return None
    icpt = min(0.9, dfn["units"].get("ad", 0) * 0.04)
    hits = int(mis * (1 - icpt))
    att["units"]["missile"] = att["units"].get("missile", 0) - mis
    D *= 1 - min(0.3, hits * 0.01)
    destroyed = []
    for _ in range(0 if dfn.get("camp") else hits // 6):
        pool = [k for k, v in dfn["buildings"].items() if v > 0]
        if not pool:
            break
        k = random.choice(pool)
        dfn["buildings"][k] -= 1
        destroyed.append(B[k]["n"])

    win = A > D
    ratio = A / max(D, 1.0)
    r_loser = 0.25 + random.random() * 0.1
    r_winner = 0.05 + 0.12 * min(1.0, D / max(A, 1.0))
    ra, rd = (r_winner, r_loser) if win else (r_loser, r_winner)
    ra *= st["loss"]
    rec_a, rec_d = min(0.4, 0.10 + 0.03 * lv(att, "hospital")), min(0.4, 0.10 + 0.03 * lv(dfn, "hospital"))
    la, ld, back_a, back_d = {}, {}, 0, 0
    for k in ATK:                      # هر جبهه‌ای که بردی تلفات کمتری می‌دی
        if not sent.get(k):
            continue
        w = fr[FRONT_OF[k]][2]
        lost = int(sent[k] * min(0.9, ra * (0.8 if w else 1.25 if w is False else 1.0)))
        b = int(lost * rec_a)
        att["units"][k] -= lost - b
        la[k], back_a = lost - b, back_a + b
    for k in U:
        if k == "missile":
            continue
        f = FRONT_OF.get(k)
        w = fr[f][2] if f in fr else None
        lost = int(dfn["units"].get(k, 0) * min(0.9, rd * wm.get(f, 1.0) * (1.25 if w else 0.8 if w is False else 1.0)))
        b = int(lost * rec_d)
        dfn["units"][k] = dfn["units"].get(k, 0) - (lost - b)
        ld[k], back_d = lost - b, back_d + b

    loot = {}
    if win:
        lm = min(2.0, st["loot"] * loot_mult * events.mult("loot"))
        t, f, s_ = max(0, dfn["treasury"]) * 0.12 * lm, dfn["food"] * 0.1 * lm, dfn["steel"] * 0.1 * lm
        dfn["treasury"] -= t
        dfn["food"] -= f
        dfn["steel"] -= s_
        att["treasury"] += t
        att["food"] += f
        att["steel"] += s_
        dfn["pop"] *= 0.98
        dfn["sat"] = max(0.0, dfn["sat"] - 8)
        att["sat"] = min(100.0, att["sat"] + 6)
        att["wins"] += 1
        dfn["losses"] += 1
        dfn["unrest"] = min(100.0, dfn.get("unrest", 15.0) + 5)
        dfn["shield_until"] = now() + SHIELD_LOSS_H * 3600
        loot = dict(t=t, f=f, s=s_)
    else:
        att["sat"] = max(0.0, att["sat"] - 10)
        att["unrest"] = min(100.0, att.get("unrest", 15.0) + 8)
        att["losses"] += 1
        dfn["wins"] += 1
    att["weariness"] = min(40.0, att["weariness"] + 6)
    need = config.CONQUEST_RATIO if conquest_ratio is None else conquest_ratio
    return dict(win=win, A=A, D=D, la=la, ld=ld, loot=loot, destroyed=destroyed, hits=hits, mis=mis, icpt=icpt,
                fronts=[(e, nm, fr[f][0], fr[f][1], fr[f][2]) for f, e, nm in FRONTS if fr[f][0] > 0 or fr[f][1] > 0],
                air=r["air"], stance=stance, ratio=ratio, decisive=win and ratio >= need, mode=mode,
                back_a=back_a, back_d=back_d)


# ---------------------------------------------------------------- جاسوسی
def spy(att, tgt, op):
    """برمی‌گردونه (موفق، متن، لو_رفت)"""
    lvl = lv(att, "intel")
    if lvl < 1:
        return False, "🕵️ سازمان اطلاعات نداری", False
    if att["treasury"] < 500:
        return False, "💸 عملیات ۵۰۰ سکه هزینه داره", False
    att["treasury"] -= 500
    prog.bump(att, "spy")
    chance = max(0.1, min(0.9, 0.35 + 0.1 * lvl - 0.08 * lv(tgt, "intel") - tgt["security"] / 400))
    if random.random() > chance:
        att["sat"] = max(0.0, att["sat"] - 2)
        return False, "🚨 عملیات لو رفت و عوامل دستگیر شدند", True
    if op == "scout":
        u = " ".join(f"{U[k]['e']}{tgt['units'].get(k, 0)}" for k in U)
        att.setdefault("intel", {})[str(tgt["_id"])] = dict(
            ts=now(), dfn=defense_power(tgt), atk=attack_power(tgt), score=score(tgt), land=tgt.get("land", config.LAND_START),
            treasury=tgt["treasury"], units={k: tgt["units"].get(k, 0) for k in U})
        return True, (f"🔍 <b>گزارش اطلاعاتی</b>\n💰 {tgt['treasury']:,.0f} · 👥 {tgt['pop']:,.0f} · 🏞 {tgt.get('land', config.LAND_START)} استان\n"
                      f"😊 رضایت {tgt['sat']:.0f} · 🌾 {tgt['food']:,.0f} · ⚙️ {tgt['steel']:,.0f}\n"
                      f"🗡 {attack_power(tgt):,.0f} · 🛡 {defense_power(tgt):,.0f}\n{u}\n"
                      f"⏳ این اطلاعات {config.INTEL_TTL // 60} دقیقه معتبره"), False
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


def upg_secs(l):
    return config.UPG_T0 * (l + 1) ** 1.5 * config.BUILD_TIME_MULT * events.mult("build")


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
    if any(j["kind"] == "u" and j["key"] == br for j in c["queue"]):
        return False, "⏳ این شاخه همین الان در حال ارتقاست"
    if len(c["queue"]) >= slots(c):
        return False, f"🏗 همه‌ی {slots(c)} کارگاه مشغوله؛ صبر کن یا با زیرو تسریع کن"
    coin, steel = upg_cost(l)
    if c["treasury"] < coin:
        return False, f"💸 {coin:,} سکه لازمه"
    if c["steel"] < steel:
        return False, f"⚙️ {steel:,} فولاد لازمه"
    c["treasury"] -= coin
    c["steel"] -= steel
    prog.bump(c, "build")
    secs = upg_secs(l)
    if secs < 1:
        c["upg"][br] = l + 1
        return True, f"✅ نیروی {nm} {e} → سطح {l + 1} (+{(l + 1) * 10}٪ قدرت)"
    c["queue"].append({"id": _jid(c), "kind": "u", "key": br, "to": l + 1, "start": now(), "end": now() + secs})
    return True, f"⬆️ ارتقای نیروی {nm} {e} به سطح {l + 1} شروع شد؛ {dur(secs)} دیگه"


# ---------------------------------------------------------------- 🏕 استعمار (آباد کردن زمین خالی)
def land_cap(c):
    """سقف استان‌های هر کشور از روی جمعیتش: ۵ استان اول با ۱۰ هزار نفر، بعدش به‌ازای هر ۲٬۵۰۰ نفر بیشتر یکی."""
    extra = max(0, int((c["pop"] - config.LAND_POP0) // config.LAND_POP_PER))
    return min(config.LAND_MAX, config.LAND_START + extra)


def land_cap_msg(c):
    return (f"👥 جمعیتت ({c['pop']:,.0f}) فقط تا {land_cap(c)} استان رو پشتیبانی می‌کنه "
            f"(هر {config.LAND_POP_PER:,} نفرِ بالای {config.LAND_POP0:,} یه استان) — جمعیتت رو زیاد کن")


def colony_step(c):
    """تعداد پله‌ی استعمار: استان‌های بالای شروع + کارهای در حال انجام."""
    return min(config.COLONY_STEPS_MAX, max(0, c.get("land", config.LAND_START) - config.LAND_START) + len(c.get("colony", [])))


def colony_cost(c):
    k = colony_step(c)
    return int(config.COLONY_COST0 * config.COLONY_GROWTH ** k), int(config.COLONY_STEEL0 * (1 + 0.25 * k)), int(config.COLONY_FOOD0 * (1 + 0.25 * k))


def colony_secs(c):
    k = max(0, c.get("land", config.LAND_START) - config.LAND_START) + len(c.get("colony", []))
    return min(config.COLONY_SECS_MAX, config.COLONY_SECS0 * config.COLONY_SECS_GROWTH ** k) * config.BUILD_TIME_MULT


def colony_slots(c):
    return 1 + (lv(c, "palace") >= 5)


def colony_start(c, free_cells):
    """شروع آباد کردن یه استانِ تازه روی زمین خالیِ نقشه. (موفق؟، پیام)"""
    c.setdefault("colony", [])
    if lv(c, "palace") < config.COLONY_MIN_PALACE:
        return False, f"🏰 برای استعمار باید کاخ حداقل سطح {config.COLONY_MIN_PALACE} باشه"
    if c.get("land", config.LAND_START) + len(c["colony"]) >= land_cap(c):
        return False, "🏞 " + land_cap_msg(c)
    if len(c["colony"]) >= colony_slots(c):
        return False, f"⏳ همین الان {len(c['colony'])} استعمار در حال انجامه (کاخ سطح ۵ ظرفیت دومی میده)"
    if free_cells < 10:
        return False, "🗺 زمین خالیِ مناسبی روی نقشه نمونده"
    coins, steel, food = colony_cost(c)
    if c["treasury"] < coins:
        return False, f"💸 استعمار {coins:,} سکه می‌خواد"
    if c["steel"] < steel:
        return False, f"⚙️ استعمار {steel:,} فولاد می‌خواد"
    if c["food"] < food:
        return False, f"🌾 استعمار {food:,} غذا می‌خواد (برای مهاجران)"
    c["treasury"] -= coins
    c["steel"] -= steel
    c["food"] -= food
    secs = colony_secs(c)
    c["colony"].append({"id": _jid(c), "start": now(), "end": now() + secs})
    prog.bump(c, "build")
    if secs < 1:
        settle(c)
        return True, "🏕 استان جدید همون لحظه آباد شد! 🎉"
    return True, f"🏕 استعمار شروع شد؛ {dur(secs)} دیگه یه استان تازه به قلمروت اضافه میشه (−{coins:,}💰 −{steel:,}⚙️ −{food:,}🌾)"


def settle(c):
    """کارهای تمام‌شده (ساخت، ارتقا، آموزش) رو تحویل می‌ده و رویداد دوگزینه‌ای منقضی رو می‌بنده."""
    if c.get("npc"):
        return []
    t, msgs, keep = now(), [], []
    for j in c["queue"]:
        if j["end"] > t:
            keep.append(j)
        elif j["kind"] == "b":
            c["buildings"][j["key"]] = max(lv(c, j["key"]), j["to"])
            msgs.append(f"🏗 {B[j['key']]['e']} {B[j['key']]['n']} شد سطح {j['to']} ✅")
        else:
            c["upg"][j["key"]] = max(c["upg"].get(j["key"], 0), j["to"])
            e, nm, _ = BRANCH[j["key"]]
            msgs.append(f"⬆️ نیروی {nm} {e} شد سطح {j['to']} ✅")
    c["queue"] = keep
    keep = []
    for b in c["tq"]:
        if b["end"] > t:
            keep.append(b)
        else:
            c["units"][b["k"]] = c["units"].get(b["k"], 0) + b["n"]
            msgs.append(f"🪖 {b['n']:,} {U[b['k']]['n']} آماده‌ی نبرد شد")
    c["tq"] = keep
    keep = []
    for j in c.get("colony", []):
        if j["end"] > t:
            keep.append(j)
        elif c.get("land", config.LAND_START) < config.LAND_MAX:          # سقفِ جمعیت موقع شروع چک شده؛ این فقط سقف فنیه
            c["land"] = c.get("land", config.LAND_START) + 1
            msgs.append(f"🏕 استعمار تموم شد؛ یه استان تازه آباد شد! قلمروت {c['land']} استان 🎉")
            c.setdefault("news_out", []).append(f"🏕 <b>{c['name']}</b> زمین‌های خالی رو آباد کرد و استان {c['land']}ـمش رو ساخت!")
    c["colony"] = keep
    d = c.get("dil")
    if d and t - d["ts"] > events.DIL_TTL:
        r = events.resolve(c, "b", auto=True)
        if r:
            msgs.append(r)
    if msgs:
        c["pending"] = (c.get("pending", []) + msgs)[-8:]
    return msgs


def speedup(c, jid):
    """تسریع یه کار ساخت/ارتقا/آموزش با زیرو."""
    job = next((x for x in c["queue"] + c["tq"] if x["id"] == jid), None)
    if not job:
        return False, "این کار دیگه تموم شده"
    left = job["end"] - now()
    spd = c.setdefault("spd", {"d": "", "s": 0.0})
    if spd.get("d") != prog.day_id():
        spd["d"], spd["s"] = prog.day_id(), 0.0
    room = (config.SPEEDUP_DAILY - spd["s"]) if config.SPEEDUP_DAILY else left
    if room < 60:
        return False, "⏳ سقف تسریع امروز پر شده؛ فردا ادامه بده"
    skip = min(left, room)
    cost = max(1, math.ceil(skip / config.SPEEDUP_SECS))
    if c["fx"].get("PHX", 0) < cost:
        return False, f"⚡ {cost} زیرو لازمه"
    c["fx"]["PHX"] -= cost
    spd["s"] += skip
    job["end"] -= skip
    settle(c)
    if skip < left:
        return True, f"⚡ {prog.dur(skip)} تسریع شد (−{cost} زیرو)؛ {prog.dur(left - skip)} مونده (سقف امروز پر شد)"
    return True, f"⚡ تسریع شد (−{cost} زیرو)"


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
    c["land"] = config.NPC_LAND_BASE + spec["tier"]
    c["base"] = dict(units=dict(c["units"]), treasury=c["treasury"], pop=c["pop"], food=c["food"], steel=c["steel"], land=c["land"])
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
    # 🏞 استان‌های تسخیرشده‌ی NPC کم‌کم برمی‌گردن (dt بر حسب ساعتِ بازیه)
    b.setdefault("land", max(c.get("land", config.LAND_START), config.NPC_LAND_BASE + c.get("tier", 1)))
    if c.get("land", b["land"]) < b["land"]:
        c["land_acc"] = c.get("land_acc", 0.0) + dt
        while c["land_acc"] >= config.NPC_LAND_REGEN_H and c["land"] < b["land"]:
            c["land_acc"] -= config.NPC_LAND_REGEN_H
            c["land"] += 1
    else:
        c["land_acc"] = 0.0
        c["land"] = b["land"]
