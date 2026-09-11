"""Save files (docs/PLAN.md section 3.9).

saves/<slug>/
    meta.json         identity + resume state: name, seed, created, last_played,
                      camera, balance, tick_count, targets, stats, wave
    structures.json   {"version", "structures": [records]}
    enemies.json      {"version", "nests_destroyed", "nests_damaged"}
    chunks/<cx>_<cy>.bin   version byte + 256 tile bytes (only modified chunks;
                      deposits are infinite so in practice none)
config.json (project root): machine-local prefs (fullscreen, last_world).

Every JSON write is atomic: write <file>.tmp, rotate the previous file to
<file>.bak, then os.replace. Readers fall back to .bak when the main file is
missing or corrupt, so a process kill never loses more than one save.
"""
import json
import os
import random
import time
from pathlib import Path

from settings import CHUNK_SIZE, SAVE_VERSION

ROOT = Path(__file__).resolve().parent.parent
_saves_dir = ROOT / "saves"
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONFIG = {"fullscreen": False, "last_world": None, "hints": True,
                  "text_scale": 1.0, "button_scale": 1.0,    # menu Settings (ui/prefs.py)
                  "waves_paused": False}                     # menu Settings: the wave countdown stands still
CHUNK_VERSION = 1

warnings = []          # human-readable notes about fallbacks (UI may show them)


def set_saves_dir(path):
    """Redirect the save root (tests)."""
    global _saves_dir
    _saves_dir = Path(path)


def saves_dir():
    return _saves_dir


# ---- json helpers ---------------------------------------------------------------

def write_json(path, data, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    bak = path.with_name(path.name + ".bak")
    text = json.dumps(data, separators=(",", ":")) if compact else json.dumps(data, indent=2)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    if path.exists():
        os.replace(path, bak)
    os.replace(tmp, path)


def read_json(path, default=None):
    """Parse path, falling back to path.bak; `default` if neither works."""
    path = Path(path)
    for candidate in (path, path.with_name(path.name + ".bak")):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"{candidate.name}: unreadable ({exc.__class__.__name__}), trying fallback")
            continue
        if candidate is not path:
            warnings.append(f"{path.name}: restored from backup")
        return data
    return default


# ---- config ----------------------------------------------------------------------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    data = read_json(CONFIG_PATH, default={})
    if isinstance(data, dict):
        cfg.update(data)
    return cfg


def save_config(config):
    write_json(CONFIG_PATH, config)


# ---- world registry --------------------------------------------------------------

def slugify(name):
    slug = "".join(c if c.isalnum() else "_" for c in name.strip())
    return slug or "world"


def world_dir(slug):
    return _saves_dir / slug


def list_worlds():
    """All world metas, most recently played first (corrupt ones skipped)."""
    metas = []
    if _saves_dir.exists():
        for d in _saves_dir.iterdir():
            if not d.is_dir():
                continue
            meta = read_json(d / "meta.json")
            if isinstance(meta, dict) and "seed" in meta:
                meta.setdefault("slug", d.name)
                metas.append(meta)
    return sorted(metas, key=lambda m: m.get("last_played", 0), reverse=True)


def load_meta(slug):
    meta = read_json(world_dir(slug) / "meta.json")
    if isinstance(meta, dict):
        meta.setdefault("slug", slug)
        return meta
    return None


def create_world(name=None, seed=None):
    existing = {m["name"] for m in list_worlds()}
    if not name:
        i = 1
        while f"World {i}" in existing:
            i += 1
        name = f"World {i}"
    slug = slugify(name)
    base, n = slug, 2
    while world_dir(slug).exists():
        slug = f"{base}_{n}"
        n += 1
    if seed is None:
        seed = random.randrange(2 ** 31)
    now = time.time()
    meta = {"version": SAVE_VERSION, "name": name, "slug": slug, "seed": int(seed),
            "created": now, "last_played": now, "camera": None}
    write_json(world_dir(slug) / "meta.json", meta)
    return meta


def find_or_create(name, seed=None):
    for m in list_worlds():
        if m["name"] == name or m.get("slug") == slugify(name):
            return m
    return create_world(name, seed)


def delete_world(slug):
    """Remove a world's save folder for good. True if it existed and is gone."""
    import shutil
    d = world_dir(slug)
    if not d.exists():
        return False
    shutil.rmtree(d, ignore_errors=True)
    return not d.exists()


# ---- world state -----------------------------------------------------------------

FACTORY_META_KEYS = ("balance", "tick_count", "targets", "targets_completed", "stats")


def save_world(meta, factory, camera=None, nests=None, wave=None):
    """Write structures.json, enemies.json, then meta.json (the commit record)."""
    d = world_dir(meta["slug"])
    state = factory.to_dict()
    structures = state.pop("structures")
    meta["version"] = SAVE_VERSION
    meta["last_played"] = time.time()
    meta.update(state)
    if camera is not None:
        meta["camera"] = [camera.x, camera.y, camera.zoom_index]
    meta["wave"] = wave
    write_json(d / "structures.json", structures, compact=True)
    enemies = {"version": SAVE_VERSION}
    if nests is not None:
        enemies.update(nests.to_dict())
    write_json(d / "enemies.json", enemies)
    write_json(d / "meta.json", meta)
    return d


def load_world(slug):
    """(meta, structures_data | None, enemies_data | {})."""
    d = world_dir(slug)
    meta = load_meta(slug)
    structures = read_json(d / "structures.json", default=None)
    enemies = read_json(d / "enemies.json", default={}) or {}
    if structures is not None and not isinstance(structures, dict):
        warnings.append("structures.json: wrong shape, ignored")
        structures = None
    return meta, structures, enemies


def factory_state_from_meta(meta, structures):
    """Assemble the dict Factory.from_dict expects."""
    state = {k: meta[k] for k in FACTORY_META_KEYS if k in meta}
    state["structures"] = structures or {}
    return state


# ---- chunk files -----------------------------------------------------------------

def _chunk_path(save_dir, cx, cy):
    return Path(save_dir) / "chunks" / f"{cx}_{cy}.bin"


def save_chunk(save_dir, cx, cy, tiles):
    p = _chunk_path(save_dir, cx, cy)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(bytes([CHUNK_VERSION]) + bytes(tiles))
    os.replace(tmp, p)


def load_chunk(save_dir, cx, cy):
    """Saved tiles or None (regenerate)."""
    try:
        data = _chunk_path(save_dir, cx, cy).read_bytes()
    except FileNotFoundError:
        return None
    n = CHUNK_SIZE * CHUNK_SIZE
    if len(data) == n + 1 and data[0] == CHUNK_VERSION:
        return list(data[1:])
    warnings.append(f"chunk {cx},{cy}: corrupt file ignored")
    return None
