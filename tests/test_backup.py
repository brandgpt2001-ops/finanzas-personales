"""Pruebas de finanzas_app.data.backup"""

from finanzas_app.data import backup, db


class TestCreateBackup:
    def test_crea_archivo_de_respaldo(self, conn, tmp_path):
        db_path = tmp_path / "finanzas.db"
        db_path.touch()  # el contenido real viene de conn, no del archivo
        backups_dir = tmp_path / "backups"

        backup_path = backup.create_backup(conn, db_path, backups_dir)
        assert backup_path.exists()
        assert backup_path.parent == backups_dir

    def test_respaldo_contiene_los_datos_reales(self, conn, tmp_path):
        db.add_entry(conn, "income", db.get_or_create_month(conn, 2026, 6), "Sueldo", 25000)

        db_path = tmp_path / "finanzas.db"
        db_path.touch()
        backups_dir = tmp_path / "backups"
        backup_path = backup.create_backup(conn, db_path, backups_dir)

        from finanzas_app.models.schema import get_connection
        backup_conn = get_connection(backup_path)
        row = backup_conn.execute(
            "SELECT amount FROM income_entries WHERE category = 'Sueldo'"
        ).fetchone()
        backup_conn.close()

        assert row["amount"] == 25000

    def test_nombre_de_archivo_incluye_fecha(self, conn, tmp_path):
        db_path = tmp_path / "finanzas.db"
        db_path.touch()
        backups_dir = tmp_path / "backups"

        backup_path = backup.create_backup(conn, db_path, backups_dir)
        assert backup_path.name.startswith("finanzas_")
        assert backup_path.suffix == ".db"

    def test_crea_carpeta_backups_si_no_existe(self, conn, tmp_path):
        db_path = tmp_path / "finanzas.db"
        db_path.touch()
        backups_dir = tmp_path / "no_existe_todavia"
        assert not backups_dir.exists()

        backup.create_backup(conn, db_path, backups_dir)
        assert backups_dir.exists()

    def test_backups_dir_por_defecto_es_junto_a_db_path(self, conn, tmp_path):
        db_path = tmp_path / "finanzas.db"
        db_path.touch()

        backup_path = backup.create_backup(conn, db_path)
        assert backup_path.parent == tmp_path / "backups"


class TestListBackups:
    def test_lista_vacia_si_no_existe_la_carpeta(self, tmp_path):
        backups_dir = tmp_path / "no_existe"
        assert backup.list_backups(backups_dir) == []

    def test_lista_ordenada_mas_reciente_primero(self, conn, tmp_path):
        import time

        db_path = tmp_path / "finanzas.db"
        db_path.touch()
        backups_dir = tmp_path / "backups"

        first = backup.create_backup(conn, db_path, backups_dir)
        time.sleep(0.05)
        # Forzar un nombre distinto creando el archivo directo, ya que
        # dentro del mismo segundo create_backup generaría el mismo nombre.
        second = backups_dir / "finanzas_2099-01-01_0000.db"
        second.touch()

        backups = backup.list_backups(backups_dir)
        assert backups[0] == second  # el más reciente por fecha de modificación
