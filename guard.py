"""ضدتقلب: تشخیص چندحسابی (نشونه‌ها، نه اثبات) و هشدار به چنل لاگ + پنل ادمین.
ربات تلگرام IP نمی‌بینه؛ برای همین فقط الگوهای رفتاری بررسی میشن و تصمیم نهایی با ادمینه."""
import re
import time

import config
import db
from core import tlog
from util import esc


def now():
    return time.time()


def uname_base(u):
    """یوزرنیم بدون عدد و آندرلاین (ali_123 و ali456 هم‌خانواده حساب میشن)."""
    return re.sub(r"[\d_]+", "", (u or "").lower())


async def flag(uid, kind, detail, score=1):
    """هشدار ثبت می‌کنه؛ همون نوع برای همون کاربر تا یک ساعت تکرار نمیشه."""
    if await db.FLAGS.find_one({"uid": uid, "kind": kind, "ts": {"$gt": now() - 3600}}):
        return None
    fid = await db.next_id("flag")
    await db.FLAGS.insert_one({"_id": fid, "uid": uid, "kind": kind, "detail": detail, "score": score,
                               "ts": now(), "resolved": False})
    tlog("🚨", "هشدار ضدتقلب", f"<code>{uid}</code> · {esc(kind)}\n{esc(detail)}")
    return fid


async def check_registration(c, inviter_id=None, username=""):
    """بعد از ثبت‌نام صدا زده میشه. (مشکوک؟، دلیل‌ها)"""
    reasons = []
    t = now()
    dup = await db.C.count_documents({"leader": c["leader"], "_id": {"$ne": c["_id"]}, "created": {"$gt": t - 3 * 86400}})
    if dup:
        reasons.append(f"نام مدیر تکراری ({dup} حساب دیگه با همین نام در ۳ روز اخیر)")
    base = uname_base(username)
    if len(base) >= 4:
        same = await db.C.count_documents({"uname_base": base, "_id": {"$ne": c["_id"]}, "created": {"$gt": t - 3 * 86400}})
        if same:
            reasons.append(f"یوزرنیم هم‌خانواده ({same} حساب مشابه)")
    if c.get("home"):
        burst = await db.C.count_documents({"home": c["home"], "created": {"$gt": t - 300}})
        if burst >= 4:
            reasons.append(f"{burst} ثبت‌نام در ۵ دقیقه از یک گروه")
    strong = False
    if inviter_id:
        cnt = await db.INVITES.count_documents({"by": inviter_id, "ts": {"$gt": t - 3600}})
        if cnt >= 4:
            reasons.append(f"دعوت‌کننده {cnt} دعوت در یک ساعت داشته")
        strong = cnt >= 6
    suspect = strong or len(reasons) >= 2
    if reasons:
        await flag(c["_id"], "چندحسابی؟", " | ".join(reasons) + (f" | دعوت‌کننده <code>{inviter_id}</code>" if inviter_id else ""),
                   score=len(reasons) + (2 if strong else 0))
    return suspect, reasons


async def record_transfer(frm, to, value, kind):
    """هر هدیه/معامله ثبت میشه؛ اگه چند حساب تازه به یه حساب پول بریزن هشدار میده."""
    t = now()
    young = t - frm["created"] < 3 * 86400
    await db.TRF.insert_one({"from": frm["_id"], "to": to["_id"], "value": value, "kind": kind, "ts": t, "young": young})
    rows = await db.TRF.find({"to": to["_id"], "ts": {"$gt": t - 86400}, "young": True}).to_list(200)
    senders = {r["from"] for r in rows}
    total = sum(r["value"] for r in rows)
    if len(senders) >= 3 or total >= 30000:
        await flag(to["_id"], "قیف انتقال", f"{len(senders)} حساب تازه (کمتر از ۳ روز) در ۲۴ ساعت مجموعاً {total:,.0f} (ارزش سکه) به این حساب فرستادن: "
                                            + ", ".join(str(x) for x in list(senders)[:6]), score=3)


async def recent(k=12, open_only=True):
    q = {"resolved": False} if open_only else {}
    return await db.FLAGS.find(q).sort("ts", -1).to_list(k)


async def resolve(fid):
    await db.FLAGS.update_one({"_id": fid}, {"$set": {"resolved": True}})
