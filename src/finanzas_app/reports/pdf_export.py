"""
Exportación del presupuesto mensual a PDF — un snapshot conciso para
tener a la mano en el teléfono, sin abrir la app.

Contenido: tarjetas informativas del mes, tablas de gastos fijos /
ingresos / gastos variables, y el ahorro acumulado histórico. Sin
gráficas ni comparación con meses anteriores (deliberado: esto es un
snapshot rápido, no un reporte analítico).

Esta capa solo da formato — todos los cálculos vienen de
services/budget.py y services/trends.py, y los datos crudos de
data/repository.py. No se duplica ninguna lógica de negocio aquí.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from finanzas_app.services.budget import MonthlyBudgetSummary

ACCENT = colors.HexColor("#2F526A")
BORDER = colors.HexColor("#DADDE1")
TEXT_SECONDARY = colors.HexColor("#5A6470")

MONTH_NAMES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _money(amount: float) -> str:
    """Formatea un monto como '$1,234.50', consistente con el resto de la app."""
    return f"${amount:,.2f}"


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BudgetTitle", parent=base["Title"], textColor=ACCENT, fontSize=20, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "BudgetSubtitle", parent=base["Normal"], textColor=TEXT_SECONDARY, fontSize=10, spaceAfter=18,
        ),
        "section": ParagraphStyle(
            "SectionHeading", parent=base["Heading2"], textColor=ACCENT, fontSize=13,
            spaceBefore=14, spaceAfter=6,
        ),
        "caption": ParagraphStyle(
            "Caption", parent=base["Normal"], textColor=TEXT_SECONDARY, fontSize=9, spaceAfter=10,
        ),
    }


def _metric_cards_table(summary: MonthlyBudgetSummary) -> Table:
    """Tabla de 3x2 simulando las tarjetas informativas del Dashboard."""
    cards = [
        ("Ingresos totales", summary.total_income),
        ("Gastos fijos", summary.total_fixed),
        ("Disponible discrecional", summary.available_for_discretionary),
        ("Gastos variables", summary.total_variable),
        ("Balance del mes", summary.month_balance),
        ("Invertido obligatorio", summary.total_invested_mandatory),
    ]

    cell_style = ParagraphStyle("CardLabel", fontSize=8.5, textColor=TEXT_SECONDARY, leading=11)
    value_style = ParagraphStyle("CardValue", fontSize=13, textColor=colors.HexColor("#1B2228"), leading=16, fontName="Helvetica-Bold")
    balance_negative_style = ParagraphStyle("CardValueNeg", parent=value_style, textColor=colors.HexColor("#B14B38"))

    def cell(label: str, value: float, negative_aware: bool = False) -> list:
        style = balance_negative_style if (negative_aware and value < 0) else value_style
        return [Paragraph(label, cell_style), Paragraph(_money(value), style)]

    row1 = [cell(l, v, negative_aware=(l == "Balance del mes")) for l, v in cards[:3]]
    row2 = [cell(l, v, negative_aware=(l == "Balance del mes")) for l, v in cards[3:]]

    table_data = [
        [row1[0][0], row1[1][0], row1[2][0]],
        [row1[0][1], row1[1][1], row1[2][1]],
        [row2[0][0], row2[1][0], row2[2][0]],
        [row2[0][1], row2[1][1], row2[2][1]],
    ]

    col_width = 5.8 * cm
    table = Table(table_data, colWidths=[col_width] * 3)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#F0F1F3")),
                ("BACKGROUND", (0, 2), (-1, 3), colors.HexColor("#F0F1F3")),
                ("BOX", (0, 0), (0, 1), 0.5, BORDER),
                ("BOX", (1, 0), (1, 1), 0.5, BORDER),
                ("BOX", (2, 0), (2, 1), 0.5, BORDER),
                ("BOX", (0, 2), (0, 3), 0.5, BORDER),
                ("BOX", (1, 2), (1, 3), 0.5, BORDER),
                ("BOX", (2, 2), (2, 3), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _category_table(df: pd.DataFrame, empty_message: str) -> Table | Paragraph:
    """Tabla de dos columnas (categoría, monto) a partir de un DataFrame
    con columnas 'category' y 'amount'. Si está vacío, devuelve un texto
    de aviso en su lugar."""
    if df.empty:
        style = ParagraphStyle("EmptyNote", fontSize=10, textColor=TEXT_SECONDARY)
        return Paragraph(empty_message, style)

    header_style = ParagraphStyle("TblHeader", fontSize=9.5, textColor=colors.white, fontName="Helvetica-Bold")
    row_style = ParagraphStyle("TblRow", fontSize=10, textColor=colors.HexColor("#1B2228"))
    amount_style = ParagraphStyle("TblAmount", fontSize=10, textColor=colors.HexColor("#1B2228"), alignment=2)

    rows = [[Paragraph("Categoría", header_style), Paragraph("Monto", header_style)]]
    total = 0.0
    for _, row in df.iterrows():
        rows.append([Paragraph(str(row["category"]), row_style), Paragraph(_money(row["amount"]), amount_style)])
        total += float(row["amount"])

    total_style = ParagraphStyle("TblTotal", fontSize=10, textColor=ACCENT, fontName="Helvetica-Bold")
    total_amount_style = ParagraphStyle("TblTotalAmt", parent=total_style, alignment=2)
    rows.append([Paragraph("Total", total_style), Paragraph(_money(total), total_amount_style)])

    table = Table(rows, colWidths=[10 * cm, 5.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, ACCENT),
                ("GRID", (0, 1), (-1, -2), 0.5, BORDER),
                ("LINEABOVE", (0, -1), (-1, -1), 0.75, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _cumulative_savings_block(cumulative_total: float) -> list:
    label_style = ParagraphStyle("SavingsLabel", fontSize=10, textColor=TEXT_SECONDARY)
    value_color = colors.HexColor("#3FAE7E") if cumulative_total >= 0 else colors.HexColor("#B14B38")
    value_style = ParagraphStyle("SavingsValue", fontSize=22, textColor=value_color, fontName="Helvetica-Bold", spaceBefore=2)

    box = Table(
        [[Paragraph("Ahorro acumulado histórico (todos los meses)", label_style)],
         [Paragraph(_money(cumulative_total), value_style)]],
        colWidths=[15.5 * cm],
    )
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F1F3")),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return [KeepTogether(box)]


def generate_budget_pdf(
    output_path: Path,
    year: int,
    month: int,
    summary: MonthlyBudgetSummary,
    fixed_df: pd.DataFrame,
    income_df: pd.DataFrame,
    variable_df: pd.DataFrame,
    cumulative_savings_total: float,
) -> Path:
    """Genera el PDF del presupuesto mensual y lo guarda en output_path.

    fixed_df, income_df, variable_df: DataFrames con columnas 'category'
    y 'amount' (la misma forma que ya usan las vistas del Dashboard).
    cumulative_savings_total: el acumulado histórico, típicamente
    calculado con trends.add_cumulative_savings() sobre todos los meses.

    Devuelve la ruta del archivo generado (la misma que output_path).
    """
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
    )

    month_name = MONTH_NAMES_ES[month - 1]
    story = [
        Paragraph(f"Presupuesto — {month_name} {year}", styles["title"]),
        Paragraph("Generado por Finanzas personales", styles["subtitle"]),
        KeepTogether(_metric_cards_table(summary)),
        Spacer(1, 16),
        KeepTogether([Paragraph("Gastos fijos", styles["section"]),
                      _category_table(fixed_df, "Sin gastos fijos definidos para este mes.")]),
        Spacer(1, 10),
        KeepTogether([Paragraph("Ingresos", styles["section"]),
                      _category_table(income_df, "Sin ingresos capturados este mes.")]),
        Spacer(1, 10),
        KeepTogether([Paragraph("Gastos variables", styles["section"]),
                      _category_table(variable_df, "Sin gastos variables capturados este mes.")]),
        Spacer(1, 16),
        *_cumulative_savings_block(cumulative_savings_total),
    ]

    doc.build(story)
    return output_path
