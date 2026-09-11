"""HUD: balance, targets, build toolbar with hotkeys, hover info, messages."""
import math

import pygame

from settings import COLORS, COSTS, REPAIR_COST_PER_HP, TICK_RATE, TILE_SIZE, CHUNK_SIZE, WAVE_WARNING_S
from render import numbers
from render import combat as rcombat
from sim import leveling
from sim.structures import KINDS, Belt, Miner, MathMachine, Tower, Spawner, Hub, ROLE_FEED

# toolbar order and hotkeys (Phase 5 appends spawners)
TOOLS = [("belt", "1"), ("miner", "2"), ("adder", "3"), ("subtractor", "4"),
         ("multiplier", "5"), ("divider", "6"), ("wall", "7"), ("tower", "8"),
         ("spawner_ranged", "9"), ("spawner_melee", "0"), ("spawner_heavy", "-"),
         ("demolish", "X")]                 # demolish is a tool too: click or drag to remove
TOOL_NAMES = {"belt": "Belt", "miner": "Miner", "adder": "Adder", "subtractor": "Subtract",
              "multiplier": "Multiply", "divider": "Divide", "wall": "Wall", "tower": "Tower",
              "spawner_ranged": "Ranged", "spawner_melee": "Melee", "spawner_heavy": "Heavy",
              "demolish": "Demolish"}
_KEYCODES = {"1": pygame.K_1, "2": pygame.K_2, "3": pygame.K_3, "4": pygame.K_4, "5": pygame.K_5,
             "6": pygame.K_6, "7": pygame.K_7, "8": pygame.K_8, "9": pygame.K_9, "0": pygame.K_0,
             "-": pygame.K_MINUS, "X": pygame.K_x}
HOTKEYS = {_KEYCODES[k]: kind for kind, k in TOOLS}
DISPLAY_NAMES = dict(TOOL_NAMES, hub="HQ")     # what the player calls each kind
BTN = 62                                        # 12 buttons fit left of the 440 px minimap at 1280 wide
GAP = 4


