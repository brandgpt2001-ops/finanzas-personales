"""Pruebas de finanzas_app.data.validation"""

import pytest

from finanzas_app.data.validation import (
    ValidationError,
    clean_amount,
    clean_bool,
    clean_category,
    clean_month,
    clean_year,
)


class TestCleanCategory:
    def test_quita_espacios_extra(self):
        assert clean_category("  comida   rica  ") == "Comida Rica"

    def test_unifica_mayusculas_y_minusculas(self):
        assert clean_category("COMIDA RICA") == clean_category("comida rica")

    def test_respeta_preposiciones_en_minuscula(self):
        assert clean_category("transporte de la casa") == "Transporte de la Casa"

    def test_categoria_vacia_cae_en_default(self):
        assert clean_category("") == "Sin categoría"
        assert clean_category("   ") == "Sin categoría"
        assert clean_category(None) == "Sin categoría"

    def test_palabra_unica(self):
        assert clean_category("renta") == "Renta"


class TestCleanAmount:
    def test_acepta_numero_directo(self):
        assert clean_amount(1234.5) == 1234.5

    def test_acepta_string_con_punto_decimal(self):
        assert clean_amount("800.50") == 800.50

    def test_acepta_separador_de_miles_con_coma(self):
        assert clean_amount("1,234.50") == 1234.50

    def test_acepta_coma_como_decimal(self):
        assert clean_amount("350,75") == 350.75

    def test_redondea_a_dos_decimales(self):
        assert clean_amount(10.999) == 11.0

    def test_rechaza_negativos(self):
        with pytest.raises(ValidationError):
            clean_amount(-100)

    def test_rechaza_texto_no_numerico(self):
        with pytest.raises(ValidationError):
            clean_amount("no es un numero")

    def test_rechaza_vacio(self):
        with pytest.raises(ValidationError):
            clean_amount("")
        with pytest.raises(ValidationError):
            clean_amount(None)


class TestCleanYearMonth:
    def test_year_valido(self):
        assert clean_year(2026) == 2026
        assert clean_year("2026") == 2026

    def test_year_fuera_de_rango(self):
        with pytest.raises(ValidationError):
            clean_year(1800)

    def test_month_valido(self):
        assert clean_month(6) == 6
        assert clean_month("12") == 12

    def test_month_fuera_de_rango(self):
        with pytest.raises(ValidationError):
            clean_month(13)
        with pytest.raises(ValidationError):
            clean_month(0)


class TestCleanBool:
    def test_acepta_booleanos(self):
        assert clean_bool(True) is True
        assert clean_bool(False) is False

    def test_acepta_enteros(self):
        assert clean_bool(1) is True
        assert clean_bool(0) is False

    def test_acepta_strings_comunes(self):
        assert clean_bool("si") is True
        assert clean_bool("sí") is True
        assert clean_bool("no") is False
        assert clean_bool("true") is True
        assert clean_bool("false") is False

    def test_none_es_false(self):
        assert clean_bool(None) is False
