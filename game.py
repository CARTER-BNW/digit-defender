"""Game: one play session. Event loop, fixed-timestep accumulator, camera
input (pan/zoom), build mode (toolbar/hotkeys, rotate, ghost, paint-place,
demolish), terrain streaming, rendering. The sim ticks from update() only in
whole ticks; rendering runs at FPS.
"""
import math

import pygame

from settings import (FPS, TICK_DT, MAX_TICKS_PER_FRAME, CAMERA_SPEED,
                      CAMERA_FAST_MULT, WINDOW_W, WINDOW_H, TILE_SIZE, AUTOSAVE_S,
                      CHUNK_SIZE)
from world.terrain import Terrain
from world import persistence
from sim.factory import Factory
from sim.nests import NestRegistry
from sim.combat import Combat
from sim.structures import Spawner
from sim import nests as nestmod
from sim.structures import E, DIR_VEC, Belt
from render.camera import Camera
from render.renderer import Renderer
from ui.hud import Hud, HOTKEYS, TOOL_NAMES, DISPLAY_NAMES


class Game:
    def __init__(self, screen, seed, save_dir=None, factory=None, meta=None,
                 state=None, enemies=None):
        self.screen = screen
        self.seed = seed
        self.save_dir = save_dir
        self.meta = meta                     # world meta dict when persistent
        self.terrain = Terrain(seed, save_dir)
        if save_dir is not None:
            self.terrain.loader = lambda cx, cy: persistence.load_chunk(save_dir, cx, cy)
            self.terrain.saver = lambda ch: persistence.save_chunk(save_dir, ch.cx, ch.cy, ch.tiles)
        if factory is not None:
            self.factory = factory
        elif state is not None:
            self.factory = Factory.from_dict(state, seed=seed, terrain=self.terrain)
            if self.factory.hub is None:
                self.factory.create_hub(0, 0)
        else:
            self.factory = self._new_factory()
        self.nests = NestRegistry.from_dict(enemies or {})
        wave = (meta or {}).get("wave")
        self.combat = Combat(self.factory, seed, nests=self.nests, wave=wave,
                             raids=(wave or {}).get("raids"), units=(wave or {}).get("units"))
        self.autosave_s = AUTOSAVE_S
        self.autosave_t = 0.0
        w, h = screen.get_size()
        self.camera = Camera(w, h, x=TILE_SIZE / 2, y=TILE_SIZE / 2)   # hub centre
        cam = (meta or {}).get("camera")
        if cam:
            self.camera.x, self.camera.y = float(cam[0]), float(cam[1])
            self.camera.zoom_index = max(0, min(len(__import__("settings").ZOOM_LEVELS) - 1, int(cam[2])))
        self.renderer = Renderer(screen)
        self.renderer.nests = self.nests
        self.hud = Hud(screen)
        self.clock = pygame.time.Clock()
        self.running = True
        self.result = "quit"
        self.frame = 0
        self.acc = 0.0
        self.dragging = False
        self.fullscreen = bool(screen.get_flags() & pygame.FULLSCREEN)
        # build mode
        self.tool = None
        self.build_dir = E
        self.selected = None
        self.selected_units = []             # player units under command (RMB = move)
        self.selected_structures = []        # drag-box multi-select: [U] / [H] apply to all
        self.box_start = None                # screen pos where a LMB drag-select began
        self.box_end = None
        self.click_target = None             # structure under a pending click (selected on release)
        self.painting = False
        self.last_paint = None
        self.belt_path = []                  # [[tx, ty, dir], ...] belt drag preview, built on release
        self.belt_anchor = None              # tile the belt drag started on (Shift: straight L from here)
        self.belt_axis = None                # Shift drag: first run goes along "x" or "y" (locked on first move)
        self.belt_turn = 0                   # quarter turns [R] applied to every belt of the drag
        self.hover_tile = (0, 0)
        self.game_over = False
        self.paused = False
        self.speed = 1                       # sim speed multiplier: 1, 2, 4
        self.show_help = False

    def _new_factory(self):
        f = Factory(self.seed, self.terrain)
        f.create_hub(0, 0)
        return f

    # ---- persistence -----------------------------------------------------

    @classmethod
    def load(cls, screen, meta):
        """Resume a saved world (or start a freshly created one)."""
        saved_meta, structures, enemies = persistence.load_world(meta["slug"])
        meta = saved_meta or meta
        state = None
        if structures is not None:
            state = persistence.factory_state_from_meta(meta, structures)
        return cls(screen, int(meta["seed"]), save_dir=persistence.world_dir(meta["slug"]),
                   meta=meta, state=state, enemies=enemies)

    def save(self):
        if self.meta is None:
            return False
        persistence.save_world(self.meta, self.factory, self.camera, self.nests,
                               wave=self.wave_state())
        self.terrain.save_modified()
        self.autosave_t = 0.0
        return True

    def wave_state(self):
        """Serializable wave timer + raid counters (units are transient)."""
        return self.combat.to_dict()

    @property
    def tick_count(self):
        return self.factory.tick_count

    # ---- loop ------------------------------------------------------------

    def run(self, max_frames=None):
        try:
            while self.running:
                dt = self.clock.tick(FPS) / 1000.0
                self.handle_events()
                self.update(dt)
                self.draw()
                self.frame += 1
                if max_frames is not None and self.frame >= max_frames:
                    self.running = False
        except Exception:
            # crash insurance: the sim state is consistent between frames, so
            # keep the progress, log the traceback, then let it propagate
            self._crash_save()
            raise
        if self.meta is not None and not self.game_over:
            self.save()                          # never overwrite a save with a dead base
        return self.result

    def _crash_save(self):
        import traceback
        try:
            with open("crash.log", "a", encoding="utf-8") as fh:
                fh.write(traceback.format_exc() + "\n")
        except OSError:
            pass
        if self.meta is not None and not self.game_over:
            try:
                self.save()
            except Exception:
                pass

    def handle_events(self):
        for event in pygame.event.get():
            self.handle_event(event)

    def handle_event(self, event):
        cam = self.camera
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            self._key_down(event)
        elif event.type == pygame.MOUSEWHEEL:
            cam.zoom_by(1 if event.y > 0 else -1, pygame.mouse.get_pos())
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2:
                self.dragging = True
            elif event.button == 1:
                self._left_click(event.pos)
            elif event.button == 3:
                self._right_click(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self.dragging = False
            elif event.button == 1:
                if self.belt_path:
                    self._commit_belt_path()
                self.painting = False
                self.last_paint = None
                self._end_box(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            self.hover_tile = cam.screen_to_tile(*event.pos)
            if self.dragging:
                z = cam.zoom
                cam.move(-event.rel[0] / z, -event.rel[1] / z)
            elif self.painting and self.tool and not self.hud.over_ui(event.pos):
                self._paint(self.hover_tile)
            elif self.box_start is not None:
                self.box_end = event.pos
        elif event.type == pygame.VIDEORESIZE:
            cam.resize(event.w, event.h)

    def _key_down(self, event):
        key = event.key
        if self.game_over:
            if key == pygame.K_l:
                self.result = "reload"
                self.running = False
            elif key == pygame.K_ESCAPE:
                self.result = "menu"
                self.running = False
            return
        if key == pygame.K_ESCAPE:
            if self.tool is not None:
                self.set_tool(None)
            elif self.selected is not None or self.selected_units or self.selected_structures:
                self.selected = None
                self.selected_units = []
                self.selected_structures = []
            else:
                self.result = "menu"
                self.running = False
        elif key == pygame.K_F3:
            self.renderer.debug = not self.renderer.debug
        elif key == pygame.K_F11:
            self.toggle_fullscreen()
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.camera.zoom_by(1)
        elif key == pygame.K_KP_MINUS:
            self.camera.zoom_by(-1)
        elif key in HOTKEYS:
            kind = HOTKEYS[key]
            self.set_tool(None if self.tool == kind else kind)
        elif key == pygame.K_r:
            self.rotate()
        elif key == pygame.K_DELETE:             # one-shot; [X] is the demolish tool
            self.demolish(self.hover_tile)
        elif key == pygame.K_q:
            self.pick()
        elif key == pygame.K_h:
            self.repair()
        elif key == pygame.K_u:
            self.upgrade()
        elif key == pygame.K_HOME:
            self.go_home()
        elif key == pygame.K_SPACE:
            self.paused = not self.paused
        elif key == pygame.K_RIGHTBRACKET:
            self.speed = min(4, self.speed * 2)
        elif key == pygame.K_LEFTBRACKET:
            self.speed = max(1, self.speed // 2)
        elif key == pygame.K_F1:
            self.show_help = not self.show_help
        elif key == pygame.K_F6:                 # debug: spawn an enemy at the cursor
            tx, ty = self.hover_tile
            self.combat.spawn_enemy("grunt", tx + 0.5, ty + 0.5)
        elif key == pygame.K_F7:                 # debug: next wave now
            self.combat.wave.next_at_tick = self.factory.tick_count

    # ---- build mode ------------------------------------------------------

    def set_tool(self, kind):
        self.tool = kind
        self.belt_path = []
        self.belt_turn = 0
        self.painting = False
        if kind is not None:
            self.selected = None
            self.selected_structures = []

    def rotate(self):
        if self.belt_path:                       # mid-drag: every belt of the path turns a quarter
            self.belt_turn = (self.belt_turn + 1) % 4
            return
        if self.tool is not None:
            self.build_dir = (self.build_dir + 1) % 4
            return
        target = self.selected or self.factory.structure_at(*self.hover_tile)
        if target is not None:
            self.factory.rotate(target.x, target.y)

    def pick(self):
        s = self.factory.structure_at(*self.hover_tile)
        if s is not None and s.KIND in TOOL_NAMES:
            self.set_tool(s.KIND)
            self.build_dir = s.direction

    def _left_click(self, pos):
        """Build with a tool; otherwise pick a unit (Shift adds), select a
        structure (a spawner also trains one unit), or start a drag box on
        open ground."""
        if self.hud.click(pos, self):
            return
        tile = self.camera.screen_to_tile(*pos)
        self.hover_tile = tile
        if self.tool is not None:
            self.painting = True
            self.last_paint = tile
            if self.tool == "belt":
                self.belt_path = [[tile[0], tile[1], self.build_dir]]   # preview; built on release
                self.belt_anchor = tile
                self.belt_axis = None
                self.belt_turn = 0
            elif self.tool == "demolish":
                self.demolish(tile)
            else:
                self.try_place(tile, verbose=True)
            return
        shift = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        wx, wy = self.camera.screen_to_world(*pos)
        u = self.combat.unit_at(wx / TILE_SIZE, wy / TILE_SIZE)
        if u is not None:
            self.selected = None
            self.selected_structures = []
            if not shift:
                self.selected_units = [u]
            elif u in self.selected_units:
                self.selected_units.remove(u)
            else:
                self.selected_units.append(u)
            return
        # anything else is decided on release: a click selects the structure
        # under the cursor, a drag (even one starting on a belt) boxes an area
        self.click_target = self.factory.structure_at(*tile)
        self.box_start = self.box_end = pos

    def _end_box(self, pos):
        """Mouse-up without a tool. A tiny box is a click: select the
        structure under it (a spawner also trains one unit; Shift adds it to
        the group). A real box: player units inside join the unit selection,
        structures inside join the structure selection, a lone structure
        becomes the panel selection."""
        if self.box_start is None:
            return
        x0, y0 = self.box_start
        x1, y1 = pos
        self.box_start = self.box_end = None
        target, self.click_target = self.click_target, None
        shift = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        if abs(x1 - x0) < 4 and abs(y1 - y0) < 4:
            if target is None:
                if not shift:
                    self.selected = None
                    self.selected_units = []
                    self.selected_structures = []
                return
            if shift:
                group = self.selected_structures or ([self.selected] if self.selected else [])
                if target not in group:
                    group.append(target)
                self.selected_structures = sorted(group, key=lambda s: (s.y, s.x))
                self.selected = None
                self.selected_units = []
                return
            self.selected = target
            self.selected_units = []
            self.selected_structures = []
            if isinstance(target, Spawner):
                self.train(target)
            return
        if not shift:
            self.selected_units = []
            self.selected_structures = []
        self.selected = None
        ax, ay = self.camera.screen_to_world(min(x0, x1), min(y0, y1))
        bx, by = self.camera.screen_to_world(max(x0, x1), max(y0, y1))
        for u in self.combat.units:
            if u.dead or u in self.selected_units:
                continue
            if ax <= u.x * TILE_SIZE <= bx and ay <= u.y * TILE_SIZE <= by:
                self.selected_units.append(u)
        tx0, ty0 = math.floor(ax / TILE_SIZE), math.floor(ay / TILE_SIZE)
        tx1, ty1 = math.floor(bx / TILE_SIZE), math.floor(by / TILE_SIZE)
        seen = {id(s) for s in self.selected_structures}
        by_chunk = self.factory.by_chunk
        for cy in range(ty0 // CHUNK_SIZE, ty1 // CHUNK_SIZE + 1):
            for cx in range(tx0 // CHUNK_SIZE, tx1 // CHUNK_SIZE + 1):
                for s in by_chunk.get((cx, cy), ()):
                    if id(s) in seen:
                        continue
                    if any(tx0 <= tx <= tx1 and ty0 <= ty <= ty1 for tx, ty in s.tiles()):
                        seen.add(id(s))
                        self.selected_structures.append(s)
        self.selected_structures.sort(key=lambda s: (s.y, s.x))
        if len(self.selected_structures) == 1 and not self.selected_units:
            self.selected = self.selected_structures[0]
            self.selected_structures = []
        parts = []
        if self.selected_units:
            parts.append(f"{len(self.selected_units)} units   [RMB] move")
        if self.selected_structures:
            parts.append(f"{len(self.selected_structures)} structures   [U] upgrade all   [H] repair all")
        if parts:
            self.hud.message("selected: " + "     ".join(parts), 1.8)

    def _right_click(self, pos):
        """Cancel the tool; else move the selected units / set the selected
        spawner's gather point at the cursor; else clear the selection."""
        if self.tool is not None:
            self.set_tool(None)
            return
        wx, wy = self.camera.screen_to_world(*pos)
        gx, gy = wx / TILE_SIZE, wy / TILE_SIZE
        live = [u for u in self.selected_units if not u.dead]
        spawners = [s for s in self._group() if isinstance(s, Spawner)]
        if not spawners and isinstance(self.selected, Spawner):
            spawners = [self.selected]
        if live:
            self.combat.gather(live, gx, gy)
            self.hud.message(f"Moving {len(live)} unit{'s' if len(live) > 1 else ''}", 1.0)
        elif spawners:
            # one gather point for every selected spawner; their idle units regroup there
            point = (math.floor(gx) + 0.5, math.floor(gy) + 0.5)
            ids = {id(s) for s in spawners}
            for sp in spawners:
                sp.rally = point
            self.combat.gather([u for u in self.combat.units if id(u.owner) in ids], *point)
            n = len(spawners)
            self.hud.message("Gather point set" if n == 1 else f"Gather point set for {n} spawners", 1.2)
        else:
            self.selected = None
            self.selected_units = []
            self.selected_structures = []

    def train(self, sp):
        """Queue one unit at a spawner (pays its unit cost)."""
        err = sp.enqueue(self.factory)
        if err:
            self.hud.message(f"Cannot train: {err}", 1.5)
            return False
        self.hud.message(f"{TOOL_NAMES[sp.KIND]} unit queued ({sp.queue} waiting)", 1.2)
        return True

    def try_place(self, tile, verbose=False):
        tx, ty = tile
        ok, reason = self.factory.can_place(self.tool, tx, ty, self.build_dir)
        if not ok:
            if verbose and reason != "occupied":
                self.hud.message(reason)
            return None
        s = self.factory.place(self.tool, tx, ty, self.build_dir)
        if s is not None and verbose and self.tool == "tower":
            self.hud.message("Tower placed: run a belt or a miner into any side for ammo", 3.5)
        return s

    @staticmethod
    def _tiles_between(a, b):
        """Tiles from a (exclusive) to b (inclusive), one step at a time along
        the larger remaining axis, so a fast drag never skips tiles."""
        x, y = a
        bx, by = b
        while (x, y) != (bx, by):
            dx, dy = bx - x, by - y
            if abs(dx) >= abs(dy):
                x += 1 if dx > 0 else -1
            else:
                y += 1 if dy > 0 else -1
            yield (x, y)

    def _paint(self, tile):
        """Drag with a tool held: belts extend the preview path; the demolish
        tool sweeps; other kinds place on every tile crossed."""
        if tile == self.last_paint:
            return
        last = self.last_paint if self.last_paint is not None else tile
        if self.tool == "belt":
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self._straight_belt_path(tile)     # Shift: one straight run and one square corner
            else:
                self._extend_belt_path(tile)
        elif self.tool == "demolish":
            for t in self._tiles_between(last, tile):
                self.demolish(t)
        else:
            for t in self._tiles_between(last, tile):
                self.try_place(t)
        self.last_paint = tile

    def _extend_belt_path(self, tile):
        """Grow the belt preview to `tile`: each belt turns to point at the
        next; dragging back over the previous tile undoes the last one."""
        path = self.belt_path
        if not path:
            path.append([tile[0], tile[1], self.build_dir])
            return
        if len(path) >= 2 and tile == (path[-2][0], path[-2][1]):
            path.pop()
            self.build_dir = path[-1][2]
            return
        for t in self._tiles_between((path[-1][0], path[-1][1]), tile):
            d = DIR_VEC.index((t[0] - path[-1][0], t[1] - path[-1][1]))
            path[-1][2] = d
            path.append([t[0], t[1], d])
            self.build_dir = d

    def _straight_belt_path(self, tile):
        """Shift drag: the path is one straight run from the anchor along the
        axis of the first move, then one square corner to the cursor."""
        anchor = self.belt_anchor or (self.belt_path[0][0], self.belt_path[0][1])
        ax, ay = anchor
        tx, ty = tile
        if self.belt_axis is None and (tx, ty) != (ax, ay):
            self.belt_axis = "x" if abs(tx - ax) >= abs(ty - ay) else "y"
        corner = (tx, ay) if self.belt_axis == "x" else (ax, ty)
        tiles = [anchor] + list(self._tiles_between(anchor, corner)) + list(self._tiles_between(corner, tile))
        path = []
        for i, t in enumerate(tiles):
            if i + 1 < len(tiles):
                nxt = tiles[i + 1]
                d = DIR_VEC.index((nxt[0] - t[0], nxt[1] - t[1]))
            else:
                d = path[-1][2] if path else self.build_dir
            path.append([t[0], t[1], d])
        self.belt_path = path
        self.build_dir = path[-1][2]

    def _commit_belt_path(self):
        """Build the previewed belts (each turned by the [R] offset): new belts
        are placed (cost checked per tile), anything that is not a belt is
        skipped. A belt already on the path is turned only when that cannot
        break its line: at a line's end (nothing in front) or to reverse it.
        A belt in the middle of a line keeps flowing, so a drag off it leaves
        a branch beside the line: a T-junction (John). Returns belts built."""
        path, self.belt_path = self.belt_path, []
        turn, self.belt_turn = self.belt_turn, 0
        built = 0
        reason = None
        for x, y, d in path:
            d = (d + turn) % 4
            s = self.factory.structure_at(x, y)
            if isinstance(s, Belt):
                if s.direction != d and (self.factory.structure_at(*s.front_tile()) is None
                                         or s.direction == (d + 2) % 4):
                    s.direction = d
                    self.factory.dirty_links = True
                continue
            ok, why = self.factory.can_place("belt", x, y, d)
            if not ok:
                if why != "occupied" and reason is None:
                    reason = why
                continue
            if self.factory.place("belt", x, y, d) is not None:
                built += 1
        if reason is not None:
            self.hud.message(reason)
        return built

    def go_home(self):
        """Centre the camera on the hub."""
        hub = self.factory.hub
        cx, cy = (hub.x, hub.y) if hub is not None else (0, 0)
        self.camera.x = (cx + 0.5) * TILE_SIZE
        self.camera.y = (cy + 0.5) * TILE_SIZE

    def _group(self):
        """Live structures of the drag-box selection."""
        return [s for s in self.selected_structures if self.factory.structure_at(s.x, s.y) is s]

    def upgrade(self):
        """[U]: pay balance to lift the selected/hovered structure one level
        (every structure of a drag-box selection, in (y, x) order)."""
        group = self._group()
        if group:
            done = skipped = total = 0
            for s in group:
                if self.factory.upgrade_cost(s) is None:
                    continue
                paid = self.factory.upgrade(s)
                if paid:
                    done += 1
                    total += paid
                else:
                    skipped += 1
            msg = f"Upgraded {done} structure{'s' if done != 1 else ''} for {total}"
            if skipped:
                msg += f"   ({skipped} skipped: not enough balance)"
            self.hud.message(msg, 2)
            return total
        target = self.selected or self.factory.structure_at(*self.hover_tile)
        if target is None:
            return 0
        cost = self.factory.upgrade_cost(target)
        if cost is None:
            self.hud.message("Already at max level", 1.5)
            return 0
        paid = self.factory.upgrade(target)
        if paid:
            self.hud.message(f"{DISPLAY_NAMES.get(target.KIND, target.KIND)} upgraded to Lv {target.level} for {paid}", 1.5)
        else:
            self.hud.message(f"Upgrade needs {cost}", 1.5)
        return paid

    def repair(self):
        group = self._group()
        if group:
            total = sum(self.factory.repair(s) for s in group)
            self.hud.message(f"Repaired for {total}" if total else "Nothing to repair (or not enough balance)", 1.5)
            return total
        target = self.selected or self.factory.structure_at(*self.hover_tile)
        if target is None:
            return 0
        missing = target.max_hp - target.hp
        if missing <= 0:
            self.hud.message("Already at full hp", 1.5)
            return 0
        cost = self.factory.repair(target)
        if cost:
            self.hud.message(f"Repaired for {cost}", 1.5)
        else:
            from settings import REPAIR_COST_PER_HP
            self.hud.message(f"Repair needs {int(missing * REPAIR_COST_PER_HP + 0.999)}", 1.5)
        return cost

    def demolish(self, tile):
        s = self.factory.remove(*tile)
        if s is not None and s is self.selected:
            self.selected = None
        return s

    # ---- update ----------------------------------------------------------

    def update(self, dt):
        self._pan_keys(min(dt, 0.1))
        # hover follows the camera too (keeps hover queries on-screen, so the
        # HUD never regenerates a chunk that streaming just dropped)
        self.hover_tile = self.camera.screen_to_tile(*pygame.mouse.get_pos())
        # links (belt shapes, miner outputs, machine targets) refresh right away
        # even while paused, so what you build looks and behaves connected
        if self.factory.dirty_links:
            self.factory.rebuild_links()
        # fixed-timestep sim: whole ticks only, capped so a slow frame never
        # snowballs into a frozen game (docs/PLAN.md section 2.4)
        if not self.game_over and not self.paused:
            self.acc += dt * self.speed
            n = 0
            while self.acc >= TICK_DT and n < MAX_TICKS_PER_FRAME:
                self.tick()
                self.acc -= TICK_DT
                n += 1
            if n == MAX_TICKS_PER_FRAME:
                self.acc = 0.0
        for ev in self.factory.events:
            self._on_event(ev)
        self.factory.events.clear()
        if self.selected_units and any(u.dead for u in self.selected_units):
            self.selected_units = [u for u in self.selected_units if not u.dead]
        if self.selected_structures:
            live = self._group()
            if len(live) != len(self.selected_structures):
                self.selected_structures = live
        if self.selected is not None and self.factory.structure_at(self.selected.x, self.selected.y) is not self.selected:
            self.selected = None                     # destroyed in combat
        if self.factory.hub_destroyed and not self.game_over:
            self.game_over = True
            self.set_tool(None)
        self.hud.update(dt)
        if self.meta is not None:
            self.autosave_t += dt
            if self.autosave_t >= self.autosave_s:
                self.save()
                self.hud.message("Autosaved", 1.5)
        keep, unload = self.camera.keep_unload_rects()
        self.terrain.update(keep, unload, self.camera.visible_chunk_range())

    def tick(self):
        self.factory.tick()

    def _on_event(self, ev):
        kind = ev[0]
        if kind == "target":
            self.hud.message(f"Target done: {ev[3]} x {ev[1]} delivered, +{ev[2]} bonus!   "
                             f"Next: Lv{ev[4]} wants {ev[6]} x {ev[5]}", 4)
        elif kind == "wave":
            self.hud.message(f"Wave {ev[1]}: {ev[2]} enemies incoming!", 4)
        elif kind == "raid":
            self.hud.message(f"Nest raid: {ev[3]} enemies!", 4)
        elif kind == "nest_aggro":
            self.hud.message("A nest noticed your base...", 4)
        elif kind == "nest_destroyed":
            self.hud.message(f"Nest destroyed! Bounty +{ev[5]}", 5)
            cx, cy = ev[3] // CHUNK_SIZE, ev[4] // CHUNK_SIZE
            chunk = self.terrain.peek_chunk(cx, cy)
            if chunk is not None:
                chunk.invalidate()
        elif kind == "destroyed":
            self.hud.message(f"{ev[1]} at ({ev[2]}, {ev[3]}) destroyed", 2)

    def _pan_keys(self, dt):
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        if dx or dy:
            speed = CAMERA_SPEED / self.camera.zoom   # constant screen speed
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                speed *= CAMERA_FAST_MULT
            self.camera.move(dx * speed * dt, dy * speed * dt)

    # ---- draw ------------------------------------------------------------

    @property
    def render_frac(self):
        """Fraction of the next tick already elapsed (belt item interpolation)."""
        if self.paused or self.game_over:
            return 0.0
        return min(1.0, self.acc / TICK_DT)

    def draw(self):
        self.renderer.draw(self)
        self.hud.draw(self)
        pygame.display.flip()

    def ghost(self):
        """(kind, tx, ty, dir, ok, cost) for the build preview, or None (no
        tool, the demolish tool, a belt drag in progress, or over the UI)."""
        if self.tool is None or self.tool == "demolish" or self.belt_path:
            return None
        if self.hud.over_ui(pygame.mouse.get_pos()):
            return None
        tx, ty = self.hover_tile
        ok, _ = self.factory.can_place(self.tool, tx, ty, self.build_dir)
        from settings import COSTS
        return self.tool, tx, ty, self.build_dir, ok, COSTS.get(self.tool, 0)

    def debug_lines(self):
        f, c = self.factory, self.combat
        return [f"structures {f.count()}  belts {len(f.belts)}  miners {len(f.miners)}  "
                f"machines {len(f.machines)}  delivered {f.stats['delivered']}  voided {f.stats['voided']}",
                f"enemies {len(c.enemies)}  units {len(c.units)}  kills {c.stats['kills']}  wave {c.wave.number} "
                f"in {c.seconds_to_wave():.0f}s  nests known {len(c.known_nests)} active {len(c.active_nests)}  "
                f"[F6] spawn enemy  [F7] wave now"]

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.renderer.screen = self.screen
        self.hud.screen = self.screen
        self.camera.resize(*self.screen.get_size())
