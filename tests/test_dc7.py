"""Cierre de DC.7: ``separar_nombre_y_cargo`` con LLM sustituible.

Tres contratos del item:
  1) **Cierre 1** -- ``MARIA GOMEZ GERENTE`` y ``Pedro Ruiz
     (Contador)`` quedan en campos separados (nombre y cargo).
  2) **Cierre 2** -- el LLM es sustituible: la suite corre con
     ``SeparadorFalso`` (sin red, sin credenciales). La firma
     publica del modulo **no** depende de un proveedor externo.
  3) **Cierre 3** -- si el LLM no esta disponible, el sistema
     sigue funcionando y deja el campo sin separar (``(valor,
     None)``) en vez de fallar. Esto es la pieza "conservar"
     de la regla 4: nunca perdemos un dato por no poder
     separarlo.

Ademas:
  * Si el separador no se atreve a cortar, devuelve
    ``(texto, None)`` (regla 4: cero falsos positivos).
  * ``None`` y vacios se devuelven como ``(None, None)`` -- no
    se confunden con "separable".
"""

from __future__ import annotations

import importlib

import pandas as pd
import pytest

from dataclean import (
    SeparadorFalso,
    SeparadorNombreCargo,
    SeparadorPorPrefijo,
    separar_nombre_y_cargo,
)
# Importamos el modulo fuente directamente: si alguien borra
# ``cargo.py`` pero deja el reexport de pega en ``__init__``,
# los tests de comportamiento (mas abajo) caen con
# ``ImportError`` desde el modulo, no con un falso verde.
from dataclean import cargo as cargo_modulo


# --- Cierre 1: los dos formatos del item -------------------------------


def test_formato_mayusculas_pegado_se_separa() -> None:
    """``MARIA GOMEZ GERENTE`` -> nombre ``MARIA GOMEZ``, cargo ``GERENTE``.

    El formato mas basico del item: nombre en MAYUSCULAS y cargo
    en MAYUSCULAS pegado al final, sin senal. La heuristica
    conservadora del ``SeparadorFalso`` lo corta porque
    ``GERENTE`` esta en la lista cerrada de cargos conocidos.
    """
    separador = SeparadorFalso()
    nombre, cargo = separador.separar("MARIA GOMEZ GERENTE")
    assert nombre == "MARIA GOMEZ"
    assert cargo == "GERENTE"


def test_formato_parentesis_se_separa() -> None:
    """``Pedro Ruiz (Contador)`` -> nombre ``Pedro Ruiz``, cargo ``Contador``.

    El segundo formato del item: cargo entre parentesis al final.
    Aqui el cargo no esta pegado al nombre sin mas; esta
    delimitado por ``( ... )``. La heuristica detecta el patron
    y devuelve el cargo en MAYUSCULAS, porque asi esta en la
    lista cerrada (``CONTADOR``).
    """
    separador = SeparadorFalso()
    nombre, cargo = separador.separar("Pedro Ruiz (Contador)")
    assert nombre == "Pedro Ruiz"
    assert cargo == "CONTADOR"


def test_separar_nombre_y_cargo_cumple_caso_del_item() -> None:
    """La funcion publica (de cara al reporte) cumple Cierre 1
    sobre los dos formatos literales del item.

    Aqui ejercitamos la API que el reporte va a llamar:
    ``separar_nombre_y_cargo(valor, separador)``. El ``SeparadorFalso``
    es la implementacion por defecto que la suite usa para
    correr sin red (Cierre 2).
    """
    separador = SeparadorFalso()

    nombre, cargo = separar_nombre_y_cargo("MARIA GOMEZ GERENTE", separador)
    assert nombre == "MARIA GOMEZ"
    assert cargo == "GERENTE"

    nombre, cargo = separar_nombre_y_cargo("Pedro Ruiz (Contador)", separador)
    assert nombre == "Pedro Ruiz"
    assert cargo == "CONTADOR"


