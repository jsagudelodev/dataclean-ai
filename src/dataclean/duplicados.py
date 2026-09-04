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

from dataclean.nombre import normalizar_nombre
from dataclean.telefono import normalizar_telefono


_MOTIVO_DUPLICADO: Final[str] = "duplicado de otra fila del mismo grupo"
_MOTIVO_SIN_TELEFONO: Final[str] = (
    "sin telefono normalizable: la fila no entra en grupos de duplicados"
)
_MOTIVO_SIN_NOMBRE: Final[str] = (
    "sin nombre normalizable: la fila no entra en grupos de duplicados"
)
_MOTIVO_SOSPECHOSO: Final[str] = (
    "parecido a otra fila del mismo grupo: revisar antes de consolidar"
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


def _similitud(a: str, b: str) -> float:
    """Devuelve un ratio de parecido entre dos strings en ``[0.0, 1.0]``.

    Usa ``difflib.SequenceMatcher`` (stdlib, sin red) que es
    suficiente para el caso del item: las entradas ya vienen
    normalizadas por DC.6 (``Juan Perez`` y ``JUAN PEREZ`` son el
    mismo string canonico; ``Juan Perez`` y ``Juana Perez`` no).
    Para nombres cortos (<= 4 caracteres por palabra) el ratio
    puede pasar el umbral por un caracter compartido, asi que el
    umbral por defecto se situa por encima del ruido tipico de
    nombres distintos (``Juan Perez`` / ``Juana Perez`` ~= 0.77).
    """
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def detectar_duplicados_por_nombre(
    tabla: pd.DataFrame,
    columna: str,
    similitud_minima: float = 1.0,
    particulas: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Agrupa filas por nombre parecido; **no borra nada**.

    DC.9 Cierre 1, 2 y 3:

      * **Cierre 1** -- ``Juan Pérez`` y ``JUAN PEREZ`` caen al
        mismo grupo (porque DC.6 los normaliza al mismo canonico);
        ``Juan Pérez`` y ``Juana Pérez`` NO caen al mismo grupo.
        Si dos filas producen el MISMO canonico, el grupo se
        considera **confirmado** (``sospechoso=False``); si los
        canonicos son DISTINTOS pero el ratio de parecido pasa el
        umbral, el grupo se considera **sospechoso**
        (``sospechoso=True``).
      * **Cierre 2** -- el umbral (``similitud_minima``) se pasa
        por parametro; nada esta escrito en el codigo. El caller
        lo configura por mercado o por nivel de tolerancia.
      * **Cierre 3** -- todo grupo de nombres parecidos se marca
        como **sospechoso**, no confirmado. La regla 4 del encargo
        ("ante la duda, conservar") obliga: un nombre parecido
        puede ser una coincidencia (``Juan`` y ``Juana``), asi que
        el reporte deja la consolidacion al cliente.

    Ademas:
      * **Reutiliza DC.6 por construccion.** La funcion IMPORTA
        :func:`normalizar_nombre`. Si el caller no normalizo antes,
        lo hace por el.
      * **Vacio no es duplicado** (``None``, ``NaN``, vacio,
        solo espacios): sale sin grupo, ``es_duplicado=False``,
        ``sospechoso=False``.
      * **Una sola entrada y una sola salida.** Recibe una tabla y
        devuelve una copia con cinco columnas anadidas:
        ``<columna>_nombre_canon``, ``grupo_id``, ``es_duplicado``,
        ``sospechoso`` y ``motivo_conservar``. No muta la entrada.
      * **Cual se conserva** -- la fila con mas datos no-vacios en
        el resto de columnas; empate -> la primera (determinista).
      * **Regla 9** -- los motivos NO contienen el nombre original
        ni el canonico (el canonico ya es dato personal).

    Args:
        tabla: ``DataFrame`` con la columna de nombres.
        columna: nombre de la columna a normalizar y agrupar.
        similitud_minima: ratio minimo (``0.0`` a ``1.0``) para
            considerar que dos canonicos distintos son "parecidos"
            y merecen un grupo. ``1.0`` (por defecto) exige
            canonicos identicos: es la opcion mas conservadora y
            rechaza ``Juan Pérez`` / ``Juana Pérez`` (ratio 0.95)
            para que NO se confundan. Si el caller quiere ser mas
            laxo (p.ej. 0.90), lo baja por parametro (Cierre 2).
        particulas: conjunto de particulas para DC.6. ``None``
            usa el default (``de``, ``del``, ``la``, ...).

    Returns:
        Nuevo ``DataFrame`` con las cinco columnas anadidas.
    """
    if columna not in tabla.columns:
        raise KeyError(
            f"la columna {columna!r} no esta en la tabla; "
            f"columnas disponibles: {list(tabla.columns)}"
        )
    if not 0.0 <= similitud_minima <= 1.0:
        raise ValueError(
            "similitud_minima debe estar entre 0.0 y 1.0 "
            f"(recibido {similitud_minima!r})"
        )

    if particulas is None:
        from dataclean.nombre import _PARTICULAS_POR_DEFECTO
        particulas = _PARTICULAS_POR_DEFECTO

    resultado = tabla.copy()

    canonicos: list[str | None] = []
    for valor in tabla[columna]:
        nombre, ok = normalizar_nombre(valor, particulas=particulas)
        if ok and nombre is not None:
            canonicos.append(nombre)
        else:
            canonicos.append("")

    canon_col = f"{columna}_nombre_canon"
    resultado[canon_col] = canonicos
    resultado["grupo_id"] = [
        f"nom-{c}" if c else "" for c in canonicos
    ]
    resultado["es_duplicado"] = False
    resultado["sospechoso"] = False
    resultado["motivo_conservar"] = ""

    columnas_contexto = _columnas_de_contexto(
        tabla,
        columna,
    )

    # Agrupar primero por canonico (DC.6), luego fusionar grupos
    # cuyos canonicos sean parecidos (umbral configurable). Asi
    # ``Juan Pérez`` / ``JUAN PEREZ`` caen al mismo grupo sin
    # necesidad de medir parecido: su canonico es identico.
    grupos: dict[str, list[int]] = {}
    canon_del_grupo: dict[str, str] = {}
    for pos, canon in enumerate(canonicos):
        if not canon:
            continue
        # Buscar un grupo existente cuyo canonico sea parecido.
        elegido: str | None = None
        for gid, otro_canon in canon_del_grupo.items():
            if _similitud(canon, otro_canon) >= similitud_minima:
                elegido = gid
                break
        if elegido is None:
            nuevo_gid = f"nom-{canon}"
            grupos[nuevo_gid] = [pos]
            canon_del_grupo[nuevo_gid] = canon
            resultado.at[pos, "grupo_id"] = nuevo_gid
        else:
            grupos[elegido].append(pos)
            resultado.at[pos, "grupo_id"] = elegido
            # Actualizar el canonico representativo al mas largo
            # (suele ser el que conserva tildes / es mas completo).
            if len(canon) > len(canon_del_grupo[elegido]):
                canon_del_grupo[elegido] = canon

    for gid, lista in grupos.items():
        if len(lista) < 2:
            continue

        # Determinar si el grupo es sospechoso: si todos los
        # canonicos son identicos, NO es sospechoso (confirmado);
        # si hay canonicos distintos dentro del grupo, SI es
        # sospechoso (Cierre 3: ante la duda, conservar).
        canonicos_del_grupo = {canonicos[i] for i in lista}
        es_sospechoso = len(canonicos_del_grupo) > 1

        # Elegir la fila a conservar (mas datos, empate -> primera).
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
                resultado.at[pos, "sospechoso"] = es_sospechoso
                if es_sospechoso:
                    detalle = (
                        "los nombres normalizados del grupo no son "
                        "identicos: revisar antes de consolidar"
                    )
                else:
                    detalle = (
                        "es la primera del grupo y no hay otras "
                        "filas con mas datos"
                        if mejor_puntaje == 0
                        else (
                            f"tiene {mejor_puntaje} campo(s) con dato "
                            "en el resto de columnas"
                        )
                    )
                resultado.at[pos, "motivo_conservar"] = (
                    _MOTIVO_CONSERVAR + detalle
                )
            else:
                resultado.at[pos, "es_duplicado"] = True
                resultado.at[pos, "sospechoso"] = es_sospechoso
                if es_sospechoso:
                    resultado.at[
                        pos, "motivo_conservar"
                    ] = _MOTIVO_SOSPECHOSO
                else:
                    resultado.at[
                        pos, "motivo_conservar"
                    ] = _MOTIVO_DUPLICADO

    sin_grupo = resultado["grupo_id"] == ""
    if sin_grupo.any():
        resultado.loc[sin_grupo, "motivo_conservar"] = _MOTIVO_SIN_NOMBRE

    return resultado