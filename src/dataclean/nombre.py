"""Normalizacion de nombres propios: presentable, sin perder tildes ni siglas.

Un mismo contacto puede llegar escrito de varias formas:

    ``JUAN PEREZ``          -> mayusculas totales
    ``juan perez``          -> minusculas totales
    ``Juan Pérez``          -> forma "bonita" con tildes
    `` Juan   Pérez  ``     -> espacios de sobra

Para que el reporte y la deduplicacion (DC.9) puedan trabajar, todas
esas formas tienen que producir **un mismo** valor normalizado, con
las tildes conservadas (regla 4: "ante la duda, conservar" -- las
tildes son dato, no ruido) y las **siglas** que ya venian en
mayusculas se conservan en mayusculas (``SAS``, ``LTDA``, ``CIA``).

Por que existe este modulo:
    El item DC.6 pide normalizar nombres de personas en hojas de
    contactos. La intencion es **presentable**, no canonico en el
    sentido de "un nombre por persona": lo que devuelve este modulo
    es lo que el reporte va a mostrar al cliente cuando le pregunte
    "como quedo este nombre?". Por eso conservamos tildes y siglas.

Decisiones de diseno explicitas:
    * **Particulas** (``de``, ``del``, ``la``, ``las``, ``los``, ``y``,
      ``e``, ``van``, ``von``, ``der``) **no** se ponen en mayuscula
      en posicion no inicial. La primera palabra SI se capitaliza
      aunque sea particular (``DE LA CRUZ`` -> ``De la Cruz``); es
      la convencion que el cliente espera ver en el reporte.
    * **Siglas** se conservan en mayusculas: ``EMPRESA SAS`` ->
      ``Empresa SAS``, ``CIA LTDA DE TRANSPORTES`` -> ``CIA LTDA
      de Transportes``. Esto es importante para no perder la razon
      social de empresas donde la sigla es dato.
    * **Tildes** se conservan: regla 4 ("ante la duda, conservar").
    * **Espacios** se colapsan y se quitan los de los bordes; la
      cadena interna no se reordena.
    * **Ausentes** (``None``, ``NaN``, vacio) se devuelven como
      ``(None, False)``: igual que en DC.3 y DC.5, los huecos no
      son "invalidos con motivo"; son otra cosa.
"""

from __future__ import annotations

from typing import Final

import pandas as pd


# Particulas que el item DC.6 obliga a no-capitalizar (Cierre 2).
# La lista viene en minusculas; la comparacion se hace en minusculas
# para que ``DE`` y ``de`` cuenten igual. Configurable por el caller
# (consistente con la regla del Cierre 2 de DC.3: "el pais se
# configura, no esta escrito").
_PARTICULAS_POR_DEFECTO: Final[frozenset[str]] = frozenset({
    "de", "del", "la", "las", "los", "y", "e", "van", "von", "der",
})

# Siglas hispanas conocidas que el item DC.6 obliga a conservar en
# mayusculas (Cierre 3). Usamos una lista **cerrada y pequena** en
# vez de una heuristica de patron (longitud, terminaciones,
# vocales) por una razon concreta: cualquier heuristica de patron
# falla en al menos uno de los dos extremos:
#
#   * patron laxo (>= 2 letras mayusculas)  -> ``JUAN``, ``JOSE``,
#     ``ANA``, ``LOLA`` se conservan en mayusculas y el reporte
#     muestra "JUAN PEREZ" en vez de "Juan Perez" (falso positivo
#     en la normalizacion, el cliente ve su nombre gritando).
#   * patron estricto (longitud, terminaciones, etc.) -> ``LTDA``
#     sale "Ltda" (falso negativo en la deteccion de sigla, el
#     cliente ve su razon social rota).
#
# La lista cerrada es la unica opcion que cumple los DOS extremos
# del item a la vez: las siglas que importan estan aqui, y todo lo
# que no esta aqui se trata como nombre propio. Es ademas
# extensible: si aparece un nuevo dominio (ONG, EPS, etc.), se
# anade y ya.
_SIGLAS_CONOCIDAS: Final[frozenset[str]] = frozenset({
    # Formas juridicas hispanas (el item nombra LTDA explicitamente).
    "SA", "SL", "SRL", "SC", "SAS", "SAB", "SAC", "SAU", "SAL",
    "LTDA", "CIA", "EIRL", "EADA", "SCP",
    # Tipos de organizacion.
    "ONG", "EPS", "IPS", "OC", "PYME", "ONGD",
    # Terminos administrativos.
    "NIT", "DNI", "CIF", "IVA", "IRPF", "ISLR",
})


def _es_particula(token: str, particulas: frozenset[str]) -> bool:
    """Devuelve ``True`` si ``token`` es una particular.

    Compara contra ``particulas`` en minusculas para que ``DE``,
    ``De`` y ``de`` cuenten igual.
    """
    return token.lower() in particulas


def _es_sigla(token: str, particulas: frozenset[str]) -> bool:
    """Devuelve ``True`` si ``token`` es una sigla que ya venia en mayusculas.

    Regla: ``token`` esta en la lista cerrada de siglas conocidas
    Y todas sus letras son ASCII mayusculas. Asi:

      * ``SAS``, ``LTDA``, ``CIA``, ``SA`` -> True (estan en la
        lista, se conservan en mayusculas, Cierre 3).
      * ``JUAN``, ``JOSE``, ``ANA``, ``LOLA`` -> False (no estan
        en la lista, son nombres propios y van a Title Case).
      * ``Sas``, ``sas`` -> False (no estan en mayusculas).
      * ``DE`` -> False primero por la particular (chequeada
        antes), y ademas no esta en la lista de siglas.
    """
    if _es_particula(token, particulas):
        return False
    letras = [c for c in token if c.isalpha() and c.isascii()]
    if not letras or not all(c.isupper() for c in letras):
        return False
    return token in _SIGLAS_CONOCIDAS


