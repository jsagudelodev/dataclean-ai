"""Clasificacion de columnas: que es cada columna de la tabla.

Las hojas de calculo que recibimos no tienen un esquema pactado: llegan
con cabeceras como ``TELEFONO``, ``Cel``, ``movil 2``, ``Correo
electronico`` o ``NOMBRE COMPLETO``. Antes de tocar los datos tenemos
que saber que contiene cada columna, pero **sin destruir nada** (regla
4 del encargo): una columna que no reconocemos se conserva intacta y
se marca como no clasificada, para que un paso posterior decida.

Por que existe este modulo: el clasificador aísla la decision
heurística del resto del pipeline. Aqui solo se mira el NOMBRE de la
columna (no sus valores), porque el enunciado de DC.2 trata sobre
cabeceras. Si en el futuro hay que clasificar por contenido, se añade
otro modulo al lado sin tocar este.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum

import pandas as pd


class RolColumna(str, Enum):
    """Roles que podemos asignar a una columna.

    Hereda de ``str`` para que ``str(rol) == rol.value`` y el valor sea
    estable si lo serializamos a JSON mas adelante, pero ``is``
    compara por identidad de miembro (recomendado por la docs de
    ``enum``).
    """

    TELEFONO = "telefono"
    CORREO = "correo"
    NOMBRE = "nombre"
    NO_CLASIFICADA = "no_clasificada"


# Sinonimos por rol, ya normalizados (ver ``_normalizar``). Mantenerlos
# normalizados evita re-normalizar miles de veces en cada llamada y
# hace explicito que la comparacion es contra la forma canonica.
#
# Sinonimos de telefono: cubre lo que dice el enunciado (``TELEFONO``,
# ``Cel``, ``movil 2``) y lo habitual en listados hispanos (``tel``,
# ``celular``, ``movil``, ``fijo``).
# Sinonimos de correo: ``correo``, ``email``, ``e-mail``, ``mail``.
# Sinonimos de nombre: ``nombre``, ``contacto`` (lo segundo es lo que
# usan muchos CRM cuando solo hay un campo de "persona").
SINONIMOS_POR_ROL: dict[RolColumna, frozenset[str]] = {
    RolColumna.TELEFONO: frozenset(
        {"telefono", "tel", "cel", "celular", "movil", "movil2", "fijo", "telf"}
    ),
    RolColumna.CORREO: frozenset(
        {"correo", "email", "e-mail", "mail", "correoelectronico"}
    ),
    RolColumna.NOMBRE: frozenset(
        {"nombre", "contacto", "persona", "nombrecompleto"}
    ),
}

# Orden de prioridad si una columna encajara en mas de un rol (caso
# raro con la lista del enunciado, pero pasa con sinonimos tipo
# "contacto" cuando alguien exporta "contacto telefonico"). Telefono
# gana porque es el dato mas escaso y valioso para DataClean.
_PRIORIDAD: tuple[RolColumna, ...] = (
    RolColumna.TELEFONO,
    RolColumna.CORREO,
    RolColumna.NOMBRE,
)


_ESPACIOS_MULTIPLES = re.compile(r"\s+")


def _normalizar(nombre: str) -> str:
    """Devuelve la forma canonica de un nombre de columna.

    Pasos (en este orden):
      1. ``strip`` para borrar espacios al inicio y al final.
      2. ``casefold`` para que ``TELEFONO`` y ``telefono`` sean iguales.
         ``casefold`` es mejor que ``lower`` para español: además de
         mayúsculas, deshace ligaduras y variantes que ``lower`` deja
         (p. ej. la ``ß`` alemana, que en español no aplica pero
         tampoco estorba).
      3. NFKD + encode/decode ascii para quitar tildes y diéresis:
         ``Correo electrónico`` -> ``correo electronico``. La ñ
         tambien se va (``Muñoz`` -> ``munoz``); eso es intencionado
         porque el matching es contra sinonimos ASCII.
      4. Colapso de espacios multiples a uno solo.
    """
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    sin_mayusculas = sin_tildes.casefold()
    sin_espacios = _ESPACIOS_MULTIPLES.sub(" ", sin_mayusculas).strip()
    # Por ultimo, pegamos todo: ``correo electronico`` -> ``correoelectronico``
    # para que el sinonimo precomputado ``correoelectronico`` coincida
    # sin que el caller tenga que saber que hay un espacio "logico" en
    # medio. Esto cubre el Cierre 3 (espacios sobrantes) sin necesidad
    # de sinonimos duplicados con espacio.
    return sin_espacios.replace(" ", "")


def _rol_para(nombre_columna: str) -> RolColumna:
    """Decide el rol de una columna por su nombre (ya normalizado).

    Si no encaja en ninguno de los sinonimos conocidos, devuelve
    ``RolColumna.NO_CLASIFICADA``. **No lanza**: la regla 4 manda que
    una columna desconocida se conserva intacta, no que se rechace.
    """
    for rol in _PRIORIDAD:
        if nombre_columna in SINONIMOS_POR_ROL[rol]:
            return rol
    return RolColumna.NO_CLASIFICADA


def clasificar_columnas(tabla: pd.DataFrame) -> dict[str, RolColumna]:
    """Asigna un rol a cada columna de la tabla, mirando solo el nombre.

    Args:
        tabla: el ``DataFrame`` cargado por ``cargar_tabla``. **No se
            modifica**: la funcion solo lee ``tabla.columns`` y devuelve
            un diccionario.

    Returns:
        Un ``dict`` ``{nombre_original: RolColumna}`` con una entrada
        por columna, en el mismo orden que ``tabla.columns``. Las
        columnas que no reconocemos aparecen como
        ``RolColumna.NO_CLASIFICADA``, no se descartan.

    Notas:
        - La comparacion es contra sinonimos pre-normalizados: no
          importa que la cabecera tenga mayusculas, tildes o espacios
          sobrantes (Cierre 3).
        - Si dos columnas tienen el mismo nombre tras normalizar, se
          clasifican igual; eso es comportamiento esperado (la
          deduplicacion es tema de otro item).
    """
    resultado: dict[str, RolColumna] = {}
    for nombre in tabla.columns:
        # ``_normalizar`` acepta ``str``; pandas suele devolver ``str``
        # pero nos protegemos por si en el futuro llega un dtype raro.
        clave = _normalizar(str(nombre))
        resultado[str(nombre)] = _rol_para(clave)
    return resultado


__all__ = ["RolColumna", "clasificar_columnas"]
