"""دستورهای کلمه‌ایِ سیستم‌های تازه (دعوت، کد، جعبه، رویداد، اخبار، برترین‌ها، دیپلماسی، کمپین، جنگ بزرگ، صف).
به همون CMDS و دیسپچر commands.py وصل میشن."""
import re

import config
import db
import engine as E
import growth
import prog
import ui
import war
import world
from commands import cmd, resolve
from util import amount, esc, n


def usage(m, text):
    """راهنمای استفاده فقط وقتی با اسلش صدا زده شده؛ وسط حرف‌های عادی گروه (کلمه‌ی بدون اسلش) ساکت می‌مونه."""
    return text if (m.text or "").lstrip().startswith("/") else None


# ------------------------------------------------------------------ ریست (فقط ادمین)
@cmd("resetplayer", "ریست پلیر", "ریست بازیکن", args=True, need=False)
async def h_resetplayer(m, c, a):
    """ریپلای روی پیام بازیکن یا «ریست پلیر آیدی/اسم» → دکمه‌ی تأیید"""
    import admin
    from util import kb
    if m.from_user.id not in config.ADMINS:
        return None
    if not admin.is_owner(m.from_user.id):
        return "⛔ ریست فقط برای مالک ربات مجازه"
    tk = a.split()
    tid = None
    if len(tk) == 1 and tk[0].isdigit():            # آیدی عددی تلگرام (قبل از ایندکس NPC بررسی میشه)
        d0 = await db.C.find_one({"_id": int(tk[0]), "npc": {"$ne": True}}, {"_id": 1})
        tid = d0["_id"] if d0 else None
    if tid is None:
        tid = await resolve(m, tk)
    if tid is None or tid < 0:
        return "مثال: روی پیام بازیکن ریپلای کن و بنویس «ریست پلیر»، یا <code>ریست پلیر آیدی-عددی</code>"
    d = await db.C.find_one({"_id": tid}, {"name": 1})
    if not d:
        return "کشوری با این مشخصات پیدا نشد"
    admin.st(m.from_user.id)["tid"] = tid
    return (f"⚠️ <b>ریست کشور «{esc(d['name'])}»</b> (<code>{tid}</code>)؟ برگشت‌پذیر نیست.",
            kb([[("✅ بله، ریست کن", "ad:ok:reset")], [("❌ نه", "ad:home")]]))


@cmd("resetall", "ریست آل پلیر", "ریست همه", "ریست همه پلیرها", need=False)
async def h_resetall(m, c, a):
    import admin
    from util import kb
    if m.from_user.id not in config.ADMINS:
        return None
    if not admin.is_owner(m.from_user.id):
        return "⛔ ریست همه فقط برای مالک ربات مجازه"
    return ("☢️ <b>ریست همه‌ی پلیرها</b>\nهمه‌ی کشورها از صفر شروع می‌کنن (اسم، مدیر و دکترین می‌مونه)؛ اتحادها، آگهی‌ها، پیمان‌ها و جنگ‌ها پاک میشن. "
            "قبلش یه بکاپ برات فرستاده میشه.", kb([[("ادامه ←", "ad:rsa")], [("❌ نه", "ad:home")]]))


# ------------------------------------------------------------------ رشد
@cmd("invite", "دعوت", "لینک دعوت", "دعوت دوست")
async def h_invite(m, c, a):
    return growth.s_invite(c)


@cmd("code", "کد", "کد هدیه", args=True)
async def h_code(m, c, a):
    if not config.CODES_ON:
        return None
    if not (m.text or "").lstrip().startswith("/") and not re.fullmatch(r"[A-Za-z0-9_\-]{3,24}", a.strip()):
        return None               # «کد زدن» وسط حرف عادی نباید جواب بگیره
    return await growth.redeem(c, a)


@cmd("box", "جعبه", "جعبه‌ی شانس", "جعبه شانس", args=True)
async def h_box(m, c, a):
    ok, msg = growth.open_box(c) if a else (None, None)
    text, mk = growth.s_lucky(c)
    return ((msg + "\n\n") if msg else "") + text, mk


