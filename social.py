"""🎯 سرجایزه و 🧭 مشاور — دو قابلیت ساده برای بازی توی گروه.

🎯 سرجایزه: هر بازیکن می‌تونه روی یه بازیکن دیگه سکه «سرجایزه» بذاره (از خزانه‌ی خودش کم میشه و روی اون کشور جمع میشه).
   هرکی توی نبرد ببردش ۹۰٪ جمع جایزه رو می‌گیره (۱۰٪ می‌سوزه). خود جایزه‌گذارها نمی‌تونن جایزه رو بردارن (جلوی تقلب با حساب دوم).
🧭 مشاور: وضع کشورت رو می‌خونه و مهم‌ترین قدم‌های بعدی رو پیشنهاد می‌ده.
"""
import config
import db
import engine as E
import prog
from commands import cmd, resolve
from util import amount, esc, kb, n, BACK

BOUNTY_MIN = 500
BOUNTY_MAX_FRAC = 0.5          # حداکثر نصف خزانه
BOUNTY_BURN = 0.10


def place_bounty(c, t, amt):
    """(موفق؟، پیام) — c جایزه‌گذار، t هدف؛ ذخیره‌ی هر دو با صدا زننده‌ست."""
    if t["_id"] == c["_id"]:
        return False, "روی خودت که سرجایزه نمیشه گذاشت 😄"
    if t.get("npc"):
        return False, "روی NPC سرجایزه نمیشه گذاشت"
    if amt < BOUNTY_MIN:
        return False, f"حداقل سرجایزه {BOUNTY_MIN} سکه‌ست"
    if amt > c["treasury"] * BOUNTY_MAX_FRAC:
        return False, f"حداکثر نصف خزانه‌ت ({int(c['treasury'] * BOUNTY_MAX_FRAC):,} سکه) رو می‌تونی بذاری"
    c["treasury"] -= amt
    t["bounty_pool"] = int(t.get("bounty_pool", 0)) + int(amt)
    by = t.setdefault("bounty_by", [])
    if c["_id"] not in by:
        by.append(c["_id"])
    del by[:-12]
    return True, f"🎯 {n(amt)} سکه سرجایزه روی «{esc(t['name'])}» گذاشتی؛ جمع جایزه: {n(t['bounty_pool'])}💰"


def claim_bounty(att, dfn):
    """موقع پیروزی مهاجم صدا زده میشه؛ (مبلغ، متن) یا (0، '')."""
    pool = int(dfn.get("bounty_pool", 0))
    if pool <= 0 or att["_id"] in dfn.get("bounty_by", []):
        return 0, ""
    got = int(pool * (1 - BOUNTY_BURN))
    att["treasury"] += got
    dfn["bounty_pool"], dfn["bounty_by"] = 0, []
    return got, f"\n🎯 <b>سرجایزه‌ی {esc(dfn['name'])}</b> مال تو شد: +{n(got)}💰"


@cmd("bounty", "سرجایزه", "سر جایزه", args=True)
async def h_bounty(m, c, a):
    tk = a.split()
    amt = amount(tk.pop(), int(c["treasury"])) if tk else None
    if amt is None:
        return ("🎯 <b>سرجایزه</b>: روی یه بازیکن سکه بذار؛ هرکی ببردش جایزه رو می‌گیره.\n"
                "مثال: روی پیام اون بازیکن ریپلای کن و بنویس <code>سرجایزه 5000</code> · لیست: «تحت تعقیب‌ها»")
    tid = await resolve(m, tk)
    if tid is None:
        return "هدف پیدا نشد؛ روی پیامش ریپلای کن یا اسم کشورش رو بنویس"
    t = await db.load(tid)
    ok, msg = place_bounty(c, t, int(amt))
    if ok:
        await db.save(t)
    return msg


