"""رویدادهای هفتگی (ضریب‌های جهانی که ادمین از پنل شروعشون می‌کنه) و رویدادهای دوگزینه‌ای کشور.
این ماژول به بقیه وابسته نیست (db فقط توی تابع‌های ذخیره/بارگذاری import میشه) تا engine هم بتونه ازش استفاده کنه."""
import random
import time

import prog

# kind=نوع ضریب · mult=مقدار (برای نوع بدون ضریب، kind=None مثل جنگ بزرگ)
TYPES = {
    "gold": dict(n="هفته‌ی طلا", e="💰", kind="income", mult=2.0, d="درآمد کشورها ۲ برابر"),
    "loot": dict(n="هفته‌ی غنیمت", e="🏴‍☠️", kind="loot", mult=2.0, d="غنیمت جنگ‌ها ۲ برابر"),
    "build": dict(n="هفته‌ی سازندگی", e="🏗", kind="build", mult=0.5, d="زمان ساخت، ارتقا و آموزش نصف"),
    "science": dict(n="هفته‌ی دانش", e="🔬", kind="research", mult=2.0, d="امتیاز پژوهش ۲ برابر"),
    "war": dict(n="جنگ بزرگ", e="🌑", kind=None, mult=1.0, d="تهدید جهانی؛ همه با هم می‌جنگیم"),
}
STATE = {"list": []}      # [{"id", "type", "start", "end", "by"}]


def now():
    return time.time()


async def load():
    import db
    d = await db.META.find_one({"_id": "events"}) or {}
    STATE["list"] = d.get("list", [])


async def save():
    import db
    await db.META.replace_one({"_id": "events"}, {"_id": "events", "list": STATE["list"][-30:]}, upsert=True)


def active(t=None):
    t = t or now()
    return [e for e in STATE["list"] if e["start"] <= t < e["end"]]


def mult(kind, t=None):
    m = 1.0
    for e in active(t):
        ty = TYPES.get(e["type"])
        if ty and ty["kind"] == kind:
            m *= ty["mult"]
    return m


def weighted(kind, t0, t1):
    """میانگین وزنی ضریب روی بازه‌ی [t0, t1] (برای کسایی که چند ساعت آفلاین بودن)."""
    if t1 - t0 < 1:
        return mult(kind, t1)
    m = 1.0
    for e in STATE["list"]:
        ty = TYPES.get(e["type"])
        if not ty or ty["kind"] != kind:
            continue
        ov = max(0.0, min(t1, e["end"]) - max(t0, e["start"]))
        if ov > 0:
            m *= 1 + (ty["mult"] - 1) * ov / (t1 - t0)
    return m


def start(typ, hours, by=0):
    """رویداد جدید؛ اگه از همین نوع فعال بود، تموم میشه و جایگزین میشه."""
    stop(typ)
    t = now()
    e = {"id": int(t * 1000) % 10 ** 9, "type": typ, "start": t, "end": t + hours * 3600, "by": by}
    STATE["list"].append(e)
    return e


def stop(typ):
    t, n = now(), 0
    for e in STATE["list"]:
        if e["type"] == typ and e["start"] <= t < e["end"]:
            e["end"] = t
            n += 1
    return n


def banner_lines():
    out = []
    for e in active():
        ty = TYPES[e["type"]]
        out.append(f"{ty['e']} <b>{ty['n']}</b> — {ty['d']} · {prog.dur(e['end'] - now())} مانده")
    return out


# ------------------------------------------------------------------ رویدادهای دوگزینه‌ای
def _pct(c, p, lo=0):
    return int(max(lo, max(0.0, c["treasury"]) * p))


def _pay(c, cost):
    cost = min(cost, max(0, int(c["treasury"])))
    c["treasury"] -= cost
    return cost


def _clamp(c):
    for k in ("sat", "literacy", "health", "security", "unrest"):
        c[k] = max(0.0, min(100.0, c[k]))


