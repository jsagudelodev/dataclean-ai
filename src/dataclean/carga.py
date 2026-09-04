"""Carga de archivos de contactos (CSV o Excel).

Una sola funcion publica: ``cargar_tabla``. Decide por el contenido del
archivo, no por la extension: un ``.dat`` con bytes de Excel se carga como
Excel, y un ``.xlsx`` que en realidad es CSV se carga como CSV.

Por que existe este modulo: el primer paso de DataClean es leer lo que el
cliente envia. Si ese paso rompe con un ``UnicodeDecodeError`` o un
``BadZipFile``, la API entera cae antes de poder devolver un reporte util.
Aqui se encapsula esa decision para que el resto del pipeline solo vea
``pandas.DataFrame``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


# Codificaciones que se prueban en orden al leer un CSV. ``utf-8-sig`` se
# lleva primero porque es lo que exportan la mayoria de herramientas
# modernas (y traga el BOM si esta); ``latin-1`` (alias de ISO-8859-1) es
# lo que exporta Excel en espanol, donde las tildes viven en un solo
# byte; ``cp1252`` cubre el resto de Windows. Cualquier byte de 0x00-0xFF
# es valido en latin-1, asi que esta cadena SIEMPRE logra decodificar;
# lo que no podemos garantizar es que el resultado tenga sentido, y eso
# es responsabilidad del clasificador de DC.2, no de la carga.
CODIFICACIONES_CSV: Final[tuple[str, ...]] = ("utf-8-sig", "latin-1", "cp1252")

# Marca comun al inicio de un XLSX (que es un ZIP). No usamos extension.
FIRMA_XLSX: Final[bytes] = b"PK\x03\x04"

# Mensajes que el usuario final puede ver sin que se le tape la pantalla
# con un traceback (regla 8 del encargo).
MENSAJE_NO_CSV_NI_EXCEL: Final[str] = (
    "El archivo no parece ser un CSV ni un Excel: "
    "no se pudo decodificar como texto y tampoco tiene la firma de un "
    "libro de Excel. Comprueba que sea un .csv o un .xlsx valido."
)


class ErrorDeCargaInesperado(ValueError):
    """Se lanza cuando un archivo no se puede cargar como CSV ni como Excel.

    Es un ``ValueError`` (no ``RuntimeError``) porque el fallo es del
    contenido que nos pasan, no del estado interno del programa. Asi, el
    caller puede hacer ``except ValueError`` si quiere tratar todos los
    argumentos invalidos por igual.
    """


def _es_xlsx_por_contenido(primeros_bytes: bytes) -> bool:
    """Devuelve True si los primeros bytes parecen un XLSX (un ZIP)."""
    return primeros_bytes.startswith(FIRMA_XLSX)


def _leer_csv_con_fallback(ruta: Path) -> pd.DataFrame:
    """Lee un CSV probando codificaciones en orden hasta que una funcione.

    ``pandas.read_csv`` con ``encoding="utf-8"`` lanza
    ``UnicodeDecodeError`` en cuanto aparece una tilde en latin-1; con
    ``encoding="latin-1"`` nunca falla porque cada byte 0x00-0xFF es
    valido en latin-1, asi que esa es la red de seguridad. Entre medias
    va ``utf-8-sig`` para atrapar BOM.
    """
    ultimo_error: UnicodeDecodeError | None = None
    for codificacion in CODIFICACIONES_CSV:
        try:
            return pd.read_csv(ruta, encoding=codificacion)
        except UnicodeDecodeError as error:
            # Esta codificacion no sirve: probamos la siguiente.
            ultimo_error = error
            continue

    # latin-1 no deberia lanzar nunca; si llega aqui es un bug.
    raise ErrorDeCargaInesperado(
        f"No se pudo decodificar el CSV con ninguna codificacion: {ultimo_error}"
    ) from ultimo_error


def cargar_tabla(ruta: str | Path) -> pd.DataFrame:
    """Carga un archivo de contactos (CSV o Excel) como ``DataFrame``.

    La decision se toma por el contenido del archivo, no por la extension:
    se mira la cabecera de bytes para distinguir un XLSX (que es un ZIP y
    empieza por ``PK\\x03\\x04``) de un CSV; cualquier cosa que no encaje
    en ninguna de las dos categorias produce un
    ``ErrorDeCargaInesperado`` con un mensaje que el cliente puede leer.

    Args:
        ruta: ruta al archivo. Acepta ``str`` o ``pathlib.Path``.

    Returns:
        Un ``pandas.DataFrame`` con los datos del archivo. Las columnas
        se conservan tal cual llegan del archivo; la normalizacion de
        cabeceras es tarea de DC.2, no de este modulo.

    Raises:
        FileNotFoundError: si ``ruta`` no existe en disco.
        ErrorDeCargaInesperado: si el archivo existe pero no es CSV ni
            Excel. El mensaje explica que se espera y que compruebe la
            extension.
    """
    ruta = Path(ruta)

    with ruta.open("rb") as archivo:
        bytes_crudos = archivo.read()

    if _es_xlsx_por_contenido(bytes_crudos[:4]):
        return pd.read_excel(ruta, engine="openpyxl")

    # Si no parece XLSX, intentamos como CSV. ``read_csv`` detecta el
    # delimitador y la cabecera por si solo; lo que si necesita es una
    # codificacion. Si el archivo no es texto (por ejemplo, un PDF), la
    # primera lectura con utf-8 va a fallar, y con latin-1 va a
    # "funcionar" pero dando una tabla inutil. Para cerrar el Cierre 3
    # del item tenemos que detectar ese caso y lanzar nuestro error.
    try:
        tabla = _leer_csv_con_fallback(ruta)
    except UnicodeDecodeError:
        # Caso extremo: ni utf-8 ni latin-1 pudieron. No deberia ocurrir
        # porque latin-1 acepta cualquier byte, pero si el archivo es
        # binario no-CSV igual producimos algo y queremos que el caller
        # sepa que no es lo que esperaba.
        raise ErrorDeCargaInesperado(MENSAJE_NO_CSV_NI_EXCEL) from None

    # Heuristica: si "se leyo" como CSV pero el contenido tiene una
    # densidad alta de bytes de control (lo que pasaria si fuera un PDF,
    # un PNG renombrado, o cualquier binario), no es un CSV razonable
    # aunque latin-1 lo haya decodificado sin quejarse. Probamos el
    # contenido en latin-1, que es la red de seguridad, y contamos
    # cuantos bytes son de control (fuera de tab, LF y CR).
    total = len(bytes_crudos)
    if total > 0:
        bytes_control = sum(
            1 for b in bytes_crudos if b < 0x20 and b not in (0x09, 0x0A, 0x0D)
        )
        # Mas del 5% de bytes de control: no es texto, no es CSV.
        if bytes_control / total > 0.05:
            raise ErrorDeCargaInesperado(MENSAJE_NO_CSV_NI_EXCEL)

    return tabla