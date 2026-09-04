"""Cierre de DC.2: ``clasificar_columnas`` decide el rol por el nombre.

Tres contratos del item:
  1) Sobre las cinco cabeceras del enunciado (``TELEFONO``, ``Cel``,
     ``movil 2``, ``Correo electronico``, ``NOMBRE COMPLETO``)
     identifica telefono, correo y nombre correctamente.
  2) Una columna que no reconoce se conserva intacta y se marca como
     no clasificada; no se descarta, no se modifica.
  3) La clasificacion es robusta a mayusculas, tildes y espacios
     sobrantes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dataclean import RolColumna, clasificar_columnas
# Importamos el modulo fuente directamente: si alguien borra
# ``clasificacion.py`` pero deja el reexport de pega en ``__init__``,
# los tests del comportamiento (mas abajo) caen.
from dataclean import clasificacion as clasificacion_modulo


# --- Cierre 1: las cinco cabeceras del enunciado -------------------------


def test_clasifica_las_cinco_cabeceras_del_enunciado() -> None:
    """TELEFONO, Cel, movil 2, Correo electronico, NOMBRE COMPLETO.

    El enunciado del item lista estas cinco cabeceras exactas y dice
    que tenemos que saber cual es telefono, cual correo y cual
    nombre. Las tres primeras son variantes de telefono (el enunciado
    las junta a proposito: ``Cel`` y ``movil 2`` son sinonimos
    telefonicos).
    """
    tabla = pd.DataFrame(
        columns=["TELEFONO", "Cel", "movil 2", "Correo electronico", "NOMBRE COMPLETO"]
    )
    roles = clasificar_columnas(tabla)
    assert roles == {
        "TELEFONO": RolColumna.TELEFONO,
        "Cel": RolColumna.TELEFONO,
        "movil 2": RolColumna.TELEFONO,
        "Correo electronico": RolColumna.CORREO,
        "NOMBRE COMPLETO": RolColumna.NOMBRE,
    }


# --- Cierre 2: columna desconocida se conserva como no clasificada -----


def test_columna_desconocida_se_conserva_y_se_marca_como_no_clasificada() -> None:
    """Una columna que no reconocemos NO se borra, se queda con su nombre."""
    tabla = pd.DataFrame(
        columns=["nombre", "telefono", "ciudad_de_residencia", "codigo_interno"]
    )
    roles = clasificar_columnas(tabla)

    # Lo conocido entra bien.
    assert roles["nombre"] == RolColumna.NOMBRE
    assert roles["telefono"] == RolColumna.TELEFONO
    # Y lo desconocido aparece marcado, no desaparece.
    assert roles["ciudad_de_residencia"] == RolColumna.NO_CLASIFICADA
    assert roles["codigo_interno"] == RolColumna.NO_CLASIFICADA
    # Ademas, la tabla original NO se ha tocado: la clasificacion
    # lee, no escribe.
    assert list(tabla.columns) == [
        "nombre",
        "telefono",
        "ciudad_de_residencia",
        "codigo_interno",
    ]


# --- Cierre 3: robusto a mayusculas, tildes y espacios sobrantes --------


@pytest.mark.parametrize(
    "cabecera, rol_esperado",
    [
        ("TELEFONO", RolColumna.TELEFONO),
        ("telefono", RolColumna.TELEFONO),
        ("  Telefono  ", RolColumna.TELEFONO),       # espacios sobrantes
        ("TELÉFONO", RolColumna.TELEFONO),            # tilde
        ("teléfono", RolColumna.TELEFONO),            # tilde + minuscula
        ("Correo  Electrónico", RolColumna.CORREO),   # espacio + tilde
        ("NOMBRE COMPLETO", RolColumna.NOMBRE),       # mayusculas + espacio
        ("  nombre   completo ", RolColumna.NOMBRE),  # todo
    ],
)
def test_clasificacion_ignora_mayusculas_tildes_y_espacios(
    cabecera: str, rol_esperado: RolColumna
) -> None:
    """La cabecera puede llegar como llegue, el rol es el mismo."""
    tabla = pd.DataFrame(columns=[cabecera])
    assert clasificar_columnas(tabla) == {cabecera: rol_esperado}


# --- pruebas de comportamiento (no de import) --------------------------


def test_clasificacion_modulo_define_las_funciones_publicas() -> None:
    """El modulo ``dataclean.clasificacion`` define su contrato, no un reexport."""
    assert hasattr(clasificacion_modulo, "clasificar_columnas")
    assert hasattr(clasificacion_modulo, "RolColumna")
    # La funcion tiene que venir DEFINIDA aqui, no ser un alias.
    assert (
        clasificacion_modulo.clasificar_columnas.__module__
        == "dataclean.clasificacion"
    )


def test_normalizar_quita_tildes_y_espacios() -> None:
    """El helper de normalizacion colapsa tildes, mayusculas y espacios."""
    # Llamamos a la funcion interna para fijar el contrato del helper:
    # si alguien la borra, este test cae. Asi el helper no se queda
    # obsoleto sin que nadie se entere.
    assert clasificacion_modulo._normalizar("  TELÉFONO  ") == "telefono"
    assert clasificacion_modulo._normalizar("Correo Electrónico") == "correoelectronico"
    assert clasificacion_modulo._normalizar("NOMBRE   COMPLETO") == "nombrecompleto"


def test_tabla_sin_columnas_devuelve_diccionario_vacio() -> None:
    """Una tabla vacia no rompe: simplemente no hay nada que clasificar."""
    tabla = pd.DataFrame()
    assert clasificar_columnas(tabla) == {}


# --- test de camino real -------------------------------------------------
# Esto es la Regla 6 "fuerte": un test que NO pasaria con un
# ``clasificar_columnas`` de pega. Los tres pegas tipicos contra los
# que nos protegemos:
#   (a) Implementacion trivial que devuelve siempre ``{}``.
#   (b) Implementacion que ignora el orden de las columnas y devuelve
#       un dict vacio o con claves que no existen en la tabla.
#   (c) Implementacion que solo hace ``lower()`` y compara contra
#       ``{"telefono","correo","nombre"}`` sin quitar tildes, lo que
#       falla con ``TELEFONO`` o ``Correo electronico``.
# El test siguiente ejercita el camino real con datos de produccion y
# comprueba algo que solo una implementacion correcta (con la
# normalizacion del modulo) puede satisfacer: en una tabla CON FILAS
# (no solo con ``columns=``), el diccionario devuelto tiene una entrada
# por cada columna y los roles son los del enunciado del item, con las
# cinco cabeceras literales que el item DC.2 pone como ejemplo.


def test_camino_real_tabla_con_filas_y_cabeceras_del_enunciado() -> None:
    """Tabla con filas + las cinco cabeceras del item -> roles correctos.

    Es la prueba "de produccion" de DC.2: una tabla con datos (no solo
    la declaracion de columnas) entra en ``clasificar_columnas`` y
    sale un dict que un consumidor puede usar para, por ejemplo, pillar
    la columna telefono y normalizarla en DC.3.
    """
    tabla = pd.DataFrame(
        {
            "TELEFONO": ["3001234567", "3107654321", None],
            "Cel": ["3151112233", "3009998877", "3112223344"],
            "movil 2": ["", "3201234567", ""],
            "Correo electrónico": ["a@x.com", "b@x.com", "c@x.com"],
            "NOMBRE COMPLETO": ["Ana", "Jose", "Maria"],
            "ciudad_origen": ["Bogota", "Medellin", "Cali"],
        }
    )
    roles = clasificar_columnas(tabla)

    # Una entrada por cada columna: la implementacion trivial (a) y la
    # que ignora el orden (b) caen aqui. Tamano exacto: 6, ni mas ni
    # menos.
    assert len(roles) == 6
    assert set(roles) == set(tabla.columns)

    # Las cinco cabeceras del item DC.2, con mayusculas, tildes y
    # espacios tal cual las pone el enunciado: solo la normalizacion
    # completa (tilde + espacio) las lleva a un sinonimo. La pega (c)
    # no las reconoce todas. El orden de prioridad de telefono mete
    # las tres primeras en TELEFONO.
    assert roles["TELEFONO"] == RolColumna.TELEFONO
    assert roles["Cel"] == RolColumna.TELEFONO
    assert roles["movil 2"] == RolColumna.TELEFONO
    assert roles["Correo electrónico"] == RolColumna.CORREO
    assert roles["NOMBRE COMPLETO"] == RolColumna.NOMBRE

    # Y la columna "de la casa" (no la puso el item, no es sinonimo
    # de nada): se conserva y se marca como no clasificada, NO se
    # borra, NO se devuelve como otro rol.
    assert roles["ciudad_origen"] == RolColumna.NO_CLASIFICADA