"""Portrait (a rotated phone) and the fold-away minimap (John, phone round 3):
the toolbar wraps to two rows, the panels stack under the right column, the
minimap sits above the toolbar and the Android button rows, a click folds it
into a Map button, and the Android entry re-creates the logical canvas when
the window's aspect flips."""
import sys
from pathlib import Path

import pygame
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android"))

from mobile import entry                       # noqa: E402
from mobile.entry import MobileGame            # noqa: E402
from mobile.touch import STATE                 # noqa: E402
from render import numbers                     # noqa: E402
from game import Game                          # noqa: E402
from ui.hud import TOOLS                       # noqa: E402

PORTRAIT = (720, 1616)
LANDSCAPE = (1616, 720)


@pytest.fixture
def screen_factory():
    pygame.init()
    numbers.reset()

    def make(size):
        return pygame.display.set_mode(size)

    yield make
    pygame.quit()


@pytest.fixture
def phone(screen_factory):
    """A MobileGame with the touch layer, in the size the test asks for."""
    MobileGame.touch_only = True
    entry.install_patches(True)
    MobileGame.fit_flags = 0                   # the dummy driver has no SCALED fullscreen

    def make(size):
        g = MobileGame(screen_factory(size), 1337)
        g.draw()
        return g

    yield make
    entry.uninstall_patches()
    MobileGame.fit_flags = pygame.SCALED | pygame.FULLSCREEN
    STATE["mods"] = 0


def finger(g, etype, fid, pos):
    w, h = g.screen.get_size()
    g.handle_event(pygame.event.Event(etype, touch_id=1, finger_id=fid, x=pos[0] / w, y=pos[1] / h,
                                      dx=0.0, dy=0.0, pressure=1.0))


def tap(g, pos):
    finger(g, pygame.FINGERDOWN, 0, pos)
    finger(g, pygame.FINGERUP, 0, pos)


def test_toolbar_wraps_to_two_rows_in_portrait(screen_factory):
    g = Game(screen_factory(PORTRAIT), 1)
    rects = [r for r, _, _ in g.hud.buttons()]
    assert len(rects) == len(TOOLS) == 14
    assert len({r.top for r in rects}) == 2 and sum(r.top == rects[0].top for r in rects) == 7
    assert all(8 <= r.left and r.right <= PORTRAIT[0] - 8 for r in rects)
    assert g.hud.btn == 60                     # room for full-size buttons across 720 px
    assert g.hud.toolbar_rect.bottom <= PORTRAIT[1] and g.hud.toolbar_rect.height > 100
    g.draw()                                   # the hotkeys still map to the same kinds
    assert [k for _, k, _ in g.hud.buttons()] == [k for k, _ in TOOLS]


def test_portrait_hud_stacks_the_panels(screen_factory):
    g = Game(screen_factory(PORTRAIT), 1)
    g.show_hints = True
    g.selected = g.factory.hub
    g.hud.message("hello")
    g.draw()
    hud = g.hud
    w, h = PORTRAIT
    assert hud.portrait
    assert hud.rects["balance"].right == w - 8 and hud.rects["balance"].width == 340
    assert hud.panel_rect.top >= hud.column_bottom + 6 and hud.panel_rect.left == 8    # under the column
    assert hud.panel_rect.right <= w - 8
    assert hud.minimap_rect.bottom <= hud.toolbar_rect.top and hud.minimap_rect.right == w - 8
    assert hud.wave_rect.left == 8 or hud.wave_rect.top > hud.content_bottom   # top left, or under everything
    assert not hud.hints_rect.colliderect(hud.panel_rect)
    g.selected = None
    g.factory.place("wall", 8, 0, 0)
    g.factory.place("wall", 9, 0, 0)
    g.selected_structures = [g.factory.structure_at(8, 0), g.factory.structure_at(9, 0)]
    g.show_help = True
    g.game_over = True
    g.draw()                                   # group panel, help and game over fit a narrow screen
    assert hud.panel_rect.right <= w - 8


def test_long_panel_lines_wrap_to_the_room(screen_factory):
    from ui import prefs
    g = Game(screen_factory(PORTRAIT), 1)
    sp = g.factory.place("spawner_ranged", 6, 4, 1)
    g.selected = sp
    g.draw()
    small = g.hud.panel_rect.copy()
    assert small.width <= PORTRAIT[0] - 16
    try:
        prefs.text_scale = 1.5                 # now its lines are wider than the screen: they wrap
        g.draw()
        big = g.hud.panel_rect
        assert big.width <= PORTRAIT[0] - 16 and big.height > small.height * 1.5
    finally:
        prefs.text_scale = 1.0


def test_minimap_folds_into_a_button_and_back(screen_factory):
    g = Game(screen_factory(LANDSCAPE), 1)
    g.draw()
    hud = g.hud
    full = hud.minimap_rect.copy()
    assert full.size == (440, 300)
    assert hud.click(full.center, g)           # a click folds it
    assert hud.minimap_hidden
    g.draw()
    button = hud.minimap_rect
    assert button.size == (120, 26) and button.bottomright == full.bottomright
    assert hud.over_ui(button.center) and not hud.over_ui(full.center)
    x0 = g.camera.x
    assert hud.click(button.center, g)         # a click on the button unfolds it
    assert not hud.minimap_hidden and g.camera.x == x0
    g.draw()
    assert hud.minimap_rect == full
    # a right click on the map looks there
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(full.left + 20, full.top + 20), button=3, touch=False))
    assert g.camera.x != x0


def test_minimap_state_comes_from_the_config(screen_factory):
    g = Game(screen_factory(LANDSCAPE), 1)
    g.apply_config({"minimap": False})
    assert g.hud.minimap_hidden
    g.apply_config({})
    assert not g.hud.minimap_hidden


def test_logical_size_keeps_720_on_the_short_side():
    assert entry.logical_size(2424, 1080) == (1616, 720)
    assert entry.logical_size(1080, 2424) == (720, 1616)
    assert entry.logical_size(1000, 720) == (1180, 720)     # a squarer landscape screen: minimum width


def test_refit_follows_a_rotation(phone, monkeypatch):
    g = phone(LANDSCAPE)
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1080, 2424))
    g.refit()
    assert g.screen.get_size() == PORTRAIT
    assert g.hud.screen is g.screen and g.renderer.screen is g.screen
    assert (g.camera.w, g.camera.h) == PORTRAIT
    g.draw()                                   # the touch rows and the minimap lay out in portrait
    rows = g.touch.layout()
    assert rows and all(r.bottom <= g.hud.toolbar_rect.top for r, _, _ in rows)
    assert g.hud.minimap_rect.bottom <= min(r.top for r, _, _ in rows)     # the minimap sits above the rows
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (2424, 1080))
    g.refit()
    assert g.screen.get_size() == LANDSCAPE
    same = g.screen
    g.refit()                                  # the same aspect: nothing happens
    assert g.screen is same


def test_phone_tap_folds_the_minimap_in_portrait(phone):
    g = phone(PORTRAIT)
    hud = g.hud
    full = hud.minimap_rect.copy()
    tap(g, full.center)
    g.draw()
    assert hud.minimap_hidden and hud.minimap_rect.size == (120, 26)
    rows = g.touch.layout()
    assert hud.minimap_rect.bottom <= min(r.top for r, _, _ in rows)     # the Map button above the rows too
    tap(g, hud.minimap_rect.center)
    g.draw()
    assert not hud.minimap_hidden and hud.minimap_rect == full
