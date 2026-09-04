"""Normalizacion de telefonos: una misma persona, una sola forma.

Un mismo contacto puede llegar escrito de cuatro formas distintas:
``3001234567``, ``300 123 4567``, ``+57 300 1234567``, ``(300)123-4567``.
Para que el resto del pipeline (duplicados, reportes, conciliacion) pueda
trabajar, todos esos textos tienen que producir **un mismo** valor canonico.

Por que existe este modulo: la regla 4 del encargo dice "ante la duda,
conservar". Eso aqui significa que un numero que NO sabemos normalizar
(porque le faltan digitos, trae letras, o el codigo de pais no encaja
con el configurado) **se marca y se conserva** en la columna original;
no se borra, no se sustituye por un valor inventado. El caller decide
que hacer con la marca.

Diseno (regla del Cierre 2: el pais se configura, no esta escrito):
    El codigo de pais se pasa como parametro (``codigo_pais="+57"`` por
    defecto). Si el caller lo necesita para otro mercado, lo pasa y ya.
    No hay un mapa hardcodeado de "todos los paises del mundo"; anadir
    mercados nuevos es trabajo del item que los pida.
"""

from __future__ import annotations

import re
from typing import Final

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


def _a_digitos(valor: str) -> str:
    """Devuelve solo los digitos del valor. La ``+`` y letras se pierden."""
    return "".join(caracter for caracter in valor if caracter.isdigit())


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
    # 1) Vacios y tipos no string: no se puede normalizar.
    if valor is None:
        return None, False
    if not isinstance(valor, str):
        try:
            if pd.isna(valor):  # type: ignore[arg-type]
                return None, False
        except (TypeError, ValueError):
            pass
        if isinstance(valor, (int,)):
            valor = str(valor)
        else:
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