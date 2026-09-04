"""Reporte de limpieza: lo que se vende.

Por que existe este modulo (regla 1 del ENCARGO):
    "Lo que se vende no es el archivo limpio: es el reporte." El
    cliente quiere ver en cinco segundos el desorden de su hoja de
    contactos cuantificado: cuantos telefonos son moviles, cuantos
    fijos, cuantos correos dudosos, cuantos duplicados. Este modulo
    NO modifica la tabla: solo **cuenta** sobre una tabla que el
    caller ya paso por las normalizaciones de los items anteriores
    (si quiso). Si una cifra no se puede calcular, lo dice con un
    motivo legible y un booleano ``disponible=False`` (Cierre 3:
    "el reporte no inventa").

Tres contratos del item (Cierres):
    1) **Cierre 1** -- el reporte dice cuantos registros entraron,
       cuantos telefonos se normalizaron, cuantos son
       MOVIL / FIJO / INVALIDO, cuantos correos se marcaron y
       cuantos grupos de duplicados hay.
    2) **Cierre 2** -- cada cifra se puede rastrear: por cada una se
       puede pedir la lista de filas que la componen (campo
       ``filas`` de cada :class:`Cifra`).
    3) **Cierre 3** -- el reporte no inventa: si un dato no se pudo
       calcular (``valor=None``, ``disponible=False``), dice que no
       se pudo y por que; nunca pone cero a ciegas.

Diseno:
    * Cada cifra es un :class:`Cifra` con ``valor`` opcional,
      ``disponible`` (bool) y ``motivo`` legible. Si la columna
      pedida no existe en la tabla, ``valor=None``,
      ``disponible=False``, ``motivo="la columna no esta en la
      tabla"``. Asi, el reporte distingue "hay 0 moviles" (dato
      real) de "no pude saber cuantos moviles hay" (dato
      desconocido).
    * **No muta la tabla.** El reporte solo lee. Si el caller
      quiere conteos sobre filas auxiliares (``telefono_normalizado``,
      ``telefono_tipo``, ``grupo_id``), las pasa; el reporte
      **no** aplica las transformaciones de DC.3/4/5/8 por su
      cuenta -- las recomputa en sitio si faltan, pero solo como
      fallback. Asi DC.10 no se acopla con los items previos.
    * **Regla 9.** Ningun motivo contiene un telefono, un nombre ni
      un correo en claro. Solo la categoria del problema
      ("la columna no esta en la tabla", "el dato no se pudo
      normalizar"). Los IDs de grupo (``tel-3001234567``) tampoco
      contienen el telefono original: usan el canonico de DC.3.

Justificacion del diseno (la apunto en la bitacora):
    Una sola clase :class:`Cifra` para todas las metricas en vez de
    cinco clases distintas. Razon: el item pide que CADA cifra se
    pueda rastrear y que CADA cifra diga si se pudo calcular. Si
    fueran clases distintas, el caller tendria que aprender cinco
    APIs; con una sola clase, ``reporte.telefonos_moviles.filas``
    funciona siempre igual y el reporte es trivial de serializar a
    JSON para el endpoint de DC.13.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from dataclean.correo import validar_correo
from dataclean.telefono import (
    TIPO_FIJO,
    TIPO_INVALIDO,
    TIPO_MOVIL,
    clasificar_columna_telefono,
    normalizar_columna_telefono,
)


# Motivos legibles que **no** contienen datos personales (regla 9).
_MOTIVO_SIN_COLUMNA_TELEFONO: Final[str] = (
    "la columna de telefono no esta en la tabla"
)
_MOTIVO_SIN_COLUMNA_CORREO: Final[str] = (
    "la columna de correo no esta en la tabla"
)


# ---------------------------------------------------------------------------
# Tipos publicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cifra:
    """Una cifra del reporte: cuenta, motivo y rastreo.

    Atributos:
        valor: el numero entero que reporta la metrica. ``None``
            cuando no se pudo calcular.
        disponible: ``True`` si el reporte tiene un dato real.
        motivo: explicacion legible de por que la cifra no esta
            disponible. Vacio cuando ``disponible=True``. **No**
            contiene telefonos, correos ni nombres (regla 9).
        filas: indices de la tabla original que componen esta
            cifra (Cierre 2).
    """

    valor: int | None
    disponible: bool
    motivo: str = ""
    filas: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.disponible:
            if self.valor is None:
                raise ValueError("Cifra disponible requiere valor entero.")
            if self.valor < 0:
                raise ValueError(
                    f"Cifra disponible no admite valor negativo: {self.valor}."
                )
            if self.motivo:
                raise ValueError("Cifra disponible no admite motivo no vacio.")
        else:
            if self.valor is not None:
                raise ValueError("Cifra no disponible debe tener valor=None.")
            if not self.motivo:
                raise ValueError("Cifra no disponible requiere motivo legible.")


@dataclass(frozen=True)
class GrupoDuplicados:
    """Un grupo de duplicados por telefono."""

    id: str
    filas: tuple[int, ...]
    canonico: str


@dataclass(frozen=True)
class Reporte:
    """El reporte que el producto vende."""

    registros_totales: int
    telefonos_normalizados: Cifra
    telefonos_moviles: Cifra
    telefonos_fijos: Cifra
    telefonos_invalidos: Cifra
    correos_marcados: Cifra
    grupos_duplicados: tuple[GrupoDuplicados, ...]
    total_grupos_duplicados: Cifra


# ---------------------------------------------------------------------------
# Implementacion
# ---------------------------------------------------------------------------


def _cifra_disponible(filas: list[int]) -> Cifra:
    return Cifra(
        valor=len(filas),
        disponible=True,
        motivo="",
        filas=tuple(filas),
    )


def _cifra_no_disponible(motivo: str) -> Cifra:
    return Cifra(
        valor=None,
        disponible=False,
        motivo=motivo,
        filas=(),
    )


def _es_valor_no_vacio(valor: object) -> bool:
    if valor is None:
        return False
    try:
        if pd.isna(valor):
            return False
    except (TypeError, ValueError):
        return True
    if isinstance(valor, str):
        return bool(valor.strip())
    return True


def _indices_con_predicado(serie: pd.Series, predicado: object) -> list[int]:
    return [i for i, valor in enumerate(serie) if predicado(valor)]


def _calcular_telefonos(
    tabla: pd.DataFrame,
    columna_telefono: str,
) -> tuple[Cifra, Cifra, Cifra, Cifra]:
    """Calcula normalizados / moviles / fijos / invalidos.

    Politica de fallback: el reporte **no** exige que el caller
    haya pasado antes por DC.3/DC.4. Si las columnas auxiliares
    (``telefono_normalizado`` / ``telefono_tipo``) estan, las usa.
    Si no, las recomputa via ``normalizar_columna_telefono`` y
    ``clasificar_columna_telefono`` (DC.3/DC.4).
    """
    if columna_telefono not in tabla.columns:
        motivo = _MOTIVO_SIN_COLUMNA_TELEFONO
        return (
            _cifra_no_disponible(motivo),
            _cifra_no_disponible(motivo),
            _cifra_no_disponible(motivo),
            _cifra_no_disponible(motivo),
        )

    # Canonicos: DC.3 crea ``telefono_normalizado`` y ``telefono_marcado``.
    auxiliar_canon = f"{columna_telefono}_normalizado"
    if auxiliar_canon in tabla.columns:
        canonicos = tabla[auxiliar_canon]
    else:
        canonicos = normalizar_columna_telefono(
            tabla, columna_telefono
        )[auxiliar_canon]

    # Tipos: DC.4 crea ``telefono_tipo`` y ``telefono_motivo``.
    auxiliar_tipo = f"{columna_telefono}_tipo"
    if auxiliar_tipo in tabla.columns:
        tipos = tabla[auxiliar_tipo]
    else:
        tipos = clasificar_columna_telefono(
            tabla, columna_telefono
        )[auxiliar_tipo]

    filas_normalizados = _indices_con_predicado(canonicos, _es_valor_no_vacio)
    filas_moviles = _indices_con_predicado(tipos, lambda v: v == TIPO_MOVIL)
    filas_fijos = _indices_con_predicado(tipos, lambda v: v == TIPO_FIJO)
    filas_invalidos = _indices_con_predicado(tipos, lambda v: v == TIPO_INVALIDO)

    return (
        _cifra_disponible(filas_normalizados),
        _cifra_disponible(filas_moviles),
        _cifra_disponible(filas_fijos),
        _cifra_disponible(filas_invalidos),
    )


def _calcular_correos(
    tabla: pd.DataFrame,
    columna_correo: str | None,
) -> Cifra:
    """Cuenta correos marcados (DC.5)."""
    if columna_correo is None or columna_correo not in tabla.columns:
        return _cifra_no_disponible(_MOTIVO_SIN_COLUMNA_CORREO)

    filas_marcados: list[int] = []
    columna = tabla[columna_correo]
    for i, valor in enumerate(columna):
        _, valido, motivo = validar_correo(valor)
        if not valido and motivo:
            filas_marcados.append(i)
    return _cifra_disponible(filas_marcados)


def _asegurar_normalizado(
    tabla: pd.DataFrame,
    columna_telefono: str,
) -> pd.DataFrame:
    auxiliar_canon = f"{columna_telefono}_normalizado"
    if auxiliar_canon in tabla.columns:
        return tabla
    return normalizar_columna_telefono(tabla, columna_telefono)


def _detectar_grupos(
    tabla: pd.DataFrame, columna_telefono: str
) -> pd.DataFrame:
    from dataclean.duplicados import detectar_duplicados_por_telefono
    return detectar_duplicados_por_telefono(tabla, columna_telefono)


def _calcular_grupos(
    tabla: pd.DataFrame,
    columna_telefono: str | None,
) -> tuple[tuple[GrupoDuplicados, ...], Cifra]:
    if columna_telefono is None or columna_telefono not in tabla.columns:
        return (), _cifra_no_disponible(_MOTIVO_SIN_COLUMNA_TELEFONO)

    tabla_con_aux = _asegurar_normalizado(tabla, columna_telefono)
    resultado = _detectar_grupos(tabla_con_aux, columna_telefono)

    grupos: list[GrupoDuplicados] = []
    ids = resultado["grupo_id"].tolist()
    col_canon = f"{columna_telefono}_canon"
    if col_canon in resultado.columns:
        canonicos = resultado[col_canon].tolist()
    else:
        canonicos = resultado[f"{columna_telefono}_normalizado"].tolist()

    agrupado: dict[str, list[int]] = {}
    canonico_por_grupo: dict[str, str] = {}
    for i, gid in enumerate(ids):
        if not gid or gid == "":
            continue
        agrupado.setdefault(gid, []).append(i)
        canonico_por_grupo[gid] = str(canonicos[i] or "")

    for gid in sorted(agrupado.keys()):
        filas = agrupado[gid]
        if len(filas) < 2:
            continue
        grupos.append(
            GrupoDuplicados(
                id=gid,
                filas=tuple(filas),
                canonico=canonico_por_grupo[gid],
            )
        )

    total = Cifra(
        valor=len(grupos),
        disponible=True,
        motivo="",
        filas=tuple(range(len(grupos))),
    )
    return tuple(grupos), total


def generar_reporte(
    tabla: pd.DataFrame,
    columna_telefono: str | None = None,
    columna_correo: str | None = None,
) -> Reporte:
    """Genera el reporte de limpieza a partir de una tabla.

    Parametros:
        tabla: la tabla ya cargada (vía ``cargar_tabla`` de DC.1).
        columna_telefono: nombre de la columna de telefonos. Si es
            ``None`` o la columna no esta, las cifras de telefono
            y duplicados quedan no disponibles (Cierre 3).
        columna_correo: nombre de la columna de correos. Misma
            semantica de "no disponible" si falta.

    Retorna:
        Un :class:`Reporte` inmutable con todas las cifras. Cada
        cifra se puede rastrear (Cierre 2) y dice si esta
        disponible (Cierre 3).
    """
    registros_totales = len(tabla)

    telefonos_normalizados, telefonos_moviles, telefonos_fijos, telefonos_invalidos = (
        _calcular_telefonos(tabla, columna_telefono or "")
    )

    correos_marcados = _calcular_correos(tabla, columna_correo)
    grupos, total_grupos = _calcular_grupos(tabla, columna_telefono)

    return Reporte(
        registros_totales=registros_totales,
        telefonos_normalizados=telefonos_normalizados,
        telefonos_moviles=telefonos_moviles,
        telefonos_fijos=telefonos_fijos,
        telefonos_invalidos=telefonos_invalidos,
        correos_marcados=correos_marcados,
        grupos_duplicados=grupos,
        total_grupos_duplicados=total_grupos,
    )