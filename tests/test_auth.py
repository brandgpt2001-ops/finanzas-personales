"""Pruebas de finanzas_app.data.auth"""

import pytest

from finanzas_app.data import auth


class TestSetPasswordAndVerify:
    def test_sin_credenciales_al_inicio(self, conn):
        assert auth.has_credentials(conn) is False

    def test_crear_contrasena_la_deja_disponible(self, conn):
        auth.set_password(conn, "miClave123")
        assert auth.has_credentials(conn) is True

    def test_verifica_contrasena_correcta(self, conn):
        auth.set_password(conn, "miClave123")
        assert auth.verify_password(conn, "miClave123") is True

    def test_rechaza_contrasena_incorrecta(self, conn):
        auth.set_password(conn, "miClave123")
        assert auth.verify_password(conn, "otraClave") is False

    def test_verify_password_sin_credenciales_devuelve_false_no_lanza_error(self, conn):
        assert auth.verify_password(conn, "cualquiera") is False

    def test_rechaza_contrasena_demasiado_corta(self, conn):
        with pytest.raises(auth.ValidationError):
            auth.set_password(conn, "abc")

    def test_set_password_devuelve_codigo_de_recuperacion_valido(self, conn):
        code = auth.set_password(conn, "miClave123")
        assert auth.verify_recovery_code(conn, code) is True

    def test_crear_contrasena_dos_veces_reemplaza_la_anterior(self, conn):
        auth.set_password(conn, "primeraClave")
        auth.set_password(conn, "segundaClave")
        assert auth.verify_password(conn, "primeraClave") is False
        assert auth.verify_password(conn, "segundaClave") is True


class TestUserName:
    def test_sin_nombre_antes_de_crear_contrasena(self, conn):
        assert auth.get_user_name(conn) is None

    def test_guarda_nombre_al_crear_contrasena(self, conn):
        auth.set_password(conn, "miClave123", user_name="Brandon")
        assert auth.get_user_name(conn) == "Brandon"

    def test_change_password_no_borra_el_nombre(self, conn):
        auth.set_password(conn, "viejaClave", user_name="Brandon")
        auth.change_password(conn, "viejaClave", "nuevaClave")
        assert auth.get_user_name(conn) == "Brandon"

    def test_reset_con_codigo_no_borra_el_nombre(self, conn):
        code = auth.set_password(conn, "olvidada", user_name="Brandon")
        auth.reset_password_with_recovery_code(conn, code, "recuperada")
        assert auth.get_user_name(conn) == "Brandon"

    def test_set_password_sin_user_name_conserva_el_existente(self, conn):
        auth.set_password(conn, "primeraClave", user_name="Brandon")
        auth.set_password(conn, "segundaClave")  # sin user_name explícito
        assert auth.get_user_name(conn) == "Brandon"


class TestChangeUserName:
    def test_cambia_exitosamente_con_contrasena_correcta(self, conn):
        auth.set_password(conn, "clave123", user_name="Brandon")
        auth.change_user_name(conn, "clave123", "Brandon G.")
        assert auth.get_user_name(conn) == "Brandon G."

    def test_no_afecta_la_contrasena(self, conn):
        auth.set_password(conn, "clave123", user_name="Brandon")
        auth.change_user_name(conn, "clave123", "Otro Nombre")
        assert auth.verify_password(conn, "clave123") is True

    def test_rechaza_contrasena_incorrecta(self, conn):
        auth.set_password(conn, "clave123", user_name="Brandon")
        with pytest.raises(auth.ValidationError):
            auth.change_user_name(conn, "incorrecta", "Otro Nombre")
        assert auth.get_user_name(conn) == "Brandon"

    def test_rechaza_nombre_vacio(self, conn):
        auth.set_password(conn, "clave123", user_name="Brandon")
        with pytest.raises(auth.ValidationError):
            auth.change_user_name(conn, "clave123", "   ")

    def test_recorta_espacios_del_nombre(self, conn):
        auth.set_password(conn, "clave123", user_name="Brandon")
        auth.change_user_name(conn, "clave123", "  Nombre Nuevo  ")
        assert auth.get_user_name(conn) == "Nombre Nuevo"


