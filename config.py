import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_TOKEN_HERE")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "phoenix_nations")     # اسم قدیمی رو نگه داشتم تا دیتای موجود نپره
BOT_NAME = "EMPIRE ZERO"
LOG_CHANNEL = os.getenv("LOG_CHANNEL", "@LogSTMended")   # ربات باید توی این چنل ادمین (با اجازه‌ی ارسال پیام) باشه
OWNER_ID = int(os.getenv("OWNER_ID", "8925078035"))   # مالک اصلی ربات (دسترسی کامل پنل ادمین)

TIME_SCALE = 2          # هر ۱ ساعت واقعی = ۲ ساعت بازی
TICK_MAX_H = 72         # حداکثر ساعت واقعی جبرانی
SHIELD_NEW_H = 24       # سپر کشور تازه
SHIELD_LOSS_H = 8       # سپر بعد از باخت
STRIKE_CD = 30 * 60     # کولداون ضربه در جنگ اتحاد
ALLY_WAR_H = 6          # مدت جنگ اتحادها
ALLY_MAX = 30
MAX_LEVEL = 10

# n=نام e=ایموجی cost=هزینه پایه up=نگهداری/ساعت jobs=شغل en=مصرف انرژی req=پیش‌نیاز d=توضیح
B = {
    "farm":       dict(n="مزرعه", e="🌾", cost=800, up=20, jobs=400, en=0, req={}, d="غذا +۱۲۰/ساعت"),
    "power":      dict(n="نیروگاه", e="⚡", cost=1800, up=50, jobs=150, en=0, req={}, d="انرژی +۱۲۰"),
    "factory":    dict(n="کارخانه", e="🏭", cost=2500, up=60, jobs=600, en=40, req={"power": 1}, d="فولاد +۴۰/ساعت، شغل زیاد"),
    "market":     dict(n="بازار", e="🏪", cost=1500, up=30, jobs=300, en=10, req={}, d="+۶٪ بهره‌وری کل"),
    "school":     dict(n="مدرسه", e="🏫", cost=1200, up=40, jobs=150, en=5, req={}, d="سقف سواد ↑"),
    "university": dict(n="دانشگاه", e="🎓", cost=4000, up=120, jobs=250, en=15, req={"school": 2}, d="سواد ↑ و پژوهش +۸/ساعت"),
    "hospital":   dict(n="بیمارستان", e="🏥", cost=2000, up=70, jobs=200, en=10, req={}, d="سلامت ↑"),
    "police":     dict(n="پلیس", e="🚓", cost=1500, up=50, jobs=200, en=5, req={}, d="امنیت ↑ و دفاع +۳٪"),
    "infra":      dict(n="زیرساخت", e="🛣", cost=3000, up=40, jobs=300, en=5, req={"market": 1}, d="+۱۰٪ بهره‌وری، ظرفیت جمعیت ↑"),
    "intel":      dict(n="سازمان اطلاعات", e="🕵️", cost=3000, up=80, jobs=150, en=10, req={"police": 2}, d="جاسوسی، خرابکاری، ضدجاسوسی"),
    "port":       dict(n="بندر نظامی", e="⚓", cost=3500, up=90, jobs=250, en=10, req={"factory": 1}, d="باز شدن نیروی دریایی و ارتقای دریایی"),
    "barracks":   dict(n="پادگان", e="🏕", cost=2200, up=60, jobs=150, en=10, req={"police": 1}, d="ظرفیت ارتش +۱۵۰۰"),
    "palace":     dict(n="کاخ", e="🏰", cost=6000, up=30, jobs=100, en=0, req={}, max=5, d="سقف سطح ساختمان‌ها ↑، فرمان نظامی و کارگاه ساخت بیشتر"),
}

