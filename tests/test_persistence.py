"""Save/load: atomic JSON + .bak fallback, chunk files, world registry, the
determinism round-trip (save@100 + load + 100 == twin@200), Game-level
save/load with camera, and world isolation."""
import json

import pygame
import pytest

from settings import WINDOW_W, WINDOW_H, CHUNK_SIZE
from world import persistence
from sim.factory import Factory
from sim.structures import N, E, S, W
from sim.nests import NestRegistry


@pytest.fixture
def saves(tmp_path):
    persistence.set_saves_dir(tmp_path / "saves")
    persistence.warnings.clear()
    yield tmp_path / "saves"
    persistence.set_saves_dir(persistence.ROOT / "saves")


def build(seed=5):
    f = Factory(seed=seed, balance=10 ** 6)
    f.create_hub(0, 0)
    f.place("miner", 8, 0, W, free=True, value=3)
    f.place("miner", 8, 2, W, free=True, value=5)
    for x in range(2, 8):
        f.place("belt", x, 0, W, free=True)
        f.place("belt", x, 2, W, free=True)
    f.place("belt", 1, 2, N, free=True)          # into the hub from below
    a = f.place("adder", 5, -4, W, free=True)
    f.place("miner", 5, -5, S, free=True, value=2)
    f.place("miner", 5, -3, N, free=True, value=4)
    for x in range(2, 5):
        f.place("belt", x, -4, W, free=True)
    f.place("belt", 1, -4, S, free=True)
    f.place("belt", 1, -3, S, free=True)
    return f


def test_write_json_is_atomic_with_bak_fallback(tmp_path):
    p = tmp_path / "a" / "meta.json"
    persistence.write_json(p, {"v": 1})
    persistence.write_json(p, {"v": 2})
    assert json.loads(p.read_text()) == {"v": 2}
    assert json.loads(p.with_name("meta.json.bak").read_text()) == {"v": 1}
    assert not p.with_name("meta.json.tmp").exists()
    p.write_text("{corrupt")
    persistence.warnings.clear()
    assert persistence.read_json(p) == {"v": 1}
    assert any("backup" in w for w in persistence.warnings)
    p.unlink()
    assert persistence.read_json(p) == {"v": 1}        # main missing -> bak
    p.with_name("meta.json.bak").unlink()
    assert persistence.read_json(p, default="dflt") == "dflt"


def test_chunk_file_roundtrip_negative_coords(tmp_path):
    tiles = [(i * 7) % 22 for i in range(CHUNK_SIZE * CHUNK_SIZE)]
    persistence.save_chunk(tmp_path, -3, 7, tiles)
    assert persistence.load_chunk(tmp_path, -3, 7) == tiles
    assert persistence.load_chunk(tmp_path, 0, 0) is None
    (tmp_path / "chunks" / "-3_7.bin").write_bytes(b"\x01abc")
    assert persistence.load_chunk(tmp_path, -3, 7) is None


def test_world_registry(saves):
    a = persistence.create_world("My World!", 5)
    assert a["slug"] == "My_World_" and a["seed"] == 5
    b = persistence.create_world(None, None)
    assert b["name"].startswith("World ")
    c = persistence.create_world("My World!", 9)           # same name: distinct dir
    assert c["slug"] != a["slug"] and persistence.world_dir(c["slug"]).exists()
    a["last_played"] = 10 ** 10
    persistence.write_json(persistence.world_dir(a["slug"]) / "meta.json", a)
    worlds = persistence.list_worlds()
    assert worlds[0]["slug"] == a["slug"]
    assert persistence.find_or_create("My World!")["slug"] == a["slug"]
    assert persistence.load_meta("nope") is None


def test_roundtrip_determinism(saves):
    f = build()
    twin = build()
    for _ in range(100):
        f.tick()
        twin.tick()
    meta = persistence.create_world("det", 5)
    persistence.save_world(meta, f, camera=None, nests=NestRegistry())
    meta2, structures, enemies = persistence.load_world(meta["slug"])
    g = Factory.from_dict(persistence.factory_state_from_meta(meta2, structures), seed=5)
    assert g.to_dict() == f.to_dict()
    for _ in range(100):
        g.tick()
        twin.tick()
    assert g.to_dict() == twin.to_dict()
    assert g.balance == twin.balance and g.tick_count == 200
    assert enemies.get("nests_destroyed") == []


@pytest.fixture
def screen():
    pygame.init()
    scr = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    yield scr
    pygame.quit()


def test_game_save_and_load(saves, screen):
    from game import Game
    meta = persistence.create_world("gameworld", 1337)
    g = Game.load(screen, meta)
    assert g.factory.hub is not None and g.meta["slug"] == "gameworld"
    g.factory.balance = 10 ** 6
    for x in range(3, 9):
        g.factory.place("belt", x, 4, E)
    g.camera.move(300, -120)
    g.camera.set_zoom_index(1)
    for _ in range(30):
        g.update(1 / 60)
    g.save()
    d = persistence.world_dir("gameworld")
    assert (d / "structures.json").exists() and (d / "enemies.json").exists()
    g2 = Game.load(screen, persistence.load_meta("gameworld"))
    assert g2.factory.to_dict() == g.factory.to_dict()
    assert (g2.camera.x, g2.camera.y, g2.camera.zoom_index) == (g.camera.x, g.camera.y, 1)
    assert g2.factory.structure_at(5, 4).KIND == "belt"
    # run() saves on exit
    g2.factory.place("belt", 9, 4, E)
    g2.run(max_frames=2)
    g3 = Game.load(screen, persistence.load_meta("gameworld"))
    assert g3.factory.structure_at(9, 4) is not None


def test_two_worlds_do_not_cross_contaminate(saves, screen):
    from game import Game
    a = Game.load(screen, persistence.create_world("A", 1))
    b = Game.load(screen, persistence.create_world("B", 2))
    a.factory.place("belt", 5, 5, E, free=True)
    b.factory.place("wall", 6, 6, N, free=True)
    a.save()
    b.save()
    a2 = Game.load(screen, persistence.load_meta("A"))
    b2 = Game.load(screen, persistence.load_meta("B"))
    assert a2.factory.structure_at(5, 5).KIND == "belt" and a2.factory.structure_at(6, 6) is None
    assert b2.factory.structure_at(6, 6).KIND == "wall" and b2.factory.structure_at(5, 5) is None
    assert a2.terrain.seed == 1 and b2.terrain.seed == 2


def test_corrupt_structures_file_fallbacks(saves, screen):
    from game import Game
    meta = persistence.create_world("C", 3)
    g = Game.load(screen, meta)
    g.factory.place("belt", 2, 2, E, free=True)
    g.save()
    g.factory.place("belt", 3, 2, E, free=True)
    g.save()                                       # .bak now holds the 1-belt save
    d = persistence.world_dir("C")
    (d / "structures.json").write_text("{not json")
    persistence.warnings.clear()
    g2 = Game.load(screen, persistence.load_meta("C"))
    assert g2.factory.structure_at(2, 2) is not None and g2.factory.structure_at(3, 2) is None
    assert any("backup" in w for w in persistence.warnings)
    (d / "structures.json").write_text("{not json")
    (d / "structures.json.bak").write_text("also bad")
    g3 = Game.load(screen, persistence.load_meta("C"))
    assert g3.factory.hub is not None and len(g3.factory.belts) == 0   # fresh factory, hub intact