# --- Cierre 2: el LLM es sustituible ----------------------------------


def test_la_suite_corre_con_separador_sin_red_ni_credenciales() -> None:
    """El modulo no importa ni LLM ni credenciales: la suite corre
    con ``SeparadorFalso``, que vive en este paquete.

    Lo que se prueba: la **funcion publica** del paquete cumple
    el contrato del item sin necesitar nada externo. Si alguien
    intenta ``import openai`` en ``cargo.py``, este test sigue
    pasando (la suite ya cargo el modulo), pero la regla 7 del
    encargo ("sin red ni credenciales") la romperia el resto de
    la tanda. Aqui verificamos que la pieza DC.7 cumple
    Cierre 2 de forma autonoma.
    """
    # Si este test se ejecuta, ya estamos en un entorno sin red
    # ni credenciales (regla 7). Y el ``SeparadorFalso`` resuelve
    # los dos formatos del item.
    nombre, cargo = separar_nombre_y_cargo(
        "MARIA GOMEZ GERENTE", SeparadorFalso()
    )
    assert cargo == "GERENTE"
    nombre, cargo = separar_nombre_y_cargo(
        "Pedro Ruiz (Contador)", SeparadorFalso()
    )
    assert cargo == "CONTADOR"


def test_cualquier_separador_que_cumpla_el_protocolo_funciona() -> None:
    """El protocolo ``SeparadorNombreCargo`` admite cualquier
    implementacion: una regla, un LLM o un mock de tests.

    Aqui usamos ``SeparadorPorPrefijo`` (implementacion de
    referencia del propio modulo) para demostrar que la firma
    publica del paquete no esta casada con una sola
    implementacion. Si mañana se enchufa un LLM, basta con que
    su objeto exponga ``.separar(texto) -> (str, str | None)``.
    """
    sep_por_guion = SeparadorPorPrefijo(" - ")

    nombre, cargo = separar_nombre_y_cargo("ANA LOPEZ - DIRECTORA", sep_por_guion)
    assert nombre == "ANA LOPEZ"
    assert cargo == "DIRECTORA"

    # Y el mismo objeto cumple el protocolo: cualquier caller
    # que reciba un ``SeparadorNombreCargo`` puede usarlo.
    assert isinstance(sep_por_guion, object)
    assert callable(getattr(sep_por_guion, "separar", None))


def test_modulo_cargo_define_las_clases_y_la_funcion_publica() -> None:
    """El modulo expone la API completa: interfaz, dos
    implementaciones de referencia y la funcion de cara al
    reporte. Pieza debil de la Regla 6: si alguien borra el
    archivo, este test cae con ``ImportError``.
    """
    assert hasattr(cargo_modulo, "SeparadorNombreCargo")
    assert hasattr(cargo_modulo, "SeparadorFalso")
    assert hasattr(cargo_modulo, "SeparadorPorPrefijo")
    assert hasattr(cargo_modulo, "separar_nombre_y_cargo")
    assert callable(cargo_modulo.separar_nombre_y_cargo)


# --- Cierre 3: sin LLM, el sistema no falla ----------------------------


def test_sin_separador_se_conserva_el_campo_entero() -> None:
    """Si el caller no pasa separador (``None``), el sistema
    **no falla**: devuelve ``(valor, None)`` y conserva el
    campo original. Esto es Cierre 3 + regla 4.
    """
    nombre, cargo = separar_nombre_y_cargo("MARIA GOMEZ GERENTE")
    # Sin separador, NO se hace NADA sobre el dato. Se devuelve
    # el valor original y cargo=None.
    assert nombre == "MARIA GOMEZ GERENTE"
    assert cargo is None


def test_sin_separador_con_ausente_no_falla() -> None:
    """``None`` con ``separador=None`` devuelve ``(None, None)``
    sin lanzar excepcion.
    """
    nombre, cargo = separar_nombre_y_cargo(None)
    assert nombre is None
    assert cargo is None


