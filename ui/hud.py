"""HUD: balance, targets, build toolbar with hotkeys, hover info, messages."""
import math

import pygame

from settings import COLORS, COSTS, REPAIR_COST_PER_HP, TICK_RATE, TILE_SIZE, CHUNK_SIZE, WAVE_WARNING_S
from render import numbers
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
BTN = 64
GAP = 6


class Hud:
    def __init__(self, screen):
        self.screen = screen
        self.messages = []          # [text, ttl]
        self.toolbar_rect = pygame.Rect(0, 0, 0, 0)
        self._minimap = None        # cached surface, rebuilt every few frames
        self._minimap_frame = -100
        self._alert_surf = None     # red screen frame (hub under attack), cached per size
        self.hub_button = pygame.Rect(8, 72, 110, 26)

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
        return self.toolbar_rect.collidepoint(pos) or self.hub_button.collidepoint(pos)

    def click(self, pos, game):
        """Toolbar / hub button hit test; returns True when the click was consumed."""
        if self.hub_button.collidepoint(pos):
            game.go_home()
            return True
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
        # hub button
        hb = self.hub_button
        pygame.draw.rect(screen, COLORS["hub"], hb, border_radius=4)
        pygame.draw.rect(screen, COLORS["panel_border"], hb, 1, border_radius=4)
        label = numbers.text("HUB  [Home]", 14)
        screen.blit(label, (hb.centerx - label.get_width() // 2, hb.centery - label.get_height() // 2))
        # targets
        self._panel((w - 228, 8, 220, 24 + 22 * len(f.targets)))
        screen.blit(numbers.text("Targets  (deliver exactly)", 14, (170, 190, 170)), (w - 220, 12))
        for i, t in enumerate(f.targets):
            y = 32 + i * 22
            screen.blit(numbers.text(numbers.fmt(t.value), 18, (255, 230, 120)), (w - 220, y))
            screen.blit(numbers.text(f"+{numbers.fmt(t.reward)}", 16, (140, 255, 140)), (w - 120, y + 1))
        self._draw_wave(game)
        self._draw_minimap(game)
        self._draw_toolbar(game)
        self._draw_hover(game)
        if game.selected is not None:
            self._draw_panel(game, game.selected)
        elif game.selected_structures:
            self._draw_group_panel(game)
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

    def _draw_hover(self, game):
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
            lines.append(f"{n} structures selected   [U] upgrade all for {numbers.fmt(up)}   [H] repair all   [Shift+drag] add   [Esc] deselect")
        else:
            lines.append("[F1] help   [1-9] build  [X] demolish  [R] rotate  [U] upgrade  [Q] pick  drag a box = select  [Space] pause  [ ] speed  [F3] debug")
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
                info += f"  range {s.range}  ammo {list(s.ammo)}" if s.ammo else \
                    f"  range {s.range}  NO AMMO - run a belt or a miner into any side"
            elif isinstance(s, Spawner):
                info += f"  queue {s.queue}  [click] train {s.UNIT} for {s.unit_cost}"
        lines.append(info)
        sel = game.selected
        if sel is not None and sel is not s:
            lines.append(f"selected {TOOL_NAMES.get(sel.KIND, sel.KIND)} at ({sel.x}, {sel.y})  Lv {sel.level}"
                         f"  fed {numbers.fmt(sel.invested)}  hp {numbers.fmt(sel.hp)}/{numbers.fmt(sel.max_hp)}")
        y = self.toolbar_rect.top - 8 - 18 * len(lines)
        for line in lines:
            self.screen.blit(numbers.text(line, 14), (12, y))
            y += 18

    def _draw_panel(self, game, s):
        """Selected-structure panel: level, invested, next threshold, hp,
        rate, buffers, actions. Every number comes from sim.leveling."""
        w, h = self.screen.get_size()
        pw, ph = 372, 190
        x0, y0 = w - pw - 8, 8 + 24 + 22 * len(game.factory.targets) + 10
        self._panel((x0, y0, pw, ph))
        blit = self.screen.blit
        name = TOOL_NAMES.get(s.KIND, s.KIND)
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
            rate = f"speed {s.speed:.4f} tiles/tick  ({s.speed * TICK_RATE:.2f} tiles/s)   items {len(s.items)}"
        elif isinstance(s, Miner):
            rate = f"mines a {s.value} every {s.period} ticks ({s.period / TICK_RATE:.2f} s) out of every side"
        elif isinstance(s, MathMachine):
            rate = f"{s.period} ticks/op   A{list(s.in_a)} B{list(s.in_b)} out {s.out if s.out is not None else '-'}"
        elif isinstance(s, Tower):
            ammo = " ".join(numbers.abbrev(v) for v in list(s.ammo)[:8]) + ("..." if len(s.ammo) > 8 else "")
            rate = f"range {s.range}   fires every {s.period} ticks   ammo {len(s.ammo)}: {ammo}"
            if not s.ammo:
                rate = f"range {s.range}   NO AMMO: run a belt or a miner into any side"
        elif isinstance(s, Spawner):
            nxt = f"next in {s.timer / TICK_RATE:.1f} s" if s.queue else f"{s.period / TICK_RATE:.0f} s per unit"
            rate = f"[click] train {s.UNIT} for {s.unit_cost}   queue {s.queue}   {nxt}"
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
        actions = f"{rot}[X] demolish +{refund}   {repair}" if not isinstance(s, Hub) else "the hub cannot be moved"
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
        txt = numbers.text("HUB UNDER ATTACK", 22, (255, 90, 90))
        self.screen.blit(txt, (w // 2 - txt.get_width() // 2, 46))

    def _draw_group_panel(self, game):
        """Drag-box selection: counts per kind, total upgrade / repair cost."""
        group = game.selected_structures
        w, h = self.screen.get_size()
        pw, ph = 372, 118
        x0, y0 = w - pw - 8, 8 + 24 + 22 * len(game.factory.targets) + 10
        self._panel((x0, y0, pw, ph))
        blit = self.screen.blit
        counts = {}
        for s in group:
            counts[s.KIND] = counts.get(s.KIND, 0) + 1
        kinds = ", ".join(f"{TOOL_NAMES.get(k, k.capitalize())} x{n}"
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
        blit(numbers.text("[Shift+drag] add more   [Esc] deselect", 12, (170, 190, 170)), (x0 + 10, y0 + 96))

    MINI_W, MINI_H, MINI_TILES = 220, 150, 96       # panel px and tiles shown across

    def _draw_minimap(self, game):
        w, h = self.screen.get_size()
        x0, y0 = w - self.MINI_W - 8, h - self.MINI_H - 8
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
        "X = demolish tool: click or drag over buildings (50% refund), X or Esc to stop.   Del = remove the hovered one",
        "click = select (panel on the right); drag a box = select many (U upgrades / H repairs them all)   RMB = cancel",
        "wheel zoom   MMB drag / WASD pan (Shift fast)   Space pause   [ ] sim speed x1 x2 x4   F3 debug   F11 fullscreen",
        "Belts: items enter from behind or the sides; a belt pointing INTO another belt's front FEEDS it (levels it up).",
        "Machines: every side but the front is an input (left = A, right = B, back = the emptier one); output in front.",
        "Hub: deliver from any side = income.  Feed sides (yellow) level belts/walls/spawners; U levels anything.",
        "Towers (range 10): run a belt or put a miner beside one, any side; it fires those numbers. Red frame = no ammo.",
        "Spawners: click one to train a unit (costs balance); units walk to its gather point beside the hub.",
        "Units: click or drag a box to select (Shift adds), RMB moves them in a grid; RMB on a selected spawner = gather point.",
        "Targets pay a bonus for delivering the exact number. Waves come from the red edge arrow. Hub dead = game over.",
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
        title = numbers.text("HUB DESTROYED", 56, (255, 80, 80))
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
