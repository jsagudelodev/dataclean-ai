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


# Marcamos con un texto explicito cuando no se propuso conservar una
# fila porque es duplicada de otra. Asi el reporte puede filtrar sin
# ambiguedad.
_MOTIVO_DUPLICADO: Final[str] = "duplicado de otra fila del mismo grupo"

# Marcamos con un texto explicito cuando el telefono no se pudo
# normalizar y por tanto la fila no entra en ningun grupo de
# duplicados. NO contiene el telefono (regla 9).
_MOTIVO_SIN_TELEFONO: Final[str] = (
    "sin telefono normalizable: la fila no entra en grupos de duplicados"
)

# Marcamos con un texto explicito cuando la fila es la propuesta a
# conservar dentro de un grupo. ``detalle`` se rellena con la razon
# concreta (mas datos en otras columnas, etc.). Asi el reporte
# puede mostrar al cliente "estas dos son la misma; conserva esta
# por X".
_MOTIVO_CONSERVAR: Final[str] = "propuesta a conservar en el grupo: "


def _columnas_de_contexto(tabla: pd.DataFrame, columna: str) -> list[str]:
    """Devuelve las columnas de la tabla que NO son la del telefono.

    Se usan para puntuar que fila de un grupo de duplicados tiene
    mas informacion. Mantenemos el conjunto cerrado a las columnas
    que el cliente ya tenia: no anadimos columnas calculadas.
    """
    return [c for c in tabla.columns if c != columna]


def _conteo_de_datos(
    fila: pd.Series, columnas_contexto: list[str]
) -> int:
    """Cuenta cuantos campos de la fila (fuera del telefono) tienen dato.

    "Dato" significa: NO es ``None``, NO es ``NaN`` y NO es la cadena
    vacia tras ``str.strip``. Asi, una fila con nombre, correo y
    cargo puntua 3; una fila solo con telefono puntua 0.
    """
    total = 0
    for c in columnas_contexto:
        valor = fila[c]
        if valor is None:
            continue
        # ``isna`` cubre ``float('nan')`` y ``pd.NA``.
        try:
            if pd.isna(valor):
                continue
        except (TypeError, ValueError):
            # Por si un dtype raro rechaza ``isna``; tratamos como
            # dato y ya.
            total += 1
            continue
        if isinstance(valor, str) and not valor.strip():
            continue
        total += 1
    return total


def _motivo_para_conservar(
    fila: pd.Series, columnas_contexto: list[str]
) -> str:
    """Construye el motivo legible de por que esta fila se conserva.

    NO incluye el telefono (regla 9). Solo describe cuantos datos
    acompanan a la fila en el resto de columnas.
    """
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
    """Agrupa filas por telefono canonico; no borra ninguna.

    Devuelve una copia de ``tabla`` con cuatro columnas nuevas:

    * ``telefono_canon``: el canonico que DC.3 produjo (``str``) o
      la cadena vacia si no se pudo normalizar.
    * ``grupo_id``: identificador estable del grupo, formato
      ``"tel-<canonico>"``. Vacio para las filas sin telefono
      normalizable (asi dos vacias no se cuentan como duplicadas).
    * ``es_duplicado``: ``True`` si la fila pertece a un grupo de
      mas de una fila y NO es la propuesta a conservar; ``False``
      en otro caso (incluye "unica en su grupo" y "sin telefono").
    * ``motivo_conservar``: texto legible explicando la decision.
      Vacio para filas sin grupo. Para la propuesta a conservar,
      lleva el motivo de la eleccion. Para las duplicadas, lleva
      un texto generico que no expone el telefono (regla 9).

    Parametros:
        tabla: tabla de contactos. No se muta.
        columna: nombre de la columna con el telefono.
        codigo_pais: prefijo del mercado, igual que en DC.3.
        longitud_esperada: longitud del canonico, igual que en DC.3.
    """
    if columna not in tabla.columns:
        raise KeyError(
            f"la columna {columna!r} no esta en la tabla; "
            f"columnas disponibles: {list(tabla.columns)}"
        )

    resultado = tabla.copy()

    # 1) Normalizar TODOS los telefonos. Una sola pasada; DC.3 ya
    #    aplica la heuristica de "no se puede normalizar -> se
    #    conserva y se marca", que es justo lo que el Cierre 3
    #    necesita (vacio no es duplicado).
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
            # Marcado como no normalizable: vacio, None, NaN, letras,
            # longitud incorrecta, etc. Lo dejamos FUERA de cualquier
            # grupo (regla del Cierre 3: dos vacios no son duplicados).
            canonicos.append("")

    resultado["telefono_canon"] = canonicos
    resultado["grupo_id"] = [
        f"tel-{c}" if c else "" for c in canonicos
    ]
    # Por defecto: no es duplicado y sin motivo. Lo recalculamos abajo
    # solo para los grupos con mas de una fila.
    resultado["es_duplicado"] = False
    resultado["motivo_conservar"] = ""

    columnas_contexto = _columnas_de_contexto(tabla, columna)

    # 2) Recorrer los grupos de duplicados. Usamos ``groupby`` sobre
    #    el ``grupo_id`` ya calculado; los vacios tienen ``""`` y
    #    groupby los mete a todos juntos, asi que los filtramos
    #    explicitamente (un grupo "" con >1 fila NO es un grupo de
    #    duplicados: son N filas sin telefono).
    for grupo_id, indices in resultado.groupby("grupo_id").groups.items():
        if grupo_id == "":
            # Todas las filas sin telefono normalizable. Por
            # construcion ya tienen ``es_duplicado=False`` y motivo
            # vacio. El Cierre 3 exige que dos vacias NO sean
            # duplicadas: confirmado.
            continue
        # ``indices`` es un ``pd.Index`` con las posiciones de las
        # filas del grupo. Lo pasamos a lista para iterar.
        lista = list(indices)
        if len(lista) < 2:
            # Grupo de uno: no hay duplicado, lo dejamos como esta.
            continue

        # 3) Elegir la propuesta a conservar. Regla unica: la fila
        #    con mas datos en el resto de columnas; empate -> la
        #    primera que aparece en la tabla.
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

        # 4) Marcar. La propuesta a conservar lleva un motivo
        #    descriptivo; las demas quedan como ``es_duplicado=True``
        #    con un motivo generico que NO contiene el telefono
        #    (regla 9).
        for pos in lista:
            if pos == mejor_pos:
                resultado.at[pos, "es_duplicado"] = False
                resultado.at[pos, "motivo_conservar"] = _motivo_para_conservar(
                    resultado.loc[pos], columnas_contexto
                )
            else:
                resultado.at[pos, "es_duplicado"] = True
                resultado.at[pos, "motivo_conservar"] = _MOTIVO_DUPLICADO

    # Las filas sin grupo ya tienen ``motivo_conservar=""``. Anadimos
    # el motivo "sin telefono" para que el reporte pueda distinguir
    # "no es duplicado porque es unica" de "no es duplicado porque
    # no hay telefono". Asi el reporte es fiel a la realidad (regla
    # de DC.10: el reporte no inventa).
    sin_grupo = resultado["grupo_id"] == ""
    if sin_grupo.any():
        resultado.loc[sin_grupo, "motivo_conservar"] = _MOTIVO_SIN_TELEFONO

    return resultado