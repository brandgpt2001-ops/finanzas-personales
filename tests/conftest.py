"""Fixtures compartidos para todas las pruebas.

pytest descubre este archivo automáticamente; cualquier fixture aquí
está disponible en todos los test_*.py sin necesidad de importarlo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from finanzas_app.models.schema import init_db, get_connection


@pytest.fixture
def conn(tmp_path):
    """Conexión a una base de datos SQLite limpia, en un archivo temporal.

    tmp_path es un fixture nativo de pytest: crea un directorio temporal
    único por prueba y lo borra automáticamente al terminar. Así cada
    prueba arranca con una base 100% vacía, sin contaminar a las demás.
    """
    db_path = tmp_path / "test.db"
    init_db(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()
