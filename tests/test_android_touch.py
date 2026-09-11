"""The Android touch layer (android/mobile) driven headlessly with finger
events: taps, long press, drags, pinch, overlay buttons, the back key and the
desktop mouse emulation. Runs with the desktop game code untouched."""
import sys
from pathlib import Path

import pygame
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android"))

from mobile import entry                       # noqa: E402
from mobile.entry import MobileGame            # noqa: E402
from mobile.touch import LONG_PRESS_S, STATE   # noqa: E402
from sim.structures import Belt                # noqa: E402
from world import persistence                  # noqa: E402

W, H = 1616, 720


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def game():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    MobileGame.touch_only = True
    entry.install_patches(True)
    g = MobileGame(screen, 1337)
    g.touch.clock = FakeClock()
    g.draw()
    yield g
    entry.uninstall_patches()
    STATE["mods"] = 0
    pygame.quit()


def finger(g, etype, fid, pos):
    x, y = pos
    g.handle_event(pygame.event.Event(etype, touch_id=1, finger_id=fid, x=x / W, y=y / H,
                                      dx=0.0, dy=0.0, pressure=1.0))


def tap(g, pos, fid=0):
    finger(g, pygame.FINGERDOWN, fid, pos)
    finger(g, pygame.FINGERUP, fid, pos)


