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
    frames(game, 5)
    loaded_at_start = set(game.terrain.chunks)
    keep, unload = game.camera.keep_unload_rects()
    assert loaded_at_start == {(x, y) for x in range(keep[0], keep[2] + 1)
                               for y in range(keep[1], keep[3] + 1)}
    game.camera.move(200 * CHUNK_PX, 0)   # far to the east
    frames(game, 5)
    assert not (loaded_at_start & set(game.terrain.chunks))
    ux0, uy0, ux1, uy1 = game.camera.visible_chunk_range(UNLOAD_MARGIN)
    for cx, cy in game.terrain.chunks:
        assert ux0 <= cx <= ux1 and uy0 <= cy <= uy1


def test_return_trip_regenerates_identical_terrain(game):
    frames(game, 5)
    before = {k: list(c.tiles) for k, c in game.terrain.chunks.items()}
    game.camera.move(0, 500 * CHUNK_PX)
    frames(game, 5)
    game.camera.move(0, -500 * CHUNK_PX)
    frames(game, 5)
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
    frames(game, 5)
    cached = sum(1 for c in game.terrain.chunks.values() if c.surface is not None)
    x0, y0, x1, y1 = game.camera.visible_chunk_range()
    assert cached <= (x1 - x0 + 3) * (y1 - y0 + 3)
    assert game.renderer.surfaces_built == cached   # nothing rendered twice


def test_game_over_overlay_and_reload_result(game):
    frames(game, 2)
    game.factory.hub.hp = 1
    game.combat.spawn_enemy("brute", 2.5, 0.5)
    for _ in range(400):
        game.update(1 / 60)
    assert game.game_over and game.factory.hub_destroyed
    frames(game, 2)                                   # overlay draws without error
    tc = game.tick_count
    game.update(1 / 60)
    assert game.tick_count == tc                      # sim frozen
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l, mod=0, unicode="l"))
    assert not game.running and game.result == "reload"


def test_rally_right_click_on_selected_spawner(game):
    frames(game, 1)
    sp = game.factory.place("spawner_melee", 4, 4, 2, free=True)
    game.selected = sp
    pos = game.camera.tile_to_screen(-9, -9)              # clear of the minimap (a right click there looks around)
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(pos[0] + 16, pos[1] + 16)))
    assert sp.rally is not None and abs(sp.rally[0] + 8.5) < 0.01 and abs(sp.rally[1] + 8.5) < 0.01
    game.selected = None
    game.set_tool("belt")
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(10, 10)))
    assert game.tool is None                          # plain right-click still cancels


def test_building_while_paused_links_immediately(game):
    from sim.structures import E, W
    frames(game, 1)
    game.paused = True
    game.factory.balance = 10 ** 6
    m = game.factory.place("miner", 6, 6, E, free=True, value=4)
    a = game.factory.place("belt", 7, 6, E, free=True)
    b = game.factory.place("belt", 8, 6, E, free=True)
    game.update(1 / 60)                               # paused: no tick, but links rebuilt
    assert game.tick_count == 0
    assert [nb for nb, _ in m.outputs] == [a] and a.next is b
    assert a.in_sides == 1 << W and b.in_sides == 1 << W
    game.paused = False
    for _ in range(60 * 3):
        game.update(1 / 60)
    assert game.factory.stats["mined"] >= 1


def _mouse(game, kind, button, tile, dx=16, dy=16, rel=(0, 0)):
    pos = game.camera.tile_to_screen(*tile)
    pos = (pos[0] + dx, pos[1] + dy)
    if kind == pygame.MOUSEMOTION:
        game.handle_event(pygame.event.Event(kind, pos=pos, rel=rel, buttons=(1, 0, 0)))
    else:
        game.handle_event(pygame.event.Event(kind, button=button, pos=pos))
    return pos