@cmd("event", "رویداد")
async def h_event(m, c, a):
    return growth.s_event(c)


@cmd("news", "اخبار", "اخبار جهان")
async def h_news(m, c, a):
    return world.s_news(c)


@cmd("boards", "برترین‌ها", "برترینها", "جدول")
async def h_boards(m, c, a):
    return await world.s_boards(c)


# ------------------------------------------------------------------ دیپلماسی
@cmd("diplo", "دیپلماسی")
async def h_diplo(m, c, a):
    return await world.s_diplo(c)


@cmd("pact", "پیمان", args=True)
async def h_pact(m, c, a):
    tk, hours = a.split(), 24
    if tk and tk[-1].isdigit():
        hours = int(tk.pop())
    tid = await resolve(m, tk)
    if tid is None:
        return usage(m, "مثال: <code>پیمان نام‌کشور 24</code> (یا ریپلای روی پیام بازیکن) · مدت‌ها: " + "، ".join(str(h) for h in config.PACT_HOURS) + " ساعت")
    return (await world.pact_propose(c, tid, hours))[1]


@cmd("gift", "هدیه", args=True)
async def h_gift(m, c, a):
    tk = a.split()
    amt = amount(tk.pop()) if tk else None
    res = world.RES_ALIAS.get(tk.pop().lower()) if tk else None
    tid = await resolve(m, tk)
    if tid is None or not res or not amt:
        return usage(m, "مثال: <code>هدیه نام‌کشور فولاد 100</code> · کالاها: سکه، غذا، فولاد، زیرو")
    return (await world.gift_send(c, tid, res, amt))[1]


@cmd("trade_offer", "معامله", args=True)
async def h_offer(m, c, a):
    tk = a.split()
    if len(tk) < 4:
        return usage(m, "مثال: <code>معامله نام‌کشور فولاد 100 غذا 500</code> (فولاد می‌دی، غذا می‌خوای)")
    ask_amt, ask_res = amount(tk.pop()), world.RES_ALIAS.get(tk.pop().lower())
    give_amt, give_res = amount(tk.pop()), world.RES_ALIAS.get(tk.pop().lower())
    tid = await resolve(m, tk)
    if tid is None or not (ask_amt and ask_res and give_amt and give_res):
        return usage(m, "مثال: <code>معامله نام‌کشور فولاد 100 غذا 500</code>")
    return (await world.offer_create(c, tid, (give_res, give_amt), (ask_res, ask_amt)))[1]


# ------------------------------------------------------------------ جنگ
@cmd("camp", "کمپین")
async def h_camp(m, c, a):
    return war.s_camp(c)


@cmd("boss", "جنگ بزرگ", "غول", "تهدید جهانی")
async def h_boss(m, c, a):
    return await war.s_boss(c)


@cmd("orders", "فرمان", "فرمان نظامی")
async def h_orders(m, c, a):
    return war.orders_line(c) + f"\nهر حمله ۱ فرمان می‌خواد (تسخیر ۲)؛ هر {config.ORDER_REGEN // 60} دقیقه یکی پر میشه. سقف: {E.orders_max(c)} (با ارتقای 🏰 کاخ بیشتر میشه)"


# ------------------------------------------------------------------ صف ساخت و آموزش
@cmd("queue", "صف", "صف ساخت")
async def h_queue(m, c, a):
    return ui.s_queue(c)


@cmd("speedup", "تسریع", args=True)
async def h_speedup(m, c, a):
    jobs = c["queue"] + c["tq"]
    idx = amount(a)
    if not jobs:
        return "چیزی در حال ساخت یا آموزش نیست"
    if not idx or idx > len(jobs):
        text, mk = ui.s_queue(c)
        return "شماره‌ی کار رو بنویس: <code>تسریع 1</code>\n\n" + text, mk
    return E.speedup(c, jobs[idx - 1]["id"])[1]
