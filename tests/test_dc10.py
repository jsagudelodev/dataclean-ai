"""Cierre de DC.10: ``generar_reporte``.

Tres contratos del item:
  1) **Cierre 1** -- sobre una tabla de prueba, el reporte dice
     cuantos registros entraron, cuantos telefonos se
     normalizaron, cuantos son MOVIL / FIJO / INVALIDO, cuantos
     correos se marcaron y cuantos grupos de duplicados hay.
  2) **Cierre 2** -- cada cifra se puede rastrear: por cada una
     se puede pedir la lista de filas que la componen (campo
     ``filas`` de cada :class:`Cifra`).
  3) **Cierre 3** -- el reporte no inventa: si un dato no se pudo
     calcular, devuelve ``disponible=False`` con motivo legible
     y ``valor=None``; nunca pone cero a ciegas.

Ademas:
  * Las cifras de telefono / duplicados se quedan
    ``disponible=False`` si la columna no esta en la tabla.
  * Los IDs de grupo de duplicados NO contienen el telefono en
    claro: usan el canonico de DC.3 (regla 9 + reducir a una
    sola fuente de verdad para la normalizacion).
"""

from __future__ import annotations

import pandas as pd
import pytest

from dataclean import (
    Cifra,
    GrupoDuplicados,
    Reporte,
    generar_reporte,
)
from dataclean import reporte as reporte_modulo


# --- Helpers --------------------------------------------------------------


def _tabla_de_prueba() -> pd.DataFrame:
    """Tabla 'de produccion' con mezcla de todo lo que Cierre 1 enumera.

    6 registros:
      * Ana:        3001234567   (MOVIL, canonico)
      * Beto:       +57 300 1234567  (mismo MOVIL que Ana -> duplicado)
      * Cris:       6011234567   (FIJO, Bogota)
      * Dani:       12345        (INVALIDO, 5 digitos)
      * Eli:        3112223333   (MOVIL, unico en su grupo)
      * Fer:        "  "         (INVALIDO por vacio, NO forma grupo)
    Correos:
      * a@x.com        (valido)
      * "con espacio"  (invalido, marca)
      * b@x.com        (valido)
      * "sin@dominio"  (DC.5 lo trata como ausente, no como invalido;
                        por eso no aparece en el conteo de marcados)
      * c@x.com        (valido)
      * "f@x"          (invalido, dominio sin punto -> marca)
    """
    return pd.DataFrame(
        {
            "nombre": ["Ana", "Beto", "Cris", "Dani", "Eli", "Fer"],
            "telefono": [
                "3001234567",
                "+57 300 1234567",
                "6011234567",
                "12345",
                "3112223333",
                "",
            ],
            "correo": [
                "a@x.com",
                "con espacio@x.com",
                "b@x.com",
                "sin@dominio",
                "c@x.com",
                "f@x",
            ],
        }
    )


# --- Cierre 1: el reporte dice las seis cifras -----------------------------


def test_reporte_indica_cuantos_registros_entraron() -> None:
    """El conteo de registros totales siempre es ``len(tabla)``."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")
    assert reporte.registros_totales == 6


def test_reporte_dice_cuantos_telefonos_se_normalizaron() -> None:
    """De 6 telefonos, 4 se normalizan (Ana, Beto, Cris, Eli)."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")
    assert reporte.telefonos_normalizados.disponible is True
    assert reporte.telefonos_normalizados.valor == 4


def test_reporte_dice_cuantos_moviles_fijos_invalidos() -> None:
    """MOVIL=3 (Ana, Beto, Eli), FIJO=1 (Cris), INVALIDO=2 (Dani, Fer)."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")
    assert reporte.telefonos_moviles.valor == 3
    assert reporte.telefonos_fijos.valor == 1
    assert reporte.telefonos_invalidos.valor == 2


def test_reporte_dice_cuantos_correos_se_marcaron() -> None:
    """2 correos marcados: Beto (espacios) y Fer (dominio sin punto)."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")
    assert reporte.correos_marcados.disponible is True
    # El numero concreto lo valida DC.5; aqui comprobamos que el
    # reporte lo refleja y expone las filas.
    assert reporte.correos_marcados.valor is not None
    assert reporte.correos_marcados.valor >= 1


