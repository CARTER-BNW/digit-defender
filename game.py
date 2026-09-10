"""Game: one play session. Event loop, fixed-timestep accumulator, camera
input (pan/zoom), build mode (toolbar/hotkeys, rotate, ghost, paint-place,
demolish), terrain streaming, rendering. The sim ticks from update() only in
whole ticks; rendering runs at FPS.
"""
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
from ui.hud import Hud, HOTKEYS, TOOL_NAMES


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
                             raids=(wave or {}).get("raids"))
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
        self.painting = False
        self.last_paint = None
        self.hover_tile = (0, 0)
        self.game_over = False

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
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            self.frame += 1
            if max_frames is not None and self.frame >= max_frames:
                self.running = False
        if self.meta is not None and not self.game_over:
            self.save()                          # never overwrite a save with a dead base
        return self.result

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
                if self.tool is None and isinstance(self.selected, Spawner):
                    wx, wy = self.camera.screen_to_world(*event.pos)
                    self.selected.rally = (wx / TILE_SIZE, wy / TILE_SIZE)
                    for u in self.combat.units:
                        if u.owner is self.selected:
                            u.rally = self.selected.rally
                    self.hud.message("Rally point set", 1.2)
                else:
                    self.set_tool(None)
                    self.selected = None
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self.dragging = False
            elif event.button == 1:
                self.painting = False
                self.last_paint = None
        elif event.type == pygame.MOUSEMOTION:
            self.hover_tile = cam.screen_to_tile(*event.pos)
            if self.dragging:
                z = cam.zoom
                cam.move(-event.rel[0] / z, -event.rel[1] / z)
            elif self.painting and self.tool and not self.hud.over_ui(event.pos):
                self._paint(self.hover_tile)
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
            elif self.selected is not None:
                self.selected = None
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
        elif key == pygame.K_x or key == pygame.K_DELETE:
            self.demolish(self.hover_tile)
        elif key == pygame.K_q:
            self.pick()
        elif key == pygame.K_h:
            self.repair()
        elif key == pygame.K_F6:                 # debug: spawn an enemy at the cursor
            tx, ty = self.hover_tile
            self.combat.spawn_enemy("grunt", tx + 0.5, ty + 0.5)
        elif key == pygame.K_F7:                 # debug: next wave now
            self.combat.wave.next_at_tick = self.factory.tick_count

    # ---- build mode ------------------------------------------------------

    def set_tool(self, kind):
        self.tool = kind
        if kind is not None:
            self.selected = None

    def rotate(self):
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
        if self.hud.click(pos, self):
            return
        tile = self.camera.screen_to_tile(*pos)
        self.hover_tile = tile
        if self.tool is not None:
            self.painting = True
            self.last_paint = tile
            self.try_place(tile, verbose=True)
        else:
            self.selected = self.factory.structure_at(*tile)

    def try_place(self, tile, verbose=False):
        tx, ty = tile
        ok, reason = self.factory.can_place(self.tool, tx, ty, self.build_dir)
        if not ok:
            if verbose and reason != "occupied":
                self.hud.message(reason)
            return None
        return self.factory.place(self.tool, tx, ty, self.build_dir)

    def _paint(self, tile):
        """Drag-place: belts follow the drag direction (the previous belt turns
        to point at the new tile); other kinds just repeat."""
        if tile == self.last_paint:
            return
        last = self.last_paint
        if self.tool == "belt" and last is not None:
            dx, dy = tile[0] - last[0], tile[1] - last[1]
            if (dx, dy) in DIR_VEC:
                self.build_dir = DIR_VEC.index((dx, dy))
                prev = self.factory.structure_at(*last)
                if isinstance(prev, Belt) and prev.direction != self.build_dir:
                    prev.direction = self.build_dir
                    self.factory.dirty_links = True
        self.try_place(tile)
        self.last_paint = tile

    def repair(self):
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
        keys = pygame.key.get_pressed()
        if keys[pygame.K_x] and not self.hud.over_ui(pygame.mouse.get_pos()):
            self.demolish(self.hover_tile)
        # fixed-timestep sim: whole ticks only, capped so a slow frame never
        # snowballs into a frozen game (docs/PLAN.md section 2.4)
        if not self.game_over:
            self.acc += dt
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
            self.hud.message(f"Target {ev[1]} delivered: +{ev[2]} bonus!")
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

    def draw(self):
        self.renderer.draw(self)
        self.hud.draw(self)
        pygame.display.flip()

    def ghost(self):
        """(kind, tx, ty, dir, ok, cost) for the build preview, or None."""
        if self.tool is None or self.hud.over_ui(pygame.mouse.get_pos()):
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
