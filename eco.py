"""بانک مرکزی، بازار، ارز/توکن، جایزه‌ی روزانه، کار و ماموریت‌ها."""
import math
import random
import time

import config
import engine as E
import db
import prog
from config import ASSETS, ITEMS

WORLD = {}


# ------------------------------------------------------------------ دنیا (قیمت‌ها / نرخ بانک مرکزی)
def new_world():
    return {"_id": "world", "rate": 0.02, "reserve": 0.0, "mid": dict(config.MID0), "news": [],
            "fx": {k: {"p": a["p0"], "h": [a["p0"]]} for k, a in ASSETS.items()}}


def apply_rates():
    r = WORLD["rate"]
    E.RATE["dep"], E.RATE["loan"] = r * 0.5, r + 0.03


async def init_world():
    global WORLD
    WORLD = await db.META.find_one({"_id": "world"}) or new_world()
    base = new_world()
    for k in ("mid", "fx"):
        for kk, v in base[k].items():
            WORLD[k].setdefault(kk, v)
    apply_rates()
    await save_world()


async def save_world():
    await db.META.replace_one({"_id": "world"}, WORLD, upsert=True)


def world_step(total_dep=0.0, total_loan=0.0):
    """هر FX_STEP ثانیه: نوسان قیمت ارزها/کالاها + سیاست پولی بانک مرکزی."""
    w = WORLD
    for k, a in ASSETS.items():
        f = w["fx"][k]
        p, anchor = f["p"], a["p0"]
        r = 0.03 * math.log(anchor / p) + a["vol"] * random.gauss(0, 1)
        if random.random() < 0.04:
            s = random.choice((-1, 1)) * random.uniform(0.08, 0.18)
            r += s
            w["news"] = (w["news"] + [("📈 جهش" if s > 0 else "📉 سقوط") + f" {a['e']} {a['n']}: {s * 100:+.0f}٪"])[-5:]
        f["p"] = max(anchor * 0.15, min(anchor * 6, p * math.exp(r)))
        f["h"] = (f["h"] + [f["p"]])[-48:]
    for k, base in config.MID0.items():
        m = w["mid"][k]
        m *= math.exp(0.05 * math.log(base / m) + 0.02 * random.gauss(0, 1))
        w["mid"][k] = max(base * 0.4, min(base * 3, m))
    credit = total_loan / (total_dep + total_loan + 1)
    w["rate"] = round(max(0.01, min(0.08, 0.015 + 0.05 * credit)), 4)
    if w.get("rate_lock") is not None:       # ادمین نرخ رو قفل کرده
        w["rate"] = w["rate_lock"]
    apply_rates()


def spark(h):
    if len(h) < 2:
        return "▁"
    lo, hi = min(h), max(h)
    return "".join("▁▂▃▄▅▆▇█"[0 if hi == lo else int((x - lo) / (hi - lo) * 7)] for x in h[-16:])


# ------------------------------------------------------------------ بانک
def bank(c):
    return c["bank"]


def bank_deposit(c, amt):
    b = c["bank"]
    if amt <= 0 or c["treasury"] < amt:
        return False, "💸 سکه‌ت کافی نیست"
    if b["dep"] + amt > config.DEP_MAX:
        return False, f"سقف سپرده {config.DEP_MAX:,} سکه است"
    c["treasury"] -= amt
    b["dep"] += amt
    prog.bump(c, "deposit")
    return True, f"🏦 {amt:,} سکه سپرده شد؛ از غارت امنه 😉"


def bank_withdraw(c, amt):
    b = c["bank"]
    if amt <= 0 or b["dep"] < amt:
        return False, "سپرده‌ت کمتر از اینه"
    b["dep"] -= amt
    c["treasury"] += amt
    return True, f"💰 {amt:,} سکه برداشت شد"


def bank_borrow(c, amt):
    b = c["bank"]
    room = E.credit_limit(c) - b["loan"]
    if amt <= 0:
        return False, "؟"
    if amt > room:
        return False, f"سقف اعتبار تو {max(0, int(room)):,} سکه‌ی دیگه‌ست"
    b["loan"] += amt
    c["treasury"] += amt * (1 - config.LOAN_FEE)
    return True, f"🏛 وام {amt:,} سکه گرفتی (کارمزد {config.LOAN_FEE * 100:.0f}٪)"


def bank_repay(c, amt):
    b = c["bank"]
    amt = min(amt, int(b["loan"] + 0.999))
    if amt <= 0 or b["loan"] <= 0:
        return False, "وامی نداری 😊"
    if c["treasury"] < amt:
        return False, "💸 سکه‌ت کافی نیست"
    c["treasury"] -= amt
    b["loan"] = max(0.0, b["loan"] - amt)
    return True, f"✅ {amt:,} سکه از وامت پرداخت شد؛ آفرین!"


