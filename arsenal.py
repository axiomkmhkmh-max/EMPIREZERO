"""زرادخانه‌ی بازی: ۵ بخش (زمینی، هوایی، موشکی، دریایی، پدافند) × ۱۰ مدل معروف تاریخ + ۱ سلاح ویژه‌ی ساخته‌ی بازی.

قدرت هر یگان = حمله + دفاع (پدافند: دفاع · موشک: قدرت تخریب × دقت).
نسبت قدرت به ظرفیت (قدرت ÷ size) برای مدل‌های واقعی بین ۱ تا ۴ است و برای سلاح ویژه‌ی هر بخش دقیقاً ۵ (قیمت‌شون هم گرون‌تره).
باز شدن: ۵ مدل ضعیف‌تر هر بخش از اول بازن؛ مدل ششم تا دهم (به ترتیب قدرت) با کارخانه‌ی سطح ۱۰، ۲۰، ۳۰، ۴۰، ۵۰ باز میشن
و سلاح ویژه با کارخانه‌ی سطح ۶۰.

کلید یگان‌های قدیمی (inf, cmd, tank, arty, htank, drone, heli, jet, bomber, missile, ad, corvette, ship, destroyer, sub, carrier)
حفظ شده تا دیتای بازیکن‌ها نپره؛ فقط اسم و آمارشون به مدل واقعی نزدیک‌ترشون تغییر کرده.
"""

FREE_COUNT = 5                                  # چند مدل از اول بازن
UNLOCK_STEP = 10                                # هر چند سطح کارخانه یه مدل باز میشه
SUPER_UNLOCK = 60                               # سطح کارخانه‌ی سلاح ویژه

# دسته → (ایموجی، اسم، شاخه‌ی جنگی br، ساختمان ضروری، قیمت به‌ازای هر واحد قدرت)
CATS = {
    "land":    ("🪖", "زمینی", "land", None, 30.0),
    "air":     ("✈️", "هوایی", "air", None, 38.0),
    "missile": ("🚀", "موشکی", "air", None, 45.0),
    "sea":     ("🚢", "دریایی", "sea", "port", 40.0),
    "ad":      ("📡", "پدافند", "air", None, 40.0),
}
CAT_ORDER = ("land", "air", "missile", "sea", "ad")

# ردیف: (کلید، اسم، ایموجی، حمله، دفاع، ظرفیت، سرعت)
LAND = [
    ("inf", "پیاده‌نظام AK-47", "🪖", 1, 1.2, 1, 1.0),
    ("cmd", "کماندو SAS", "🥷", 3, 1.6, 2, 1.5),
    ("sherman", "تانک M4 شرمن", "🚜", 7, 5, 9, 1.2),
    ("tank", "تانک T-34", "🚜", 8, 6, 10, 1.2),
    ("arty", "توپخانه M109", "💣", 14, 2, 12, 0.6),
    ("t72", "تانک T-72", "🚜", 15, 12, 14, 1.1),
    ("htank", "تانک تایگر I", "🛡", 20, 16, 20, 0.8),
    ("leo", "تانک لئوپارد ۲", "🚜", 26, 22, 22, 1.1),
    ("abrams", "تانک M1 آبرامز", "🚜", 30, 26, 24, 1.0),
    ("merkava", "تانک مرکاوا", "🛡", 28, 34, 26, 0.9),
]
LAND_SUPER = ("zland", "تانک شبح زیرو", "👹", 60, 50, 22, 1.3)