def test_click_spawner_trains_and_units_are_commanded(game):
    from settings import UNIT_COSTS
    frames(game, 1)
    sp = game.factory.place("spawner_melee", 4, 4, 2, free=True)
    bal = game.factory.balance
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, 4))          # click = select + queue one
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (4, 4))
    assert game.selected is sp and sp.queue == 1
    assert game.factory.balance == bal - UNIT_COSTS["melee"]
    game.update(0.05)                                          # one tick: the unit walks out
    assert len(game.combat.units) == 1 and sp.queue == 0
    u = game.combat.units[0]
    u.x, u.y = 3.5, 6.5                                        # clear of the minimap corner
    # click the unit: selected; RMB somewhere: it gathers on that tile centre
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (3, 6))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (3, 6))
    assert game.selected_units == [u] and game.selected is None
    _mouse(game, pygame.MOUSEBUTTONDOWN, 3, (-9, 2))       # clear of the minimap (a right click there looks around)
    assert u.rally == (-8.5, 2.5)
    # drag a box on empty ground around two units
    v = game.combat.spawn_unit("melee", 8.5, 8.5)
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (2, 5), dx=2, dy=2)
    assert game.box_start is not None                          # selection is decided on release
    end = _mouse(game, pygame.MOUSEMOTION, 1, (9, 9), dx=30, dy=30)
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (9, 9), dx=30, dy=30)
    assert game.box_start is None and set(game.selected_units) == {u, v}
    frames(game, 2)                                            # draws rings/box without error
    # RMB on a selected spawner sets its gather point (tile centre)
    game.selected_units = []
    game.selected = sp
    _mouse(game, pygame.MOUSEBUTTONDOWN, 3, (-9, 9))
    assert sp.rally == (-8.5, 9.5)
    # Esc clears a unit selection before it leaves to the menu
    game.selected_units = [u]
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert game.selected_units == [] and game.running


def test_u_key_upgrades_hovered_structure(game):
    frames(game, 1)
    game.factory.balance = 150
    w = game.factory.place("wall", 3, 3, 0, free=True)
    game.hover_tile = (3, 3)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0, unicode="u"))
    assert w.level == 2 and game.factory.balance == 50
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0, unicode="u"))
    assert w.level == 2 and game.factory.balance == 50      # cannot afford the next 100
    game.factory.rebuild_links()
    game.selected = w
    frames(game, 2)                                          # panel shows the upgrade line


def test_x_is_a_demolish_tool_click_or_box(game):
    from settings import COSTS
    frames(game, 1)
    f = game.factory
    f.terrain = None                                           # any tile is buildable
    belts = [f.place("belt", x, -4, 1, free=True) for x in range(3, 9)]
    walls = [f.place("wall", x, -6, 0, free=True) for x in range(3, 9)]
    bal = f.balance
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, mod=0, unicode="x"))
    assert game.tool == "demolish"
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (3, -4))           # click: nothing until the release...
    assert f.structure_at(3, -4) is belts[0] and game.demolish_start is not None
    frames(game, 1)                                            # cursor draws
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (3, -4))             # ...then one belt gone, 50% back
    assert f.structure_at(3, -4) is None and f.balance == bal + COSTS["belt"] // 2
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, -7), dx=4, dy=4)    # drag a box over both rows (John)
    _mouse(game, pygame.MOUSEMOTION, 1, (8, -4), dx=28, dy=28)
    assert len(game.demolish_targets()) == 10 and f.count() == 12   # preview only
    frames(game, 1)                                            # red box + frames draw
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (8, -4), dx=28, dy=28)
    assert all(f.structure_at(x, -4) is None and f.structure_at(x, -6) is None for x in range(4, 9))
    assert f.structure_at(3, -6) is walls[0]                   # outside the box
    assert any("Demolished 10" in m[0] for m in game.hud.messages)
    # a box over the HQ never removes it; Esc mid-drag cancels the box
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (-4, -4), dx=4, dy=4)
    _mouse(game, pygame.MOUSEMOTION, 1, (3, -6), dx=28, dy=28)
    assert game.demolish_targets() == [walls[0]]
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert game.tool is None and game.demolish_start is None and f.structure_at(3, -6) is walls[0]
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (3, -6), dx=28, dy=28)
    assert f.structure_at(3, -6) is walls[0] and f.hub is not None and game.running
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, mod=0, unicode="x"))
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, mod=0, unicode="x"))
    assert game.tool is None                                   # X again leaves the tool


