"""HUD: balance, targets, build toolbar with hotkeys, hover info, messages."""
import pygame

from settings import COLORS, COSTS
from render import numbers
from sim.structures import KINDS, Belt, Miner, MathMachine, Tower

# toolbar order and hotkeys (Phase 5 appends spawners)
TOOLS = [("belt", "1"), ("miner", "2"), ("adder", "3"), ("subtractor", "4"),
         ("multiplier", "5"), ("divider", "6"), ("wall", "7"), ("tower", "8"),
         ("spawner_ranged", "9"), ("spawner_melee", "0"), ("spawner_heavy", "-")]
TOOL_NAMES = {"belt": "Belt", "miner": "Miner", "adder": "Adder", "subtractor": "Subtract",
              "multiplier": "Multiply", "divider": "Divide", "wall": "Wall", "tower": "Tower",
              "spawner_ranged": "Ranged", "spawner_melee": "Melee", "spawner_heavy": "Heavy"}
_KEYCODES = {"1": pygame.K_1, "2": pygame.K_2, "3": pygame.K_3, "4": pygame.K_4, "5": pygame.K_5,
             "6": pygame.K_6, "7": pygame.K_7, "8": pygame.K_8, "9": pygame.K_9, "0": pygame.K_0,
             "-": pygame.K_MINUS}
HOTKEYS = {_KEYCODES[k]: kind for kind, k in TOOLS}
BTN = 64
GAP = 6


