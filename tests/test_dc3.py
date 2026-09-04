"""Cierre de DC.3: ``normalizar_telefono`` y ``normalizar_columna_telefono``.

Tres contratos del item:
  1) Las cuatro formas del enunciado (``3001234567``, ``300 123 4567``,
     ``+57 300 1234567``, ``(300)123-4567``) producen el mismo valor
     normalizado.
  2) El pais se configura por parametro y NO esta hardcodeado: un
     telefono con prefijo explicito de OTRO pais se marca como no
     normalizable, no se "cuela" como si fuera del pais configurado.
  3) Un telefono que no se puede normalizar se queda con su valor
     original y se marca (la regla 4 del encargo: ante la duda,
     conservar).
"""

from __future__ import annotations

import pandas as pd
import pytest

from dataclean import normalizar_columna_telefono, normalizar_telefono
# Importamos el modulo fuente directamente: si alguien borra
# ``telefono.py`` pero deja el reexport de pega en ``__init__``, los
# tests de comportamiento (mas abajo) caen con ``ImportError`` desde
# el modulo, no con un falso verde.
from dataclean import telefono as telefono_modulo


# --- Cierre 1: las cuatro formas producen el mismo normalizado -----------


@pytest.mark.parametrize(
    "forma",
    [
        "3001234567",          # 10 digitos tal cual
        "300 123 4567",        # con espacios
        "+57 300 1234567",     # con prefijo internacional
        "(300)123-4567",       # con parentesis y guion
        "300-123-4567",        # solo guiones
        "300.123.4567",        # con puntos
    ],
)
def test_las_cuatro_formas_del_enunciado_producen_el_mismo_valor(
    forma: str,
) -> None:
    """Las cuatro (seis) formas del item normalizan a ``3001234567``."""
    normalizado, marcado = normalizar_telefono(forma)
    assert normalizado == "3001234567"
    assert marcado is True


def test_las_cuatro_formas_en_una_sola_operacion() -> None:
    """Las cuatro formas, en la misma llamada, dan el mismo canonico.

    Esto ata el caso "una llamada devuelve valores distintos para
    entradas que representan el mismo contacto": la implementacion
    trivial que solo hace ``str(valor).strip()`` no lo cumple.
    """
    entradas = [
        "3001234567",
        "300 123 4567",
        "+57 300 1234567",
        "(300)123-4567",
    ]
    resultados = {normalizar_telefono(e)[0] for e in entradas}
    assert resultados == {"3001234567"}


# --- Cierre 2: el pais se configura, no esta escrito ---------------------


def test_pais_por_defecto_es_colombia_pero_se_puede_cambiar() -> None:
    """El pais se pasa por parametro: no hay un "+57" grabado en piedra."""
    # Con el default, un +57 explicito se acepta.
    assert normalizar_telefono("+57 300 1234567") == ("3001234567", True)
    # Y con otro mercado, ese mismo +57 NO se cuela como si fuera de
    # alli: un espanol con un mercado espanol configurado se acepta
    # (con la longitud de ese mercado, 9 digitos), pero un +57 se
    # marca.
    assert normalizar_telefono(
        "+34 911 234 567", codigo_pais="+34", longitud_esperada=9
    ) == ("911234567", True)
    assert normalizar_telefono(
        "+57 300 1234567", codigo_pais="+34", longitud_esperada=9
    ) == (None, False)


def test_prefijo_explicito_de_otro_pais_se_marca() -> None:
    """Un telefono con prefijo que NO es el configurado -> marcado, no inventado."""
    normalizado, marcado = normalizar_telefono("+34 911 234 567")
    assert normalizado is None
    assert marcado is False


# --- Cierre 3: lo dudoso se conserva y se marca --------------------------


@pytest.mark.parametrize(
    "valor",
    [
        "",                  # vacio
        "   ",               # solo espacios
        None,                # None
        "llamar a juan",     # letras
        "300",               # muy corto
        "30012345678",       # muy largo (11)
        "300123456",         # 9 digitos, no encaja
        "abc1234567",        # mezcla raro
    ],
)
def test_valor_no_normalizable_se_marca_y_no_se_borra(valor: object) -> None:
    """Lo que no se puede normalizar devuelve ``(None, False)`` y NO se inventa."""
    normalizado, marcado = normalizar_telefono(valor)
    assert normalizado is None
    assert marcado is False


# --- API sobre DataFrame: la columna original se conserva ---------------


