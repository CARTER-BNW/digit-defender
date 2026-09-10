"""Phase 0 placeholder: settings import cleanly and the window opens headless."""
import settings
from world import tiles


def test_settings_sane():
    assert settings.CHUNK_PX == settings.CHUNK_SIZE * settings.TILE_SIZE
    assert abs(settings.TICK_DT * settings.TICK_RATE - 1.0) < 1e-9
    assert list(settings.ZOOM_LEVELS) == sorted(settings.ZOOM_LEVELS)
    assert settings.ZOOM_LEVELS[settings.DEFAULT_ZOOM_INDEX] == 1.0
    assert set(settings.COSTS) == set(settings.BASE_HP) - {"hub"}


def test_tile_ids():
    assert tiles.deposit_value(tiles.DEPOSIT_BASE + 7) == 7
    assert tiles.deposit_value(0) == 0
    assert tiles.is_ground(tiles.GROUND_MAX) and not tiles.is_ground(tiles.DEPOSIT_1)
    assert tiles.is_nest(tiles.NEST_CORE) and not tiles.is_buildable(tiles.NEST_GROUND)


def test_main_opens_and_quits_headless():
    import main  # conftest forces the SDL dummy driver
    assert main.main(["--frames", "3"]) == 0