# cost=سکه steel=فولاد up=نگهداری atk/dfn=قدرت size=ظرفیت پادگان br=شاخه (land/air/sea) t=ثانیه‌ی آموزش هر واحد
# spd=سرعت نسبی توی لشکرکشی (۱ = معمولی؛ کندترین یگانِ اعزامی سرعت کل لشکر رو تعیین می‌کنه)
U = {
    # ---- 🪖 زمینی
    "inf":     dict(n="پیاده‌نظام", e="🪖", cost=30, steel=0, up=0.15, atk=1, dfn=1.2, size=1, br="land", t=5, spd=1.0, req={}),
    "cmd":     dict(n="کماندو", e="🥷", cost=90, steel=0, up=0.4, atk=3, dfn=1.6, size=2, br="land", t=12, spd=1.5, req={"barracks": 2}),
    "tank":    dict(n="تانک", e="🚜", cost=400, steel=30, up=2, atk=8, dfn=6, size=10, br="land", t=45, spd=1.2, req={"factory": 1}),
    "arty":    dict(n="توپخانه", e="💣", cost=600, steel=40, up=2.5, atk=14, dfn=2, size=12, br="land", t=60, spd=0.6, req={"factory": 2, "barracks": 1}),
    "htank":   dict(n="تانک سنگین", e="🛡", cost=1100, steel=80, up=4, atk=20, dfn=16, size=20, br="land", t=110, spd=0.8, req={"factory": 3, "barracks": 2}),
    # ---- ✈️ هوایی
    "drone":   dict(n="پهپاد", e="🛸", cost=250, steel=15, up=0.8, atk=5, dfn=1, size=3, br="air", t=25, spd=2.2, req={"factory": 2}),
    "heli":    dict(n="بالگرد", e="🚁", cost=700, steel=45, up=3, atk=12, dfn=6, size=12, br="air", t=60, spd=1.6, req={"factory": 2}),
    "jet":     dict(n="جنگنده", e="✈️", cost=1000, steel=60, up=5, atk=16, dfn=8, size=20, br="air", t=90, spd=2.4, req={"factory": 2}),
    "bomber":  dict(n="بمب‌افکن", e="🛩", cost=1700, steel=100, up=6, atk=30, dfn=2, size=25, br="air", t=120, spd=1.8, req={"factory": 3}),
    "missile": dict(n="موشک", e="🚀", cost=1500, steel=80, up=2, atk=0, dfn=0, size=25, br="air", t=100, spd=3.0, req={"factory": 3}),
    "ad":      dict(n="پدافند", e="📡", cost=1200, steel=60, up=3, atk=0, dfn=25, size=15, br="air", t=70, spd=1.0, req={"factory": 2}),
    # ---- 🚢 دریایی
    "corvette": dict(n="ناوچه", e="⛵", cost=350, steel=20, up=1.2, atk=5, dfn=5, size=6, br="sea", t=35, spd=1.5, req={"port": 1}),
    "ship":    dict(n="ناو", e="🚢", cost=900, steel=50, up=4, atk=12, dfn=10, size=15, br="sea", t=80, spd=1.0, req={"port": 1, "factory": 1}),
    "destroyer": dict(n="ناوشکن", e="🔱", cost=1300, steel=70, up=4, atk=17, dfn=16, size=20, br="sea", t=95, spd=1.2, req={"port": 2, "factory": 2}),
    "sub":     dict(n="زیردریایی", e="🤿", cost=1500, steel=70, up=5, atk=22, dfn=6, size=20, br="sea", t=120, spd=0.9, req={"port": 2, "factory": 2}),
    "carrier": dict(n="ناو هواپیمابر", e="🛳", cost=4200, steel=180, up=12, atk=28, dfn=20, size=40, br="sea", t=200, spd=0.8, req={"port": 3, "factory": 3}),
}

# شاخه‌های نظامی و ساختمان لازم برای ارتقا
BRANCH = {
    "land": ("🪖", "زمینی", "barracks"),
    "air":  ("✈️", "هوایی", "factory"),
    "sea":  ("🚢", "دریایی", "port"),
}

