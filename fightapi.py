"""⚔️ API سیستم فایت مینی‌اپ.

هیچ منطق جنگ تازه‌ای این‌جا نیست: حمله/کمپین/جنگ بزرگ همون war.do_attack / do_camp / boss_hit هستن
(همون فرمان، هزینه‌ی بسیج، سپر، کولداون، مه جنگ و تعادل). این فایل فقط
  • فهرست هدف‌ها و پیش‌نمایش (شانس، جبهه‌ها، هزینه) می‌ده،
  • حمله رو زیر db.LOCK اجرا می‌کنه و نتیجه‌ی ساخت‌یافته‌ی نبرد (cine.record) رو برای صحنه‌ی زنده‌ی مینی‌اپ برمی‌گردونه.
"""
import html
import math
import re
import time

import config
import cine
import crown
import db
import engine as E
import prog
import war
import webapp as W
from config import U

_TAG = re.compile(r"<[^>]+>")
_LAST = {}
PCTS = (30, 60, 100)


def plain(t):
    return html.unescape(_TAG.sub("", t or "")).strip()


def _ready(c):
    """دلیل اینکه همین الان نمیشه حمله کرد (بدون ارتش، فرمان یا سکه‌ی بسیج)؛ خالی = آماده."""
    e = war.check_ready(c, 30)
    return plain(e) if e else ""


def _unit_meta():
    return {k: dict(n=v["n"], e=v["e"], atk=v["atk"], dfn=v["dfn"], br=v["br"]) for k, v in U.items()}


def my_state(c):
    return dict(units={k: int(c["units"].get(k, 0)) for k in U}, atk=int(E.attack_power(c)), dfn=int(E.defense_power(c)),
                orders=round(E.orders(c), 1), orders_max=E.orders_max(c), wait=int(E.order_wait(c)),
                coins=int(c["treasury"]), land=c.get("land", config.LAND_START), wins=c.get("wins", 0), losses=c.get("losses", 0),
                logi={p: war.logi_cost(c, p) for p in PCTS}, sent={p: war.sent_size(c, p) for p in PCTS},
                camp=c["camp"]["stage"], weary=round(c.get("weariness", 0), 1), morale=round(E.morale(c), 2))


def _row(c, d, npc):
    exact = True
    view = int(E.defense_power(d))
    if not npc:
        i = war.intel_of(c, d["_id"])
        exact = bool(i)
        view = int(i["dfn"]) if i else int(war.fog(c, d["_id"], view))
    t = time.time()
    return dict(id=d["_id"], name=d["name"], e=d.get("emblem", "🏛"), npc=npc, tier=d.get("tier", 0), land=d.get("land", 5),
                score=int(E.score(d)), dfn=view, exact=exact, shield=max(0, int(d.get("shield_until", 0) - t)),
                rev=(not npc) and c["revenge"].get(str(d["_id"]), 0) > t, bounty=int(d.get("bounty", 0)) if npc else 0,
                emp=crown.is_holder(d["_id"]))


async def _block(c, t):
    """دلیل ممنوع بودن حمله (یا None) — همون شرط‌های war.do_attack."""
    t0, npc = time.time(), bool(t.get("npc"))
    if npc:
        left = config.NPC_CD - (t0 - c["npc_cd"].get(str(t["_id"]), 0))
        return f"⏳ ارتش این کشور {int(left // 60) + 1} دقیقه‌ی دیگه بازسازی میشه" if left > 0 else None
    rev = c["revenge"].get(str(t["_id"]), 0) > t0
    if t["shield_until"] > t0:
        return "🛡 این کشور سپر داره"
    if c.get("alliance") and t.get("alliance") == c["alliance"]:
        return "🤝 هم‌پیمانته"
    if await W.world.has_pact(c["_id"], t["_id"]):
        return "🕊 پیمان عدم‌تجاوز داری"
    left = config.PVP_CD - (t0 - c["pvp_cd"].get(str(t["_id"]), 0))
    if left > 0 and not rev:
        return f"⏳ {prog.dur(left)} دیگه می‌تونی دوباره بزنی"
    if E.score(t) < config.BULLY_RATIO * E.score(c) and not rev:
        return "🙅 خیلی ضعیف‌تر از توئه"
    return None