class Hud:
    def __init__(self, screen):
        self.screen = screen
        self.messages = []          # [text, ttl]
        self.toolbar_rect = pygame.Rect(0, 0, 0, 0)

    def message(self, text, ttl=2.5):
        self.messages = [m for m in self.messages if m[0] != text]
        self.messages.append([text, ttl])

    def update(self, dt):
        for m in self.messages:
            m[1] -= dt
        self.messages = [m for m in self.messages if m[1] > 0][-4:]

    # ---- layout --------------------------------------------------------------

    def buttons(self):
        w, h = self.screen.get_size()
        total = len(TOOLS) * BTN + (len(TOOLS) - 1) * GAP
        x0 = (w - total) // 2
        y0 = h - BTN - 10
        out = []
        for i, (kind, key) in enumerate(TOOLS):
            out.append((pygame.Rect(x0 + i * (BTN + GAP), y0, BTN, BTN), kind, key))
        self.toolbar_rect = pygame.Rect(x0 - 8, y0 - 8, total + 16, BTN + 16)
        return out

    def over_ui(self, pos):
        return self.toolbar_rect.collidepoint(pos)

    def click(self, pos, game):
        """Toolbar hit test; returns True when the click was consumed."""
        for rect, kind, _ in self.buttons():
            if rect.collidepoint(pos):
                game.set_tool(None if game.tool == kind else kind)
                return True
        return self.toolbar_rect.collidepoint(pos)

    # ---- drawing -------------------------------------------------------------

    def draw(self, game):
        screen = self.screen
        f = game.factory
        w, h = screen.get_size()
        # balance
        self._panel((8, 8, 260, 58))
        screen.blit(numbers.text("Balance", 14, (170, 190, 170)), (16, 12))
        screen.blit(numbers.text(numbers.fmt(f.balance), 28), (16, 28))
        # targets
        self._panel((w - 228, 8, 220, 24 + 22 * len(f.targets)))
        screen.blit(numbers.text("Targets  (deliver exactly)", 14, (170, 190, 170)), (w - 220, 12))
        for i, t in enumerate(f.targets):
            y = 32 + i * 22
            screen.blit(numbers.text(numbers.fmt(t.value), 18, (255, 230, 120)), (w - 220, y))
            screen.blit(numbers.text(f"+{numbers.fmt(t.reward)}", 16, (140, 255, 140)), (w - 120, y + 1))
        self._draw_toolbar(game)
        self._draw_hover(game)
        self._draw_messages()

    def _panel(self, rect):
        r = pygame.Rect(rect)
        surf = pygame.Surface(r.size, pygame.SRCALPHA)
        surf.fill((*COLORS["panel"], 200))
        self.screen.blit(surf, r.topleft)
        pygame.draw.rect(self.screen, COLORS["panel_border"], r, 1)

    def _draw_toolbar(self, game):
        screen = self.screen
        buttons = self.buttons()
        self._panel(self.toolbar_rect)
        balance = game.factory.balance
        for rect, kind, key in buttons:
            cost = COSTS.get(kind, 0)
            color = COLORS.get(kind, (120, 120, 120))
            if balance < cost:
                color = tuple(int(c * 0.45) for c in color)
            pygame.draw.rect(screen, color, rect.inflate(-8, -22).move(0, -6), border_radius=4)
            if game.tool == kind:
                pygame.draw.rect(screen, (255, 255, 120), rect, 2, border_radius=4)
            else:
                pygame.draw.rect(screen, COLORS["panel_border"], rect, 1, border_radius=4)
            screen.blit(numbers.text(key, 13), (rect.x + 4, rect.y + 2))
            name = numbers.text(TOOL_NAMES[kind], 12)
            screen.blit(name, (rect.centerx - name.get_width() // 2, rect.bottom - 26))
            c = numbers.text(str(cost), 12, (255, 230, 120) if balance >= cost else (255, 110, 110))
            screen.blit(c, (rect.centerx - c.get_width() // 2, rect.bottom - 13))

    def _draw_hover(self, game):
        lines = []
        if game.tool:
            d = "NESW"[game.build_dir]
            lines.append(f"Build {TOOL_NAMES[game.tool]} facing {d}   [R] rotate  [LMB] place  [X] demolish  [Esc] cancel")
        else:
            lines.append("[1-9] build tools  [R] rotate  [X] demolish  [Q] pick  [wheel] zoom  [MMB] pan  [F3] debug")
        tx, ty = game.hover_tile
        s = game.factory.structure_at(tx, ty)
        info = f"tile ({tx}, {ty})"
        dep = game.terrain.deposit_at(tx, ty)
        if dep:
            info += f"   deposit {dep}"
        if s is not None:
            info += f"   {TOOL_NAMES.get(s.KIND, s.KIND)}  Lv {s.level}  fed {numbers.fmt(s.invested)}  hp {numbers.fmt(s.hp)}/{numbers.fmt(s.max_hp)}"
            if isinstance(s, Belt):
                info += f"  speed {s.speed * 20:.2f} t/s  items {len(s.items)}"
            elif isinstance(s, Miner):
                info += f"  every {s.period / 20:.2f}s"
            elif isinstance(s, MathMachine):
                info += f"  A{list(s.in_a)} B{list(s.in_b)} out {s.out}"
            elif isinstance(s, Tower):
                info += f"  ammo {list(s.ammo)}"
        lines.append(info)
        sel = game.selected
        if sel is not None and sel is not s:
            lines.append(f"selected {TOOL_NAMES.get(sel.KIND, sel.KIND)} at ({sel.x}, {sel.y})  Lv {sel.level}"
                         f"  fed {numbers.fmt(sel.invested)}  hp {numbers.fmt(sel.hp)}/{numbers.fmt(sel.max_hp)}")
        y = self.toolbar_rect.top - 8 - 18 * len(lines)
        for line in lines:
            self.screen.blit(numbers.text(line, 14), (12, y))
            y += 18

    def _draw_messages(self):
        w = self.screen.get_width()
        y = 80
        for text, ttl in self.messages:
            surf = numbers.text(text, 18, (255, 220, 120))
            if ttl < 0.6:
                surf = surf.copy()
                surf.set_alpha(int(255 * ttl / 0.6))
            self.screen.blit(surf, (w // 2 - surf.get_width() // 2, y))
            y += 24
