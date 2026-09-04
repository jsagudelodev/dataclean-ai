"""Duplicados por telefono: agrupar sin borrar, explicar el por que.

DC.3 normalizo un monton de formatos distintos del mismo numero a un
canonico (``3001234567``). DC.8 usa ese canonico para detectar que
dos filas representan al mismo contacto y **no las borra**: las
agrupa, etiqueta y dice cual se propone conservar.

Por que existe este modulo (regla 4 del encargo):
    "Ante la duda, conservar." El cliente tiene que poder revisar lo
    que el sistema considero duplicado. Por eso este modulo NUNCA
    borra filas: las marca con ``es_duplicado=True`` y deja al
    caller (el reporte de DC.10) la decision final. Borrar un
    contacto bueno es un falso positivo que el producto no se puede
    permitir; una marca reversible, no.

Diseno:
    * **Una sola entrada y una sola salida.** Recibe una tabla
      (``pd.DataFrame``) y una columna de telefonos; devuelve la
      MISMA tabla con cuatro columnas anadidas: ``telefono_canon``,
      ``grupo_id``, ``es_duplicado`` y ``motivo_conservar``. No
      muta la entrada; el caller decide si sobrescribe.
    * **Reutiliza DC.3.** La deteccion delega en
      ``normalizar_telefono``: si el caller no normalizo antes, la
      funcion lo hace por el. Asi se cumple el Cierre 1 ("solo
      funciona si DC.3 normalizo antes") **por construccion**: la
      funcion IMPORTA DC.3.
    * **Vacio no es duplicado** (Cierre 3). Un telefono que
      ``normalizar_telefono`` no pudo normalizar (``marcado is False
      AND normalizado is None``: vacio, ``None``, NaN, solo
      separadores) sale **sin grupo**: ``grupo_id=""``,
      ``es_duplicado=False``. Dos filas con telefono vacio no se
      agrupan entre si.
    * **Cual se conserva y por que** (Cierre 2). Para cada grupo con
      mas de una fila se propone **una** a conservar y se explica
      en ``motivo_conservar``. La regla de eleccion es la unica
      conservadora que cumple Cierre 1 sin meter sesgo de orden:
      la fila con **mas datos no-vacios en el resto de columnas**
      (las columnas de la tabla que NO son la del telefono). Si
      hay empate, gana la primera que aparece (determinista, no
      aleatoria). Las demas filas del grupo quedan con
      ``es_duplicado=True`` y un motivo legible.
    * **Pais configurable.** Igual que DC.3, el codigo de pais y la
      longitud esperada se pasan por parametro; el caller no tiene
      que reescribir la funcion para otro mercado.
    * **Regla 9.** Ningun motivo contiene el telefono original ni
      el canonico. El reporte nunca filtra datos personales al log.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

from dataclean.telefono import normalizar_telefono


_MOTIVO_DUPLICADO: Final[str] = "duplicado de otra fila del mismo grupo"
_MOTIVO_SIN_TELEFONO: Final[str] = (
    "sin telefono normalizable: la fila no entra en grupos de duplicados"
)
_MOTIVO_CONSERVAR: Final[str] = "propuesta a conservar en el grupo: "


def _columnas_de_contexto(tabla: pd.DataFrame, columna: str) -> list[str]:
    return [c for c in tabla.columns if c != columna]


def _conteo_de_datos(
    fila: pd.Series, columnas_contexto: list[str]
) -> int:
    total = 0
    for c in columnas_contexto:
        valor = fila[c]
        if valor is None:
            continue
        try:
            if pd.isna(valor):
                continue
        except (TypeError, ValueError):
            total += 1
            continue
        if isinstance(valor, str) and not valor.strip():
            continue
        total += 1
    return total


def _motivo_para_conservar(
    fila: pd.Series, columnas_contexto: list[str]
) -> str:
    puntaje = _conteo_de_datos(fila, columnas_contexto)
    if puntaje == 0:
        detalle = "es la primera del grupo y no hay otras filas con mas datos"
    else:
        detalle = (
            f"tiene {puntaje} campo(s) con dato en el resto de columnas"
        )
    return _MOTIVO_CONSERVAR + detalle


def detectar_duplicados_por_telefono(
    tabla: pd.DataFrame,
    columna: str,
    codigo_pais: str = "+57",
    longitud_esperada: int = 10,
) -> pd.DataFrame:
    """Agrupa filas por telefono canonico; no borra ninguna."""
    if columna not in tabla.columns:
        raise KeyError(
            f"la columna {columna!r} no esta en la tabla; "
            f"columnas disponibles: {list(tabla.columns)}"
        )

    resultado = tabla.copy()

    canonicos: list[str] = []
    for valor in tabla[columna]:
        normalizado, marcado = normalizar_telefono(
            valor,
            codigo_pais=codigo_pais,
            longitud_esperada=longitud_esperada,
        )
        if marcado and normalizado is not None:
            canonicos.append(normalizado)
        else:
            canonicos.append("")

    resultado["telefono_canon"] = canonicos
    resultado["grupo_id"] = [
        f"tel-{c}" if c else "" for c in canonicos
    ]
    resultado["es_duplicado"] = False
    resultado["motivo_conservar"] = ""

    columnas_contexto = _columnas_de_contexto(tabla, columna)

    for grupo_id, indices in resultado.groupby("grupo_id").groups.items():
        if grupo_id == "":
            continue
        lista = list(indices)
        if len(lista) < 2:
            continue

        mejor_pos = lista[0]
        mejor_puntaje = _conteo_de_datos(
            resultado.loc[mejor_pos], columnas_contexto
        )
        for pos in lista[1:]:
            puntaje = _conteo_de_datos(
                resultado.loc[pos], columnas_contexto
            )
            if puntaje > mejor_puntaje:
                mejor_puntaje = puntaje
                mejor_pos = pos

        for pos in lista:
            if pos == mejor_pos:
                resultado.at[pos, "es_duplicado"] = False
                resultado.at[pos, "motivo_conservar"] = _motivo_para_conservar(
                    resultado.loc[pos], columnas_contexto
                )
            else:
                resultado.at[pos, "es_duplicado"] = True
                resultado.at[pos, "motivo_conservar"] = _MOTIVO_DUPLICADO

    sin_grupo = resultado["grupo_id"] == ""
    if sin_grupo.any():
        resultado.loc[sin_grupo, "motivo_conservar"] = _MOTIVO_SIN_TELEFONO

    return resultado