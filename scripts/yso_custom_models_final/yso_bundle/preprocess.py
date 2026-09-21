from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image
import torch


def preprocess_pil(
    img: Image.Image,
    target_size: Tuple[int, int],
    as_gray: bool,
    normalize_01: bool,
    invert: bool,
    binarize: bool,
) -> torch.Tensor:
    """
    Returns FloatTensor [C,H,W], C=1 if as_gray else 3.
    Behaviour matches your training dataset code.
    """
    img = img.resize(tuple(target_size), Image.BILINEAR)

    if as_gray:
        img = img.convert("L")
        arr = np.array(img, dtype=np.float32)  # (H,W), 0..255

        if normalize_01:
            arr = arr / 255.0
            if invert:
                arr = 1.0 - arr
            if binarize:
                arr = (arr >= 0.5).astype(np.float32)
        else:
            if invert:
                arr = 255.0 - arr
            if binarize:
                arr = np.where(arr >= 127.5, 255.0, 0.0).astype(np.float32)

        x = torch.tensor(arr, dtype=torch.float32).unsqueeze(0).contiguous()  # (1,H,W)
        return x

    img = img.convert("RGB")
    arr = np.array(img, dtype=np.float32)  # (H,W,3), 0..255

    if normalize_01:
        arr = arr / 255.0
        if invert:
            arr = 1.0 - arr
        if binarize:
            arr = (arr >= 0.5).astype(np.float32)
    else:
        if invert:
            arr = 255.0 - arr
        if binarize:
            arr = np.where(arr >= 127.5, 255.0, 0.0).astype(np.float32)

    x = torch.tensor(arr, dtype=torch.float32).permute(2, 0, 1).contiguous()  # (3,H,W)
    return x
