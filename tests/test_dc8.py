"""Cierre de DC.8: ``detectar_duplicados_por_telefono``.

Tres contratos del item:
  1) **Cierre 1** — dos filas con el mismo telefono en formatos
     distintos (los cuatro del enunciado de DC.3) se detectan como
     duplicadas. Esto SOLO funciona si DC.3 normalizo antes; por
     construccion, esta funcion IMPORTA DC.3.
  2) **Cierre 2** — no se borra ninguna fila: la funcion devuelve
     la tabla con cuatro columnas anadidas y ``es_duplicado=True``
     solo en las que son duplicadas de la propuesta a conservar.
     El motivo de conservar es legible y NO contiene el telefono
     (regla 9).
  3) **Cierre 3** — dos filas con el telefono vacio NO son
     duplicadas entre si: cada una sale con ``grupo_id=""`` y
     ``es_duplicado=False``.

Ademas:
  * La entrada NO se muta: la funcion devuelve una copia.
  * La eleccion de "a conservar" es determinista: la fila con
    mas datos en el resto de columnas; empate -> la primera.
"""

from __future__ import annotations

import importlib

import pandas as pd
import pytest

from dataclean import detectar_duplicados_por_telefono
# Importamos el modulo fuente directamente: si alguien borra
# ``duplicados.py`` pero deja el reexport de pega en ``__init__``,
# los tests de comportamiento (mas abajo) caen con ``ImportError``
# desde el modulo, no con un falso verde.
from dataclean import duplicados as duplicados_modulo


def _tabla_dos_filas_mismo_numero() -> pd.DataFrame:
    """Dos filas con el mismo telefono en formatos distintos.

    Los formatos son los cuatro del enunciado de DC.3: pelado, con
    espacios, con prefijo, con parentesis y guion.
    """
    return pd.DataFrame(
        {
            "nombre": ["Juan Perez", "Juan P."],
            "correo": ["a@x.com", "a@x.com"],
            "telefono": ["3001234567", "+57 300 1234567"],
        }
    )


# --- Cierre 1: dos formatos del mismo telefono -> mismo grupo ----------


def test_dos_formatos_distintos_mismo_numero_son_duplicados() -> None:
    """Las cuatro formas de DC.3 aplicadas al mismo numero caen al mismo grupo."""
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B", "C", "D"],
            "telefono": [
                "3001234567",
                "300 123 4567",
                "+57 300 1234567",
                "(300)123-4567",
            ],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    # Un solo grupo de telefono.
    grupos_con_dato = resultado.loc[
        resultado["grupo_id"] != "", "grupo_id"
    ].unique()
    assert len(grupos_con_dato) == 1
    assert grupos_con_dato[0] == "tel-3001234567"

    # Todas tienen el mismo canonico.
    assert (resultado["telefono_canon"] == "3001234567").all()

    # Tres son duplicadas; una es la propuesta a conservar.
    assert resultado["es_duplicado"].sum() == 3
    assert (~resultado["es_duplicado"]).sum() == 1


