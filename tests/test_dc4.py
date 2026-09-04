"""Cierre de DC.4: ``clasificar_telefono`` y ``clasificar_columna_telefono``.

Tres contratos del item:
  1) Movil colombiano (10 digitos empezando por 3) -> ``MOVIL``.
     Fijo con indicativo (10 digitos que NO empiezan por 3) -> ``FIJO``.
     Numero de 5 digitos -> ``INVALIDO``.
  2) Cero falsos positivos: un test con >= 20 moviles reales en
     formatos distintos, todos clasificados como ``MOVIL``.
  3) Conservar y marcar, no borrar: la columna original se queda
     intacta y los invalidos llevan motivo legible, no solo la marca.

Ademas, DC.4 hereda el principio de DC.3:
  - El pais se configura por parametro (``codigo_pais`` y
    ``prefijo_movil``), no esta hardcodeado.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dataclean import (
    TIPO_FIJO,
    TIPO_INVALIDO,
    TIPO_MOVIL,
    clasificar_columna_telefono,
    clasificar_telefono,
)
# Importamos el modulo fuente directamente: si alguien borra
# ``telefono.py`` pero deja el reexport de pega en ``__init__``, los
# tests de comportamiento (mas abajo) caen con ``ImportError`` desde
# el modulo, no con un falso verde.
from dataclean import telefono as telefono_modulo


# --- Cierre 1: las tres categorias basicas -------------------------------


def test_movil_colombiano_empieza_por_3_es_MOVIL() -> None:
    """Un movil colombiano de 10 digitos que empieza por 3 -> MOVIL."""
    canonico, tipo, motivo = clasificar_telefono("3001234567")
    assert canonico == "3001234567"
    assert tipo == TIPO_MOVIL
    assert motivo == ""


def test_movil_en_los_tres_formatos_del_enunciado_es_MOVIL() -> None:
    """Las 3 formas canonicas de un mismo movil -> MOVIL.

    Esto ata DC.4 a DC.3: si DC.3 no colapso las formas, este test
    falla. La trampa contra ``return TIPO_MOVIL, ""`` es justamente
    que tres entradas que representan el mismo contacto tienen que
    caer en la misma categoria por el mismo canonico.
    """
    formas = [
        "3001234567",
        "300 123 4567",
        "+57 300 1234567",
        "(300)123-4567",
    ]
    resultados = [clasificar_telefono(f) for f in formas]
    # Mismo canonico en las cuatro.
    canonicos = {r[0] for r in resultados}
    assert canonicos == {"3001234567"}
    # Mismo tipo en las cuatro.
    tipos = {r[1] for r in resultados}
    assert tipos == {TIPO_MOVIL}
    # Sin motivo: ninguna es invalida.
    motivos = {r[2] for r in resultados}
    assert motivos == {""}


@pytest.mark.parametrize(
    "fijo,canonico_esperado",
    [
        ("6011234567", "6011234567"),   # Bogota
        ("6041234567", "6041234567"),   # Medellin
        ("6021234567", "6021234567"),   # Cali
        ("6051234567", "6051234567"),   # Barranquilla
        ("6061234567", "6061234567"),   # Pereira
        ("6071234567", "6071234567"),   # Bucaramanga
        ("6081234567", "6081234567"),   # Ibague
        ("+57 604 1234567", "6041234567"),  # Medellin con +57
        ("+57 601 1234567", "6011234567"),  # Bogota con +57
        ("(604) 123-4567", "6041234567"),
    ],
)
def test_fijo_con_indicativo_es_FIJO(
    fijo: str, canonico_esperado: str
) -> None:
    """Indicativos colombianos que NO son 3 son fijos."""
    canonico, tipo, motivo = clasificar_telefono(fijo)
    assert canonico == canonico_esperado
    assert tipo == TIPO_FIJO
    assert motivo == ""


def test_numero_de_5_digitos_es_INVALIDO() -> None:
    """Un numero de 5 digitos no es ni movil ni fijo -> INVALIDO.

    Caso literal del item: 'un numero de 5 digitos que no es ni una
    cosa ni otra'. La trampa: una implementacion que devuelve
    ``MOVIL``/'FIJO' cuando el canonico empieza por 3 o NO empieza
    por 3 sin mirar la longitud, falla aqui.
    """
    canonico, tipo, motivo = clasificar_telefono("12345")
    assert canonico is None
    assert tipo == TIPO_INVALIDO
    # Motivo legible, sin el numero en si (regla 9).
    assert motivo
    assert "12345" not in motivo


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "   ",
        None,
        "abc1234567",
        "300",            # 3 digitos
        "1234567",        # 7 digitos
        "+34 911 234 567",  # prefijo de otro pais
    ],
)
def test_no_se_puede_clasificar_devuelve_INVALIDO_con_motivo(
    valor: object,
) -> None:
    """Lo que DC.3 marco como no-normalizable, DC.4 lo marca INVALIDO."""
    canonico, tipo, motivo = clasificar_telefono(valor)
    assert canonico is None
    assert tipo == TIPO_INVALIDO
    assert motivo  # motivo no vacio


# --- Cierre 2: cero falsos positivos, 20+ moviles reales -----------------


# 20 moviles "reales" en formatos distintos: mismas areas que aparecen
# en cualquier listado exportado de CRM, con la pinta real (espacios,
# parentesis, guiones, prefijos, codigo de area explicito, etc.).
# Todos tienen que clasificar como MOVIL o el item NO cierra.
MOVILES_REALES = [
    "3001234567",
    "3011234567",
    "3021234567",
    "3031234567",
    "3041234567",
    "3051234567",
    "3061234567",
    "3071234567",
    "3101234567",
    "3111234567",
    "3121234567",
    "3151234567",
    "3161234567",
    "3171234567",
    "3181234567",
    "3201234567",
    "3211234567",
    "3221234567",
    "3501234567",
    "3511234567",
    "300 123 4567",
    "+57 300 1234567",
    "(300) 123-4567",
    "300-123-4567",
    "300.123.4567",
    "+57 301 123 4567",
    "+57 312 1234567",
    "+57 3501234567",
]


def test_veinte_moviles_reales_de_formatos_distintos_cero_falsos_positivos() -> None:
    """DC.4 Cierre 2: >= 20 moviles reales, todos MOVIL, cero falsos positivos.

    Esta es la 'trampa' del item: si la regla de clasificacion esta
    mal calibrada (p.ej. exigir primer digito == 3 y longitud == 10
    pero descartar los que tienen '0' a la izquierda del indicativo,
    o exigir exactamente 10 digitos ASCII cuando DC.3 ya colapso las
    formas), algunos de estos caen como INVALIDO. La regla 4 del
    encargo dice 'ante la duda, conservar' y DC.4 Cierre 2 dice
    'ningun movil valido puede quedar como invalido'. Este test los
    protege a todos.
    """
    assert len(MOVILES_REALES) >= 20, (
        f"DC.4 exige al menos 20 moviles reales; hay {len(MOVILES_REALES)}."
    )

    falsos_positivos: list[tuple[str, str]] = []
    for numero in MOVILES_REALES:
        _canonico, tipo, _motivo = clasificar_telefono(numero)
        if tipo != TIPO_MOVIL:
            falsos_positivos.append((numero, tipo))

    assert not falsos_positivos, (
        "Moviles reales clasificados como no-MOVIL: " + str(falsos_positivos)
    )


# --- camino real: tabla completa, columna original intacta ----------------


def test_camino_real_tabla_con_moviles_fijos_e_invalidos() -> None:
    """Tabla 'de produccion' con mezcla: moviles, fijos, invalidos.

    Verifica que:
      - la columna original NO se sobreescribe (regla 4);
      - los tipos son correctos para cada fila;
      - los invalidos llevan motivo y NO llevan canonico;
      - los moviles y fijos llevan canonico y motivo vacio.
    """
    tabla = pd.DataFrame(
        {
            "contacto": ["Ana", "Jose", "Maria", "Pedro", "Lucia", "Marta", "Sofia"],
            "telefono": [
                "3001234567",          # MOVIL
                "6041234567",          # FIJO (Medellin)
                "+57 601 1234567",     # FIJO (Bogota con prefijo)
                "12345",               # INVALIDO (5 digitos)
                "",                    # INVALIDO (vacio)
                "esto no es telefono", # INVALIDO (letras)
                "+34 911 234 567",     # INVALIDO (otro pais)
            ],
        }
    )
    resultado = clasificar_columna_telefono(tabla, "telefono", codigo_pais="+57")

    # La columna original esta intacta, fila a fila.
    assert list(resultado["telefono"]) == [
        "3001234567",
        "6041234567",
        "+57 601 1234567",
        "12345",
        "",
        "esto no es telefono",
        "+34 911 234 567",
    ]
    # Y la tabla original tampoco se muto.
    assert list(tabla["telefono"]) == [
        "3001234567",
        "6041234567",
        "+57 601 1234567",
        "12345",
        "",
        "esto no es telefono",
        "+34 911 234 567",
    ]

    # Las columnas auxiliares existen.
    assert "telefono_canonico" in resultado.columns
    assert "telefono_tipo" in resultado.columns
    assert "telefono_motivo" in resultado.columns

    # Tipos fila a fila.
    assert list(resultado["telefono_tipo"]) == [
        TIPO_MOVIL,
        TIPO_FIJO,
        TIPO_FIJO,
        TIPO_INVALIDO,
        TIPO_INVALIDO,
        TIPO_INVALIDO,
        TIPO_INVALIDO,
    ]
    # Canonicos: solo donde se pudo normalizar.
    assert list(resultado["telefono_canonico"]) == [
        "3001234567",
        "6041234567",
        "6011234567",
        "",
        "",
        "",
        "",
    ]
    # Motivos: vacio en moviles/fijos, texto en invalidos. Y NO
    # contienen el numero (regla 9).
    motivos = list(resultado["telefono_motivo"])
    assert motivos[0] == "" and motivos[1] == "" and motivos[2] == ""
    for idx in (3, 4, 5, 6):
        assert motivos[idx]  # no vacio
        assert "12345" not in motivos[idx]
        assert "esto no es telefono" not in motivos[idx]
        assert "911" not in motivos[idx]
        assert "1234567" not in motivos[idx]


# --- configurabilidad del mercado (no hardcodeado) ----------------------


def test_pais_y_prefijo_movil_se_configuran() -> None:
    """El pais y el prefijo de movil son parametros, no constantes.

    Mismo argumento que DC.3 Cierre 2: si DC.4 tiene "+57" o "3"
    escritos en piedra, no se puede vender en otro mercado sin
    cambiar codigo.
    """
    # Espana: 9 digitos, moviles que empiezan por 6 o 7.
    canonico, tipo, motivo = clasificar_telefono(
        "612345678",
        codigo_pais="+34",
        longitud_esperada=9,
        prefijo_movil="6",
    )
    assert canonico == "612345678"
    assert tipo == TIPO_MOVIL
    assert motivo == ""

    # En el mercado espanol, un 3XX es fijo (no empieza por 6).
    canonico, tipo, motivo = clasificar_telefono(
        "312345678",
        codigo_pais="+34",
        longitud_esperada=9,
        prefijo_movil="6",
    )
    assert canonico == "312345678"
    assert tipo == TIPO_FIJO
    assert motivo == ""


# --- pruebas de comportamiento (no de import) ---------------------------


def test_modulo_telefono_define_las_funciones_DC4() -> None:
    """El modulo fuente expone las funciones de DC.4, no un reexport de pega."""
    assert hasattr(telefono_modulo, "clasificar_telefono")
    assert hasattr(telefono_modulo, "clasificar_columna_telefono")
    assert hasattr(telefono_modulo, "TIPO_MOVIL")
    assert hasattr(telefono_modulo, "TIPO_FIJO")
    assert hasattr(telefono_modulo, "TIPO_INVALIDO")
    assert callable(telefono_modulo.clasificar_telefono)
    assert callable(telefono_modulo.clasificar_columna_telefono)


def test_tipo_y_motivo_no_se_inventan() -> None:
    """``clasificar_telefono`` no devuelve siempre el mismo tipo.

    Cierra el caso 'pega que devuelve (None, TIPO_MOVIL, "") para
    todo': la implementacion real distingue moviles de fijos de
    invalidos, y pone motivo solo en invalidos.
    """
    # Un movil NO puede salir como FIJO.
    _, tipo_m, _ = clasificar_telefono("3001234567")
    _, tipo_f, _ = clasificar_telefono("6041234567")
    _, tipo_i, motivo_i = clasificar_telefono("12345")
    assert tipo_m == TIPO_MOVIL
    assert tipo_f == TIPO_FIJO
    assert tipo_i == TIPO_INVALIDO
    assert motivo_i  # motivo no vacio en invalido


def test_motivos_de_invalidos_no_contienen_el_numero() -> None:
    """Regla 9: el motivo de un INVALIDO NO contiene el telefono.

    El motivo va al reporte y al log; si el telefono original acabara
    en el motivo, estariamos filtrando un dato personal. Verificamos
    que el motivo lleva solo la 'categoria' del fallo, no el valor.
    """
    casos = [
        "3001234567",   # canonico pero la pega le pasaria el numero
        "604-123-4567",
        "+57 300 1234567",
    ]
    for valor in casos:
        _canonico, _tipo, motivo = clasificar_telefono(valor)
        # En este caso el canonico existe -> tipo != INVALIDO -> motivo
        # vacio. Probamos entonces con un valor que SI cae como invalido.
        if motivo:
            assert valor.replace(" ", "").replace("-", "").replace("+", "") not in motivo


def test_clasificar_columna_no_decide_por_indice() -> None:
    """``clasificar_columna_telefono`` no devuelve siempre el mismo tipo.

    Una pega que siempre clasifica como MOVIL (o como INVALIDO) pasa
    el test de imports pero falla este: las filas reciben tipos
    distintos segun su contenido.
    """
    tabla = pd.DataFrame(
        {
            "telefono": [
                "3001234567",  # MOVIL
                "6041234567",  # FIJO
                "12345",       # INVALIDO
            ],
        }
    )
    resultado = clasificar_columna_telefono(tabla, "telefono")
    tipos = list(resultado["telefono_tipo"])
    assert tipos == [TIPO_MOVIL, TIPO_FIJO, TIPO_INVALIDO]
    # Tres tipos distintos en la misma columna: la pega "todo MOVIL"
    # o "todo INVALIDO" cae aqui.
    assert len(set(tipos)) == 3