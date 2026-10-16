import sys

# no __pycache__ folders in the (synced) project folder while testing
sys.dont_write_bytecode = True


def make_result(folder, name, index=0, source=""):
    """A minimal image result folder as FAST-HIPPOS writes it (meta.json with name and version, traces next to it)."""
    import json

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.json").write_text(json.dumps({"name": name, "index": index, "version": "test", "n_cells": 5,
                                                  "source": source}))
    (folder / "traces.npz").write_bytes(b"")
    return folder
