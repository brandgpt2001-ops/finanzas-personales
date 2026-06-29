"""Pruebas de finanzas_app.services (budget, categorization, trends)"""

import pandas as pd

from finanzas_app.data import db, repository
from finanzas_app.services import budget, categorization, trends


class TestBudgetSummary:
    def test_disponible_tras_fijos(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "income", mid, "Sueldo", 25000)
        db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-01-01")

        income_df = repository.get_entries_df(conn, "income", mid)
        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df)
        assert summary.total_income == 25000
        assert summary.total_fixed == 8000
        assert summary.available_after_fixed == 17000

    def test_available_for_discretionary_resta_inversion_obligatoria(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "income", mid, "Sueldo", 25000)
        db.add_investment(conn, mid, "Empresa", 3000, is_mandatory=True)
        db.add_investment(conn, mid, "CETES", 1500, is_mandatory=False)

        income_df = repository.get_entries_df(conn, "income", mid)
        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df)
        # available_after_fixed (25000) - mandatory (3000) - variable (0)
        assert summary.available_for_discretionary == 22000
        # la discrecional NO debe restarse de available_for_discretionary
        assert summary.total_invested_discretionary == 1500

    def test_net_savings_resta_retiros(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_investment(conn, mid, "CETES", 2000)
        db.add_withdrawal(conn, mid, "CETES viejo", 500)

        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        income_df = repository.get_entries_df(conn, "income", mid)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)
        wd_df = repository.get_withdrawals_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df, wd_df)
        assert summary.net_savings_this_month == 1500

    def test_net_savings_suma_rendimiento_capturado(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_investment(conn, mid, "CETES", 1200, return_amount=1212)

        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        income_df = repository.get_entries_df(conn, "income", mid)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)
        wd_df = repository.get_withdrawals_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df, wd_df)
        # 1200 aportado - 0 retirado + 1212 de rendimiento capturado
        assert summary.net_savings_this_month == 2412

    def test_net_savings_sin_rendimiento_capturado_no_suma_nada(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_investment(conn, mid, "CETES", 1200)  # sin return_amount

        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        income_df = repository.get_entries_df(conn, "income", mid)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)
        wd_df = repository.get_withdrawals_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df, wd_df)
        assert summary.net_savings_this_month == 1200

    def test_mes_vacio_no_falla(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        income_df = repository.get_entries_df(conn, "income", mid)
        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df)
        assert summary.total_income == 0
        assert summary.month_balance == 0

    def test_ratios_none_sin_ingreso(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        income_df = repository.get_entries_df(conn, "income", mid)
        fixed_df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        variable_df = repository.get_entries_df(conn, "variable", mid)
        inv_df = repository.get_investments_df(conn, mid)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df)
        assert budget.fixed_expense_ratio(summary) is None
        assert budget.savings_rate(summary) is None