class Hud:
    """Layout (John, round 11): a right column with the balance (centred),
    the targets, the HQ button and a hints panel (menu toggle); the wave timer
    top centre; the clicked structure's info panel top left; a double-size
    minimap bottom right with the toolbar centred in the space left of it."""
    COL_W = 340                                       # right column width

    def __init__(self, screen):
        self.screen = screen
        self.messages = []          # [text, ttl]
        self.toolbar_rect = pygame.Rect(0, 0, 0, 0)
        self.minimap_rect = pygame.Rect(0, 0, 0, 0)
        self.hints_rect = pygame.Rect(0, 0, 0, 0)
        self.rects = {}             # balance / targets panels (click-through blockers)
        self._minimap = None        # cached surface, rebuilt every few frames
        self._minimap_frame = -100
        self._mini_origin = None    # (tx0, ty0, scale) of the cached minimap: click -> world
        self._alert_surf = None     # red screen frame (hub under attack), cached per size
        self.hub_button = pygame.Rect(8, 72, 120, 26)

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
        avail = w - self.MINI_W - 16                  # centred in the space left of the minimap
        x0 = max(8, (avail - total) // 2)
        y0 = h - BTN - 10
        out = []
        for i, (kind, key) in enumerate(TOOLS):
            out.append((pygame.Rect(x0 + i * (BTN + GAP), y0, BTN, BTN), kind, key))
        self.toolbar_rect = pygame.Rect(x0 - 8, y0 - 8, total + 16, BTN + 16)
        return out

    def over_ui(self, pos):
        return (self.toolbar_rect.collidepoint(pos) or self.hub_button.collidepoint(pos)
                or self.minimap_rect.collidepoint(pos) or self.hints_rect.collidepoint(pos)
                or any(r.collidepoint(pos) for r in self.rects.values()))

    def click(self, pos, game):
        """UI hit test; returns True when the click was consumed. The HQ button
        recentres on the HQ, the minimap recentres on the clicked spot."""
        if self.hub_button.collidepoint(pos):
            game.go_home()
            return True
        if self.minimap_rect.collidepoint(pos) and self._mini_origin is not None:
            tx0, ty0, scale = self._mini_origin
            game.camera.x = (tx0 + (pos[0] - self.minimap_rect.x) / scale) * TILE_SIZE
            game.camera.y = (ty0 + (pos[1] - self.minimap_rect.y) / scale) * TILE_SIZE
            return True
        for rect, kind, _ in self.buttons():
            if rect.collidepoint(pos):
                game.set_tool(None if game.tool == kind else kind)
                return True
        return self.over_ui(pos)

    # ---- drawing -------------------------------------------------------------

    def draw(self, game):
        screen = self.screen
        f = game.factory
        w, h = screen.get_size()
        col = self.COL_W
        x = w - col - 8
        # right column, top to bottom: balance (centred), targets, HQ button, hints
        bal = pygame.Rect(x, 8, col, 58)
        self._panel(bal)
        t = numbers.text("Balance", 14, (170, 190, 170))
        screen.blit(t, (bal.centerx - t.get_width() // 2, bal.y + 4))
        t = numbers.text(numbers.fmt(f.balance), 28)
        screen.blit(t, (bal.centerx - t.get_width() // 2, bal.y + 22))
        tg = pygame.Rect(x, bal.bottom + 6, col, 24 + 22 * len(f.targets))
        self._panel(tg)
        screen.blit(numbers.text("Targets   (deliver amount x number)", 14, (170, 190, 170)), (tg.x + 8, tg.y + 4))
        for i, tgt in enumerate(f.targets):
            y = tg.y + 24 + i * 22
            xx = tg.x + 8
            screen.blit(numbers.text(f"{tgt.amount} x", 15, (200, 220, 200)), (xx, y + 2))
            screen.blit(numbers.text(numbers.fmt(tgt.value), 18, (255, 230, 120)), (xx + 52, y))
            screen.blit(numbers.text(f"{tgt.delivered}/{tgt.amount}", 14, (200, 220, 200)), (xx + 140, y + 3))
            screen.blit(numbers.text(f"Lv{tgt.level}", 13, (170, 190, 170)), (xx + 208, y + 3))
            screen.blit(numbers.text(f"+{numbers.fmt(tgt.reward)}", 16, (140, 255, 140)), (xx + 258, y + 1))
        self.rects = {"balance": bal, "targets": tg}
        hb = self.hub_button
        hb.update(x + col // 2 - 60, tg.bottom + 6, 120, 26)
        pygame.draw.rect(screen, COLORS["hub"], hb, border_radius=4)
        pygame.draw.rect(screen, COLORS["panel_border"], hb, 1, border_radius=4)
        label = numbers.text("HQ  [Home]", 14)
        screen.blit(label, (hb.centerx - label.get_width() // 2, hb.centery - label.get_height() // 2))
        if getattr(game, "show_hints", True):
            self._draw_hints(game, x, hb.bottom + 6, col)
        else:
            self.hints_rect = pygame.Rect(0, 0, 0, 0)
        self._draw_wave(game)
        self._draw_minimap(game)
        self._draw_toolbar(game)
        if game.selected is not None:
            self._draw_panel(game, game.selected)
        elif game.selected_structures:
            self._draw_group_panel(game)
        rcombat.draw_offscreen_indicators(screen, game.camera, game.combat)   # on top of the panels
        self._draw_hub_alert(game)
        self._draw_messages()
        if game.show_help:
            self._draw_help()
        if game.game_over:
            self._draw_game_over(game)

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
            if kind == "demolish":
                c = numbers.text("50% back", 11, (255, 230, 120))
            else:
                c = numbers.text(str(cost), 12, (255, 230, 120) if balance >= cost else (255, 110, 110))
            screen.blit(c, (rect.centerx - c.get_width() // 2, rect.bottom - 13))

    @staticmethod
    def _wrap(text, px, max_w):
        """Greedy word wrap using the cached text widths."""
        lines, cur = [], ""
        for word in text.split():
            cand = f"{cur} {word}" if cur else word
            if not cur or numbers.text(cand, px).get_width() <= max_w:
                cur = cand
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _draw_hints(self, game, x, y, col):
        """The info hints (controls, hovered tile, selection) in a panel."""
        lines = []
        for text in self._hint_lines(game):
            lines.extend(self._wrap(text, 12, col - 16))
        self.hints_rect = pygame.Rect(x, y, col, 12 + 16 * len(lines))
        self._panel(self.hints_rect)
        for i, line in enumerate(lines):
            self.screen.blit(numbers.text(line, 12), (x + 8, y + 6 + i * 16))

    def _hint_lines(self, game):
        lines = []
        if game.tool == "demolish":
            lines.append("Demolish   [LMB] click or drag over buildings to remove (50% refund)   [X] or [Esc] to stop")
        elif game.tool == "belt":
            n = len(game.belt_path)
            if n:
                turned = f"   belts turned {game.belt_turn * 90} deg" if game.belt_turn else ""
                lines.append(f"Belt preview: {n} tiles, {n * COSTS['belt']}   release to build   [Shift] straight   "
                             f"[R] turn every belt{turned}   drag back = undo   [Esc] cancel")
            else:
                lines.append(f"Build Belt facing {'NESW'[game.build_dir]}   [LMB] click, or hold and drag a path (Shift = straight),"
                             " release to build   [R] rotate  [Esc] cancel")
        elif game.tool:
            if game.tool in ("miner", "wall", "tower"):
                extra = {"miner": "   (miners push numbers out of all four sides)",
                         "tower": "   (ammo goes in through any side; range 10)"}.get(game.tool, "")
                lines.append(f"Build {TOOL_NAMES[game.tool]}   [LMB] place  [X] demolish  [Esc] cancel" + extra)
            else:
                d = "NESW"[game.build_dir]
                lines.append(f"Build {TOOL_NAMES[game.tool]} facing {d}   [R] rotate  [LMB] place  [X] demolish  [Esc] cancel")
        elif game.selected_units:
            n = len(game.selected_units)
            lines.append(f"{n} unit{'s' if n > 1 else ''} selected   [RMB] move to a grid formation   [Shift+click] add   [Esc] deselect")
        elif game.selected_structures:
            n = len(game.selected_structures)
            up = sum(c for c in (game.factory.upgrade_cost(s) for s in game.selected_structures) if c)
            rally = "   [RMB] gather point" if any(isinstance(s, Spawner) for s in game.selected_structures) else ""
            lines.append(f"{n} structures selected   [U] upgrade all for {numbers.fmt(up)}   [H] repair all{rally}"
                         "   [Shift+drag] add   [Esc] deselect")
        else:
            lines.append("[F1] help   [1-9] build  [X] demolish  [R] rotate  [U] upgrade  [Q] pick  drag a box = select  [Space] pause  [ ] speed  [F3] debug")
        tx, ty = game.hover_tile
        s = game.factory.structure_at(tx, ty)
        info = f"tile ({tx}, {ty})"
        dep = game.terrain.deposit_at(tx, ty)
        if dep:
            info += f"   deposit {dep}"
        if s is not None:
            info += f"   {DISPLAY_NAMES.get(s.KIND, s.KIND)}  Lv {s.level}  fed {numbers.fmt(s.invested)}  hp {numbers.fmt(s.hp)}/{numbers.fmt(s.max_hp)}"
            if isinstance(s, Belt):
                info += f"  speed {s.speed * 20:.2f} t/s  items {len(s.items)}  [T] split {'FORCED' if s.split else 'auto'}"
            elif isinstance(s, Miner):
                info += f"  every {s.period / 20:.2f}s"
            elif isinstance(s, MathMachine):
                info += f"  A{list(s.in_a)} B{list(s.in_b)} out {s.out}"
            elif isinstance(s, Tower):
                info += f"  range {s.range}  ammo {list(s.ammo)}" if s.ammo else \
                    f"  range {s.range}  NO AMMO - run a belt or a miner into any side"
            elif isinstance(s, Spawner):
                info += f"  queue {s.queue}  [click] train {s.UNIT} for {s.unit_cost}"
        lines.append(info)
        sel = game.selected
        if sel is not None and sel is not s:
            lines.append(f"selected {DISPLAY_NAMES.get(sel.KIND, sel.KIND)} at ({sel.x}, {sel.y})  Lv {sel.level}"
                         f"  fed {numbers.fmt(sel.invested)}  hp {numbers.fmt(sel.hp)}/{numbers.fmt(sel.max_hp)}")
        return lines

    def _draw_panel(self, game, s):
        """Selected-structure panel: level, invested, next threshold, hp,
        rate, buffers, actions. Every number comes from sim.leveling."""
        pw, ph = 372, 190
        x0, y0 = 8, 8                                   # top left (John)
        self._panel((x0, y0, pw, ph))
        blit = self.screen.blit
        name = DISPLAY_NAMES.get(s.KIND, s.KIND)
        facing = "" if s.KIND in ("miner", "wall", "hub", "tower") else f"  facing {'NESW'[s.direction]}"
        blit(numbers.text(f"{name}  ({s.x}, {s.y}){facing}", 15), (x0 + 10, y0 + 8))
        blit(numbers.text(f"Level {s.level}", 22, (255, 230, 120)), (x0 + 10, y0 + 28))
        nxt = leveling.next_threshold(s.invested)
        if nxt is None:
            nxt_txt = "max level"
        else:
            nxt_txt = f"next at {numbers.fmt(nxt)}  ({numbers.fmt(nxt - s.invested)} to go)"
        blit(numbers.text(f"fed {numbers.fmt(s.invested)}   {nxt_txt}", 14, (200, 220, 200)), (x0 + 10, y0 + 56))
        # hp bar
        bx, by, bw, bh = x0 + 10, y0 + 80, pw - 20, 12
        pygame.draw.rect(self.screen, COLORS["hp_bar_bg"], (bx, by, bw, bh))
        frac = max(0.0, min(1.0, s.hp / s.max_hp)) if s.max_hp else 0
        pygame.draw.rect(self.screen, COLORS["hp_bar"] if frac > 0.5 else (230, 160, 60) if frac > 0.25 else (230, 70, 60),
                         (bx, by, int(bw * frac), bh))
        blit(numbers.text(f"hp {numbers.fmt(s.hp)} / {numbers.fmt(s.max_hp)}", 13), (bx + 4, by - 1))
        # rate line
        if isinstance(s, Belt):
            rate = (f"speed {s.speed * TICK_RATE:.2f} tiles/s   items {len(s.items)}   "
                    f"[T] T-junction {'FORCED' if s.split else 'auto'}")
        elif isinstance(s, Miner):
            rate = f"mines a {s.value} every {s.period} ticks ({s.period / TICK_RATE:.2f} s) out of every side"
        elif isinstance(s, MathMachine):
            rate = f"{s.period} ticks/op   A{list(s.in_a)} B{list(s.in_b)} out {s.out if s.out is not None else '-'}"
        elif isinstance(s, Tower):
            ammo = " ".join(numbers.abbrev(v) for v in list(s.ammo)[:8]) + ("..." if len(s.ammo) > 8 else "")
            rate = f"range {s.range}   fires every {s.period} ticks   ammo {len(s.ammo)}/{s.ammo_max}: {ammo}"
            if not s.ammo:
                rate = f"range {s.range}   NO AMMO: run a belt or a miner into any side"
        elif isinstance(s, Spawner):
            nxt = f"next in {s.timer / TICK_RATE:.1f} s" if s.queue else f"{s.period / TICK_RATE:.0f} s per unit"
            rate = f"[click] or [C] train {s.UNIT} for {s.unit_cost}   queue {s.queue}   {nxt}"
        elif isinstance(s, Hub):
            rate = "everything delivered here is income"
        else:
            rate = "blocks enemies; joins neighbouring walls; the number is its level"
        blit(numbers.text(rate, 13, (200, 220, 200)), (x0 + 10, y0 + 100))
        # actions
        missing = s.max_hp - s.hp
        repair = f"[H] repair {int(missing * REPAIR_COST_PER_HP + 0.999)}" if missing > 0 else "[H] repair (full)"
        up_cost = game.factory.upgrade_cost(s)
        upgrade = f"[U] upgrade to Lv {s.level + 1} for {numbers.fmt(up_cost)}" if up_cost else "[U] max level"
        refund = int(COSTS.get(s.KIND, 0) * 0.5)
        rot = "" if s.KIND in ("miner", "wall", "tower") else "[R] rotate   "
        actions = f"{rot}[X] demolish +{refund}   {repair}" if not isinstance(s, Hub) else "the HQ cannot be moved"
        blit(numbers.text(f"{upgrade}   {actions}", 13, (255, 230, 120)), (x0 + 10, y0 + 124))
        if isinstance(s, Spawner):
            roles = f"alive {game.combat.count_units_of(s)}   [RMB] on the map = gather point (new and idle units)"
        else:
            roles = "sides F/R/B/L: " + " / ".join(str(r) for r in type(s).SIDE_ROLES)
        blit(numbers.text(roles, 12, (170, 190, 170)), (x0 + 10, y0 + 146))
        if ROLE_FEED in type(s).SIDE_ROLES:
            hint = "feed sides level it up too: belt numbers into a yellow side"
        else:
            hint = "no feed sides here: level it up with [U]"
        blit(numbers.text(hint, 12, (170, 190, 170)), (x0 + 10, y0 + 164))

    def _draw_hub_alert(self, game):
        """Pulsing red frame along the screen edges while the hub takes damage."""
        if not game.factory.hub_under_attack():
            return
        w, h = self.screen.get_size()
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 120.0)
        th = 12
        if self._alert_surf is None or self._alert_surf.get_size() != (w, h):
            surf = pygame.Surface((w, h))
            surf.fill((0, 0, 0))
            surf.set_colorkey((0, 0, 0))
            for rect in ((0, 0, w, th), (0, h - th, w, th), (0, 0, th, h), (w - th, 0, th, h)):
                pygame.draw.rect(surf, (255, 40, 40), rect)
            self._alert_surf = surf
        self._alert_surf.set_alpha(int(60 + 170 * pulse))
        self.screen.blit(self._alert_surf, (0, 0))
        txt = numbers.text("HQ UNDER ATTACK", 22, (255, 90, 90))
        self.screen.blit(txt, (w // 2 - txt.get_width() // 2, 46))

    def _draw_group_panel(self, game):
        """Drag-box selection: counts per kind, total upgrade / repair cost."""
        group = game.selected_structures
        pw, ph = 372, 118
        x0, y0 = 8, 8                                   # top left, like the single panel
        self._panel((x0, y0, pw, ph))
        blit = self.screen.blit
        counts = {}
        for s in group:
            counts[s.KIND] = counts.get(s.KIND, 0) + 1
        kinds = ", ".join(f"{DISPLAY_NAMES.get(k, k.capitalize())} x{n}"
                          for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        blit(numbers.text(f"{len(group)} structures selected", 15), (x0 + 10, y0 + 8))
        blit(numbers.text(kinds, 13, (200, 220, 200)), (x0 + 10, y0 + 30))
        levels = [s.level for s in group]
        blit(numbers.text(f"levels {min(levels)} - {max(levels)}", 13, (200, 220, 200)), (x0 + 10, y0 + 50))
        up = sum(c for c in (game.factory.upgrade_cost(s) for s in group) if c)
        missing = sum(max(0, s.max_hp - s.hp) for s in group)
        rep = int(missing * REPAIR_COST_PER_HP + 0.999) if missing else 0
        blit(numbers.text(f"[U] upgrade all for {numbers.fmt(up)}   [H] repair all for {numbers.fmt(rep)}", 13, (255, 230, 120)),
             (x0 + 10, y0 + 74))
        n_sp = sum(1 for s in group if isinstance(s, Spawner))
        rally = f"[C] queue a unit at each of {n_sp} spawner{'s' if n_sp > 1 else ''}   [RMB] gather point   " if n_sp else ""
        blit(numbers.text(f"{rally}[Shift+drag] add more   [Esc] deselect", 12, (170, 190, 170)), (x0 + 10, y0 + 96))

    MINI_W, MINI_H, MINI_TILES = 440, 300, 128      # panel px (2x, John) and tiles shown across

    def _draw_minimap(self, game):
        w, h = self.screen.get_size()
        x0, y0 = w - self.MINI_W - 8, h - self.MINI_H - 8
        self.minimap_rect = pygame.Rect(x0, y0, self.MINI_W, self.MINI_H)
        if game.frame - self._minimap_frame >= 6 or self._minimap is None:
            self._minimap_frame = game.frame
            self._minimap = self._build_minimap(game)
        self.screen.blit(self._minimap, (x0, y0))
        pygame.draw.rect(self.screen, COLORS["panel_border"], (x0, y0, self.MINI_W, self.MINI_H), 1)

    def _build_minimap(self, game):
        surf = pygame.Surface((self.MINI_W, self.MINI_H))
        surf.fill((14, 26, 16))
        cam = game.camera
        scale = self.MINI_W / self.MINI_TILES              # px per tile
        ccx, ccy = cam.x / TILE_SIZE, cam.y / TILE_SIZE     # camera centre in tiles
        tx0 = ccx - self.MINI_TILES / 2
        ty0 = ccy - (self.MINI_H / scale) / 2
        tiles_h = self.MINI_H / scale
        self._mini_origin = (tx0, ty0, scale)

        def to_px(tx, ty):
            return int((tx - tx0) * scale), int((ty - ty0) * scale)

        fill = surf.fill
        f = game.factory
        cx0, cx1 = int(tx0 // CHUNK_SIZE), int((tx0 + self.MINI_TILES) // CHUNK_SIZE) + 1
        cy0, cy1 = int(ty0 // CHUNK_SIZE), int((ty0 + tiles_h) // CHUNK_SIZE) + 1
        d = max(1, int(scale))
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                for s in f.by_chunk.get((cx, cy), ()):
                    px, py = to_px(s.x - s.SIZE // 2, s.y - s.SIZE // 2)
                    size = max(d, int(scale * s.SIZE))
                    fill(COLORS.get(s.KIND, (200, 200, 200)), (px, py, size, size))
        for spec in game.combat.known_nests.values():
            px, py = to_px(spec.tx - 2, spec.ty - 2)
            fill((120, 40, 40), (px, py, max(2, int(scale * 5)), max(2, int(scale * 5))))
        for u in game.combat.units:
            px, py = to_px(u.x, u.y)
            fill((80, 220, 240), (px - 1, py - 1, 2, 2))
        for e in game.combat.enemies:
            px, py = to_px(e.x, e.y)
            fill((255, 60, 60), (px - 1, py - 1, 3, 3))
        # camera view rectangle
        vw, vh = cam.w / cam.zoom / TILE_SIZE, cam.h / cam.zoom / TILE_SIZE
        vx, vy = to_px(ccx - vw / 2, ccy - vh / 2)
        pygame.draw.rect(surf, (200, 210, 200), (vx, vy, max(2, int(vw * scale)), max(2, int(vh * scale))), 1)
        return surf

    def _draw_wave(self, game):
        c = game.combat
        w = self.screen.get_width()
        secs = c.seconds_to_wave()
        urgent = secs <= WAVE_WARNING_S
        text = f"Wave {c.wave.number + 1} in {int(secs // 60)}:{int(secs % 60):02d}"
        if c.enemies:
            text += f"   enemies {len(c.enemies)}"
        if game.paused:
            text += "   PAUSED"
        elif game.speed > 1:
            text += f"   x{game.speed}"
        surf = numbers.text(text, 20, (255, 90, 90) if urgent else (220, 230, 220))
        self._panel((w // 2 - surf.get_width() // 2 - 10, 8, surf.get_width() + 20, 32))
        self.screen.blit(surf, (w // 2 - surf.get_width() // 2, 14))

    HELP = [
        "1-6 belt / miner / adder / subtract / multiply / divide     7 wall   8 tower   9 0 - spawners     X demolish tool",
        "LMB place; belts: hold and drag = preview, release to build; Shift = straight run + square corner; R while",
        "dragging turns every belt (twice = the line runs backwards); drag back to undo.   R rotate   Q pick tool",
        "Drag off the MIDDLE of a line to branch it (T-junction); from its END the last belt turns; backwards reverses.",
        "T on a belt = forced T-junction: it splits into every side belt pointing away, even one with its own feed.",
        "X = demolish tool: click or drag over buildings (50% refund), X or Esc to stop.   Del = remove the hovered one",
        "click = select (panel on the right); drag a box = select many (U upgrades / H repairs them all)   RMB = cancel",
        "wheel zoom   MMB drag / WASD pan (Shift fast)   Space pause   [ ] sim speed x1 x2 x4   F3 debug   F11 fullscreen",
        "Belts: items enter from behind or the sides; a belt pointing INTO another belt's front FEEDS it (levels it up).",
        "Machines: every side but the front is an input (left = A, right = B, back = the emptier one); output in front.",
        "HQ: deliver from any side = income.  Feed sides (yellow) level belts/walls/spawners; U levels anything.",
        "Towers (range 10): run a belt or put a miner beside one, any side; it fires those numbers. Red frame = no ammo.",
        "Spawners: click one (or press C with one or a boxed group selected) to train a unit (costs balance); new units",
        "walk to its gather point beside the HQ. RMB with spawners selected = gather point for units trained from then on.",
        "Units: click or drag a box to select (Shift adds), RMB moves them in a grid. Attackers each take their own tile.",
        "Targets: deliver the shown amount of that number for the bonus; the slot then levels up (bigger number and amount).",
        "Waves come from the red edge arrow. HQ destroyed = game over.",
        "An enemy camp always sits about 100 tiles from the HQ (dark-red edge arrow, minimap): it is quiet until you",
        "build within 48 tiles of it, then it raids; kill its core for a 500 bounty. More camps lie further out.",
        "Enemies shoot from 3-5 tiles and melee up close; each level costs 25% more than the last, no cap.",
        "F1 closes this help.",
    ]

    def _draw_help(self):
        w, h = self.screen.get_size()
        lines = [numbers.text(t, 15) for t in self.HELP]
        pw = max(s.get_width() for s in lines) + 40
        ph = len(lines) * 22 + 40
        x0, y0 = (w - pw) // 2, (h - ph) // 2
        self._panel((x0, y0, pw, ph))
        for i, s in enumerate(lines):
            self.screen.blit(s, (x0 + 20, y0 + 20 + i * 22))

    def _draw_game_over(self, game):
        w, h = self.screen.get_size()
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((40, 0, 0, 170))
        self.screen.blit(dim, (0, 0))
        title = numbers.text("HQ DESTROYED", 56, (255, 80, 80))
        self.screen.blit(title, (w // 2 - title.get_width() // 2, h // 2 - 80))
        c = game.combat
        line = numbers.text(f"survived {c.wave.number} waves, {c.stats['kills']} kills, tick {game.factory.tick_count}", 20)
        self.screen.blit(line, (w // 2 - line.get_width() // 2, h // 2 - 10))
        keys = numbers.text("[L] load last save      [Esc] back to menu", 24, (255, 230, 120))
        self.screen.blit(keys, (w // 2 - keys.get_width() // 2, h // 2 + 40))

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
