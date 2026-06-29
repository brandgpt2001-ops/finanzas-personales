"""
Cálculos centrales del presupuesto mensual.

Estas funciones reciben DataFrames (típicamente desde repository.py)
y devuelven totales y balances. No tocan SQL ni la UI.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MonthlyBudgetSummary:
    """Resumen de un mes, listo para mostrarse en el dashboard."""

    total_income: float
    total_fixed: float
    available_after_fixed: float
    total_variable: float
    month_balance: float
    total_invested: float
    total_invested_mandatory: float
    total_invested_discretionary: float
    available_for_discretionary: float
    total_return: float
    total_withdrawn: float
    net_savings_this_month: float

    def as_dict(self) -> dict:
        return {
            "total_income": self.total_income,
            "total_fixed": self.total_fixed,
            "available_after_fixed": self.available_after_fixed,
            "total_variable": self.total_variable,
            "month_balance": self.month_balance,
            "total_invested": self.total_invested,
            "total_invested_mandatory": self.total_invested_mandatory,
            "total_invested_discretionary": self.total_invested_discretionary,
            "available_for_discretionary": self.available_for_discretionary,
            "total_return": self.total_return,
            "total_withdrawn": self.total_withdrawn,
            "net_savings_this_month": self.net_savings_this_month,
        }


def _safe_sum(df: pd.DataFrame, column: str) -> float:
    """Suma una columna numérica, devolviendo 0.0 si el DataFrame está vacío."""
    if df.empty or column not in df.columns:
        return 0.0
    return round(float(df[column].sum()), 2)


def compute_monthly_summary(
    income_df: pd.DataFrame,
    fixed_df: pd.DataFrame,
    variable_df: pd.DataFrame,
    investments_df: pd.DataFrame,
    withdrawals_df: pd.DataFrame | None = None,
) -> MonthlyBudgetSummary:
    """Calcula todos los totales y balances de un mes.

    Reglas de negocio:
        available_after_fixed = total_income - total_fixed
        month_balance = available_after_fixed - total_variable
        available_for_discretionary =
            available_after_fixed - total_invested_mandatory - total_variable

    available_for_discretionary trata las inversiones obligatorias
    (ej. el aporte recurrente a tu empresa) casi como un gasto fijo más:
    es el número real que te queda para gastos variables y, si alcanza,
    inversión discrecional.

    net_savings_this_month = total_invested - total_withdrawn + total_return
    Mide cuánto creció tu ahorro neto este mes: lo que aportaste, menos lo
    que retiraste, más el rendimiento generado (si lo capturaste). Si no
    capturas rendimiento, cuenta como 0 y no afecta el cálculo.

    Nota: month_balance NO resta inversiones (igual que antes). Para ver
    el efecto de las inversiones obligatorias en lo que te queda libre,
    usa available_for_discretionary.
    """
    total_income = _safe_sum(income_df, "amount")
    total_fixed = _safe_sum(fixed_df, "amount")
    total_variable = _safe_sum(variable_df, "amount")
    total_return = _safe_sum(investments_df, "return_amount")
    total_withdrawn = _safe_sum(withdrawals_df, "amount") if withdrawals_df is not None else 0.0

    if investments_df is None or investments_df.empty:
        total_invested = 0.0
        total_invested_mandatory = 0.0
        total_invested_discretionary = 0.0
    else:
        total_invested = round(float(investments_df["amount"].sum()), 2)
        mandatory_mask = investments_df["is_mandatory"].astype(bool)
        total_invested_mandatory = round(float(investments_df.loc[mandatory_mask, "amount"].sum()), 2)
        total_invested_discretionary = round(total_invested - total_invested_mandatory, 2)

    available_after_fixed = round(total_income - total_fixed, 2)
    month_balance = round(available_after_fixed - total_variable, 2)
    available_for_discretionary = round(
        available_after_fixed - total_invested_mandatory - total_variable, 2
    )
    net_savings_this_month = round(total_invested - total_withdrawn + total_return, 2)

    return MonthlyBudgetSummary(
        total_income=total_income,
        total_fixed=total_fixed,
        available_after_fixed=available_after_fixed,
        total_variable=total_variable,
        month_balance=month_balance,
        total_invested=total_invested,
        total_invested_mandatory=total_invested_mandatory,
        total_invested_discretionary=total_invested_discretionary,
        available_for_discretionary=available_for_discretionary,
        total_return=total_return,
        total_withdrawn=total_withdrawn,
        net_savings_this_month=net_savings_this_month,
    )


def fixed_expense_ratio(summary: MonthlyBudgetSummary) -> float | None:
    """Porcentaje del ingreso que se va a gastos fijos. None si no hay ingreso."""
    if summary.total_income == 0:
        return None
    return round((summary.total_fixed / summary.total_income) * 100, 1)


def variable_expense_ratio(summary: MonthlyBudgetSummary) -> float | None:
    """Porcentaje del ingreso que se va a gastos variables. None si no hay ingreso."""
    if summary.total_income == 0:
        return None
    return round((summary.total_variable / summary.total_income) * 100, 1)


def savings_rate(summary: MonthlyBudgetSummary) -> float | None:
    """Porcentaje del ingreso que se destinó a inversión/ahorro. None si no hay ingreso."""
    if summary.total_income == 0:
        return None
    return round((summary.total_invested / summary.total_income) * 100, 1)
