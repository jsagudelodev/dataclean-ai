"""Normalizacion y clasificacion de telefonos: una misma persona, una sola forma.

Un mismo contacto puede llegar escrito de cuatro formas distintas:
``3001234567``, ``300 123 4567``, ``+57 300 1234567``, ``(300)123-4567``.
Para que el resto del pipeline (duplicados, reportes, conciliacion) pueda
trabajar, todos esos textos tienen que producir **un mismo** valor canonico.

Una vez normalizado, el reporte necesita saber **que es** ese telefono:
si es un movil colombiano, si es un fijo con indicativo, o si no es
ninguna de las dos cosas. DC.4 cierra eso.

Por que existe este modulo: la regla 4 del encargo dice "ante la duda,
conservar". Eso aqui significa que un numero que NO sabemos normalizar
(porque le faltan digitos, trae letras, o el codigo de pais no encaja
con el configurado) **se marca y se conserva** en la columna original;
no se borra, no se sustituye por un valor inventado. El caller decide
que hacer con la marca. La clasificacion hereda esa misma filosofia:
un numero que no encaja en las dos categorias conocidas (movil / fijo)
se marca como ``"INVALIDO"`` **con un motivo legible** y su valor
original se preserva; no se borra.

Diseno (regla del Cierre 2: el pais se configura, no esta escrito):
    El codigo de pais se pasa como parametro (``codigo_pais="+57"`` por
    defecto). Si el caller lo necesita para otro mercado, lo pasa y ya.
    No hay un mapa hardcodeado de "todos los paises del mundo"; anadir
    mercados nuevos es trabajo del item que los pida.

Diseno DC.4 (cero falsos positivos):
    La clasificacion **delega** en la normalizacion de DC.3: nunca
    clasifica un telefono que la normalizacion marco como dudoso.
    Asi, si el canonico existe, la regla es mirar solo el primer
    digito y la longitud: un ``3...`` de 10 digitos es ``MOVIL``;
    cualquier otro ``X...`` de 10 digitos es ``FIJO`` (los indicativos
    colombianos que NO son 3 son fijos: Bogota 1, Medellin 4, Cali 2,
    Barranquilla 5, Cartagena 5, Pereira 6, Bucaramanga 7, etc.).
    Un numero que no encaja en ninguno de los dos grupos se conserva
    tal cual y se devuelve como ``INVALIDO`` con su motivo. Asi, un
    numero de 5 digitos nunca queda "promovido" a una categoria por
    error: se queda como invalido, con su valor original a la vista.
"""

from __future__ import annotations

import numbers
import re
from typing import Final

import numpy as np
import pandas as pd


# Caracteres que no aportan a un telefono: espacios, guiones, parentesis,
# puntos y barras. El ``+`` se trata aparte (es la marca de codigo de
# pais), asi que va en su propio grupo para que el caller pueda
# distinguirlo si quiere.
_SEPARADORES: Final[re.Pattern[str]] = re.compile(r"[\s\-\.\(\)/]")

# Caracteres validos en un telefono: digitos, ``+`` opcional al
# principio, y separadores tipicos. Si hay una letra en medio, el
# numero no se puede normalizar. Asi, el caller puede decidir rapido
# si vale la pena procesar la cadena ANTES de limpiar separadores.
_VALIDOS: Final[re.Pattern[str]] = re.compile(r"^\+?[\d\s\-\.\(\)/]+$")

# Longitud esperada por defecto de un telefono normalizado: 10 digitos
# (mercado colombiano: indicativo de ciudad + numero). El caller puede
# sobreescribirla con ``longitud_esperada`` para otros mercados
# (``+34`` son 9, ``+1`` son 10, etc.). Asi el pais se configura, no
# esta escrito en el codigo (regla del Cierre 2).
_LONGITUD_ESPERADA_POR_DEFECTO: Final[int] = 10

# --- DC.4: tipos de telefono --------------------------------------------
# Solo dos categorias oficiales para Colombia + un "no encaja" para
# cualquier cosa que no podamos asegurar. NO usamos ``None`` para el
# tipo porque eso fuerza al caller a tratar dos cosas distintas
# (no-clasificado vs sin-datos) con la misma logica; y romperia el
# principio "conservar": un INVALIDO no es lo mismo que un hueco.
TIPO_MOVIL: Final[str] = "MOVIL"
TIPO_FIJO: Final[str] = "FIJO"
TIPO_INVALIDO: Final[str] = "INVALIDO"

