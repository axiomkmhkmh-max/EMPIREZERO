"""🌐 مینی‌اپ تلگرام: نقشه‌ی زنده‌ی جهان + فروشگاه + رتبه‌ها.

داخل همون پروسه‌ی ربات اجرا میشه (aiohttp همراه aiogram نصبه؛ وابستگی تازه‌ای لازم نیست).
  • احراز هویت: initData تلگرام با امضای HMAC چک میشه؛ کلاینت نمی‌تونه هویت یا قیمت جعل کنه
  • /api/live (SSE): هاب زنده؛ هر ۴ ثانیه نقشه رو چک می‌کنه و تغییرها (تسخیر، تاج، اخبار، آنلاین‌ها) رو به همه می‌فرسته
  • خریدها همون توابع اقتصاد بازی رو صدا می‌زنن و زیر db.LOCK اجرا میشن (مثل دکمه‌های ربات)
"""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl

import config
import crown
import db
import eco
import engine as E
import shop
import world
import worldmap
from core import log_exc, tlog

try:
    from aiohttp import web
except ImportError:          # برای تست‌هایی که فقط توابع داده رو می‌خوان
    web = None

INDEX = Path(__file__).with_name("webapp") / "index.html"
TICK = 4                     # هر چند ثانیه نقشه چک بشه
STATS_EVERY = 20             # هر چند ثانیه امتیازها/سپرها تازه بشن
NEWS_KEEP = 30

HUB = dict(ver="0", lay=None, map=None, geo={}, scores={}, shields={}, scores_ts=0.0,
           crown_key=None, news=[], clients={}, online=0, capov={})
CAP_GAP = 24 * 3600          # هر بازیکن روزی یک‌بار می‌تونه پایتختش رو جابه‌جا کنه
_ME = {}                     # uid → (ts, payload)؛ کش کوتاه برای سبک‌ماندن قفل دیتابیس
_LAST_BUY = {}
_TAG = re.compile(r"<[^>]+>")


# ------------------------------------------------------------------ احراز هویت
def verify(init_data):
    """initData تلگرام رو اعتبارسنجی می‌کنه؛ دیکشنری کاربر یا None."""
    if not init_data:
        return None
    if config.WEBAPP_DEV and init_data.startswith("dev:") and init_data[4:].lstrip("-").isdigit():
        return {"id": int(init_data[4:]), "first_name": "Dev"}
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        got = pairs.pop("hash", None)
        if not got:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(pairs.get("auth_date", "0")) > 86400:
            return None
        return json.loads(pairs["user"])
    except Exception:
        return None


def _user(request):
    return verify(request.headers.get("X-Init") or request.query.get("a") or "")


# ------------------------------------------------------------------ ساخت داده‌ی نقشه
def build_geo(tier):
    W, H, _nb, cells, _pts, elev = worldmap.make_world(tier)
    bands = "".join("0" if elev[c] < 0.22 else "1" if elev[c] < 0.45 else "2" if elev[c] < 0.70 else "3" for c in cells)
    ev = "".join(str(min(9, int(elev[c] * 10))) for c in cells)          # ارتفاع ۱۰ سطحی (۰..۹)؛ برای کوه و دشتِ نرم روی کره
    return dict(tier=tier, W=W, H=H, cells=list(cells), elev=bands, ev=ev)


def _cap_of(lay, k, cid):
    """پایتخت پیش‌فرض، مگه اینکه بازیکن یه استان خودش رو پایتخت کرده باشه."""
    ov = HUB["capov"].get(cid)
    own = lay["own"]
    if ov is not None and 0 <= ov < len(own) and own[ov] == k:
        return ov
    return lay["caps"].get(k, -1)


def build_map(lay, scores, shields):
    """وضعیت مالکیت + فهرست کشورها. هیچ آیدی تلگرامی توش نیست (فقط اندیس)."""
    cells = worldmap.make_world(lay["tier"])[3]
    own = [lay["own"][c] for c in cells]
    cs = []
    for k, c in enumerate(lay["cs"]):
        npc = bool(c.get("npc"))
        cs.append(dict(n=c["name"], e=c.get("emblem", "🏛"), l=c["land"], npc=npc,
                       c=list(worldmap.color_of(lay["entries"][k][1], npc)),
                       cap=_cap_of(lay, k, c["id"]), s=int(scores.get(c["id"], 0)), sh=bool(shields.get(c["id"]))))
    holder = crown.CROWN["holder"]
    ci = next((k for k, c in enumerate(lay["cs"]) if c["id"] == holder), -1) if holder is not None else -1
    cr = dict(i=ci, name=crown.CROWN["name"], since=crown.CROWN["since"], guard=crown.CROWN["guard"])
    return dict(tier=lay["tier"], own=own, cs=cs, crown=cr, claimed=lay["claimed"])


