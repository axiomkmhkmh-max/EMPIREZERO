"""اعتبارسنجی و ضدسوءاستفاده‌ی ثبت‌نام."""
import re
import time
import unicodedata

import config
from util import digits

_ZW = {ord(ch): None for ch in "\u200b\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff\u0640"}
_AR = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ؤ": "و"})
_DIAC = re.compile("[\u064B-\u065F\u0670]")
_ALLOWED = re.compile(r"^[\u0621-\u063A\u0641-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CCA-Za-z0-9\u200c _\-]+$")
_LETTER = re.compile(r"[\u0621-\u063A\u0641-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CCA-Za-z]")

ANON_ID = 1087968824          # GroupAnonymousBot


def clean(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = digits(s).translate(_ZW).translate(_AR)
    s = _DIAC.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def name_key(s):
    return re.sub(r"[ \u200c_\-]", "", clean(s).lower())


def validate_name(raw):
    """(True, نام‌تمیز) یا (False, پیام‌خطا)"""
    name = clean(raw)
    if not 2 <= len(name) <= 24:
        return False, "اسم کشور باید ۲ تا ۲۴ حرف باشه"
    if not _ALLOWED.match(name):
        return False, "فقط حروف فارسی/انگلیسی، عدد، فاصله، - و _ مجازه (بدون لینک، @ و ایموجی)"
    if len(_LETTER.findall(name)) < 2:
        return False, "اسم باید حداقل ۲ حرف داشته باشه"
    low = name.lower()
    if any(w in low for w in config.RESERVED_WORDS):
        return False, "این اسم رزرو یا غیرمجازه"
    if any(name_key(sp["name"]) == name_key(name) for sp in config.NPCS):
        return False, "این اسم مال یکی از کشورهای جهانه"
    return True, name


_tries = {}


def throttle(uid, key="reg"):
    """True یعنی مجازه. حداکثر REG_TRIES[0] بار در REG_TRIES[1] ثانیه."""
    mx, win = config.REG_TRIES
    t = time.time()
    lst = [x for x in _tries.get((key, uid), []) if t - x < win]
    if len(lst) >= mx:
        _tries[(key, uid)] = lst
        return False
    lst.append(t)
    _tries[(key, uid)] = lst
    return True