TECH = {
    "eco": ("📈", "اقتصاد", "+۶٪ بهره‌وری"),
    "mil": ("⚔️", "تهاجمی", "+۸٪ قدرت حمله"),
    "def": ("🛡", "دفاعی", "+۸٪ قدرت دفاع"),
}


# ------------------------------------------------------------------ افزوده‌ها
BASE_ADMINS = {OWNER_ID} | {int(x) for x in os.getenv("ADMINS", "").replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()}
ADMINS = set(BASE_ADMINS)      # پنل ادمین موقع اجرا ادمین‌های اضافه رو هم اینجا می‌ریزه
DAILY_MULT = 1.0         # ضریب جایزه‌ی روزانه (از پنل ادمین قابل تغییر)
WORK_MULT = 1.0          # ضریب درآمد /work
BARE_WORDS = True        # دستورهای فارسی بدون اسلش ("بانک"، "کشور من")
CMD_GAP = 1.2            # فاصله‌ی حداقل بین دو دستور یک کاربر (ثانیه)
NPC_CD = 45 * 60         # کولداون حمله به هر NPC
NPC_FIRST_ID = 1

# --- ثبت‌نام
REG_TRIES = (5, 600)     # حداکثر ۵ تلاش در ۱۰ دقیقه
REG_PENDING_TTL = 900
RESERVED_WORDS = ("http", "www", "t.me", "telegram", "تلگرام", "admin", "ادمین", "مدیر", "ققنوس", "phoenix", "empire zero", "empirezero", "امپایر زیرو")
DOCTRINES = {
    "eco": ("📈", "اقتصادی", "مزرعه و بازار بیشتر، خزانه‌ی بزرگ‌تر"),
    "mil": ("⚔️", "نظامی", "پادگان، پلیس، ۲۵۰ پیاده و فولاد بیشتر"),
    "bal": ("⚖️", "متعادل", "پلیس و خزانه‌ی متوسط"),
}
# بسته‌ی حمایتی بانک مرکزی (پشتوانه‌ی شروع)
STARTER = dict(food=800.0, steel=80.0, phx=3.0, shield_h=24, newbie_days=7)

# --- بانک
DEP_INT_CAP = 100_000    # سقفی که روی‌اش سود سپرده داده میشه
DEP_MAX = 500_000
LOAN_FEE = 0.01

# --- بازار
ITEMS = {"food": ("🌾", "غذا"), "steel": ("⚙️", "فولاد")}
MID0 = {"food": 1.2, "steel": 5.5}
MARKET_LIQ = {"food": 30000, "steel": 2000}
MARKET_SPREAD = 0.25     # خرید = mid*(1+0.25) · فروش = mid*(1-0.25)
LIST_FEE = 0.03
LIST_MAX = 10

# --- ارز و توکن
FX_STEP = 300            # هر ۵ دقیقه یک بروزرسانی قیمت
FX_FEE = 0.01
ASSETS = {
    "PHX": dict(n="زیرو", e="⚡", p0=100.0, vol=0.040),
    "DNR": dict(n="دینار آرداک", e="🪙", p0=40.0, vol=0.025),
    "KRN": dict(n="کرون نوردلند", e="💶", p0=25.0, vol=0.020),
    "SLR": dict(n="سولار زروان", e="💴", p0=8.0, vol=0.030),
}
TOKEN = "PHX"            # نماد داخلی توکن (ثابت برای سازگاری با دیتابیس)
TOKEN_NAME = "زیرو"
TOKEN_E = "⚡"
TOKEN_ALIASES = {"ZERO": "PHX", "زیرو": "PHX", "ZERO⚡": "PHX"}


def sym_name(s):
    return TOKEN_NAME if s == "PHX" else s


SHIELD_PHX = (15, 12)    # ۱۵ توکن = ۱۲ ساعت سپر

