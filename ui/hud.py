"""HUD: balance, targets, build toolbar with hotkeys, hover info, messages."""
import math

import pygame

from settings import (COLORS, COSTS, REPAIR_COST_PER_HP, TICK_RATE, TILE_SIZE, CHUNK_SIZE, WAVE_WARNING_S,
                      REPAIR_UNIT_CAPACITY, REPAIR_UNIT_SEARCH)
from render import numbers
from render import combat as rcombat
from sim import leveling
from ui import prefs
from sim.structures import KINDS, Belt, Bridge, Miner, MathMachine, Tower, Spawner, Hub, ROLE_FEED

# toolbar order and hotkeys (Phase 5 appends spawners)
TOOLS = [("belt", "1"), ("bridge", "B"), ("miner", "2"), ("adder", "3"), ("subtractor", "4"),
         ("multiplier", "5"), ("divider", "6"), ("wall", "7"), ("tower", "8"),
         ("spawner_ranged", "9"), ("spawner_melee", "0"), ("spawner_heavy", "-"), ("spawner_repair", "="),
         ("demolish", "X")]                 # demolish is a tool too: click or drag to remove
TOOL_NAMES = {"belt": "Belt", "bridge": "Bridge", "miner": "Miner", "adder": "Adder", "subtractor": "Subtract",
              "multiplier": "Multiply", "divider": "Divide", "wall": "Wall", "tower": "Tower",
              "spawner_ranged": "Ranged", "spawner_melee": "Melee", "spawner_heavy": "Heavy",
              "spawner_repair": "Repair", "demolish": "Demolish"}
_KEYCODES = {"1": pygame.K_1, "2": pygame.K_2, "3": pygame.K_3, "4": pygame.K_4, "5": pygame.K_5,
             "6": pygame.K_6, "7": pygame.K_7, "8": pygame.K_8, "9": pygame.K_9, "0": pygame.K_0,
             "-": pygame.K_MINUS, "=": pygame.K_EQUALS, "X": pygame.K_x, "B": pygame.K_b}
HOTKEYS = {_KEYCODES[k]: kind for kind, k in TOOLS}
DISPLAY_NAMES = dict(TOOL_NAMES, hub="HQ")     # what the player calls each kind
BTN = 60                                        # button size; shrinks so every button fits left of the minimap
GAP = 3