async def h_hub(request):
    u = W._user(request)
    if not u:
        return W._json(dict(error="auth"), 401)
    async with db.LOCK:
        if await db.is_banned(u["id"]):
            return W._json(dict(error="ban"), 403)
        c = await db.load(u["id"])
        if not c:
            return W._json(dict(error="reg"), 403)
        banned = {d["_id"] async for d in db.BANS.find({}, {"_id": 1})}
        docs = await db.C.find({"npc": {"$ne": True}, "_id": {"$ne": c["_id"]}}).to_list(600)
        mine, rows = max(1, E.score(c)), []
        for d in docs:
            if d["_id"] in banned:
                continue
            E.defaults(d)
            rows.append((0 if c["revenge"].get(str(d["_id"]), 0) > time.time() else 1, abs(math.log(max(E.score(d), 1) / mine)), d))
        rows.sort(key=lambda x: (x[0], x[1]))
        players = []
        for _, _, d in rows[:14]:
            r = _row(c, d, False)
            r["block"] = await _block(c, d)
            players.append(r)
        npcs = []
        for d in await db.C.find({"npc": True, "_id": {"$gt": -100}}).sort("_id", -1).to_list(20):
            E.defaults(d)
            r = _row(c, d, True)
            r["block"] = await _block(c, d)
            npcs.append(r)
        e = war.camp_enemy(c["camp"]["stage"])
        rw = war.camp_reward(c["camp"]["stage"])
        camp = dict(stage=c["camp"]["stage"], name=e["name"], tag=e["tag"], dfn=int(E.defense_power(e)), boss=rw["boss"],
                    reward=prog.rew_text(rw), pts=rw["pts"], best=c["camp"].get("best", 0), chance=round(E.estimate(c, e, 1.0, "bal")[2], 2))
        boss = None
        if war.boss_active():
            B = war.BOSS
            mine_d = {int(k): v for k, v in B.get("dmg", {}).items()}.get(c["_id"], 0.0)
            boss = dict(name=B["name"], hp=int(max(0, B["hp"])), hp_max=int(B["hp_max"]), left=int(B["end"] - time.time()), mine=int(mine_d),
                        hit=int(E.attack_power(c, {k: int(c["units"].get(k, 0)) for k in war.ATK})))
    return W._json(dict(me=my_state(c), units=_unit_meta(), players=players, npcs=npcs, camp=camp, boss=boss))


async def h_prep(request):
    u = W._user(request)
    if not u:
        return W._json(dict(error="auth"), 401)
    q = request.query
    async with db.LOCK:
        c = await db.load(u["id"])
        if not c:
            return W._json(dict(error="reg"), 403)
        kind, t = q.get("kind", "pvp"), None
        if kind == "camp":
            t = war.camp_enemy(c["camp"]["stage"])
        elif kind == "boss":
            return W._json(dict(me=my_state(c), units=_unit_meta(), kind="boss", ready=_ready(c)))
        elif q.get("tid", "").lstrip("-").isdigit():
            t = await db.load(int(q["tid"]))
        elif q.get("name"):
            t = await db.C.find_one({"name": q["name"][:40]})
            if t:
                E.defaults(t)
        if not t or t["_id"] == c["_id"]:
            return W._json(dict(error="none"), 404)
        npc = bool(t.get("npc"))
        row = _row(c, t, npc)
        row["block"] = None if kind == "camp" else await _block(c, t)
        out = dict(ready=_ready(c), me=my_state(c), units=_unit_meta(), t=row, kind="camp" if kind == "camp" else "npc" if npc else "pvp",
                   stance={k: dict(n=v["n"], e=v["e"], d=v["d"], atk=v["atk"], loss=v["loss"], loot=v["loot"]) for k, v in E.STANCES.items()},
                   crown=config.CROWN_BOUNTY if crown.is_holder(t["_id"]) else 0, cq=config.CONQUEST_RATIO)
        i = None if npc else war.intel_of(c, t["_id"])
        if row["exact"]:
            sup = 0.0 if npc else await war.ally_support(t)
            out["chance"] = {s: {p: round(E.estimate(c, t, p / 100, s, sup)[2], 2) for p in PCTS} for s in E.STANCES}
            bp, bpr, _ = war.best_pct(c, t, sup)
            out["best"] = dict(pct=bp, chance=round(bpr, 2))
            cl = E.calc(c, t, 1.0, "bal", sup)
            out["fronts"] = [[e, nm, int(cl["fronts"][f][0]), int(cl["fronts"][f][1])] for f, e, nm in E.FRONTS]
            out["eunits"] = (t["units"] if npc else i["units"])
    return W._json(out)


