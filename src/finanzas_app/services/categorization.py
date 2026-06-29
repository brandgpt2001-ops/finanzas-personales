"""
Agregaciones por categoría — la base de las gráficas de distribución
de gastos fijos y variables, y para detectar dónde recortar.
"""

from __future__ import annotations

import pandas as pd


def totals_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa un DataFrame de entradas (income/fixed/variable) por category.

    Devuelve un DataFrame con columnas: category, amount, pct
    ordenado de mayor a menor monto. pct es el porcentaje que cada
    categoría representa del total (0-100).
    """
    if df.empty:
        return pd.DataFrame(columns=["category", "amount", "pct"])

    grouped = (
        df.groupby("category", as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
        .reset_index(drop=True)
    )
    total = grouped["amount"].sum()
    grouped["pct"] = (
        (grouped["amount"] / total * 100).round(1) if total > 0 else 0.0
    )
    return grouped


def top_categories(df: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Devuelve las n categorías con mayor gasto. Útil para sugerir dónde recortar."""
    agg = totals_by_category(df)
    return agg.head(n)


def compare_categories_across_months(
    monthly_dfs: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Compara el gasto por categoría entre varios meses.

    monthly_dfs: diccionario {etiqueta_de_mes: DataFrame de entradas}
        ej. {"2026-05": df_mayo, "2026-06": df_junio}

    Devuelve un DataFrame pivote: filas = categorías, columnas = meses,
    valores = monto total. Categorías ausentes en un mes quedan en 0.
    Útil para ver si una categoría está creciendo mes a mes.
    """
    frames = []
    for month_label, df in monthly_dfs.items():
        agg = totals_by_category(df)[["category", "amount"]]
        agg["month"] = month_label
        frames.append(agg)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    pivot = combined.pivot_table(
        index="category", columns="month", values="amount", fill_value=0.0
    )
    return pivot.reset_index()