# ------------------------------------------------------------------ بازار (قیمت جهانی)
def prices(item):
    m = WORLD["mid"][item]
    return m * (1 + config.MARKET_SPREAD), m * (1 - config.MARKET_SPREAD)   # خرید، فروش


def _move_mid(item, qty, sign):
    base = config.MID0[item]
    m = WORLD["mid"][item] * (1 + sign * 0.5 * qty / config.MARKET_LIQ[item])
    WORLD["mid"][item] = max(base * 0.4, min(base * 3, m))


def global_buy(c, item, qty):
    if item not in ITEMS or qty <= 0:
        return False, "؟"
    cost = math.ceil(prices(item)[0] * qty)
    if c["treasury"] < cost:
        return False, f"💸 {cost:,} سکه لازمه"
    c["treasury"] -= cost
    c[item] += qty
    _move_mid(item, qty, +1)
    prog.bump(c, "trade")
    c["st"]["trades"] = c["st"].get("trades", 0) + 1
    return True, f"{ITEMS[item][0]} +{qty:,} {ITEMS[item][1]} (−{cost:,} سکه)"


def global_sell(c, item, qty):
    if item not in ITEMS or qty <= 0:
        return False, "؟"
    if c[item] < qty:
        return False, f"{ITEMS[item][1]} کافی نیست"
    gain = int(prices(item)[1] * qty)
    c[item] -= qty
    c["treasury"] += gain
    _move_mid(item, qty, -1)
    prog.bump(c, "trade")
    c["st"]["trades"] = c["st"].get("trades", 0) + 1
    return True, f"{ITEMS[item][0]} −{qty:,} {ITEMS[item][1]} (+{gain:,} سکه)"


# ------------------------------------------------------------------ بازار آزاد (آگهی بازیکن‌ها)
async def list_create(c, item, qty, price):
    if item not in ITEMS or qty <= 0 or price <= 0:
        return False, "مثال: آگهی فولاد 100 6"
    mid = WORLD["mid"][item]
    if not mid * 0.6 <= price <= mid * 1.8:
        return False, f"قیمت باید بین {mid * 0.6:.1f} و {mid * 1.8:.1f} باشه"
    if c[item] < qty:
        return False, f"{ITEMS[item][1]} کافی نیست"
    if await db.M.count_documents({"seller": c["_id"]}) >= config.LIST_MAX:
        return False, f"حداکثر {config.LIST_MAX} آگهی فعال"
    c[item] -= qty
    lid = await db.next_id("listing")
    await db.M.insert_one({"_id": lid, "seller": c["_id"], "item": item, "qty": qty, "price": price, "ts": time.time()})
    return True, f"📣 آگهی #{lid}: {qty:,} {ITEMS[item][1]} × {price} سکه"


async def list_take(c, lid, qty):
    li = await db.M.find_one({"_id": lid})
    if not li:
        return False, "این آگهی وجود نداره"
    if li["seller"] == c["_id"]:
        return False, "آگهی خودته؛ بنویس «لغو آگهی شماره»"
    qty = min(qty or li["qty"], li["qty"])
    cost = qty * li["price"]
    if qty <= 0 or c["treasury"] < cost:
        return False, f"💸 {cost:,} سکه لازمه"
    s = await db.load(li["seller"])
    if not s:
        await db.M.delete_one({"_id": lid})
        return False, "فروشنده پیدا نشد"
    fee = int(cost * config.LIST_FEE)
    c["treasury"] -= cost
    c[li["item"]] += qty
    s["treasury"] += cost - fee
    s["st"]["trades"] = s["st"].get("trades", 0) + 1
    c["st"]["trades"] = c["st"].get("trades", 0) + 1
    prog.bump(c, "trade")
    WORLD["reserve"] += fee
    if qty >= li["qty"]:
        await db.M.delete_one({"_id": lid})
    else:
        await db.M.update_one({"_id": lid}, {"$inc": {"qty": -qty}})
    await db.save(s)
    return True, (f"🛒 {qty:,} {ITEMS[li['item']][1]} خریدی (−{cost:,})", s["_id"], cost - fee)


async def list_cancel(c, lid):
    li = await db.M.find_one({"_id": lid})
    if not li or li["seller"] != c["_id"]:
        return False, "آگهی تو نیست"
    c[li["item"]] += li["qty"]
    await db.M.delete_one({"_id": lid})
    return True, f"آگهی #{lid} لغو شد و کالا برگشت"