# --- کشورهای NPC (واحد: id منفی)
NPCS = [
    dict(name="جمهوری آرداک", tier=1, units=dict(inf=60), treasury=2500, bounty=250),
    dict(name="امارت سرنیا", tier=2, units=dict(inf=150), treasury=6000, bounty=600),
    dict(name="اتحادیه‌ی هورمند", tier=3, units=dict(inf=400, tank=10), treasury=14000, bounty=1400),
    dict(name="پادشاهی کالوین", tier=4, units=dict(inf=700, tank=40, ad=3), treasury=30000, bounty=3200),
    dict(name="فدراسیون نوردلند", tier=5, units=dict(inf=1200, tank=90, jet=12, ship=3, ad=6), treasury=60000, bounty=7000),
    dict(name="امپراتوری زروان", tier=6, units=dict(inf=2500, tank=200, jet=40, ship=10, sub=4, ad=12), treasury=120000, bounty=15000),
]


# ================================================================== سیستم جنگ بزرگ و رشد
# --- زمان‌بندی (سخت‌کردن بازی: دیگه با پول زیاد توی ۲۰ دقیقه مکس نمیشی)
BUILD_T0 = 180           # ثانیه‌ی ساخت سطح ۱ (هر سطح BUILD_GROWTH برابر سخت‌تر)
BUILD_GROWTH = 1.5
BUILD_TIME_MULT = 1.0    # ضریب کلی زمان ساخت/ارتقا (۰ = فوری) · از پنل ادمین قابل تغییر
UPG_T0 = 1200            # ثانیه‌ی ارتقای نیروی سطح ۱
TRAIN_TIME_MULT = 1.0    # ضریب زمان آموزش یگان‌ها (۰ = فوری)
SPEEDUP_SECS = 1200      # هر ۱ زیرو = ۲۰ دقیقه تسریع
SPEEDUP_DAILY = 6 * 3600 # سقف تسریع در روز (۰ = بدون سقف)؛ جلوی «با پول زیاد همه‌چی رو یه‌روزه مکس کردن» رو می‌گیره
LAND_ARMY = 150          # هر استانِ بیشتر از ۵ تا، ظرفیت ارتش رو این‌قدر زیاد می‌کنه
TRAIN_QUEUE_MAX = 8      # حداکثر دسته‌ی در انتظار برای هر شاخه (زمینی/هوایی/دریایی)

# --- فرمان نظامی (انرژی حمله)
ORDERS_MAX = 6           # سقف فرمان (به‌علاوه‌ی سطح کاخ)
ORDER_REGEN = 30 * 60    # هر ۳۰ دقیقه ۱ فرمان
LOGI_COIN = 0.6          # هزینه‌ی بسیج: سکه به‌ازای هر واحد ظرفیتِ اعزامی
PVP_CD = 30 * 60         # کولداون حمله‌ی دوباره به همون بازیکن
REVENGE_H = 24           # مهلت انتقام بعد از حمله‌ی دشمن
INTEL_TTL = 30 * 60      # اعتبار گزارش جاسوسی
BULLY_RATIO = 0.2        # حمله به کشوری ضعیف‌تر از ۲۰٪ قدرت خودت ممنوعه
LAND_MIN, LAND_MAX = 3, 400      # LAND_MAX فقط سقف فنیه؛ سقف واقعی هر کشور از روی جمعیتشه (engine.land_cap)
LAND_POP0 = 10000                # جمعیتی که ۵ استان اول رو پشتیبانی می‌کنه
LAND_POP_PER = 2500              # بعدش به‌ازای هر این‌قدر جمعیتِ بیشتر، ظرفیت یه استان دیگه
NPC_LAND_BASE = 4         # استانِ پایه‌ی NPC = این + سطح ⭐ (مثلاً ⭐۳ ← ۷ استان)
NPC_LAND_REGEN_H = 4      # هر چند ساعت یه استانِ از دست‌رفته‌ی NPC برمی‌گرده
LAND_START = 5
CONQUEST_RATIO = 1.3     # برای تسخیر استان باید با این نسبت قدرت ببری

