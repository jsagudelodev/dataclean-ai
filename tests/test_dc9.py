"""Cierre de DC.9: ``detectar_duplicados_por_nombre``.

Tres contratos del item:
  1) **Cierre 1** -- ``juan perez`` y ``JUAN PEREZ`` caen al mismo
     grupo (DC.6 los normaliza al mismo canonico); ``Juan Pérez``
     y ``Juana Pérez`` NO caen al mismo grupo (canonicos
     distintos).
  2) **Cierre 2** -- el umbral de parecido es un parametro
     (``similitud_minima``); nada esta escrito en el codigo. Por
     defecto exige canonicos identicos (``1.0``).
  3) **Cierre 3** -- un grupo con dos canonicos distintos sale
     marcado como **sospechoso**, no confirmado. Ante la duda,
     conservar: la consolidacion la hace el cliente tras revisar.
"""

from __future__ import annotations

import importlib

import pandas as pd
import pytest

from dataclean import detectar_duplicados_por_nombre
from dataclean import duplicados as duplicados_modulo


def _ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


# --- Cierre 1.a: iguales al canonico -> mismo grupo --------------------


def test_juan_perez_y_juan_perez_caen_al_mismo_grupo() -> None:
    """``juan perez`` y ``JUAN PEREZ`` -> mismo grupo (Cierre 1.a).

    DC.6 colapsa ambas entradas al mismo canonico (``Juan Perez``,
    sin tilde porque ninguna entrada la trae). Grupo **confirmado**
    (``sospechoso=False``).
    """
    tabla = pd.DataFrame(
        {
            "nombre": ["juan perez", "JUAN PEREZ"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(tabla, "nombre")

    grupos = resultado.loc[
        resultado["grupo_id"] != "", "grupo_id"
    ].unique()
    assert len(grupos) == 1

    canonicos = resultado["nombre_nombre_canon"].tolist()
    assert canonicos[0] == canonicos[1]
    assert canonicos[0] == "Juan Perez"

    # Una es propuesta a conservar, la otra es duplicada.
    assert resultado["es_duplicado"].sum() == 1
    assert (~resultado["es_duplicado"]).sum() == 1

    # Grupo confirmado.
    assert (~resultado["sospechoso"]).all()


# --- Cierre 1.b: parecidos pero distintos -> NO agrupan ----------------


def test_juan_perez_y_juana_perez_no_caen_al_mismo_grupo() -> None:
    """``Juan Pérez`` y ``Juana Pérez`` -> grupos distintos (Cierre 1.b).

    Canonicos distintos; ratio ~0.95; con default 1.0 no agrupan.
    """
    tabla = pd.DataFrame(
        {
            "nombre": ["Juan Pérez", "Juana Pérez"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(tabla, "nombre")

    # Cada fila en su propio grupo, ninguna duplicada ni sospechosa.
    assert (resultado["es_duplicado"] == False).all()  # noqa: E712
    assert (resultado["sospechoso"] == False).all()  # noqa: E712

    grupos = resultado["grupo_id"].tolist()
    assert grupos[0] != ""
    assert grupos[1] != ""
    assert grupos[0] != grupos[1]

    # Anti-regresion: el ratio esta por debajo del default 1.0.
    canon_a = resultado.loc[0, "nombre_nombre_canon"]
    canon_b = resultado.loc[1, "nombre_nombre_canon"]
    assert _ratio(canon_a, canon_b) < 1.0


def test_umbral_por_defecto_separa_juan_y_juana() -> None:
    """El ratio del caso del item esta por debajo del default 1.0."""
    ratio = _ratio("Juan Pérez", "Juana Pérez")
    assert 0.9 < ratio < 1.0, (
        f"el ratio del caso del item cambio: ratio={ratio}"
    )


# --- Cierre 2: umbral configurable -------------------------------------


def test_umbral_1_exige_canonicos_identicos() -> None:
    """``similitud_minima=1.0`` exige canonicos IDENTICOS para agrupar."""
    tabla = pd.DataFrame(
        {
            "nombre": ["Juan Pérez", "Juana Pérez", "Pedro Gomez"],
            "correo": ["a@x.com", "b@x.com", "c@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(
        tabla, "nombre", similitud_minima=1.0
    )
    assert (resultado["es_duplicado"] == False).all()  # noqa: E712
    grupos = resultado["grupo_id"].tolist()
    assert grupos[0] != "" and grupos[1] != "" and grupos[2] != ""
    assert len({grupos[0], grupos[1], grupos[2]}) == 3


def test_umbral_bajo_agrupa_parecidos_distintos() -> None:
    """Un umbral bajo (0.5) agrupa ``Juan Pérez`` y ``Juana Pérez``."""
    tabla = pd.DataFrame(
        {
            "nombre": ["Juan Pérez", "Juana Pérez"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(
        tabla, "nombre", similitud_minima=0.5
    )
    grupos = resultado["grupo_id"].tolist()
    assert grupos[0] != ""
    assert grupos[0] == grupos[1]
    assert resultado["es_duplicado"].sum() == 1


def test_umbral_fuera_de_rango_rechaza() -> None:
    """Un umbral fuera de ``[0.0, 1.0]`` lanza ``ValueError``."""
    tabla = pd.DataFrame({"nombre": ["A", "B"]})
    with pytest.raises(ValueError):
        detectar_duplicados_por_nombre(tabla, "nombre", similitud_minima=1.5)
    with pytest.raises(ValueError):
        detectar_duplicados_por_nombre(tabla, "nombre", similitud_minima=-0.1)


# --- Cierre 3: sospechoso cuando los canonicos del grupo difieren ------


def test_umbral_bajo_crea_grupo_sospechoso_con_dos_canonicos() -> None:
    """Con umbral bajo, ``Juan Pérez`` y ``Juana Pérez`` -> grupo sospechoso.

    Dos canonicos distintos dentro del grupo => sospechoso=True
    (Cierre 3 explicito).
    """
    tabla = pd.DataFrame(
        {
            "nombre": ["Juan Pérez", "Juana Pérez"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(
        tabla, "nombre", similitud_minima=0.5
    )
    grupos = resultado["grupo_id"].tolist()
    assert grupos[0] == grupos[1]
    # Grupo sospechoso porque hay dos canonicos distintos.
    assert resultado["sospechoso"].all()
    assert resultado["es_duplicado"].sum() == 1
    motivo_dup = resultado.loc[
        resultado["es_duplicado"], "motivo_conservar"
    ].iloc[0]
    assert "parecido" in motivo_dup.lower()


# --- No mutacion y vacio -----------------------------------------------


def test_no_se_borra_ninguna_fila() -> None:
    tabla = pd.DataFrame(
        {
            "nombre": ["Juan Pérez", "JUAN PEREZ", "Juana Pérez"],
            "correo": ["a@x.com", "b@x.com", "c@x.com"],
        }
    )
    n_filas = len(tabla)
    resultado = detectar_duplicados_por_nombre(tabla, "nombre")

    assert len(resultado) == n_filas
    assert list(resultado["nombre"]) == list(tabla["nombre"])
    assert "grupo_id" not in tabla.columns
    assert "es_duplicado" not in tabla.columns


def test_motivos_no_contienen_el_nombre_regla_9() -> None:
    tabla = pd.DataFrame(
        {
            "nombre": ["juan perez", "JUAN PEREZ"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(tabla, "nombre")
    motivos = resultado["motivo_conservar"].tolist()
    for motivo in motivos:
        assert "juan" not in motivo.lower()
        assert "perez" not in motivo.lower()


@pytest.mark.parametrize(
    "valor_vacio",
    ["", "   ", None],
)
def test_nombre_vacio_no_entra_en_grupos(valor_vacio: object) -> None:
    tabla = pd.DataFrame(
        {
            "nombre": [valor_vacio, valor_vacio],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    resultado = detectar_duplicados_por_nombre(tabla, "nombre")
    assert (resultado["grupo_id"] == "").all()
    assert (resultado["es_duplicado"] == False).all()  # noqa: E712
    assert (resultado["sospechoso"] == False).all()  # noqa: E712


def test_columna_inexistente_lanza_key_error() -> None:
    tabla = pd.DataFrame({"nombre": ["A"]})
    with pytest.raises(KeyError):
        detectar_duplicados_por_nombre(tabla, "no_existe")


# --- Test de camino real (pieza reforzada tras el aviso de DC.5) -------


def test_camino_real_sin_reexport_logica_pura() -> None:
    """Test reforzado: importa el modulo FUENTE (no el reexport).

    Tres garantias:
      1) si alguien borra ``duplicados.py`` y deja el reexport de
         pega en ``__init__``, este test cae con ``ImportError``
         desde ``duplicados_modulo`` (no con un falso verde);
      2) si rompe el reexport en ``__init__``, este test sigue
         corriendo porque el modulo fuente sigue ahi;
      3) si pega una implementacion trivial (``return tabla``),
         las ``AssertionError`` de comportamiento real (Cierres 1,
         2 y 3) caen con datos del item.
    """
    importlib.reload(duplicados_modulo)
    assert hasattr(duplicados_modulo, "detectar_duplicados_por_nombre")
    fn = duplicados_modulo.detectar_duplicados_por_nombre

    # Cierre 1.a: canonico identico -> mismo grupo.
    tabla_iguales = pd.DataFrame(
        {
            "nombre": ["juan perez", "JUAN PEREZ"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    r_iguales = fn(tabla_iguales, "nombre")
    grupos_iguales = r_iguales.loc[
        r_iguales["grupo_id"] != "", "grupo_id"
    ].unique()
    assert len(grupos_iguales) == 1, (
        f"Cierre 1.a falla: {r_iguales['grupo_id'].tolist()}"
    )
    assert r_iguales["es_duplicado"].sum() == 1

    # Cierre 1.b: parecidos pero distintos -> NO agrupan (default).
    tabla_parecidos = pd.DataFrame(
        {
            "nombre": ["Juan Pérez", "Juana Pérez"],
            "correo": ["a@x.com", "b@x.com"],
        }
    )
    r_parecidos = fn(tabla_parecidos, "nombre")
    grupos_parecidos = r_parecidos["grupo_id"].tolist()
    assert grupos_parecidos[0] != "" and grupos_parecidos[1] != ""
    assert grupos_parecidos[0] != grupos_parecidos[1], (
        f"Cierre 1.b falla: {grupos_parecidos}"
    )

    # Cierre 2: el umbral es parametro (distinto resultado con 0.5).
    r_bajo = fn(tabla_parecidos, "nombre", similitud_minima=0.5)
    grupos_bajo = r_bajo["grupo_id"].tolist()
    assert grupos_bajo[0] == grupos_bajo[1], (
        f"Cierre 2 falla con umbral 0.5: {grupos_bajo}"
    )

    # Cierre 3: grupo con dos canonicos => sospechoso.
    assert r_bajo["sospechoso"].all(), (
        f"Cierre 3 falla: {r_bajo['sospechoso'].tolist()}"
    )


def test_modulo_duplicados_define_dc9() -> None:
    assert hasattr(duplicados_modulo, "detectar_duplicados_por_nombre")
    assert callable(duplicados_modulo.detectar_duplicados_por_nombre)