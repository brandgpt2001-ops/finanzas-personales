"""
Generación de gráficas con matplotlib, devueltas como imágenes PNG
codificadas en base64 listas para insertarse en un ft.Image de Flet
(vía data URI: f"data:image/png;base64,{resultado}").

Cada función recibe la Palette activa (ver views/theme.py) para que el
estilo de la gráfica combine con el tema oscuro/claro de la app. Las
funciones consumen DataFrames ya calculados por services/categorization.py
y services/trends.py — esta capa solo dibuja, no calcula.
"""

from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")  # backend sin GUI: necesario para generar imágenes sin ventana
import matplotlib.pyplot as plt
import pandas as pd

from finanzas_app.views.theme import Palette

# Paleta categórica para distinguir categorías en la dona. Tonos variados
# pero apagados, coherentes con la estética seria/minimalista de la app.
CATEGORY_COLORS = [
    "#4A7390", "#C99A3F", "#3FAE7E", "#C75D49", "#8A7BB5",
    "#5A9BA8", "#B5854A", "#6FA85A", "#A85A7B", "#7B8AA8",
]


def _fig_to_base64(fig: plt.Figure) -> str:
    """Convierte una figura de matplotlib a un string PNG en base64."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, dpi=150, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def _style_axes(ax: plt.Axes, palette: Palette) -> None:
    """Aplica el estilo de texto/ejes coherente con la paleta activa."""
    ax.tick_params(colors=palette.text_secondary, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(palette.border)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def category_distribution_donut(df: pd.DataFrame, palette: Palette, title: str = "") -> str | None:
    """Dona de distribución por categoría (gastos variables, por ejemplo).

    df: salida de services.categorization.totals_by_category()
        (columnas: category, amount, pct)
    Devuelve None si el DataFrame está vacío (no hay nada que graficar).
    """
    if df.empty:
        return None

    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    fig.patch.set_alpha(0)

    colors = [CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i in range(len(df))]
    wedges, _ = ax.pie(
        df["amount"],
        colors=colors,
        startangle=90,
        wedgeprops={"width": 0.4, "edgecolor": palette.background, "linewidth": 2},
    )
    ax.legend(
        wedges,
        [f"{row['category']} ({row['pct']:.0f}%)" for _, row in df.iterrows()],
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=False,
        labelcolor=palette.text_primary,
        fontsize=9,
    )
    if title:
        ax.set_title(title, color=palette.text_primary, fontsize=12, pad=10)

    return _fig_to_base64(fig)


def fixed_vs_variable_bars(df: pd.DataFrame, palette: Palette) -> str | None:
    """Barras agrupadas de gastos fijos vs. variables por mes.

    df: DataFrame con columnas month_label, total_fixed, total_variable
        (salida de trends.add_month_label sobre el resumen filtrado por rango)
    """
    if df.empty:
        return None

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    x = range(len(df))
    width = 0.38
    ax.bar(
        [i - width / 2 for i in x], df["total_fixed"], width,
        label="Fijos", color=palette.accent,
    )
    ax.bar(
        [i + width / 2 for i in x], df["total_variable"], width,
        label="Variables", color=palette.warning,
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(df["month_label"], rotation=45 if len(df) > 6 else 0, ha="right")
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    ax.legend(frameon=False, labelcolor=palette.text_primary, fontsize=9, loc="upper left")
    ax.grid(axis="y", color=palette.border, linewidth=0.5, alpha=0.6)
    _style_axes(ax, palette)

    return _fig_to_base64(fig)


def cumulative_savings_line(df: pd.DataFrame, palette: Palette) -> str | None:
    """Línea de ahorro acumulado (neto: aportes - retiros + rendimiento) por mes.

    df: DataFrame con columnas month_label, cumulative_invested
        (salida de trends.add_cumulative_savings + add_month_label,
        ya filtrado por el rango de fechas elegido)
    """
    if df.empty:
        return None

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    x = range(len(df))
    ax.plot(
        x, df["cumulative_invested"],
        color=palette.positive, linewidth=2.2, marker="o", markersize=4,
    )
    ax.fill_between(
        x, df["cumulative_invested"],
        color=palette.positive, alpha=0.08,
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(df["month_label"], rotation=45 if len(df) > 6 else 0, ha="right")
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    ax.grid(axis="y", color=palette.border, linewidth=0.5, alpha=0.6)
    _style_axes(ax, palette)

    return _fig_to_base64(fig)


def to_data_uri(base64_str: str) -> str:
    """Envuelve un string base64 de PNG en un data URI listo para ft.Image(src=...)."""
    return f"data:image/png;base64,{base64_str}"
