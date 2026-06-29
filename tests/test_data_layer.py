"""Pruebas de finanzas_app.data.db y finanzas_app.data.repository"""

from finanzas_app.data import db, repository


class TestMonths:
    def test_crea_mes_si_no_existe(self, conn):
        month_id = db.get_or_create_month(conn, 2026, 6)
        assert month_id is not None

    def test_no_duplica_el_mismo_mes(self, conn):
        id1 = db.get_or_create_month(conn, 2026, 6)
        id2 = db.get_or_create_month(conn, 2026, 6)
        assert id1 == id2


class TestIncomeAndVariableEntries:
    def test_agrega_y_lee_ingresos(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "income", mid, "Sueldo", 25000)
        df = repository.get_entries_df(conn, "income", mid)
        assert len(df) == 1
        assert df.iloc[0]["category"] == "Sueldo"
        assert df.iloc[0]["amount"] == 25000

    def test_categorias_sucias_se_normalizan_y_agrupan(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "variable", mid, "  comida   rica  ", 100)
        db.add_entry(conn, "variable", mid, "COMIDA RICA", 200)
        df = repository.get_entries_df(conn, "variable", mid)
        grouped = df.groupby("category")["amount"].sum()
        assert len(grouped) == 1
        assert grouped.iloc[0] == 300

    def test_update_entry(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        entry_id = db.add_entry(conn, "income", mid, "Sueldo", 25000)
        db.update_entry(conn, "income", entry_id, "Sueldo", 27000)
        df = repository.get_entries_df(conn, "income", mid)
        assert df.iloc[0]["amount"] == 27000

    def test_delete_entry(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        entry_id = db.add_entry(conn, "income", mid, "Sueldo", 25000)
        db.delete_entry(conn, "income", entry_id)
        df = repository.get_entries_df(conn, "income", mid)
        assert df.empty


class TestFixedExpenseDefinitions:
    def test_gasto_fijo_aparece_en_meses_sin_captura_manual(self, conn):
        db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-01-01")
        df = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        assert len(df) == 1
        assert df.iloc[0]["amount"] == 8000

    def test_cambio_de_monto_no_afecta_meses_pasados(self, conn):
        group_id = db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-01-01")
        db.update_fixed_expense_definition(conn, group_id, "Renta", 8500, effective_date="2026-07-01")

        junio = repository.get_fixed_expenses_for_month(conn, 2026, 6)
        julio = repository.get_fixed_expenses_for_month(conn, 2026, 7)

        assert junio.iloc[0]["amount"] == 8000
        assert julio.iloc[0]["amount"] == 8500

    def test_no_duplica_version_en_el_mes_de_transicion(self, conn):
        group_id = db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-01-01")
        db.update_fixed_expense_definition(conn, group_id, "Renta", 8500, effective_date="2026-07-01")

        julio = repository.get_fixed_expenses_for_month(conn, 2026, 7)
        assert len(julio) == 1
        assert julio.iloc[0]["amount"] == 8500

    def test_eliminar_gasto_fijo_no_afecta_meses_pasados(self, conn):
        group_id = db.add_fixed_expense_definition(conn, "Internet", 600, valid_from="2026-01-01")
        db.deactivate_fixed_expense_definition(conn, group_id, effective_date="2026-08-01")

        julio = repository.get_fixed_expenses_for_month(conn, 2026, 7)
        agosto = repository.get_fixed_expenses_for_month(conn, 2026, 8)

        assert len(julio) == 1
        assert agosto.empty

    def test_mes_anterior_a_la_creacion_no_lo_incluye(self, conn):
        db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-06-01")
        mayo = repository.get_fixed_expenses_for_month(conn, 2026, 5)
        assert mayo.empty


class TestInvestmentsAndWithdrawals:
    def test_distingue_obligatoria_de_discrecional(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_investment(conn, mid, "Empresa", 3000, is_mandatory=True)
        db.add_investment(conn, mid, "CETES", 1500, is_mandatory=False)

        df = repository.get_investments_df(conn, mid)
        mandatory_total = df[df["is_mandatory"]]["amount"].sum()
        discretionary_total = df[~df["is_mandatory"]]["amount"].sum()

        assert mandatory_total == 3000
        assert discretionary_total == 1500

    def test_return_amount_opcional_default_cero(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_investment(conn, mid, "CETES", 1000)
        df = repository.get_investments_df(conn, mid)
        assert df.iloc[0]["return_amount"] == 0.0

    def test_retiro_se_registra_por_separado(self, conn):
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_withdrawal(conn, mid, "CETES viejo", 500)
        df = repository.get_withdrawals_df(conn, mid)
        assert len(df) == 1
        assert df.iloc[0]["amount"] == 500


class TestAllMonthsSummary:
    def test_resumen_incluye_fijos_calculados_por_vigencia(self, conn):
        db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-01-01")
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "income", mid, "Sueldo", 25000)

        summary_df = repository.get_all_months_summary_df(conn)
        row = summary_df.iloc[0]

        assert row["total_fixed"] == 8000
        assert row["total_income"] == 25000

    def test_dataframe_vacio_sin_meses(self, conn):
        summary_df = repository.get_all_months_summary_df(conn)
        assert summary_df.empty

    def test_columnas_numericas_son_float64_no_object(self, conn):
        """Las columnas numéricas deben ser float64 real, no 'object'.

        Si esto regresa a dtype object (ej. por un fillna que no castea),
        operaciones de matplotlib como fill_between fallan en runtime con
        un TypeError críptico. Ver el bug que motivó este fix.
        """
        db.add_fixed_expense_definition(conn, "Renta", 8000, valid_from="2026-01-01")
        mid = db.get_or_create_month(conn, 2026, 6)
        db.add_entry(conn, "income", mid, "Sueldo", 25000)

        summary_df = repository.get_all_months_summary_df(conn)
        numeric_cols = [
            "total_income", "total_fixed", "total_variable",
            "total_invested", "total_invested_mandatory", "total_invested_discretionary",
            "total_return", "total_withdrawn",
        ]
        for col in numeric_cols:
            assert summary_df[col].dtype == "float64", f"{col} tiene dtype {summary_df[col].dtype}, esperado float64"
