"""
Sistema de diseño de la app: paletas de color (claro/oscuro) y helpers
de estilo reutilizables para construir tarjetas, listas y secciones
consistentes en toda la UI de Flet.

Filosofía: minimalista, serio, con un azul oscuro (#2F526A) como acento
único — no como color dominante. Jerarquía visual por contraste de
superficie (fondo vs. tarjeta), no por bordes gruesos ni sombras.
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

ACCENT = "#2F526A"
ACCENT_LIGHT = "#4A7390"  # variante más clara del acento, para hover/dark mode

POSITIVE = "#3FAE7E"   # balance positivo, ahorro — verde apagado, no neón
NEGATIVE = "#C75D49"   # balance negativo, alertas — coral apagado
WARNING = "#C99A3F"    # atención / pendiente


@dataclass(frozen=True)
class Palette:
    """Paleta de colores para un tema (claro u oscuro)."""

    background: str        # fondo general de la página
    surface: str            # tarjetas, contenedores
    surface_alt: str        # superficie ligeramente distinta (inputs, filas alternas)
    border: str              # bordes sutiles
    text_primary: str
    text_secondary: str
    text_tertiary: str
    accent: str
    positive: str
    negative: str
    warning: str


DARK = Palette(
    background="#13181D",
    surface="#1B2228",
    surface_alt="#222A31",
    border="#2A3138",
    text_primary="#EDEFF1",
    text_secondary="#8A949E",
    text_tertiary="#5A6470",
    accent=ACCENT_LIGHT,
    positive=POSITIVE,
    negative=NEGATIVE,
    warning=WARNING,
)

LIGHT = Palette(
    background="#F5F6F7",
    surface="#FFFFFF",
    surface_alt="#F0F1F3",
    border="#DDE1E4",
    text_primary="#1B2228",
    text_secondary="#5A6470",
    text_tertiary="#8A949E",
    accent=ACCENT,
    positive="#2E8C63",
    negative="#B14B38",
    warning="#A87C2C",
)


def get_palette(theme_mode: ft.ThemeMode) -> Palette:
    return DARK if theme_mode == ft.ThemeMode.DARK else LIGHT


def metric_card(
    title: str, value_control: ft.Text, palette: Palette, accent_color: str | None = None
) -> ft.Container:
    """Tarjeta de métrica con borde lateral de acento, estilo dashboard financiero."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(title, size=12, color=palette.text_secondary),
                value_control,
            ],
            spacing=6,
        ),
        bgcolor=palette.surface,
        border_radius=10,
        border=ft.Border(
            left=ft.BorderSide(3, accent_color or palette.accent),
        ),
        padding=ft.Padding(16, 14, 16, 14),
        expand=True,
    )


def section_title(text: str, palette: Palette) -> ft.Text:
    return ft.Text(text, size=16, weight=ft.FontWeight.W_500, color=palette.text_primary)


def caption(text: str, palette: Palette) -> ft.Text:
    return ft.Text(text, size=12, color=palette.text_secondary)


def styled_text_field(
    label: str, palette: Palette, width: int | None = None, expand: bool = False
) -> ft.TextField:
    return ft.TextField(
        label=label,
        width=width,
        expand=expand,
        border_color=palette.border,
        focused_border_color=palette.accent,
        bgcolor=palette.surface_alt,
        color=palette.text_primary,
        label_style=ft.TextStyle(color=palette.text_secondary),
        border_radius=8,
    )


def row_card(left: ft.Control, right: ft.Control, palette: Palette, trailing: ft.Control | None = None) -> ft.Container:
    """Fila de lista (ej. una entrada de ingreso/gasto) con estilo de tarjeta sutil."""
    controls = [left, right]
    if trailing is not None:
        controls.append(trailing)
    return ft.Container(
        content=ft.Row(controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        bgcolor=palette.surface_alt,
        border_radius=8,
        padding=ft.Padding(12, 8, 8, 8),
    )
