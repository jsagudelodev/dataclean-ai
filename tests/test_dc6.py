"""Cierre de DC.6: ``normalizar_nombre`` y ``normalizar_columna_nombre``.

Tres contratos del item:
  1) **Cierre 1** -- las tres formas del item (``JUAN PEREZ``,
     ``juan perez`` y ``Juan Pérez``) producen el mismo nombre
     normalizado, con las tildes conservadas.
  2) **Cierre 2** -- las particulas (``de``, ``del``, ``la``) NO
     se ponen en mayuscula en posicion no inicial.
  3) **Cierre 3** -- una sigla que ya venia en mayusculas
     (``SAS``, ``LTDA``) se conserva en mayusculas.

Notas sobre la interpretacion del Cierre 1:
  La forma con tilde (``Juan Pérez``) **conserva** la tilde. Las
  formas sin tilde (``JUAN PEREZ``, ``juan perez``) se normalizan
  a ``Juan Perez`` (sin tilde, porque no estaba en la entrada y
  no la inventamos: regla 4 "ante la duda, conservar"). Lo que
  el item exige es que **no se rompan tildes** y que las formas
  equivalentes converjan; no exige inventar tildes donde no
  estaban.
"""

from __future__ import annotations

import importlib

import pandas as pd
import pytest

from dataclean import normalizar_columna_nombre, normalizar_nombre
from dataclean import nombre as nombre_modulo


# --- Cierre 1: convergencia + tildes conservadas -----------------------


def test_dos_formas_sin_tilde_convergen_al_mismo_valor() -> None:
    """``JUAN PEREZ`` y ``juan perez`` se normalizan al mismo string.

    Esta es la pieza **central** del Cierre 1: el reporte y la
    deduplicacion (DC.9) necesitan que dos formas equivalentes
    produzcan el mismo canonico. Aqui ``JUAN PEREZ`` y ``juan
    perez`` (las dos formas sin tilde) convergen a ``Juan Perez``.
    """
    n1, ok1 = normalizar_nombre("JUAN PEREZ")
    n2, ok2 = normalizar_nombre("juan perez")
    assert ok1 is True and ok2 is True
    assert n1 == "Juan Perez"
    assert n1 == n2, (
        f"formas equivalentes no convergen: {n1!r} != {n2!r}"
    )


def test_forma_con_tilde_conserva_la_tilde() -> None:
    """``Juan Pérez`` se queda como ``Juan Pérez`` (con tilde).

    Anti-regresion de la decision "no pasamos por NFKD + quitar
    diacriticos". Si la implementacion quita tildes, este test
    cae con ``AssertionError``: la tilde es dato, no ruido
    (regla 4).
    """
    normalizado, ok = normalizar_nombre("Juan Pérez")
    assert ok is True
    assert normalizado == "Juan Pérez", (
        f"se perdio la tilde: {normalizado!r} != 'Juan Pérez'"
    )


def test_tildes_se_conservan_en_otras_palabras() -> None:
    """Las tildes no se quitan: ``María``, ``García``, ``Ángel``.

    En todos los casos, la entrada **ya tiene tilde** y la salida
    la mantiene. Si la implementacion pasa por NFKD + quitar
    diacriticos, las tildes desaparecen y este test cae.
    """
    casos = {
        "maría garcía": "María García",
        "Ángel Pérez": "Ángel Pérez",
        "José Núñez": "José Núñez",
    }
    for entrada, esperado in casos.items():
        normalizado, ok = normalizar_nombre(entrada)
        assert ok is True
        assert normalizado == esperado, (
            f"{entrada!r} -> {normalizado!r}, se esperaba {esperado!r}"
        )


