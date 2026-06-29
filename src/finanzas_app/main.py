"""
Punto de entrada de la app. Ejecutar con: flet run src/finanzas_app/main.py

Navegación lateral con dos páginas:
  - Dashboard: ingresos, gastos fijos, gastos variables del mes, y un
    resumen rápido de inversiones obligatorias (no se gestionan aquí).
  - Ahorro: gestión completa de inversiones (obligatorias y
    discrecionales) y retiros, con un acumulado histórico siempre
    visible arriba, independiente del mes seleccionado.

Tema oscuro/claro alternable (ver views/theme.py). Gastos fijos vienen
de fixed_expense_definitions con vigencia histórica; las gráficas de
tendencia siguen pendientes.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from pathlib import Path

import flet as ft
import pandas as pd

from finanzas_app.data import db, repository
from finanzas_app.data import auth, backup
from finanzas_app.data.validation import ValidationError
from finanzas_app.models.schema import get_connection, init_db
from finanzas_app.reports import charts, pdf_export
from finanzas_app.services import budget, categorization, trends
from finanzas_app.views import login, theme

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "finanzas.db"

MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def build_main_app(page: ft.Page, conn, on_logout) -> None:
    """Construye el Dashboard/Ahorro/Tendencias completos. Se llama solo
    después de una autenticación exitosa (ver main() al final del archivo).

    on_logout: callback sin argumentos que main() usa para volver a
    mostrar la pantalla de login (se llama al cerrar sesión por
    inactividad)."""
    page.title = "Finanzas personales"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    today = date.today()
    palette = theme.get_palette(page.theme_mode)
    selected_page = {"index": 0}  # 0 = Dashboard, 1 = Ahorro

    INACTIVITY_TIMEOUT_SECONDS = 30 * 60
    last_activity = {"timestamp": time.monotonic()}
    session_active = {"value": True}

    def mark_activity() -> None:
        last_activity["timestamp"] = time.monotonic()

    # ------------------------------------------------------------------
    # Controles compartidos (selector de periodo, usado en ambas páginas)
    # ------------------------------------------------------------------
    month_dropdown = ft.Dropdown(
        label="Mes",
        width=160,
        value=str(today.month),
        options=[ft.dropdown.Option(str(i + 1), MONTH_NAMES[i]) for i in range(12)],
    )
    year_field = theme.styled_text_field("Año", palette, width=110)
    year_field.value = str(today.year)
    year_field.keyboard_type = ft.KeyboardType.NUMBER

    error_banner = ft.Text("", color=palette.negative, size=13)

    def get_current_month_id() -> int:
        return db.get_or_create_month(conn, int(year_field.value), int(month_dropdown.value))

    # ------------------------------------------------------------------
    # Controles de la página Dashboard
    # ------------------------------------------------------------------
    income_category_field = theme.styled_text_field("Categoría / fuente", palette, expand=True)
    income_amount_field = theme.styled_text_field("Monto", palette, width=140)

    variable_category_field = theme.styled_text_field("Categoría", palette, expand=True)
    variable_amount_field = theme.styled_text_field("Monto", palette, width=140)

    fixed_category_field = theme.styled_text_field("Categoría", palette, expand=True)
    fixed_amount_field = theme.styled_text_field("Monto", palette, width=140)

    metric_income = ft.Text("$0.00", size=22, weight=ft.FontWeight.W_500, color=palette.text_primary)
    metric_fixed = ft.Text("$0.00", size=22, weight=ft.FontWeight.W_500, color=palette.text_primary)
    metric_available = ft.Text("$0.00", size=22, weight=ft.FontWeight.W_500, color=palette.text_primary)
    metric_variable = ft.Text("$0.00", size=22, weight=ft.FontWeight.W_500, color=palette.text_primary)
    metric_balance = ft.Text("$0.00", size=22, weight=ft.FontWeight.W_500, color=palette.positive)
    metric_mandatory_invested = ft.Text("$0.00", size=22, weight=ft.FontWeight.W_500, color=palette.text_primary)

    storage_bar_ref: dict[str, ft.Row | None] = {"control": None}
    storage_bar_legend = ft.Row(spacing=16, wrap=True)
    storage_bar_warning = ft.Text("", size=12, color=palette.negative)

    fixed_list = ft.Column(spacing=6)
    income_summary = ft.Column(spacing=4)
    income_list = ft.Column(spacing=6)
    variable_summary = ft.Column(spacing=4)
    variable_list = ft.Column(spacing=6)

    balance_card_ref: dict[str, ft.Container | None] = {"control": None}

    # ------------------------------------------------------------------
    # Controles de la página Ahorro
    # ------------------------------------------------------------------
    investment_instrument_field = theme.styled_text_field("Instrumento", palette, expand=True)
    investment_amount_field = theme.styled_text_field("Aporte", palette, width=120)
    investment_return_field = theme.styled_text_field("Rendimiento (opcional)", palette, width=160)
    investment_mandatory_switch = ft.Switch(label="Obligatoria", value=False, active_color=palette.accent)

    withdrawal_instrument_field = theme.styled_text_field("Instrumento", palette, expand=True)
    withdrawal_amount_field = theme.styled_text_field("Monto retirado", palette, width=140)

    metric_cumulative_savings = ft.Text("$0.00", size=26, weight=ft.FontWeight.W_500, color=palette.positive)
    investment_list = ft.Column(spacing=6)
    withdrawal_list = ft.Column(spacing=6)
    investment_summary = ft.Column(spacing=4)
    savings_error_banner = ft.Text("", color=palette.negative, size=13)

    # ------------------------------------------------------------------
    # Controles de la página Tendencias
    # ------------------------------------------------------------------
    today_iso = today.isoformat()
    default_start = today.replace(year=today.year - 1).isoformat() if today.month != 2 or today.day != 29 else today.replace(year=today.year - 1, day=28).isoformat()
    trends_start_field = theme.styled_text_field("Desde (YYYY-MM-DD)", palette, width=180)
    trends_start_field.value = default_start
    trends_end_field = theme.styled_text_field("Hasta (YYYY-MM-DD)", palette, width=180)
    trends_end_field.value = today_iso

    trends_error_banner = ft.Text("", color=palette.negative, size=13)
    donut_image_ref: dict[str, ft.Image | None] = {"control": None}
    bars_image_ref: dict[str, ft.Image | None] = {"control": None}
    line_image_ref: dict[str, ft.Image | None] = {"control": None}
    donut_caption = ft.Text("", size=13, color=palette.text_secondary)
    bars_caption = ft.Text("", size=13, color=palette.text_secondary)
    line_caption = ft.Text("", size=13, color=palette.text_secondary)
    donut_container = ft.Container(alignment=ft.Alignment.CENTER)
    bars_container = ft.Container(alignment=ft.Alignment.CENTER)
    line_container = ft.Container(alignment=ft.Alignment.CENTER)

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------
    theme_icon_button = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE,
        icon_color=palette.text_secondary,
        tooltip="Cambiar tema",
    )

    export_pdf_picker = ft.FilePicker()
    export_pdf_button = ft.IconButton(
        icon=ft.Icons.PICTURE_AS_PDF_OUTLINED,
        icon_color=palette.text_secondary,
        tooltip="Exportar presupuesto a PDF",
    )
    export_error_text = ft.Text("", color=palette.negative, size=12)

    settings_name_password_field = theme.styled_text_field("Contraseña actual", palette, width=280)
    settings_name_password_field.password = True
    settings_name_password_field.can_reveal_password = True
    settings_name_new_field = theme.styled_text_field("Nombre nuevo", palette, width=280)
    settings_name_error = ft.Text("", color=palette.negative, size=12)
    settings_name_success = ft.Text("", color=palette.positive, size=12)

    settings_password_current_field = theme.styled_text_field("Contraseña actual", palette, width=280)
    settings_password_current_field.password = True
    settings_password_current_field.can_reveal_password = True
    settings_password_new_field = theme.styled_text_field("Contraseña nueva", palette, width=280)
    settings_password_new_field.password = True
    settings_password_new_field.can_reveal_password = True
    settings_password_confirm_field = theme.styled_text_field("Confirmar contraseña nueva", palette, width=280)
    settings_password_confirm_field.password = True
    settings_password_confirm_field.can_reveal_password = True
    settings_password_error = ft.Text("", color=palette.negative, size=12)
    settings_password_success = ft.Text("", color=palette.positive, size=12)

    settings_backup_status = ft.Text("", size=12)

    nav_rail_ref: dict[str, ft.NavigationRail | None] = {"control": None}
    page_root = ft.Container(expand=True)
    app_root = ft.Row(spacing=0, expand=True)

    # ------------------------------------------------------------------
    # Helpers de construcción de filas (reutilizados por ambas páginas)
    # ------------------------------------------------------------------
    def build_summary_rows(df) -> list[ft.Control]:
        agg = categorization.totals_by_category(df)
        if agg.empty:
            return [theme.caption("Sin movimientos todavía.", palette)]
        return [
            ft.Row(
                [
                    ft.Text(row["category"], size=13, color=palette.text_secondary, expand=True),
                    ft.Text(f"${row['amount']:,.2f}", size=13, weight=ft.FontWeight.W_500, color=palette.text_primary),
                ]
            )
            for _, row in agg.iterrows()
        ]

    def build_detail_rows(df, on_delete) -> list[ft.Control]:
        if df.empty:
            return []
        return [
            theme.row_card(
                ft.Text(row["category"], color=palette.text_primary, size=13, expand=True),
                ft.Text(f"${row['amount']:,.2f}", color=palette.text_secondary, size=13),
                palette,
                trailing=ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=16,
                    icon_color=palette.text_tertiary,
                    on_click=lambda e, eid=row["id"]: on_delete(eid),
                ),
            )
            for _, row in df.iterrows()
        ]

    # ------------------------------------------------------------------
    # Refresh: Dashboard
    # ------------------------------------------------------------------
    def refresh_dashboard() -> None:
        mark_activity()
        error_banner.value = ""
        year = int(year_field.value)
        month = int(month_dropdown.value)
        month_id = get_current_month_id()

        income_df = repository.get_entries_df(conn, "income", month_id)
        variable_df = repository.get_entries_df(conn, "variable", month_id)
        fixed_df = repository.get_fixed_expenses_for_month(conn, year, month)
        inv_df = repository.get_investments_df(conn, month_id)
        wd_df = repository.get_withdrawals_df(conn, month_id)

        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df, wd_df)

        metric_income.value = f"${summary.total_income:,.2f}"
        metric_income.color = palette.text_primary
        metric_fixed.value = f"${summary.total_fixed:,.2f}"
        metric_fixed.color = palette.text_primary
        metric_available.value = f"${summary.available_for_discretionary:,.2f}"
        metric_available.color = palette.text_primary
        metric_variable.value = f"${summary.total_variable:,.2f}"
        metric_variable.color = palette.text_primary
        metric_balance.value = f"${summary.month_balance:,.2f}"
        metric_balance.color = palette.positive if summary.month_balance >= 0 else palette.negative
        if balance_card_ref["control"] is not None:
            balance_card_ref["control"].border = ft.Border(left=ft.BorderSide(3, metric_balance.color))
        metric_mandatory_invested.value = f"${summary.total_invested_mandatory:,.2f}"
        metric_mandatory_invested.color = palette.text_primary

        # --- Barra de almacenamiento: fijos / variables / invertido / disponible ---
        total_invested_all = summary.total_invested_mandatory + summary.total_invested_discretionary
        disponible = summary.total_income - summary.total_fixed - summary.total_variable - total_invested_all
        storage_bar_warning.value = ""

        if summary.total_income <= 0:
            # Sin ingreso capturado: no hay base para proporciones, barra vacía.
            segments = []
        elif disponible < 0:
            # Sobregiro: ya no cabe un cuarto segmento "disponible negativo".
            # Mostramos solo los 3 gastos, escalados a su proporción real entre sí,
            # y advertimos del sobregiro aparte en texto.
            storage_bar_warning.value = (
                f"Este mes vas ${abs(disponible):,.2f} por encima de tu ingreso "
                "(gastos + inversión superan lo que entró)."
            )
            spent_total = summary.total_fixed + summary.total_variable + total_invested_all
            segments = [
                ("Fijos", summary.total_fixed, palette.accent),
                ("Variables", summary.total_variable, palette.warning),
                ("Invertido", total_invested_all, palette.positive),
            ]
            segments = [(label, amt, color) for label, amt, color in segments if amt > 0] or [("Fijos", 1, palette.accent)]
        else:
            segments = [
                ("Fijos", summary.total_fixed, palette.accent),
                ("Variables", summary.total_variable, palette.warning),
                ("Invertido", total_invested_all, palette.positive),
                ("Disponible", disponible, palette.border),
            ]
            segments = [(label, amt, color) for label, amt, color in segments if amt > 0]

        if storage_bar_ref["control"] is not None:
            storage_bar_ref["control"].controls = [
                ft.Container(
                    bgcolor=color,
                    expand=max(int(round(amt * 100)), 1),  # *100 conserva precisión de centavos; expand requiere int
                    height=22,
                    border_radius=4,
                )
                for _, amt, color in segments
            ] or [ft.Container(bgcolor=palette.border, expand=1, height=22, border_radius=4)]

        storage_bar_legend.controls = [
            ft.Row(
                [
                    ft.Container(width=10, height=10, bgcolor=color, border_radius=3),
                    ft.Text(f"{label}: ${amt:,.2f}", size=12, color=palette.text_secondary),
                ],
                spacing=6,
            )
            for label, amt, color in segments
        ]

        fixed_list.controls = [
            theme.row_card(
                ft.Text(row["category"], color=palette.text_primary, size=13, expand=True),
                ft.Text(f"${row['amount']:,.2f}", color=palette.text_secondary, size=13),
                palette,
                trailing=ft.Row(
                    [
                        ft.IconButton(
                            ft.Icons.EDIT_OUTLINED,
                            icon_size=16,
                            icon_color=palette.text_tertiary,
                            tooltip="Editar monto desde una fecha",
                            on_click=lambda e, gid=row["group_id"], cat=row["category"], amt=row["amount"]: open_edit_fixed_dialog(gid, cat, amt),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            icon_size=16,
                            icon_color=palette.text_tertiary,
                            tooltip="Eliminar desde una fecha",
                            on_click=lambda e, gid=row["group_id"], cat=row["category"]: open_deactivate_fixed_dialog(gid, cat),
                        ),
                    ],
                    spacing=0,
                ),
            )
            for _, row in fixed_df.iterrows()
        ] or [theme.caption("Sin gastos fijos definidos todavía.", palette)]

        income_summary.controls = build_summary_rows(income_df)
        variable_summary.controls = build_summary_rows(variable_df)
        income_list.controls = build_detail_rows(income_df, delete_income)
        variable_list.controls = build_detail_rows(variable_df, delete_variable)

        page.update()

    # ------------------------------------------------------------------
    # Refresh: Ahorro
    # ------------------------------------------------------------------
    def refresh_savings_page() -> None:
        mark_activity()
        savings_error_banner.value = ""
        month_id = get_current_month_id()

        inv_df = repository.get_investments_df(conn, month_id)
        wd_df = repository.get_withdrawals_df(conn, month_id)
        income_df = repository.get_entries_df(conn, "income", month_id)
        variable_df = repository.get_entries_df(conn, "variable", month_id)
        year = int(year_field.value)
        month = int(month_dropdown.value)
        fixed_df = repository.get_fixed_expenses_for_month(conn, year, month)
        summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df, inv_df, wd_df)

        # Acumulado histórico: independiente del mes seleccionado arriba.
        all_summary = repository.get_all_months_summary_df(conn)
        all_summary = trends.add_cumulative_savings(all_summary)
        cumulative_total = (
            float(all_summary["cumulative_invested"].iloc[-1]) if not all_summary.empty else 0.0
        )
        metric_cumulative_savings.value = f"${cumulative_total:,.2f}"
        metric_cumulative_savings.color = palette.positive if cumulative_total >= 0 else palette.negative

        investment_list.controls = [
            theme.row_card(
                ft.Row(
                    [
                        ft.Text(row["instrument"], color=palette.text_primary, size=13),
                        ft.Container(
                            content=ft.Text(
                                "Obligatoria" if row["is_mandatory"] else "Discrecional",
                                size=10,
                                color=palette.background if row["is_mandatory"] else palette.text_secondary,
                            ),
                            bgcolor=palette.accent if row["is_mandatory"] else palette.surface,
                            border_radius=6,
                            padding=ft.Padding(6, 2, 6, 2),
                        ),
                    ],
                    spacing=8,
                    expand=True,
                ),
                ft.Text(
                    f"${row['amount']:,.2f}" + (f" (+${row['return_amount']:,.2f})" if row["return_amount"] else ""),
                    color=palette.text_secondary, size=13,
                ),
                palette,
                trailing=ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=16,
                    icon_color=palette.text_tertiary,
                    on_click=lambda e, iid=row["id"]: delete_investment_entry(iid),
                ),
            )
            for _, row in inv_df.iterrows()
        ] or [theme.caption("Sin aportes registrados este mes.", palette)]

        withdrawal_list.controls = [
            theme.row_card(
                ft.Text(row["instrument"], color=palette.text_primary, size=13, expand=True),
                ft.Text(f"${row['amount']:,.2f}", color=palette.text_secondary, size=13),
                palette,
                trailing=ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=16,
                    icon_color=palette.text_tertiary,
                    on_click=lambda e, wid=row["id"]: delete_withdrawal_entry(wid),
                ),
            )
            for _, row in wd_df.iterrows()
        ] or [theme.caption("Sin retiros registrados este mes.", palette)]

        investment_summary.controls = [
            ft.Row(
                [theme.caption("Obligatorio este mes", palette),
                 ft.Text(f"${summary.total_invested_mandatory:,.2f}", size=13, color=palette.text_primary)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                [theme.caption("Discrecional este mes", palette),
                 ft.Text(f"${summary.total_invested_discretionary:,.2f}", size=13, color=palette.text_primary)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                [theme.caption("Retirado este mes", palette),
                 ft.Text(f"${summary.total_withdrawn:,.2f}", size=13, color=palette.text_primary)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                [
                    theme.caption("Ahorro neto del mes", palette),
                    ft.Text(
                        f"${summary.net_savings_this_month:,.2f}", size=13, weight=ft.FontWeight.W_500,
                        color=palette.positive if summary.net_savings_this_month >= 0 else palette.negative,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        ]

        page.update()

    def refresh_trends_page() -> None:
        mark_activity()
        trends_error_banner.value = ""
        start_value = trends_start_field.value.strip() or None
        end_value = trends_end_field.value.strip() or None

        try:
            if start_value:
                pd.Timestamp(start_value)
            if end_value:
                pd.Timestamp(end_value)
        except ValueError:
            trends_error_banner.value = "Fechas inválidas. Usa el formato YYYY-MM-DD."
            donut_container.content = None
            bars_container.content = None
            line_container.content = None
            page.update()
            return

        # --- Gráfica 1: dona de gastos variables (del mes seleccionado en Dashboard) ---
        month_id = get_current_month_id()
        variable_df = repository.get_entries_df(conn, "variable", month_id)
        cat_agg = categorization.totals_by_category(variable_df)
        donut_b64 = charts.category_distribution_donut(cat_agg, palette)
        if donut_b64:
            donut_container.content = ft.Image(src=charts.to_data_uri(donut_b64), width=320, height=320)
            top = cat_agg.iloc[0]
            donut_caption.value = (
                f"{top['category']} es tu mayor gasto variable este mes "
                f"({top['pct']:.0f}% del total, ${top['amount']:,.2f})."
            )
        else:
            donut_container.content = None
            donut_caption.value = "Sin gastos variables registrados en el mes seleccionado."

        # --- Datos históricos: acumulado calculado ANTES de filtrar (ver trends.py) ---
        full_summary = repository.get_all_months_summary_df(conn)
        full_summary = trends.add_month_label(full_summary)
        full_summary = trends.add_cumulative_savings(full_summary)
        ranged_summary = trends.filter_by_date_range(full_summary, start_value, end_value)

        # --- Gráfica 2: barras fijos vs. variables, en el rango elegido ---
        bars_b64 = charts.fixed_vs_variable_bars(ranged_summary, palette)
        if bars_b64:
            bars_container.content = ft.Image(src=charts.to_data_uri(bars_b64), width=620, height=340)
            total_fixed = ranged_summary["total_fixed"].sum()
            total_variable = ranged_summary["total_variable"].sum()
            if total_fixed + total_variable > 0:
                fixed_pct = total_fixed / (total_fixed + total_variable) * 100
                bars_caption.value = (
                    f"En el rango elegido, los gastos fijos representan el {fixed_pct:.0f}% "
                    f"del total entre fijos y variables (${total_fixed:,.2f} vs ${total_variable:,.2f})."
                )
            else:
                bars_caption.value = "Sin datos en el rango seleccionado."
        else:
            bars_container.content = None
            bars_caption.value = "Sin meses registrados en el rango seleccionado."

        # --- Gráfica 3: línea de ahorro acumulado, en el rango elegido ---
        line_b64 = charts.cumulative_savings_line(ranged_summary, palette)
        if line_b64:
            line_container.content = ft.Image(src=charts.to_data_uri(line_b64), width=620, height=340)
            if len(ranged_summary) >= 1:
                start_val = float(ranged_summary["cumulative_invested"].iloc[0])
                end_val = float(ranged_summary["cumulative_invested"].iloc[-1])
                change = end_val - start_val
                direction = "creció" if change >= 0 else "bajó"
                line_caption.value = (
                    f"Tu ahorro acumulado {direction} ${abs(change):,.2f} en el rango elegido, "
                    f"cerrando en ${end_val:,.2f}."
                )
        else:
            line_container.content = None
            line_caption.value = "Sin meses registrados en el rango seleccionado."

        page.update()

    def refresh_active_page() -> None:
        if selected_page["index"] == 0:
            refresh_dashboard()
        elif selected_page["index"] == 1:
            refresh_savings_page()
        else:
            refresh_trends_page()

    # ------------------------------------------------------------------
    # Acciones: Dashboard
    # ------------------------------------------------------------------
    def delete_income(entry_id: int) -> None:
        db.delete_entry(conn, "income", entry_id)
        refresh_dashboard()

    def delete_variable(entry_id: int) -> None:
        db.delete_entry(conn, "variable", entry_id)
        refresh_dashboard()

    def add_income(e: ft.ControlEvent) -> None:
        try:
            month_id = get_current_month_id()
            db.add_entry(conn, "income", month_id, income_category_field.value, income_amount_field.value)
            income_category_field.value = ""
            income_amount_field.value = ""
            refresh_dashboard()
        except ValidationError as exc:
            error_banner.value = str(exc)
            page.update()

    def add_variable(e: ft.ControlEvent) -> None:
        try:
            month_id = get_current_month_id()
            db.add_entry(conn, "variable", month_id, variable_category_field.value, variable_amount_field.value)
            variable_category_field.value = ""
            variable_amount_field.value = ""
            refresh_dashboard()
        except ValidationError as exc:
            error_banner.value = str(exc)
            page.update()

    def add_fixed(e: ft.ControlEvent) -> None:
        try:
            db.add_fixed_expense_definition(conn, fixed_category_field.value, fixed_amount_field.value)
            fixed_category_field.value = ""
            fixed_amount_field.value = ""
            refresh_dashboard()
        except ValidationError as exc:
            error_banner.value = str(exc)
            page.update()

    async def export_pdf(e: ft.ControlEvent) -> None:
        export_error_text.value = ""
        year = int(year_field.value)
        month = int(month_dropdown.value)
        suggested_name = f"presupuesto_{MONTH_NAMES[month - 1].lower()}_{year}.pdf"

        try:
            save_path = await export_pdf_picker.save_file(
                dialog_title="Guardar presupuesto como PDF",
                file_name=suggested_name,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
            )
        except ValueError as exc:
            export_error_text.value = str(exc)
            page.update()
            return

        if not save_path:
            return  # el usuario canceló el diálogo

        if not save_path.lower().endswith(".pdf"):
            save_path += ".pdf"

        try:
            month_id = get_current_month_id()
            income_df = repository.get_entries_df(conn, "income", month_id)
            variable_df_raw = repository.get_entries_df(conn, "variable", month_id)
            variable_df = categorization.totals_by_category(variable_df_raw)
            fixed_df = repository.get_fixed_expenses_for_month(conn, year, month)
            inv_df = repository.get_investments_df(conn, month_id)
            wd_df = repository.get_withdrawals_df(conn, month_id)
            summary = budget.compute_monthly_summary(income_df, fixed_df, variable_df_raw, inv_df, wd_df)

            all_summary = repository.get_all_months_summary_df(conn)
            all_summary = trends.add_cumulative_savings(all_summary)
            cumulative_total = (
                float(all_summary["cumulative_invested"].iloc[-1]) if not all_summary.empty else 0.0
            )

            pdf_export.generate_budget_pdf(
                Path(save_path), year, month, summary, fixed_df, income_df, variable_df, cumulative_total
            )
            export_error_text.value = f"PDF guardado: {save_path}"
            export_error_text.color = palette.positive
            page.update()
        except Exception as exc:  # noqa: BLE001 - mostramos cualquier fallo de exportación al usuario
            export_error_text.value = f"No se pudo exportar el PDF: {exc}"
            export_error_text.color = palette.negative
            page.update()

    export_pdf_button.on_click = export_pdf

    # ------------------------------------------------------------------
    # Acciones: Configuración
    # ------------------------------------------------------------------
    def on_change_name(e: ft.ControlEvent) -> None:
        mark_activity()
        settings_name_error.value = ""
        settings_name_success.value = ""
        try:
            auth.change_user_name(
                conn, settings_name_password_field.value or "", settings_name_new_field.value or ""
            )
            settings_name_success.value = "Nombre actualizado correctamente."
            settings_name_password_field.value = ""
            settings_name_new_field.value = ""
        except auth.ValidationError as exc:
            settings_name_error.value = str(exc)
        page.update()

    def on_change_password(e: ft.ControlEvent) -> None:
        mark_activity()
        settings_password_error.value = ""
        settings_password_success.value = ""

        if settings_password_new_field.value != settings_password_confirm_field.value:
            settings_password_error.value = "Las contraseñas nuevas no coinciden."
            page.update()
            return

        try:
            auth.change_password(
                conn,
                settings_password_current_field.value or "",
                settings_password_new_field.value or "",
            )
            settings_password_success.value = "Contraseña actualizada correctamente."
            settings_password_current_field.value = ""
            settings_password_new_field.value = ""
            settings_password_confirm_field.value = ""
        except auth.ValidationError as exc:
            settings_password_error.value = str(exc)
        page.update()

    def on_create_backup(e: ft.ControlEvent) -> None:
        mark_activity()
        try:
            backup_path = backup.create_backup(conn, DB_PATH)
            settings_backup_status.value = f"Respaldo creado: {backup_path}"
            settings_backup_status.color = palette.positive
        except backup.BackupError as exc:
            settings_backup_status.value = str(exc)
            settings_backup_status.color = palette.negative
        page.update()

    # ------------------------------------------------------------------
    # Acciones: Ahorro
    # ------------------------------------------------------------------
    def add_investment(e: ft.ControlEvent) -> None:
        try:
            month_id = get_current_month_id()
            db.add_investment(
                conn,
                month_id,
                investment_instrument_field.value,
                investment_amount_field.value,
                return_amount=investment_return_field.value or 0.0,
                is_mandatory=investment_mandatory_switch.value,
            )
            investment_instrument_field.value = ""
            investment_amount_field.value = ""
            investment_return_field.value = ""
            investment_mandatory_switch.value = False
            refresh_savings_page()
        except ValidationError as exc:
            savings_error_banner.value = str(exc)
            page.update()

    def delete_investment_entry(investment_id: int) -> None:
        db.delete_investment(conn, investment_id)
        refresh_savings_page()

    def add_withdrawal(e: ft.ControlEvent) -> None:
        try:
            month_id = get_current_month_id()
            db.add_withdrawal(conn, month_id, withdrawal_instrument_field.value, withdrawal_amount_field.value)
            withdrawal_instrument_field.value = ""
            withdrawal_amount_field.value = ""
            refresh_savings_page()
        except ValidationError as exc:
            savings_error_banner.value = str(exc)
            page.update()

    def delete_withdrawal_entry(withdrawal_id: int) -> None:
        db.delete_withdrawal(conn, withdrawal_id)
        refresh_savings_page()

    # ------------------------------------------------------------------
    # Diálogo de edición/desactivación de gastos fijos
    # ------------------------------------------------------------------
    dialog_category_field = theme.styled_text_field("Categoría", palette, expand=True)
    dialog_amount_field = theme.styled_text_field("Monto", palette, width=140)
    dialog_date_field = theme.styled_text_field("Vigente desde (YYYY-MM-DD)", palette, expand=True)
    dialog_error_text = ft.Text("", color=palette.negative, size=12)

    fixed_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(""),
        content=ft.Column([], tight=True, width=360),
        actions=[],
        open=False,
    )

    def close_dialog(e: ft.ControlEvent | None = None) -> None:
        fixed_dialog.open = False
        page.update()

    def open_edit_fixed_dialog(group_id: str, current_category: str, current_amount: float) -> None:
        dialog_category_field.value = current_category
        dialog_amount_field.value = f"{current_amount:.2f}"
        dialog_date_field.value = date.today().isoformat()
        dialog_error_text.value = ""

        def confirm_edit(e: ft.ControlEvent) -> None:
            try:
                db.update_fixed_expense_definition(
                    conn, group_id, dialog_category_field.value, dialog_amount_field.value,
                    effective_date=dialog_date_field.value or None,
                )
                close_dialog()
                refresh_dashboard()
            except (ValidationError, ValueError) as exc:
                dialog_error_text.value = str(exc)
                page.update()

        fixed_dialog.title = ft.Text("Editar gasto fijo", color=palette.text_primary)
        fixed_dialog.content = ft.Column(
            [
                theme.caption(
                    "El monto nuevo aplica desde la fecha indicada en adelante. "
                    "Los meses anteriores conservan el monto actual.",
                    palette,
                ),
                dialog_category_field, dialog_amount_field, dialog_date_field, dialog_error_text,
            ],
            spacing=10, tight=True, width=360,
        )
        fixed_dialog.actions = [
            ft.TextButton("Cancelar", on_click=close_dialog),
            ft.FilledButton("Guardar cambio", on_click=confirm_edit),
        ]
        fixed_dialog.open = True
        page.update()

    def open_deactivate_fixed_dialog(group_id: str, current_category: str) -> None:
        dialog_date_field.value = date.today().isoformat()
        dialog_error_text.value = ""

        def confirm_deactivate(e: ft.ControlEvent) -> None:
            try:
                db.deactivate_fixed_expense_definition(
                    conn, group_id, effective_date=dialog_date_field.value or None
                )
                close_dialog()
                refresh_dashboard()
            except ValueError as exc:
                dialog_error_text.value = str(exc)
                page.update()

        fixed_dialog.title = ft.Text("Eliminar gasto fijo", color=palette.text_primary)
        fixed_dialog.content = ft.Column(
            [
                ft.Text(
                    f"\"{current_category}\" dejará de aplicar desde la fecha indicada. "
                    "Los meses pasados conservan su historial intacto.",
                    color=palette.text_secondary, size=13,
                ),
                dialog_date_field, dialog_error_text,
            ],
            spacing=10, tight=True, width=360,
        )
        fixed_dialog.actions = [
            ft.TextButton("Cancelar", on_click=close_dialog),
            ft.FilledButton("Eliminar desde esa fecha", on_click=confirm_deactivate, bgcolor=palette.negative),
        ]
        fixed_dialog.open = True
        page.update()

    def on_period_change(e: ft.ControlEvent) -> None:
        refresh_active_page()

    month_dropdown.on_change = on_period_change
    year_field.on_submit = on_period_change
    year_field.on_blur = on_period_change

    def on_range_change(e: ft.ControlEvent) -> None:
        refresh_trends_page()

    trends_start_field.on_submit = on_range_change
    trends_start_field.on_blur = on_range_change
    trends_end_field.on_submit = on_range_change
    trends_end_field.on_blur = on_range_change

    # ------------------------------------------------------------------
    # Construcción de páginas
    # ------------------------------------------------------------------
    def build_dashboard_page() -> ft.Control:
        balance_card = theme.metric_card(
            "Balance del mes", metric_balance, palette, accent_color=metric_balance.color
        )
        balance_card_ref["control"] = balance_card

        metrics_grid = ft.ResponsiveRow(
            [
                ft.Container(theme.metric_card("Ingresos totales", metric_income, palette), col=4),
                ft.Container(theme.metric_card("Gastos fijos", metric_fixed, palette), col=4),
                ft.Container(
                    theme.metric_card("Disponible discrecional", metric_available, palette, accent_color=palette.accent),
                    col=4,
                ),
                ft.Container(theme.metric_card("Gastos variables", metric_variable, palette), col=4),
                ft.Container(balance_card, col=4),
                ft.Container(
                    theme.metric_card("Inversión obligatoria", metric_mandatory_invested, palette),
                    col=4,
                ),
            ],
            spacing=12,
            run_spacing=12,
        )

        storage_bar_row = ft.Row(spacing=2)
        storage_bar_ref["control"] = storage_bar_row

        storage_bar_section = ft.Container(
            content=ft.Column(
                [
                    theme.caption("Distribución del mes", palette),
                    ft.Container(height=8),
                    storage_bar_row,
                    ft.Container(height=10),
                    storage_bar_legend,
                    storage_bar_warning,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        fixed_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Gastos fijos", palette),
                    theme.caption("Definidos una sola vez; cambian solo desde la fecha que indiques.", palette),
                    ft.Container(height=8),
                    ft.Row([fixed_category_field, fixed_amount_field,
                            ft.IconButton(ft.Icons.ADD, icon_color=palette.accent, on_click=add_fixed)]),
                    ft.Container(height=8),
                    fixed_list,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        income_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Ingresos del mes", palette),
                    ft.Container(height=8),
                    ft.Row([income_category_field, income_amount_field,
                            ft.IconButton(ft.Icons.ADD, icon_color=palette.accent, on_click=add_income)]),
                    ft.Container(height=8),
                    theme.caption("Resumen por categoría", palette),
                    income_summary,
                    ft.Container(height=8),
                    theme.caption("Detalle (puedes borrar entradas individuales)", palette),
                    income_list,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        variable_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Gastos variables del mes", palette),
                    ft.Container(height=8),
                    ft.Row([variable_category_field, variable_amount_field,
                            ft.IconButton(ft.Icons.ADD, icon_color=palette.accent, on_click=add_variable)]),
                    ft.Container(height=8),
                    theme.caption("Resumen por categoría", palette),
                    variable_summary,
                    ft.Container(height=8),
                    theme.caption("Detalle (puedes borrar entradas individuales)", palette),
                    variable_list,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        return ft.Column(
            [
                metrics_grid,
                ft.Container(height=8),
                storage_bar_section,
                ft.Container(height=8),
                fixed_section,
                income_section,
                variable_section,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def build_savings_page() -> ft.Control:
        cumulative_card = ft.Container(
            content=ft.Column(
                [
                    theme.caption("Ahorro acumulado histórico (todos los meses)", palette),
                    metric_cumulative_savings,
                ],
                spacing=6,
            ),
            bgcolor=palette.surface,
            border=ft.Border(left=ft.BorderSide(3, palette.accent)),
            border_radius=10,
            padding=ft.Padding(20, 18, 20, 18),
        )

        investment_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Aportes del mes seleccionado", palette),
                    theme.caption("Marca \"Obligatoria\" para aportes no-negociables (ej. inversión recurrente en tu empresa).", palette),
                    ft.Container(height=8),
                    ft.Row([investment_instrument_field, investment_amount_field, investment_return_field]),
                    ft.Row([investment_mandatory_switch,
                            ft.IconButton(ft.Icons.ADD, icon_color=palette.accent, on_click=add_investment)],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(height=8),
                    investment_list,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        withdrawal_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Retiros del mes seleccionado", palette),
                    theme.caption("Tú decides el monto exacto; el sistema solo lo resta del acumulado.", palette),
                    ft.Container(height=8),
                    ft.Row([withdrawal_instrument_field, withdrawal_amount_field,
                            ft.IconButton(ft.Icons.ADD, icon_color=palette.accent, on_click=add_withdrawal)]),
                    ft.Container(height=8),
                    withdrawal_list,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        summary_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Resumen del mes seleccionado", palette),
                    ft.Container(height=8),
                    investment_summary,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        return ft.Column(
            [
                cumulative_card,
                ft.Container(height=8),
                savings_error_banner,
                investment_section,
                withdrawal_section,
                summary_section,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def build_trends_page() -> ft.Control:
        range_row = ft.Row(
            [
                trends_start_field, trends_end_field,
                ft.IconButton(ft.Icons.REFRESH, icon_color=palette.accent, tooltip="Actualizar", on_click=lambda e: refresh_trends_page()),
            ],
            spacing=12,
        )

        donut_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Distribución de gastos variables", palette),
                    theme.caption("Del mes seleccionado en Dashboard.", palette),
                    ft.Container(height=12),
                    donut_container,
                    ft.Container(height=8),
                    donut_caption,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        bars_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Fijos vs. variables por mes", palette),
                    theme.caption("En el rango de fechas elegido arriba.", palette),
                    ft.Container(height=12),
                    bars_container,
                    ft.Container(height=8),
                    bars_caption,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        line_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Tendencia de ahorro acumulado", palette),
                    theme.caption("Calculado sobre tu historial completo; el rango solo recorta la vista.", palette),
                    ft.Container(height=12),
                    line_container,
                    ft.Container(height=8),
                    line_caption,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        return ft.Column(
            [
                range_row,
                trends_error_banner,
                ft.Container(height=8),
                donut_section,
                bars_section,
                line_section,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def build_settings_page() -> ft.Control:
        name_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Cambiar nombre", palette),
                    theme.caption("Confirma con tu contraseña actual.", palette),
                    ft.Container(height=12),
                    settings_name_password_field,
                    settings_name_new_field,
                    settings_name_error,
                    settings_name_success,
                    ft.Container(height=8),
                    ft.FilledButton("Guardar nombre", on_click=on_change_name),
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        password_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Cambiar contraseña", palette),
                    theme.caption(
                        "Ya estás dentro de la app: solo se pide tu contraseña actual, "
                        "sin código de recuperación.",
                        palette,
                    ),
                    ft.Container(height=12),
                    settings_password_current_field,
                    settings_password_new_field,
                    settings_password_confirm_field,
                    settings_password_error,
                    settings_password_success,
                    ft.Container(height=8),
                    ft.FilledButton("Guardar contraseña", on_click=on_change_password),
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        backup_section = ft.Container(
            content=ft.Column(
                [
                    theme.section_title("Respaldo", palette),
                    theme.caption(
                        "Crea una copia de tu base de datos con fecha y hora, antes de "
                        "cualquier cambio grande. Se guarda en data/backups/.",
                        palette,
                    ),
                    ft.Container(height=12),
                    ft.FilledButton("Crear respaldo ahora", icon=ft.Icons.BACKUP_OUTLINED, on_click=on_create_backup),
                    ft.Container(height=8),
                    settings_backup_status,
                ]
            ),
            bgcolor=palette.surface, border_radius=12, padding=18,
        )

        return ft.Column(
            [name_section, password_section, backup_section],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def build_current_page_content() -> ft.Control:
        titles = ["Dashboard", "Ahorro", "Tendencias", "Configuración"]
        title = titles[selected_page["index"]]

        header_actions = [theme_icon_button]
        if selected_page["index"] == 0:
            header_actions.insert(0, export_pdf_button)

        header = ft.Row(
            [
                ft.Text(title, size=24, weight=ft.FontWeight.W_500, color=palette.text_primary),
                ft.Row(header_actions, alignment=ft.MainAxisAlignment.END),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        if selected_page["index"] in (0, 1):
            selector_row = ft.Row([month_dropdown, year_field], spacing=12)
        else:
            selector_row = None  # Tendencias y Configuración no usan selector de mes/año

        if selected_page["index"] == 0:
            body = build_dashboard_page()
        elif selected_page["index"] == 1:
            body = build_savings_page()
        elif selected_page["index"] == 2:
            body = build_trends_page()
        else:
            body = build_settings_page()

        children = [header, ft.Container(height=4)]
        if selector_row is not None:
            children += [selector_row, error_banner, ft.Container(height=8)]
        if selected_page["index"] == 0:
            children.append(export_error_text)
        children.append(body)

        return ft.Container(
            content=ft.Column(children, spacing=16, expand=True),
            bgcolor=palette.background,
            padding=ft.Padding(28, 24, 28, 32),
            expand=True,
        )

    def on_nav_change(e: ft.ControlEvent) -> None:
        selected_page["index"] = e.control.selected_index
        rebuild_and_refresh()

    def build_nav_rail() -> ft.NavigationRail:
        rail = ft.NavigationRail(
            selected_index=selected_page["index"],
            label_type=ft.NavigationRailLabelType.ALL,
            bgcolor=palette.surface,
            indicator_color=palette.accent,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SAVINGS_OUTLINED, selected_icon=ft.Icons.SAVINGS, label="Ahorro"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SHOW_CHART_OUTLINED, selected_icon=ft.Icons.SHOW_CHART, label="Tendencias"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Configuración"
                ),
            ],
            on_change=on_nav_change,
        )
        nav_rail_ref["control"] = rail
        return rail

    def toggle_theme(e: ft.ControlEvent) -> None:
        nonlocal palette
        page.theme_mode = ft.ThemeMode.LIGHT if page.theme_mode == ft.ThemeMode.DARK else ft.ThemeMode.DARK
        palette = theme.get_palette(page.theme_mode)
        theme_icon_button.icon = ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE
        rebuild_and_refresh()

    theme_icon_button.on_click = toggle_theme

    def rebuild_and_refresh() -> None:
        """Reconstruye todo el árbol de controles con la paleta activa
        y vuelve a aplicar los estilos a los campos persistentes, luego
        recalcula los totales de la página activa."""

        def apply_field_theme(field: ft.TextField) -> None:
            field.border_color = palette.border
            field.bgcolor = palette.surface_alt
            field.color = palette.text_primary
            field.focused_border_color = palette.accent

        for field in (
            income_category_field, income_amount_field,
            variable_category_field, variable_amount_field,
            fixed_category_field, fixed_amount_field,
            investment_instrument_field, investment_amount_field, investment_return_field,
            withdrawal_instrument_field, withdrawal_amount_field,
            trends_start_field, trends_end_field,
            year_field,
            dialog_category_field, dialog_amount_field, dialog_date_field,
            settings_name_password_field, settings_name_new_field,
            settings_password_current_field, settings_password_new_field, settings_password_confirm_field,
        ):
            apply_field_theme(field)

        settings_name_error.color = palette.negative
        settings_name_success.color = palette.positive
        settings_password_error.color = palette.negative
        settings_password_success.color = palette.positive

        trends_error_banner.color = palette.negative
        donut_caption.color = palette.text_secondary
        bars_caption.color = palette.text_secondary
        line_caption.color = palette.text_secondary
        storage_bar_warning.color = palette.negative
        investment_mandatory_switch.active_color = palette.accent
        theme_icon_button.icon_color = palette.text_secondary
        export_pdf_button.icon_color = palette.text_secondary
        error_banner.color = palette.negative
        savings_error_banner.color = palette.negative
        dialog_error_text.color = palette.negative
        fixed_dialog.bgcolor = palette.surface

        page_root.content = build_current_page_content()
        app_root.controls = [build_nav_rail(), ft.VerticalDivider(width=1, color=palette.border), page_root]
        page.bgcolor = palette.background
        page.update()
        refresh_active_page()

    async def monitor_inactivity() -> None:
        """Revisa periódicamente si pasó el umbral de inactividad y, si
        es así, cierra la sesión llamando a on_logout. Se detiene solo
        (no sigue corriendo en segundo plano) en cuanto cierra sesión
        una vez, ya que en ese punto el Dashboard ya no está visible."""
        check_interval_seconds = 30
        while session_active["value"]:
            await asyncio.sleep(check_interval_seconds)
            elapsed = time.monotonic() - last_activity["timestamp"]
            if elapsed >= INACTIVITY_TIMEOUT_SECONDS:
                session_active["value"] = False
                on_logout()
                break

    if fixed_dialog not in page.overlay:
        page.overlay.append(fixed_dialog)
    if export_pdf_picker not in page.services:
        page.services.append(export_pdf_picker)

    page.add(app_root)
    rebuild_and_refresh()
    page.run_task(monitor_inactivity)


def main(page: ft.Page) -> None:
    """Punto de entrada real. Gestiona el flujo de login antes de
    construir la app principal (build_main_app)."""
    page.title = "Finanzas personales"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    palette = theme.get_palette(page.theme_mode)

    login_error = ft.Text("", color=palette.negative, size=12)
    forgot_error = ft.Text("", color=palette.negative, size=12)
    create_error = ft.Text("", color=palette.negative, size=12)

    def show(control: ft.Control) -> None:
        page.controls.clear()
        page.bgcolor = palette.background
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.add(control)
        page.update()

    def enter_main_app() -> None:
        page.controls.clear()
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.horizontal_alignment = ft.CrossAxisAlignment.START
        page.update()
        build_main_app(page, conn, show_login_screen)

    def current_user_name() -> str:
        return auth.get_user_name(conn) or "ahí"

    def show_login_screen() -> None:
        login_error.value = ""
        show(
            login.build_welcome_login(
                palette, current_user_name(), on_password_submitted, show_forgot_password_screen, login_error
            )
        )

    def on_password_submitted(password: str) -> None:
        if auth.verify_password(conn, password or ""):
            enter_main_app()
        else:
            login_error.value = "Contraseña incorrecta."
            show_login_screen_preserving_error()

    def show_login_screen_preserving_error() -> None:
        show(
            login.build_welcome_login(
                palette, current_user_name(), on_password_submitted, show_forgot_password_screen, login_error
            )
        )

    def show_forgot_password_screen() -> None:
        forgot_error.value = ""
        show(login.build_forgot_password(palette, on_reset_requested, show_login_screen, forgot_error))

    def on_reset_requested(code: str, new_password: str) -> None:
        try:
            recovery_code = auth.reset_password_with_recovery_code(conn, code or "", new_password or "")
            show_recovery_code_reveal(recovery_code, after=show_login_screen)
        except auth.ValidationError as exc:
            forgot_error.value = str(exc)
            show(login.build_forgot_password(palette, on_reset_requested, show_login_screen, forgot_error))

    def show_create_password_screen() -> None:
        create_error.value = ""
        show(login.build_create_password(palette, on_create_requested, create_error))

    def on_create_requested(name: str, password: str, confirm: str) -> None:
        if not (name or "").strip():
            create_error.value = "Escribe tu nombre."
            show(login.build_create_password(palette, on_create_requested, create_error))
            return
        if password != confirm:
            create_error.value = "Las contraseñas no coinciden."
            show(login.build_create_password(palette, on_create_requested, create_error))
            return
        try:
            recovery_code = auth.set_password(conn, password or "", user_name=name.strip())
            show_recovery_code_reveal(recovery_code, after=show_login_screen)
        except auth.ValidationError as exc:
            create_error.value = str(exc)
            show(login.build_create_password(palette, on_create_requested, create_error))

    def show_recovery_code_reveal(recovery_code: str, after) -> None:
        show(login.build_recovery_code_reveal(palette, recovery_code, after))

    if auth.has_credentials(conn):
        show_login_screen()
    else:
        show_create_password_screen()


if __name__ == "__main__":
    ft.app(target=main)
