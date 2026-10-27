"""📍 مختصات، فاصله، همسایگی و برنامه‌ی لشکرکشی.

هر کشور یه پایتخت ثابت روی نقشه داره (شماره‌ی «seed» که یه‌بار تخصیص داده میشه و برای همیشه می‌مونه).
از روی جای پایتخت‌ها فاصله (به خونه‌ی شش‌ضلعی) و قاره‌ی هر کشور معلومه. با همین‌ها:
  🤝 همسایه‌ها (فقط روی اون‌ها «تسخیر» ممکنه)
  🚢 هزینه‌ی حمل‌ونقل و ⏱ زمان رسیدن لشکر (بسته به فاصله، مقدار و نوع ارتش اعزامی)
  📏 برد هر شاخه (زمینی فقط روی یه قاره · دریایی با بندر · هوایی با کارخانه)
محاسبه‌ها «خالص»ن (بدون دیتابیس) تا راحت تست بشن؛ فقط بخش بارگذاری به db وصله.
"""
import asyncio
import math
import time

import config
import worldmap
from config import U

CACHE = {"tier": None, "ts": 0.0, "pos": {}, "total": 0, "pending": 0, "players": 0, "banned": set()}
SEEDS = {"m": {}, "loaded": False}
_SEED_LOCK = None
TTL = 120


def now():
    return time.time()


# ------------------------------------------------------------------ پایتخت‌ها (seed) و بارگذاری
def _lock():
    global _SEED_LOCK
    if _SEED_LOCK is None:
        _SEED_LOCK = asyncio.Lock()
    return _SEED_LOCK


async def seeds(ids):
    """پایتخت هر کشور برای همیشه ثابته (توی دیتابیس نگه‌داری میشه) تا نقشه و فاصله‌ها جابه‌جا نشن.
    کشورِ تازه به ترتیب ثبت‌نام، شماره‌ی بعدی رو می‌گیره."""
    import db
    async with _lock():
        if not SEEDS["loaded"]:
            doc = await db.META.find_one({"_id": "mapseeds"}) or {}
            SEEDS["m"] = {str(k): int(v) for k, v in doc.get("m", {}).items()}
            fl = await db.META.find_one({"_id": "maptier"}) or {}
            worldmap.TIER_FLOOR = max(worldmap.TIER_FLOOR, int(fl.get("v", 0)))     # نقشه هیچ‌وقت کوچیک‌تر نمیشه
            SEEDS["floor_saved"] = int(fl.get("v", 0))
            SEEDS["loaded"] = True
        m = SEEDS["m"]
        nxt = max(list(m.values()) + [-1]) + 1
        changed = False
        for cid in ids:
            if str(cid) not in m:
                m[str(cid)] = nxt
                nxt += 1
                changed = True
        if changed:
            await db.META.replace_one({"_id": "mapseeds"}, {"_id": "mapseeds", "m": m}, upsert=True)
        return {int(k): int(v) for k, v in m.items()}


async def refresh(force=False, need=None):
    """موقعیت همه‌ی کشورها رو (هر ۲ دقیقه یا وقتی کشور تازه‌ای پیدا نشد) بروز می‌کنه."""
    import db
    if not force and now() - CACHE["ts"] < TTL and (need is None or need in CACHE["pos"]):
        return CACHE
    docs = await db.C.find({}, {"land": 1, "created": 1, "colony": 1}).to_list(8000)
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    docs.sort(key=lambda d: (d.get("created", 0), d["_id"]))
    total = sum(int(d.get("land", config.LAND_START)) for d in docs if d["_id"] not in banned)       # همون عددی که نقشه برای انتخاب اندازه‌ش می‌گیره
    pending = sum(len(d.get("colony") or []) for d in docs if d["_id"] not in banned)
    sd = await seeds([d["_id"] for d in docs])                                  # (اول seeds تا کف اندازه‌ی نقشه از دیتابیس بیاد)
    players = sum(1 for d in docs if d["_id"] not in banned)
    tier = worldmap.pick_tier(total, players)                                   # نقشه خودکار با تعداد کشورها بزرگ میشه
    if tier > SEEDS.get("floor_saved", 0):
        SEEDS["floor_saved"] = tier
        await db.META.replace_one({"_id": "maptier"}, {"_id": "maptier", "v": tier}, upsert=True)
    W, H, nb, cells, pts, elev = worldmap.make_world(tier)
    cont = worldmap.continents(tier)
    pos = {}
    for d in docs:
        if not pts:
            continue
        cell = pts[sd.get(d["_id"], 0) % len(pts)]
        x, y = worldmap.cell_xy(tier, cell)
        pos[d["_id"]] = dict(cell=cell, x=x, y=y, cont=cont.get(cell, -1))
    CACHE.update(tier=tier, ts=now(), pos=pos, total=total, pending=pending, players=players, banned=banned)
    return CACHE


def dist(a, b):
    """فاصله‌ی دو کشور (به خونه)؛ یا None اگه یکی‌شون روی نقشه نیست."""
    pa, pb = CACHE["pos"].get(a), CACHE["pos"].get(b)
    if not pa or not pb:
        return None
    return math.hypot(pa["x"] - pb["x"], pa["y"] - pb["y"])


def same_continent(a, b):
    pa, pb = CACHE["pos"].get(a), CACHE["pos"].get(b)
    return bool(pa and pb and pa["cont"] == pb["cont"] and pa["cont"] != -1)