# ------------------------------------------------------------------ ارز و توکن
def fx_price(sym):
    return WORLD["fx"][sym]["p"]


def fx_change(sym):
    h = WORLD["fx"][sym]["h"]
    return (h[-1] / h[-2] - 1) * 100 if len(h) > 1 else 0.0


def _impact(sym, value, sign):
    a = ASSETS[sym]
    f = WORLD["fx"][sym]
    f["p"] = max(a["p0"] * 0.15, min(a["p0"] * 6, f["p"] * (1 + sign * 0.5 * value / config.FX_LIQ)))


def fx_buy(c, sym, qty):
    if sym not in ASSETS or qty <= 0:
        return False, "؟"
    p = fx_price(sym)
    cost = math.ceil(qty * p * (1 + config.FX_FEE))
    if c["treasury"] < cost:
        return False, f"💸 {cost:,} سکه لازمه"
    held = c["fx"].get(sym, 0.0)
    avg = c["fxcost"].get(sym, 0.0)
    c["fxcost"][sym] = (held * avg + qty * p) / (held + qty)
    c["fx"][sym] = held + qty
    c["treasury"] -= cost
    WORLD["reserve"] += qty * p * config.FX_FEE
    _impact(sym, qty * p, +1)
    prog.bump(c, "fx")
    prog.bump(c, "trade")
    c["st"]["fx_trades"] = c["st"].get("fx_trades", 0) + 1
    return True, f"{ASSETS[sym]['e']} +{qty:,} {config.sym_name(sym)} @ {p:,.2f} (−{cost:,} سکه)"


def fx_sell(c, sym, qty):
    if sym not in ASSETS or qty <= 0:
        return False, "؟"
    held = c["fx"].get(sym, 0.0)
    if held + 1e-9 < qty:
        return False, f"فقط {held:,.0f} {sym} داری"
    p = fx_price(sym)
    gain = int(qty * p * (1 - config.FX_FEE))
    pl = gain - qty * c["fxcost"].get(sym, 0.0)
    c["fx"][sym] = max(0.0, held - qty)
    c["treasury"] += gain
    WORLD["reserve"] += qty * p * config.FX_FEE
    _impact(sym, qty * p, -1)
    prog.bump(c, "fx")
    prog.bump(c, "trade")
    c["st"]["fx_trades"] = c["st"].get("fx_trades", 0) + 1
    return True, f"{ASSETS[sym]['e']} −{qty:,} {config.sym_name(sym)} @ {p:,.2f} (+{gain:,} سکه · {'سود' if pl >= 0 else 'زیان'} {abs(pl):,.0f})"


def fx_value(c):
    return sum(q * fx_price(s) for s, q in c["fx"].items() if s in ASSETS)


def buy_shield(c):
    cost, hours = config.SHIELD_PHX
    if c["fx"].get("PHX", 0) < cost:
        return False, f"⚡ {cost} زیرو لازمه"
    c["fx"]["PHX"] -= cost
    c["shield_until"] = max(c["shield_until"], E.now()) + hours * 3600
    return True, f"🛡 {hours} ساعت سپر فعال شد (−{cost} زیرو)"


# ------------------------------------------------------------------ درآمد: روزانه / کار / ماموریت
def newbie(c):
    return E.now() - c["created"] < config.STARTER["newbie_days"] * 86400


def daily(c):
    d, t = c["daily"], E.now()
    left = 20 * 3600 - (t - d["last"])
    if left > 0:
        return False, f"⏳ جایزه‌ی بعدی {left / 3600:.1f} ساعت دیگه‌ست"
    streak = d["streak"] + 1 if t - d["last"] < 48 * 3600 else 1
    k, mult = min(streak, 7), (2 if newbie(c) else 1)
    coins, steel, food = int((600 + 150 * k + c.get("gdp", 0) * 0.4) * mult * config.DAILY_MULT), 5 * k * mult, 100 * k * mult
    phx = 2 if streak % 7 == 0 else 0
    c["treasury"] += coins
    c["steel"] += steel
    c["food"] += food
    if phx:
        c["fx"]["PHX"] = c["fx"].get("PHX", 0) + phx
    d["last"], d["streak"] = t, streak
    prog.bump(c, "daily")
    return True, (f"🎁 جایزه‌ی روز {streak}{' (×۲ تازه‌کار)' if mult > 1 else ''}: {coins:,}💰 {steel}⚙️ {food}🌾"
                  + (f" · +{phx} ⚡زیرو" if phx else "") + "\nفردا هم بیا، بزرگ‌تر میشه 💛")