async def h_attack(request):
    import admin
    u = W._user(request)
    if not u:
        return W._json(dict(ok=False, msg="نشست منقضی شده؛ مینی‌اپ رو ببند و دوباره باز کن"), 401)
    uid = u["id"]
    if admin.blocked(uid):
        return W._json(dict(ok=False, msg=admin.SET["maint_msg"]))
    t0 = time.time()
    if t0 - _LAST.get(uid, 0) < 2.5:
        return W._json(dict(ok=False, msg="یه لحظه صبر کن"))
    _LAST[uid] = t0
    try:
        b = await request.json()
        kind = b.get("kind") if b.get("kind") in ("pvp", "npc", "camp", "boss") else "pvp"
        pct = max(10, min(100, int(b.get("pct", 60))))
        stance = b.get("stance") if b.get("stance") in E.STANCES else "bal"
        tid, cq = int(b.get("tid", 0) or 0), bool(b.get("conquest"))
    except Exception:
        return W._json(dict(ok=False, msg="درخواست نامعتبر"), 400)
    async with db.LOCK:
        if await db.is_banned(uid):
            return W._json(dict(ok=False, msg="🚫"))
        c = await db.load(uid)
        if not c:
            return W._json(dict(ok=False, msg="اول توی ربات بنویس «ثبت نام»"))
        cine.take_raw(uid)
        if kind == "camp":
            txt = war.do_camp(c, pct, stance)
        elif kind == "boss":
            txt = await war.boss_hit(c, pct)
        else:
            txt = await war.do_attack(c, tid, pct, stance, cq)
        raw = cine.take_raw(uid)
        cine.take(uid)                                  # فریم‌های متنی ربات اینجا لازم نیستن
        if raw or kind not in ("camp", "boss"):          # حمله حالا لشکرکشیه: بدون raw هم وضعیت (لشکر در راه) باید ذخیره بشه
            await db.save(c)
    me = await W.load_me(uid, fresh=True)
    if not raw:
        return W._json(dict(ok=False, msg=plain(txt), me=me))
    return W._json(dict(ok=True, raw=raw, msg=plain(txt), me=me, st=my_state(c)))


async def h_spy(request):
    import admin
    u = W._user(request)
    if not u:
        return W._json(dict(ok=False, msg="auth"), 401)
    if admin.blocked(u["id"]):
        return W._json(dict(ok=False, msg=admin.SET["maint_msg"]))
    try:
        tid = int((await request.json()).get("tid"))
    except Exception:
        return W._json(dict(ok=False, msg="درخواست نامعتبر"), 400)
    async with db.LOCK:
        c = await db.load(u["id"])
        if not c:
            return W._json(dict(ok=False, msg="اول توی ربات بنویس «ثبت نام»"))
        txt = await war.do_spy(c, tid, "scout")
        await db.save(c)
    return W._json(dict(ok=True, msg=plain(txt), me=await W.load_me(u["id"], fresh=True)))


def add_routes(app):
    app.router.add_get("/api/war/hub", h_hub)
    app.router.add_get("/api/war/prep", h_prep)
    app.router.add_post("/api/war/attack", h_attack)
    app.router.add_post("/api/war/spy", h_spy)