def neighbors(uid):
    """{id همسایه: فاصله}؛ همون قاره و ≤ NEIGHBOR_R خونه، به‌علاوه‌ی نزدیک‌ترین‌ها تا شعاع دوم (جلوی بن‌بست توی بازی خلوت)."""
    me = CACHE["pos"].get(uid)
    if not me:
        return {}
    same = []
    for oid, p in CACHE["pos"].items():
        if oid == uid or oid in CACHE["banned"] or p["cont"] != me["cont"]:
            continue
        same.append((math.hypot(p["x"] - me["x"], p["y"] - me["y"]), oid))
    same.sort()
    out = {oid: d for d, oid in same if d <= config.NEIGHBOR_R}
    for d, oid in same[:config.NEIGHBOR_NEAREST]:
        if d <= config.NEIGHBOR_R2:
            out.setdefault(oid, d)
    return out


def is_neighbor(a, b):
    return b in neighbors(a)


def free_cells():
    """زمین خالیِ فعلی نقشه (خونه‌ی خشکیِ بدون صاحب)."""
    tier = CACHE["tier"] if CACHE["tier"] is not None else max(config.MAP_MIN_TIER, worldmap.TIER_FLOOR)
    return max(0, len(worldmap.make_world(tier)[3]) - CACHE["total"] - CACHE["pending"])


# ------------------------------------------------------------------ برنامه‌ی لشکرکشی (خالص)
def _lv(c, k):
    return c["buildings"].get(k, 0)


def ranges(c):
    """برد هر شاخه به خونه."""
    return {"land": config.RANGE_LAND,
            "sea": config.RANGE_SEA[0] + config.RANGE_SEA[1] * _lv(c, "port"),
            "air": config.RANGE_AIR[0] + config.RANGE_AIR[1] * _lv(c, "factory")}


def reachable(c, d, same_cont):
    """شاخه‌هایی که به این فاصله می‌رسن."""
    rg = ranges(c)
    ok = set()
    for br, r in rg.items():
        if d <= r and (br != "land" or same_cont):
            ok.add(br)
    return ok


def pick_sent(c, pct, mode, ok_branches):
    """یگان‌های اعزامی برای نوع حمله‌ی mode (همه‌جانبه یا ترکیب دلخواه شاخه‌ها) با pct٪ ارتش، فقط از شاخه‌هایی که برد دارن."""
    brs = set(config.mode_branches(mode)) & set(ok_branches)
    u = c["units"]
    sent = {k: int(u.get(k, 0) * pct / 100) for k, d in U.items() if d["atk"] > 0 and d["br"] in brs}
    if "air" in brs:
        sent["missile"] = int(u.get("missile", 0) * pct / 100)
    return {k: v for k, v in sent.items() if v > 0}


def sent_size(sent):
    return sum(v * U[k]["size"] for k, v in sent.items())


def travel_secs(c, sent, d):
    """زمان رسیدن: کندترین یگانِ اعزامی تعیین‌کننده‌ست؛ بودجه‌ی راه و زیرساخت سرعت رو بالا می‌بره."""
    t = 0.0
    for k, v in sent.items():
        if v > 0:
            t = max(t, d * config.MARCH_BASE[U[k]["br"]] / U[k]["spd"])
    t /= 1 + config.MARCH_SPEED_INFRA * c.get("budget", {}).get("infra", 0)
    return int(max(config.MARCH_MIN_S, min(config.MARCH_MAX_S, t)))


def transport_cost(sent, d):
    return int(sum(v * U[k]["size"] * config.TRANSPORT[U[k]["br"]] for k, v in sent.items()) * d * config.TRANSPORT_MULT)


def plan(c, pct, mode, d, same_cont):
    """(نقشه یا None، پیام خطا). نقشه = dict(sent, secs, transport, size, mode, dist, dropped)"""
    mode = config.norm_mode(mode)
    ok = reachable(c, d, same_cont)
    want = list(config.mode_branches(mode))
    if not set(want) & ok:
        rg = ranges(c)
        if len(want) > 1:
            return None, "📏 هیچ‌کدوم از شاخه‌های انتخابی (از نظر برد یا قاره) به این کشور نمی‌رسن؛ نوع دیگه‌ای انتخاب کن"
        br = want[0]
        if br == "land" and not same_cont:
            return None, "🪖 نیروی زمینی نمی‌تونه از دریا رد بشه (اون کشور روی قاره‌ی دیگه‌ست)؛ حمله‌ی «دریایی» یا «هوایی» بزن"
        need = "بندر نظامی" if br == "sea" else "کارخانه" if br == "air" else ""
        return None, (f"📏 برد نیروی {config.BRANCH_N[br]} تو {rg[br]} خونه‌ست ولی فاصله {d:.0f} خونه‌ست"
                      + (f" (با ارتقای {need} بیشتر میشه)" if need else ""))
    dropped = sorted(br for br in want if br not in ok)
    sent = pick_sent(c, pct, mode, ok)
    if not any(U[k]["atk"] > 0 for k in sent):
        return None, "🪖 برای این نوع حمله یگانِ آماده‌ای نداری"
    return dict(sent=sent, size=sent_size(sent), secs=travel_secs(c, sent, d), transport=transport_cost(sent, d),
                mode=mode, dist=d, dropped=dropped), None