# Prefijos de los indicativos de telefonia fija en Colombia. NO son
# exhaustivos: la estrategia real es "si NO empieza por 3 y tiene la
# longitud esperada, es fijo", porque los indicativos fijos validos
# (Bogota 1, Medellin 4, Cali 2, Barranquilla 5, Cartagena 5, Pereira
# 6, Bucaramanga 7, Cucuta 7, Ibague 8, Manizales 6, etc.) NO
# empiezan por 3. Mantener una lista cerrada aqui seria escribir el
# conocimiento del regulador en el codigo: si MinTIC agrega un
# indicativo, el codigo se queda obsoleto. La regla "primer digito !=
# 3 y longitud esperada" cubre todos los fijos colombianos sin
# enumerarlos.
#
# El 3 es exclusivo para moviles (pospago y prepago) en Colombia;
# es la unica "lista cerrada" que necesitamos y es publica y estable
# desde hace decadas.
_PREFIJO_MOVIL_COLOMBIA: Final[str] = "3"


def _a_digitos(valor: str) -> str:
    """Devuelve solo los digitos del valor. La ``+`` y letras se pierden."""
    return "".join(caracter for caracter in valor if caracter.isdigit())


def _numero_a_texto(valor: object) -> str | None:
    """Devuelve los digitos de un telefono que llego como numero, o ``None``.

    Pandas lee una columna de telefonos como ``int64`` si esta completa y
    como ``float64`` en cuanto tiene una sola celda vacia: ``3001234567``
    llega entonces como ``3001234567.0``. Rechazar esos valores marcaria
    como invalidos todos los moviles de la columna (el falso positivo que
    el criterio de vendible prohibe). Un numero con decimales reales, un
    ``NaN`` o un booleano no son un telefono.
    """
    if isinstance(valor, (bool, np.bool_)):
        return None
    if isinstance(valor, numbers.Integral):
        return str(int(valor))
    if isinstance(valor, numbers.Real):
        flotante = float(valor)
        if flotante.is_integer():
            return str(int(flotante))
    return None


def normalizar_telefono(
    valor: object,
    codigo_pais: str = "+57",
    longitud_esperada: int = _LONGITUD_ESPERADA_POR_DEFECTO,
) -> tuple[str | None, bool]:
    """Normaliza un telefono a su forma canonica (solo digitos).

    La funcion **no destruye** la entrada: devuelve el valor normalizado
    (o ``None`` si no se pudo) y una marca ``marcado`` (``True`` si se
    pudo normalizar, ``False`` si no). El caller decide que hacer con
    la marca; este modulo solo informa.

    Formas que reconoce como el mismo numero (ejemplo colombiano):
        ``3001234567``       -> ``3001234567``
        ``300 123 4567``     -> ``3001234567``
        ``+57 300 1234567``  -> ``3001234567``
        ``(300)123-4567``    -> ``3001234567``

    Casos que **se conservan y se marcan** (devuelve ``(None, False)``):
        * Valor vacio, ``None`` o solo espacios.
        * Texto con letras (``"llamar a juan"``).
        * Longitud incorrecta para el mercado configurado (ni muy
          corto ni muy largo): por ejemplo, 5 digitos no es un telefono
          colombiano completo.
        * Codigo de pais explicito que NO coincide con el configurado
          (``+34 911 23 45 67`` con ``codigo_pais="+57"``): mejor
          marcar que inventar.

    Args:
        valor: cualquier valor. Si no es texto, se intenta convertir.
        codigo_pais: prefijo internacional con el ``+`` (``"+57"``,
            ``"+34"``, ...). Si el telefono llega con un prefijo
            explicito distinto, se marca como no normalizable.
        longitud_esperada: cuantos digitos tiene que tener el numero
            una vez limpio de prefijo. Default 10 (mercado colombiano);
            para ``+34`` espanol, pasar 9.

    Returns:
        Tupla ``(normalizado, marcado)``:
          * ``normalizado`` (``str | None``): la forma canonica
            (solo digitos, sin ``+``), o ``None`` si no se pudo.
          * ``marcado`` (``bool``): ``True`` si ``normalizado`` es
            util; ``False`` si el valor quedo dudoso.
    """
    # 1) Vacios y tipos no string. Un numero entero (``int``, ``int64``
    #    o ``3001234567.0``) se lee como sus digitos; cualquier otro tipo
    #    no se puede normalizar.
    if valor is None:
        return None, False
    if not isinstance(valor, str):
        valor = _numero_a_texto(valor)
        if valor is None:
            return None, False
    texto = valor.strip()
    if not texto:
        return None, False

    # 2) Si trae letras, no es un telefono (regla 4: conservar y
    #    marcar, no inventar).
    if not _VALIDOS.match(texto):
        return None, False

    # 3) Quitar separadores y trabajar solo con ``+`` + digitos.
    limpio = _SEPARADORES.sub("", texto)
    if not limpio:
        return None, False

    # 4) Comparar contra el codigo de pais por digitos: ``+57`` -> ``57``.
    digitos_pais = _a_digitos(codigo_pais) if codigo_pais else ""

    if not digitos_pais:
        digitos = _a_digitos(limpio)
    elif limpio.startswith("+"):
        # Telefono internacional explicito. Si NO encaja con el
        # pais configurado, marcamos: no queremos "normalizar" un
        # espanol a 10 digitos colombianos.
        digitos_tel = _a_digitos(limpio)
        if not digitos_tel.startswith(digitos_pais):
            return None, False
        digitos = digitos_tel[len(digitos_pais):]
    else:
        # Telefono sin prefijo internacional: si empieza por el
        # codigo de pais "crudo" (algunos listados lo ponen asi,
        # p.ej. ``57 300 1234567``), se lo quitamos; si no, lo
        # tratamos como nacional.
        digitos = _a_digitos(limpio)
        if digitos.startswith(digitos_pais) and len(digitos) > len(digitos_pais):
            digitos = digitos[len(digitos_pais):]

    # 5) ``0`` a la izquierda de un numero nacional colombiano es el
    #    prefijo de marcado local: ``(057) 300 1234567`` -> ``3001234567``.
    if digitos.startswith("0") and digitos_pais == "57":
        digitos_sin_ceros = digitos.lstrip("0")
        if digitos_sin_ceros:
            digitos = digitos_sin_ceros

    # 6) Si despues de todo lo de arriba no quedan digitos, o la
    #    longitud no encaja con la del mercado, marcamos. NO
    #    truncamos ni rellenamos: eso seria inventar.
    if not digitos:
        return None, False
    if len(digitos) != longitud_esperada:
        return None, False

    return digitos, True