# --- کمپین جهانی (مرحله‌های بی‌نهایت)
CAMP_BASE_DEF = 50
CAMP_GROWTH = 1.2          # رشد قدرت دشمن در هر مرحله (تا مرحله‌ی ۳۰)
CAMP_GROWTH2 = 1.28        # بعد از مرحله‌ی ۳۰ تندتر میشه تا بازیکن مکس هم همیشه هدف بعدی داشته باشه
CAMP_BOSS_EVERY = 5
CAMP_COIN0 = 150
CAMP_COIN_GROWTH = 1.13

# --- جنگ بزرگ (تهدید جهانی)
BOSS_HP_FACTOR = 4.0     # HP = مجموع قدرت حمله‌ی بازیکن‌های فعال × این ضریب
BOSS_HP_MIN = 20000
BOSS_COINS = 4000        # پایه‌ی جایزه‌ی هر شرکت‌کننده
BOSS_ZERO = (15, 8, 4)   # جایزه‌ی زیرو برای نفر اول تا سوم
BOSS_PART_ZERO = 1

# --- دعوت دوست و کد هدیه
INVITE_COINS, INVITE_ZERO = 3000, 2          # جایزه‌ی دعوت‌کننده
INVITE_NEW_COINS, INVITE_NEW_ZERO = 2500, 1  # جایزه‌ی دعوت‌شده
INVITE_DAILY_CAP = 10
INVITE_MILESTONES = {3: (3000, 3), 10: (10000, 10), 25: (30000, 25)}   # تعداد دعوت: (سکه، زیرو)
CODE_TRIES = (6, 600)
CODES_ON = False           # سیستم کد هدیه فعلاً خاموشه (کدش آماده‌ست؛ True کن تا روشن بشه)

# --- جعبه‌ی شانس
LUCKY_PAID = (2, 3, 4, 6, 8)   # هزینه‌ی زیرو برای بار دوم تا ششم در روز

# --- جدول برترین‌ها و فصل
WEEK_PRIZES = {1: (15000, 10), 2: (8000, 5), 3: (4000, 3)}       # رتبه: (سکه، زیرو)
SEASON_PRIZES = {1: (60000, 40), 2: (30000, 20), 3: (15000, 10)}
SEASON_DAYS = 30
PRIZE_MULT = 1.0

# --- دیپلماسی
PACT_HOURS = (12, 24, 72, 168)
PACT_BREAK_FEE = 0.05
GIFT_FEE = 0.05
GIFT_DAILY_CAP = 50_000   # سقف هدیه‌ی روزانه (به ارزش سکه)
GIFT_MIN_AGE_H = 24
TRADE_FEE = 0.03
OFFER_TTL = 24 * 3600
NEWS_CHANNEL = os.getenv("NEWS_CHANNEL", "")   # اختیاری: اخبار مهم جهان توی این چنل هم میره


# ================================================================== 🎬 نبرد زنده · 👑 تاج امپراتوری · 🗺 نقشه
# --- نبرد زنده: نتیجه‌ی جنگ مرحله‌به‌مرحله جلوی چشم بازیکن ادیت میشه (نتیجه از قبل محاسبه شده؛ فقط نمایشش زنده‌ست)
CINE_ON = True           # False = گزارش یهویی مثل قبل
CINE_DELAY = 1.0         # ثانیه بین هر مرحله (تلگرام توی گروه‌ها ادیت زیاد رو محدود می‌کنه؛ کمتر از ۰٫۸ نذار)

