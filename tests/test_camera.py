from settings import ZOOM_LEVELS, TILE_SIZE, CHUNK_PX, PRELOAD_CHUNKS, UNLOAD_MARGIN
from render.camera import Camera


def test_zoom_levels_give_integer_tile_sizes():
    for z in ZOOM_LEVELS:
        assert float(TILE_SIZE * z).is_integer(), z


def test_round_trip_transforms():
    cam = Camera(1280, 720, x=123.0, y=-456.0, zoom_index=1)
    for sx, sy in ((0, 0), (640, 360), (1279, 719), (17, 900)):
        wx, wy = cam.screen_to_world(sx, sy)
        assert cam.world_to_screen(wx, wy) == (sx, sy)
    assert cam.screen_to_tile(640, 360) == (int(123 // TILE_SIZE), int(-456 // TILE_SIZE))


def test_zoom_keeps_anchor_fixed():
    cam = Camera(1280, 720, x=1000.0, y=2000.0)
    anchor = (200, 650)
    wx, wy = cam.screen_to_world(*anchor)
    for idx in (0, 5, 2, 4, 1, 3):
        cam.set_zoom_index(idx, anchor)
        assert cam.zoom == ZOOM_LEVELS[idx]
        ax, ay = cam.screen_to_world(*anchor)
        assert abs(ax - wx) < 1e-6 and abs(ay - wy) < 1e-6
    cam.zoom_by(+10)
    assert cam.zoom_index == len(ZOOM_LEVELS) - 1
    cam.zoom_by(-10)
    assert cam.zoom_index == 0


def test_visible_range_grows_when_zoomed_out():
    cam = Camera(1280, 720)
    cam.set_zoom_index(3)
    x0, y0, x1, y1 = cam.visible_chunk_range()
    n1 = (x1 - x0 + 1) * (y1 - y0 + 1)
    cam.set_zoom_index(0)
    x0, y0, x1, y1 = cam.visible_chunk_range()
    n0 = (x1 - x0 + 1) * (y1 - y0 + 1)
    assert n0 > n1 * 8
    # at zoom 0.25 a 1280px screen spans 5120 world px = 10 chunks
    assert x1 - x0 + 1 in (10, 11)


def test_keep_inside_unload():
    cam = Camera(1280, 720, x=-3000.0, y=777.0)
    keep, unload = cam.keep_unload_rects()
    assert unload[0] <= keep[0] and unload[1] <= keep[1]
    assert unload[2] >= keep[2] and unload[3] >= keep[3]
    assert keep[0] - unload[0] == UNLOAD_MARGIN - PRELOAD_CHUNKS


def test_chunk_origins_land_on_whole_pixels():
    """Consecutive chunks must tile exactly (no seams) at every zoom."""
    cam = Camera(1280, 720, x=333.7, y=-91.2)
    for idx in range(len(ZOOM_LEVELS)):
        cam.set_zoom_index(idx)
        step = int(CHUNK_PX * cam.zoom)
        ax, ay = cam.world_to_screen(0, 0)
        bx, by = cam.world_to_screen(CHUNK_PX, CHUNK_PX)
        assert (bx - ax, by - ay) == (step, step)
