"""Lectura y escritura de los CSV raw y del solucionario."""

import json
from pathlib import Path

import pandas as pd

from academy.core.paths import RAW_DIR, TRUTH_DIR

from .generator import SyntheticDataset


def write_dataset(ds: SyntheticDataset, raw_dir: Path = RAW_DIR) -> list[Path]:
    """Escribe una tabla CSV por sistema y el solucionario en `raw_dir/_truth`."""
    truth_dir = raw_dir / TRUTH_DIR.name
    truth_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in ds.tables.items():
        path = raw_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        written.append(path)
    ds.customer_links.to_csv(truth_dir / "customer_links.csv", index=False, encoding="utf-8")
    (truth_dir / "defects.json").write_text(
        json.dumps(ds.defects, ensure_ascii=False, indent=2), encoding="utf-8")
    return written


def read_raw(name: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Lee una tabla raw tal como llega: todo como texto."""
    return pd.read_csv(raw_dir / f"{name}.csv", dtype=str, keep_default_na=False,
                       na_values=[""])


def read_truth(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Solucionario: vínculos persona ↔ registros de cada sistema y defectos sembrados."""
    truth_dir = raw_dir / TRUTH_DIR.name
    links = pd.read_csv(truth_dir / "customer_links.csv", dtype=str)
    defects = json.loads((truth_dir / "defects.json").read_text(encoding="utf-8"))
    return links, defects