def _title_sin_particulas(
    token: str,
    es_primera: bool,
    particulas: frozenset[str] = _PARTICULAS_POR_DEFECTO,
) -> str:
    """Devuelve ``token`` con title-case, respetando particulas y siglas.

    Orden de las comprobaciones (importa):

      1. **Particulas**: si ``token`` es una particular y NO es la
         primera palabra, va en minusculas (``DE`` -> ``de``,
         Cierre 2). Si es la primera palabra, va en mayuscula
         (``DE LA CRUZ`` -> ``De la Cruz``).
      2. **Siglas**: si cumple la heuristica de sigla, se conserva
         tal cual en mayusculas (Cierre 3).
      3. **Title case** para el resto (``perez`` -> ``Perez``,
         ``pérez`` -> ``Pérez``); las tildes se conservan porque
         ``str.title()`` opera letra a letra sobre la forma
         ``lower()`` sin perder diacriticos.
    """
    minuscula = token.lower()
    if minuscula in particulas:
        return minuscula.title() if es_primera else minuscula
    if _es_sigla(token, particulas):
        return token
    return minuscula.title()


def _normalizar_interno(texto: str, particulas: frozenset[str]) -> str:
    """Normaliza un nombre que sabemos que es ``str`` no vacio.

    Pasos:
      1. colapsar espacios y quitar los de los bordes;
      2. partir en tokens;
      3. aplicar ``_title_sin_particulas`` token a token.
    """
    limpio = " ".join(texto.split())
    if not limpio:
        return ""
    tokens = limpio.split(" ")
    salida: list[str] = []
    for i, token in enumerate(tokens):
        salida.append(_title_sin_particulas(token, es_primera=(i == 0),
                                            particulas=particulas))
    return " ".join(salida)


def normalizar_nombre(
    valor: object,
    particulas: frozenset[str] = _PARTICULAS_POR_DEFECTO,
) -> tuple[str | None, bool]:
    """Normaliza un nombre y devuelve ``(normalizado, marcado)``.

    DC.6 Cierre 1, 2 y 3:

      * **Cierre 1** -- las tres formas del item
        (``JUAN PEREZ``, ``juan perez``, ``Juan Pérez``) producen
        el mismo valor normalizado, con las tildes conservadas.
      * **Cierre 2** -- las particulas (``de``, ``del``, ``la``)
        NO se ponen en mayuscula en posicion no inicial.
      * **Cierre 3** -- una sigla que ya venia en mayusculas
        (``SAS``, ``LTDA``) se conserva en mayusculas.

    Args:
        valor: cualquier valor. ``None``, ``NaN`` de pandas y
            vacios se tratan como **ausentes**: se devuelven como
            ``(None, False)``. No-string se convierte a ``str``;
            si la conversion falla, ``(None, False)``.
        particulas: conjunto de particulas que NO se capitalizan
            en posicion no inicial. Configurable para otros
            mercados.

    Returns:
        Tupla ``(normalizado, marcado)``:
          * ``normalizado`` (``str | None``): la forma presentable
            del nombre con tildes y siglas conservadas, o ``None``
            si el valor era ausente.
          * ``marcado`` (``bool``): ``True`` si se pudo normalizar;
            ``False`` si el valor era ausente.
    """
    if valor is None:
        return None, False
    try:
        if pd.isna(valor):  # type: ignore[arg-type]
            return None, False
    except (TypeError, ValueError):
        pass
    if not isinstance(valor, str):
        try:
            valor = str(valor)
        except Exception:  # noqa: BLE001
            return None, False
    if not valor or not valor.strip():
        return None, False

    normalizado = _normalizar_interno(valor, particulas)
    if not normalizado:
        return None, False
    return normalizado, True


def normalizar_columna_nombre(
    tabla: pd.DataFrame,
    columna: str,
    particulas: frozenset[str] = _PARTICULAS_POR_DEFECTO,
) -> pd.DataFrame:
    """Anade columnas auxiliares con la version normalizada del nombre.

    Crea (sin mutar ``tabla``):

      * ``<columna>_nombre_canonico``: la version normalizada
        (``Juan Pérez``), o ``None`` para ausentes.
      * ``<columna>_nombre_marcado``: ``True`` si se pudo
        normalizar, ``False`` si no.

    Args:
        tabla: ``DataFrame`` con la columna de nombres.
        columna: nombre de la columna a normalizar.
        particulas: ver :func:`normalizar_nombre`.

    Returns:
        Nuevo ``DataFrame`` con las dos columnas auxiliares anadidas.
    """
    canonico: list[str | None] = []
    marcado: list[bool] = []
    for valor in tabla[columna]:
        nombre, ok = normalizar_nombre(valor, particulas=particulas)
        canonico.append(nombre)
        marcado.append(ok)
    resultado = tabla.copy()
    resultado[f"{columna}_nombre_canonico"] = canonico
    resultado[f"{columna}_nombre_marcado"] = marcado
    return resultado