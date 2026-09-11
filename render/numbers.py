"""Cached number/text rendering. Every piece of text on screen goes through
text() so nothing calls font.render per frame (docs/PLAN.md section 3.4).
"""
from functools import lru_cache

import pygame

from settings import COLORS

_SUFFIXES = ("", "K", "M", "B", "T", "Q")


def abbrev(n):
    """7 -> '7', 1234 -> '1.2K', 3_400_000 -> '3.4M', 5.1e9 -> '5.1B'.
    Beyond the suffix table falls back to scientific notation."""
    n = int(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n < 1000:
        return f"{sign}{n}"
    for i, suf in enumerate(_SUFFIXES[1:], start=1):
        unit = 1000 ** i
        if n < unit * 1000:
            v = n / unit
            s = f"{v:.1f}" if v < 100 else f"{v:.0f}"
            if s.endswith(".0"):
                s = s[:-2]
            return f"{sign}{s}{suf}"
    return f"{sign}{n:.1e}"


def fmt(n):
    """Thousands separators up to a million, abbreviated beyond."""
    n = int(n)
    return f"{n:,}" if abs(n) < 1_000_000 else abbrev(n)


@lru_cache(maxsize=64)
def font(px, bold=True):
    """A font whose digits are about px pixels tall. SysFont lookup happens
    once per size (it is slow); default font is the fallback."""
    try:
        f = pygame.font.SysFont("consolas", px, bold=bold)
    except Exception:  # pragma: no cover - font machinery varies by machine
        f = None
    return f or pygame.font.Font(None, int(px * 1.3))


@lru_cache(maxsize=4096)
def text(s, px, color=COLORS["text"], outline=True):
    """Rendered text Surface with a 1px dark outline (4 offset blits)."""
    f = font(px)
    if not outline:
        return f.render(s, True, color)
    fg = f.render(s, True, color)
    bg = f.render(s, True, COLORS["text_shadow"])
    w, h = fg.get_size()
    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(bg, (dx, dy))
    out.blit(fg, (1, 1))
    return out


@lru_cache(maxsize=4096)
def glyph(s, px, color=COLORS["text"]):
    """Outlined text cropped to its ink bounds, so blit_centered puts the
    visual centre of a digit exactly on the target (font boxes are taller
    than digits and sit them high)."""
    surf = text(s, px, color)
    r = surf.get_bounding_rect()
    if r.width == 0 or r.height == 0:
        return surf
    return surf.subsurface(r).copy()


def reset():
    """Drop cached Font/Surface objects. Call after pygame.init(): fonts made
    before a pygame.quit() are invalid afterwards (tests re-init a lot)."""
    font.cache_clear()
    text.cache_clear()
    glyph.cache_clear()


def blit_centered(surface, surf, cx, cy):
    surface.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))