def _ver(own, cr):
    h = hashlib.md5(bytes((o + 1) & 255 for o in own) + repr((len(own), cr["i"], cr["name"], sorted(HUB["capov"].items()))).encode()).hexdigest()
    return h[:10]


async def _scores():
    banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
    sc, sh, ov, t = {}, {}, {}, time.time()
    async for d in db.C.find({}):
        if d["_id"] in banned:
            continue
        try:
            E.defaults(d)
            sc[d["_id"]] = E.score(d)
            sh[d["_id"]] = d.get("shield_until", 0) > t
            if d.get("cap_cell") is not None:
                ov[d["_id"]] = int(d["cap_cell"])
        except Exception:
            continue
    HUB["capov"] = ov
    return sc, sh


def _strip(text):
    return _TAG.sub("", text or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")[:240]


# ------------------------------------------------------------------ هاب زنده
def broadcast(event, data):
    for q in list(HUB["clients"]):
        try:
            q.put_nowait((event, data))
        except asyncio.QueueFull:
            pass


def push_news(text):
    item = dict(t=time.time(), x=_strip(text))
    HUB["news"].append(item)
    del HUB["news"][:-NEWS_KEEP]
    broadcast("news", item)


def _online():
    return len({u for u in HUB["clients"].values() if u is not None})


async def refresh(force=False):
    """نقشه رو دوباره می‌سازه اگه مالکیت/تاج/امتیازها عوض شده باشه؛ نسخه‌ی تازه رو برمی‌گردونه."""
    from wow import _layout
    t = time.time()
    if force or t - HUB["scores_ts"] > STATS_EVERY or not HUB["scores"]:
        HUB["scores"], HUB["shields"] = await _scores()
        HUB["scores_ts"] = t
        stats_dirty = True
    else:
        stats_dirty = False
    lay = await _layout()
    ck = (crown.CROWN["holder"], crown.CROWN["name"])
    if lay is HUB["lay"] and ck == HUB["crown_key"] and not stats_dirty:
        return False
    if lay is not HUB["lay"] or not HUB["geo"]:
        HUB["geo"] = build_geo(lay["tier"])
    HUB["lay"], HUB["crown_key"] = lay, ck
    old = HUB["ver"]
    HUB["map"] = build_map(lay, HUB["scores"], HUB["shields"])
    HUB["ver"] = _ver(HUB["map"]["own"], HUB["map"]["crown"])
    HUB["map"]["ver"] = HUB["ver"]
    if HUB["ver"] != old:
        broadcast("map", dict(ver=HUB["ver"]))
    elif stats_dirty:
        broadcast("stats", dict(ver=HUB["ver"]))
    return True


async def hub_loop():
    await asyncio.sleep(1)
    while True:
        try:
            await refresh()
        except Exception:
            logging.exception("webapp hub")
            log_exc("هاب زنده‌ی مینی‌اپ")
        await asyncio.sleep(TICK)


def hook_news():
    """هر خبر جهان (تسخیر، تاج، جنگ بزرگ ...) همون لحظه به مینی‌اپ‌ها هم می‌رسه."""
    if getattr(world.news, "_hooked", False):
        return
    orig = world.news

    def news(text, important=False):
        orig(text, important)
        try:
            push_news(text)
        except Exception:
            pass
    news._hooked = True
    world.news = news


# ------------------------------------------------------------------ اطلاعات کاربر
def me_payload(c):
    sc = int(E.score(c))
    mine = HUB["scores"].get(c["_id"])
    rank = (1 + sum(1 for v in HUB["scores"].values() if v > mine)) if mine is not None else None
    lay = HUB["lay"]
    idx = next((k for k, x in enumerate(lay["cs"]) if x["id"] == c["_id"]), -1) if lay else -1
    return dict(reg=True, name=c["name"], emblem=c.get("emblem", "🏛"), idx=idx, land=c.get("land", config.LAND_START),
                score=sc, rank=rank, coins=int(c["treasury"]), zero=round(c["fx"].get("PHX", 0.0), 2),
                food=int(c["food"]), steel=int(c["steel"]), orders=round(E.orders(c), 1), orders_max=E.orders_max(c),
                shield=max(0, int(c["shield_until"] - E.now())), emperor=crown.is_holder(c["_id"]),
                pop=int(c["pop"]), sat=int(c["sat"]), now=time.time())


async def load_me(uid, fresh=False):
    hit = _ME.get(uid)
    if hit and not fresh and time.time() - hit[0] < 6:
        return hit[1]
    async with db.LOCK:
        if await db.is_banned(uid):
            return dict(reg=False, banned=True)
        c = await db.load(uid)
    p = me_payload(c) if c else dict(reg=False)
    _ME[uid] = (time.time(), p)
    return p


# ------------------------------------------------------------------ هندلرها
def _json(data, status=200):
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


async def h_index(request):
    resp = web.Response(body=INDEX.read_bytes(), content_type="text/html", charset="utf-8",
                        headers={"Cache-Control": "no-cache"})
    resp.enable_compression()                      # صفحه ~۱۰۰ کیلوبایته؛ فشرده شه سریع‌تر بالا میاد
    return resp


async def h_geo(request):
    if not HUB["geo"]:
        await refresh(force=True)
    tag = f"geo{HUB['geo']['tier']}v3"            # v3: دنیای تازه (قاره‌های جدید)؛ کش قدیمی باطل میشه
    if request.headers.get("If-None-Match") == tag:
        return web.Response(status=304)
    return web.json_response(HUB["geo"], headers={"ETag": tag, "Cache-Control": "no-cache"})


async def h_map(request):
    u = _user(request)
    if not u:
        return _json(dict(error="auth"), 401)
    if not HUB["map"]:
        await refresh(force=True)
    m = HUB["map"]
    me = await load_me(u["id"])
    if request.query.get("since") == HUB["ver"]:         # مالکیت عوض نشده؛ فقط آمار کشورها
        return _json(dict(ver=HUB["ver"], same=True, cs=m["cs"], crown=m["crown"], claimed=m["claimed"], me=me,
                          online=_online()))
    return _json(dict(m, me=me, online=_online()))


async def h_me(request):
    u = _user(request)
    if not u:
        return _json(dict(error="auth"), 401)
    return _json(await load_me(u["id"], fresh=True))


async def h_shop(request):
    u = _user(request)
    if not u:
        return _json(dict(error="auth"), 401)
    async with db.LOCK:
        c = await db.load(u["id"])
        view = shop.view(c) if c else None
    if not c:
        return _json(dict(error="reg"), 403)
    return _json(dict(view, me=await load_me(u["id"], fresh=True)))


async def h_buy(request):
    import admin
    u = _user(request)
    if not u:
        return _json(dict(ok=False, msg="نشست منقضی شده؛ مینی‌اپ رو ببند و دوباره باز کن"), 401)
    uid = u["id"]
    if admin.blocked(uid):
        return _json(dict(ok=False, msg=admin.SET["maint_msg"]))
    t = time.time()
    if t - _LAST_BUY.get(uid, 0) < config.SHOP_BUY_GAP:
        return _json(dict(ok=False, msg="یه لحظه صبر کن و دوباره بزن"))
    _LAST_BUY[uid] = t
    try:
        body = await request.json()
        item = str(body.get("item", ""))[:40]
    except Exception:
        return _json(dict(ok=False, msg="درخواست نامعتبر"), 400)
    async with db.LOCK:
        if await db.is_banned(uid):
            return _json(dict(ok=False, msg="🚫"))
        c = await db.load(uid)
        if not c:
            return _json(dict(ok=False, msg="اول توی ربات بنویس «ثبت نام»"))
        ok, msg, wd = shop.buy(c, item)
        view = None
        if ok:
            view = shop.view(c)
            await db.save(c)
            if wd:
                await eco.save_world()
            tlog("🛒", "خرید از فروشگاه مینی‌اپ", f"{c['name']} · {item}")
    me = await load_me(uid, fresh=True)
    return _json(dict(ok=ok, msg=msg, me=me, shop=view))


async def h_setcap(request):
    import admin
    u = _user(request)
    if not u:
        return _json(dict(ok=False, msg="نشست منقضی شده؛ مینی‌اپ رو ببند و دوباره باز کن"), 401)
    uid = u["id"]
    if admin.blocked(uid):
        return _json(dict(ok=False, msg=admin.SET["maint_msg"]))
    try:
        cell = int((await request.json()).get("cell"))
    except Exception:
        return _json(dict(ok=False, msg="درخواست نامعتبر"), 400)
    if not HUB["lay"]:
        await refresh(force=True)
    lay = HUB["lay"]
    k = next((i for i, c in enumerate(lay["cs"]) if c["id"] == uid), -1)
    if k < 0 or not (0 <= cell < len(lay["own"])) or lay["own"][cell] != k:
        return _json(dict(ok=False, msg="این استان مال کشور تو نیست"))
    t = time.time()
    async with db.LOCK:
        if await db.is_banned(uid):
            return _json(dict(ok=False, msg="🚫"))
        c = await db.load(uid)
        if not c:
            return _json(dict(ok=False, msg="اول توی ربات بنویس «ثبت نام»"))
        wait = CAP_GAP - (t - c.get("cap_ts", 0))
        if wait > 0:
            return _json(dict(ok=False, msg=f"پایتخت رو تازه جابه‌جا کردی؛ {int(wait // 3600) + 1} ساعت دیگه می‌تونی دوباره", wait=int(wait)))
        c["cap_cell"], c["cap_ts"] = cell, t
        await db.save(c)
        name = c["name"]
    HUB["capov"][uid] = cell
    await refresh(force=True)
    push_news(f"🏛 {name} پایتختش رو به استان تازه‌ای منتقل کرد")
    return _json(dict(ok=True, msg="🏛 پایتخت جابه‌جا شد", next=t + CAP_GAP))


async def h_live(request):
    u = _user(request)
    if not u:
        return web.Response(status=401, text="auth")
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                                       "Connection": "keep-alive", "X-Accel-Buffering": "no"})
    await resp.prepare(request)
    q = asyncio.Queue(maxsize=64)
    HUB["clients"][q] = u["id"]
    broadcast("online", dict(n=_online()))

    async def send(ev, data):
        await resp.write(f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())

    try:
        await send("hello", dict(ver=HUB["ver"], online=_online(), news=HUB["news"][-12:]))
        while True:
            try:
                ev, data = await asyncio.wait_for(q.get(), 15)
            except asyncio.TimeoutError:
                await resp.write(b": ping\n\n")
                continue
            await send(ev, data)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    except Exception:
        logging.exception("sse")
    finally:
        HUB["clients"].pop(q, None)
        broadcast("online", dict(n=_online()))
    return resp