def normalizar_columna_telefono(
    tabla: pd.DataFrame,
    columna: str,
    codigo_pais: str = "+57",
    longitud_esperada: int = _LONGITUD_ESPERADA_POR_DEFECTO,
) -> pd.DataFrame:
    """Devuelve una copia de ``tabla`` con dos columnas auxiliares de telefono.

    Las columnas nuevas son:
      * ``f"{columna}_normalizado"``: la forma canonica (``str`` o
        ``""`` si no se pudo normalizar). Elegimos ``""`` y no
        ``None`` para que pandas no la promotione a ``object``.
      * ``f"{columna}_marcado"``: ``True`` si el telefono se pudo
        normalizar, ``False`` si quedo dudoso. La columna original
        **se conserva intacta** (regla 4).

    Args:
        tabla: el ``DataFrame`` con los contactos.
        columna: nombre de la columna a normalizar.
        codigo_pais: prefijo internacional con el ``+``.
        longitud_esperada: digitos esperados tras limpiar prefijos.
            Se reenvia a ``normalizar_telefono`` para toda la columna.

    Returns:
        Un ``DataFrame`` nuevo (no se muta el original) con las dos
        columnas anadidas al final.
    """
    if columna not in tabla.columns:
        raise ValueError(
            f"La columna {columna!r} no existe en la tabla "
            f"(hay: {list(tabla.columns)})."
        )

    resultados = tabla[columna].map(
        lambda v: normalizar_telefono(v, codigo_pais, longitud_esperada)
    )
    normalizados = [r[0] if r[0] is not None else "" for r in resultados]
    marcados = [bool(r[1]) for r in resultados]

    copia = tabla.copy()
    copia[f"{columna}_normalizado"] = normalizados
    copia[f"{columna}_marcado"] = marcados
    return copia


def _motivo_invalido(valor: object, digitos: str | None) -> str:
    """Devuelve un motivo legible para un telefono que no se clasifico.

    El motivo va al reporte (regla DC.4 Cierre 1 + regla 9: el caller
    necesita saber POR QUE se marco, no solo QUE se marco). NO incluye
    el numero en si (regla 9: nada de contactos en logs).
    """
    if digitos is None:
        # El normalizador no produjo canonico: ya hay un motivo
        # concreto en su logica, pero desde la clasificacion lo que
        # vemos es "no pudimos obtener un canonico". Razones tipicas:
        # vacio, letras, longitud incorrecta, prefijo de otro pais.
        if valor is None:
            return "valor ausente"
        texto = str(valor).strip()
        if not texto:
            return "valor vacio"
        return "no se pudo normalizar"
    # Hay canonico pero no encaja en MOVIL/FIJO. Por construccion
    # hoy solo ocurre cuando la longitud esperada es distinta de la
    # longitud que toma la regla MOVIL/FIJO; mantenemos el motivo
    # generico por si en el futuro hay mas criterios.
    return f"longitud {len(digitos)} no encaja en movil ni fijo"


