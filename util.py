"""ابزارهای مشترک: فرمت، کیبورد (قفل‌شده روی صاحب منو)، تبدیل عدد."""
import contextvars
import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# صاحب منوی فعلی؛ هر دکمه «|uid» می‌گیره تا توی گروه کس دیگه نتونه دست بزنه
OWNER = contextvars.ContextVar("owner", default=None)
BACK = [("🔙 منو", "m")]

_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def esc(s):
    return html.escape(str(s))


def n(x):
    return f"{x:,.0f}"


def bar(v, w=10):
    k = int(round(max(0, min(100, v)) / 100 * w))
    return "▰" * k + "▱" * (w - k)


def kb(rows):
    o = OWNER.get()
    suf = f"|{o}" if o else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d + suf) for t, d in r] for r in rows])


def digits(s):
    return (s or "").translate(_FA)


def amount(s, maximum=None):
    """'۵k' → 5000 · 'همه' → maximum · نامعتبر → None"""
    s = digits(s).replace(",", "").replace("٬", "").strip().lower()
    if s in ("all", "همه", "کل", "max") and maximum is not None:
        v = int(maximum)
        return v if v > 0 else None
    mult = 1
    if s.endswith("k"):
        s, mult = s[:-1], 1000
    elif s.endswith("m"):
        s, mult = s[:-1], 1_000_000
    try:
        v = float(s) * mult
    except ValueError:
        return None
    v = int(v)
    return v if v > 0 else None
