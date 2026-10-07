"""Random-forest pixel classifier (replaces the Labkit nuclei classifier of the Fiji macro).

Train from scribbles: an annotation image of the same size as the training image, with 0 = unlabelled
and 1..K = classes (e.g. 1 = nucleus, 2 = cytoplasm, 3 = background). Paint it in napari or Fiji
(Labkit/ROI -> label image) and save as TIFF.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
from skimage.feature import multiscale_basic_features
from skimage.filters import threshold_otsu

log = logging.getLogger(__name__)


def normalize(img: np.ndarray) -> np.ndarray:
    """Divide by the Otsu threshold (as Fiji v0.9.5 does before Labkit), so the model transfers between images."""
    img = np.nan_to_num(img.astype(np.float32))
    t = threshold_otsu(img) if np.ptp(img) > 0 else 1.0
    return img / (t if t > 0 else 1.0)


def _features(img: np.ndarray, sigma_min: float, sigma_max: float) -> np.ndarray:
    return multiscale_basic_features(
        normalize(img), intensity=True, edges=True, texture=True, sigma_min=sigma_min, sigma_max=sigma_max
    )


def train(
    image: np.ndarray,
    annotations: np.ndarray,
    path: Path,
    sigma_min: float = 1.0,
    sigma_max: float = 16.0,
    n_estimators: int = 100,
) -> None:
    from sklearn.ensemble import RandomForestClassifier

    if image.shape != annotations.shape:
        raise ValueError(f"Image {image.shape} and annotations {annotations.shape} differ in shape")
    features = _features(image, sigma_min, sigma_max)
    mask = annotations > 0
    if not mask.any():
        raise ValueError("The annotation image contains no labelled pixels")
    clf = RandomForestClassifier(n_estimators=n_estimators, max_depth=12, n_jobs=-1, random_state=0)
    clf.fit(features[mask], annotations[mask])
    joblib.dump({"model": clf, "sigma_min": sigma_min, "sigma_max": sigma_max, "version": 1}, path)
    log.info("Pixel classifier trained on %d pixels, classes %s -> %s", mask.sum(), list(clf.classes_), path)


def predict_probability(image: np.ndarray, path: Path, class_index: int = 1) -> np.ndarray:
    """Probability (Y, X) of class `class_index` (the annotation value) for a 2-D image."""
    bundle = joblib.load(path)
    clf = bundle["model"]
    classes = list(clf.classes_)
    if class_index not in classes:
        raise ValueError(f"Class {class_index} not in classifier classes {classes}")
    features = _features(image, bundle["sigma_min"], bundle["sigma_max"])
    proba = clf.predict_proba(features.reshape(-1, features.shape[-1]))[:, classes.index(class_index)]
    return proba.reshape(image.shape).astype(np.float32)