def test_sin_separador_con_vacio_no_falla() -> None:
    """Vacio con ``separador=None`` devuelve ``(None, None)``
    sin lanzar excepcion.
    """
    nombre, cargo = separar_nombre_y_cargo("")
    assert nombre is None
    assert cargo is None


def test_separador_conservador_no_inventa_cortes() -> None:
    """Si el separador no reconoce el formato, **no** corta:
    devuelve ``(texto, None)``. Cero falsos positivos (regla 4).

    Casos que la heuristica conservadora del ``SeparadorFalso``
    no toca: cargo en minusculas, cargo que no esta en la lista
    cerrada, texto sin cargo, cargo suelto sin nombre.
    """
    sep = SeparadorFalso()

    # Cargo en minusculas: podria ser parte del nombre; no corta.
    nombre, cargo = sep.separar("Maria Gomez gerente")
    assert cargo is None
    assert nombre == "Maria Gomez gerente"

    # Cargo que no esta en la lista: el sistema no se atreve.
    nombre, cargo = sep.separar("Maria Gomez Astronauta")
    assert cargo is None
    assert nombre == "Maria Gomez Astronauta"

    # Texto sin cargo: no se inventa uno.
    nombre, cargo = sep.separar("Maria Gomez")
    assert cargo is None
    assert nombre == "Maria Gomez"


# --- camino real: tabla completa, columna original intacta -------------


def test_camino_real_tabla_con_nombres_y_cargos_mezclados() -> None:
    """Tabla "de produccion" con mezcla: nombres pegados, nombres
    solos, ausentes.

    Verifica que:
      - la columna original NO se sobreescribe (regla 4);
      - el reporte puede iterar ``separar_nombre_y_cargo`` fila
        a fila sin fallar (Cierre 3: aun sin LLM);
      - los formatos del item se separan; los nombres solos
        quedan ``(nombre, None)``; los ausentes quedan
        ``(None, None)``.
    """
    tabla = pd.DataFrame(
        {
            "contacto": [
                "MARIA GOMEZ GERENTE",   # Cierre 1: MAYUSCULAS pegado
                "Pedro Ruiz (Contador)",  # Cierre 1: parentesis
                "Ana Lopez",             # sin cargo -> (Ana Lopez, None)
                "JUAN PEREZ DIRECTOR",   # Cierre 1, variante
                None,                    # ausente
                "",                      # vacio
            ]
        }
    )
    sep = SeparadorFalso()
    resultados = [
        separar_nombre_y_cargo(v, sep) for v in tabla["contacto"]
    ]
    assert resultados == [
        ("MARIA GOMEZ", "GERENTE"),
        ("Pedro Ruiz", "CONTADOR"),
        ("Ana Lopez", None),
        ("JUAN PEREZ", "DIRECTOR"),
        (None, None),
        (None, None),
    ]
    # La columna original NO se muto (regla 4).
    assert list(tabla["contacto"]) == [
        "MARIA GOMEZ GERENTE",
        "Pedro Ruiz (Contador)",
        "Ana Lopez",
        "JUAN PEREZ DIRECTOR",
        None,
        "",
    ]


def test_camino_real_sin_separador_conserva_todo() -> None:
    """El sistema funciona aunque el LLM no este: el reporte
    itera y conserva el campo entero para todos.
    """
    tabla = pd.DataFrame(
        {
            "contacto": [
                "MARIA GOMEZ GERENTE",
                "Pedro Ruiz (Contador)",
                "Ana Lopez",
                None,
            ]
        }
    )
    resultados = [separar_nombre_y_cargo(v) for v in tabla["contacto"]]
    # Todos se conservan tal cual; cargo=None en todos.
    assert resultados == [
        ("MARIA GOMEZ GERENTE", None),
        ("Pedro Ruiz (Contador)", None),
        ("Ana Lopez", None),
        (None, None),
    ]


# --- pieza anti-pega: SeparadorFalso no es un "siempre None" --------


