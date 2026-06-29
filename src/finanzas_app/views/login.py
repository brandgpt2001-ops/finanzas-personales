"""
Vista de login: pantalla de bienvenida con contraseña, creación inicial
de contraseña (primera vez que se abre la app), y recuperación por
código cuando se olvida la contraseña.

Este módulo solo construye controles de Flet; toda la lógica de
verificación vive en data/auth.py. main.py decide cuándo mostrar esta
vista y qué hacer al autenticarse correctamente.
"""

from __future__ import annotations

import flet as ft

from finanzas_app.views.theme import Palette, styled_text_field


def build_welcome_login(
    palette: Palette,
    user_name: str,
    on_submit_password,
    on_forgot_password,
    error_text: ft.Text,
) -> ft.Control:
    """Pantalla de login normal: 'Hola {user_name}, bienvenido...' + contraseña."""
    password_field = styled_text_field("Contraseña", palette, width=280)
    password_field.password = True
    password_field.can_reveal_password = True
    password_field.on_submit = lambda e: on_submit_password(password_field.value)

    submit_button = ft.FilledButton(
        "Entrar",
        on_click=lambda e: on_submit_password(password_field.value),
        width=280,
    )
    forgot_link = ft.TextButton(
        "Olvidé mi contraseña",
        on_click=lambda e: on_forgot_password(),
        style=ft.ButtonStyle(color=palette.text_secondary),
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.SAVINGS_OUTLINED, size=48, color=palette.accent),
                ft.Container(height=8),
                ft.Text(
                    f"Hola {user_name}, Bienvenido a tu app de finanzas personales",
                    size=18,
                    weight=ft.FontWeight.W_500,
                    color=palette.text_primary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                password_field,
                error_text,
                ft.Container(height=8),
                submit_button,
                ft.Container(height=4),
                forgot_link,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        alignment=ft.Alignment.CENTER,
        bgcolor=palette.background,
        expand=True,
        padding=32,
        width=420,
    )


def build_create_password(
    palette: Palette,
    on_create,
    error_text: ft.Text,
) -> ft.Control:
    """Pantalla de creación de contraseña, primera vez que se abre la app."""
    name_field = styled_text_field("Tu nombre", palette, width=280)

    password_field = styled_text_field("Nueva contraseña", palette, width=280)
    password_field.password = True
    password_field.can_reveal_password = True

    confirm_field = styled_text_field("Confirmar contraseña", palette, width=280)
    confirm_field.password = True
    confirm_field.can_reveal_password = True

    submit_button = ft.FilledButton(
        "Crear contraseña",
        on_click=lambda e: on_create(name_field.value, password_field.value, confirm_field.value),
        width=280,
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=palette.accent),
                ft.Container(height=8),
                ft.Text(
                    "Crea una contraseña para proteger tu app",
                    size=18,
                    weight=ft.FontWeight.W_500,
                    color=palette.text_primary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "La necesitarás cada vez que abras la app.",
                    size=12,
                    color=palette.text_secondary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                name_field,
                password_field,
                confirm_field,
                error_text,
                ft.Container(height=8),
                submit_button,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        alignment=ft.Alignment.CENTER,
        bgcolor=palette.background,
        expand=True,
        padding=32,
        width=420,
    )


def build_recovery_code_reveal(
    palette: Palette,
    recovery_code: str,
    on_continue,
) -> ft.Control:
    """Pantalla que muestra el código de recuperación UNA SOLA VEZ.

    Se llama justo después de crear o resetear la contraseña. El código
    nunca se vuelve a mostrar después de que el usuario continúe.
    """
    code_box = ft.Container(
        content=ft.Text(
            recovery_code, size=22, weight=ft.FontWeight.W_500,
            color=palette.accent, selectable=True,
        ),
        bgcolor=palette.surface,
        border=ft.Border(left=ft.BorderSide(3, palette.accent)),
        border_radius=10,
        padding=ft.Padding(20, 16, 20, 16),
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.KEY_OUTLINED, size=48, color=palette.accent),
                ft.Container(height=8),
                ft.Text(
                    "Guarda tu código de recuperación",
                    size=18,
                    weight=ft.FontWeight.W_500,
                    color=palette.text_primary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Si olvidas tu contraseña, este código es la única forma de "
                    "recuperarla. Guárdalo en un lugar seguro fuera de la app "
                    "(ej. un gestor de contraseñas o una nota física). No volverá "
                    "a mostrarse.",
                    size=12,
                    color=palette.text_secondary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=20),
                code_box,
                ft.Container(height=24),
                ft.FilledButton("Ya lo guardé, continuar", on_click=lambda e: on_continue(), width=280),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        alignment=ft.Alignment.CENTER,
        bgcolor=palette.background,
        expand=True,
        padding=32,
        width=460,
    )


def build_forgot_password(
    palette: Palette,
    on_reset,
    on_back,
    error_text: ft.Text,
) -> ft.Control:
    """Pantalla de recuperación: pide el código y una contraseña nueva."""
    code_field = styled_text_field("Código de recuperación", palette, width=280)
    new_password_field = styled_text_field("Nueva contraseña", palette, width=280)
    new_password_field.password = True
    new_password_field.can_reveal_password = True

    submit_button = ft.FilledButton(
        "Restablecer contraseña",
        on_click=lambda e: on_reset(code_field.value, new_password_field.value),
        width=280,
    )
    back_link = ft.TextButton(
        "Volver al inicio de sesión",
        on_click=lambda e: on_back(),
        style=ft.ButtonStyle(color=palette.text_secondary),
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.HELP_OUTLINE, size=48, color=palette.accent),
                ft.Container(height=8),
                ft.Text(
                    "Recuperar acceso",
                    size=18,
                    weight=ft.FontWeight.W_500,
                    color=palette.text_primary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Ingresa el código de recuperación que guardaste y elige una contraseña nueva.",
                    size=12,
                    color=palette.text_secondary,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                code_field,
                new_password_field,
                error_text,
                ft.Container(height=8),
                submit_button,
                ft.Container(height=4),
                back_link,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        alignment=ft.Alignment.CENTER,
        bgcolor=palette.background,
        expand=True,
        padding=32,
        width=420,
    )