class TestCategorization:
    def test_totals_by_category_ordena_descendente(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "variable", mid, "Ocio", 500)
        db.add_entry(conn, "variable", mid, "Comida", 3000)
        db.add_entry(conn, "variable", mid, "Transporte", 900)

        df = repository.get_entries_df(conn, "variable", mid)
        result = categorization.totals_by_category(df)

        assert result.iloc[0]["category"] == "Comida"
        assert result.iloc[0]["pct"] > result.iloc[1]["pct"]

    def test_dataframe_vacio_no_falla(self):
        empty = pd.DataFrame(columns=["category", "amount"])
        result = categorization.totals_by_category(empty)
        assert result.empty

    def test_top_categories_respeta_n(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        for cat, amt in [("A", 100), ("B", 300), ("C", 200), ("D", 50)]:
            db.add_entry(conn, "variable", mid, cat, amt)
        df = repository.get_entries_df(conn, "variable", mid)
        top2 = categorization.top_categories(df, n=2)
        assert len(top2) == 2
        assert list(top2["category"]) == ["B", "C"]


class TestTrends:
    def test_cumulative_invested_resta_retiros(self, conn):
        mid_abr = db.get_or_create_month(conn, 2026, 4)
        db.add_investment(conn, mid_abr, "CETES", 2000)

        mid_may = db.get_or_create_month(conn, 2026, 5)
        db.add_investment(conn, mid_may, "CETES", 2000)
        db.add_withdrawal(conn, mid_may, "CETES", 500)

        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_cumulative_savings(summary_df)

        assert summary_df.iloc[0]["cumulative_invested"] == 2000
        assert summary_df.iloc[1]["cumulative_invested"] == 3500

    def test_cumulative_invested_suma_rendimiento(self, conn):
        mid_abr = db.get_or_create_month(conn, 2026, 4)
        db.add_investment(conn, mid_abr, "CETES", 1200, return_amount=1212)

        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_cumulative_savings(summary_df)

        # 1200 aportado + 1212 de rendimiento capturado = 2412 acumulado
        assert summary_df.iloc[0]["cumulative_invested"] == 2412

    def test_detect_rising_categories(self):
        pivot = pd.DataFrame({
            "category": ["Comida", "Ocio", "Transporte"],
            "2026-04": [2500, 800, 900],
            "2026-06": [3400, 1200, 950],
        })
        rising = trends.detect_rising_categories(pivot, threshold_pct=15.0)
        categories = list(rising["category"])
        assert "Comida" in categories
        assert "Ocio" in categories
        assert "Transporte" not in categories

    def test_month_label_formato(self, conn):
        db.get_or_create_month(conn, 2026, 6)
        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_month_label(summary_df)
        assert summary_df.iloc[0]["month_label"] == "Jun 2026"


class TestFilterByDateRange:
    def test_filtra_por_rango_inclusive(self, conn):
        for month in [1, 2, 3, 4]:
            mid = db.get_or_create_month(conn, 2026, month)
            db.add_investment(conn, mid, "CETES", 1000)

        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_month_label(summary_df)

        filtered = trends.filter_by_date_range(summary_df, "2026-02-01", "2026-03-31")
        assert list(filtered["month_label"]) == ["Feb 2026", "Mar 2026"]

    def test_acumulado_no_se_pierde_al_filtrar_si_se_calcula_antes(self, conn):
        """Caso crítico: el acumulado debe calcularse sobre el historial
        completo ANTES de filtrar, para no perder el ahorro de meses
        anteriores al rango seleccionado."""
        for month in [1, 2, 3, 4]:
            mid = db.get_or_create_month(conn, 2026, month)
            db.add_investment(conn, mid, "CETES", 1000)

        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_cumulative_savings(summary_df)  # ANTES de filtrar
        filtered = trends.filter_by_date_range(summary_df, "2026-03-01", "2026-04-30")

        # Marzo debe reflejar el acumulado real (ene+feb+mar = 3000), no 1000
        assert filtered.iloc[0]["cumulative_invested"] == 3000
        assert filtered.iloc[-1]["cumulative_invested"] == 4000

    def test_solo_start_date(self, conn):
        for month in [1, 2, 3]:
            db.get_or_create_month(conn, 2026, month)
        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_month_label(summary_df)

        filtered = trends.filter_by_date_range(summary_df, "2026-02-01", None)
        assert list(filtered["month_label"]) == ["Feb 2026", "Mar 2026"]

    def test_solo_end_date(self, conn):
        for month in [1, 2, 3]:
            db.get_or_create_month(conn, 2026, month)
        summary_df = repository.get_all_months_summary_df(conn)
        summary_df = trends.add_month_label(summary_df)

        filtered = trends.filter_by_date_range(summary_df, None, "2026-02-28")
        assert list(filtered["month_label"]) == ["Ene 2026", "Feb 2026"]

    def test_sin_filtros_devuelve_todo(self, conn):
        for month in [1, 2, 3]:
            db.get_or_create_month(conn, 2026, month)
        summary_df = repository.get_all_months_summary_df(conn)

        filtered = trends.filter_by_date_range(summary_df, None, None)
        assert len(filtered) == 3

    def test_rango_sin_resultados(self, conn):
        db.get_or_create_month(conn, 2026, 1)
        summary_df = repository.get_all_months_summary_df(conn)

        filtered = trends.filter_by_date_range(summary_df, "2027-01-01", "2027-12-31")
        assert filtered.empty

    def test_dataframe_vacio_no_falla(self):
        empty_df = pd.DataFrame()
        filtered = trends.filter_by_date_range(empty_df, "2026-01-01", "2026-12-31")
        assert filtered.empty