def _famine_a(c):
    cost = _pay(c, _pct(c, 0.08, 300))
    gain = int(c["pop"] * 0.04 + 500)
    c["food"] += gain
    return f"🚚 غذای اضطراری رسید: +{gain:,}🌾 (−{cost:,}💰)"


def _famine_b(c):
    c["sat"] -= 6
    c["unrest"] += 4
    _clamp(c)
    return "📉 جیره‌بندی شد؛ مردم غر زدن (رضایت −۶، ناآرامی +۴)"


def _fest_a(c):
    cost = _pay(c, _pct(c, 0.05, 200))
    c["sat"] += 10
    c["unrest"] -= 5
    _clamp(c)
    return f"🎆 جشن باشکوه! رضایت +۱۰، ناآرامی −۵ (−{cost:,}💰)"


def _fest_b(c):
    c["sat"] += 3
    _clamp(c)
    return "🎈 جشن ساده برگزار شد (رضایت +۳)"


def _mine_a(c):
    if random.random() < 0.7:
        c["steel"] += 220
        return "⛏ استخراج سریع موفق بود: +۲۲۰⚙️"
    c["steel"] += 80
    c["pop"] *= 0.995
    c["sat"] -= 4
    _clamp(c)
    return "💥 حادثه‌ی معدن! فقط +۸۰⚙️ گرفتی و رضایت ۴ افت کرد"


def _mine_b(c):
    c["steel"] += 70
    return "🛡 استخراج امن و آهسته: +۷۰⚙️"


def _spy_a(c):
    c["security"] += 5
    c["sat"] -= 2
    _clamp(c)
    return "🚔 جاسوس اخراج شد؛ امنیت +۵ (رضایت −۲)"


def _spy_b(c):
    if random.random() < 0.65:
        c["tech"] += 60
        return "🕵️ جاسوس دوجانبه شد: +۶۰🔬"
    loss = _pay(c, _pct(c, 0.04, 100))
    c["security"] -= 4
    _clamp(c)
    return f"🚨 دوجانبه لو رفت! −{loss:,}💰 و امنیت −۴"


def _ref_a(c):
    c["pop"] *= 1.03
    c["food"] = max(0.0, c["food"] - 300)
    c["sat"] -= 3
    c["unrest"] += 2
    _clamp(c)
    return "🫂 پناهجوها پذیرفته شدن: جمعیت +۳٪ (غذا −۳۰۰، رضایت −۳)"


def _ref_b(c):
    c["security"] += 2
    c["sat"] += 1
    _clamp(c)
    return "🚧 مرز بسته شد (امنیت +۲)"


def _loan_a(c):
    amt = int(max(4000, c.get("gdp", 0) * 6))
    c["treasury"] += amt
    c["bank"]["loan"] += int(amt * 1.15)
    return f"🏛 وام خارجی گرفتی: +{amt:,}💰 (بدهی {int(amt * 1.15):,})"


def _loan_b(c):
    c["sat"] = min(100.0, c["sat"] + 1)
    return "🙅 پیشنهاد رد شد؛ مردم از استقلالت تعریف کردن (رضایت +۱)"


def _raid_a(c):
    inf = c["units"].get("inf", 0)
    if random.random() < min(0.85, 0.3 + inf / 2000):
        gain = int(600 + c.get("gdp", 0) * 0.2)
        c["treasury"] += gain
        c["sat"] = min(100.0, c["sat"] + 3)
        return f"⚔️ مهاجمان شکست خوردن! غنیمت +{gain:,}💰"
    c["units"]["inf"] = int(inf * 0.96)
    c["sat"] = max(0.0, c["sat"] - 3)
    return "💀 نبرد سخت بود؛ ۴٪ پیاده‌نظام از دست رفت (رضایت −۳)"


def _raid_b(c):
    cost = _pay(c, _pct(c, 0.06, 300))
    c["sat"] = max(0.0, c["sat"] - 1)
    return f"💸 باج دادی و رفتن (−{cost:,}💰)"


