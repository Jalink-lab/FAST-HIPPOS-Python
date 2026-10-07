"""Run Cellpose (3 or 4) on a 2-D image. Executed as a standalone script, possibly by the Python of another
environment, so it must not import fast_hippos.

Usage: python _cellpose_runner.py input.npy output.npy '{"model": "cyto3", ...}'
"""

import json
import sys

import numpy as np


def run(img: np.ndarray, params: dict) -> np.ndarray:
    from importlib.metadata import version

    from cellpose import models

    major = int(version("cellpose").split(".")[0])
    model_name = params["model"]
    gpu = params.get("use_gpu", True)
    diameter = params.get("diameter") or None
    is_path = any(ch in model_name for ch in "/\\.")
    kwargs = {"flow_threshold": params["flow_threshold"], "cellprob_threshold": params["cellprob_threshold"]}

    if major >= 4:
        if is_path:
            model = models.CellposeModel(gpu=gpu, pretrained_model=model_name)
        else:
            model = models.CellposeModel(gpu=gpu)  # cpsam
        masks = model.eval(img, diameter=diameter, **kwargs)[0]
    else:
        if is_path:
            model = models.CellposeModel(gpu=gpu, pretrained_model=model_name)
            masks = model.eval(img, diameter=diameter, channels=[0, 0], **kwargs)[0]
        elif diameter is None and model_name in ("cyto", "cyto2", "cyto3", "nuclei"):
            model = models.Cellpose(gpu=gpu, model_type=model_name)  # includes the size model
            masks = model.eval(img, diameter=None, channels=[0, 0], **kwargs)[0]
        else:
            model = models.CellposeModel(gpu=gpu, model_type=model_name)
            masks = model.eval(img, diameter=diameter, channels=[0, 0], **kwargs)[0]
    return np.asarray(masks).astype(np.int32)


if __name__ == "__main__":
    image = np.load(sys.argv[1])
    np.save(sys.argv[2], run(image, json.loads(sys.argv[3])))
