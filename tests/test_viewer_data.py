import numpy as np

from fast_hippos.viewer_data import TILE, ViewerData, prepare


def test_pyramid_tiles(tmp_path):
    rng = np.random.default_rng(0)
    intensity = rng.random((3, 1100, 1100), dtype=np.float32) * 100
    lifetime = (2.5 + rng.random((3, 1100, 1100), dtype=np.float32)).astype(np.float32)
    labels = (np.arange(1100)[:, None] // 50 * 30 + np.arange(1100)[None, :] // 50).astype(np.int32)
    v = prepare(intensity, lifetime, intensity.sum(0), labels, (2.0, 3.4), max_size=300, tiles_dir=tmp_path / "tiles")
    # 1100 px -> overview at factor 4 (275 px); levels 0 and 1 are tiled
    assert v.factor == 4 and v.lifetime8.shape == (3, 275, 275)
    assert [lv["level"] for lv in v.tiles["levels"]] == [0, 1]
    l0 = v.tiles["levels"][0]
    assert (l0["nx"], l0["ny"]) == (-(-1100 // TILE), -(-1100 // TILE))
    files = sorted(p.name for p in (tmp_path / "tiles" / "L0").iterdir())
    assert "lab_0_0.js" in files and "p_2_2.js" in files and "t2_2_2.js" in files
    text = (tmp_path / "tiles" / "L1" / "t0_0_0.js").read_text()
    assert text.startswith('FHTile("L1/t0_0_0","data:image/png;base64,')
    # round trip of the metadata
    v.save(tmp_path / "viewer.npz")
    w = ViewerData.load(tmp_path / "viewer.npz")
    assert w.tiles == v.tiles and w.factor == 4 and np.array_equal(w.labels, v.labels) and w.smoothed_xy == 0


def test_frames_are_files_next_to_the_dashboard(tmp_path):
    """write_frames: one frames/t<i>.js per frame (FHTile("O/t<i>", url)); the first frame is returned for the page."""
    import numpy as np

    from fast_hippos.viewer_data import FRAMES_DIR, prepare, write_frames

    rng = np.random.default_rng(1)
    t, h, w = 3, 20, 24
    v = prepare(rng.random((t, h, w)).astype(np.float32), rng.random((t, h, w)).astype(np.float32) + 2,
                rng.random((h, w)).astype(np.float32), np.ones((h, w), np.int32), (2.0, 3.0))
    first = write_frames(v, tmp_path)
    files = sorted((tmp_path / FRAMES_DIR).glob("t*.js"))
    assert [f.name for f in files] == ["t0.js", "t1.js", "t2.js"]
    assert first.startswith("data:image/png;base64,")
    assert (tmp_path / FRAMES_DIR / "t1.js").read_text().startswith('FHTile("O/t1","data:image/png;base64,')
    write_frames(v, tmp_path)  # again: the old files are replaced, not added to
    assert len(list((tmp_path / FRAMES_DIR).iterdir())) == 3