# --- تاج امپراتوری (قوی‌ترین کشور جهان)
EMPEROR = {"id": None}   # خود ربات پرش می‌کنه (crown.py)؛ engine از اینجا می‌خونه
CROWN_MIN_SCORE = 2000   # تا کسی به این امتیاز قدرت نرسیده، تاج صاحب نداره
CROWN_RISE = 1.10        # اگه قدرت یکی ۱۰٪ از امپراتور بیشتر شد، تاج بهش می‌رسه
CROWN_GUARD_MIN = 30     # بعد از هر دست‌به‌دست شدن، تاج این‌قدر دقیقه امنه (جلوی پینگ‌پونگ تاج)
CROWN_BOUNTY = 4000      # جایزه‌ی کسی که امپراتور رو توی جنگ شکست میده و تاج رو می‌گیره
CROWN_TRIBUTE_H = 600    # خراج ساعتی امپراتور (سکه)
CROWN_ORDERS = 2         # سقف فرمان نظامی امپراتور اضافه میشه
CROWN_STEP = 300         # هر چند ثانیه رتبه‌ها چک بشه


# ================================================================== 🌐 مینی‌اپ (نقشه‌ی زنده + فروشگاه)
# آدرس عمومی HTTPS مینی‌اپ (مثلاً https://empire.example.com). خالی = مینی‌اپ خاموش و /map مثل قبل عکس می‌فرسته
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
# لینک مستقیم مینی‌اپ برای گروه‌ها (BotFather ← /newapp)؛ مثلاً https://t.me/YourBot/map — اختیاری
WEBAPP_LINK = os.getenv("WEBAPP_LINK", "").strip()
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("PORT", os.getenv("WEBAPP_PORT", "8080")))
WEBAPP_DEV = os.getenv("WEBAPP_DEV", "") == "1"      # فقط برای تست محلی: ?dev=<آیدی> بدون تلگرام کار می‌کنه

# --- فروشگاه (همه‌ی قیمت‌ها اینجا قابل تنظیمه)
# (ساعت سپر، قیمت به زیرو)؛ بسته‌ی ۱۲ ساعته همون قیمت قبلی SHIELD_PHX ـه، بسته‌های بزرگ‌تر کمی ارزون‌ترن
SHOP_SHIELDS = ((12, 15), (24, 28), (72, 78))
SHOP_ZERO = (1, 5, 10, 25)               # بسته‌های زیرو؛ قیمت = قیمت زنده‌ی بازار ارز
SHOP_FOOD = (1000, 5000)                 # قیمت = قیمت زنده‌ی بازار کالا
SHOP_STEEL = (100, 500)
SHOP_OFFER_BONUS = (25, 40)              # درصد بونوس آفرهای روزانه‌ی منابع
SHOP_OFFER_SHIELD = (20, 30)             # درصد تخفیف آفرهای روزانه‌ی سپر
SHOP_BUY_GAP = 0.6                       # فاصله‌ی حداقل بین دو خرید یک کاربر (ثانیه)


# ================================================================== 💸 اقتصاد: بودجه و مالیات (نسخه‌ی عامل‌محور)
# مالیات = درصد × (سهم تولید ناخالص + درآمد سرانه‌ی جمعیت)؛ پس هرچی جمعیت بیشتر، حتی با درصد کم، درآمد بیشتر
TAX_GDP_SHARE = 1.0          # چند درصد از GDP مشمول مالیاته
TAX_CAPITA = 0.9            # پایه‌ی مالیاتی هر نفر در هر ساعت بازی (سکه)
# هزینه‌ی هر «واحد بودجه» در هر ساعت بازی = نرخ × عامل. عامل: pop = جمعیت · land = تعداد استان
BUDGET_COST = {
    "edu":     ("pop", 0.0007),     # آموزش با جمعیت گرون میشه
    "health":  ("pop", 0.0008),     # سلامت با جمعیت
    "sec":     ("pop", 0.0006),     # امنیت با جمعیت
    "welfare": ("pop", 0.0010),     # رفاه و یارانه با جمعیت
    "mil":     ("land", 1.6),       # نظامی با پهناوری (استان) نه جمعیت
    "infra":   ("land", 1.2),       # راه و زیرساخت با پهناوری
}
BUDGET_CAP = 70                  # سقف مجموع واحدهای بودجه
BUDGET_STEP = 5
BUDGET_NAMES = {"edu": "🎓 آموزش", "health": "🏥 سلامت", "sec": "🚓 امنیت", "welfare": "🤲 رفاه", "mil": "🪖 نظامی", "infra": "🛣 راه و زیرساخت"}
BUDGET_FACTOR = {"edu": "جمعیت", "health": "جمعیت", "sec": "جمعیت", "welfare": "جمعیت", "mil": "استان‌ها", "infra": "استان‌ها"}

