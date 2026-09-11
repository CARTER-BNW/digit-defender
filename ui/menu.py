"""World-select menu: Continue / New World / recent worlds / Fullscreen / Quit.

Blocking loop on the existing display. run() returns
{"action": "play", "meta": <world meta>} or {"action": "quit"}.
max_frames caps the total frames drawn (scripted smoke runs).
"""
import time

import pygame

from settings import WINDOW_W, WINDOW_H, COLORS
from world import persistence
from render import numbers

QUIT = "__quit__"
BACK = "__back__"
BG = (10, 22, 12)
FG = (230, 235, 230)
DIM = (140, 160, 140)
HI = (255, 220, 90)
MAX_LISTED = 6


def _ago(ts):
    s = max(0, time.time() - ts)
    if s < 90:
        return "just now"
    if s < 3600 * 1.5:
        return f"{int(s // 60)} min ago"
    if s < 86400 * 1.5:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} d ago"


class Menu:
    def __init__(self, config, max_frames=None):
        self.config = config
        self.clock = pygame.time.Clock()
        self.frames_left = max_frames

    def _tick(self):
        """Frame budget for scripted runs: True when the menu must stop."""
        self.clock.tick(60)
        if self.frames_left is not None:
            self.frames_left -= 1
            return self.frames_left <= 0
        return False

    def run(self):
        while True:
            worlds = persistence.list_worlds()
            options = []
            last = self.config.get("last_world")
            cont = next((m for m in worlds if m.get("slug") == last), worlds[0] if worlds else None)
            if cont is not None:
                options.append((f"Continue  {cont['name']}", ("play", cont)))
            options.append(("New World", ("new", None)))
            for m in worlds[:MAX_LISTED]:
                options.append((f"{m['name']}   seed {m['seed']}   {_ago(m.get('last_played', 0))}",
                                ("play", m)))
            fs = self.config.get("fullscreen", False)
            options.append((f"Fullscreen: {'On' if fs else 'Off'}", ("fullscreen", None)))
            options.append(("Quit", ("quit", None)))
            footer = "Up/Down or mouse, Enter to select, Del deletes the highlighted world"
            footer += ", Esc back to the game" if cont is not None else ""
            key = self._select(None, options, footer)
            if key == BACK:                              # Esc closes the menu: back into the last world
                if cont is None:
                    continue
                return {"action": "play", "meta": cont}
            if key == QUIT or key[0] == "quit":
                return {"action": "quit"}
            if key[0] == "delete":                       # Del on a world entry -> confirm -> remove
                payload = key[1]
                if isinstance(payload, tuple) and payload[0] == "play":
                    if self._delete_world(payload[1]) == QUIT:
                        return {"action": "quit"}
                continue
            action, meta = key
            if action == "play":
                return {"action": "play", "meta": meta}
            if action == "fullscreen":
                self._toggle_fullscreen()
                continue
            r = self._new_world()
            if r == QUIT:
                return {"action": "quit"}
            if isinstance(r, dict):
                return {"action": "play", "meta": r}

    def _delete_world(self, meta):
        """Confirm, then remove the world's save folder. Returns True when
        deleted, False when kept, QUIT if the window was closed."""
        choice = self._select(f"Delete world '{meta['name']}'?",
                              [("No, keep it", ("no", None)), ("Yes, delete it for good", ("yes", None))],
                              "Enter to choose, Esc keeps it")
        if choice == QUIT:
            return QUIT
        if choice == BACK or choice[0] != "yes":
            return False
        persistence.delete_world(meta["slug"])
        if self.config.get("last_world") == meta["slug"]:
            self.config.pop("last_world", None)
        return True

    def _toggle_fullscreen(self):
        self.config["fullscreen"] = not self.config.get("fullscreen", False)
        if self.config["fullscreen"]:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode((WINDOW_W, WINDOW_H))
        persistence.save_config(self.config)

    # ---- screens ---------------------------------------------------------------

    def _select(self, subtitle, options, footer):
        sel = 0
        while True:
            rects = self._draw(subtitle, [label for label, _ in options], sel, footer)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return QUIT
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return BACK
                    if event.key == pygame.K_DELETE:
                        return ("delete", options[sel][1])
                    if event.key in (pygame.K_UP, pygame.K_w):
                        sel = (sel - 1) % len(options)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        sel = (sel + 1) % len(options)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return options[sel][1]
                elif event.type == pygame.MOUSEMOTION:
                    for i, r in enumerate(rects):
                        if r.collidepoint(event.pos):
                            sel = i
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for i, r in enumerate(rects):
                        if r.collidepoint(event.pos):
                            return options[i][1]
            if self._tick():
                return QUIT

    def _new_world(self):
        name, seed, sel = "", "", 0
        while True:
            rows = [f"Name: {name or '(auto)'}", f"Seed: {seed or '(random)'}", "Create"]
            rects = self._draw("New World", rows, sel,
                               "type to edit, Up/Down to move, Enter on Create, Esc back")
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return QUIT
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for i, r in enumerate(rects):
                        if r.collidepoint(event.pos):
                            sel = i
                            if i == 2:
                                return self._create(name, seed)
                if event.type != pygame.KEYDOWN:
                    continue
                if event.key == pygame.K_ESCAPE:
                    return BACK
                elif event.key == pygame.K_UP:
                    sel = (sel - 1) % len(rows)
                elif event.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(rows)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if sel == 2:
                        return self._create(name, seed)
                    sel += 1
                elif event.key == pygame.K_BACKSPACE:
                    if sel == 0:
                        name = name[:-1]
                    elif sel == 1:
                        seed = seed[:-1]
                elif sel == 0 and event.unicode and event.unicode.isprintable() and len(name) < 24:
                    name += event.unicode
                elif sel == 1 and event.unicode.isdigit() and len(seed) < 10:
                    seed += event.unicode
            if self._tick():
                return QUIT

    @staticmethod
    def _create(name, seed):
        return persistence.create_world(name.strip() or None, int(seed) if seed else None)

    # ---- drawing ---------------------------------------------------------------

    def _draw(self, subtitle, lines, sel, footer):
        screen = pygame.display.get_surface()
        screen.fill(BG)
        w, h = screen.get_size()
        title = numbers.text("DIGIT DEFENDER", 64, HI)
        screen.blit(title, ((w - title.get_width()) // 2, h // 8))
        tag = numbers.text("mine digits, build math, defend the HQ", 18, DIM)
        screen.blit(tag, ((w - tag.get_width()) // 2, h // 8 + 74))
        y = h // 8 + 130
        if subtitle:
            s = numbers.text(subtitle, 28, DIM)
            screen.blit(s, ((w - s.get_width()) // 2, y))
            y += 56
        rects = []
        for i, line in enumerate(lines):
            s = numbers.text(line, 26, HI if i == sel else FG)
            rects.append(screen.blit(s, ((w - s.get_width()) // 2, y)))
            y += 44
        if footer:
            s = numbers.text(footer, 16, DIM)
            screen.blit(s, ((w - s.get_width()) // 2, h - 44))
        for note in persistence.warnings[-2:]:
            s = numbers.text(note, 14, (255, 150, 120))
            screen.blit(s, (12, h - 20 - 16 * (2 - persistence.warnings[-2:].index(note))))
        pygame.display.flip()
        return rects
