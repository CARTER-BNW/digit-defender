"""Menu Settings (John, phone round 1): text size, button size, fullscreen,
info hints and the wave pause. Config round trip through ui.prefs, the HUD
scaling with the text size, the settings screen's keys and the frozen wave
countdown."""
import pygame
import pytest

from settings import WINDOW_W, WINDOW_H
from sim.factory import Factory
from sim.combat import Combat
from render import numbers
from ui import prefs
from ui.menu import Menu, BACK, QUIT
from world import persistence
from game import Game


@pytest.fixture
def screen():
    pygame.init()
    numbers.reset()                     # fonts cached by an earlier test's pygame session are dead
    scr = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    yield scr
    pygame.quit()


@pytest.fixture
def scales():
    yield
    prefs.text_scale = prefs.button_scale = 1.0


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "CONFIG_PATH", tmp_path / "config.json")
    return tmp_path / "config.json"


@pytest.fixture
def saves(tmp_path):
    persistence.set_saves_dir(tmp_path / "saves")
    yield tmp_path / "saves"
    persistence.set_saves_dir(persistence.ROOT / "saves")


def post(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def test_prefs_apply_step_and_clamp(scales):
    prefs.apply({"text_scale": 1.5, "button_scale": "bad"})
    assert prefs.text_scale == 1.5 and prefs.button_scale == 1.0
    prefs.apply({"text_scale": 9, "button_scale": 0.1})
    assert prefs.text_scale == prefs.TEXT_SCALES[-1] and prefs.button_scale == prefs.BUTTON_SCALES[0]
    prefs.apply({})
    assert prefs.text_scale == 1.0 and prefs.button_scale == 1.0
    assert prefs.step(1.0, prefs.TEXT_SCALES, 1) == 1.2
    assert prefs.step(0.8, prefs.TEXT_SCALES, -1) == prefs.TEXT_SCALES[-1]      # wraps
    assert prefs.percent(1.25) == "125%"
    prefs.text_scale = 1.8
    assert prefs.tsize(12) == 22 and prefs.tpx(100) == 180


def test_menu_settings_rows_adjust_and_save(screen, config_path, scales):
    cfg = {"last_world": None}
    menu = Menu(cfg)
    assert [k for _, k in menu.settings_rows()] == ["text", "button", "fullscreen", "hints", "waves", "back"]
    assert menu.adjust("text") is False and cfg["text_scale"] == 1.2 and prefs.text_scale == 1.2
    assert menu.adjust("button") is False and cfg["button_scale"] == 1.25 and prefs.button_scale == 1.25
    assert menu.adjust("text", -1) is False and cfg["text_scale"] == 1.0
    assert menu.adjust("hints") is False and cfg["hints"] is False
    assert menu.adjust("waves") is False and cfg["waves_paused"] is True
    assert menu.adjust("back") is True
    saved = persistence.load_config()
    assert saved["waves_paused"] is True and saved["hints"] is False and saved["button_scale"] == 1.25
    labels = [l for l, _ in menu.settings_rows()]
    assert "Enemy waves: Paused" in labels and "Info hints: Off" in labels
    assert "Button size: 125%" in labels and "Text size: 100%" in labels


def test_settings_screen_keys(screen, config_path, scales):
    """Right steps the highlighted value, Down moves on, Esc returns BACK."""
    cfg = {}
    menu = Menu(cfg, max_frames=30)
    pygame.event.clear()
    for key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_ESCAPE):
        post(key)
    assert menu._settings() == BACK
    assert cfg["text_scale"] == 1.2 and cfg["button_scale"] == 1.25
    pygame.event.clear()
    assert menu._settings() == QUIT                 # frame budget runs out: a scripted run ends


def test_main_menu_lists_settings_not_the_old_toggles(screen, config_path, saves, monkeypatch):
    seen = {}

    def fake_select(self, subtitle, options, footer):
        seen["labels"] = [label for label, _ in options]
        return QUIT

    monkeypatch.setattr(Menu, "_select", fake_select)
    assert Menu({}).run() == {"action": "quit"}
    labels = seen["labels"]
    assert any(label.startswith("Settings") for label in labels)
    assert not any(label.startswith(("Fullscreen", "Info hints")) for label in labels)


def test_phone_menu_has_no_fullscreen_row(screen, config_path):
    import sys
    sys.path.insert(0, str(persistence.ROOT / "android"))
    from mobile.entry import MobileMenu
    assert "fullscreen" not in [k for _, k in MobileMenu({}).settings_rows()]


def test_hud_scales_with_the_text_size(screen, scales):
    g = Game(screen, 1337)
    g.draw()
    hud = g.hud
    assert hud.hub_button.size == (120, 26) and hud.rects["balance"].size == (340, 58) and hud.btn == 54
    prefs.text_scale = 1.5
    g.draw()
    assert hud.hub_button.size == (180, 39) and hud.rects["balance"].size == (510, 87)
    assert hud.rects["targets"].height == 36 + 33 * len(g.factory.targets)
    assert hud.btn == 54                                # the toolbar follows the button size only
    prefs.button_scale = 0.8
    g.draw()
    assert hud.btn == 48
    # every panel draws at the biggest text size: hints, the structure panel, the group panel,
    # messages, help, the game-over screen
    prefs.text_scale = prefs.TEXT_SCALES[-1]
    g.show_hints = True
    g.selected = g.factory.hub
    hud.message("hello")
    g.show_help = True
    g.draw()
    assert hud.hints_rect.bottom <= hud.minimap_rect.top             # the hints stop short of the minimap
    g.selected = None
    g.factory.place("wall", 8, 0, 0)
    g.factory.place("wall", 9, 0, 0)
    g.selected_structures = [g.factory.structure_at(8, 0), g.factory.structure_at(9, 0)]
    g.game_over = True
    g.draw()


def test_apply_config_sets_hints_and_the_wave_pause(screen):
    g = Game(screen, 1)
    g.apply_config({"hints": False, "waves_paused": True})
    assert g.show_hints is False and g.combat.waves_paused is True
    g.draw()                                            # the wave line reads "(waves paused)"
    g.apply_config({})
    assert g.show_hints is True and g.combat.waves_paused is False


def test_waves_paused_holds_the_countdown():
    f = Factory(seed=7)
    f.create_hub(0, 0)
    c = Combat(f, 7)
    c.waves_paused = True
    before = c.seconds_to_wave()
    for _ in range(100):
        f.tick()
    assert c.seconds_to_wave() == before and c.wave.number == 0
    c.waves_paused = False
    for _ in range(100):
        f.tick()
    assert c.seconds_to_wave() == before - 5
    c.waves_paused = True                               # [F7] (next_at_tick <= now) still fires
    c.wave.next_at_tick = f.tick_count
    f.tick()
    assert c.wave.number == 1 and c.enemies
