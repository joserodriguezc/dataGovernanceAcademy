"""Rutas por defecto del espacio de trabajo con los datos de NovaMercado.

La app pasa siempre rutas explícitas (el directorio de datos se puede cambiar con
ACADEMY_DATA_DIR); estas son las de por defecto, como en el laboratorio.
"""

from academy.paths import DATA_DIR

WORKSPACE_DIR = DATA_DIR / "workspace"
RAW_DIR = WORKSPACE_DIR / "raw"
TRUTH_DIR = RAW_DIR / "_truth"  # solucionario de los datos sintéticos (solo para evaluar)
WAREHOUSE_DB = WORKSPACE_DIR / "novamercado.duckdb"

# Registro de operaciones (lección 11): fuera del warehouse para que no se pierda al reconstruirlo
OPS_DB = WORKSPACE_DIR / "operations.duckdb"
