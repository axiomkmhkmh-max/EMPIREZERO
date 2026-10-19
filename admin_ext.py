"""افزونه‌ی پنل ادمین: هدیه‌ی فردی · کد هدیه · رویدادها و جنگ بزرگ · آمار رشد · برترین‌ها و فصل · ضدتقلب.
از admin.py صدا زده میشه (route و handle_input)؛ توکن‌های دکمه عمداً با «c» شروع نمیشن (admin.route برای c* کشور می‌خواد)."""
import random
import re
import secrets
import string
import time

from aiogram.types import BufferedInputFile

import admin as A
import config
import db
import eco
import engine as E
import events
import growth
import guard
import prog
import war
import world
from core import bot
from util import digits, esc, kb, n

HOME = A.HOME
OWNER_ONLY = {"rsp", "rsa", "rsay", "gc", "gcs", "gcn", "gct", "gcx", "gcxy", "gcb", "xv", "xvs", "xvh", "xvx", "xb", "xbh", "xbx", "sb", "sbw", "sbs", "sbwy", "sbsy"}

# ================================================================== هدیه‌ی فردی
GL = {"coins": ("💰", "سکه"), "zero": ("⚡", "زیرو"), "food": ("🌾", "غذا"), "steel": ("⚙️", "فولاد"),
      "tech": ("🔬", "پژوهش"), "shield": ("🛡", "ساعت سپر"), "box": ("🎰", "جعبه‌ی شانس")}


def apply_gift(c, key, amt):
    """amt مثبت = دادن · منفی = کسر. (قبل، بعد) برمی‌گردونه."""
    if key == "coins":
        old = c["treasury"]
        c["treasury"] = max(0.0, old + amt) if amt < 0 else old + amt
        return old, c["treasury"]
    if key == "zero":
        old = c["fx"].get("PHX", 0.0)
        c["fx"]["PHX"] = max(0.0, old + amt)
        c["fxcost"].setdefault("PHX", eco.fx_price("PHX") if eco.WORLD else 100.0)
        return old, c["fx"]["PHX"]
    if key in ("food", "steel", "tech"):
        old = c[key]
        c[key] = max(0.0, old + amt)
        return old, c[key]
    if key == "shield":
        old = max(0.0, c["shield_until"] - E.now()) / 3600
        c["shield_until"] = max(0.0, max(E.now(), c["shield_until"]) + amt * 3600) if amt > 0 else max(0.0, c["shield_until"] + amt * 3600)
        return old, max(0.0, c["shield_until"] - E.now()) / 3600
    old = c["lucky"].get("bonus", 0)
    c["lucky"]["bonus"] = max(0, int(old + amt))
    return old, c["lucky"]["bonus"]


async def s_ig(S, note=""):
    tid = S.get("tid")
    if tid is None:
        return A.ask(S, {"act": "ig_find"}, "🎁 <b>هدیه‌ی فردی</b>\nکی؟ آیدی عددی، اسم کشور، @یوزرنیم، یا یه پیامش رو فوروارد کن:", "ad:home")[1]
    async with db.LOCK:
        c = await db.load(tid)
    if not c:
        return (f"{A.note_(note)}❌ برای <code>{tid}</code> کشوری وجود نداره (باید اول ثبت‌نام کرده باشه).", kb([[("🔎 یکی دیگه", "ad:ig")], HOME]))
    t = (f"{A.note_(note)}🎁 <b>هدیه‌ی فردی ← {esc(c['name'])}</b>\n🆔 <code>{tid}</code> · {esc(c['leader'])}\n"
         f"💰 {n(c['treasury'])} · ⚡ {c['fx'].get('PHX', 0):,.1f} · 🌾 {n(c['food'])} · ⚙️ {n(c['steel'])} · 🔬 {n(c['tech'])}\n\n"
         "چی بدی؟ (توی مرحله‌ی بعد عدد منفی = کسر)")
    rows = A.grid([(f"{e} {nm}", f"ad:igr:{k}") for k, (e, nm) in GL.items()], 2)
    return t, kb(rows + [[("🔎 بازیکن دیگه", "ad:ig")], HOME])


