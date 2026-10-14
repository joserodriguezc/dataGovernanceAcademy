"""Variaciones realistas con las que un mismo dato llega distinto a cada sistema."""

import re
import unicodedata

import numpy as np


def strip_accents(text: str) -> str:
    """'José Núñez' -> 'Jose Nunez'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def slug(text: str) -> str:
    """Texto apto para la parte local de un email: 'María José' -> 'mariajose'."""
    return re.sub(r"[^a-z]", "", strip_accents(text).lower())


def typo(text: str, rng: np.random.Generator) -> str:
    """Intercambia dos letras contiguas de una palabra (errata típica de tecleo)."""
    if len(text) < 4:
        return text
    i = int(rng.integers(1, len(text) - 2))
    return text[:i] + text[i + 1] + text[i] + text[i + 2:]


def phone_format(digits: str, style: str) -> str:
    """Formatea un móvil de 9 dígitos con el estilo de cada sistema."""
    if style == "international":  # CRM
        return f"+34 {digits[:3]} {digits[3:6]} {digits[6:]}"
    if style == "dashes":  # tiendas
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return digits  # e-commerce: solo dígitos


def invalid_postal(rng: np.random.Generator) -> str:
    """Código postal con un error típico: le falta un dígito o lleva letras."""
    if rng.random() < 0.5:
        return str(int(rng.integers(1000, 9999)))
    return f"{int(rng.integers(10, 99))}A{int(rng.integers(10, 99))}"


def pick(n: int, rate: float, rng: np.random.Generator) -> set[int]:
    """Elige exactamente round(n × rate) posiciones distintas."""
    k = round(n * rate)
    return set(rng.choice(n, size=k, replace=False).tolist()) if k else set()
