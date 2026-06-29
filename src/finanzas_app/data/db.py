"""
Operaciones CRUD de bajo nivel sobre la base de datos SQLite.

Esta capa no sabe nada de pandas ni de la UI; solo ejecuta SQL.
La capa `repository.py` construye sobre esta para entregar DataFrames.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date
from pathlib import Path

from finanzas_app.models.schema import get_connection
from finanzas_app.data import validation

TABLES_BY_KIND = {
    "income": "income_entries",
    "variable": "variable_expenses",
}


def get_or_create_month(conn: sqlite3.Connection, year: int, month: int) -> int:
    """Devuelve el id del mes (year, month); lo crea si no existe.

    year y month se validan y normalizan antes de tocar la base.
    """
    year = validation.clean_year(year)
    month = validation.clean_month(month)

    row = conn.execute(
        "SELECT id FROM months WHERE year = ? AND month = ?", (year, month)
    ).fetchone()
    if row is not None:
        return row["id"]

    cursor = conn.execute(
        "INSERT INTO months (year, month) VALUES (?, ?)", (year, month)
    )
    conn.commit()
    return cursor.lastrowid


def add_entry(conn: sqlite3.Connection, kind: str, month_id: int, category: str, amount: float) -> int:
    """Agrega una fila a income_entries, fixed_expenses o variable_expenses.

    category y amount se normalizan/validan antes de insertar.
    """
    table = TABLES_BY_KIND[kind]
    clean_category = validation.clean_category(category)
    clean_amount = validation.clean_amount(amount, field_name="monto")

    cursor = conn.execute(
        f"INSERT INTO {table} (month_id, category, amount) VALUES (?, ?, ?)",
        (month_id, clean_category, clean_amount),
    )
    conn.commit()
    return cursor.lastrowid


def update_entry(conn: sqlite3.Connection, kind: str, entry_id: int, category: str, amount: float) -> None:
    """Actualiza una fila existente, normalizando category y amount."""
    table = TABLES_BY_KIND[kind]
    clean_category = validation.clean_category(category)
    clean_amount = validation.clean_amount(amount, field_name="monto")

    conn.execute(
        f"UPDATE {table} SET category = ?, amount = ? WHERE id = ?",
        (clean_category, clean_amount, entry_id),
    )
    conn.commit()


def delete_entry(conn: sqlite3.Connection, kind: str, entry_id: int) -> None:
    table = TABLES_BY_KIND[kind]
    conn.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
    conn.commit()


def add_fixed_expense_definition(
    conn: sqlite3.Connection,
    category: str,
    amount: float,
    valid_from: str | None = None,
) -> str:
    """Crea un nuevo gasto fijo recurrente. Devuelve su group_id.

    valid_from: fecha ISO "YYYY-MM-DD" desde la que aplica. Si no se da,
    se usa la fecha de hoy.

    Esto crea la PRIMERA versión de este gasto fijo. Para cambiarle el
    monto más adelante, usa update_fixed_expense_definition (NO esta
    función), que cierra esta versión y abre una nueva.
    """
    clean_category = validation.clean_category(category)
    clean_amount = validation.clean_amount(amount, field_name="monto")
    valid_from = valid_from or date.today().isoformat()
    group_id = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO fixed_expense_definitions
           (group_id, category, amount, valid_from, valid_to)
           VALUES (?, ?, ?, ?, NULL)""",
        (group_id, clean_category, clean_amount, valid_from),
    )
    conn.commit()
    return group_id


def update_fixed_expense_definition(
    conn: sqlite3.Connection,
    group_id: str,
    category: str,
    amount: float,
    effective_date: str | None = None,
) -> None:
    """Cambia el monto/categoría de un gasto fijo a partir de effective_date.

    Cierra la versión vigente (valid_to = effective_date) y crea una
    nueva versión vigente desde ese mismo día. Los meses anteriores a
    effective_date siguen viendo el monto viejo; effective_date en
    adelante usan el nuevo.

    effective_date: fecha ISO "YYYY-MM-DD". Si no se da, se usa hoy.
    """
    clean_category = validation.clean_category(category)
    clean_amount = validation.clean_amount(amount, field_name="monto")
    effective_date = effective_date or date.today().isoformat()

    current = conn.execute(
        """SELECT id FROM fixed_expense_definitions
           WHERE group_id = ? AND valid_to IS NULL""",
        (group_id,),
    ).fetchone()
    if current is None:
        raise ValueError(f"No hay una versión vigente para group_id='{group_id}'.")

    conn.execute(
        "UPDATE fixed_expense_definitions SET valid_to = ? WHERE id = ?",
        (effective_date, current["id"]),
    )
    conn.execute(
        """INSERT INTO fixed_expense_definitions
           (group_id, category, amount, valid_from, valid_to)
           VALUES (?, ?, ?, ?, NULL)""",
        (group_id, clean_category, clean_amount, effective_date),
    )
    conn.commit()