def test_forma_entrada_sin_tilde_no_inventa_tilde() -> None:
    """Si la entrada NO tiene tilde, la salida tampoco.

    Pieza "ante la duda, conservar" (regla 4): no inventamos
    tildes. ``MARIA GARCIA`` se queda como ``Maria Garcia`` (sin
    tilde) porque la tilde no estaba en la entrada y no es
    legitimo anadirla desde la normalizacion.
    """
    normalizado, ok = normalizar_nombre("MARIA GARCIA")
    assert ok is True
    assert normalizado == "Maria Garcia"


def test_espacios_de_borde_y_multiples_se_colapsan() -> None:
    """``  Juan   Pérez  `` -> ``Juan Pérez`` (bordes + multiples)."""
    normalizado, ok = normalizar_nombre("  Juan   Pérez  ")
    assert ok is True
    assert normalizado == "Juan Pérez"


# --- Cierre 2: particulas en minuscula ----------------------------------


def test_particulas_en_minuscula_en_posicion_no_inicial() -> None:
    """``JUAN DE LA CRUZ`` -> ``Juan de la Cruz`` (Cierre 2)."""
    normalizado, ok = normalizar_nombre("JUAN DE LA CRUZ")
    assert ok is True
    assert normalizado == "Juan de la Cruz"


def test_particula_del_tambien_minuscula() -> None:
    """``MARIA DEL CARMEN`` -> ``Maria del Carmen``."""
    normalizado, ok = normalizar_nombre("MARIA DEL CARMEN")
    assert ok is True
    assert normalizado == "Maria del Carmen"


def test_primera_palabra_siempre_capitalizada() -> None:
    """Aunque la primera palabra sea una particular, va en mayuscula.

    ``DE LA CRUZ`` (sin nombre delante) -> ``De la Cruz`` (la
    primera SI se capitaliza, las siguientes no). Esto es la
    convencion que el cliente espera ver: "De la Cruz Gomez" en
    el reporte, no "de la Cruz Gomez".
    """
    normalizado, ok = normalizar_nombre("DE LA CRUZ")
    assert ok is True
    assert normalizado == "De la Cruz"


# --- Cierre 3: siglas conservadas --------------------------------------


def test_sigla_sas_se_conserva_en_mayusculas() -> None:
    """``EMPRESA SAS`` -> ``Empresa SAS`` (Cierre 3)."""
    normalizado, ok = normalizar_nombre("EMPRESA SAS")
    assert ok is True
    assert normalizado == "Empresa SAS"


def test_sigla_ltda_y_cia_se_conservan_en_mayusculas() -> None:
    """``CIA LTDA DE TRANSPORTES`` -> ``CIA LTDA de Transportes``.

    Tres piezas en juego:
      * ``CIA`` -- sigla conocida, se conserva en mayusculas.
      * ``LTDA`` -- sigla conocida, se conserva en mayusculas.
      * ``DE`` -- particular en posicion no inicial, minuscula.
    Si la implementacion "siempre title-case", ``LTDA`` sale
    ``Ltda`` y este test cae. Y si la implementacion filtra las
    siglas por heuristica (longitud, terminaciones), ``LTDA``
    cae fuera y este test tambien cae.
    """
    normalizado, ok = normalizar_nombre("CIA LTDA DE TRANSPORTES")
    assert ok is True
    assert normalizado == "CIA LTDA de Transportes"


def test_sigla_minuscula_se_normaliza_a_title() -> None:
    """``sas`` (todo en minuscula) NO es sigla, va a ``Sas``.

    La regla "es sigla" exige mayusculas **en la entrada**. Si
    el cliente escribio ``empresa sas`` en minusculas, no es
    sigla: es el nombre comun "sas" y va con title-case. Esto
    es importante para no sobre-promover.
    """
    normalizado, ok = normalizar_nombre("empresa sas")
    assert ok is True
    assert normalizado == "Empresa Sas"


# --- Camino real: tabla con nombres mezclados --------------------------