class TestChangePassword:
    def test_cambia_exitosamente_con_contrasena_actual_correcta(self, conn):
        auth.set_password(conn, "viejaClave")
        auth.change_password(conn, "viejaClave", "nuevaClave")
        assert auth.verify_password(conn, "viejaClave") is False
        assert auth.verify_password(conn, "nuevaClave") is True

    def test_rechaza_cambio_con_contrasena_actual_incorrecta(self, conn):
        auth.set_password(conn, "viejaClave")
        with pytest.raises(auth.ValidationError):
            auth.change_password(conn, "incorrecta", "nuevaClave")
        # la contraseña original debe seguir intacta
        assert auth.verify_password(conn, "viejaClave") is True

    def test_rechaza_nueva_contrasena_demasiado_corta(self, conn):
        auth.set_password(conn, "viejaClave")
        with pytest.raises(auth.ValidationError):
            auth.change_password(conn, "viejaClave", "ab")

    def test_cambiar_contrasena_no_invalida_codigo_de_recuperacion(self, conn):
        code = auth.set_password(conn, "viejaClave")
        auth.change_password(conn, "viejaClave", "nuevaClave")
        assert auth.verify_recovery_code(conn, code) is True


class TestResetWithRecoveryCode:
    def test_resetea_exitosamente_con_codigo_correcto(self, conn):
        code = auth.set_password(conn, "olvidada")
        auth.reset_password_with_recovery_code(conn, code, "recuperada")
        assert auth.verify_password(conn, "olvidada") is False
        assert auth.verify_password(conn, "recuperada") is True

    def test_rechaza_codigo_de_recuperacion_incorrecto(self, conn):
        auth.set_password(conn, "olvidada")
        with pytest.raises(auth.ValidationError):
            auth.reset_password_with_recovery_code(conn, "codigo-falso-000", "nueva")

    def test_reset_genera_nuevo_codigo_e_invalida_el_anterior(self, conn):
        old_code = auth.set_password(conn, "olvidada")
        new_code = auth.reset_password_with_recovery_code(conn, old_code, "recuperada")

        assert new_code != old_code
        assert auth.verify_recovery_code(conn, old_code) is False
        assert auth.verify_recovery_code(conn, new_code) is True

    def test_reset_no_afecta_contrasena_si_codigo_es_invalido(self, conn):
        auth.set_password(conn, "original")
        with pytest.raises(auth.ValidationError):
            auth.reset_password_with_recovery_code(conn, "codigo-falso-000", "intento")
        assert auth.verify_password(conn, "original") is True


class TestSecretsNeverStoredInPlainText:
    def test_password_hash_no_es_igual_a_la_contrasena_original(self, conn):
        auth.set_password(conn, "miClaveSecreta")
        row = conn.execute("SELECT password_hash FROM auth_credentials WHERE id = 1").fetchone()
        assert row["password_hash"] != "miClaveSecreta"

    def test_recovery_code_hash_no_es_igual_al_codigo_original(self, conn):
        code = auth.set_password(conn, "miClaveSecreta")
        row = conn.execute("SELECT recovery_code_hash FROM auth_credentials WHERE id = 1").fetchone()
        assert row["recovery_code_hash"] != code

    def test_dos_bases_con_la_misma_contrasena_tienen_hashes_distintos(self, conn, tmp_path):
        """El salt aleatorio asegura que la misma contraseña no produzca
        el mismo hash en dos bases de datos distintas."""
        from finanzas_app.models.schema import get_connection, init_db

        auth.set_password(conn, "contraseñaComun")
        row1 = conn.execute("SELECT password_hash, password_salt FROM auth_credentials WHERE id = 1").fetchone()

        db_path2 = tmp_path / "test2.db"
        init_db(db_path2)
        conn2 = get_connection(db_path2)
        auth.set_password(conn2, "contraseñaComun")
        row2 = conn2.execute("SELECT password_hash, password_salt FROM auth_credentials WHERE id = 1").fetchone()
        conn2.close()

        assert row1["password_salt"] != row2["password_salt"]
        assert row1["password_hash"] != row2["password_hash"]
