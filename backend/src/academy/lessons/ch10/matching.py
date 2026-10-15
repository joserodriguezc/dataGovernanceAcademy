"""Deduplicación (match and merge): reglas deterministas, coincidencia aproximada y revisión.

1. Mismo email o mismo teléfono -> mismo cliente (reglas deterministas).
2. Mismo código postal y nombre parecido (>= auto_match_score) -> mismo cliente (fuzzy).
3. Casos dudosos -> cola de revisión humana: nombre parecido con distinto código postal
   (¿se ha mudado?) o mismo código postal con un nombre algo parecido.

Los emparejamientos se cierran por transitividad (union-find): si A=B y B=C, A=B=C.
"""

from dataclasses import dataclass
from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz

from .config import Matching


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


@dataclass(frozen=True)
class Pair:
    a: int
    b: int
    rule: str
    score: float


def _pairs_by(df: pd.DataFrame, column: str) -> set[tuple[int, int]]:
    """Pares de filas que comparten un valor no nulo de `column`."""
    out = set()
    for _, idx in df.dropna(subset=[column]).groupby(column).groups.items():
        out.update(combinations(sorted(idx), 2))
    return out


def find_pairs(df: pd.DataFrame, m: Matching) -> tuple[list[Pair], list[Pair]]:
    """Devuelve (emparejamientos automáticos, pares para revisión humana)."""
    scorer = getattr(fuzz, m.name_scorer)
    matches: dict[tuple[int, int], Pair] = {}
    for column, rule in (("email", "email idéntico"), ("phone", "teléfono idéntico")):
        for a, b in sorted(_pairs_by(df, column)):
            matches.setdefault((a, b), Pair(a, b, rule, 100.0))

    # Bloqueo para la parte difusa: mismo código postal, o mismo nombre de pila + primer
    # apellido (para encontrar a quien se ha mudado). Así no se compara todo con todo.
    tokens = df["name_key"].str.split()
    df = df.assign(_block_name=tokens.map(lambda t: " ".join(t[:2]) if len(t) >= 2 else None))
    candidates = _pairs_by(df, "postal_code") | _pairs_by(df, "_block_name")
    review: list[Pair] = []
    for a, b in sorted(candidates - matches.keys()):
        score = scorer(df.at[a, "name_key"], df.at[b, "name_key"])
        same_postal = df.at[a, "postal_code"] == df.at[b, "postal_code"]
        if same_postal and score >= m.auto_match_score:
            matches[(a, b)] = Pair(a, b, "mismo CP y nombre similar", score)
        elif (same_postal and score >= m.review_score) or (
                m.review_if_postal_differs and not same_postal and score >= m.auto_match_score):
            review.append(Pair(a, b, "mismo CP, nombre dudoso" if same_postal
                               else "mismo nombre, distinto CP", score))
    # No se pide revisar lo que ya queda unido por transitividad (A=B y B=C ya da A=C)
    groups = cluster(len(df), list(matches.values()))
    return list(matches.values()), [p for p in review if groups[p.a] != groups[p.b]]


def cluster(n: int, pairs: list[Pair]) -> list[int]:
    """Identificador de grupo (la fila representante) de cada registro."""
    uf = UnionFind(n)
    for p in pairs:
        uf.union(p.a, p.b)
    return [uf.find(i) for i in range(n)]


@dataclass(frozen=True)
class PairwiseScore:
    true_pairs: int
    predicted_pairs: int
    correct_pairs: int

    @property
    def precision(self) -> float:
        return self.correct_pairs / self.predicted_pairs if self.predicted_pairs else 1.0

    @property
    def recall(self) -> float:
        return self.correct_pairs / self.true_pairs if self.true_pairs else 1.0


def _pairs_count(sizes: pd.Series) -> int:
    return int((sizes * (sizes - 1) // 2).sum())


def evaluate(groups: pd.Series, persons: pd.Series) -> PairwiseScore:
    """Precisión y recall por pares frente al solucionario (persona real de cada registro)."""
    df = pd.DataFrame({"g": groups.values, "p": persons.values})
    return PairwiseScore(_pairs_count(df.groupby("p").size()),
                         _pairs_count(df.groupby("g").size()),
                         _pairs_count(df.groupby(["g", "p"]).size()))
