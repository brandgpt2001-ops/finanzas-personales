"""
Respaldo manual del archivo de base de datos: copia finanzas.db a una
carpeta data/backups/ con un nombre que incluye fecha y hora, para que
nunca se sobreescriban respaldos anteriores.

Usa sqlite3.Connection.backup() — el mecanismo oficial de respaldo de
SQLite — en vez de copiar el archivo crudo con shutil. Esto evita
corrupción si hubiera una escritura en curso al momento de respaldar.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class BackupError(Exception):
    """Error al crear el respaldo, con mensaje listo para mostrar en UI."""


def create_backup(conn: sqlite3.Connection, db_path: Path, backups_dir: Path | None = None) -> Path:
    """Respalda la base de datos activa (conn) a backups_dir con fecha y hora.

    Ej.: finanzas.db -> backups/finanzas_2026-06-28_1430.db

    db_path se usa solo para derivar el nombre del archivo de respaldo
    (stem y extensión); el contenido siempre se lee de conn, no del
    archivo en disco, para evitar copiar un archivo a medio escribir.

    backups_dir por defecto es una carpeta 'backups' junto a db_path.
    Se crea si no existe. Devuelve la ruta del archivo de respaldo creado.
    """
    if backups_dir is None:
        backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    backup_name = f"{db_path.stem}_{timestamp}{db_path.suffix}"
    backup_path = backups_dir / backup_name

    try:
        backup_conn = sqlite3.connect(backup_path)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()
    except sqlite3.Error as exc:
        raise BackupError(f"No se pudo crear el respaldo: {exc}") from exc

    return backup_path


def list_backups(backups_dir: Path) -> list[Path]:
    """Lista los respaldos existentes, más reciente primero."""
    if not backups_dir.exists():
        return []
    return sorted(backups_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