def s_confirm(S):
    g, tid = S["ig"], S["tid"]
    e, nm = GL[g["key"]]
    act = "دادن" if g["amt"] > 0 else "کسر"
    t = (f"⚠️ <b>تأیید</b>\n{act} <b>{abs(g['amt']):g}</b> {e} {nm} {'به' if g['amt'] > 0 else 'از'} <code>{tid}</code>؟"
         + (f"\n✉️ پیام: {esc(g['note'])}" if g.get("note") else ""))
    return t, kb([[("✅ تأیید و ارسال", "ad:igok")], [("✉️ پیام همراه", "ad:ign"), ("❌ انصراف", "ad:ig")]])


# ================================================================== کد هدیه
def rew_line(d):
    r = d.get("rew", {})
    return growth.code_text(r)


def _gen_code():
    return "EZ" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


async def s_codes(page=0):
    docs = await db.CODES.find().sort("created", -1).to_list(200)
    per = 8
    page = max(0, min(page, max(0, (len(docs) - 1) // per)))
    sub = docs[page * per:(page + 1) * per]
    t = [f"🎟 <b>کدهای هدیه</b> ({len(docs)})", "بازیکن می‌نویسه «کد EMPIRE100» و جایزه می‌گیره.", ""]
    rows = []
    for d in sub:
        exp = "" if not d.get("exp") else (" ⌛" if d["exp"] < E.now() else "")
        t.append(f"{'✅' if d.get('active', True) else '⏸'} <code>{d['_id']}</code> · {d.get('used', 0)}/{d.get('max', 1)}{exp} · {rew_line(d)}")
        rows.append([(f"{d['_id']} · {d.get('used', 0)}/{d.get('max', 1)}", f"ad:gcs:{d['_id']}")])
    rows.append(A.pager(page, len(docs), per, lambda p: f"ad:gc:{p}"))
    rows.append([("➕ ساخت کد جدید", "ad:gcn")])
    return "\n".join(t), kb(rows + [HOME])


async def s_code(code, note=""):
    d = await db.CODES.find_one({"_id": code})
    if not d:
        return "کد پیدا نشد", kb([[("🔙", "ad:gc:0")]])
    exp = "بدون انقضا" if not d.get("exp") else f"تا {A.fdate(d['exp'])} UTC"
    t = (f"{A.note_(note)}🎟 <b>{d['_id']}</b> · {'✅ فعال' if d.get('active', True) else '⏸ غیرفعال'}\n🎁 {rew_line(d)}\n"
         f"👥 استفاده: {d.get('used', 0)}/{d.get('max', 1)} · ⌛ {exp}\n"
         f"🧾 آخرین‌ها: {' '.join(str(u) for u in d.get('users', [])[-6:]) or '—'}\n\n"
         f"متن اعلان برای بازیکن‌ها: «کد {d['_id']}»")
    rows = [[("⏯ فعال/غیرفعال", f"ad:gct:{code}"), ("📣 اعلان به همه", f"ad:gcb:{code}")],
            [("🗑 حذف", f"ad:gcx:{code}"), ("🔙 لیست", "ad:gc:0")]]
    return t, kb(rows + [HOME])


def parse_code(txt):
    """«EMPIRE100 coins=5000 zero=2 uses=100 days=7» یا «auto coins=1000» → (کد، جایزه، تعداد، روز) یا پیام خطا"""
    tk = digits(txt).replace("،", " ").split()
    if not tk:
        return "متن خالیه"
    code = _gen_code() if tk[0].lower() == "auto" else tk[0].upper()
    if not re.fullmatch(r"[A-Z0-9_\-]{3,24}", code):
        return "کد باید ۳ تا ۲۴ حرف انگلیسی/عدد/-/_ باشه"
    rew, uses, days = {}, 1, 0
    alias = {"coins": "coins", "coin": "coins", "سکه": "coins", "zero": "zero", "phx": "zero", "زیرو": "zero", "food": "food", "غذا": "food",
             "steel": "steel", "فولاد": "steel", "tech": "tech", "پژوهش": "tech", "shield": "shield", "سپر": "shield", "box": "box", "جعبه": "box"}
    for tok in tk[1:]:
        if "=" not in tok:
            return f"«{tok}» رو نفهمیدم؛ شکل درست: coins=5000"
        k, v = tok.split("=", 1)
        k = k.lower()
        try:
            val = float(v.replace(",", "").lower().replace("k", "e3").replace("m", "e6"))
        except ValueError:
            return f"عدد «{v}» معتبر نیست"
        if k in ("uses", "max", "تعداد"):
            uses = max(1, int(val))
        elif k in ("days", "روز"):
            days = max(0, val)
        elif k in alias and val > 0:
            rew[alias[k]] = int(val)
        else:
            return f"پارامتر «{k}» ناشناخته‌ست (coins zero food steel tech shield box uses days)"
    if not rew:
        return "حداقل یه جایزه بده. مثال: <code>EMPIRE100 coins=5000 zero=2 uses=100 days=7</code>"
    return code, rew, uses, days


# ================================================================== رویدادها و جنگ بزرگ
async def s_events(note=""):
    act = events.banner_lines()
    t = [f"{A.note_(note)}🎉 <b>رویدادهای هفتگی</b>", "با شروع رویداد، به همه‌ی بازیکن‌ها خبر میره.", ""]
    t += act or ["الان رویداد فعالی نیست."]
    rows = []
    for k, ty in events.TYPES.items():
        if k == "war":
            continue
        rows.append([(f"{ty['e']} شروع {ty['n']}", f"ad:xvs:{k}")])
    for e in events.active():
        if e["type"] != "war":
            rows.append([(f"⏹ پایان {events.TYPES[e['type']]['n']}", f"ad:xvx:{e['type']}")])
    rows.append([("🌑 جنگ بزرگ (تهدید جهانی)", "ad:xb")])
    return "\n".join(t), kb(rows + [HOME])


def s_boss_admin(note=""):
    B = war.BOSS
    t = [f"{A.note_(note)}🌑 <b>جنگ بزرگ</b>"]
    if war.boss_active():
        dm = B.get("dmg", {})
        t += [f"فعال: «{B['name']}» · ❤️ {n(B['hp'])}/{n(B['hp_max'])} · ⏳ {prog.dur(B['end'] - E.now())}",
              f"👥 شرکت‌کننده: {len(dm)} · 💥 مجموع: {n(sum(dm.values()))}"]
        rows = [[("⏹ پایان همین الان (بدون نابودی)", "ad:xbx")]]
    else:
        t += ["الان فعال نیست. HP خودکار = مجموع قدرت حمله‌ی بازیکن‌های فعال ۷ روز اخیر × " + f"{config.BOSS_HP_FACTOR:g}",
              "مدت رو انتخاب کن تا شروع بشه و همه خبردار بشن:"]
        rows = [[(f"{h} ساعت", f"ad:xbh:{h}") for h in (6, 12, 24, 48)]]
    return "\n".join(t), kb(rows + [[("🔙 رویدادها", "ad:xv")], HOME])


# ================================================================== آمار رشد
async def s_growth():
    rows = await growth.series(14)
    ret = await growth.retention(5)
    users = await db.C.count_documents({"npc": {"$ne": True}})
    t = ["📈 <b>آمار رشد</b> (۱۴ روز اخیر)", f"👥 کل بازیکن: <b>{n(users)}</b> · 🟢 فعال امروز: <b>{rows[-1]['act']}</b> · 🆕 جدید امروز: <b>{rows[-1]['new']}</b>", "",
         "🆕 <b>بازیکن جدید در روز</b>", growth.text_chart(rows, "new"), "", "🟢 <b>بازیکن فعال در روز</b>", growth.text_chart(rows, "act"), "",
         "🔁 <b>بازگشت روز بعد (D1)</b>"]
    t += [f"<code>{d[5:]}</code> · {c} نفر → {p:.0f}٪" for d, c, p in ret]
    return "\n".join(t)[:3900], kb([[("🖼 نمودار تصویری", "ad:gsp"), ("🔄", "ad:gs")], HOME])


# ================================================================== فصل و برترین‌ها
async def s_season(note=""):
    S = world.SEASON
    t = [f"{A.note_(note)}🏅 <b>برترین‌ها و فصل</b>", f"📅 هفته تا {prog.dur(S['wend'] - E.now())} دیگه تموم میشه",
         f"🏆 فصل {S['sid']} تا {prog.dur(S['send'] - E.now())} دیگه", f"🎁 جایزه‌ی هفتگی: {world.prize_text('w')}",
         f"🎁 جایزه‌ی فصل: {world.prize_text('s')}", ""]
    for b, (e, nm, _) in world.BOARDS.items():
        rows = await world.top(b, "w", 3)
        t.append(f"{e} {nm}: " + (" · ".join(f"{r[2]} ({n(r[0])})" for r in rows) or "—"))
    return "\n".join(t), kb([[("⏩ پایان هفته الان", "ad:sbw"), ("🏁 پایان فصل الان", "ad:sbs")], HOME])


# ================================================================== ضدتقلب
async def s_anticheat(note=""):
    fl = await guard.recent(10)
    held = await db.INVITES.count_documents({"held": True})
    t = [f"{A.note_(note)}🕵️ <b>ضدتقلب</b> — هشدارهای باز ({len(fl)})", f"⏸ جایزه‌ی دعوتِ نگه‌داشته‌شده: {held}",
         "<i>اینا نشونه‌ان نه اثبات؛ باز کن و خودت قضاوت کن.</i>", ""]
    rows = []
    for f in fl:
        t.append(f"#{f['_id']} <code>{f['uid']}</code> · {esc(f['kind'])}\n{esc(f['detail'])[:160]}")
        rows.append([(f"🔎 {f['uid']}", f"ad:c:{f['uid']}"), (f"✅ رد #{f['_id']}", f"ad:acr:{f['_id']}")])
    if not fl:
        t.append("هشدار بازی نیست ✅")
    return "\n".join(t)[:3900], kb(rows + [[("🔄", "ad:ac")], HOME])


# ================================================================== ریست همه‌ی پلیرها
async def reset_all():
    """همه‌ی کشورهای بازیکن از صفر؛ اتحاد/آگهی/پیمان/جنگ پاک میشن. (تعداد کشورهای ریست‌شده)"""
    async with db.LOCK:
        docs = await db.C.find({"npc": {"$ne": True}}).to_list(None)
        await db.A.delete_many({})
        await db.W.delete_many({})
        await db.M.delete_many({})
        await db.PACTS.delete_many({})
        for old in docs:
            c = E.new_country(old["_id"], old["name"], old["leader"], old.get("doctrine", "bal"))
            for k in ("name_key", "home", "emblem", "uname", "uname_base"):
                if old.get(k) is not None:
                    c[k] = old[k]
            await db.save(c)
        war.BOSS.clear()
        await war.boss_save()
        world._CACHE.clear()
    return len(docs)


# ================================================================== مسیریابی
async def route(uid, S, p):
    t = p[0]
    if t in OWNER_ONLY and not A.is_owner(uid):
        return "⛔ فقط مالک ربات", None
    if t in ("gc", "gcs", "gcn", "gct", "gcx", "gcxy", "gcb") and not config.CODES_ON:
        return "🎟 کد هدیه فعلاً غیرفعاله", None

    # --- ریست
    if t == "rsp":
        S["tid"] = None
        return A.ask(S, {"act": "rs_find"}, "♻️ <b>ریست پلیر</b>\nکی؟ آیدی عددی، اسم کشور، @یوزرنیم، یا یه پیامش رو فوروارد کن:", "ad:home")
    if t == "rsa":
        return A.ask(S, {"act": "reset_all"},
                     "☢️ <b>ریست همه‌ی پلیرها</b>\nهمه‌ی کشورها از صفر شروع می‌کنن و اتحاد/آگهی/پیمان/جنگ‌ها پاک میشن.\n"
                     "برای تأیید دقیقاً بنویس: <code>ریست همه</code>", "ad:home")

    # --- هدیه‌ی فردی
    if t == "ig":
        S["tid"], S["ig"] = None, None
        return None, await s_ig(S)
    if t == "igp":
        S["tid"] = int(p[1])
        return None, await s_ig(S)
    if t == "igr":
        if S.get("tid") is None or p[1] not in GL:
            return "اول بازیکن رو انتخاب کن", None
        e, nm = GL[p[1]]
        return A.ask(S, {"act": "ig_amt", "key": p[1]}, f"{e} <b>{nm}</b> — چند تا؟ (<code>5000</code> یا <code>5k</code> = بده · <code>-200</code> = کسر)", "ad:igp:" + str(S["tid"]))
    if t == "ign":
        return A.ask(S, {"act": "ig_note"}, "✉️ پیام همراه هدیه (برای بازیکن می‌ره):", "ad:igp:" + str(S["tid"]))
    if t == "igok":
        g, tid = S.get("ig"), S.get("tid")
        if not g or tid is None:
            return "چیزی برای ارسال نیست", None
        r = await A.mutate(tid, lambda c: apply_gift(c, g["key"], g["amt"]))
        if r is None:
            return "کشور پیدا نشد", None
        e, nm = GL[g["key"]]
        S["ig"] = None
        await A.alog(uid, f"هدیه‌ی فردی {g['amt']:g} {g['key']} به {tid}: {r[0]:,.1f} → {r[1]:,.1f}")
        if g["amt"] > 0:
            msg = f"🎁 <b>هدیه از طرف مدیریت {config.BOT_NAME}!</b>\n{e} {g['amt']:g} {nm} به کشورت اضافه شد 💛"
        else:
            msg = f"⚠️ <b>مدیریت {config.BOT_NAME}</b> {abs(g['amt']):g} {e} {nm} از کشورت کسر کرد."
        if g.get("note"):
            msg += f"\n\n✉️ {esc(g['note'])}"
        A.spawn(A._gift_notify([tid], msg))
        return "✅ انجام شد", await s_ig(S, f"✅ {e} {nm}: {r[0]:,.1f} → <b>{r[1]:,.1f}</b> و بازیکن خبردار شد")

    # --- کد هدیه
    if t == "gc":
        return None, await s_codes(int(p[1]) if len(p) > 1 else 0)
    if t == "gcs":
        return None, await s_code(p[1])
    if t == "gcn":
        return A.ask(S, {"act": "code_new"},
                     "🎟 <b>ساخت کد هدیه</b>\nبه این شکل بفرست:\n<code>EMPIRE100 coins=5000 zero=2 uses=100 days=7</code>\n"
                     "• به‌جای اسم کد، <code>auto</code> بنویس تا خودم بسازم\n• جایزه‌ها: coins zero food steel tech shield(ساعت) box(جعبه‌ی شانس)\n"
                     "• uses = چند نفر بتونن استفاده کنن · days = چند روز اعتبار (۰ = همیشه)", "ad:gc:0")
    if t == "gct":
        d = await db.CODES.find_one({"_id": p[1]})
        if d:
            await db.CODES.update_one({"_id": p[1]}, {"$set": {"active": not d.get("active", True)}})
            await A.alog(uid, f"کد {p[1]} → {'غیرفعال' if d.get('active', True) else 'فعال'}")
        return "✅", await s_code(p[1])
    if t == "gcx":
        return None, (f"⚠️ کد <code>{p[1]}</code> حذف بشه؟", kb([[("✅ بله حذف کن", f"ad:gcxy:{p[1]}")], [("❌ نه", f"ad:gcs:{p[1]}")]]))
    if t == "gcxy":
        await db.CODES.delete_one({"_id": p[1]})
        await A.alog(uid, f"حذف کد {p[1]}")
        return "🗑", await s_codes(0)
    if t == "gcb":
        d = await db.CODES.find_one({"_id": p[1]})
        if not d:
            return "پیدا نشد", None
        cnt = await world.broadcast_players(f"🎟 <b>کد هدیه‌ی جدید!</b>\nبنویس: <code>کد {d['_id']}</code>\n🎁 {rew_line(d)}\n"
                                            f"(ظرفیت {d.get('max', 1)} نفر{'؛ زود باش!' if d.get('max', 1) < 500 else ''})")
        await A.alog(uid, f"اعلان کد {p[1]} به {cnt} نفر")
        return f"📣 برای {cnt} نفر در حال ارسال", await s_code(p[1], f"📣 اعلان برای {cnt} بازیکن فرستاده میشه")

    # --- رویدادها
    if t == "xv":
        return None, await s_events()
    if t == "xvs":
        ty = events.TYPES[p[1]]
        rows = [[(f"{h} ساعت", f"ad:xvh:{p[1]}:{h}") for h in (24, 48, 72, 168)]]
        return None, (f"{ty['e']} <b>{ty['n']}</b> — {ty['d']}\nچند ساعت؟", kb(rows + [[("🔙", "ad:xv")]]))
    if t == "xvh":
        typ, hours = p[1], int(p[2])
        ty = events.TYPES[typ]
        events.start(typ, hours, uid)
        await events.save()
        cnt = await world.broadcast_players(f"🎉 <b>رویداد {ty['n']} شروع شد!</b> {ty['e']}\n{ty['d']} — تا {hours} ساعت.\nاز فرصت استفاده کن! 🚀")
        world.news(f"🎉 رویداد «{ty['n']}» شروع شد ({hours} ساعت): {ty['d']}", important=True)
        await A.alog(uid, f"شروع رویداد {typ} {hours}h")
        return "✅ شروع شد", await s_events(f"✅ {ty['n']} شروع شد؛ برای {cnt} نفر خبر میره")
    if t == "xvx":
        events.stop(p[1])
        await events.save()
        await A.alog(uid, f"پایان رویداد {p[1]}")
        return "⏹", await s_events("⏹ رویداد تموم شد")
    if t == "xb":
        return None, s_boss_admin()
    if t == "xbh":
        ok, msg = await war.boss_start(int(p[1]), None, uid)
        await A.alog(uid, f"جنگ بزرگ {p[1]}h → {msg}")
        return ("✅" if ok else msg), s_boss_admin(msg)
    if t == "xbx":
        async with db.LOCK:
            await war.boss_finish(False)
        await A.alog(uid, "پایان دستی جنگ بزرگ")
        return "⏹", s_boss_admin("⏹ جنگ بزرگ تموم شد و جایزه‌ها (نصف) رفت")

    # --- آمار رشد
    if t == "gs":
        return None, await s_growth()
    if t == "gsp":
        png = growth.chart_png(await growth.series(14))
        if not png:
            return "matplotlib نصب نیست؛ نمودار متنی بالا رو ببین (pip install matplotlib)", None
        await bot.send_photo(uid, BufferedInputFile(png, filename="growth.png"), caption="📈 رشد EMPIRE ZERO")
        return "🖼 فرستاده شد", None

    # --- فصل
    if t == "sb":
        return None, await s_season()
    if t in ("sbw", "sbs"):
        w = "هفته" if t == "sbw" else "فصل"
        return None, (f"⚠️ <b>پایان {w} همین الان؟</b>\nجایزه‌ها به ۳ نفر اول هر جدول داده میشه و {w} جدید شروع میشه.",
                      kb([[("✅ بله، جایزه بده", f"ad:{t}y")], [("❌ نه", "ad:sb")]]))
    if t in ("sbwy", "sbsy"):
        txt = await world.finalize("w" if t == "sbwy" else "s")
        await world.broadcast_players(("🏅 <b>هفته تموم شد!</b>\n" if t == "sbwy" else "🏆 <b>فصل تموم شد!</b>\n") + txt)
        await A.alog(uid, "پایان دستی " + ("هفته" if t == "sbwy" else "فصل"))
        return "✅", await s_season("✅ انجام شد")

    # --- ضدتقلب
    if t == "ac":
        return None, await s_anticheat()
    if t == "acr":
        await guard.resolve(int(p[1]))
        return "✅", await s_anticheat("✅ هشدار بسته شد")
    return None


async def handle_input(m, S, w, txt, uid):
    act = w["act"]
    if act == "rs_find":
        ids = await A.find_targets(m, txt)
        if not ids:
            return A.retry(S, w, "چیزی پیدا نشد")
        if len(ids) > 1:
            docs = await db.C.find({"_id": {"$in": ids}}, {"name": 1, "leader": 1}).to_list(10)
            return "🔎 کدوم؟", kb([[(f"{d['name'][:20]} · {d['leader'][:12]}", f"ad:c:{d['_id']}")] for d in docs] + [HOME])
        S["tid"] = ids[0]
        d = await db.C.find_one({"_id": ids[0]}, {"name": 1})
        if not d:
            return "کشوری با این مشخصات نیست", kb([HOME])
        return (f"⚠️ <b>تأیید</b>\n♻️ ریست کشور «{esc(d['name'])}» (<code>{ids[0]}</code>)؟ برگشت‌پذیر نیست.",
                kb([[("✅ بله، انجام بده", "ad:ok:reset")], [("❌ نه", "ad:home")]]))
    if act == "reset_all":
        if not A.is_owner(uid):
            return "⛔ فقط مالک ربات", kb([HOME])
        if digits(txt).strip() != "ریست همه":
            return "↩️ متن تأیید درست نبود؛ چیزی ریست نشد.", kb([HOME])
        await A.q_backup(uid)                       # بکاپ قبل از ریست
        cnt = await reset_all()
        await A.alog(uid, f"ریست همه‌ی پلیرها ({cnt} کشور)")
        await world.broadcast_players("🔄 <b>همه‌ی کشورها ریست شدن!</b> از صفر شروع کنید و با «دنیای من» ادامه بدید 🌍")
        return f"✅ {cnt} کشور ریست شد (بکاپ قبلش فرستاده شد).", kb([HOME])
    if act == "ig_find":
        ids = await A.find_targets(m, txt)
        if not ids:
            return A.retry(S, w, "چیزی پیدا نشد")
        if len(ids) == 1:
            S["tid"] = ids[0]
            return await s_ig(S)
        docs = await db.C.find({"_id": {"$in": ids}}, {"name": 1, "leader": 1}).to_list(10)
        return "🔎 کدوم؟", kb([[(f"{d['name'][:20]} · {d['leader'][:12]}", f"ad:igp:{d['_id']}")] for d in docs] + [HOME])
    if act == "ig_amt":
        pn = A.parse_num(txt)
        if not pn or pn[0] != "add" or pn[1] == 0:
            return A.retry(S, w, "عدد معتبر بفرست (مثبت = بده، منفی = کسر؛ بدون = )")
        S["ig"] = {"key": w["key"], "amt": pn[1] if w["key"] != "coins" else int(pn[1]), "note": ""}
        return s_confirm(S)
    if act == "ig_note":
        if not S.get("ig"):
            return "چیزی برای ارسال نیست", kb([HOME])
        S["ig"]["note"] = txt[:300]
        return s_confirm(S)
    if act == "code_new":
        r = parse_code(txt)
        if isinstance(r, str):
            return A.retry(S, w, r)
        code, rew, uses, days = r
        if await db.CODES.find_one({"_id": code}):
            return A.retry(S, w, f"کد {code} از قبل وجود داره")
        await db.CODES.insert_one({"_id": code, "rew": rew, "max": uses, "used": 0, "users": [], "active": True,
                                   "exp": (time.time() + days * 86400) if days else 0, "created": time.time(), "by": uid})
        await A.alog(uid, f"ساخت کد {code} {rew} ×{uses}")
        return await s_code(code, f"✅ ساخته شد. بازیکن‌ها بنویسن «کد {code}»")
    return None
