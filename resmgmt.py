"""🏗 مدیریت منابع: ساختمان‌های «تعدادی» (مثلاً ۱۰۰۰ بیمارستان).

بخش «ساختمان» فقط برای فناوری و سطح‌هاست؛ اینجا تعداد مهمه. اثر هر نوع با «پوشش» حساب میشه:
    پوشش = تعداد × (نفری که هر واحد سرویس میده) ÷ جمعیت
    اثر  = 1 − e^(−پوشش)        (۰ تا ۱؛ پوشش ۱ ≈ ۶۳٪ اثر کامل، پوشش ۳ ≈ ۹۵٪)
پس جمعیت بیشتر = تعداد بیشتر لازم. سقف تعداد هر نوع هم به تعداد استان‌ها بستگی داره (per_land × استان).
اثرها شبیه بخش «سیاست و بودجه»ـن (سواد، سلامت، امنیت، رفاه، روحیه‌ی ارتش، بهره‌وری) ولی با ساخت‌وساز تعدادی.
"""
import math

import config
import prog

# n=اسم e=ایموجی cost=قیمت هر واحد up=نگهداری هر واحد در ساعت per=جمعیتی که هر واحد پوشش میده (۰ = اثر مستقیم)
# per_land=سقف تعداد به‌ازای هر استان jobs=شغل هر واحد d=توضیح اثر
RM = {
    "hospital":   dict(n="بیمارستان", e="🏥", cost=700, up=0.9, per=500, per_land=60, jobs=12, d="سلامت ↑ (تا +۴۵) · تلفات جنگی کمتر"),
    "school":     dict(n="مدرسه", e="🏫", cost=450, up=0.5, per=400, per_land=80, jobs=8, d="سواد ↑ (تا +۲۰)"),
    "university": dict(n="دانشگاه", e="🎓", cost=1800, up=2.0, per=1500, per_land=25, jobs=20, d="سواد ↑ (تا +۲۰) · پژوهش +۰٫۴/ساعت هر واحد"),
    "police":     dict(n="ماشین پلیس", e="🚓", cost=350, up=0.4, per=250, per_land=100, jobs=4, d="امنیت ↑ (تا +۴۰)"),
    "welfare":    dict(n="مرکز رفاه", e="🤲", cost=500, up=0.8, per=600, per_land=50, jobs=10, d="رضایت مردم ↑ (تا +۱۰)"),
    "base":       dict(n="پایگاه نظامی", e="🪖", cost=900, up=1.0, per=1200, per_land=30, jobs=15, d="روحیه‌ی ارتش ↑ (تا +۱۵٪)"),
    "roads":      dict(n="راه‌ساز", e="🛣", cost=600, up=0.5, per=1000, per_land=40, jobs=10, d="بهره‌وری کل ↑ (تا +۱۵٪)"),
    "factory":    dict(n="کارخانه‌ی تولیدی", e="🏭", cost=1200, up=1.5, per=0, per_land=40, jobs=40, d="فولاد +۱٫۵/ساعت و ۴۰ شغل هر واحد"),
    "farm":       dict(n="تعاونی کشاورزی", e="🌾", cost=500, up=0.4, per=0, per_land=80, jobs=8, d="غذا +۳/ساعت هر واحد"),
    "plant":      dict(n="نیروگاه کوچک", e="⚡", cost=800, up=0.6, per=0, per_land=40, jobs=5, d="انرژی +۲ هر واحد"),
}
COST_GROWTH = 400          # قیمت هر واحد با هر ۴۰۰ واحدِ موجود یه برابر پایه گرون‌تر میشه

# سقف اثر هر نوع (وقتی پوشش کامل باشه)
EFFECT = {"hospital": 45.0, "school": 20.0, "university": 20.0, "police": 40.0, "welfare": 10.0, "base": 0.15, "roads": 0.15}


def have(c, k):
    return int(c.get("rm", {}).get(k, 0))


def eff(c, k):
    """اثر نوع k از ۰ تا ۱ (۰ = هیچ، ۱ = پوشش کامل)."""
    r = RM[k]
    n = have(c, k)
    if n <= 0 or not r["per"]:
        return 0.0
    return 1 - math.exp(-n * r["per"] / max(1000.0, c["pop"]))


def bonus(c, k):
    """مقدار اثر نوع k (مثلاً +۳۰ سلامت)."""
    return EFFECT.get(k, 0.0) * eff(c, k)


def cap(c, k):
    return int(RM[k]["per_land"] * c.get("land", config.LAND_START))


def jobs(c):
    return sum(have(c, k) * r["jobs"] for k, r in RM.items())


def upkeep(c):
    return sum(have(c, k) * r["up"] for k, r in RM.items())


def unit_cost(c, k):
    return RM[k]["cost"] * (1 + have(c, k) / COST_GROWTH)


def cost(c, k, qty):
    """قیمت خرید qty واحد پشت‌سرهم (قیمت با تعداد موجود کم‌کم بالا میره)."""
    n0 = have(c, k)
    return int(RM[k]["cost"] * (qty + (qty * n0 + qty * (qty - 1) / 2.0) / COST_GROWTH))


def max_buy(c, k):
    room = cap(c, k) - have(c, k)
    if room <= 0 or c["treasury"] <= 0:
        return 0
    lo, hi = 0, room
    while lo < hi:                       # بزرگ‌ترین تعدادی که پولش رو داری (قیمت صعودی‌ه، پس جستجوی دودویی)
        mid = (lo + hi + 1) // 2
        if cost(c, k, mid) <= c["treasury"]:
            lo = mid
        else:
            hi = mid - 1
    return lo


def buy(c, k, qty):
    if k not in RM:
        return False, "؟ نوع نامعتبر"
    if qty == "max":
        qty = max_buy(c, k)
    if qty <= 0:
        return False, f"💸 الان برای {RM[k]['n']} پول یا جا (سقف استان‌ها) نداری"
    room = cap(c, k) - have(c, k)
    if qty > room:
        return False, f"🏞 سقف {RM[k]['n']} با {c.get('land', config.LAND_START)} استان = {cap(c, k):,} (جای {max(0, room):,} تای دیگه داری)"
    price = cost(c, k, qty)
    if c["treasury"] < price:
        return False, f"💸 {price:,} سکه لازمه"
    c["treasury"] -= price
    c.setdefault("rm", {})[k] = have(c, k) + qty
    prog.bump(c, "build")
    r = RM[k]
    return True, f"✅ {qty:,} {r['n']} {r['e']} ساخته شد (−{price:,}💰) · الان {have(c, k):,} تا داری"
