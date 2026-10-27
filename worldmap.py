"""🗺 نقشه‌ی زنده‌ی جهان (خالص: بدون دیتابیس و تلگرام؛ فقط Pillow).

هر استان = یه خونه‌ی شش‌ضلعی. قاره‌ها یه‌بار با seed ثابت ساخته میشن، پس نقشه همیشه همونه؛
فقط رنگ مالکیت عوض میشه. هر کشور از یه «پایتخت» ثابت شروع می‌کنه و به‌اندازه‌ی استان‌هاش رشد می‌کنه؛
یعنی تسخیر یه استان واقعاً روی نقشه دیده میشه.

ورودی: لیست کشورها (id, name, land, npc) + seeds (id → شماره‌ی پایتخت). خروجی: تصویر PNG + اطلاعات راهنما.
"""
import colorsys
import io
import math
import random
from functools import lru_cache

import config

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TIERS = ((34, 22), (46, 30), (60, 38), (80, 50), (110, 66), (150, 90), (200, 120), (260, 156), (320, 192))     # (ستون، ردیف)؛ با رشد بازی نقشه بزرگ‌تر میشه
LAND_FRAC = 0.42
SEED = 6
CONT_F = 2.2                                            # فرکانس قاره‌ها (بیشتر = قاره‌ی کوچک‌تر و بیشتر)
WARP = 0.9
SQ3 = math.sqrt(3)
TOP_N = 12                                              # این تعداد کشور برتر روی نقشه شماره می‌خورن
NAME_N = 36                                             # این تعداد کشور برتر اسمشون هم روی نقشه نوشته میشه
FILL = config.MAP_FILL                                  # زمین آزاد ≈ ۲٫۲ برابر خاک اشغالی؛ جا برای تازه‌وارد و استعمار
MIN_TIER = config.MAP_MIN_TIER                          # نقشه هیچ‌وقت از این کوچیک‌تر نمیشه

_EDGE_EVEN = ((1, 0), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1))     # E, SE, SW, W, NW, NE
_EDGE_ODD = ((1, 0), (1, 1), (0, 1), (-1, 0), (0, -1), (1, -1))

EMOJI_COLORS = {"🟥": (221, 46, 68), "🟧": (244, 144, 12), "🟨": (253, 203, 88), "🟩": (120, 177, 89),
                "🟦": (85, 172, 238), "🟪": (170, 142, 214), "🟫": (193, 105, 79), "⬛": (49, 55, 61), "⬜": (230, 231, 232)}


# ------------------------------------------------------------------ شبکه و قاره‌ها
def _nbrs(W, H):
    out = []
    for r in range(H):
        offs = _EDGE_ODD if r & 1 else _EDGE_EVEN
        for q in range(W):
            row = []
            for dq, dr in offs:
                x, y = q + dq, r + dr
                row.append(y * W + x if 0 <= x < W and 0 <= y < H else -1)
            out.append(row)
    return out


def _xy(i, W):
    r, q = divmod(i, W)
    return q + 0.5 * (r & 1), r * 0.8660254


def _h3(ix, iy, iz):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ SEED
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _vn3(x, y, z):
    """نویز مقداریِ سه‌بعدی (نرم)؛ روی کره پیوسته‌ست، پس نه درز داره نه کشیدگی قطب."""
    ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - ix, y - iy, z - iz
    fx, fy, fz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    def l(a, b, t):
        return a + (b - a) * t
    return l(l(l(_h3(ix, iy, iz), _h3(ix + 1, iy, iz), fx), l(_h3(ix, iy + 1, iz), _h3(ix + 1, iy + 1, iz), fx), fy),
             l(l(_h3(ix, iy, iz + 1), _h3(ix + 1, iy, iz + 1), fx), l(_h3(ix, iy + 1, iz + 1), _h3(ix + 1, iy + 1, iz + 1), fx), fy), fz)


def _fbm3(x, y, z, octs):
    t = n = 0.0
    a, f = 1.0, 1.0
    for _ in range(octs):
        t += a * _vn3(x * f + 17.3 * f, y * f - 9.1 * f, z * f + 4.7 * f)
        n += a
        a *= 0.5
        f *= 2.03
    return t / n


def _conts(k=7):
    """مرکز و اندازه‌ی قاره‌ها روی کره: نقطه‌هایی که تا جای ممکن از هم دورن (ثابت با SEED)."""
    rr = random.Random(SEED * 7 + 1)
    def rp():
        z = rr.uniform(-0.8, 0.8)
        t = rr.uniform(0, 2 * math.pi)
        c = math.sqrt(1 - z * z)
        return (c * math.cos(t), z, c * math.sin(t))
    pts = [rp()]
    while len(pts) < k:
        cand = [rp() for _ in range(60)]
        pts.append(max(cand, key=lambda p: min(math.acos(max(-1, min(1, p[0] * q[0] + p[1] * q[1] + p[2] * q[2]))) for q in pts)))
    return tuple((p[0], p[1], p[2], rr.uniform(0.32, 0.62)) for p in pts)


CONTS = _conts()


def _sph(q, r, W, H):
    """مختصات خونه روی کره (همون نگاشتی که مینی‌اپ استفاده می‌کنه)."""
    u = (q + 0.5 * (r & 1) + 0.5) / (W + 0.5)
    lon = (u - 0.5) * 2 * math.pi
    lat = (0.5 - (1.5 * r + 1) / (1.5 * H + 0.5)) * math.pi
    c = math.cos(lat)
    return c * math.sin(lon), math.sin(lat), c * math.cos(lon), lat