def test_del_removes_the_selection_and_c_shows_unit_costs(game):
    from ui.hud import unit_cost_summary
    frames(game, 1)
    f = game.factory
    f.terrain = None
    walls = [f.place("wall", x, 3, 0, free=True) for x in (3, 4, 5)]
    a = f.place("spawner_ranged", 3, 5, 2, free=True)
    b = f.place("spawner_ranged", 5, 5, 2, free=True)
    h = f.place("spawner_heavy", 7, 5, 2, free=True)
    assert unit_cost_summary([a, b, h]) == "250 (Ranged 50 x2, Heavy 150)"
    assert unit_cost_summary([h]) == "150 (Heavy 150)"
    game.selected_structures = list(walls)
    bal = f.balance
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, mod=0, unicode=""))
    assert all(f.structure_at(x, 3) is None for x in (3, 4, 5)) and game.selected_structures == []
    assert f.balance == bal + 3 * 2                            # 50% of three walls
    game.selected = h
    game.hover_tile = (3, 5)                                   # the hovered spawner is NOT the one removed
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, mod=0, unicode=""))
    assert f.structure_at(7, 5) is None and f.structure_at(3, 5) is a and game.selected is None
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, mod=0, unicode=""))
    assert f.structure_at(3, 5) is None                        # nothing selected: the hovered one
    game.selected_structures = [b]
    game.selected = None
    frames(game, 1)                                            # group panel with the [C] cost line draws
    game.selected_structures = []
    game.selected = b
    frames(game, 1)                                            # single spawner panel with "50 each"


def test_belt_drag_previews_then_builds_on_release(game):
    from settings import COSTS
    from sim.structures import E, S, W
    frames(game, 1)
    f = game.factory
    f.terrain = None
    f.balance = 1000
    game.set_tool("belt")
    game.build_dir = E
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, -3))
    _mouse(game, pygame.MOUSEMOTION, 1, (6, -3))               # skipped a tile: filled in
    _mouse(game, pygame.MOUSEMOTION, 1, (6, -1))
    assert len(f.belts) == 0 and f.balance == 1000             # nothing built yet
    assert [(x, y, d) for x, y, d in game.belt_path] == [(4, -3, E), (5, -3, E), (6, -3, S), (6, -2, S), (6, -1, S)]
    frames(game, 1)                                            # preview draws
    _mouse(game, pygame.MOUSEMOTION, 1, (6, -2))               # drag back: last tile undone
    assert len(game.belt_path) == 4 and game.build_dir == S
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (6, -2))
    assert game.belt_path == [] and len(f.belts) == 4 and f.balance == 1000 - 4 * COSTS["belt"]
    assert [f.structure_at(*t).direction for t in ((4, -3), (5, -3), (6, -3), (6, -2))] == [E, E, S, S]
    # a plain click still places one belt; dragging from an existing belt turns it to follow
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (8, -3))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (8, -3))
    assert f.structure_at(8, -3).direction == S and len(f.belts) == 5
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (6, -2))
    _mouse(game, pygame.MOUSEMOTION, 1, (5, -2))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (5, -2))
    assert f.structure_at(6, -2).direction == W and f.structure_at(5, -2).direction == W and len(f.belts) == 6


def test_box_select_structures_upgrade_and_repair_all(game):
    frames(game, 1)
    f = game.factory
    walls = [f.place("wall", x, 2, 0, free=True) for x in (3, 4, 5)]
    f.balance = 250
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (3, 1), dx=4, dy=4)     # box clear of the 6x6 HQ (x <= 2)
    _mouse(game, pygame.MOUSEMOTION, 1, (6, 3), dx=20, dy=20)
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (6, 3), dx=20, dy=20)
    assert game.selected_structures == walls and game.selected is None
    frames(game, 1)                                            # group panel + frames draw
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0, unicode="u"))
    assert [w.level for w in walls] == [2, 2, 1] and f.balance == 50   # third one unaffordable
    for w in walls:
        f.damage(w, 50)
    f.balance = 1000
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h, mod=0, unicode="h"))
    assert all(w.hp == w.max_hp for w in walls) and f.balance == 1000 - 3 * 10
    f.remove(4, 2)
    game.update(1 / 60)
    assert game.selected_structures == [walls[0], walls[2]]   # demolished one dropped
    # a box around a single structure selects it for the panel
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (3, 1), dx=4, dy=4)
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (3, 3), dx=20, dy=20)
    assert game.selected is walls[0] and game.selected_structures == []


def test_drag_from_a_belt_boxes_the_line_and_a_click_still_selects_one(game):
    frames(game, 1)
    f = game.factory
    f.terrain = None
    belts = [f.place("belt", x, 3, 1, free=True) for x in range(3, 8)]
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, 3))            # plain click: panel selection
    assert game.selected is None and game.box_start is not None  # decided on release
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (4, 3))
    assert game.selected is belts[1] and game.selected_structures == []
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (3, 3), dx=4, dy=4)  # drag starting ON a belt
    _mouse(game, pygame.MOUSEMOTION, 1, (7, 3), dx=28, dy=28)
    frames(game, 1)                                            # box draws
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (7, 3), dx=28, dy=28)
    assert game.selected is None and game.selected_structures == belts
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert game.selected_structures == [] and game.running


