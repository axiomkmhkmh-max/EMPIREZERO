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

# cost=سکه steel=فولاد up=نگهداری atk/dfn=قدرت size=ظرفیت پادگان br=شاخه (land/air/sea)
U = {
    "inf":     dict(n="پیاده‌نظام", e="🪖", cost=30, steel=0, up=0.15, atk=1, dfn=1.2, size=1, br="land", t=5, req={}),
    "tank":    dict(n="تانک", e="🚜", cost=400, steel=30, up=2, atk=8, dfn=6, size=10, br="land", t=45, req={"factory": 1}),
    "jet":     dict(n="جنگنده", e="✈️", cost=1000, steel=60, up=5, atk=16, dfn=8, size=20, br="air", t=90, req={"factory": 2}),
    "missile": dict(n="موشک", e="🚀", cost=1500, steel=80, up=2, atk=0, dfn=0, size=25, br="air", t=100, req={"factory": 3}),
    "ad":      dict(n="پدافند", e="📡", cost=1200, steel=60, up=3, atk=0, dfn=25, size=15, br="air", t=70, req={"factory": 2}),
    "ship":    dict(n="ناو", e="🚢", cost=900, steel=50, up=4, atk=12, dfn=10, size=15, br="sea", t=80, req={"port": 1, "factory": 1}),
    "sub":     dict(n="زیردریایی", e="🤿", cost=1500, steel=70, up=5, atk=22, dfn=6, size=20, br="sea", t=120, req={"port": 2, "factory": 2}),
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
FX_LIQ = 400_000
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
TRAIN_QUEUE_MAX = 6      # حداکثر دسته‌ی در انتظار برای هر شاخه (زمینی/هوایی/دریایی)

# --- فرمان نظامی (انرژی حمله)
ORDERS_MAX = 6           # سقف فرمان (به‌علاوه‌ی سطح کاخ)
ORDER_REGEN = 30 * 60    # هر ۳۰ دقیقه ۱ فرمان
LOGI_COIN = 0.6          # هزینه‌ی بسیج: سکه به‌ازای هر واحد ظرفیتِ اعزامی
PVP_CD = 30 * 60         # کولداون حمله‌ی دوباره به همون بازیکن
REVENGE_H = 24           # مهلت انتقام بعد از حمله‌ی دشمن
INTEL_TTL = 30 * 60      # اعتبار گزارش جاسوسی
BULLY_RATIO = 0.2        # حمله به کشوری ضعیف‌تر از ۲۰٪ قدرت خودت ممنوعه
LAND_MIN, LAND_MAX = 3, 30
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