def _components(cells, nb, N):
    """قاره‌ها (کامپوننت‌های همبند خشکی): (خونه→شماره‌ی قاره، فهرست اعضای هر قاره)."""
    is_land = [False] * N
    for c in cells:
        is_land[c] = True
    comp, groups = {}, []
    for c in cells:
        if c in comp:
            continue
        cid, members, st = len(groups), [], [c]
        comp[c] = cid
        while st:
            a = st.pop()
            members.append(a)
            for b in nb[a]:
                if b >= 0 and is_land[b] and b not in comp:
                    comp[b] = cid
                    st.append(b)
        groups.append(members)
    return comp, groups


def _capital_points(cells, W, nb, N):
    """جای پایتخت‌ها به ترتیب ثبت‌نام: از بزرگ‌ترین قاره شروع میشه و از مرکزش به بیرون پر میشه، با فاصله‌ی حداقلی بین پایتخت‌ها
    (دور اول فاصله‌ی زیاد؛ اگه جا کم بیاد دورهای بعدی با فاصله‌ی کمتر) → از همون اول همسایه داری و نقشه خلوت و بی‌هدف نیست."""
    comp, groups = _components(cells, nb, N)
    xy = {c: _xy(c, W) for c in cells}
    order = sorted(range(len(groups)), key=lambda i: (-len(groups[i]), i))
    limit = min(len(cells), 1500)
    pts, taken, grid = [], set(), {}
    bucket = max(config.MAP_SEP) if config.MAP_SEP else 6.0

    def near(x, y, sep):
        gx, gy = int(x // bucket), int(y // bucket)
        for ix in range(gx - 1, gx + 2):
            for iy in range(gy - 1, gy + 2):
                for (px, py) in grid.get((ix, iy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < sep * sep:
                        return True
        return False

    for sep in config.MAP_SEP:
        for gi in order:
            mem = groups[gi]
            mx = sum(xy[c][0] for c in mem) / len(mem)
            my = sum(xy[c][1] for c in mem) / len(mem)
            cand = sorted((c for c in mem if c not in taken),
                          key=lambda c: (math.hypot(xy[c][0] - mx, xy[c][1] - my) + (_hs(c, gi, 7) % 100) / 100 * sep * 0.8, c))
            for c in cand:
                if len(pts) >= limit:
                    return pts
                x, y = xy[c]
                if near(x, y, sep):
                    continue
                pts.append(c)
                taken.add(c)
                grid.setdefault((int(x // bucket), int(y // bucket)), []).append((x, y))
    for c in cells:                                                          # آخرین پناه: هر خونه‌ی باقی‌مونده
        if len(pts) >= limit:
            break
        if c not in taken:
            pts.append(c)
            taken.add(c)
    return pts


@lru_cache(maxsize=8)
def continents(tier):
    """(خونه→شماره‌ی قاره) برای اندازه‌ی نقشه‌ی tier؛ برای فاصله و همسایگی."""
    W, H, nb, cells, pts, elev = make_world(tier)
    return _components(cells, nb, W * H)[0]


def cell_xy(tier, cell):
    return _xy(cell, TIERS[tier][0])


def _hs(a, b, c):
    """هش ساده و ثابت (بدون random سراسری) برای شکستن مساوی‌ها."""
    return ((a * 73856093) ^ (b * 19349663) ^ (c * 83492791)) & 0xFFFF


@lru_cache(maxsize=8)
def make_world(tier):
    """(W, H, نقشه‌ی همسایه‌ها، فهرست خونه‌های خشکی، نقطه‌های پایتخت به ترتیب فاصله‌ی حداکثری، ارتفاع 0..1 هر خونه)

    قاره‌ها از نویز سه‌بعدیِ روی خودِ کره ساخته میشن (چند قاره‌ی نامنظم + جزیره + رشته‌کوه)؛
    برای همه‌ی اندازه‌ها یه دنیای یکسانه و فقط ریزتر میشه."""
    W, H = TIERS[tier]
    N = W * H
    rnd = random.Random(SEED + tier)
    nb = _nbrs(W, H)
    f, ridge, pl = [0.0] * N, [0.0] * N, [0.0] * N
    for i in range(N):
        q, r = i % W, i // W
        x, y, z, lat = _sph(q, r, W, H)
        wx, wy, wz = (_fbm3(x * 1.7 + 3, y * 1.7, z * 1.7, 2) - 0.5) * WARP, (_fbm3(x * 1.7, y * 1.7 + 5, z * 1.7, 2) - 0.5) * WARP, (_fbm3(x * 1.7, y * 1.7, z * 1.7 + 8, 2) - 0.5) * WARP
        px, py, pz = x + wx, y + wy, z + wz                                  # کمی تابِ دامنه تا ساحل‌ها طبیعی و پرپیچ‌وخم بشن
        det = 0.62 * _fbm3(px * CONT_F, py * CONT_F, pz * CONT_F, 3) + 0.26 * _fbm3(px * 3.0, py * 3.0, pz * 3.0, 3) + 0.12 * _fbm3(px * 7.0, py * 7.0, pz * 7.0, 2)
        infl = 0.0
        for cx, cy, cz, sz in CONTS:                                         # هر قاره یه هسته داره؛ پس قاره‌ها از هم جدا می‌مونن
            ang = math.acos(max(-1.0, min(1.0, x * cx + y * cy + z * cz)))
            infl = max(infl, math.exp(-(ang / sz) ** 2))
        v = 0.68 * infl + 0.58 * det
        a = abs(lat) / (math.pi / 2)
        v -= 0.50 * max(0.0, (a - 0.78) / 0.22) ** 1.5                      # نزدیک قطب‌ها یخ و دریا
        edge = min(q, W - 1 - q, r, H - 1 - r)
        v -= 0.9 * max(0, 3 - edge)                                          # حاشیه‌ی نقشه همیشه اقیانوسه
        f[i] = v
        ridge[i] = 1.0 - abs(2.0 * _fbm3(x * 3.3 + 20, y * 3.3, z * 3.3, 3) - 1.0)
    thr = sorted(f, reverse=True)[int(N * LAND_FRAC)]
    land = [v > thr for v in f]
    seen = [False] * N                                                       # جزیره‌های خیلی ریز (کمتر از ۴ خونه) حذف
    for i in range(N):
        if land[i] and not seen[i]:
            comp, st = [], [i]
            seen[i] = True
            while st:
                a = st.pop()
                comp.append(a)
                for b in nb[a]:
                    if b >= 0 and land[b] and not seen[b]:
                        seen[b] = True
                        st.append(b)
            if len(comp) < 4:
                for a in comp:
                    land[a] = False
    cells = [i for i in range(N) if land[i]]
    pts = _capital_points(cells, W, nb, N) if cells else []
    fmax = max((f[c] for c in cells), default=thr + 1)
    elev = [0.0] * N
    for c in cells:
        inl = max(0.0, min(1.0, (f[c] - thr) / max(1e-9, fmax - thr)))      # هرچی داخل‌تر، بلندتر
        rg = ridge[c] ** 2.2 * min(1.0, inl * 3.0)                          # رشته‌کوه فقط داخل خشکی
        elev[c] = max(0.0, min(1.0, 0.10 + 0.34 * inl ** 0.8 + 0.62 * rg))
    return W, H, nb, cells, pts, elev


TIER_FLOOR = 0            # نقشه فقط بزرگ میشه نه کوچیک (کوچیک‌شدن مختصات همه رو دوباره جابه‌جا می‌کرد)


def pick_tier(total_land, players=0):
    """اندازه‌ی نقشه خودکار از روی خاک اشغالی و تعداد کشورها: جا برای خاک فعلی × FILL
    + به‌ازای هر کشور MAP_FREE_PER_PLAYER خونه‌ی خالی (تازه‌وارد و استعمار). کف هم داره تا هیچ‌وقت کوچیک نشه."""
    global TIER_FLOOR
    need = total_land * FILL + players * config.MAP_FREE_PER_PLAYER + 30
    pick = len(TIERS) - 1
    for t in range(MIN_TIER, len(TIERS)):
        if len(make_world(t)[3]) >= need:
            pick = t
            break
    pick = max(pick, TIER_FLOOR)
    TIER_FLOOR = pick
    return pick


# ------------------------------------------------------------------ مالکیت (رشد از پایتخت)
def assign(tier, entries):
    """entries = [(cid, seed_idx, quota)] → (own: خونه→اندیس entries یا -1، پایتخت هر ورودی)"""
    W, H, nb, cells, pts, _el = make_world(tier)
    N = W * H
    own = [-1] * N
    order = sorted(range(len(entries)), key=lambda k: (entries[k][1], entries[k][0]))
    caps, cnt, front = {}, [0] * len(entries), [set() for _ in entries]
    is_land = [False] * N
    for c in cells:
        is_land[c] = True

    def claim(k, cell):
        own[cell] = k
        cnt[k] += 1
        front[k].discard(cell)
        for b in nb[cell]:
            if b >= 0 and is_land[b] and own[b] == -1:
                front[k].add(b)

    for k in order:
        _, si, quota = entries[k]
        if quota <= 0 or not pts:
            continue
        cell = pts[si % len(pts)]
        if own[cell] != -1:                                  # برخورد نادر: نزدیک‌ترین خونه‌ی آزاد
            cx, cy = _xy(cell, W)
            free = [c for c in cells if own[c] == -1]
            if not free:
                continue
            cell = min(free, key=lambda c: (_xy(c, W)[0] - cx) ** 2 + (_xy(c, W)[1] - cy) ** 2)
        caps[k] = cell
        claim(k, cell)
    progress = True
    while progress:
        progress = False
        for k in order:
            if k not in caps or cnt[k] >= entries[k][2]:
                continue
            for c in [c for c in front[k] if own[c] != -1]:
                front[k].discard(c)
            if front[k]:
                si_ = entries[k][1]                          # انتخاب فقط به خود کشور وابسته‌ست (نه ترتیب بقیه)؛ پس نقشه پایدار می‌مونه
                cell = max(front[k], key=lambda c: (sum(1 for b in nb[c] if b >= 0 and own[b] == k), _hs(si_, c, cnt[k]), c))
            else:                                            # محاصره شده؛ نزدیک‌ترین خونه‌ی آزاد (جزیره‌ی دورافتاده)
                cx, cy = _xy(caps[k], W)
                free = [c for c in cells if own[c] == -1]
                if not free:
                    continue
                cell = min(free, key=lambda c: (_xy(c, W)[0] - cx) ** 2 + (_xy(c, W)[1] - cy) ** 2)
            claim(k, cell)
            progress = True
    return own, caps


# ------------------------------------------------------------------ رنگ و فونت
# پالت دست‌چین (رنگ‌های متمایز ولی خوش‌رنگ، نه نئونی)؛ بعد از تموم شدن، همون رنگ‌ها با روشنایی دیگه تکرار میشن
PALETTE = ((214, 69, 65), (52, 120, 208), (236, 164, 40), (46, 160, 110), (150, 84, 190), (222, 112, 40),
           (44, 168, 184), (200, 76, 142), (118, 160, 44), (88, 96, 208), (180, 120, 70), (60, 140, 150),
           (230, 196, 60), (170, 60, 90), (100, 180, 140), (140, 110, 220))


def color_of(seed_idx, npc=False):
    base = PALETTE[seed_idx % len(PALETTE)]
    ring = (seed_idx // len(PALETTE)) % 3
    if ring:
        base = _mix(base, (255, 255, 255), 0.18 * ring) if ring == 1 else _shade(base, 0.72)
    if npc:                                   # NPCها کم‌رنگ‌تر و خاکستری‌ترن تا بازیکن‌ها دیده بشن
        g = int(sum(base) / 3)
        base = _mix(base, (g, g, g), 0.55)
    return base


def nearest_emoji(rgb):
    return min(EMOJI_COLORS, key=lambda e: sum((a - b) ** 2 for a, b in zip(EMOJI_COLORS[e], rgb)))


@lru_cache(maxsize=32)
def _font(size):
    size = max(8, int(size))
    paths = ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"]
    try:
        import matplotlib
        paths.append(matplotlib.get_data_path() + "/fonts/ttf/DejaVuSans-Bold.ttf")
    except Exception:
        pass
    for path in paths:
        try:
            return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def short(name, k):
    """اسم بلند رو وسط کلمه نمی‌بُره؛ آخرش «…» می‌ذاره."""
    name = " ".join(str(name).split())
    if len(name) <= k:
        return name
    cut = name[:k - 1]
    if " " in cut and name[k - 1:k] != " ":
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


def _shade(rgb, k):
    return tuple(max(0, min(255, int(c * k))) for c in rgb)


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


# ------------------------------------------------------------------ فارسی روی تصویر (بدون وابستگی؛ شکل‌دهی حروف + راست‌به‌چپ)
# حرف: (جدا، پایانی، ابتدایی، میانی)؛ حروف دوشکلی فقط جدا/پایانی دارن
_FA = {
    "ا": ("ﺍ", "ﺎ"), "آ": ("ﺁ", "ﺂ"), "ب": ("ﺏ", "ﺐ", "ﺑ", "ﺒ"), "پ": ("ﭖ", "ﭗ", "ﭘ", "ﭙ"),
    "ت": ("ﺕ", "ﺖ", "ﺗ", "ﺘ"), "ث": ("ﺙ", "ﺚ", "ﺛ", "ﺜ"), "ج": ("ﺝ", "ﺞ", "ﺟ", "ﺠ"), "چ": ("ﭺ", "ﭻ", "ﭼ", "ﭽ"),
    "ح": ("ﺡ", "ﺢ", "ﺣ", "ﺤ"), "خ": ("ﺥ", "ﺦ", "ﺧ", "ﺨ"), "د": ("ﺩ", "ﺪ"), "ذ": ("ﺫ", "ﺬ"), "ر": ("ﺭ", "ﺮ"),
    "ز": ("ﺯ", "ﺰ"), "ژ": ("ﮊ", "ﮋ"), "س": ("ﺱ", "ﺲ", "ﺳ", "ﺴ"), "ش": ("ﺵ", "ﺶ", "ﺷ", "ﺸ"),
    "ص": ("ﺹ", "ﺺ", "ﺻ", "ﺼ"), "ض": ("ﺽ", "ﺾ", "ﺿ", "ﻀ"), "ط": ("ﻁ", "ﻂ", "ﻃ", "ﻄ"), "ظ": ("ﻅ", "ﻆ", "ﻇ", "ﻈ"),
    "ع": ("ﻉ", "ﻊ", "ﻋ", "ﻌ"), "غ": ("ﻍ", "ﻎ", "ﻏ", "ﻐ"), "ف": ("ﻑ", "ﻒ", "ﻓ", "ﻔ"), "ق": ("ﻕ", "ﻖ", "ﻗ", "ﻘ"),
    "ک": ("ﮎ", "ﮏ", "ﮐ", "ﮑ"), "گ": ("ﮒ", "ﮓ", "ﮔ", "ﮕ"), "ل": ("ﻝ", "ﻞ", "ﻟ", "ﻠ"), "م": ("ﻡ", "ﻢ", "ﻣ", "ﻤ"),
    "ن": ("ﻥ", "ﻦ", "ﻧ", "ﻨ"), "ه": ("ﻩ", "ﻪ", "ﻫ", "ﻬ"), "و": ("ﻭ", "ﻮ"), "ی": ("ﯼ", "ﯽ", "ﯾ", "ﯿ"),
    "ء": ("ﺀ", "ﺀ"), "ئ": ("ﺉ", "ﺊ", "ﺋ", "ﺌ"), "ؤ": ("ﺅ", "ﺆ"), "ة": ("ﺓ", "ﺔ"),
}
_FA_ALIAS = {"ك": "ک", "ي": "ی", "ى": "ی", "أ": "ا", "إ": "ا"}
_NOJOIN = "ء"


def _can_next(ch):          # آیا این حرف می‌تونه به حرف بعدی بچسبه؟
    f = _FA.get(ch)
    return bool(f) and len(f) == 4


def fa(text):
    """متن فارسی/لاتین رو برای رسم با PIL آماده می‌کنه (حروف چسبیده + ترتیب بصری). ایموجی‌ها حذف میشن."""
    chars = []
    for ch in str(text):
        ch = _FA_ALIAS.get(ch, ch)
        if ch == "‌":          # نیم‌فاصله: چسبندگی رو قطع می‌کنه
            chars.append("\0")
        elif ord(ch) > 0xFFFF or 0x2190 <= ord(ch) <= 0x2BFF or 0xFE00 <= ord(ch) <= 0xFE0F or ch == "️":
            continue
        else:
            chars.append(ch)
    out = []
    for i, ch in enumerate(chars):
        if ch not in _FA:
            out.append(None if ch == "\0" else ch)
            continue
        prev = chars[i - 1] if i else ""
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        pj = bool(prev) and _can_next(prev)
        nj = _can_next(ch) and nxt in _FA and ch not in _NOJOIN
        f = _FA[ch]
        if ch == "ل" and nxt == "ا":                      # لام‌الف
            out.append("ﻼ" if pj else "ﻻ")
            chars[i + 1] = "\1"
            continue
        if ch == "\1":
            continue
        if len(f) == 2:
            out.append(f[1] if pj else f[0])
        else:
            out.append(f[3] if pj and nj else f[1] if pj else f[2] if nj else f[0])
    out = [c for c in out if c not in (None, "\1")]
    rev = out[::-1]
    res, i = [], 0
    while i < len(rev):                                   # عدد/لاتین داخل متن راست‌به‌چپ جهتش رو حفظ می‌کنه
        if rev[i].isascii() and rev[i].isalnum():
            j = i
            while j < len(rev) and rev[j].isascii() and rev[j].isalnum():
                j += 1
            res += rev[i:j][::-1]
            i = j
        else:
            res.append(rev[i])
            i += 1
    return "".join(res)


# ------------------------------------------------------------------ ساخت چیدمان
def layout(countries, seeds):
    """countries = [dict(id, name, land, npc)] → دیکشنری چیدمان (قابل کش)"""
    cs = [c for c in countries if c["land"] > 0]
    total = sum(c["land"] for c in cs)
    tier = pick_tier(total, len(cs))
    entries = [(c["id"], seeds.get(c["id"], 0), c["land"]) for c in cs]
    own, caps = assign(tier, entries)
    ranked = sorted(range(len(cs)), key=lambda k: (-cs[k]["land"], entries[k][1]))
    return dict(tier=tier, cs=cs, entries=entries, own=own, caps=caps, ranked=ranked, total=total,
                claimed=sum(1 for o in own if o != -1), land_cells=len(make_world(tier)[3]))


def legend(lay, k=10):
    """[(شماره، کشور، رنگ، ایموجی رنگ)] برای کپشن"""
    out = []
    for num, k_i in enumerate(lay["ranked"][:k], 1):
        c = lay["cs"][k_i]
        rgb = color_of(lay["entries"][k_i][1], c.get("npc"))
        out.append((num, c, rgb, nearest_emoji(rgb)))
    return out


# ------------------------------------------------------------------ نقاشی
def _terrain(e):
    """رنگ زمینِ بدون صاحب بر اساس ارتفاع: دشت ← جنگل ← کوه ← صخره"""
    if e < 0.22:
        return (92, 126, 88)
    if e < 0.45:
        return (112, 134, 86)
    if e < 0.70:
        return (134, 120, 94)
    return (128, 126, 134)


def _castle(d, x, y, u, fill, outline):
    """قلعه‌ی کوچیک؛ (x, y) = وسط پایین، u = اندازه"""
    w, h = u * 1.0, u * 0.8
    body = [(x - w / 2, y), (x - w / 2, y - h), (x - w / 2 + u * 0.18, y - h), (x - w / 2 + u * 0.18, y - h - u * 0.22),
            (x - w / 6, y - h - u * 0.22), (x - w / 6, y - h), (x + w / 6, y - h), (x + w / 6, y - h - u * 0.22),
            (x + w / 2 - u * 0.18, y - h - u * 0.22), (x + w / 2 - u * 0.18, y - h), (x + w / 2, y - h), (x + w / 2, y)]
    d.polygon(body, fill=fill, outline=outline)
    d.rectangle([x - u * 0.1, y - u * 0.34, x + u * 0.1, y], fill=outline)


def _crown(d, x, y, u, fill=(255, 205, 40), outline=(90, 55, 0)):
    poly = [(-0.62, 0.32), (-0.62, -0.38), (-0.32, -0.08), (0, -0.62), (0.32, -0.08), (0.62, -0.38), (0.62, 0.32)]
    pp = [(x + px * u, y + py * u) for px, py in poly]
    d.polygon(pp, fill=fill)
    d.line(pp + [pp[0]], fill=outline, width=max(2, int(u * 0.09)))
    for px, py in ((-0.62, -0.38), (0, -0.62), (0.62, -0.38)):
        r = u * 0.12
        d.ellipse([x + px * u - r, y + py * u - r, x + px * u + r, y + py * u + r], fill=(255, 70, 90), outline=outline)


def render(lay, crown_id=None, crown_name=""):
    """تصویر بزرگ و سه‌بعدی (PIL). برمی‌گردونه (تصویر، {id کشور: (x, y)}، اندازه‌ی خونه S)."""
    W, H, nb, cells, pts, elev = make_world(lay["tier"])
    own, caps, cs, entries = lay["own"], lay["caps"], lay["cs"], lay["entries"]
    S = max(12.0, min(34.0, 4600 / (SQ3 * (W + 0.5))))
    m = int(S * 1.6)
    top = int(S * 3.4)
    foot = int(S * 1.7)
    lift_max = S * 1.0
    mapw = int(S * SQ3 * (W + 0.5)) + 2 * m
    maph = int(S * (1.5 * H + 0.5) + lift_max) + 2 * m
    panel = int(S * 15)
    wpx, hpx = mapw + panel, top + maph + foot
    is_land = [False] * (W * H)
    for c in cells:
        is_land[c] = True

    def ctr(i):
        r, q = divmod(i, W)
        return m + S * SQ3 * (q + 0.5 * (r & 1) + 0.5), top + m + lift_max * 0.6 + S * (1.5 * r + 1.0)

    def corners(cx, cy, k):
        return [(cx + k * math.cos(math.radians(60 * j - 30)), cy + k * math.sin(math.radians(60 * j - 30))) for j in range(6)]

    # ---------- اقیانوس: گرادیان + شبکه‌ی عرض/طول + آب کم‌عمق نورانی
    ocean = Image.new("RGB", (mapw, hpx))
    od = ImageDraw.Draw(ocean)
    for y in range(hpx):
        t = y / hpx
        od.line([(0, y), (mapw, y)], fill=(int(6 + 10 * t), int(22 + 40 * t), int(48 + 64 * t)))
    step = S * SQ3 * 6
    x = m + step * 0.5
    while x < mapw:
        od.line([(x, top), (x, hpx - foot)], fill=(26, 70, 118), width=1)
        x += step
    y = top + step * 0.5
    while y < hpx - foot:
        od.line([(0, y), (mapw, y)], fill=(26, 70, 118), width=1)
        y += step
    glow = Image.new("L", (mapw, hpx), 0)
    gd = ImageDraw.Draw(glow)
    for i in range(W * H):
        if not is_land[i] and any(b >= 0 and is_land[b] for b in nb[i]):
            cx, cy = ctr(i)
            gd.polygon(corners(cx, cy, S * 1.05), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.9))
    shallow = Image.new("RGB", (mapw, hpx), (36, 128, 186))
    ocean = Image.composite(shallow, ocean, glow.point(lambda v: int(v * 0.62)))
    # سایه‌ی خشکی روی آب
    sh = Image.new("L", (mapw, hpx), 0)
    sd = ImageDraw.Draw(sh)
    for c in cells:
        cx, cy = ctr(c)
        sd.polygon(corners(cx + S * 0.25, cy + S * 0.5, S), fill=170)
    sh = sh.filter(ImageFilter.GaussianBlur(S * 0.55))
    ocean = Image.composite(Image.new("RGB", (mapw, hpx), (3, 10, 24)), ocean, sh)

    img = Image.new("RGB", (wpx, hpx), (7, 12, 26))
    img.paste(ocean, (0, 0))
    d = ImageDraw.Draw(img)
    rnd = random.Random(SEED)
    pos = {}
    for k, cell in caps.items():
        cx, cy = ctr(cell)
        pos[cs[k]["id"]] = (cx, cy - S * (0.12 + 0.8 * elev[cell]))

    # ---------- خشکی سه‌بعدی؛ ردیف‌به‌ردیف از بالا به پایین تا جلویی‌ها روی عقبی‌ها بیفتن
    for c in sorted(cells, key=lambda i: (i // W, i % W)):
        cx, cy = ctr(c)
        e = elev[c]
        lift = S * (0.12 + 0.8 * e)
        o = own[c]
        base = _terrain(e) if o == -1 else color_of(entries[o][1], cs[o].get("npc"))
        jitter = 0.95 + rnd.random() * 0.08
        face = _shade(_mix(base, (255, 255, 255), 0.10 * e), (0.9 + 0.2 * e) * jitter)
        T = corners(cx, cy - lift, S * 0.985)
        G = [(px, py + lift + S * 0.16) for px, py in T]
        for a_, b_, k_ in ((0, 1, 0.66), (1, 2, 0.52), (2, 3, 0.42), (3, 4, 0.58)):        # دیواره‌ی وجه‌دار
            d.polygon([T[a_], T[b_], G[b_], G[a_]], fill=_shade(base, k_ * 0.85))
        d.polygon(T, fill=face)
        hl = corners(cx - S * 0.06, cy - lift - S * 0.08, S * 0.6)
        d.polygon(hl, fill=_shade(face, 1.07))
        if e > 0.93:                                                    # قله‌ی برفی (فقط بلندترین‌ها)
            d.polygon(corners(cx, cy - lift - S * 0.05, S * 0.36), fill=(240, 245, 252))
        # ساحل و مرز کشورها
        for j, b in enumerate(nb[c]):
            p1, p2 = T[j], T[(j + 1) % 6]
            if b < 0 or not is_land[b]:
                d.line([p1, p2], fill=(10, 34, 62), width=max(2, int(S * 0.14)))
            elif own[b] != own[c] and (own[c] != -1 or own[b] != -1):
                d.line([p1, p2], fill=(250, 250, 240), width=max(3, int(S * 0.2)))
                d.line([p1, p2], fill=(30, 30, 46), width=max(1, int(S * 0.07)))

    # ---------- نورپردازی سلطنتی دور تاج
    layer = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if crown_id in pos:
        x, y = pos[crown_id]
        for rr, al in ((S * 4.2, 28), (S * 3.0, 40), (S * 1.9, 60)):
            ld.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 205, 60, al))
        layer = layer.filter(ImageFilter.GaussianBlur(S * 0.8))
    img = Image.alpha_composite(img.convert("RGBA"), layer)
    d = ImageDraw.Draw(img)

    # ---------- پایتخت‌ها: قلعه‌ی همه، نشان شماره‌دار + نام برای برترین‌ها
    rank_of = {k: i + 1 for i, k in enumerate(lay["ranked"][:TOP_N])}
    f_num = _font(S * 0.82)
    f_name = _font(S * 0.78)
    f_small = _font(S * 0.62)
    named = set(lay["ranked"][:NAME_N])
    plates = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plates)
    for k, (x, y) in sorted(((k, pos[cs[k]["id"]]) for k in caps), key=lambda t: t[1][1]):
        col = color_of(entries[k][1], cs[k].get("npc"))
        if k in rank_of:
            r_ = S * 0.74
            d.ellipse([x - r_ - 2, y - r_ - 2, x + r_ + 2, y + r_ + 2], fill=(255, 255, 255))
            d.ellipse([x - r_, y - r_, x + r_, y + r_], fill=_shade(col, 0.62), outline=(12, 14, 26), width=max(2, int(S * 0.08)))
            d.text((x, y), str(rank_of[k]), font=f_num, fill=(255, 255, 255), anchor="mm")
            nm = fa(short(cs[k]["name"], 16))
            if nm.strip():
                tw = d.textlength(nm, font=f_name)
                px0, py0 = x - tw / 2 - S * 0.4, y + r_ + S * 0.15
                pd.rounded_rectangle([px0, py0, px0 + tw + S * 0.8, py0 + S * 1.15], radius=S * 0.3, fill=(8, 12, 26, 205))
                pd.rectangle([px0 + S * 0.12, py0 + S * 0.12, px0 + S * 0.3, py0 + S * 1.03], fill=col + (255,))
                pd.text((px0 + S * 0.4 + tw / 2, py0 + S * 0.6), nm, font=f_name, fill=(255, 255, 255, 255), anchor="mm")
        else:
            _castle(d, x, y + S * 0.3, S * 0.72, (250, 250, 245), (20, 22, 36))
            if k in named:                                              # کشورهای معمولی: اسم کوچیک زیر قلعه
                nm = fa(short(cs[k]["name"], 14))
                if nm.strip():
                    tw = d.textlength(nm, font=f_small)
                    px0, py0 = x - tw / 2 - S * 0.3, y + S * 0.42
                    pd.rounded_rectangle([px0, py0, px0 + tw + S * 0.6, py0 + S * 0.95], radius=S * 0.25, fill=(8, 12, 26, 175))
                    pd.text((x, py0 + S * 0.5), nm, font=f_small, fill=(235, 240, 250, 255), anchor="mm")
    img = Image.alpha_composite(img, plates)
    d = ImageDraw.Draw(img)
    if crown_id in pos:
        x, y = pos[crown_id]
        _crown(d, x, y - S * 1.55, S * 1.25)

    # ---------- قطب‌نما (پایین-چپ نقشه)
    cx, cy, rr = m + S * 2.4, top + maph - m - S * 1.2, S * 1.5
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(8, 16, 36, 190), outline=(255, 205, 60), width=max(2, int(S * 0.1)))
    d.polygon([(cx, cy - rr * 0.92), (cx - rr * 0.22, cy), (cx + rr * 0.22, cy)], fill=(255, 205, 60))
    d.polygon([(cx, cy + rr * 0.92), (cx - rr * 0.22, cy), (cx + rr * 0.22, cy)], fill=(180, 190, 210))
    d.text((cx, cy - rr - S * 0.55), "N", font=_font(S * 0.9), fill=(255, 205, 60), anchor="mm")

    # ---------- محو گوشه‌ها (وینیت)
    vig = Image.radial_gradient("L").resize((mapw, hpx)).point(lambda v: max(0, int((v - 150) * 1.1)))
    black = Image.new("RGBA", (mapw, hpx), (2, 6, 16, 255))
    mapimg = img.crop((0, 0, mapw, hpx))
    mapimg = Image.composite(black, mapimg, vig)
    img.paste(mapimg, (0, 0))
    d = ImageDraw.Draw(img)

    # ---------- پنل کناری: جدول کشورها
    px = mapw
    for y in range(hpx):
        t = y / hpx
        d.line([(px, y), (wpx, y)], fill=(int(10 + 8 * t), int(16 + 12 * t), int(34 + 20 * t)))
    d.line([(px, top), (px, hpx - foot)], fill=(255, 205, 60), width=max(2, int(S * 0.12)))
    f_h = _font(S * 1.0)
    f_r = _font(S * 0.86)
    f_s = _font(S * 0.7)
    d.text((px + S * 1.2, top + S * 1.3), "TOP EMPIRES", font=f_h, fill=(255, 205, 60), anchor="lm")
    y = top + S * 3.1
    mx = max([cs[k]["land"] for k in lay["ranked"][:TOP_N]] + [1])
    for num, k in enumerate(lay["ranked"][:TOP_N], 1):
        c = cs[k]
        col = color_of(entries[k][1], c.get("npc"))
        d.rounded_rectangle([px + S * 0.9, y, wpx - S * 0.9, y + S * 1.9], radius=S * 0.35, fill=(24, 36, 66), outline=(44, 62, 100))
        d.ellipse([px + S * 1.1, y + S * 0.3, px + S * 2.5, y + S * 1.7], fill=_shade(col, 0.62), outline=(255, 255, 255), width=2)
        d.text((px + S * 1.8, y + S * 1.0), str(num), font=f_s, fill=(255, 255, 255), anchor="mm")
        nm = fa(short(c["name"], 15))
        is_emp = crown_id is not None and c["id"] == crown_id
        d.text((wpx - S * 1.2 - (S * 1.7 if is_emp else 0), y + S * 0.62), nm, font=f_r, fill=(255, 255, 255), anchor="rm")
        bw = (panel - S * 5.2) * c["land"] / mx
        d.rectangle([px + S * 2.9, y + S * 1.2, px + S * 2.9 + panel - S * 5.2, y + S * 1.5], fill=(40, 56, 92))
        d.rectangle([px + S * 2.9, y + S * 1.2, px + S * 2.9 + bw, y + S * 1.5], fill=col)
        d.text((px + S * 2.9, y + S * 0.6), f"{c['land']}", font=f_s, fill=(190, 210, 235), anchor="lm")
        if crown_id is not None and c["id"] == crown_id:
            _crown(d, px + panel - S * 1.6, y + S * 1.15, S * 0.9)
        y += S * 2.15
    y += S * 0.5
    free = max(0, lay["land_cells"] - lay["claimed"])
    for label, val in (("PROVINCES CLAIMED", lay["claimed"]), ("FREE LAND", free), ("COUNTRIES", len(cs))):
        d.text((px + S * 1.2, y), label, font=f_s, fill=(150, 175, 210), anchor="lm")
        d.text((wpx - S * 1.2, y), str(val), font=f_r, fill=(255, 255, 255), anchor="rm")
        y += S * 1.35
    if crown_id is not None and crown_name:
        nm = fa(short(crown_name, 15))
        yb = hpx - foot - S * 3.4
        d.rounded_rectangle([px + S * 0.9, yb, wpx - S * 0.9, yb + S * 2.5], radius=S * 0.4, fill=(70, 50, 8, 255), outline=(255, 205, 60), width=2)
        _crown(d, px + S * 2.4, yb + S * 1.45, S * 1.05)
        d.text((px + S * 4.0, yb + S * 0.75), "EMPEROR", font=f_s, fill=(255, 215, 120), anchor="lm")
        d.text((px + S * 4.0, yb + S * 1.7), nm, font=f_r, fill=(255, 255, 255), anchor="lm")

    # ---------- نوار عنوان + فوتر
    for yy in range(top):
        t = yy / top
        d.line([(0, yy), (wpx, yy)], fill=(int(8 + 16 * t), int(14 + 24 * t), int(34 + 36 * t)))
    d.line([(0, top - 3), (wpx, top - 3)], fill=(255, 205, 60), width=max(3, int(S * 0.16)))
    d.text((m, top * 0.5), "EMPIRE ZERO", font=_font(top * 0.52), fill=(255, 255, 255), anchor="lm")
    d.text((m + d.textlength("EMPIRE ZERO", font=_font(top * 0.52)) + S * 1.2, top * 0.56), "WORLD MAP", font=_font(top * 0.3),
           fill=(255, 205, 60), anchor="lm")
    d.text((wpx - m, top * 0.5), f"{len(cs)} COUNTRIES  ·  {lay['claimed']} PROVINCES", font=_font(top * 0.3), fill=(180, 205, 235), anchor="rm")
    d.rectangle([0, hpx - foot, wpx, hpx], fill=(6, 10, 22))
    d.line([(0, hpx - foot), (wpx, hpx - foot)], fill=(255, 205, 60), width=max(2, int(S * 0.1)))
    d.text((m, hpx - foot / 2), "Conquer provinces to grow your empire  ·  Defeat the emperor to take the crown", font=_font(S * 0.8),
           fill=(150, 175, 210), anchor="lm")
    return img.convert("RGB"), pos, S


def mark(img, pos, S, me):
    """حلقه‌ی «تو» رو روی یه کپی از نقشه می‌ذاره (نقشه‌ی اصلی کش میشه و دست نمی‌خوره)."""
    if me not in pos:
        return img
    out = img.copy()
    d = ImageDraw.Draw(out)
    x, y = pos[me]
    for rr, col, w in ((S * 1.9, (255, 60, 60), 0.22), (S * 1.6, (255, 255, 255), 0.16), (S * 1.35, (255, 60, 60), 0.1)):
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=col, width=max(2, int(S * w)))
    f = _font(S * 0.95)
    tw = d.textlength("YOU", font=f)
    d.rounded_rectangle([x - tw / 2 - S * 0.5, y - S * 3.9, x + tw / 2 + S * 0.5, y - S * 2.55], radius=S * 0.3, fill=(220, 40, 50), outline=(255, 255, 255), width=2)
    d.text((x, y - S * 3.22), "YOU", font=f, fill=(255, 255, 255), anchor="mm")
    d.polygon([(x - S * 0.35, y - S * 2.55), (x + S * 0.35, y - S * 2.55), (x, y - S * 2.0)], fill=(220, 40, 50))
    return out


def to_png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=4)
    return buf.getvalue()


def to_preview(img, width=1800, quality=90):
    """نسخه‌ی سبک برای پیش‌نمایش داخل تلگرام (JPEG)."""
    w, h = img.size
    sm = img.resize((width, int(h * width / w)), Image.LANCZOS) if w > width else img
    buf = io.BytesIO()
    sm.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()