def work(c):
    t = E.now()
    left = 2 * 3600 - (t - c["cd2"].get("work", 0))
    if left > 0:
        return False, f"☕ {int(left // 60) + 1} دقیقه‌ی دیگه آماده‌ای"
    coins = random.randint(250, 450) + c.get("gdp", 0) * 0.25
    if newbie(c):
        coins *= 1.5
    r, note = random.random(), "🧳 سفر تجاری موفق"
    if r < 0.08:
        coins, note = coins * 3, "🤝 قرارداد بزرگ بستی!"
    elif r < 0.16:
        coins, note = coins * 0.5, "🚧 تحریم و تأخیر؛ سود کم شد"
    coins = int(coins * config.WORK_MULT)
    c["treasury"] += coins
    c["cd2"]["work"] = t
    prog.bump(c, "work")
    c["st"]["works"] = c["st"].get("works", 0) + 1
    return True, f"{note}: +{coins:,} سکه"


MISSIONS = [
    ("farm3", "۳ مزرعه بساز", lambda c: E.lv(c, "farm") >= 3, dict(coins=1200, food=300)),
    ("power2", "نیروگاه سطح ۲", lambda c: E.lv(c, "power") >= 2, dict(coins=1500)),
    ("police", "پلیس بساز", lambda c: E.lv(c, "police") >= 1, dict(coins=1000)),
    ("barracks", "پادگان بساز", lambda c: E.lv(c, "barracks") >= 1, dict(coins=1500, steel=30)),
    ("factory", "کارخانه بساز", lambda c: E.lv(c, "factory") >= 1, dict(coins=2000, steel=60)),
    ("inf300", "۳۰۰ پیاده‌نظام داشته باش", lambda c: c["units"].get("inf", 0) >= 300, dict(coins=1500)),
    ("daily", "جایزه‌ی روزانه بگیر", lambda c: c["daily"]["streak"] >= 1, dict(coins=500)),
    ("work", "۳ بار «کار» کن", lambda c: c["st"].get("works", 0) >= 3, dict(coins=1000)),
    ("deposit", "۵٬۰۰۰ سکه سپرده‌ی بانکی", lambda c: c["bank"]["dep"] >= 5000, dict(coins=1000, phx=1)),
    ("npc1", "یک NPC رو شکست بده", lambda c: c["st"].get("npc_wins", 0) >= 1, dict(coins=3000, phx=2)),
    ("fx", "یک معامله‌ی ارزی انجام بده", lambda c: c["st"].get("fx_trades", 0) >= 1, dict(coins=1000, phx=1)),
    ("market", "یک معامله‌ی بازار انجام بده", lambda c: c["st"].get("trades", 0) >= 1, dict(coins=800)),
    ("upgrade", "یک شاخه‌ی نظامی رو ارتقا بده", lambda c: sum(c["upg"].values()) >= 1, dict(coins=2000)),
    ("ally", "عضو یک اتحاد (گروه) شو", lambda c: bool(c.get("alliance")), dict(coins=2000, phx=1)),
    ("npc3", "۳ بار NPC رو شکست بده", lambda c: c["st"].get("npc_wins", 0) >= 3, dict(coins=5000, phx=3)),
]


def _rew(r):
    p = []
    for k, e in (("coins", "💰"), ("steel", "⚙️"), ("food", "🌾"), ("phx", "⚡")):
        if r.get(k):
            p.append(f"{r[k]:,}{e}")
    return " ".join(p)


def missions_text(c):
    out = []
    for mid, title, chk, rew in MISSIONS:
        st = "🎖" if mid in c["done"] else ("✅" if chk(c) else "⬜")
        out.append(f"{st} {title} — {_rew(rew)}")
    return out


def claim(c):
    got, lines = {}, []
    for mid, title, chk, rew in MISSIONS:
        if mid not in c["done"] and chk(c):
            c["done"].append(mid)
            lines.append(title)
            for k, v in rew.items():
                got[k] = got.get(k, 0) + v
    if got:
        prog.give(c, got)
    g2, t2 = prog.claim(c)              # روزانه و هفتگی (جایزه‌شون خودش داخل prog.claim داده میشه)
    for k, v in g2.items():
        got[k] = got.get(k, 0) + v
    lines += t2
    if not lines:
        return False, "هنوز ماموریت آماده‌ای نداری؛ بزن به کار 💪"
    return True, f"🎖 {len(lines)} ماموریت تحویل شد: {prog.rew_text(got)}"
