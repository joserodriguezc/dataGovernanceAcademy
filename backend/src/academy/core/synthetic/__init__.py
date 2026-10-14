"""Datos sintéticos de NovaMercado: generador determinista con defectos sembrados."""

from .config import DEFAULT_SEED, DefectRates, Presence, Scale, SyntheticConfig
from .generator import SyntheticDataset, generate
from .io import read_raw, read_truth, write_dataset

__all__ = [
    "DEFAULT_SEED", "DefectRates", "Presence", "Scale", "SyntheticConfig", "SyntheticDataset",
    "generate", "read_raw", "read_truth", "write_dataset",
]