# --- بازار ارز: نقدینگی خیلی بزرگ‌تر + قیمت اجرای میانگین + سقف معامله؛ دیگه با یه خرید بزرگ نمیشه قیمت رو پمپ کرد
FX_LIQ = 6_000_000
FX_IMPACT = 0.5
FX_TRADE_CAP = 0.012              # سقف ارزش یه معامله (کسری از نقدینگی) ≈ ۷۲ هزار سکه
FX_DAY_CAP = 0.04                 # سقف حجم خرید روزانه‌ی هر بازیکن برای هر ارز (کسری از نقدینگی)
FX_QUICK_MIN = 30                 # فروش زودتر از این (دقیقه) بعد از خرید کارمزد اضافه داره
FX_QUICK_FEE = 0.03
FX_BAND = (0.55, 1.9)             # کف و سقف قیمت نسبت به قیمت پایه (زیرو: ۵۵ تا ۱۹۰ به‌جای ۱۵ تا ۶۰۰)
FX_VOL_MULT = 0.7                 # نوسان هر تیک (قبلاً ۱٫۰)
FX_REVERT = 0.05                  # برگشت به قیمت پایه در هر تیک (قبلاً ۰٫۰۳)
FX_TICK_MAX = 0.07                # بیشترین تغییر قیمت در یه تیک


# ================================================================== 🗺 نقشه‌ی بزرگ · 📍 مختصات · 🚢 لشکرکشی · 🏕 استعمار
MAP_MIN_TIER = 1                  # کوچک‌ترین اندازه‌ی نقشه؛ بزرگ‌تر شدنش کاملاً خودکاره و از روی تعداد بازیکن و خاک اشغالی حساب میشه
MAP_FREE_PER_PLAYER = 45          # به‌ازای هر کشور این‌قدر خونه‌ی خالی هم باید جا باشه (برای تازه‌واردها و استعمار)
MAP_FILL = 3.2                    # زمین آزاد ≈ ۲٫۲ برابر خاک اشغالی؛ جا برای تازه‌وارد و استعمار
MAP_SEP = (6.0, 4.0, 2.5, 1.5)    # حداقل فاصله‌ی پایتخت‌ها (به خونه)؛ اگه جا کم بیاد دور بعدی با فاصله‌ی کمتر پر میشه

NEIGHBOR_R = 14                   # کشورهایی که توی این شعاع (خونه) و روی همون قاره‌ان همسایه حساب میشن
NEIGHBOR_NEAREST = 2              # ... و ۲ کشور نزدیکِ همون قاره تا شعاع دوم (جلوی بن‌بست توی بازی خلوت)
NEIGHBOR_R2 = 34

