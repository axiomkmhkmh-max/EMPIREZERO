"""🛒 منطق فروشگاه مینی‌اپ (بدون تلگرام و بدون وب‌سرور؛ فقط روی دیکشنری کشور کار می‌کنه).

هر خرید همون توابع اقتصاد بازی رو صدا می‌زنه (eco.fx_buy / eco.global_buy)، پس قیمت‌ها زنده‌ان و بازار تکون می‌خوره.
آفرهای روزانه هر روز (به وقت تهران) عوض میشن و سرور خودش اعتبارشون رو چک می‌کنه؛ کلاینت نمی‌تونه قیمت بفرسته.
"""
import math
import time
from datetime import datetime, timedelta

import config
import eco
import engine as E
import prog
from config import ITEMS

CATS = (("shield", "سپر"), ("zero", "زیرو"), ("food", "غذا"), ("steel", "فولاد"))
HIST_MAX = 12


def now():
    return time.time()


def _day_end(t=None):
    d = datetime.fromtimestamp(t or now(), prog.TEHRAN)
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def _seed():
    return sum(ord(ch) for ch in prog.day_id())


# ------------------------------------------------------------------ قیمت‌ها
def _price_zero(qty):
    return math.ceil(qty * eco.fx_price("PHX") * (1 + config.FX_FEE))


def _price_item(item, qty):
    return math.ceil(eco.prices(item)[0] * qty)


def _shield_item(h, z, off=None):
    cost = z if not off else max(1, math.ceil(z * (100 - off["pct"]) / 100))
    return dict(id=f"shield:{h}" + (":o" if off else ""), cat="shield", qty=h,
                title=f"سپر {h} ساعته", sub="تا وقتی سپر داری کسی بهت حمله نمی‌کنه",
                cur="zero", cost=cost, was=z if off else None, offer=off)


def _zero_item(q):
    return dict(id=f"zero:{q}", cat="zero", qty=q, title=f"{q} زیرو", sub="ارز جنگ؛ برای سپر و تسریع ساخت",
                cur="coin", cost=_price_zero(q), was=None, offer=None)


def _res_item(kind, q, off=None):
    price = _price_item(kind, q)
    emoji, name = ITEMS[kind]
    bonus = int(q * off["pct"] / 100) if off else 0
    title = f"{q:,} {name}" if not bonus else f"{q + bonus:,} {name}"
    return dict(id=f"{kind}:{q}" + (":o" if off else ""), cat=kind, qty=q, bonus=bonus, title=title,
                sub="خرید از بازار جهانی با قیمت لحظه‌ای" if not off else f"{q:,} خرید + {bonus:,} هدیه",
                cur="coin", cost=price, was=None, offer=off)


def offers(t=None):
    """دو آفر روزانه: یه سپر تخفیف‌دار و یه بسته‌ی منابع با بونوس."""
    s, end = _seed(), _day_end(t)
    h, z = config.SHOP_SHIELDS[s % len(config.SHOP_SHIELDS)]
    sh_off = dict(kind="discount", pct=config.SHOP_OFFER_SHIELD[s % len(config.SHOP_OFFER_SHIELD)], ends=end)
    kind = ("steel", "food")[s % 2]
    packs = config.SHOP_STEEL if kind == "steel" else config.SHOP_FOOD
    res_off = dict(kind="bonus", pct=config.SHOP_OFFER_BONUS[(s // 2) % len(config.SHOP_OFFER_BONUS)], ends=end)
    return [_shield_item(h, z, sh_off), _res_item(kind, packs[-1], res_off)]


def catalog():
    items = [_shield_item(h, z) for h, z in config.SHOP_SHIELDS]
    items += [_zero_item(q) for q in config.SHOP_ZERO]
    items += [_res_item("food", q) for q in config.SHOP_FOOD]
    items += [_res_item("steel", q) for q in config.SHOP_STEEL]
    return items


def find(item_id):
    for it in catalog() + offers():
        if it["id"] == item_id:
            return it
    return None


def view(c):
    """همه‌چیزی که صفحه‌ی فروشگاه لازم داره."""
    fx = eco.fx_price("PHX")
    return dict(
        items=catalog(), offers=offers(), cats=[dict(id=k, n=v) for k, v in CATS],
        zero_price=round(fx, 2), zero_change=round(eco.fx_change("PHX"), 2),
        hist=list(reversed(c.get("shop_hist", [])))[:6], now=now(),
    )


# ------------------------------------------------------------------ خرید
def buy(c, item_id):
    """(موفق؟، پیام، آیا قیمت‌های بازار عوض شد؟) — ذخیره‌ی کشور و بازار با صدا زننده‌ست."""
    it = find(item_id)
    if not it:
        return False, "این آیتم دیگه توی فروشگاه نیست (آفر عوض شده)", False
    world = False
    if it["cat"] == "shield":
        cost = it["cost"]
        if c["fx"].get("PHX", 0) < cost:
            return False, f"⚡ {cost} زیرو لازمه", False
        c["fx"]["PHX"] -= cost
        c["shield_until"] = max(c["shield_until"], E.now()) + it["qty"] * 3600
        msg = f"🛡 {it['qty']} ساعت سپر فعال شد (−{cost} زیرو)"
    elif it["cat"] == "zero":
        ok, msg = eco.fx_buy(c, "PHX", it["qty"])
        if not ok:
            return False, msg, False
        world = True
    else:
        ok, msg = eco.global_buy(c, it["cat"], it["qty"])
        if not ok:
            return False, msg, False
        world = True
        if it.get("bonus"):
            c[it["cat"]] += it["bonus"]
            msg += f" + {it['bonus']:,} هدیه 🎁"
    h = c.setdefault("shop_hist", [])
    h.append(dict(id=item_id[:-2] if item_id.endswith(":o") else item_id, t=now(), title=it["title"], cur=it["cur"], cost=it["cost"]))
    del h[:-HIST_MAX]
    return True, msg, world
