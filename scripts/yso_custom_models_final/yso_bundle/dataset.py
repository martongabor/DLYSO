from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
import torch
from torch.utils.data import Dataset

from .preprocess import preprocess_pil


class SplitImageDataset(Dataset):
    """
    Folder structure:
      <root>/<split>/other/*.png
      <root>/<split>/YSO/*.png
    """

    def __init__(
        self,
        root_dir: str,
        split: str,
        class_to_idx: Optional[Dict[str, int]],
        preprocess_cfg: Dict,
    ):
        self.root_dir = Path(root_dir)
        self.split = str(split)
        self.split_dir = self.root_dir / self.split

        if class_to_idx is None:
            class_to_idx = {"other": 0, "YSO": 1}
        self.class_to_idx = dict(class_to_idx)

        self.preprocess_cfg = dict(preprocess_cfg)
        self.samples: List[Dict] = []
        self._build_index()

    def _build_index(self):
        if not self.split_dir.exists():
            raise FileNotFoundError(f"Split directory not found: {self.split_dir}")

        for class_name, label in self.class_to_idx.items():
            class_dir = self.split_dir / class_name
            if not class_dir.exists():
                print(f"[WARN] Class directory missing in {self.split}: {class_dir}")
                continue

            for img_path in sorted(class_dir.glob("*.png")):
                self.samples.append({"path": img_path, "label": int(label), "class_name": class_name})

        if len(self.samples) == 0:
            raise RuntimeError(f"No samples found in {self.split_dir}")

        print(f"[{self.split}] found {len(self.samples)} images ({self.class_to_idx}) under {self.split_dir}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict:
        s = self.samples[idx]
        p: Path = s["path"]
        y = int(s["label"])

        with Image.open(p) as img:
            x = preprocess_pil(
                img,
                target_size=tuple(self.preprocess_cfg["target_size"]),
                as_gray=bool(self.preprocess_cfg["as_gray"]),
                normalize_01=bool(self.preprocess_cfg["normalize_01"]),
                invert=bool(self.preprocess_cfg["invert"]),
                binarize=bool(self.preprocess_cfg["binarize"]),
            )

        return {
            "image": x,  # [C,H,W]
            "label": torch.tensor(y, dtype=torch.long),  # []
            "path": str(p),
        }


class FlatFolderDataset(Dataset):
    """
    Folder with *.png (non-recursive), no labels.
    """

    def __init__(self, folder: str, preprocess_cfg: Dict):
        self.folder = Path(folder)
        if not self.folder.exists() or not self.folder.is_dir():
            raise FileNotFoundError(f"Folder not found / not a directory: {self.folder}")
        self.preprocess_cfg = dict(preprocess_cfg)

        self.paths = sorted(self.folder.glob("*.png"))
        if not self.paths:
            raise RuntimeError(f"No PNGs found in folder: {self.folder}")

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int) -> Dict:
        p: Path = self.paths[idx]
        with Image.open(p) as img:
            x = preprocess_pil(
                img,
                target_size=tuple(self.preprocess_cfg["target_size"]),
                as_gray=bool(self.preprocess_cfg["as_gray"]),
                normalize_01=bool(self.preprocess_cfg["normalize_01"]),
                invert=bool(self.preprocess_cfg["invert"]),
                binarize=bool(self.preprocess_cfg["binarize"]),
            )
        return {
            "image": x,
            "path": str(p),
        }
