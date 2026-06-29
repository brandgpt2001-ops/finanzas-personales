"""
Esquema de la base de datos SQLite para la app de finanzas personales.

Tablas:
    months                      -> un registro por cada periodo (año, mes)
    income_entries               -> ingresos del mes, por categoría/fuente
                                     (captura puntual, no persiste como plantilla)
    fixed_expense_definitions    -> catálogo de gastos fijos recurrentes con
                                     vigencia temporal (ver más abajo)
    variable_expenses            -> gastos variables del mes, por categoría
                                     (captura puntual, no persiste como plantilla)
    investments                  -> aportes y rendimientos del mes, por instrumento
                                     (is_mandatory distingue las obligatorias,
                                     como una inversión recurrente en tu empresa,
                                     de las discrecionales que dependen de presupuesto)
    investment_withdrawals       -> retiros de inversión del mes, por instrumento
    auth_credentials              -> contraseña de acceso y código de recuperación,
                                     ambos guardados como hash (nunca en texto plano).
                                     Diseñada para un único registro (app de un
                                     solo usuario); siempre se usa el id=1.

Gastos fijos recurrentes (fixed_expense_definitions):
    A diferencia de ingresos y variables, los gastos fijos NO se capturan
    cada mes. Se definen una vez (ej. "Renta: $8,000") y existen de forma
    indefinida hasta que el usuario los edite o elimine.

    Cada definición tiene vigencia temporal: valid_from / valid_to.
    Al editar el monto, la versión vieja se cierra (valid_to = fecha del
    cambio) y se crea una nueva versión vigente desde ese momento. Así,
    un mes pasado siempre consulta el monto que estaba vigente en ese
    momento, y el historial nunca se reescribe.

    "Eliminar" un gasto fijo no borra filas: cierra la versión vigente
    (valid_to = fecha de eliminación) sin crear una nueva, así deja de
    aparecer en meses futuros pero sigue existiendo en meses pasados
    donde sí aplicaba.

Todas las tablas de detalle referencian a `months` mediante `month_id`
con ON DELETE CASCADE, así que borrar un mes limpia automáticamente
sus ingresos, gastos variables, inversiones y retiros asociados.
fixed_expense_definitions NO depende de months: vive independientemente
y se consulta por fecha de vigencia.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS months (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (year, month)
);

CREATE TABLE IF NOT EXISTS income_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id    INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    amount      REAL NOT NULL CHECK (amount >= 0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fixed_expense_definitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    TEXT NOT NULL,
    category    TEXT NOT NULL,
    amount      REAL NOT NULL CHECK (amount >= 0),
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS variable_expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id    INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    amount      REAL NOT NULL CHECK (amount >= 0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS investments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id        INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    instrument      TEXT NOT NULL,
    amount          REAL NOT NULL CHECK (amount >= 0),
    return_amount   REAL NOT NULL DEFAULT 0,
    is_mandatory    INTEGER NOT NULL DEFAULT 0 CHECK (is_mandatory IN (0, 1)),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS investment_withdrawals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id    INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    instrument  TEXT NOT NULL,
    amount      REAL NOT NULL CHECK (amount >= 0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_credentials (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    user_name                    TEXT NOT NULL DEFAULT '',
    password_hash               TEXT NOT NULL,
    password_salt                TEXT NOT NULL,
    recovery_code_hash           TEXT NOT NULL,
    recovery_code_salt            TEXT NOT NULL,
    updated_at                   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_income_month ON income_entries(month_id);
CREATE INDEX IF NOT EXISTS idx_fixed_def_group ON fixed_expense_definitions(group_id);
CREATE INDEX IF NOT EXISTS idx_fixed_def_validity ON fixed_expense_definitions(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_variable_month ON variable_expenses(month_id);
CREATE INDEX IF NOT EXISTS idx_investments_month ON investments(month_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_month ON investment_withdrawals(month_id);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Abre una conexión a la base, creando el archivo si no existe."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    """Crea las tablas si no existen. Seguro de llamar múltiples veces."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Permite inicializar la base manualmente: python -m finanzas_app.models.schema
    default_path = Path(__file__).resolve().parents[3] / "data" / "finanzas.db"
    init_db(default_path)
    print(f"Base de datos inicializada en: {default_path}")