AIR = [
    ("drone", "پهپاد MQ-9 ریپر", "🛸", 5, 1, 3, 2.2),
    ("p51", "پی-۵۱ موستانگ", "🛩", 8, 5, 9, 2.0),
    ("heli", "بالگرد آپاچی AH-64", "🚁", 12, 6, 12, 1.6),
    ("f4", "اف-۴ فانتوم", "✈️", 18, 8, 18, 2.3),
    ("jet", "اف-۱۶ فالکون", "✈️", 20, 10, 19, 2.4),
    ("bomber", "بمب‌افکن B-52", "🛩", 30, 2, 25, 1.8),
    ("mig29", "میگ-۲۹", "✈️", 22, 12, 20, 2.4),
    ("f14", "اف-۱۴ تامکت", "✈️", 25, 14, 22, 2.4),
    ("su35", "سوخو-۳۵", "✈️", 28, 15, 22, 2.5),
    ("f15", "اف-۱۵ ایگل", "✈️", 30, 18, 23, 2.5),
]
AIR_SUPER = ("zair", "جنگنده شبح زیرو", "🦅", 70, 40, 22, 2.8)

SEA = [
    ("corvette", "ناوچه فلاور", "⛵", 5, 5, 6, 1.5),
    ("dread", "ناو دردنات HMS", "🚢", 10, 10, 12, 0.9),
    ("ship", "رزم‌ناو بیسمارک", "🚢", 12, 10, 15, 1.0),
    ("sub", "زیردریایی کیلو", "🤿", 22, 6, 20, 0.9),
    ("destroyer", "ناوشکن آرلی‌برک", "🔱", 17, 16, 20, 1.2),
    ("iowa", "ناو جنگی آیوا", "🚢", 24, 18, 24, 1.0),
    ("carrier", "ناو هواپیمابر آبراهام لینکلن", "🛳", 28, 20, 40, 0.8),
    ("typhoon", "زیردریایی تایفون", "🤿", 34, 16, 30, 0.8),
    ("yamato", "ناو یاماتو", "🚢", 30, 24, 30, 0.9),
    ("ford", "ناو هواپیمابر جرالد فورد", "🛳", 40, 30, 45, 0.8),
]
SEA_SUPER = ("zsea", "ناو ققنوس زیرو", "🌊", 90, 60, 30, 1.2)

# موشک: (کلید، اسم، ایموجی، قدرت تخریب، دقت، برد به خونه، ظرفیت، سرعت)
MISSILE = [
    ("v2", "موشک V-2", "🚀", 40, 0.50, 12, 20, 3.0),
    ("missile", "موشک اسکاد-B", "🚀", 52, 0.50, 16, 20, 3.0),
    ("fateh", "فاتح-۱۱۰", "🚀", 48, 0.73, 20, 22, 3.0),
    ("tomahawk", "تاماهاک", "🚀", 54, 0.90, 44, 22, 3.2),
    ("shahab", "شهاب-۳", "🚀", 82, 0.60, 38, 26, 3.0),
    ("khaibar", "خیبر", "🚀", 81, 0.80, 52, 26, 3.2),
    ("kalibr", "کالیبر", "🚀", 75, 0.90, 60, 24, 3.2),
    ("iskander", "ایسکندر", "🚀", 80, 0.93, 45, 24, 3.4),
    ("sejjil", "سجیل", "🚀", 150, 0.70, 80, 30, 3.0),
    ("minuteman", "مینیت‌من ۳", "🚀", 152, 0.85, 150, 34, 3.6),
]
MISSILE_SUPER = ("zmis", "موشک قاره‌پیمای زیرو", "☄️", 151, 0.93, 300, 28, 4.0)

# پدافند: (کلید، اسم، ایموجی، دفاع هوایی، ظرفیت، رهگیری موشک به‌ازای هر یگان، سرعت)
AD = [
    ("zu23", "توپ ZU-23-2", "🔫", 4, 4, 0.004, 1.0),
    ("s75", "S-75 دوینا", "📡", 8, 8, 0.008, 1.0),
    ("ad", "هاوک MIM-23", "📡", 11, 9, 0.012, 1.0),
    ("s125", "S-125 پچورا", "📡", 13, 10, 0.014, 1.0),
    ("tor", "تور-ام۱", "📡", 15, 10, 0.016, 1.0),
    ("bavar", "باور-۳۷۳", "📡", 20, 12, 0.020, 1.0),
    ("s300", "S-300", "📡", 24, 13, 0.026, 1.0),
    ("patriot", "پاتریوت PAC-3", "📡", 27, 13, 0.030, 1.0),
    ("thaad", "تاد THAAD", "🛰", 30, 15, 0.045, 1.0),
    ("s400", "S-400", "📡", 32, 14, 0.035, 1.0),
]
AD_SUPER = ("zad", "گنبد ققنوس زیرو", "🔰", 85, 17, 0.08, 1.0)

