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


def bar(v, w=10, inv=False):
    """نوار رنگی: سبز = خوب، زرد = متوسط، قرمز = بد. inv=True یعنی عدد بالا بده (مثل ناآرامی)."""
    v = max(0, min(100, v))
    k = int(round(v / 100 * w))
    good = 100 - v if inv else v
    col = "🟩" if good >= 60 else "🟨" if good >= 35 else "🟥"
    return col * k + "⬜" * (w - k)


# رنگ دکمه‌ها (Bot API 9.4+): primary=آبی · success=سبز · danger=قرمز · بدون رنگ = پیش‌فرض تلگرام
_EXACT = {"b": "primary", "p": "primary", "a": "primary", "r": "primary", "o": "primary", "top": "primary",
          "q": "primary", "sh": "primary", "k": "success", "t": "success", "x": "success", "d": "success",
          "wk": "success", "u": "danger", "g": "danger", "w": "danger", "s": "danger"}
_PREFIX = (("b:buy", "success"), ("u:buy", "success"), ("k:dep", "success"), ("k:rep", "success"),
           ("k:loan", "primary"), ("k:wd", "primary"), ("t:buy", "success"), ("t:sell", "danger"),
           ("x:b", "success"), ("x:s", "danger"), ("q:claim", "success"), ("d:go", "success"),
           ("wk:go", "success"), ("sh:go", "success"), ("g:up", "success"), ("r:up", "success"),
           ("p:", "primary"), ("w:go", "danger"), ("w:pick", "danger"), ("s:go", "danger"),
           ("s:pick", "danger"), ("a:strike", "danger"), ("a:donate", "success"), ("o:do:crack", "danger"),
           ("o:do", "primary"),
           ("rg:x", "danger"), ("rg:ok", "success"), ("rg:use", "success"), ("rg:d:eco", "success"),
           ("rg:d:mil", "danger"), ("rg:d:bal", "primary"), ("rg:rn", "primary"), ("rg:typ", "primary"),
           ("rg:e", "primary"),
           ("ad:ok", "success"), ("ad:bcgo", "success"), ("ad:gfgo", "success"), ("ad:ub", "success"),
           ("ad:ask", "danger"), ("ad:cban", "danger"), ("ad:cdanger", "danger"), ("ad:lx", "danger"),
           ("ad:wx", "danger"), ("ad:amdel", "danger"), ("ad:npa", "danger"), ("ad:npr", "danger"),
           ("ad:wreset", "danger"), ("ad:tnr", "danger"), ("ad:cx:wipeu", "danger"), ("ad:cx:zerob", "danger"),
           ("ad:cs:0", "danger"), ("ad:cs", "success"), ("ad:gfr", "success"), ("ad:bca", "primary"),
           ("ad:cx", "success"), ("ad:", "primary"))


def style_of(text, data):
    if text.startswith("🔙") or data == "m":
        return None
    if "انصراف" in text:
        return "danger"
    if data in _EXACT:
        return _EXACT[data]
    for pre, st in _PREFIX:
        if data.startswith(pre):
            return st
    return None


def _btn(t, d, suf):
    if d.startswith("url:"):
        return InlineKeyboardButton(text=t, url=d[4:])
    st = style_of(t, d)
    kw = {"style": st} if st else {}
    return InlineKeyboardButton(text=t, callback_data=d + suf, **kw)


def kb(rows):
    o = OWNER.get()
    suf = f"|{o}" if o else ""
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(t, d, suf) for t, d in r] for r in rows])


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
