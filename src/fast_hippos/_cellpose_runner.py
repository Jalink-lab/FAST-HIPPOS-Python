"""Run Cellpose (3 or 4) on a 2-D image. Executed as a standalone script, possibly by the Python of another
environment, so it must not import fast_hippos.

Usage: python _cellpose_runner.py input.npy output.npy '{"model": "cyto3", ...}'
"""

import json
import sys
import time

import numpy as np


def run(img: np.ndarray, params: dict) -> tuple[np.ndarray, dict]:
    """Segment img; returns the masks and info on the run (Cellpose version, device, timing)."""
    from importlib.metadata import version

    from cellpose import models

    major = int(version("cellpose").split(".")[0])
    model_name = params["model"]
    gpu = params.get("use_gpu", True)
    diameter = params.get("diameter") or None
    is_path = any(ch in model_name for ch in "/\\.")
    t0 = time.perf_counter()
    kwargs = {"flow_threshold": params["flow_threshold"], "cellprob_threshold": params["cellprob_threshold"]}

    if major >= 4:
        if is_path:
            model = models.CellposeModel(gpu=gpu, pretrained_model=model_name)
        else:
            model = models.CellposeModel(gpu=gpu)  # cpsam
        t1 = time.perf_counter()
        masks = model.eval(img, diameter=diameter, **kwargs)[0]
    else:
        if is_path:
            model = models.CellposeModel(gpu=gpu, pretrained_model=model_name)
            t1 = time.perf_counter()
            masks = model.eval(img, diameter=diameter, channels=[0, 0], **kwargs)[0]
        elif diameter is None and model_name in ("cyto", "cyto2", "cyto3", "nuclei"):
            model = models.Cellpose(gpu=gpu, model_type=model_name)  # includes the size model
            t1 = time.perf_counter()
            masks = model.eval(img, diameter=None, channels=[0, 0], **kwargs)[0]
        else:
            model = models.CellposeModel(gpu=gpu, model_type=model_name)
            t1 = time.perf_counter()
            masks = model.eval(img, diameter=diameter, channels=[0, 0], **kwargs)[0]
    t2 = time.perf_counter()
    device = getattr(model, "device", None) or getattr(getattr(model, "cp", None), "device", None)
    info = {"version": version("cellpose"), "device": str(device), "gpu_requested": bool(gpu),
            "load_s": round(t1 - t0, 2), "eval_s": round(t2 - t1, 2)}
    try:
        import torch

        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001, S110 - info only
        pass
    return np.asarray(masks).astype(np.int32), info


if __name__ == "__main__":
    image = np.load(sys.argv[1])
    masks, info = run(image, json.loads(sys.argv[3]))
    np.save(sys.argv[2], masks)
    print("FH_INFO " + json.dumps(info))