def deactivate_fixed_expense_definition(
    conn: sqlite3.Connection,
    group_id: str,
    effective_date: str | None = None,
) -> None:
    """"Elimina" un gasto fijo: cierra su versión vigente sin abrir una
    nueva. Deja de aparecer en meses futuros, pero los meses pasados que
    ya lo tenían vigente conservan su historial intacto.

    effective_date: fecha ISO "YYYY-MM-DD". Si no se da, se usa hoy.
    """
    effective_date = effective_date or date.today().isoformat()
    conn.execute(
        """UPDATE fixed_expense_definitions
           SET valid_to = ?
           WHERE group_id = ? AND valid_to IS NULL""",
        (effective_date, group_id),
    )
    conn.commit()


def list_active_fixed_expense_definitions(
    conn: sqlite3.Connection, as_of_date: str | None = None
) -> list[sqlite3.Row]:
    """Lista los gastos fijos vigentes en as_of_date (por defecto, hoy).

    Útil para el dashboard del mes actual: muestra solo lo que aplica
    ahora mismo, sin importar el historial de versiones anteriores.
    """
    as_of_date = as_of_date or date.today().isoformat()
    return conn.execute(
        """SELECT id, group_id, category, amount, valid_from, valid_to
           FROM fixed_expense_definitions
           WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)
           ORDER BY category""",
        (as_of_date, as_of_date),
    ).fetchall()


def add_investment(
    conn: sqlite3.Connection,
    month_id: int,
    instrument: str,
    amount: float,
    return_amount: float = 0.0,
    is_mandatory: bool = False,
) -> int:
    """Agrega una inversión, normalizando todos sus campos.

    is_mandatory distingue una inversión no-negociable (ej. la inversión
    recurrente en tu empresa) de una discrecional que solo haces si el
    presupuesto del mes lo permite.
    """
    clean_instrument = validation.clean_category(instrument)
    clean_amount = validation.clean_amount(amount, field_name="aporte")
    clean_return = validation.clean_amount(return_amount, field_name="rendimiento") if return_amount not in (None, "") else 0.0
    clean_mandatory = validation.clean_bool(is_mandatory)

    cursor = conn.execute(
        "INSERT INTO investments (month_id, instrument, amount, return_amount, is_mandatory) VALUES (?, ?, ?, ?, ?)",
        (month_id, clean_instrument, clean_amount, clean_return, int(clean_mandatory)),
    )
    conn.commit()
    return cursor.lastrowid


def update_investment(
    conn: sqlite3.Connection,
    investment_id: int,
    instrument: str,
    amount: float,
    return_amount: float,
    is_mandatory: bool = False,
) -> None:
    """Actualiza una inversión existente, normalizando todos sus campos."""
    clean_instrument = validation.clean_category(instrument)
    clean_amount = validation.clean_amount(amount, field_name="aporte")
    clean_return = validation.clean_amount(return_amount, field_name="rendimiento") if return_amount not in (None, "") else 0.0
    clean_mandatory = validation.clean_bool(is_mandatory)

    conn.execute(
        "UPDATE investments SET instrument = ?, amount = ?, return_amount = ?, is_mandatory = ? WHERE id = ?",
        (clean_instrument, clean_amount, clean_return, int(clean_mandatory), investment_id),
    )
    conn.commit()


def delete_investment(conn: sqlite3.Connection, investment_id: int) -> None:
    conn.execute("DELETE FROM investments WHERE id = ?", (investment_id,))
    conn.commit()


def add_withdrawal(
    conn: sqlite3.Connection,
    month_id: int,
    instrument: str,
    amount: float,
) -> int:
    """Registra un retiro de inversión del mes. Normaliza instrument y amount."""
    clean_instrument = validation.clean_category(instrument)
    clean_amount = validation.clean_amount(amount, field_name="retiro")

    cursor = conn.execute(
        "INSERT INTO investment_withdrawals (month_id, instrument, amount) VALUES (?, ?, ?)",
        (month_id, clean_instrument, clean_amount),
    )
    conn.commit()
    return cursor.lastrowid


def update_withdrawal(
    conn: sqlite3.Connection,
    withdrawal_id: int,
    instrument: str,
    amount: float,
) -> None:
    clean_instrument = validation.clean_category(instrument)
    clean_amount = validation.clean_amount(amount, field_name="retiro")

    conn.execute(
        "UPDATE investment_withdrawals SET instrument = ?, amount = ? WHERE id = ?",
        (clean_instrument, clean_amount, withdrawal_id),
    )
    conn.commit()


def delete_withdrawal(conn: sqlite3.Connection, withdrawal_id: int) -> None:
    conn.execute("DELETE FROM investment_withdrawals WHERE id = ?", (withdrawal_id,))
    conn.commit()


def delete_month(conn: sqlite3.Connection, month_id: int) -> None:
    """Borra un mes completo y, por ON DELETE CASCADE, todas sus entradas."""
    conn.execute("DELETE FROM months WHERE id = ?", (month_id,))
    conn.commit()


def list_months(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, year, month FROM months ORDER BY year, month"
    ).fetchall()
