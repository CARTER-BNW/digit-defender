"""Structure records <-> objects. Records are plain dicts (JSON-ready).
File layout and atomic writes live in world/persistence.py (Phase 3)."""
from sim.structures import KINDS

STRUCTURES_VERSION = 1


def structure_records(factory):
    """Unique structures, sorted by (y, x) so output is stable."""
    seen = set()
    out = []
    for s in sorted(factory.all_structures(), key=lambda s: (s.y, s.x)):
        if id(s) in seen:
            continue
        seen.add(id(s))
        out.append(s.to_dict())
    return {"version": STRUCTURES_VERSION, "structures": out}


def load_structure_records(factory, data):
    """Rebuild factory structures from structure_records() output."""
    factory.clear_structures()
    for rec in data.get("structures", []):
        cls = KINDS.get(rec.get("kind"))
        if cls is None:
            continue
        factory.add_structure(cls.from_dict(rec))
    factory.dirty_links = True