def clasificar_telefono(
    valor: object,
    codigo_pais: str = "+57",
    longitud_esperada: int = _LONGITUD_ESPERADA_POR_DEFECTO,
    prefijo_movil: str = _PREFIJO_MOVIL_COLOMBIA,
) -> tuple[str | None, str, str]:
    """Clasifica un telefono normalizado en ``MOVIL`` / ``FIJO`` / ``INVALIDO``.

    DC.4. La funcion **no destruye**: devuelve el canonico (o ``None``
    si el normalizador no lo pudo producir), el tipo y un motivo
    legible cuando el tipo es ``INVALIDO``. Cuando el tipo es
    ``MOVIL`` o ``FIJO``, el motivo es ``""`` (no hay nada que
    explicar).

    Estrategia (regla del item: cero falsos positivos):
        1) Delega en :func:`normalizar_telefono`. Si el normalizador
           no produce canonico, devolvemos ``INVALIDO`` con motivo: no
           queremos clasificar algo que no sabemos ni leer.
        2) Si hay canonico y empieza por ``prefijo_movil`` (``"3"``
           por defecto para Colombia) -> ``MOVIL``.
        3) Si hay canonico y NO empieza por ``prefijo_movil`` y tiene
           la longitud esperada -> ``FIJO`` (indicativos colombianos
           Bog=1, Med=4, Cal=2, Baq=5, etc.).
        4) Cualquier otro caso -> ``INVALIDO`` con motivo. Esto cubre
           explicitamente el caso del item: un numero de 5 digitos
           que no es ni una cosa ni otra.

    Args:
        valor: cualquier valor (mismo contrato que
            :func:`normalizar_telefono`).
        codigo_pais: prefijo internacional con el ``+``.
        longitud_esperada: digitos esperados tras limpiar prefijos.
        prefijo_movil: primer digito que identifica un movil del
            mercado. Por defecto ``"3"`` (Colombia); para otros
            mercados el caller lo pasa.

    Returns:
        Tupla ``(canonico, tipo, motivo)``:
          * ``canonico``: la forma canonica (digitos) o ``None`` si no
            se pudo normalizar.
          * ``tipo``: ``"MOVIL"``, ``"FIJO"`` o ``"INVALIDO"``.
          * ``motivo``: ``""`` si es ``MOVIL``/``FIJO``; texto
            legible si es ``"INVALIDO"``.
    """
    canonico, _marcado = normalizar_telefono(
        valor, codigo_pais=codigo_pais, longitud_esperada=longitud_esperada
    )
    if canonico is None:
        return None, TIPO_INVALIDO, _motivo_invalido(valor, None)

    if canonico.startswith(prefijo_movil):
        return canonico, TIPO_MOVIL, ""

    # Hay canonico, longitud OK, y NO empieza por el prefijo de
    # movil: por construccion (la longitud ya fue validada por el
    # normalizador) es un fijo colombiano.
    if len(canonico) == longitud_esperada:
        return canonico, TIPO_FIJO, ""

    # No deberiamos llegar aqui con la longitud esperada por defecto
    # (la normalizacion ya filtra longitudes malas), pero si el
    # caller pasa una longitud distinta a la que asume la regla
    # MOVIL/FIJO, el canonico es valido pero no encaja en ninguna
    # categoria. Marcamos con motivo.
    return canonico, TIPO_INVALIDO, _motivo_invalido(valor, canonico)


def clasificar_columna_telefono(
    tabla: pd.DataFrame,
    columna: str,
    codigo_pais: str = "+57",
    longitud_esperada: int = _LONGITUD_ESPERADA_POR_DEFECTO,
    prefijo_movil: str = _PREFIJO_MOVIL_COLOMBIA,
) -> pd.DataFrame:
    """Devuelve una copia de ``tabla`` con tres columnas auxiliares DC.4.

    Las columnas nuevas son:
      * ``f"{columna}_canonico"``: la forma canonica (``str`` o ``""``
        si no se pudo normalizar). Mismo convenio que DC.3: ``""`` y
        no ``None`` para no promotar la columna a ``object``.
      * ``f"{columna}_tipo"``: ``"MOVIL"``, ``"FIJO"`` o
        ``"INVALIDO"``.
      * ``f"{columna}_motivo"``: ``""`` para ``MOVIL``/``FIJO``;
        motivo legible para ``"INVALIDO"``.

    La columna original **se conserva intacta** (regla 4): nunca se
    sobreescribe con el canonico.
    """
    if columna not in tabla.columns:
        raise ValueError(
            f"La columna {columna!r} no existe en la tabla "
            f"(hay: {list(tabla.columns)})."
        )

    resultados = tabla[columna].map(
        lambda v: clasificar_telefono(
            v,
            codigo_pais=codigo_pais,
            longitud_esperada=longitud_esperada,
            prefijo_movil=prefijo_movil,
        )
    )
    canonicos = [r[0] if r[0] is not None else "" for r in resultados]
    tipos = [r[1] for r in resultados]
    motivos = [r[2] for r in resultados]

    copia = tabla.copy()
    copia[f"{columna}_canonico"] = canonicos
    copia[f"{columna}_tipo"] = tipos
    copia[f"{columna}_motivo"] = motivos
    return copia