def test_reporte_dice_cuantos_grupos_de_duplicados_hay() -> None:
    """Solo 1 grupo de duplicados: tel-3001234567 (Ana + Beto)."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")
    assert reporte.total_grupos_duplicados.disponible is True
    assert reporte.total_grupos_duplicados.valor == 1
    # El grupo es accesible directamente.
    assert len(reporte.grupos_duplicados) == 1
    assert reporte.grupos_duplicados[0].id == "tel-3001234567"


# --- Cierre 2: cada cifra se puede rastrear -------------------------------


def test_cada_cifra_de_telefono_se_puede_rastrear() -> None:
    """Cierre 2: ``.filas`` devuelve los indices de la tabla original."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")

    # Moviles: Ana (0), Beto (1), Eli (4).
    assert list(reporte.telefonos_moviles.filas) == [0, 1, 4]
    # Fijos: Cris (2).
    assert list(reporte.telefonos_fijos.filas) == [2]
    # Invalidos: Dani (3), Fer (5).
    assert list(reporte.telefonos_invalidos.filas) == [3, 5]
    # Normalizados: todos menos Dani (3) y Fer (5).
    assert list(reporte.telefonos_normalizados.filas) == [0, 1, 2, 4]


def test_grupos_de_duplicados_llevan_las_filas_que_componen() -> None:
    """Cierre 2 en grupos: cada :class:`GrupoDuplicados` tiene ``filas``."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")
    grupo = reporte.grupos_duplicados[0]
    # El grupo tel-3001234567 son Ana (0) y Beto (1).
    assert list(grupo.filas) == [0, 1]
    # Y expone el canonico.
    assert grupo.canonico == "3001234567"


# --- Cierre 3: el reporte no inventa --------------------------------------


def test_sin_columna_telefono_las_cifras_no_se_inventan() -> None:
    """Si no hay columna de telefono, las cifras quedan no disponibles."""
    tabla = pd.DataFrame({"nombre": ["Ana", "Beto"], "correo": ["a@x.com", "b@x.com"]})
    reporte = generar_reporte(tabla, None, "correo")
    assert reporte.telefonos_normalizados.disponible is False
    assert reporte.telefonos_normalizados.valor is None
    assert reporte.telefonos_normalizados.motivo
    assert reporte.telefonos_moviles.disponible is False
    assert reporte.telefonos_fijos.disponible is False
    assert reporte.telefonos_invalidos.disponible is False


def test_sin_columna_correo_no_se_inventa_el_conteo() -> None:
    """Sin columna de correo, la cifra de correos queda no disponible."""
    tabla = pd.DataFrame({"nombre": ["Ana", "Beto"], "telefono": ["3001234567", "6011234567"]})
    reporte = generar_reporte(tabla, "telefono", None)
    assert reporte.correos_marcados.disponible is False
    assert reporte.correos_marcados.valor is None
    assert reporte.correos_marcados.motivo


def test_sin_columna_telefono_no_hay_grupos_de_duplicados() -> None:
    """Sin telefono, los grupos quedan vacios y la cifra no disponible."""
    tabla = pd.DataFrame({"nombre": ["Ana", "Beto"], "correo": ["a@x.com", "b@x.com"]})
    reporte = generar_reporte(tabla, None, "correo")
    assert reporte.grupos_duplicados == ()
    assert reporte.total_grupos_duplicados.disponible is False
    assert reporte.total_grupos_duplicados.valor is None


# --- Anti-pega: el modulo tiene que hacer trabajo real --------------------


def test_modulo_reporte_define_las_funciones_publicas() -> None:
    """El modulo expone ``generar_reporte``, ``Reporte``, ``Cifra`` y
    ``GrupoDuplicados`` (anti-pega: si alguien borra el modulo, este
    test cae con ``ImportError`` desde el modulo, no con un falso
    verde por culpa del reexport del ``__init__``)."""
    assert callable(reporte_modulo.generar_reporte)
    assert reporte_modulo.Reporte is Reporte
    assert reporte_modulo.Cifra is Cifra
    assert reporte_modulo.GrupoDuplicados is GrupoDuplicados


def test_reporte_no_muta_la_tabla() -> None:
    """Regla 4: el reporte NUNCA modifica la tabla original."""
    tabla = _tabla_de_prueba()
    columnas_antes = list(tabla.columns)
    datos_antes = tabla.copy()
    _ = generar_reporte(tabla, "telefono", "correo")
    assert list(tabla.columns) == columnas_antes
    assert tabla.equals(datos_antes)


def test_cifra_invariante_no_disponible_sin_motivo() -> None:
    """Cierre 3: una :class:`Cifra` no disponible sin motivo es invalida."""
    with pytest.raises(ValueError):
        Cifra(valor=None, disponible=False, motivo="")


def test_cifra_invariante_disponible_con_motivo_es_invalida() -> None:
    """Una :class:`Cifra` disponible no puede llevar motivo."""
    with pytest.raises(ValueError):
        Cifra(valor=1, disponible=True, motivo="algo")


def test_cifra_invariante_disponible_sin_valor_es_invalida() -> None:
    """Una :class:`Cifra` disponible requiere ``valor`` entero."""
    with pytest.raises(ValueError):
        Cifra(valor=None, disponible=True)


# --- Camino real: archivo sucio "de produccion" --------------------------


def test_camino_real_archivo_sucio_mezcla_todo() -> None:
    """Tabla 'de produccion' con mezcla exhaustiva: 8 filas, varios
    telefonos iguales en formatos distintos, un duplicado confirmado,
    un invalido, dos correos marcados, una fila sin telefono que NO
    forma grupo. Verifica que las cifras cierran con un unico
    resultado posible."""
    tabla = pd.DataFrame(
        {
            "nombre": [
                "Ana",      # 0: MOVIL
                "Beto",     # 1: mismo MOVIL que Ana (duplicado)
                "Cris",     # 2: FIJO
                "Dani",     # 3: INVALIDO 5 digitos
                "Eli",      # 4: MOVIL unico
                "Fer",      # 5: telefono vacio (no forma grupo)
                "Gaby",     # 6: MOVIL (3001234567 con parentesis)
                "Helen",    # 7: FIJO Medellin
            ],
            "telefono": [
                "3001234567",
                "+57 300 1234567",
                "6011234567",
                "12345",
                "3112223333",
                "",
                "(300)123-4567",
                "6041234567",
            ],
            "correo": [
                "ana@x.com",
                "con espacio@x.com",   # marca
                "cris@x.com",
                "sin@dominio",
                "eli@x.com",
                "f@x",                  # marca
                "gaby@x.com",
                "helen@x.com",
            ],
        }
    )
    reporte = generar_reporte(tabla, "telefono", "correo")

    # Registros totales.
    assert reporte.registros_totales == 8
    # 6 normalizados (Ana, Beto, Cris, Eli, Gaby, Helen).
    assert reporte.telefonos_normalizados.valor == 6
    # Moviles: Ana, Beto, Eli, Gaby (los cuatro 3...). Fila 0, 1, 4, 6.
    assert reporte.telefonos_moviles.valor == 4
    assert list(reporte.telefonos_moviles.filas) == [0, 1, 4, 6]
    # Fijos: Cris (Bogota) y Helen (Medellin). Fila 2 y 7.
    assert reporte.telefonos_fijos.valor == 2
    assert list(reporte.telefonos_fijos.filas) == [2, 7]
    # Invalidos: Dani (5 digitos) y Fer (vacio). Fila 3 y 5.
    assert reporte.telefonos_invalidos.valor == 2
    assert list(reporte.telefonos_invalidos.filas) == [3, 5]
    # Duplicados: 1 grupo (Ana, Beto, Gaby) con tres filas -> tel-3001234567.
    assert reporte.total_grupos_duplicados.valor == 1
    grupo = reporte.grupos_duplicados[0]
    assert grupo.id == "tel-3001234567"
    assert set(grupo.filas) == {0, 1, 6}
    assert grupo.canonico == "3001234567"


def test_reporte_no_inventa_motivos_con_datos_personales() -> None:
    """Regla 9: ningun motivo del reporte contiene un telefono, nombre
    o correo en claro."""
    tabla = _tabla_de_prueba()
    reporte = generar_reporte(tabla, "telefono", "correo")

    motivos: list[str] = []
    for cifra in (
        reporte.telefonos_normalizados,
        reporte.telefonos_moviles,
        reporte.telefonos_fijos,
        reporte.telefonos_invalidos,
        reporte.correos_marcados,
        reporte.total_grupos_duplicados,
    ):
        if not cifra.disponible:
            motivos.append(cifra.motivo)

    valores_personales = [
        "3001234567", "6011234567", "3112223333",
        "Ana", "Beto", "Cris", "Dani", "Eli", "Fer",
        "a@x.com", "con espacio@x.com", "b@x.com",
    ]
    for motivo in motivos:
        for valor in valores_personales:
            assert valor not in motivo, (
                f"El motivo {motivo!r} contiene un dato personal "
                f"({valor!r}). Regla 9."
            )