@cmd("wanted", "تحت تعقیب", "تحت تعقیب‌ها", "سرجایزه‌ها", "تعقیب‌شده‌ها")
async def h_wanted(m, c, a):
    docs = await db.C.find({"bounty_pool": {"$gt": 0}}, {"name": 1, "bounty_pool": 1, "emblem": 1, "land": 1}).to_list(50)
    docs.sort(key=lambda d: -d.get("bounty_pool", 0))
    if not docs:
        return "🎯 الان کسی سرجایزه نداره. با «سرجایزه 5000» (ریپلای روی یه بازیکن) شروع کن!"
    t = ["🎯 <b>تحت تعقیب‌ها</b> — هرکی ببردشون جایزه‌شون رو می‌گیره"]
    for i, d in enumerate(docs[:10], 1):
        t.append(f"{i}. {d.get('emblem', '🏛')} {esc(d['name'])} — {n(d['bounty_pool'])}💰 · 🏞 {d.get('land', 5)}")
    return "\n".join(t)


def advice(c):
    """فهرست پیشنهادهای مشاور، مهم‌ترین اول."""
    d = E.derive(c)
    tips = []
    if c["starving"]:
        tips.append("🍞 مردمت گرسنه‌ان! فوری غذا بخر یا مزرعه بساز؛ قحطی ناآرامی میاره.")
    if c["treasury"] < 0:
        tips.append("💸 خزانه منفیه؛ مالیات رو بالا ببر یا بودجه‌ای که گرون‌ه رو کم کن.")
    elif d["net"] < 0:
        worst = max(d["costs"], key=d["costs"].get)
        tips.append(f"📉 درآمدت منفیه ({d['net']:+,.0f}/ساعت). گرون‌ترین بودجه‌ت {config.BUDGET_NAMES[worst]} ({d['costs'][worst]:,.0f}💰) ـه؛ کمش کن یا مالیات بده بالا.")
    if c.get("unrest", 0) >= 50:
        tips.append("😡 ناآرامی بالاست؛ «ناآرامی» رو ببین و 🚓 امنیت یا 🤲 رفاه رو زیاد کن.")
    if E.orders(c) >= E.orders_max(c) - 0.01:
        tips.append("⚡ فرمان‌هات پره و داره هدر میره؛ یه حمله بزن یا کمپین برو.")
    if not c.get("queue"):
        tips.append("🏗 هیچ ساختی در جریان نیست؛ یه ساختمون بساز یا ارتقا بده.")
    if E.army_size(c) + E.queued_size(c) >= E.army_cap(c) * 0.95:
        tips.append("🏕 ظرفیت پادگانت تقریباً پره؛ پادگان/ساختمون ظرفیت رو ارتقا بده.")
    if c["steel"] < 100:
        tips.append("⚙️ فولادت کمه؛ از بازار بخر یا معدن بساز تا ارتش و استعمار نخوابه.")
    rich = c["treasury"] > max(15000, d["net"] * 12)
    if rich and E.lv(c, "palace") >= config.COLONY_MIN_PALACE and c.get("land", 5) + len(c.get("colony", [])) < config.LAND_MAX and not c.get("colony"):
        coins = E.colony_cost(c)[0]
        if c["treasury"] >= coins:
            tips.append(f"🏕 پول خوابیده داری؛ «استعمار» یه استان تازه می‌سازه ({coins:,}💰).")
    if rich and c["budget"].get("welfare", 0) == 0:
        tips.append("🤲 با پول مازاد، یه کم 🤲 رفاه بذار تا رضایت و آرامش بالا بره.")
    if not c.get("marches") and E.army_size(c) > 300:
        tips.append("🧭 ارتشت بیکاره؛ «همسایه‌ها» رو ببین و از بین حریف‌ها یکی رو بزن (یا «تسخیر» برای استان).")
    if c.get("lost_to"):
        tips.append("🕊 یه استانت دست یکی افتاده؛ با «تسخیر» روش پس بگیرش (آزادسازی شرط آسون‌تری داره).")
    if not tips:
        tips.append("✅ همه‌چیز سرجاشه؛ فرمانروای خوبی هستی! یه نگاه به «ماموریت» بنداز.")
    return tips


@cmd("advisor", "مشاور", "راهنمای من", "پیشنهاد")
async def h_advisor(m, c, a):
    tips = advice(c)
    t = ["🧭 <b>مشاور کشور</b> — مهم‌ترین قدم‌ها:"] + [f"{i}. {x}" for i, x in enumerate(tips[:5], 1)]
    return "\n".join(t)
