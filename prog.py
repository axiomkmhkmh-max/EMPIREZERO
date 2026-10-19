"""شمارنده‌ها، هفته/فصل رسمی و ماموریت‌های روزانه/هفتگی.
فقط به config وابسته‌ست (هیچ import دیگه‌ای نداره) تا engine و بقیه راحت ازش استفاده کنن."""
import random
import time
from datetime import date, datetime, timedelta, timezone

TEHRAN = timezone(timedelta(hours=3, minutes=30))     # ایران ساعت تابستانی نداره؛ آفست ثابت کافیه
WEEK = {"id": -1}        # هفته‌ی رسمی (فقط world.finalize_week عوضش می‌کنه تا آمار هفته‌ی قبل نپره)
SEASON = {"id": 1}       # فصل رسمی

_EPOCH = date(1970, 1, 1)


def now():
    return time.time()


def day_id(t=None):
    return datetime.fromtimestamp(t or now(), TEHRAN).strftime("%Y-%m-%d")


def calc_week(t=None):
    """شناسه‌ی هفته؛ هفته‌ی ایرانی از شنبه شروع میشه (۱۹۷۰-۰۱-۰۱ پنجشنبه بود)."""
    d = datetime.fromtimestamp(t or now(), TEHRAN).date()
    return ((d - _EPOCH).days - 2) // 7


def week_end_ts(wid):
    """ساعت ۰۰:۰۰ شنبه‌ی بعد از هفته‌ی wid (به وقت تهران)."""
    d = _EPOCH + timedelta(days=7 * wid + 9)
    return datetime(d.year, d.month, d.day, tzinfo=TEHRAN).timestamp()


def dur(s):
    """مدت به فارسی: «۲ ساعت و ۱۰ دقیقه»."""
    s = int(max(0, s))
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d} روز" + (f" و {h} ساعت" if h else "")
    if h:
        return f"{h} ساعت" + (f" و {m} دقیقه" if m else "")
    if m:
        return f"{m} دقیقه"
    return f"{s} ثانیه"


# ------------------------------------------------------------------ شمارنده‌ها
def roll(c):
    """اگه روز/هفته/فصل عوض شده باشه شمارنده‌های همون دوره رو صفر می‌کنه."""
    d = day_id()
    dm = c.get("dm")
    if not isinstance(dm, dict) or dm.get("d") != d:
        c["dm"] = {"d": d, "p": {}, "done": []}
    w = WEEK["id"]
    if w == -1:                 # هفته‌ی رسمی هنوز از world.init نیومده؛ آمار هفتگی رو دست نزن
        c.setdefault("wm", {"w": -1, "p": {}, "done": []})
        c.setdefault("wk", {"w": -1, "war": 0.0, "earn": 0.0})
    else:
        wm = c.get("wm")
        if not isinstance(wm, dict) or wm.get("w") != w:
            c["wm"] = {"w": w, "p": {}, "done": []}
        wk = c.get("wk")
        if not isinstance(wk, dict) or wk.get("w") != w:
            c["wk"] = {"w": w, "war": 0.0, "earn": 0.0}
    sn = c.get("sn")
    if not isinstance(sn, dict) or sn.get("s") != SEASON["id"]:
        c["sn"] = {"s": SEASON["id"], "war": 0.0, "earn": 0.0}


def bump(c, key, n=1):
    """یه کار انجام شد (برای ماموریت‌های روزانه/هفتگی)."""
    roll(c)
    for k in ("dm", "wm"):
        p = c[k]["p"]
        p[key] = p.get(key, 0) + n


def add(c, key, v):
    """امتیاز جدول برترین‌ها (هفتگی و فصلی)."""
    roll(c)
    c["wk"][key] = c["wk"].get(key, 0.0) + v
    c["sn"][key] = c["sn"].get(key, 0.0) + v


def stat(c, scope, key):
    """مقدار آمار بدون تغییر دادن سند (برای جدول‌ها). scope: w هفته · s فصل"""
    box = c.get("wk") if scope == "w" else c.get("sn")
    if not isinstance(box, dict):
        return 0.0
    ok = box.get("w") == WEEK["id"] if scope == "w" else box.get("s") == SEASON["id"]
    return float(box.get(key, 0.0)) if ok else 0.0


# ------------------------------------------------------------------ جایزه‌ها
def rew_text(r):
    r = dict(r)
    r["zero"] = r.get("zero", 0) + r.get("phx", 0)
    p = []
    for k, e in (("coins", "💰"), ("steel", "⚙️"), ("food", "🌾"), ("tech", "🔬"), ("zero", "⚡"), ("box", "🎰")):
        if r.get(k):
            p.append(f"{r[k]:,}{e}")
    return " ".join(p)


def give(c, r):
    """جایزه رو به کشور می‌ده (سکه، فولاد، غذا، پژوهش، زیرو، جعبه‌ی شانس)."""
    c["treasury"] += r.get("coins", 0)
    c["steel"] += r.get("steel", 0)
    c["food"] += r.get("food", 0)
    c["tech"] += r.get("tech", 0)
    z = r.get("zero", 0) or r.get("phx", 0)
    if z:
        c["fx"]["PHX"] = c["fx"].get("PHX", 0) + z
    if r.get("box"):
        c.setdefault("lucky", {}).setdefault("bonus", 0)
        c["lucky"]["bonus"] += r["box"]