def _arms_a(c):
    if c["treasury"] < 2000:
        return "💸 ۲۰۰۰ سکه نداشتی؛ تاجر رفت"
    c["treasury"] -= 2000
    if random.random() < 0.75:
        c["steel"] += 190
        return "📦 محموله رسید: +۱۹۰⚙️ (−۲۰۰۰💰)"
    return "🤥 تاجر کلاهبردار بود و فرار کرد (−۲۰۰۰💰)"


def _arms_b(c):
    return "🙅 خریدی نکردی؛ تاجر رفت"


def _relic_a(c):
    gain = int(max(1500, c.get("gdp", 0) * 5))
    c["treasury"] += gain
    c["sat"] = max(0.0, c["sat"] - 1)
    return f"🏺 آثار فروخته شد: +{gain:,}💰"


def _relic_b(c):
    c["sat"] = min(100.0, c["sat"] + 5)
    c["tech"] += 25
    return "🏛 موزه‌ی ملی ساخته شد: رضایت +۵ و +۲۵🔬"


def _quake_a(c):
    cost = _pay(c, _pct(c, 0.10, 500))
    c["health"] = min(100.0, c["health"] + 3)
    c["sat"] = min(100.0, c["sat"] + 2)
    return f"🏗 بازسازی کامل انجام شد (−{cost:,}💰، سلامت +۳، رضایت +۲)"


def _quake_b(c):
    cost = _pay(c, _pct(c, 0.03, 150))
    c["sat"] -= 5
    c["health"] -= 4
    c["unrest"] += 3
    _clamp(c)
    return f"⛺ کمک محدود شد (−{cost:,}💰، رضایت −۵، سلامت −۴)"


def _strike_a(c):
    cost = _pay(c, _pct(c, 0.04, 300))
    c["sat"] += 6
    c["unrest"] -= 4
    _clamp(c)
    return f"🤝 دستمزدها بالا رفت (−{cost:,}💰، رضایت +۶، ناآرامی −۴)"


def _strike_b(c):
    c["unrest"] += 8
    c["sat"] -= 5
    c["security"] += 2
    _clamp(c)
    return "🚔 اعتصاب سرکوب شد (ناآرامی +۸، رضایت −۵)"


def _scholar_a(c):
    if c["treasury"] < 1500:
        return "💸 ۱۵۰۰ سکه نداشتی؛ نخبگان رفتن"
    c["treasury"] -= 1500
    c["tech"] += 70
    return "🎓 نخبگان استخدام شدن: +۷۰🔬 (−۱۵۰۰💰)"


def _scholar_b(c):
    return "🙅 رد کردی؛ نخبگان به کشور دیگه رفتن"


