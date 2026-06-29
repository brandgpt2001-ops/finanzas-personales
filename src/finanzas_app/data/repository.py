"""
Capa repository: traduce las tablas SQLite a DataFrames de pandas.

Esta es la interfaz que va a usar la capa de servicios (services/).
Nadie fuera de data/ debería escribir SQL directamente.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

_QUERIES = {
    "income": """
        SELECT id, month_id, category, amount, created_at
        FROM income_entries WHERE month_id = ?
    """,
    "variable": """
        SELECT id, month_id, category, amount, created_at
        FROM variable_expenses WHERE month_id = ?
    """,
}


def get_entries_df(conn: sqlite3.Connection, kind: str, month_id: int) -> pd.DataFrame:
    """Devuelve income o variable de un mes como DataFrame.

    Columnas: id, month_id, category, amount, created_at
    Para gastos fijos usa get_fixed_expenses_for_month en su lugar,
    ya que estos no se capturan por mes sino que se derivan de
    fixed_expense_definitions según la fecha de vigencia.
    """
    query = _QUERIES[kind]
    df = pd.read_sql_query(query, conn, params=(month_id,))
    return df


def get_fixed_expenses_for_month(
    conn: sqlite3.Connection, year: int, month: int
) -> pd.DataFrame:
    """Devuelve los gastos fijos vigentes durante un año/mes específico.

    A diferencia de income/variable, esto NO se busca por month_id en una
    tabla de capturas — se calcula a partir de fixed_expense_definitions,
    encontrando qué versión de cada gasto fijo estaba vigente durante ese
    mes calendario completo.

    Columnas: group_id, category, amount
    Una fila por cada gasto fijo (group_id) vigente en algún momento de
    ese mes. Si un gasto cambió de monto a mitad del mes, se usa el monto
    vigente al ÚLTIMO día del mes (criterio simple y predecible).
    """
    # Último día del mes en cuestión, en formato ISO "YYYY-MM-DD"
    if month == 12:
        next_month_first_day = f"{year + 1}-01-01"
    else:
        next_month_first_day = f"{year}-{month + 1:02d}-01"

    query = """
        SELECT group_id, category, amount
        FROM fixed_expense_definitions
        WHERE valid_from < ?
          AND (valid_to IS NULL OR valid_to > ?)
    """
    # as_of = primer día del mes siguiente; una versión "vigente al cierre
    # del mes" debe haber empezado antes de esa fecha y no haber cerrado
    # en o antes del inicio del mes en cuestión (valid_to > month_start,
    # no >=, para no contar dos veces el día exacto de un cambio).
    month_start = f"{year}-{month:02d}-01"
    df = pd.read_sql_query(
        query, conn, params=(next_month_first_day, month_start)
    )
    return df


def get_fixed_expenses_history_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Devuelve TODO el historial de versiones de gastos fijos, sin filtrar.

    Columnas: id, group_id, category, amount, valid_from, valid_to
    Útil para auditar cambios o construir una vista de "historial de Renta".
    """
    query = """
        SELECT id, group_id, category, amount, valid_from, valid_to
        FROM fixed_expense_definitions
        ORDER BY group_id, valid_from
    """
    return pd.read_sql_query(query, conn)


def get_investments_df(conn: sqlite3.Connection, month_id: int) -> pd.DataFrame:
    """Devuelve las inversiones de un mes como DataFrame.

    Columnas: id, month_id, instrument, amount, return_amount, is_mandatory, created_at
    is_mandatory llega como 0/1 desde SQLite; se expone como bool de pandas.
    """
    query = """
        SELECT id, month_id, instrument, amount, return_amount, is_mandatory, created_at
        FROM investments WHERE month_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(month_id,))
    if not df.empty:
        df["is_mandatory"] = df["is_mandatory"].astype(bool)
    return df


def get_withdrawals_df(conn: sqlite3.Connection, month_id: int) -> pd.DataFrame:
    """Devuelve los retiros de inversión de un mes como DataFrame.

    Columnas: id, month_id, instrument, amount, created_at
    """
    query = """
        SELECT id, month_id, instrument, amount, created_at
        FROM investment_withdrawals WHERE month_id = ?
    """
    return pd.read_sql_query(query, conn, params=(month_id,))


def get_all_months_summary_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Devuelve un resumen agregado de TODOS los meses, uno por fila.

    Columnas: month_id, year, month,
              total_income, total_fixed, total_variable,
              total_invested, total_invested_mandatory, total_invested_discretionary,
              total_return, total_withdrawn
    Útil para la pestaña de tendencias históricas.

    total_fixed se calcula por mes a partir de fixed_expense_definitions
    (vigencia histórica), no de una tabla de capturas mensuales.
    """
    months_df = pd.read_sql_query(
        "SELECT id AS month_id, year, month FROM months ORDER BY year, month", conn
    )
    numeric_cols = [
        "total_income", "total_fixed", "total_variable",
        "total_invested", "total_invested_mandatory", "total_invested_discretionary",
        "total_return", "total_withdrawn",
    ]
    if months_df.empty:
        return months_df.assign(**{col: [] for col in numeric_cols})

    # Cada tabla hija se agrega por separado y se une en pandas, para evitar
    # productos cartesianos al hacer JOIN directo de varias tablas 1-a-muchos.
    income_totals = pd.read_sql_query(
        "SELECT month_id, SUM(amount) AS total_income FROM income_entries GROUP BY month_id",
        conn,
    )
    variable_totals = pd.read_sql_query(
        "SELECT month_id, SUM(amount) AS total_variable FROM variable_expenses GROUP BY month_id",
        conn,
    )
    investment_totals = pd.read_sql_query(
        """
        SELECT month_id,
               SUM(amount) AS total_invested,
               SUM(CASE WHEN is_mandatory = 1 THEN amount ELSE 0 END) AS total_invested_mandatory,
               SUM(CASE WHEN is_mandatory = 0 THEN amount ELSE 0 END) AS total_invested_discretionary,
               SUM(return_amount) AS total_return
        FROM investments GROUP BY month_id
        """,
        conn,
    )
    withdrawal_totals = pd.read_sql_query(
        "SELECT month_id, SUM(amount) AS total_withdrawn FROM investment_withdrawals GROUP BY month_id",
        conn,
    )

    result = months_df
    for totals_df in (income_totals, variable_totals, investment_totals, withdrawal_totals):
        result = result.merge(totals_df, on="month_id", how="left")

    # total_fixed se calcula aparte: una llamada por cada (year, month)
    # combinación presente en months_df, usando la vigencia histórica.
    fixed_per_month = []
    for _, row in months_df.iterrows():
        fixed_df = get_fixed_expenses_for_month(conn, int(row["year"]), int(row["month"]))
        total = float(fixed_df["amount"].sum()) if not fixed_df.empty else 0.0
        fixed_per_month.append({"month_id": row["month_id"], "total_fixed": total})
    fixed_totals = pd.DataFrame(fixed_per_month)

    result = result.merge(fixed_totals, on="month_id", how="left")
    result[numeric_cols] = result[numeric_cols].fillna(0.0).astype("float64")
    return result