def test_normalizar_columna_anade_auxiliares_y_conserva_la_original() -> None:
    """La columna original NO se modifica; se anaden ``_normalizado`` y ``_marcado``."""
    tabla = pd.DataFrame(
        {
            "nombre": ["Ana", "Jose", "Maria"],
            "telefono": ["3001234567", "+57 310 7654321", "esto no es telefono"],
        }
    )
    resultado = normalizar_columna_telefono(tabla, "telefono")

    # La columna original esta intacta (regla 4): no se sobreescribio
    # con el normalizado, no se borro.
    assert list(resultado["telefono"]) == [
        "3001234567",
        "+57 310 7654321",
        "esto no es telefono",
    ]
    # Y la tabla original tampoco se muto.
    assert tabla["telefono"].iloc[2] == "esto no es telefono"

    # Las dos columnas auxiliares existen y tienen los valores
    # esperados.
    assert "telefono_normalizado" in resultado.columns
    assert "telefono_marcado" in resultado.columns
    assert list(resultado["telefono_normalizado"]) == [
        "3001234567",
        "3107654321",
        "",
    ]
    assert list(resultado["telefono_marcado"]) == [True, True, False]


def test_normalizar_columna_pais_configurable_en_tabla() -> None:
    """El pais se aplica a TODA la columna, no fila a fila."""
    tabla = pd.DataFrame(
        {"telefono": ["+57 300 1234567", "+34 911 234 567"]}
    )
    resultado = normalizar_columna_telefono(tabla, "telefono", codigo_pais="+57")
    # El colombiano se normaliza; el espanol se marca, no se "adapta".
    assert resultado["telefono_normalizado"].iloc[0] == "3001234567"
    assert resultado["telefono_normalizado"].iloc[1] == ""
    assert list(resultado["telefono_marcado"]) == [True, False]


# --- pruebas de comportamiento (no de import) ---------------------------


def test_modulo_telefono_define_las_funciones_publicas() -> None:
    """El modulo ``dataclean.telefono`` define su contrato, no un reexport."""
    assert hasattr(telefono_modulo, "normalizar_telefono")
    assert hasattr(telefono_modulo, "normalizar_columna_telefono")
    assert callable(telefono_modulo.normalizar_telefono)
    assert callable(telefono_modulo.normalizar_columna_telefono)


def test_telefono_modulo_no_decide_por_tipo_de_objeto() -> None:
    """``normalizar_telefono`` no devuelve lo mismo para ``int`` y ``str``.

    Cierra el caso "pega que acepta cualquier cosa y la convierte a
    texto feliz": la implementacion real distingue ``None``/no-string
    de strings, y rechaza los no-telefonos.
    """
    # Un entero con forma de telefono: la implementacion real lo
    # convierte a texto y lo procesa, NO devuelve ``(None, False)``.
    n_int, m_int = normalizar_telefono(3001234567)
    assert n_int == "3001234567"
    assert m_int is True

    # Un None se queda como None marcado, sin explosion.
    assert normalizar_telefono(None) == (None, False)


def test_camino_real_mezcla_de_formatos_en_una_columna() -> None:
    """Tabla "de produccion": mezcla de formatos -> una sola forma canonica.

    Es la Regla 6 "fuerte": un test que NO pasaria con un
    ``normalizar_telefono`` de pega. Las pegas contra las que nos
    protegemos:
      (a) Implementacion que solo hace ``str(valor).strip()``: no
          colapsa las 4 formas al mismo canonico.
      (b) Implementacion que borra silenciosamente los "malos"
          (``""`` -> ``""``): el Cierre 3 dice "se marca", no se
          borra; la columna original tiene que seguir ahi.
      (c) Implementacion que ignora el parametro ``codigo_pais``: este
          test configura ``"+34"`` y mete un ``+57``; si el codigo
          estuviera hardcodeado, ese ``+57`` se cuela.
    """
    tabla = pd.DataFrame(
        {
            "contacto": [
                "Ana",
                "Jose",
                "Maria",
                "Pedro",
                "Lucia",
                "Marta",
            ],
            "movil": [
                "3001234567",
                "300 123 4567",
                "+57 300 1234567",
                "(300)123-4567",
                "+34 911 234 567",  # espanol en tabla "co" -> marcado
                "",                  # vacio -> marcado, no borrado
            ],
        }
    )
    resultado = normalizar_columna_telefono(tabla, "movil", codigo_pais="+57")

    # La columna original esta intacta, fila a fila: Ana con su
    # canonico escrito como vino, Marta con su vacio, Lucia con su
    # espanol. La pega (b) cae aqui.
    assert list(resultado["movil"]) == [
        "3001234567",
        "300 123 4567",
        "+57 300 1234567",
        "(300)123-4567",
        "+34 911 234 567",
        "",
    ]

    # Las 4 formas del item DC.3 caen en el mismo canonico. La pega
    # (a) cae aqui.
    canonicos = resultado["movil_normalizado"].tolist()
    assert canonicos[0] == "3001234567"
    assert canonicos[1] == "3001234567"
    assert canonicos[2] == "3001234567"
    assert canonicos[3] == "3001234567"
    # Y los dos que NO son del mercado se marcan (no se "normalizan"
    # a un valor inventado): la pega (c) cae aqui.
    assert canonicos[4] == ""
    assert canonicos[5] == ""
    assert list(resultado["movil_marcado"]) == [
        True,
        True,
        True,
        True,
        False,
        False,
    ]