# ثانیه به‌ازای هر خونه (پایه؛ تقسیم بر سرعت کندترین یگان)
MARCH_BASE = {"land": 55, "sea": 40, "air": 22}
MARCH_MIN_S = 60
MARCH_MAX_S = 2 * 3600
# هزینه‌ی حمل‌ونقل: سکه به‌ازای هر واحد ظرفیتِ اعزامی در هر خونه
TRANSPORT = {"land": 0.015, "sea": 0.025, "air": 0.04}
TRANSPORT_MULT = 1.0
# برد: زمینی فقط روی یه قاره (تا این فاصله)؛ دریایی/هوایی = پایه + ضریب × سطح بندر/کارخانه
RANGE_LAND = 60
RANGE_SEA = (50, 8)
RANGE_AIR = (36, 5)
MARCH_MAX = 3                     # حداکثر لشکرکشی هم‌زمان (به‌علاوه‌ی سطح کاخ ÷ ۲)
MARCH_SPEED_INFRA = 0.012         # هر واحد بودجه‌ی «راه و زیرساخت» سرعت لشکر رو این‌قدر بیشتر می‌کنه
MODE_DEF_W = {                    # وزن دفاع هر جبهه‌ی مدافع در برابر هر شاخه‌ی حمله (برای ترکیب‌ها بیشینه‌ی شاخه‌ها)
    "land": {"air": 0.55, "sea": 0.15, "land": 1.0},
    "sea":  {"air": 0.55, "sea": 1.0, "land": 0.30},
    "air":  {"air": 1.0, "sea": 0.15, "land": 0.25},
}
BRANCH_ORDER = ("land", "sea", "air")
BRANCH_E = {"land": "🪖", "sea": "🚢", "air": "✈️"}
BRANCH_N = {"land": "زمینی", "sea": "دریایی", "air": "هوایی"}


def mode_branches(mode):
    """نوع حمله → شاخه‌ها. «all» یا ترکیب با «+» مثل «land+air» (هر زیرمجموعه‌ای از زمینی/دریایی/هوایی)."""
    if not mode or mode == "all":
        return BRANCH_ORDER
    s = {p for p in str(mode).split("+") if p in BRANCH_ORDER}
    return tuple(b for b in BRANCH_ORDER if b in s) or BRANCH_ORDER


def norm_mode(mode):
    br = mode_branches(mode)
    return "all" if len(br) == 3 else "+".join(br)


def def_weights(mode):
    br = mode_branches(mode)
    if len(br) == 3:
        return {"air": 1.0, "sea": 1.0, "land": 1.0}
    return {f: max(MODE_DEF_W[b][f] for b in br) for f in ("air", "sea", "land")}


def mode_title(mode):
    br = mode_branches(mode)
    if len(br) == 3:
        return "🌐 همه‌جانبه"
    return "+".join(BRANCH_E[b] for b in br) + " " + "+".join(BRANCH_N[b] for b in br)


MODE_NAMES = {"all": ("🌐", "همه‌جانبه"), "land": ("🪖", "زمینی"), "sea": ("🚢", "دریایی"), "air": ("✈️", "هوایی")}
MODE_BRANCHES = {"all": BRANCH_ORDER, "land": ("land",), "sea": ("sea",), "air": ("air",)}

# --- تسخیر: فقط همسایه‌ها + حفاظت از قربانی (جلوی لخت‌کردن ضعیف‌ترها)
CONQUEST_MIN_RATIO = 0.4          # هدف تسخیر باید حداقل ۴۰٪ قدرت تو رو داشته باشه (بازیکن)
CONQUEST_PROTECT_H = 2            # بعد از از دست دادن استان، این‌قدر ساعت از تسخیرِ بعدی در امانه
CONQUEST_CD_H = 1                 # فاصله‌ی دو تسخیر روی یه هدفِ مشخص (ساعت)
CONQUEST_LIBERATE = 1.15          # قربانی برای پس‌گرفتن استان با این نسبت قاطع حساب میشه (به‌جای ۱٫۳)

# --- استعمار (آباد کردن زمین خالی)
COLONY_COST0 = 15000
COLONY_GROWTH = 1.35              # ضریب هزینه به‌ازای هر استانِ بالای شروع (تا ۳۰ پله)
COLONY_STEPS_MAX = 30
COLONY_STEEL0 = 120
COLONY_FOOD0 = 1500
COLONY_SECS0 = 30 * 60
COLONY_SECS_GROWTH = 1.2
COLONY_SECS_MAX = 10 * 3600      # قبلاً ۱۰ روز بود
COLONY_MIN_PALACE = 2