# id: (عنوان، متن، (برچسب الف، تابع)، (برچسب ب، تابع))
DIL = {
    "famine": ("🌾 قحطی در راهه!", "خشکسالی انبارها رو خالی کرده. مردم نگرانن.",
               ("🚚 خرید غذای اضطراری (۸٪ خزانه)", _famine_a), ("📉 جیره‌بندی (رضایت ↓)", _famine_b)),
    "festival": ("🎉 جشن ملی", "سالگرد تأسیس کشورته! مردم منتظرن.",
                 ("🎆 جشن باشکوه (۵٪ خزانه)", _fest_a), ("🎈 جشن ساده و رایگان", _fest_b)),
    "mine": ("⛏ معدن جدید کشف شد", "مهندس‌ها می‌گن می‌شه سریع یا امن استخراجش کرد.",
             ("⚡ استخراج سریع (۳۰٪ خطر)", _mine_a), ("🛡 استخراج امن و کم", _mine_b)),
    "spy": ("🕵️ جاسوس خارجی دستگیر شد", "یه جاسوس توی اداره‌ی اطلاعات گیر افتاده.",
            ("🚔 اخراج و تشدید امنیت", _spy_a), ("🎭 تبدیل به جاسوس دوجانبه (۳۵٪ خطر)", _spy_b)),
    "refugee": ("🫂 پناهجوها پشت مرزن", "هزاران نفر پشت مرز منتظر ورودن.",
                ("🤲 پذیرش (جمعیت ↑، غذا و رضایت ↓)", _ref_a), ("🚧 بستن مرز", _ref_b)),
    "loan": ("🏛 پیشنهاد وام خارجی", "یه بانک خارجی وام کلان با بهره‌ی ۱۵٪ پیشنهاد می‌ده.",
             ("✅ پذیرفتن وام", _loan_a), ("🙅 رد کردن", _loan_b)),
    "raiders": ("🏴 مهاجمان مرزی!", "یه گروه مسلح به مرزهات حمله کرده.",
                ("⚔️ نبرد (هرچی پیاده بیشتر، شانس بیشتر)", _raid_a), ("💸 پرداخت باج (۶٪ خزانه)", _raid_b)),
    "arms": ("📦 تاجر اسلحه", "یه تاجر مشکوک فولاد ارزون پیشنهاد می‌ده.",
             ("🛒 خرید (۲۰۰۰ سکه، ۲۵٪ خطر کلاهبرداری)", _arms_a), ("🙅 رد کردن", _arms_b)),
    "relic": ("🏺 آثار باستانی کشف شد", "باستان‌شناس‌ها یه گنج تاریخی پیدا کردن.",
              ("💰 فروش به کلکسیونرها", _relic_a), ("🏛 ساخت موزه‌ی ملی", _relic_b)),
    "quake": ("🌋 زلزله!", "زلزله یه شهر بزرگ رو لرزونده.",
              ("🏗 بازسازی کامل (۱۰٪ خزانه)", _quake_a), ("⛺ کمک محدود (۳٪ خزانه)", _quake_b)),
    "strike": ("✊ اعتصاب کارگران", "کارگرها دستمزد بیشتر می‌خوان.",
               ("🤝 افزایش دستمزد (۴٪ خزانه)", _strike_a), ("🚔 سرکوب اعتصاب", _strike_b)),
    "scholar": ("🎓 نخبگان خارجی", "گروهی دانشمند حاضرن به کشورت بیان.",
                ("📚 استخدام (۱۵۰۰ سکه)", _scholar_a), ("🙅 رد کردن", _scholar_b)),
}
DIL_TTL = 24 * 3600


def pick(c):
    """یه رویداد دوگزینه‌ای انتخاب می‌کنه (تکراریِ قبلی نه)."""
    last = c.get("dil_last")
    return random.choice([k for k in DIL if k != last])


def dil_text(c):
    d = c.get("dil")
    if not d or d["id"] not in DIL:
        return None
    title, text, a, b = DIL[d["id"]]
    left = max(0, DIL_TTL - (now() - d["ts"]))
    return (f"📜 <b>{title}</b>\n{text}\n\n🅰️ {a[0]}\n🅱️ {b[0]}\n\n"
            f"⏳ تصمیم نگیری تا {prog.dur(left)} دیگه خودکار «ب» انتخاب میشه")


def dil_options(c):
    d = c.get("dil")
    if not d or d["id"] not in DIL:
        return None
    _, _, a, b = DIL[d["id"]]
    return a[0], b[0]


def resolve(c, choice, auto=False):
    """تصمیم رو اجرا می‌کنه و متن نتیجه رو برمی‌گردونه."""
    d = c.get("dil")
    if not d or d["id"] not in DIL:
        c["dil"] = None
        return None
    title, _, a, b = DIL[d["id"]]
    fn = a[1] if choice == "a" else b[1]
    msg = fn(c)
    c["dil_last"] = d["id"]
    c["dil"] = None
    c["st"]["dil"] = c["st"].get("dil", 0) + 1
    return f"📜 {title}\n" + ("⏰ (مهلت تموم شد؛ خودکار «ب»)\n" if auto else "") + msg