# قیمت و نگهداری و زمان آموزش سه یگان پایه برای سازگاری با بازی قبلی
_OVERRIDE = {"inf": dict(cost=30, steel=0, up=0.15, t=5), "cmd": dict(cost=90, steel=0, up=0.4, t=12)}


def _finish(key, cat, n, e, atk, dfn, size, spd, power, rank, special=False, **extra):
    emoji, _, br, need, cpp = CATS[cat]
    cost = int(power * cpp * (1 + power / 120.0) * (1.9 if special else 1.0))
    unlock = SUPER_UNLOCK if special else (0 if rank < FREE_COUNT else (rank - FREE_COUNT + 1) * UNLOCK_STEP)
    req = {}
    if unlock:
        req["factory"] = unlock
    if need:
        req[need] = 1
    u = dict(n=n, e=e, cost=cost, steel=int(cost * 0.07), up=round(power * (0.07 if cat == "missile" else 0.12), 2),
             atk=atk, dfn=dfn, size=size, br=br, t=max(5, int(power * 3.2)), spd=spd, req=req,
             cat=cat, rank=rank, unlock=unlock, special=special, power=round(power, 2),
             ratio=round(power / size, 2))
    u.update(extra)
    u.update(_OVERRIDE.get(key, {}))
    return key, u


def build():
    out = {}
    for cat, rows, sup in (("land", LAND, LAND_SUPER), ("air", AIR, AIR_SUPER), ("sea", SEA, SEA_SUPER)):
        ranked = sorted(rows, key=lambda r: r[3] + r[4])
        for i, (k, n, e, atk, dfn, size, spd) in enumerate(ranked):
            kk, u = _finish(k, cat, n, e, atk, dfn, size, spd, atk + dfn, i)
            out[kk] = u
        k, n, e, atk, dfn, size, spd = sup
        kk, u = _finish(k, cat, "⭐ " + n, e, atk, dfn, size, spd, atk + dfn, len(ranked), special=True)
        out[kk] = u
    ranked = sorted(MISSILE, key=lambda r: r[3] * r[4])
    for i, (k, n, e, dmg, acc, rng, size, spd) in enumerate(ranked):
        kk, u = _finish(k, "missile", n, e, 0, 0, size, spd, dmg * acc, i, dmg=dmg, acc=acc, rng=rng)
        out[kk] = u
    k, n, e, dmg, acc, rng, size, spd = MISSILE_SUPER
    kk, u = _finish(k, "missile", "⭐ " + n, e, 0, 0, size, spd, dmg * acc, len(ranked), special=True, dmg=dmg, acc=acc, rng=rng)
    out[kk] = u
    ranked = sorted(AD, key=lambda r: r[3])
    for i, (k, n, e, dfn, size, icpt, spd) in enumerate(ranked):
        kk, u = _finish(k, "ad", n, e, 0, dfn, size, spd, dfn, i, icpt=icpt)
        out[kk] = u
    k, n, e, dfn, size, icpt, spd = AD_SUPER
    kk, u = _finish(k, "ad", "⭐ " + n, e, 0, dfn, size, spd, dfn, len(ranked), special=True, icpt=icpt)
    out[kk] = u
    return out


UNITS = build()


def by_cat(cat):
    """یگان‌های یک بخش به ترتیب قدرت (ضعیف ← قوی، سلاح ویژه آخر)."""
    return sorted((k for k, u in UNITS.items() if u["cat"] == cat), key=lambda k: (UNITS[k]["special"], UNITS[k]["power"]))