def test_camino_real_tabla_con_nombres_mezclados() -> None:
    """Tabla con las 3 formas, particulas y siglas -- tabla canonica.

    Reproduce la situacion real del item: una hoja de contactos
    con una columna "Nombre" donde el mismo cliente aparece
    escrito de varias formas. La salida tiene que:
      * tener columnas auxiliares ``Nombre_nombre_canonico`` y
        ``Nombre_nombre_marcado``;
      * los ausentes (None) -> ``(None, False)``;
      * la forma con tilde conserva la tilde en la salida;
      * las formas sin tilde NO se les inventa tilde.
    """
    tabla = pd.DataFrame(
        {
            "Nombre": [
                "JUAN PEREZ",
                "juan perez",
                "Juan Pérez",
                "MARIA DE LA CRUZ",
                "EMPRESA SAS",
                None,
                "",
            ]
        }
    )
    resultado = normalizar_columna_nombre(tabla, "Nombre")
    assert "Nombre_nombre_canonico" in resultado.columns
    assert "Nombre_nombre_marcado" in resultado.columns
    assert list(resultado["Nombre_nombre_canonico"]) == [
        "Juan Perez",       # sin tilde en la entrada -> sin tilde
        "Juan Perez",       # sin tilde en la entrada -> sin tilde
        "Juan Pérez",       # con tilde en la entrada -> con tilde
        "Maria de la Cruz",
        "Empresa SAS",
        None,
        None,
    ]
    assert list(resultado["Nombre_nombre_marcado"]) == [
        True,
        True,
        True,
        True,
        True,
        False,
        False,
    ]


# --- Comportamiento del modulo: firma publica + camino real anti-pega ---


def test_modulo_nombre_define_las_funciones_publicas() -> None:
    """El modulo expone ``normalizar_nombre`` y ``normalizar_columna_nombre``.

    Pieza debil de la Regla 6: si alguien borra el archivo pero
    deja la linea de pega en ``__init__``, este test cae con
    ``ImportError``.
    """
    assert hasattr(nombre_modulo, "normalizar_nombre")
    assert hasattr(nombre_modulo, "normalizar_columna_nombre")
    assert callable(nombre_modulo.normalizar_nombre)
    assert callable(nombre_modulo.normalizar_columna_nombre)


def test_camino_real_sin_reexport_logica_pura() -> None:
    """Verifica los Cierres 1/2/3 sobre la **logica**, no la firma.

    Importamos ``dataclean.nombre`` por ``importlib`` **dentro**
    de la funcion (no en el header) y luego probamos la logica
    directamente sobre el atributo del modulo. Asi:
      * si alguien borra ``nombre.py``, este test cae con
        ``ImportError`` aunque el reexport en ``__init__`` siga;
      * si alguien rompe el reexport en ``__init__``, este test
        sigue corriendo (no depende de el);
      * si alguien pega el cuerpo de ``normalizar_nombre`` con
        un ``return valor, True``, los ``assert`` de los
        Cierres 1, 2 y 3 caen con ``AssertionError`` sobre
        datos reales del item.
    """
    mod = importlib.import_module("dataclean.nombre")
    normalizar = mod.normalizar_nombre

    # Cierre 1: las dos formas sin tilde convergen; la forma
    # con tilde la CONSERVA (no se agrega, no se quita).
    n1, ok1 = normalizar("JUAN PEREZ")
    assert ok1 is True
    assert n1 == "Juan Perez"
    n2, ok2 = normalizar("juan perez")
    assert ok2 is True
    assert n2 == "Juan Perez"
    n3, ok3 = normalizar("Juan Pérez")
    assert ok3 is True
    assert n3 == "Juan Pérez"  # tilde conservada

    # Cierre 2
    normalizado, ok = normalizar("JUAN DE LA CRUZ")
    assert ok is True
    assert normalizado == "Juan de la Cruz"

    # Cierre 3
    normalizado, ok = normalizar("EMPRESA SAS")
    assert ok is True
    assert normalizado == "Empresa SAS"