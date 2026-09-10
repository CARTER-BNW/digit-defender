from world.terrain import Terrain
from world.tiles import DEPOSIT_BASE


def test_update_generates_keep_and_unloads_outside():
    t = Terrain(1337)
    t.update((0, 0, 2, 2), (-1, -1, 3, 3))
    assert len(t.chunks) == 9
    assert t.generated == 9
    # hysteresis: still inside the unload rect -> nothing dropped
    t.update((1, 1, 1, 1), (-1, -1, 3, 3))
    assert len(t.chunks) == 9
    # move far away: everything outside the unload rect is dropped
    t.update((50, 50, 50, 50), (49, 49, 51, 51))
    assert set(t.chunks) == {(50, 50)}
    # come back: regenerated, identical
    before = list(Terrain(1337).get_chunk(1, 1).tiles)
    t.update((0, 0, 2, 2), (-1, -1, 3, 3))
    assert t.get_chunk(1, 1).tiles == before


def test_peek_never_generates():
    t = Terrain(1337)
    assert t.peek_chunk(4, 4) is None
    assert t.generated == 0
    t.get_chunk(4, 4)
    assert t.peek_chunk(4, 4) is not None


def test_set_tile_marks_dirty_and_modified_and_saves_on_unload():
    saved = []
    t = Terrain(1337)
    t.saver = saved.append
    t.get_chunk(0, 0).dirty = False
    t.set_tile(-1, -1, DEPOSIT_BASE + 5)      # chunk (-1,-1), local (15,15)
    c = t.get_chunk(-1, -1)
    assert c.modified and c.dirty
    t.update((5, 5, 5, 5), (5, 5, 5, 5))
    assert [ch.cx for ch in saved] == [-1]
    assert not saved[0].modified