def make_app():
    @web.middleware
    async def gzip_mw(request, handler):
        resp = await handler(request)
        if request.path.startswith("/api/") and type(resp) is web.Response:
            resp.enable_compression()
        return resp

    app = web.Application(middlewares=[gzip_mw])
    app.router.add_get("/", h_index)
    app.router.add_get("/app", h_index)
    app.router.add_get("/api/geo", h_geo)
    app.router.add_get("/api/map", h_map)
    app.router.add_get("/api/me", h_me)
    app.router.add_get("/api/shop", h_shop)
    app.router.add_post("/api/buy", h_buy)
    app.router.add_post("/api/setcap", h_setcap)
    app.router.add_get("/api/live", h_live)
    import fightapi
    fightapi.add_routes(app)                      # ⚔️ سیستم فایت روی نقشه
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    return app


async def start(bot=None):
    """سرور وب رو بالا میاره و (اگه WEBAPP_URL ست باشه) دکمه‌ی منوی ربات رو روی مینی‌اپ می‌ذاره."""
    if web is None:
        logging.warning("aiohttp نصب نیست؛ مینی‌اپ خاموش موند")
        return None
    hook_news()
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT).start()
    logging.info("mini app on %s:%s (url=%s)", config.WEBAPP_HOST, config.WEBAPP_PORT, config.WEBAPP_URL or "-")
    asyncio.create_task(hub_loop())
    if bot is not None and config.WEBAPP_URL:
        try:
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🗺 نقشه و فروشگاه",
                                                                      web_app=WebAppInfo(url=config.WEBAPP_URL)))
        except Exception:
            logging.exception("menu button")
    return runner
