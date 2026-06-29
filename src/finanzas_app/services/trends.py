"""
Tendencias históricas — alimenta la pestaña de "Resumen y tendencias":
fijos vs. variables mes a mes, y la curva de ahorro acumulado.

Consume el DataFrame que produce
repository.get_all_months_summary_df(), que ya trae un total por mes.
"""

from __future__ import annotations

import pandas as pd


def add_month_label(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Agrega una columna 'month_label' tipo 'Jun 2026' para usar en ejes de gráfica.

    Espera que summary_df tenga columnas year y month (1-12).
    """
    if summary_df.empty:
        return summary_df.assign(month_label=[])

    month_names = [
        "Ene", "Feb", "Mar", "Abr", "May", "Jun",
        "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
    ]
    df = summary_df.copy()
    df["month_label"] = df.apply(
        lambda row: f"{month_names[int(row['month']) - 1]} {int(row['year'])}", axis=1
    )
    return df


def add_cumulative_savings(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columnas de balance mensual y ahorro/inversión acumulado neto.

    Requiere que summary_df ya tenga: total_income, total_fixed,
    total_variable, total_invested, total_withdrawn, total_return
    (en orden cronológico). Si total_withdrawn o total_return no existen
    (datos antiguos), se asumen 0.

    Agrega:
        month_balance         -> income - fixed - variable, por mes
        net_invested          -> total_invested - total_withdrawn + total_return, por mes
        cumulative_invested   -> suma acumulada de net_invested (ahorro neto)
        cumulative_balance    -> suma acumulada de month_balance

    El rendimiento (total_return) se suma porque, si lo capturaste, es
    ganancia ya generada y se considera parte de tu ahorro real. Si no
    capturas un monto de rendimiento, cuenta como 0 y no afecta el total.
    """
    if summary_df.empty:
        return summary_df.assign(
            month_balance=[], net_invested=[],
            cumulative_invested=[], cumulative_balance=[],
        )

    df = summary_df.copy()
    if "total_withdrawn" not in df.columns:
        df["total_withdrawn"] = 0.0
    if "total_return" not in df.columns:
        df["total_return"] = 0.0

    df["month_balance"] = (
        df["total_income"] - df["total_fixed"] - df["total_variable"]
    ).round(2)
    df["net_invested"] = (df["total_invested"] - df["total_withdrawn"] + df["total_return"]).round(2)
    df["cumulative_invested"] = df["net_invested"].cumsum().round(2)
    df["cumulative_balance"] = df["month_balance"].cumsum().round(2)
    return df


def detect_rising_categories(
    pivot_df: pd.DataFrame, threshold_pct: float = 15.0
) -> pd.DataFrame:
    """Detecta categorías cuyo gasto creció más de threshold_pct entre
    el primer y el último mes disponibles en pivot_df.

    pivot_df: salida de categorization.compare_categories_across_months()
        (filas = categoría, columnas = meses en orden cronológico, + columna 'category')

    Devuelve un DataFrame con: category, first_month_amount,
    last_month_amount, pct_change — solo las que subieron por encima
    del umbral, ordenadas de mayor a menor incremento.
    """
    if pivot_df.empty or "category" not in pivot_df.columns:
        return pd.DataFrame(
            columns=["category", "first_month_amount", "last_month_amount", "pct_change"]
        )

    month_columns = [c for c in pivot_df.columns if c != "category"]
    if len(month_columns) < 2:
        return pd.DataFrame(
            columns=["category", "first_month_amount", "last_month_amount", "pct_change"]
        )

    first_col, last_col = month_columns[0], month_columns[-1]
    result = pivot_df[["category", first_col, last_col]].copy()
    result.columns = ["category", "first_month_amount", "last_month_amount"]

    def _pct_change(row) -> float | None:
        if row["first_month_amount"] == 0:
            return None
        return round(
            (row["last_month_amount"] - row["first_month_amount"])
            / row["first_month_amount"]
            * 100,
            1,
        )

    result["pct_change"] = result.apply(_pct_change, axis=1)
    rising = result[
        result["pct_change"].notna() & (result["pct_change"] >= threshold_pct)
    ]
    return rising.sort_values("pct_change", ascending=False).reset_index(drop=True)


def filter_by_date_range(
    summary_df: pd.DataFrame, start_date: str | None, end_date: str | None
) -> pd.DataFrame:
    """Filtra el resumen histórico a un rango de fechas (inclusive).

    start_date / end_date: strings 'YYYY-MM-DD' o None para no acotar
    ese extremo (None en start_date = desde el inicio del historial;
    None en end_date = hasta el mes más reciente).

    IMPORTANTE: si vas a graficar el acumulado de ahorro
    (cumulative_invested / cumulative_balance), llama primero a
    add_cumulative_savings() sobre el DataFrame COMPLETO (sin filtrar)
    y filtra DESPUÉS con esta función. Si filtras antes, el acumulado
    se recalcularía desde cero a partir del rango, perdiendo el ahorro
    acumulado de los meses anteriores al rango — mostraría un número
    menor al real.
    """
    if summary_df.empty:
        return summary_df

    df = summary_df.copy()
    period = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).astype(str) + "-01"
    )

    if start_date:
        df = df[period >= pd.to_datetime(start_date)]
        period = period[period >= pd.to_datetime(start_date)]
    if end_date:
        df = df[period <= pd.to_datetime(end_date)]

    return df.reset_index(drop=True)
