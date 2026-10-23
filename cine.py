"""🎬 نبرد زنده.

به‌جای یه گزارش یهویی، همون پیام مرحله‌به‌مرحله ادیت میشه:
  «ارتش‌ها به مرز رسیدن» ← «✈️ نبرد آسمان…» ← «🚢 نبرد دریا…» ← «🪖 نبرد زمین…» ← 🚀 موشک‌ها ← گزارش نهایی.

نتیجه‌ی جنگ از قبل (توی engine.battle) محاسبه شده؛ این‌جا فقط «نمایش»ـشه، پس هیچ ریسکی برای تعادل بازی نداره.
خود انیمیشن بعد از آزاد شدن قفل دیتابیس اجرا میشه (تا بقیه‌ی بازیکن‌ها منتظر نمونن).
"""
import asyncio
import time

import config
from util import esc, n

_STASH = {}          # uid → (زمان، فریم‌ها)
_TTL = 20            # فریم‌های کهنه (مثلاً بعد از خطا) دور ریخته میشن


def stash(uid, frames):
    """do_attack / do_camp / boss_hit فریم‌ها رو این‌جا می‌ذارن؛ هندلر دکمه/دستور بعد از آزاد شدن قفل برمی‌داره."""
    if config.CINE_ON and frames and len(frames) > 1:
        _STASH[uid] = (time.time(), frames)


def take(uid):
    t = _STASH.pop(uid, None)
    if not t or time.time() - t[0] > _TTL:
        return None
    return t[1]


def _bar(i, total):
    k = max(0, min(10, round(10 * i / max(1, total))))
    return "▰" * k + "▱" * (10 - k)


def _fr(head, lines, bar_txt):
    return head + "\n\n" + "\n".join(lines) + f"\n\n{bar_txt}"


def battle_frames(r, an, dn):
    """r = خروجی engine.battle · an/dn = اسم مهاجم/مدافع (خام؛ این‌جا escape میشه). از دید مهاجم."""
    head = f"⚔️ <b>{esc(an)}</b>  ⚔️  <b>{esc(dn)}</b>"
    fronts = r.get("fronts", [])
    steps = len(fronts) + (1 if r.get("mis") else 0) + 2          # مرز + جبهه‌ها + موشک + شمارش
    frames = [_fr(head, ["🚩 ارتش‌ها به مرز رسیدن…"], _bar(0, steps))]
    done, i = [], 1
    for e, nm, a, d, w in fronts:
        frames.append(_fr(head, done + [f"{e} <b>نبرد {nm}</b> شروع شد… 💥"], _bar(i, steps)))
        i += 1
        verdict = "✅ بردی" if w else "❌ باختی" if w is False else "➖ مساوی"
        done.append(f"{e} {nm}: 🗡{n(a)} ⚔️ 🛡{n(d)} → {verdict}")
        if e == "✈️" and r.get("air") == "att":
            done.append("   ↳ آسمون مال توئه! به دریا و زمین بونوس میده")
        elif e == "✈️" and r.get("air") == "def":
            done.append("   ↳ مدافع آسمون رو گرفت؛ ارتشت ضعیف‌تر وارد می‌شه")
    if r.get("mis"):
        frames.append(_fr(head, done + [f"🚀 {r['mis']} موشک شلیک شد…"], _bar(i, steps)))
        i += 1
        done.append(f"🚀 رهگیری {int(r.get('icpt', 0) * 100)}٪ · اصابت {r.get('hits', 0)}")
        if r.get("destroyed"):
            done.append("💥 تخریب: " + "، ".join(r["destroyed"]))
    frames.append(_fr(head, done + ["🧮 داره تلفات و غنیمت شمرده میشه…"], _bar(steps - 1, steps)))
    return frames


def boss_frames(boss_name, dmg, pct_of_hp):
    head = f"🌑 <b>نبرد با {esc(boss_name)}</b>"
    return [_fr(head, ["🚩 ارتشت بسیج شد و به سمت دشمن می‌ره…"], _bar(1, 4)),
            _fr(head, ["💥 ضربه‌ی سنگین فرود اومد…"], _bar(2, 4)),
            _fr(head, [f"🔥 {n(dmg)} آسیب! ({pct_of_hp:.1f}٪ HP)", "🧮 داره تلافی دشمن شمرده میشه…"], _bar(3, 4))]


async def play(msg, frames, final, markup=None, delay=None):
    """فریم‌ها رو یکی‌یکی روی msg ادیت می‌کنه و آخرش متن نهایی (با دکمه‌ها) رو می‌ذاره.
    اگه تلگرام محدودیت ادیت داد، بی‌سروصدا می‌پره به نتیجه‌ی نهایی."""
    from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
    delay = delay or config.CINE_DELAY
    for f in frames:
        try:
            await msg.edit_text(f)
        except TelegramRetryAfter:
            break
        except TelegramBadRequest:
            pass
        except Exception:
            break
        await asyncio.sleep(delay)
    for _ in range(2):
        try:
            await msg.edit_text(final, reply_markup=markup)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after + 1, 8))
        except TelegramBadRequest:
            return
        except Exception:
            return