def test_hub_alert_draws_while_the_hub_is_hit(game):
    frames(game, 1)
    game.factory.damage(game.factory.hub, 10)
    assert game.factory.hub_under_attack()
    frames(game, 2)                                            # hub border + screen frame draw
    game.camera.zoom_index = 0
    frames(game, 1)


def test_belt_drag_shift_makes_an_l_and_r_turns_every_belt(game):
    from sim.structures import E, S, N
    frames(game, 1)
    f = game.factory
    f.terrain = None
    f.balance = 1000
    game.set_tool("belt")
    game.build_dir = E
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (2, -4))
    _mouse(game, pygame.MOUSEMOTION, 1, (4, -2))               # freehand diagonal: a staircase
    assert len(game.belt_path) == 5
    game._straight_belt_path((5, -1))                          # Shift: one run + one square corner
    assert [(x, y) for x, y, _ in game.belt_path] == [(2, -4), (3, -4), (4, -4), (5, -4), (5, -3), (5, -2), (5, -1)]
    assert [d for _, _, d in game.belt_path] == [E, E, E, S, S, S, S]
    game._straight_belt_path((2, -1))                          # back in the anchor column: straight down
    assert [(x, y) for x, y, _ in game.belt_path] == [(2, -4), (2, -3), (2, -2), (2, -1)]
    for _ in range(2):                                         # R twice: the line runs backwards
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, mod=0, unicode="r"))
    assert game.belt_turn == 2
    frames(game, 1)                                            # turned preview draws
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (2, -1))
    assert [f.structure_at(2, y).direction for y in (-4, -3, -2, -1)] == [N, N, N, N]
    assert game.belt_turn == 0 and game.belt_path == []


def test_drag_off_the_middle_of_a_line_makes_a_t_not_a_corner(game):
    from sim.structures import E, N, S, W
    frames(game, 1)
    f = game.factory
    f.terrain = None
    f.balance = 1000
    line = [f.place("belt", x, -2, E, free=True) for x in range(3, 8)]   # clear of the 6x6 HQ (x <= 2)
    game.set_tool("belt")
    game.build_dir = E
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (5, -2))           # start ON the middle belt...
    _mouse(game, pygame.MOUSEMOTION, 1, (5, -3))               # ...and drag up one tile
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (5, -3))
    mid, branch = f.structure_at(5, -2), f.structure_at(5, -3)
    assert mid is line[2] and mid.direction == E               # the line keeps flowing
    assert branch.direction == N
    game.update(1 / 60)                                        # links rebuild
    assert [o[2] for o in mid.outputs] == [E, N]               # T: straight on + the new branch
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (7, -2))           # from the END the last belt turns
    _mouse(game, pygame.MOUSEMOTION, 1, (7, 0))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (7, 0))
    assert line[4].direction == S and f.structure_at(7, -1).direction == S
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, -2))           # backwards over the line: reversed
    _mouse(game, pygame.MOUSEMOTION, 1, (3, -2))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (3, -2))
    assert line[1].direction == W and line[0].direction == W


def test_right_click_sets_gather_point_for_a_boxed_group_of_spawners(game):
    frames(game, 1)
    f = game.factory
    f.terrain = None
    a = f.place("spawner_melee", 3, 2, 2, free=True)
    b = f.place("spawner_ranged", 5, 2, 2, free=True)
    ua = game.combat.spawn_unit("melee", 3.5, 7.5, owner=a, rally=(3.5, 7.5))     # outside the box
    ub = game.combat.spawn_unit("ranged", 5.5, 7.5, owner=b, rally=(5.5, 7.5))
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (3, 1), dx=4, dy=4)   # box both spawners (clear of the HQ)
    _mouse(game, pygame.MOUSEMOTION, 1, (6, 2), dx=20, dy=20)
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (6, 2), dx=20, dy=20)
    assert game.selected_structures == [a, b] and game.selected_units == []
    frames(game, 1)                                                # flags for both draw
    _mouse(game, pygame.MOUSEBUTTONDOWN, 3, (-9, 6))       # clear of the minimap (a right click there looks around)
    assert a.rally == b.rally == (-8.5, 6.5)
    assert ua.rally == (3.5, 7.5) and ub.rally == (5.5, 7.5)        # units already out stay put (John)
    assert game.selected_structures == [a, b]                      # the group stays selected
    game.factory.balance = 1000
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=0, unicode="c"))
    assert a.queue == 1 and b.queue == 1                           # [C] queues one at every selected spawner
    game.selected_structures = []
    game.selected = a
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=0, unicode="c"))
    assert a.queue == 2 and b.queue == 1