def test_cuatro_formatos_mas_una_intrusa_separan_dos_grupos() -> None:
    """Cuatro filas del mismo numero + una de otro -> 2 grupos (1 con 4, 1 con 1)."""
    tabla = pd.DataFrame(
        {
            "nombre": ["n1", "n2", "n3", "n4", "n5"],
            "telefono": [
                "3001234567",
                "300 123 4567",
                "+57 300 1234567",
                "(300)123-4567",
                "3112223333",
            ],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    # Dos grupos con dato + un unico grupo con unico elemento.
    conteo = resultado.groupby("grupo_id").size()
    assert conteo["tel-3001234567"] == 4
    assert conteo["tel-3112223333"] == 1

    # Las tres primeras son duplicadas del grupo grande.
    assert resultado.loc[0:3, "es_duplicado"].sum() == 3
    # La intrusa NO es duplicada (es unica en su grupo).
    # En el grupo grande, las cuatro filas empatan en datos de
    # contexto (todas tienen solo el telefono), asi que gana la
    # primera: la fila 0 es la propuesta a conservar.
    assert resultado["es_duplicado"].tolist() == [False, True, True, True, False]
    assert resultado.loc[4, "grupo_id"] == "tel-3112223333"


# --- Cierre 2: no se borra nada; se propone conservar y se explica -----


def test_no_se_borra_ninguna_fila() -> None:
    """La tabla sale con las mismas filas que entro (mas columnas)."""
    tabla = _tabla_dos_filas_mismo_numero()
    n_filas_original = len(tabla)
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    assert len(resultado) == n_filas_original
    # Las dos filas originales siguen ahi, con sus valores intactos.
    assert list(resultado["nombre"]) == ["Juan Perez", "Juan P."]
    assert list(resultado["correo"]) == ["a@x.com", "a@x.com"]
    # La entrada NO se muta.
    assert "es_duplicado" not in tabla.columns
    assert "grupo_id" not in tabla.columns


def test_propuesta_a_conservar_es_una_y_lleva_motivo() -> None:
    """En cada grupo, una sola fila es la propuesta a conservar; el resto, duplicado."""
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B", "C"],
            "correo": ["x@y.com", None, "x@y.com"],
            "telefono": ["3001234567", "300 123 4567", "(300)123-4567"],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    # La fila con correo (mas datos) es la propuesta a conservar.
    propuesta = resultado[~resultado["es_duplicado"]]
    assert len(propuesta) == 1
    assert propuesta.iloc[0]["nombre"] == "A"
    assert propuesta.iloc[0]["motivo_conservar"]  # no vacio

    # Las otras dos son duplicadas con motivo legible.
    duplicadas = resultado[resultado["es_duplicado"]]
    assert len(duplicadas) == 2
    assert (duplicadas["motivo_conservar"] != "").all()


def test_motivo_no_contiene_el_telefono_regla_9() -> None:
    """El motivo de conservar NO contiene el telefono canonico (regla 9).

    Si lo contuviera, el reporte filtraria un dato personal al log.
    """
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B"],
            "telefono": ["3001234567", "+57 300 1234567"],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")
    motivos = resultado["motivo_conservar"].tolist()
    # El canonico no aparece en ningun motivo.
    for motivo in motivos:
        assert "3001234567" not in motivo
    # Y los formatos originales tampoco.
    for motivo in motivos:
        assert "+57" not in motivo


def test_empate_gana_la_primera_que_aparece() -> None:
    """Si dos filas del grupo tienen los mismos datos, gana la primera (determinista)."""
    tabla = pd.DataFrame(
        {
            "nombre": ["primera", "segunda"],
            "telefono": ["3001234567", "300 123 4567"],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")
    propuesta = resultado[~resultado["es_duplicado"]]
    assert propuesta.iloc[0]["nombre"] == "primera"
    assert resultado["es_duplicado"].tolist() == [False, True]


# --- Cierre 3: vacio no es duplicado ------------------------------------


@pytest.mark.parametrize(
    "valor_vacio",
    [
        "",
        "   ",
        None,
    ],
)
def test_dos_filas_con_telefono_vacio_no_son_duplicadas(
    valor_vacio: object,
) -> None:
    """Dos filas con telefono vacio/None/espacios NO se agrupan (Cierre 3)."""
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B"],
            "telefono": [valor_vacio, valor_vacio],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    # Ninguna fila tiene grupo.
    assert (resultado["grupo_id"] == "").all()
    # Ninguna es duplicada.
    assert (~resultado["es_duplicado"]).all()
    # Y el motivo explica por que (regla del reporte: no inventar).
    assert (
        resultado["motivo_conservar"] != ""
    ).all()


def test_mezcla_vacios_y_reales_separa_correctamente() -> None:
    """Una fila vacia y dos del mismo numero: solo las dos reales se agrupan."""
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B", "C"],
            "telefono": ["3001234567", "+57 300 1234567", ""],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    # A y B en el mismo grupo; C sin grupo.
    assert resultado.loc[0, "grupo_id"] == "tel-3001234567"
    assert resultado.loc[1, "grupo_id"] == "tel-3001234567"
    assert resultado.loc[2, "grupo_id"] == ""

    # A y B: una propuesta a conservar, una duplicada.
    assert resultado.loc[0, "es_duplicado"] in (True, False)
    assert resultado.loc[1, "es_duplicado"] in (True, False)
    assert resultado.loc[0, "es_duplicado"] != resultado.loc[1, "es_duplicado"]
    # C: nunca duplicada.
    assert resultado["es_duplicado"].tolist() == [False, True, False]


# --- Tests de comportamiento (no de import) -----------------------------


def test_deteccion_delega_en_dc3_por_construccion() -> None:
    """La funcion IMPORTA ``normalizar_telefono`` de DC.3: sin DC.3, cae.

    Si alguien borra ``telefono.py`` o rompe la funcion de
    normalizacion, este test detecta el fallo por comportamiento:
    la normalizacion se hace por dentro, no por fuera.
    """
    import dataclean.duplicados as d

    # La funcion importa ``normalizar_telefono`` directamente.
    assert hasattr(d, "normalizar_telefono")
    # Y la usa (no es un reempaquetado opaco).
    tabla = pd.DataFrame(
        {"nombre": ["A", "B"], "telefono": ["abc", "abc"]}
    )
    # Si DC.3 no esta, todos los telefonos se marcan como no
    # normalizables y, por tanto, ninguna fila entra en grupo. Eso
    # es EXACTAMENTE lo que DC.3 dice: "letras -> no normalizable".
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")
    assert (resultado["grupo_id"] == "").all()


def test_camino_real_sin_reexport_logica_pura() -> None:
    """Test de camino real: importa ``duplicados`` por ``importlib`` dentro.

    Si alguien borra ``duplicados.py`` o lo reescribe con un
    ``return tabla`` pelado, este test detecta el fallo por
    comportamiento, no por import:

    * sin ``duplicados.py`` -> ``ImportError``;
    * con un ``return tabla`` -> 4 ``AssertionError`` sobre los
      Cierres 1, 2 y 3 (no se anade ninguna columna, ninguna fila
      queda como duplicada, dos vacias se "agrupan", etc.).
    """
    modulo = importlib.import_module("dataclean.duplicados")
    fn = modulo.detectar_duplicados_por_telefono

    # Cierre 1: dos formatos del mismo telefono -> mismo grupo.
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B"],
            "telefono": ["3001234567", "+57 300 1234567"],
        }
    )
    r = fn(tabla, "telefono")
    assert "grupo_id" in r.columns
    assert (r.loc[0, "grupo_id"] == r.loc[1, "grupo_id"] == "tel-3001234567")
    assert r["es_duplicado"].tolist() == [False, True]

    # Cierre 3: dos vacios NO se agrupan.
    tabla_vacia = pd.DataFrame(
        {"nombre": ["X", "Y"], "telefono": ["", ""]}
    )
    rv = fn(tabla_vacia, "telefono")
    assert (rv["grupo_id"] == "").all()
    assert all(not v for v in rv["es_duplicado"].tolist())


# --- Tests de camino real (Regla 6 fuerte sobre la logica) -------------
# Estos tests **no se satisfacen** con un ``return tabla`` pelado ni con
# un modulo vacio: verifican el comportamiento concreto de los Cierres
# 1, 2 y 3 sobre datos que SENTENCIAN una unica respuesta posible. Si
# alguien rompe la logica de ``detectar_duplicados_por_telefono`` (la
# borra, la sustituye por un ``return tabla``, le quita la importacion
# de DC.3, etc.), estos tests caen con ``AssertionError`` de
# comportamiento real, no con un ``ImportError`` de reexport.


def test_camino_real_c1_cuatro_formatos_caen_en_un_solo_grupo() -> None:
    """Cierre 1, camino real: las 4 formas de DC.3 en una sola tabla.

    Datos de produccion: 5 contactos donde 4 son el mismo numero
    escrito de 4 formas distintas. La UNICA respuesta correcta es:
    un solo grupo, con 4 filas, una propuesta a conservar y 3
    duplicadas. Si la logica de normalizacion se rompe (porque ya
    no se importa DC.3, o porque se hace un ``return tabla``),
    este test cae con ``KeyError: 'grupo_id'`` o con conteos de
    grupo incorrectos.
    """
    tabla = pd.DataFrame(
        {
            "nombre": [
                "Ana Lopez",
                "Ana L.",
                "Ana Lopez R",
                "Ana",
                "Pedro Gomez",
            ],
            "telefono": [
                "3001234567",
                "300 123 4567",
                "+57 300 1234567",
                "(300)123-4567",
                "3112223333",
            ],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    conteo = resultado.groupby("grupo_id").size()
    assert conteo["tel-3001234567"] == 4
    assert conteo["tel-3112223333"] == 1

    canonicos_grupo_grande = resultado.loc[
        resultado["grupo_id"] == "tel-3001234567", "telefono_canon"
    ].tolist()
    assert canonicos_grupo_grande == ["3001234567"] * 4

    duplicadas_grande = resultado.loc[
        resultado["grupo_id"] == "tel-3001234567", "es_duplicado"
    ].tolist()
    assert duplicadas_grande.count(False) == 1
    assert duplicadas_grande.count(True) == 3

    propuesta = resultado.loc[
        (resultado["grupo_id"] == "tel-3001234567")
        & (~resultado["es_duplicado"])
    ]
    assert propuesta.iloc[0]["nombre"] == "Ana Lopez"

    motivo = propuesta.iloc[0]["motivo_conservar"]
    assert motivo
    assert "3001234567" not in motivo
    assert "+57" not in motivo


def test_camino_real_c2_conservar_la_de_mas_datos_no_la_primera() -> None:
    """Cierre 2, camino real: se conserva la de MAS datos, no la primera.

    La regla de "conservar la primera" seria un falso positivo: si
    la primera fila esta vacia y la segunda tiene nombre + correo
    + cargo, la correcta es la segunda. Este test fija esa
    diferencia, que es exactamente el valor que DC.8 aporta.

    Datos: dos filas con el mismo telefono. La fila A (la primera)
    solo tiene el telefono. La fila B tiene nombre, correo y
    cargo. La UNICA respuesta correcta es: B es la propuesta a
    conservar, A es la duplicada.

    Un modulo con ``return tabla`` deja ambas filas con
    ``es_duplicado=False`` -> este test cae con ``AssertionError``.
    """
    tabla = pd.DataFrame(
        {
            "nombre": [None, "Beatriz Ramirez"],
            "correo": [None, "bety@empresa.com"],
            "cargo": [None, "GERENTE"],
            "telefono": ["3001234567", "300 123 4567"],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    assert resultado["grupo_id"].tolist() == ["tel-3001234567"] * 2

    assert bool(resultado.loc[0, "es_duplicado"]) is True
    assert bool(resultado.loc[1, "es_duplicado"]) is False

    motivo = resultado.loc[1, "motivo_conservar"]
    assert "3" in motivo
    assert "3001234567" not in motivo


def test_camino_real_c3_dos_vacios_y_dos_reales_separan_bien() -> None:
    """Cierre 3, camino real: vacios y reales conviven sin mezclarse.

    Un modulo con ``return tabla`` no anade la columna ``grupo_id``,
    asi que este test cae con ``KeyError``. Un modulo que pusiera
    ``grupo_id=""`` a todo fallaria al pedir el grupo de los
    reales.
    """
    tabla = pd.DataFrame(
        {
            "nombre": ["A", "B", "C", "D"],
            "telefono": [
                "3001234567",
                "+57 300 1234567",
                "",
                None,
            ],
        }
    )
    resultado = detectar_duplicados_por_telefono(tabla, "telefono")

    assert resultado.loc[0, "grupo_id"] == "tel-3001234567"
    assert resultado.loc[1, "grupo_id"] == "tel-3001234567"
    assert resultado.loc[2, "grupo_id"] == ""
    assert resultado.loc[3, "grupo_id"] == ""

    reales = resultado.loc[resultado["grupo_id"] == "tel-3001234567"]
    assert reales["es_duplicado"].tolist() == [False, True]
    vacios = resultado.loc[resultado["grupo_id"] == ""]
    assert all(not v for v in vacios["es_duplicado"].tolist())


# --- Guardas de la API -------------------------------------------------


def test_columna_inexistente_da_error_comprensible() -> None:
    """Si la columna no esta, falla con un motivo util (no con KeyError pelado)."""
    tabla = pd.DataFrame({"nombre": ["A"], "telefono": ["3001234567"]})
    with pytest.raises(KeyError) as exc:
        detectar_duplicados_por_telefono(tabla, "no_existe")
    # El mensaje nombra la columna que faltaba y lista las que hay.
    mensaje = str(exc.value)
    assert "no_existe" in mensaje
    assert "telefono" in mensaje