# ------------------------------------------------------------------ ماموریت‌های روزانه / هفتگی
# (شناسه، عنوان، کلید شمارنده، هدف، جایزه)
DAILY_FIXED = ("d_daily", "جایزه‌ی روزانه بگیر", "daily", 1, dict(coins=400))
DAILY_POOL = [
    ("d_work", "۳ بار «کار» کن", "work", 3, dict(coins=800)),
    ("d_build", "یک ساخت یا ارتقا شروع کن", "build", 1, dict(coins=600, steel=20)),
    ("d_train", "۲۰۰ نیرو آموزش بده", "train", 200, dict(coins=700)),
    ("d_camp", "۲ نبرد کمپین انجام بده", "camp", 2, dict(coins=900, zero=1)),
    ("d_attack", "یک بار به بازیکن حمله کن", "attack", 1, dict(coins=1200)),
    ("d_trade", "۲ معامله‌ی بازار", "trade", 2, dict(coins=600, food=150)),
    ("d_fx", "یک معامله‌ی ارزی", "fx", 1, dict(coins=500)),
    ("d_lucky", "جعبه‌ی شانس رایگان رو باز کن", "lucky", 1, dict(coins=500, tech=15)),
    ("d_spy", "یک عملیات جاسوسی", "spy", 1, dict(coins=700, tech=20)),
    ("d_dep", "توی بانک سپرده بگذار", "deposit", 1, dict(coins=500)),
    ("d_win", "یک نبرد رو ببر", "win", 1, dict(coins=1000, zero=1)),
]
DAILY_ALL = dict(coins=1500, zero=1)      # جایزه‌ی کامل کردن همه‌ی ماموریت‌های روز

WEEKLY_POOL = [
    ("w_work", "۱۵ بار کار کن", "work", 15, dict(coins=4000, zero=2)),
    ("w_camp", "۱۰ نبرد کمپین", "camp", 10, dict(coins=5000, zero=3)),
    ("w_win", "۵ نبرد رو ببر", "win", 5, dict(coins=5000, zero=3)),
    ("w_build", "۴ ساخت یا ارتقا", "build", 4, dict(coins=4000, steel=100)),
    ("w_train", "۲۰۰۰ نیرو آموزش بده", "train", 2000, dict(coins=4500, zero=2)),
    ("w_trade", "۱۰ معامله‌ی بازار یا ارز", "trade", 10, dict(coins=3500, zero=1)),
    ("w_boss", "۳ ضربه به تهدید جهانی", "boss", 3, dict(coins=5000, zero=3)),
    ("w_lucky", "۵ بار جعبه‌ی شانس", "lucky", 5, dict(coins=3000, zero=2)),
    ("w_diplo", "یک هدیه، معامله یا پیمان", "diplo", 1, dict(coins=3000, zero=1)),
]
WEEKLY_ALL = dict(coins=10000, zero=5)


def daily_list(d=None):
    r = random.Random("D" + (d or day_id()))
    return [DAILY_FIXED] + r.sample(DAILY_POOL, 3)


def weekly_list(w=None):
    r = random.Random("W%s" % (WEEK["id"] if w is None else w))
    return r.sample(WEEKLY_POOL, 4)


def status_lines(c):
    """(خطوط روزانه، خطوط هفتگی) برای نمایش."""
    roll(c)
    out = []
    for lst, box in ((daily_list(), c["dm"]), (weekly_list(), c["wm"])):
        lines = []
        for mid, title, key, tgt, rew in lst:
            v = min(tgt, box["p"].get(key, 0))
            st = "🎖" if mid in box["done"] else ("✅" if v >= tgt else "⬜")
            lines.append(f"{st} {title} ({v:,}/{tgt:,}) — {rew_text(rew)}")
        out.append(lines)
    return out


def claim(c):
    """همه‌ی ماموریت‌های روزانه/هفتگی آماده رو تحویل می‌ده. (جایزه‌ی کل، عنوان‌ها)"""
    roll(c)
    got, titles = {}, []
    for lst, box, allr, nm in ((daily_list(), c["dm"], DAILY_ALL, "روزانه"), (weekly_list(), c["wm"], WEEKLY_ALL, "هفتگی")):
        for mid, title, key, tgt, rew in lst:
            if mid not in box["done"] and box["p"].get(key, 0) >= tgt:
                box["done"].append(mid)
                titles.append(title)
                for k, v in rew.items():
                    got[k] = got.get(k, 0) + v
        tag = "all_" + nm
        if tag not in box["done"] and all(m[0] in box["done"] for m in lst):
            box["done"].append(tag)
            titles.append(f"🏅 همه‌ی ماموریت‌های {nm}")
            for k, v in allr.items():
                got[k] = got.get(k, 0) + v
    if got:
        give(c, got)
    return got, titles
