"""
Autenticación local de un solo usuario: contraseña de acceso y código
de recuperación, ambos guardados como hash con salt — nunca en texto
plano, ni siquiera en memoria más tiempo del necesario.

Algoritmo: PBKDF2-HMAC-SHA256 (vía hashlib, sin dependencias externas).
200,000 iteraciones es un estándar razonable para 2026 en hardware de
escritorio: lento para un atacante que prueba muchas contraseñas,
imperceptible para el usuario real que solo escribe la suya una vez.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3

PBKDF2_ITERATIONS = 200_000


class ValidationError(ValueError):
    """Error de validación con mensaje listo para mostrar en UI."""


def _hash_secret(secret: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return digest.hex()


def _new_salt() -> str:
    return secrets.token_hex(16)


def generate_recovery_code() -> str:
    """Genera un código de recuperación legible, ej. 'a3f9-7c21-4e08'.

    Se muestra UNA SOLA VEZ al usuario en texto plano, en el momento de
    crear o resetear la contraseña. Después de eso, solo se guarda su
    hash — ni siquiera la app puede volver a mostrarlo.
    """
    return "-".join(secrets.token_hex(2) for _ in range(3))


def has_credentials(conn: sqlite3.Connection) -> bool:
    """True si ya existe una contraseña configurada (no es la primera vez)."""
    row = conn.execute("SELECT 1 FROM auth_credentials WHERE id = 1").fetchone()
    return row is not None


def _validate_password_strength(password: str) -> None:
    if not password or len(password) < 4:
        raise ValidationError("La contraseña debe tener al menos 4 caracteres.")


def set_password(conn: sqlite3.Connection, new_password: str, user_name: str | None = None) -> str:
    """Crea o reemplaza la contraseña y genera un nuevo código de recuperación.

    user_name: si se da, actualiza el nombre guardado (usado en el saludo
    de bienvenida). Si es None, conserva el nombre existente sin cambiarlo
    — así change_password/reset_password_with_recovery_code, que también
    usan esta función internamente, no requieren pedir el nombre de nuevo.

    Devuelve el código de recuperación EN TEXTO PLANO — es la única vez
    que estará disponible; el llamador debe mostrarlo al usuario de
    inmediato y no debe loguearlo ni guardarlo en ningún otro lado.
    """
    _validate_password_strength(new_password)

    password_salt = _new_salt()
    password_hash = _hash_secret(new_password, password_salt)

    recovery_code = generate_recovery_code()
    recovery_salt = _new_salt()
    recovery_hash = _hash_secret(recovery_code, recovery_salt)

    existing_name = get_user_name(conn) or ""
    name_to_store = user_name if user_name is not None else existing_name

    conn.execute(
        """
        INSERT INTO auth_credentials (id, user_name, password_hash, password_salt, recovery_code_hash, recovery_code_salt, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            user_name = excluded.user_name,
            password_hash = excluded.password_hash,
            password_salt = excluded.password_salt,
            recovery_code_hash = excluded.recovery_code_hash,
            recovery_code_salt = excluded.recovery_code_salt,
            updated_at = excluded.updated_at
        """,
        (name_to_store, password_hash, password_salt, recovery_hash, recovery_salt),
    )
    conn.commit()
    return recovery_code


def get_user_name(conn: sqlite3.Connection) -> str | None:
    """Devuelve el nombre guardado, o None si no hay credenciales todavía."""
    row = conn.execute("SELECT user_name FROM auth_credentials WHERE id = 1").fetchone()
    if row is None:
        return None
    return row["user_name"] or None


def verify_password(conn: sqlite3.Connection, password: str) -> bool:
    """Verifica si la contraseña dada coincide con la guardada.

    Devuelve False si no hay credenciales configuradas todavía, en vez
    de lanzar error — el llamador decide qué hacer en ese caso (típicamente
    redirigir a la pantalla de creación de contraseña).
    """
    row = conn.execute(
        "SELECT password_hash, password_salt FROM auth_credentials WHERE id = 1"
    ).fetchone()
    if row is None:
        return False
    candidate_hash = _hash_secret(password, row["password_salt"])
    return secrets.compare_digest(candidate_hash, row["password_hash"])


def verify_recovery_code(conn: sqlite3.Connection, code: str) -> bool:
    """Verifica si el código de recuperación dado coincide con el guardado."""
    row = conn.execute(
        "SELECT recovery_code_hash, recovery_code_salt FROM auth_credentials WHERE id = 1"
    ).fetchone()
    if row is None:
        return False
    candidate_hash = _hash_secret(code, row["recovery_code_salt"])
    return secrets.compare_digest(candidate_hash, row["recovery_code_hash"])


def change_password(conn: sqlite3.Connection, current_password: str, new_password: str) -> None:
    """Cambia la contraseña sabiendo la actual. No genera nuevo código de recuperación
    (el código de recuperación solo cambia vía reset_password_with_recovery_code,
    para no invalidarlo silenciosamente cada vez que el usuario cambia su clave)."""
    if not verify_password(conn, current_password):
        raise ValidationError("La contraseña actual no es correcta.")
    _validate_password_strength(new_password)

    new_salt = _new_salt()
    new_hash = _hash_secret(new_password, new_salt)
    conn.execute(
        "UPDATE auth_credentials SET password_hash = ?, password_salt = ?, updated_at = datetime('now') WHERE id = 1",
        (new_hash, new_salt),
    )
    conn.commit()


def reset_password_with_recovery_code(conn: sqlite3.Connection, recovery_code: str, new_password: str) -> str:
    """Resetea la contraseña usando el código de recuperación, ya que el
    usuario olvidó su contraseña. Genera un NUEVO código de recuperación
    (el anterior queda invalidado) y lo devuelve en texto plano.
    """
    if not verify_recovery_code(conn, recovery_code):
        raise ValidationError("El código de recuperación no es correcto.")
    return set_password(conn, new_password)


def change_user_name(conn: sqlite3.Connection, current_password: str, new_name: str) -> None:
    """Cambia el nombre mostrado en el saludo, verificando la contraseña
    actual como confirmación de identidad (no se requiere código de
    recuperación porque el usuario ya está autenticado dentro de la app)."""
    if not verify_password(conn, current_password):
        raise ValidationError("La contraseña actual no es correcta.")
    clean_name = (new_name or "").strip()
    if not clean_name:
        raise ValidationError("El nombre no puede estar vacío.")

    conn.execute(
        "UPDATE auth_credentials SET user_name = ?, updated_at = datetime('now') WHERE id = 1",
        (clean_name,),
    )
    conn.commit()