def test_wheel_cycles_formation_and_middle_click_patrols(game):
    frames(game, 1)
    units = [game.combat.spawn_unit("melee", 4.5 + i, 6.5, rally=(4.5 + i, 6.5)) for i in range(3)]
    zoom = game.camera.zoom
    game.selected_units = list(units)
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    assert game.combat.group_formation(units) == "line" and game.camera.zoom == zoom   # no zoom with units selected
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert game.combat.group_formation(units) == "box"
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert game.combat.group_formation(units) == "ring"
    # a middle CLICK sets a patrol; a middle DRAG still pans (tiles clear of the HUD panels)
    pos = _mouse(game, pygame.MOUSEBUTTONDOWN, 2, (6, -2))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=2, pos=pos))
    assert all(u.patrol is not None and u.leg == 1 for u in units)
    assert len({u.patrol for u in units}) == 3 and all(u.panchor == (6.5, -1.5) for u in units)
    x0 = game.camera.x
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2, pos=(200, 300)))
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(160, 300), rel=(-40, 0), buttons=(0, 1, 0)))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=2, pos=(160, 300)))
    assert game.camera.x == x0 + 40 / game.camera.zoom and all(u.panchor == (6.5, -1.5) for u in units)
    frames(game, 2)                                            # patrol lines draw
    game.camera.x = x0
    # RMB move ends the patrol and keeps the formation
    _mouse(game, pygame.MOUSEBUTTONDOWN, 3, (7, -4))
    assert all(u.patrol is None for u in units) and game.combat.group_formation(units) == "ring"
    game.selected_units = []
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert game.camera.zoom < zoom                             # nothing selected: the wheel zooms again


def test_repair_spawner_tool_key_and_toolbar_fit(game):
    from ui.hud import TOOLS
    frames(game, 1)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_EQUALS, mod=0, unicode="="))
    assert game.tool == "spawner_repair"
    buttons = game.hud.buttons()
    assert len(buttons) == len(TOOLS) == 14
    assert game.hud.toolbar_rect.right <= game.hud.minimap_rect.left     # 14 buttons fit left of the minimap
    game.factory.terrain = None
    game.factory.balance = 1000
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (8, -6))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (8, -6))
    sp = game.factory.structure_at(8, -6)
    assert sp is not None and sp.KIND == "spawner_repair" and game.factory.balance == 900
    game.set_tool(None)
    game.selected = sp
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=0, unicode="c"))
    assert sp.queue == 1 and game.factory.balance == 800
    game.update(0.05)
    u = game.combat.units[-1]
    assert u.kind == "repair"
    game.selected_units = [u]
    frames(game, 2)                                            # red unit with a cross, load label, hints line


def test_bridge_drops_onto_a_belt_and_occupied_clicks_explain(game):
    from settings import COSTS
    from sim.structures import W, BACK
    frames(game, 1)
    f = game.factory
    f.terrain = None
    f.balance = 1000
    belts = [f.place("belt", x, -6, 1, free=True) for x in range(4, 9)]
    belts[2].items.append([7, 0.4, BACK])
    game.set_tool("bridge")
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (6, -6))
    br = f.structure_at(6, -6)
    assert br is not None and br.KIND == "bridge"
    assert br.lanes[W] == [[7, 0.4]] and f.balance == 1000 - COSTS["bridge"] + COSTS["belt"] // 2
    game.update(1 / 60)
    assert br.exits[W] is not None and br.exits[W][0] is belts[3]   # the line still runs across it
    assert any("replaced the belt" in m[0] for m in game.hud.messages)
    # the bridge tool on a tower says what is in the way; so does a belt click on a tower
    f.place("tower", 4, -8, 0, free=True)
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, -8))
    assert any("occupied by a Tower" in m[0] for m in game.hud.messages)
    game.hud.messages = []
    game.set_tool("belt")
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (4, -8))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (4, -8))
    assert any("occupied by a Tower" in m[0] for m in game.hud.messages)
    # a belt in the middle of a line keeps its direction; the message says so
    game.hud.messages = []
    game.build_dir = 0
    _mouse(game, pygame.MOUSEBUTTONDOWN, 1, (7, -6))
    _mouse(game, pygame.MOUSEBUTTONUP, 1, (7, -6))
    assert belts[3].direction == 1 and any("kept its direction" in m[0] for m in game.hud.messages)