def tile_centre(g, tx, ty):
    sx, sy = g.camera.tile_to_screen(tx, ty)
    tp = g.camera.tile_px
    return (sx + tp // 2, sy + tp // 2)


def button(g, label):
    return next(r for r, l, _ in g.touch.layout() if l == label).center


def test_tap_places_one_belt(game):
    game.set_tool("belt")
    tap(game, tile_centre(game, 6, 0))
    assert isinstance(game.factory.structure_at(6, 0), Belt)
    assert game.touch.mode is None and not game.belt_path


def test_long_press_is_a_right_click(game):
    game.set_tool("wall")
    finger(game, pygame.FINGERDOWN, 0, tile_centre(game, 6, 1))
    game.touch.clock.t += LONG_PRESS_S + 0.05
    game.update(1 / 60)                          # the timer fires here
    assert game.tool is None                     # RMB with a tool = cancel it
    assert game.factory.structure_at(6, 1) is None
    finger(game, pygame.FINGERUP, 0, tile_centre(game, 6, 1))
    assert game.touch.mode is None


def test_one_finger_drag_pans_without_a_tool(game):
    x0 = game.camera.x
    z = game.camera.zoom
    finger(game, pygame.FINGERDOWN, 0, (700, 300))
    finger(game, pygame.FINGERMOTION, 0, (600, 300))
    assert game.camera.x == pytest.approx(x0 + 100 / z)
    finger(game, pygame.FINGERMOTION, 0, (550, 300))
    assert game.camera.x == pytest.approx(x0 + 150 / z)
    finger(game, pygame.FINGERUP, 0, (550, 300))
    assert game.factory.count() == 1             # the HQ only: no click happened


def test_belt_drag_builds_a_line(game):
    game.set_tool("belt")
    finger(game, pygame.FINGERDOWN, 0, tile_centre(game, 5, 2))
    finger(game, pygame.FINGERMOTION, 0, tile_centre(game, 8, 2))
    assert len(game.belt_path) == 4              # preview grows with the finger
    finger(game, pygame.FINGERUP, 0, tile_centre(game, 8, 2))
    belts = [game.factory.structure_at(x, 2) for x in range(5, 9)]
    assert all(isinstance(b, Belt) for b in belts)
    assert {b.direction for b in belts} == {1}   # all east


def test_pinch_zooms_in_and_out(game):
    zi = game.camera.zoom_index
    finger(game, pygame.FINGERDOWN, 0, (700, 360))
    finger(game, pygame.FINGERDOWN, 1, (760, 360))
    finger(game, pygame.FINGERMOTION, 1, (790, 360))     # 60 -> 90 px apart
    assert game.camera.zoom_index == zi + 1
    finger(game, pygame.FINGERMOTION, 1, (715, 360))     # 90 -> 15 px
    assert game.camera.zoom_index == zi
    finger(game, pygame.FINGERUP, 1, (715, 360))
    finger(game, pygame.FINGERUP, 0, (700, 360))
    assert game.touch.mode is None


def test_second_finger_cancels_a_belt_drag_and_pans(game):
    game.set_tool("belt")
    x0 = game.camera.x
    finger(game, pygame.FINGERDOWN, 0, tile_centre(game, 5, 3))
    finger(game, pygame.FINGERMOTION, 0, tile_centre(game, 7, 3))
    assert game.belt_path
    finger(game, pygame.FINGERDOWN, 1, (900, 500))
    assert not game.belt_path and game.tool == "belt"
    zi = game.camera.zoom_index
    fx, fy = tile_centre(game, 7, 3)
    finger(game, pygame.FINGERMOTION, 0, (fx - 40, fy))          # both fingers 40 px left: a pure pan
    finger(game, pygame.FINGERMOTION, 1, (860, 500))
    assert game.camera.zoom_index == zi
    assert game.camera.x == pytest.approx(x0 + 40 / game.camera.zoom)
    finger(game, pygame.FINGERUP, 0, (fx - 40, fy))
    finger(game, pygame.FINGERUP, 1, (860, 500))
    assert game.factory.count() == 1


def test_two_finger_tap_is_a_middle_click(game):
    finger(game, pygame.FINGERDOWN, 0, (700, 360))
    finger(game, pygame.FINGERDOWN, 1, (740, 360))
    finger(game, pygame.FINGERUP, 0, (700, 360))
    finger(game, pygame.FINGERUP, 1, (740, 360))
    assert game.touch.mode is None and not game.dragging   # no units: nothing to patrol, no crash


def test_overlay_buttons(game):
    game.set_tool("adder")
    d = game.build_dir
    tap(game, button(game, "Rot"))
    assert game.build_dir == (d + 1) % 4
    tap(game, button(game, "Esc"))
    assert game.tool is None
    tap(game, button(game, "Shift"))
    assert pygame.key.get_mods() & pygame.KMOD_SHIFT
    tap(game, button(game, "Shift"))
    assert not (pygame.key.get_mods() & pygame.KMOD_SHIFT)
    tap(game, button(game, "Zoom +"))
    assert game.camera.zoom > 1.0
    tap(game, button(game, "Pause"))
    assert game.paused
    tap(game, button(game, "Speed"))
    assert game.speed == 2
    assert not any(l == "Load" for _, l, _ in game.touch.layout())
    game.game_over = True
    assert any(l == "Load" for _, l, _ in game.touch.layout())


def test_box_button_arms_a_selection_drag(game):
    game.factory.place("wall", 6, 4, 0)
    game.factory.place("wall", 7, 4, 0)
    tap(game, button(game, "Box"))
    assert game.touch.box_armed
    a = tile_centre(game, 5, 3)
    b = tile_centre(game, 8, 5)
    finger(game, pygame.FINGERDOWN, 0, a)
    finger(game, pygame.FINGERMOTION, 0, b)
    finger(game, pygame.FINGERUP, 0, b)
    assert len(game.selected_structures) == 2
    assert not game.touch.box_armed              # one-shot


def test_back_key_becomes_escape_in_the_event_queue(game):
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_AC_BACK, mod=0, unicode="", scancode=0))
    keys = [e.key for e in pygame.event.get() if e.type == pygame.KEYDOWN]
    assert pygame.K_ESCAPE in keys and pygame.K_AC_BACK not in keys


def test_mouse_emulates_a_finger_on_desktop():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    MobileGame.touch_only = False
    entry.install_patches(False)
    try:
        g = MobileGame(screen, 1337)
        g.touch.clock = FakeClock()
        g.set_tool("belt")
        pos = tile_centre(g, 6, 0)
        g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1, touch=False))
        g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1, touch=False))
        assert isinstance(g.factory.structure_at(6, 0), Belt)
    finally:
        entry.uninstall_patches()
        MobileGame.touch_only = True
        pygame.quit()


def test_entry_runs_headless_in_desktop_mode(tmp_path):
    persistence.set_saves_dir(tmp_path / "saves")
    try:
        assert entry.main(["--desktop", "--world", "android_smoke", "--seed", "7", "--frames", "3"]) == 0
        assert (tmp_path / "saves" / "android_smoke" / "structures.json").exists()
    finally:
        entry.uninstall_patches()
        persistence.set_saves_dir(persistence.ROOT / "saves")
