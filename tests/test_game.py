"""Headless Game smoke: pan, zoom, drag, F3, streaming bounds."""
import pygame
import pytest

from settings import WINDOW_W, WINDOW_H, ZOOM_LEVELS, UNLOAD_MARGIN, CHUNK_PX
from game import Game


@pytest.fixture
def game():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    g = Game(screen, 1337)
    yield g
    pygame.quit()


def frames(g, n, dt=1 / 60):
    for _ in range(n):
        g.handle_events()
        g.update(dt)
        g.draw()
        g.frame += 1


def test_chunks_appear_only_when_seen_and_unload_far_away(game):
    frames(game, 2)
    loaded_at_start = set(game.terrain.chunks)
    keep, unload = game.camera.keep_unload_rects()
    assert loaded_at_start == {(x, y) for x in range(keep[0], keep[2] + 1)
                               for y in range(keep[1], keep[3] + 1)}
    game.camera.move(200 * CHUNK_PX, 0)   # far to the east
    frames(game, 2)
    assert not (loaded_at_start & set(game.terrain.chunks))
    ux0, uy0, ux1, uy1 = game.camera.visible_chunk_range(UNLOAD_MARGIN)
    for cx, cy in game.terrain.chunks:
        assert ux0 <= cx <= ux1 and uy0 <= cy <= uy1


def test_return_trip_regenerates_identical_terrain(game):
    frames(game, 1)
    before = {k: list(c.tiles) for k, c in game.terrain.chunks.items()}
    game.camera.move(0, 500 * CHUNK_PX)
    frames(game, 1)
    game.camera.move(0, -500 * CHUNK_PX)
    frames(game, 1)
    for k, tiles in before.items():
        assert game.terrain.chunks[k].tiles == tiles


def test_zoom_events_and_f3(game):
    frames(game, 1)
    for _ in range(10):
        game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert game.camera.zoom == ZOOM_LEVELS[0]
    frames(game, 2)
    for _ in range(10):
        game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    assert game.camera.zoom == ZOOM_LEVELS[-1]
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3, mod=0, unicode=""))
    assert game.renderer.debug
    frames(game, 2)


def test_middle_drag_pans(game):
    x0 = game.camera.x
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2, pos=(100, 100)))
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(60, 100), rel=(-40, 0), buttons=(0, 1, 0)))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=2, pos=(60, 100)))
    assert game.camera.x == x0 + 40 / game.camera.zoom
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(0, 0), rel=(-40, 0), buttons=(0, 0, 0)))
    assert game.camera.x == x0 + 40 / game.camera.zoom


def test_fixed_timestep_caps_ticks(game):
    game.update(10.0)                    # a huge stall
    assert game.tick_count == 4          # MAX_TICKS_PER_FRAME
    assert game.acc == 0.0               # leftover dropped
    game.update(0.05)
    assert game.tick_count == 5


def test_surface_cache_is_evicted_offscreen(game):
    frames(game, 2)
    cached = sum(1 for c in game.terrain.chunks.values() if c.surface is not None)
    x0, y0, x1, y1 = game.camera.visible_chunk_range()
    assert cached <= (x1 - x0 + 3) * (y1 - y0 + 3)
    assert game.renderer.surfaces_built == cached   # nothing rendered twice
