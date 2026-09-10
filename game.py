"""Game: one play session. Event loop, fixed-timestep accumulator, camera
input (pan/zoom), terrain streaming, rendering. The sim (Phase 2+) ticks from
update() only in whole ticks; rendering runs at FPS.
"""
import pygame

from settings import (FPS, TICK_DT, MAX_TICKS_PER_FRAME, CAMERA_SPEED,
                      CAMERA_FAST_MULT, WINDOW_W, WINDOW_H)
from world.terrain import Terrain
from render.camera import Camera
from render.renderer import Renderer


class Game:
    def __init__(self, screen, seed, save_dir=None):
        self.screen = screen
        self.seed = seed
        self.save_dir = save_dir
        self.terrain = Terrain(seed, save_dir)
        w, h = screen.get_size()
        self.camera = Camera(w, h)
        self.renderer = Renderer(screen)
        self.clock = pygame.time.Clock()
        self.running = True
        self.result = "quit"
        self.frame = 0
        self.tick_count = 0
        self.acc = 0.0
        self.dragging = False
        self.fullscreen = bool(screen.get_flags() & pygame.FULLSCREEN)

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
        return self.result

    def handle_events(self):
        for event in pygame.event.get():
            self.handle_event(event)

    def handle_event(self, event):
        cam = self.camera
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_F3:
                self.renderer.debug = not self.renderer.debug
            elif event.key == pygame.K_F11:
                self.toggle_fullscreen()
            elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                cam.zoom_by(1)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                cam.zoom_by(-1)
        elif event.type == pygame.MOUSEWHEEL:
            cam.zoom_by(1 if event.y > 0 else -1, pygame.mouse.get_pos())
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            z = cam.zoom
            cam.move(-event.rel[0] / z, -event.rel[1] / z)
        elif event.type == pygame.VIDEORESIZE:
            cam.resize(event.w, event.h)

    def update(self, dt):
        self._pan_keys(min(dt, 0.1))
        # fixed-timestep sim: whole ticks only, capped so a slow frame never
        # snowballs into a frozen game (docs/PLAN.md section 2.4)
        self.acc += dt
        n = 0
        while self.acc >= TICK_DT and n < MAX_TICKS_PER_FRAME:
            self.tick()
            self.acc -= TICK_DT
            n += 1
        if n == MAX_TICKS_PER_FRAME:
            self.acc = 0.0
        self.terrain.update(*self.camera.keep_unload_rects())

    def tick(self):
        """One sim tick (Phase 2 adds factory.tick())."""
        self.tick_count += 1

    def _pan_keys(self, dt):
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        if dx or dy:
            speed = CAMERA_SPEED / self.camera.zoom   # constant screen speed
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                speed *= CAMERA_FAST_MULT
            self.camera.move(dx * speed * dt, dy * speed * dt)

    def draw(self):
        self.renderer.draw(self)
        pygame.display.flip()

    def debug_lines(self):
        """Extra F3 overlay lines (subclasses/phases append here)."""
        return []

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.renderer.screen = self.screen
        self.camera.resize(*self.screen.get_size())