def unit_cost_summary(spawners):
    """What one [C] press costs at these spawners: the total, then the price
    per unit kind, e.g. "250 (Ranged 50 x2, Heavy 150)"."""
    total = sum(s.unit_cost for s in spawners)
    counts = {}
    for s in spawners:
        counts[s.KIND] = counts.get(s.KIND, 0) + 1
    parts = []
    for kind, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        cost = next(s.unit_cost for s in spawners if s.KIND == kind)
        parts.append(f"{TOOL_NAMES.get(kind, kind)} {cost}" + (f" x{n}" if n > 1 else ""))
    return f"{numbers.fmt(total)} ({', '.join(parts)})"


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
        self.btn = BTN              # toolbar button size in use (buttons())
        self.panel_rect = None      # the structure / group panel this frame (None = none shown)
        self.wave_rect = pygame.Rect(0, 0, 0, 0)
        self.portrait = False       # h > w (a rotated phone): panels stack, the toolbar wraps, the minimap sits above it
        self.minimap_hidden = False # a click on the minimap folds it into a "Map" button (config "minimap")
        self.overlay_top = None     # top of the Android button rows above the toolbar (mobile touch.layout sets it)
        self.column_bottom = 0      # bottom of the right column (balance / targets / HQ button / hints)
        self.content_bottom = 0     # bottom of the column and the structure panel (portrait: the rest goes under)

    def message(self, text, ttl=2.5):
        self.messages = [m for m in self.messages if m[0] != text]
        self.messages.append([text, ttl])

    def update(self, dt):
        for m in self.messages:
            m[1] -= dt
        self.messages = [m for m in self.messages if m[1] > 0][-4:]

    # ---- scale (menu Settings, ui/prefs.py) ----------------------------------

    @staticmethod
    def px(v):
        """Layout pixels scaled by the text size."""
        return prefs.tpx(v)

    @staticmethod
    def text(s, size, color=COLORS["text"]):
        """Text at `size` px times the text size (panels, hints, messages;
        the toolbar scales with the button size instead)."""
        return numbers.text(s, prefs.tsize(size), color)

    # ---- layout --------------------------------------------------------------

    def buttons(self):
        """Toolbar rects: one row centred left of the minimap, or two rows of
        seven across the width on a rotated phone (portrait)."""
        w, h = self.screen.get_size()
        n = len(TOOLS)
        portrait = h > w
        per_row = (n + 1) // 2 if portrait else n
        rows = -(-n // per_row)
        avail = (w - 16) if portrait else (w - self.MINI_W - 16)   # landscape: the space left of the minimap
        want = int(round(BTN * prefs.button_scale))   # menu Settings "Button size"
        btn = max(40, min(want, (avail - 16 - (per_row - 1) * GAP) // per_row))
        self.btn = btn
        total = per_row * btn + (per_row - 1) * GAP
        x0 = max(8, (avail - total) // 2)
        height = rows * btn + (rows - 1) * GAP
        y0 = h - height - 10
        out = []
        for i, (kind, key) in enumerate(TOOLS):
            r, c = divmod(i, per_row)
            out.append((pygame.Rect(x0 + c * (btn + GAP), y0 + r * (btn + GAP), btn, btn), kind, key))
        self.toolbar_rect = pygame.Rect(x0 - 8, y0 - 8, total + 16, height + 16)
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
        if self.minimap_rect.collidepoint(pos):       # John: a click folds the minimap into a Map button, and back
            self.minimap_hidden = not self.minimap_hidden
            return True
        for rect, kind, _ in self.buttons():
            if rect.collidepoint(pos):
                game.set_tool(None if game.tool == kind else kind)
                return True
        return self.over_ui(pos)

    def minimap_recentre(self, pos, game):
        """Right click on the minimap: look at that spot (a left click folds it)."""
        if self.minimap_hidden or self._mini_origin is None or not self.minimap_rect.collidepoint(pos):
            return False
        tx0, ty0, scale = self._mini_origin
        game.camera.x = (tx0 + (pos[0] - self.minimap_rect.x) / scale) * TILE_SIZE
        game.camera.y = (ty0 + (pos[1] - self.minimap_rect.y) / scale) * TILE_SIZE
        return True

    # ---- drawing -------------------------------------------------------------

    def draw(self, game):
        screen = self.screen
        f = game.factory
        w, h = screen.get_size()
        p, T = self.px, self.text                     # layout px / text scaled by the text size
        self.portrait = h > w
        col = min(p(self.COL_W), w - 16)
        x = w - col - 8
        # right column, top to bottom: balance (centred), targets, HQ button, hints
        bal = pygame.Rect(x, 8, col, p(58))
        self._panel(bal)
        t = T("Balance", 14, (170, 190, 170))
        screen.blit(t, (bal.centerx - t.get_width() // 2, bal.y + p(4)))
        t = T(numbers.fmt(f.balance), 28)
        screen.blit(t, (bal.centerx - t.get_width() // 2, bal.y + p(22)))
        row = p(22)
        tg = pygame.Rect(x, bal.bottom + 6, col, p(24) + row * len(f.targets))
        self._panel(tg)
        screen.blit(T("Targets   (deliver amount x number)", 14, (170, 190, 170)), (tg.x + 8, tg.y + p(4)))
        for i, tgt in enumerate(f.targets):
            y = tg.y + p(24) + i * row
            xx = tg.x + 8
            screen.blit(T(f"{tgt.amount} x", 15, (200, 220, 200)), (xx, y + p(2)))
            screen.blit(T(numbers.fmt(tgt.value), 18, (255, 230, 120)), (xx + p(52), y))
            screen.blit(T(f"{tgt.delivered}/{tgt.amount}", 14, (200, 220, 200)), (xx + p(140), y + p(3)))
            screen.blit(T(f"Lv{tgt.level}", 13, (170, 190, 170)), (xx + p(208), y + p(3)))
            screen.blit(T(f"+{numbers.fmt(tgt.reward)}", 16, (140, 255, 140)), (xx + p(258), y + p(1)))
        self.rects = {"balance": bal, "targets": tg}
        hb = self.hub_button
        hb.update(x + col // 2 - p(60), tg.bottom + 6, p(120), p(26))
        pygame.draw.rect(screen, COLORS["hub"], hb, border_radius=4)
        pygame.draw.rect(screen, COLORS["panel_border"], hb, 1, border_radius=4)
        label = T("HQ  [Home]", 14)
        screen.blit(label, (hb.centerx - label.get_width() // 2, hb.centery - label.get_height() // 2))
        if getattr(game, "show_hints", True):
            self._draw_hints(game, x, hb.bottom + 6, col)
        else:
            self.hints_rect = pygame.Rect(0, 0, 0, 0)
        self.column_bottom = max(hb.bottom, self.hints_rect.bottom)
        self._draw_toolbar(game)                      # first: in portrait the minimap sits above it
        self._draw_minimap(game)
        self.panel_rect = None
        if game.selected is not None:
            self._draw_panel(game, game.selected)
        elif game.selected_structures:
            self._draw_group_panel(game)
        self.content_bottom = max(self.column_bottom, self.panel_rect.bottom if self.panel_rect else 0)
        self._draw_wave(game)       # after the panel: big text makes the panel wide, the timer moves aside
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
        bs = self.btn / BTN                           # the text inside scales with the button
        q = lambda v: int(round(v * bs))              # (14 buttons at 1280 wide: a touch smaller)
        name_px = max(9, q(12))
        for rect, kind, key in buttons:
            cost = COSTS.get(kind, 0)
            color = COLORS.get(kind, (120, 120, 120))
            if balance < cost:
                color = tuple(int(c * 0.45) for c in color)
            # a keycap on top (the hotkey centred in the kind's colour), the name and the
            # cost centred under it, nothing overlapping (John, phone round 2: centred text)
            icon = pygame.Rect(rect.x + q(4), rect.y + q(4), rect.width - q(8), q(24))
            pygame.draw.rect(screen, color, icon, border_radius=4)
            if kind == "spawner_repair":                # the repair cross, like its units
                cx, cy = icon.center
                arm, th = max(3, icon.height // 3), max(2, icon.height // 6)
                pygame.draw.rect(screen, (255, 255, 255), (cx - arm, cy - th // 2, 2 * arm, th))
                pygame.draw.rect(screen, (255, 255, 255), (cx - th // 2, cy - arm, th, 2 * arm))
            k = numbers.text(key, max(9, q(13)))
            screen.blit(k, (icon.centerx - k.get_width() // 2, icon.centery - k.get_height() // 2))
            if game.tool == kind:
                pygame.draw.rect(screen, (255, 255, 120), rect, 2, border_radius=4)
            else:
                pygame.draw.rect(screen, COLORS["panel_border"], rect, 1, border_radius=4)
            name = numbers.text(TOOL_NAMES[kind], name_px)
            screen.blit(name, (rect.centerx - name.get_width() // 2, icon.bottom + q(1)))
            if kind == "demolish":
                c = numbers.text("50% back", max(8, q(11)), (255, 230, 120))
            else:
                c = numbers.text(str(cost), max(9, q(12)), (255, 230, 120) if balance >= cost else (255, 110, 110))
            screen.blit(c, (rect.centerx - c.get_width() // 2, rect.bottom - q(16)))

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
        """The info hints (controls, hovered tile, selection) in a panel that
        stops short of the minimap."""
        p = self.px
        size, lh = prefs.tsize(12), p(16)
        lines = []
        for text in self._hint_lines(game):
            lines.extend(self._wrap(text, size, col - 16))
        h = self.screen.get_height()
        room = (h // 2 if self.portrait else h - self.MINI_H - 16) - y - p(12)
        lines = lines[:room // lh] if room >= lh else []
        if not lines:                                   # big text on a small window: no room, no panel
            self.hints_rect = pygame.Rect(0, 0, 0, 0)
            return
        self.hints_rect = pygame.Rect(x, y, col, p(12) + lh * len(lines))
        self._panel(self.hints_rect)
        for i, line in enumerate(lines):
            self.screen.blit(numbers.text(line, size), (x + 8, y + p(6) + i * lh))

    def _hint_lines(self, game):
        lines = []
        if game.tool == "demolish":
            if game.demolish_start is not None:
                n = len(game.demolish_targets())
                lines.append(f"Demolish box: {n} structure{'s' if n != 1 else ''} inside   release to remove them (50% refund)   "
                             "[Esc] or [RMB] cancel")
            else:
                lines.append("Demolish   [LMB] click a building, or drag a box over many, to remove them (50% refund)   "
                             "[X] or [Esc] to stop")
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
            if game.tool in ("miner", "wall", "tower", "bridge"):
                extra = {"miner": "   (miners push numbers out of all four sides)",
                         "tower": "   (ammo goes in through any side; range 10)",
                         "bridge": "   (two lines cross without mixing: in a side, out the opposite; drops onto a belt)"}.get(game.tool, "")
                lines.append(f"Build {TOOL_NAMES[game.tool]}   [LMB] place  [X] demolish  [Esc] cancel" + extra)
            else:
                d = "NESW"[game.build_dir]
                extra = ""
                if game.tool == "spawner_repair":
                    extra = (f"   (trains repair units: they fix damaged buildings and heal units next to them, "
                             f"{REPAIR_UNIT_CAPACITY} numbers per load, refilled at the HQ)")
                lines.append(f"Build {TOOL_NAMES[game.tool]} facing {d}   [R] rotate  [LMB] place  [X] demolish  [Esc] cancel" + extra)
        elif game.selected_units:
            live = [u for u in game.selected_units if not u.dead]
            n = len(live)
            form = game.combat.group_formation(live)
            patrol = "   patrolling" if any(u.patrol is not None for u in live) else ""
            lines.append(f"{n} unit{'s' if n > 1 else ''} selected{patrol}   formation: {form.upper()}   "
                         f"[wheel] next formation (Ctrl+wheel zooms)   [RMB] move   "
                         f"[middle click] patrol between here and their rally point   [Shift+click] add   [Esc] deselect")
            repairs = [u for u in live if u.heal is not None]
            if repairs:
                loads = ", ".join(f"{u.carry}/{REPAIR_UNIT_CAPACITY}" for u in repairs[:6])
                where = f"within {REPAIR_UNIT_SEARCH} tiles" if REPAIR_UNIT_SEARCH else "anywhere"
                lines.append(f"repair units carry {loads}: they fix damaged buildings and heal units {where}, "
                             f"nearest first, and fetch more numbers from the HQ when empty")
        elif game.selected_structures:
            n = len(game.selected_structures)
            up = sum(c for c in (game.factory.upgrade_cost(s) for s in game.selected_structures) if c)
            spawners = [s for s in game.selected_structures if isinstance(s, Spawner)]
            rally = f"   [C] train a unit at each spawner for {unit_cost_summary(spawners)}   [RMB] gather point" if spawners else ""
            lines.append(f"{n} structures selected   [U] upgrade all for {numbers.fmt(up)}   [H] repair all   "
                         f"[Del] demolish all{rally}   [Shift+drag] add   [Esc] deselect")
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
            elif isinstance(s, Bridge):
                info += f"  crossing: in one side, out the opposite  items {s.count()}"
            elif isinstance(s, Miner):
                info += f"  every {s.period / 20:.2f}s"
            elif isinstance(s, MathMachine):
                info += f"  A{list(s.in_a)} B{list(s.in_b)} out {s.out}"
            elif isinstance(s, Tower):
                info += f"  range {s.range}  ammo {list(s.ammo)}" if s.ammo else \
                    f"  range {s.range}  NO AMMO - run a belt or a miner into any side"
            elif isinstance(s, Spawner):
                info += f"  queue {s.queue}  [click] or [C] train a {TOOL_NAMES[s.KIND]} unit for {s.unit_cost}"
        lines.append(info)
        sel = game.selected
        if sel is not None and sel is not s:
            lines.append(f"selected {DISPLAY_NAMES.get(sel.KIND, sel.KIND)} at ({sel.x}, {sel.y})  Lv {sel.level}"
                         f"  fed {numbers.fmt(sel.invested)}  hp {numbers.fmt(sel.hp)}/{numbers.fmt(sel.max_hp)}")
        return lines

    def _draw_panel(self, game, s):
        """Selected-structure panel: level, invested, next threshold, hp,
        rate, buffers, actions. Every number comes from sim.leveling."""
        rows = []                                       # (gap, text, size, color) | ("bar", height): see _draw_rows
        name = DISPLAY_NAMES.get(s.KIND, s.KIND)
        facing = "" if s.KIND in ("miner", "wall", "hub", "tower", "bridge") else f"  facing {'NESW'[s.direction]}"
        rows.append((0, f"{name}  ({s.x}, {s.y}){facing}", 15, COLORS["text"]))
        rows.append((2, f"Level {s.level}", 22, (255, 230, 120)))
        nxt = leveling.next_threshold(s.invested)
        if nxt is None:
            nxt_txt = "max level"
        else:
            nxt_txt = f"next at {numbers.fmt(nxt)}  ({numbers.fmt(nxt - s.invested)} to go)"
        rows.append((2, f"fed {numbers.fmt(s.invested)}   {nxt_txt}", 14, (200, 220, 200)))
        rows.append(("bar", 12))                        # hp bar
        # rate line
        if isinstance(s, Belt):
            rate = (f"speed {s.speed * TICK_RATE:.2f} tiles/s   items {len(s.items)}   "
                    f"[T] T-junction {'FORCED' if s.split else 'auto'}")
        elif isinstance(s, Bridge):
            rate = (f"two lines cross here: in through a side, out the opposite side, never mixing   "
                    f"items {s.count()}   {s.speed * TICK_RATE:.2f} tiles/s")
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
            rate = (f"[click] or [C] train a {TOOL_NAMES[s.KIND]} unit: {s.unit_cost} each   "
                    f"queue {s.queue} ({s.queue * s.unit_cost} paid)   {nxt}")
            if s.UNIT == "repair":
                rate += f"   (fixes buildings, heals units; {REPAIR_UNIT_CAPACITY} numbers per load from the HQ)"
        elif isinstance(s, Hub):
            rate = "everything delivered here is income"
        else:
            rate = "blocks enemies; joins neighbouring walls; the number is its level"
        rows.append((6, rate, 13, (200, 220, 200)))
        # actions
        missing = s.max_hp - s.hp
        repair = f"[H] repair {int(missing * REPAIR_COST_PER_HP + 0.999)}" if missing > 0 else "[H] repair (full)"
        up_cost = game.factory.upgrade_cost(s)
        upgrade = f"[U] upgrade to Lv {s.level + 1} for {numbers.fmt(up_cost)}" if up_cost else "[U] max level"
        refund = int(COSTS.get(s.KIND, 0) * 0.5)
        rot = "" if s.KIND in ("miner", "wall", "tower", "bridge") else "[R] rotate   "
        actions = f"{rot}[Del] demolish +{refund}   {repair}" if not isinstance(s, Hub) else "the HQ cannot be moved"
        rows.append((6, f"{upgrade}   {actions}", 13, (255, 230, 120)))
        if isinstance(s, Spawner):
            roles = f"alive {game.combat.count_units_of(s)}   [RMB] on the map = gather point (new and idle units)"
        else:
            roles = "sides F/R/B/L: " + " / ".join(str(r) for r in type(s).SIDE_ROLES)
        rows.append((6, roles, 12, (170, 190, 170)))
        if ROLE_FEED in type(s).SIDE_ROLES:
            hint = "feed sides level it up too: belt numbers into a yellow side"
        else:
            hint = "no feed sides here: level it up with [U]"
        rows.append((2, hint, 12, (170, 190, 170)))
        bar = self._draw_rows(rows)
        if bar is not None:                             # hp bar under the fed line
            bx, by, bw, bh = bar
            pygame.draw.rect(self.screen, COLORS["hp_bar_bg"], (bx, by, bw, bh))
            frac = max(0.0, min(1.0, s.hp / s.max_hp)) if s.max_hp else 0
            pygame.draw.rect(self.screen, COLORS["hp_bar"] if frac > 0.5 else (230, 160, 60) if frac > 0.25 else (230, 70, 60),
                             (bx, by, int(bw * frac), bh))
            self.screen.blit(self.text(f"hp {numbers.fmt(s.hp)} / {numbers.fmt(s.max_hp)}", 13), (bx + 4, by - 1))

    def _draw_rows(self, rows):
        """Draw a panel of rows: top left in landscape, under the right column
        on a rotated phone. A (gap, text, size, color) row is wrapped when it
        is wider than the room (the column's left edge / the screen); a
        ("bar", height) row reserves a strip and its rect (x, y, w, h) is
        returned. Sets panel_rect."""
        p = self.px
        w = self.screen.get_width()
        x0 = 8
        y0 = self.column_bottom + 6 if self.portrait else 8
        max_w = (w - 16) if self.portrait else max(p(372), self.rects["balance"].left - 16)
        pad, edge = 10, p(8)
        items, bar = [], None
        y, widest = edge, 0
        for row in rows:
            if row[0] == "bar":
                y += p(6)
                bar = (y, p(row[1]))
                y += p(row[1]) + p(2)
                continue
            gap, text, size, color = row
            y += p(gap)
            px_size = prefs.tsize(size)
            surf = numbers.text(text, px_size, color)
            lines = [surf] if surf.get_width() <= max_w - 2 * pad else \
                [numbers.text(line, px_size, color) for line in self._wrap(text, px_size, max_w - 2 * pad)]
            for line in lines:
                items.append((y, line))
                widest = max(widest, line.get_width())
                y += line.get_height() - 2                # the outline adds 2 px: keep the lines tight
        pw = min(max_w, max(p(372), widest + 2 * pad))
        self.panel_rect = pygame.Rect(x0, y0, pw, y + edge)
        self._panel(self.panel_rect)
        for dy, surf in items:
            self.screen.blit(surf, (x0 + pad, y0 + dy))
        return (x0 + pad, y0 + bar[0], pw - 2 * pad, bar[1]) if bar is not None else None

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
        txt = self.text("HQ UNDER ATTACK", 22, (255, 90, 90))
        y = self.content_bottom + self.px(12) if self.portrait else self.px(46)
        self.screen.blit(txt, (w // 2 - txt.get_width() // 2, y))

    def _draw_group_panel(self, game):
        """Drag-box selection: counts per kind, total upgrade / repair /
        demolish figures, and what [C] would cost at the spawners inside."""
        group = game.selected_structures
        rows = []                                       # (gap, text, size, color): see _draw_rows
        counts = {}
        for s in group:
            counts[s.KIND] = counts.get(s.KIND, 0) + 1
        kinds = ", ".join(f"{DISPLAY_NAMES.get(k, k.capitalize())} x{n}"
                          for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        rows.append((0, f"{len(group)} structures selected", 15, COLORS["text"]))
        rows.append((4, kinds, 13, (200, 220, 200)))
        levels = [s.level for s in group]
        rows.append((4, f"levels {min(levels)} - {max(levels)}", 13, (200, 220, 200)))
        up = sum(c for c in (game.factory.upgrade_cost(s) for s in group) if c)
        missing = sum(max(0, s.max_hp - s.hp) for s in group)
        rep = int(missing * REPAIR_COST_PER_HP + 0.999) if missing else 0
        refund = sum(int(COSTS.get(s.KIND, 0) * 0.5) for s in group)
        rows.append((8, f"[U] upgrade all for {numbers.fmt(up)}   [H] repair all for {numbers.fmt(rep)}   "
                        f"[Del] demolish all +{numbers.fmt(refund)}", 13, (255, 230, 120)))
        spawners = [s for s in group if isinstance(s, Spawner)]
        if spawners:
            n_sp = len(spawners)
            rows.append((6, f"[C] train a unit at each of {n_sp} spawner{'s' if n_sp > 1 else ''} for "
                            f"{unit_cost_summary(spawners)}   [RMB] gather point", 12, (255, 230, 120)))
        rows.append((6, "[Shift+drag] add more   [Esc] deselect", 12, (170, 190, 170)))
        self._draw_rows(rows)

    MINI_W, MINI_H, MINI_TILES = 440, 300, 128      # panel px (2x, John) and tiles shown across

    def _draw_minimap(self, game):
        """Bottom right; on a rotated phone above the toolbar and the Android
        button rows. Folded (minimap_hidden) it is a "Map" button in the
        corner the map would fill."""
        w, h = self.screen.get_size()
        mw, mh = min(self.MINI_W, w - 16), self.MINI_H
        if self.portrait:
            above = self.toolbar_rect.top if self.overlay_top is None else min(self.toolbar_rect.top, self.overlay_top)
            x0, y0 = w - mw - 8, above - 8 - mh
        else:
            x0, y0 = w - mw - 8, h - mh - 8
        if self.minimap_hidden:
            bw, bh = self.px(120), self.px(26)
            self.minimap_rect = pygame.Rect(x0 + mw - bw, y0 + mh - bh, bw, bh)
            self._minimap = None
            pygame.draw.rect(self.screen, COLORS["panel"], self.minimap_rect, border_radius=4)
            pygame.draw.rect(self.screen, COLORS["panel_border"], self.minimap_rect, 1, border_radius=4)
            label = self.text("Map", 14)
            self.screen.blit(label, (self.minimap_rect.centerx - label.get_width() // 2,
                                     self.minimap_rect.centery - label.get_height() // 2))
            return
        self.minimap_rect = pygame.Rect(x0, y0, mw, mh)
        if game.frame - self._minimap_frame >= 6 or self._minimap is None or self._minimap.get_size() != (mw, mh):
            self._minimap_frame = game.frame
            self._minimap = self._build_minimap(game, mw, mh)
        self.screen.blit(self._minimap, (x0, y0))
        pygame.draw.rect(self.screen, COLORS["panel_border"], (x0, y0, mw, mh), 1)

    def _build_minimap(self, game, mw, mh):
        surf = pygame.Surface((mw, mh))
        surf.fill((14, 26, 16))
        cam = game.camera
        scale = mw / self.MINI_TILES                        # px per tile
        ccx, ccy = cam.x / TILE_SIZE, cam.y / TILE_SIZE     # camera centre in tiles
        tx0 = ccx - self.MINI_TILES / 2
        ty0 = ccy - (mh / scale) / 2
        tiles_h = mh / scale
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
        urgent = secs <= WAVE_WARNING_S and not c.waves_paused
        text = f"Wave {c.wave.number + 1} in {int(secs // 60)}:{int(secs % 60):02d}"
        if c.waves_paused:
            text += "   (waves paused)"
        if c.enemies:
            text += f"   enemies {len(c.enemies)}"
        if game.paused:
            text += "   PAUSED"
        elif game.speed > 1:
            text += f"   x{game.speed}"
        surf = self.text(text, 20, (255, 90, 90) if urgent else (220, 230, 220))
        sw, ph = surf.get_width(), self.px(32)
        x, y = w // 2 - sw // 2, 8
        col_left = self.rects["balance"].left
        if self.portrait:                                 # rotated phone: top left beside the column, else under it all
            x = 18                                        # the panel starts at 8
            if x + sw + 16 > col_left:
                x, y = w // 2 - sw // 2, self.content_bottom + 6
        else:
            pr = self.panel_rect
            if pr is not None and x - 10 < pr.right + 6:  # a wide structure panel (big text): step aside
                x = pr.right + 16
                if x + sw + 16 > col_left:                # no room beside it: under it
                    x, y = w // 2 - sw // 2, pr.bottom + 6
        self.wave_rect = pygame.Rect(x - 10, y, sw + 20, ph)
        self._panel(self.wave_rect)
        self.screen.blit(surf, (x, y + (ph - surf.get_height()) // 2))

    HELP = [
        "1-6 belt / miner / adder / subtract / multiply / divide   7 wall   8 tower   9 0 - = spawners   B bridge   X demolish",
        "LMB place; belts: hold and drag = preview, release to build; Shift = straight run + square corner; R while",
        "dragging turns every belt (twice = the line runs backwards); drag back to undo.   R rotate   Q pick tool",
        "JUNCTIONS: a belt pointing into another belt's side or back MERGES into it (T / X shapes with several inputs).",
        "A belt SPLITS only when you press T on it, or when an unfed belt starts beside a straight line: items alternate",
        "between its front and each side belt pointing away; splitting belts show small arrows at every exit.",
        "B = bridge: two lines cross without mixing (whatever enters a side leaves through the opposite side);",
        "a bridge can be dropped straight onto a belt of a finished line (the belt's numbers carry on across it).",
        "Drag off the MIDDLE of a line to branch it; from its END the last belt turns; dragging backwards reverses it.",
        "X = demolish tool: click a building or drag a box over many (50% refund), X or Esc to stop.   Del = remove",
        "the selected building(s) (a boxed group too), else the one under the cursor.",
        "click = select (panel on the right); drag a box = select many (U upgrades / H repairs them all)   RMB = cancel",
        "wheel zoom   MMB drag / WASD pan (Shift fast)   Space pause   [ ] sim speed x1 x2 x4   F3 debug   F11 fullscreen",
        "Minimap: click it to fold it into a Map button (click the button to unfold); right-click the minimap to look there.",
        "Belts: items enter from behind or the sides; a belt pointing INTO another belt's front FEEDS it (levels it up).",
        "Machines: every side but the front is an input (left = A, right = B, back = the emptier one); output in front.",
        "HQ: deliver from any side = income.  Feed sides (yellow) level belts/walls/spawners; U levels anything.",
        "Towers (range 10): run a belt or put a miner beside one, any side; it fires those numbers. Red frame = no ammo.",
        "Spawners: click one (or press C with one or a boxed group selected) to train a unit (Ranged 50, Melee 50, Heavy 150,",
        "Repair 100; the panel shows the price); new units walk to its gather point beside the HQ. RMB with spawners",
        "selected = gather point for units trained from then on.   Waves come every 10 minutes.",
        "Units: click or drag a box to select (Shift adds), RMB moves them. Attackers each take their own tile.",
        "With units selected the WHEEL cycles their formation (box, line, column, wedge, ring; it sticks to the group;",
        "Ctrl+wheel zooms) and a MIDDLE CLICK sets a patrol: they walk between their rally point and the clicked point.",
        "Units walk over belts and bridges but never through walls or buildings: leave a gap in a wall line as a gate.",
        "= Repair spawner (100): its units (red, white cross) fix damaged buildings and heal units anywhere, nearest first,",
        "from a load of 500 numbers (5 hp per number, the [H] price) and walk to the HQ for a new load when empty.",
        "Targets: deliver the shown amount of that number for the bonus; the slot then levels up (bigger number and amount).",
        "Waves come from the red edge arrow. HQ destroyed = game over.",
        "An enemy camp always sits about 100 tiles from the HQ (dark-red edge arrow, minimap): it is quiet until you",
        "build within 48 tiles of it, then it raids; kill its core for a 500 bounty. More camps lie further out.",
        "Enemies shoot from 3-5 tiles and melee up close; each level costs 25% more than the last, no cap.",
        "F1 closes this help.",
    ]

    def _draw_help(self):
        """The help panel at the text size, stepping down (13 px lines at 1x,
        then smaller) until its 30-odd lines fit the window."""
        w, h = self.screen.get_size()
        ts = prefs.text_scale
        for scale in (ts, ts * 0.87, 1.0, 0.87, 0.75, 0.65):
            size, lh, pad = max(6, int(round(15 * scale))), int(round(22 * scale)), int(round(20 * scale))
            lines = [numbers.text(t, size) for t in self.HELP]
            pw = max(s.get_width() for s in lines) + 2 * pad
            ph = len(lines) * lh + 2 * pad
            if ph <= h - 16 and pw <= w - 16:
                break
        x0, y0 = (w - pw) // 2, (h - ph) // 2
        self._panel((x0, y0, pw, ph))
        for i, s in enumerate(lines):
            self.screen.blit(s, (x0 + pad, y0 + pad + i * lh))

    def _draw_game_over(self, game):
        w, h = self.screen.get_size()
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((40, 0, 0, 170))
        self.screen.blit(dim, (0, 0))
        p, T = self.px, self.text
        title = T("HQ DESTROYED", 56, (255, 80, 80))
        self.screen.blit(title, (w // 2 - title.get_width() // 2, h // 2 - p(80)))
        c = game.combat
        line = T(f"survived {c.wave.number} waves, {c.stats['kills']} kills, tick {game.factory.tick_count}", 20)
        self.screen.blit(line, (w // 2 - line.get_width() // 2, h // 2 - p(10)))
        keys = T("[L] load last save      [Esc] back to menu", 24, (255, 230, 120))
        self.screen.blit(keys, (w // 2 - keys.get_width() // 2, h // 2 + p(40)))

    def _draw_messages(self):
        w = self.screen.get_width()
        if self.portrait:                                  # under the column, the panel and the timer
            y = max(self.content_bottom, self.wave_rect.bottom) + self.px(16)
        else:
            y = max(self.px(80), self.wave_rect.bottom + self.px(40))   # under the wave timer, wherever it went
        size = prefs.tsize(18)
        for text, ttl in self.messages:
            surf = numbers.text(text, size, (255, 220, 120))
            lines = [surf] if surf.get_width() <= w - 16 else \
                [numbers.text(line, size, (255, 220, 120)) for line in self._wrap(text, size, w - 16)]
            for surf in lines:                          # a narrow (portrait) screen: wrapped, never cut off
                if ttl < 0.6:
                    surf = surf.copy()
                    surf.set_alpha(int(255 * ttl / 0.6))
                self.screen.blit(surf, (w // 2 - surf.get_width() // 2, y))
                y += self.px(24)