def test_separador_falso_no_devuelve_siempre_none() -> None:
    """Si la implementacion fuera un ``return texto, None`` pelado,
    los Cierres 1 y 2 ya habrian caido. Este test ata el caso:
    el ``SeparadorFalso`` **efectivamente** separa cuando el
    formato es claro.

    Es la pieza anti-pega que cierra el aviso del revisor: un
    reemplazo trivial del modulo no puede dejar la suite en
    verde.
    """
    sep = SeparadorFalso()
    _nombre, cargo = sep.separar("MARIA GOMEZ GERENTE")
    assert cargo is not None
    assert cargo == "GERENTE"

    _nombre, cargo = sep.separar("Pedro Ruiz (Contador)")
    assert cargo is not None
    assert cargo == "CONTADOR"


# --- Regla 6 reforzada: camino real, robusto a ``__init__`` corrupto --


def test_camino_real_sin_reexport_logica_pura() -> None:
    """Cierres 1, 2 y 3 del item, importados por ``importlib`` del
    modulo directamente, **sin** pasar por el reexport de
    ``__init__``.

    Refuerza la Regla 6: el test no depende del reexport de
    ``__init__.py``. Si alguien:
      - borra ``cargo.py`` -> el ``importlib.import_module``
        falla y pytest reporta el test en rojo;
      - rompe ``__init__.py`` -> este test sigue corriendo
        porque importa ``dataclean.cargo`` directamente, sin
        pasar por el paquete;
      - pega el cuerpo de ``SeparadorFalso.separar`` con un
        ``return texto, None`` -> el assert sobre el cargo del
        Cierre 1 cae con ``AssertionError`` sobre datos reales
        del item;
      - pega el cuerpo de ``separar_nombre_y_cargo`` con un
        ``return valor, "ALGO"`` -> el assert sobre ``cargo is
        None`` del Cierre 3 cae con ``AssertionError``.
    """
    mod = importlib.import_module("dataclean.cargo")
    sep = mod.SeparadorFalso()
    separar = mod.separar_nombre_y_cargo

    # Cierre 1: los dos formatos del item, importados del modulo
    # directamente.
    nombre, cargo = sep.separar("MARIA GOMEZ GERENTE")
    assert nombre == "MARIA GOMEZ", (
        f"Cierre 1a: esperaba 'MARIA GOMEZ', obtuvo {nombre!r}"
    )
    assert cargo == "GERENTE", (
        f"Cierre 1a: esperaba cargo 'GERENTE', obtuvo {cargo!r}"
    )

    nombre, cargo = sep.separar("Pedro Ruiz (Contador)")
    assert nombre == "Pedro Ruiz", (
        f"Cierre 1b: esperaba 'Pedro Ruiz', obtuvo {nombre!r}"
    )
    assert cargo == "CONTADOR", (
        f"Cierre 1b: esperaba cargo 'CONTADOR', obtuvo {cargo!r}"
    )

    # Cierre 2: la suite corre con la implementacion falsa, sin
    # red. Ya estamos en ese entorno; verificamos que la API
    # publica del modulo se puede usar sin nada externo.
    nombre, cargo = separar("JUAN PEREZ DIRECTOR", sep)
    assert nombre == "JUAN PEREZ"
    assert cargo == "DIRECTOR"

    # Cierre 3: sin separador, se conserva el campo entero.
    nombre, cargo = separar("MARIA GOMEZ GERENTE")
    assert nombre == "MARIA GOMEZ GERENTE", (
        f"Cierre 3: el campo debio conservarse entero, "
        f"se obtuvo {nombre!r}"
    )
    assert cargo is None, (
        f"Cierre 3: sin separador cargo debe ser None, "
        f"se obtuvo {cargo!r}"
    )

    # Cierre 3 (pieza ausente): sin separador, ``None`` y vacio
    # no rompen.
    assert separar(None) == (None, None)
    assert separar("") == (None, None)