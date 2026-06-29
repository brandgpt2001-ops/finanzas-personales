"""
Normalización y validación de datos de entrada.

Toda entrada que llegue a la base de datos pasa por aquí primero.
El objetivo es que "Comida", "comida ", "  COMIDA" y "comida  rica"
no se conviertan en categorías distintas al momento de agregarlas
en reportes y gráficas.
"""

from __future__ import annotations

import re

DEFAULT_CATEGORY = "Sin categoría"

_MULTI_SPACE_RE = re.compile(r"\s+")

# Palabras que en español NO deberían capitalizarse en Title Case
# (preposiciones y artículos comunes en nombres de categorías)
_LOWERCASE_WORDS = {"de", "del", "la", "el", "los", "las", "y", "en", "a"}


class ValidationError(ValueError):
    """Error de validación de datos de entrada, con mensaje listo para mostrar en UI."""


def clean_category(raw: str | None) -> str:
    """Normaliza un nombre de categoría o instrumento.

    - Quita espacios extra (inicio, final, e internos duplicados)
    - Aplica Title Case respetando preposiciones/artículos en minúscula
    - Si queda vacío, devuelve la categoría por defecto
    """
    if raw is None:
        return DEFAULT_CATEGORY

    collapsed = _MULTI_SPACE_RE.sub(" ", raw.strip())
    if not collapsed:
        return DEFAULT_CATEGORY

    words = collapsed.split(" ")
    titled = [
        word.lower() if word.lower() in _LOWERCASE_WORDS and i > 0 else word.capitalize()
        for i, word in enumerate(words)
    ]
    return " ".join(titled)


def clean_amount(raw: float | str | None, *, field_name: str = "monto") -> float:
    """Normaliza un monto a float redondeado a 2 decimales.

    Acepta números, o strings como "1,234.50" o "1234,50".
    Lanza ValidationError si no se puede convertir o si es negativo.
    """
    if raw is None or raw == "":
        raise ValidationError(f"El {field_name} no puede estar vacío.")

    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = raw.strip()
        # Si tiene coma Y punto, asumimos que la coma es separador de miles: "1,234.50"
        if "," in text and "." in text:
            text = text.replace(",", "")
        # Si solo tiene coma, asumimos que es separador decimal: "1234,50"
        elif "," in text:
            text = text.replace(",", ".")
        try:
            value = float(text)
        except ValueError as exc:
            raise ValidationError(
                f"El {field_name} '{raw}' no es un número válido."
            ) from exc

    if value < 0:
        raise ValidationError(f"El {field_name} no puede ser negativo.")

    return round(value, 2)


def clean_year(raw: int | str) -> int:
    try:
        year = int(raw)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Año inválido: '{raw}'.") from exc
    if year < 2000 or year > 2100:
        raise ValidationError(f"Año fuera de rango razonable: {year}.")
    return year


def clean_month(raw: int | str) -> int:
    try:
        month = int(raw)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Mes inválido: '{raw}'.") from exc
    if month < 1 or month > 12:
        raise ValidationError(f"Mes fuera de rango (1-12): {month}.")
    return month


def clean_bool(raw: bool | int | str | None) -> bool:
    """Normaliza un valor a booleano para campos tipo is_mandatory.

    Acepta True/False, 1/0, o strings comunes como "si"/"no", "true"/"false".
    None se interpreta como False.
    """
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw != 0
    text = str(raw).strip().lower()
    if text in {"true", "1", "si", "sí", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise ValidationError(f"Valor booleano inválido: '{raw}'.")
