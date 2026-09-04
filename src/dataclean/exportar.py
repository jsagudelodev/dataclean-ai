"""Exportacion del archivo limpio (DC.11).

Por que existe este modulo:
    "Lo que se vende no es el archivo limpio: es el reporte" (regla 1
    del ENCARGO), pero el archivo limpio SI se entrega: es la otra mitad
    del producto. Este modulo toma la tabla que el caller ya paso por
    las normalizaciones de los items anteriores y la escribe a disco
    en CSV o XLSX, conservando las columnas originales junto a las
    auxiliares (DC.3, DC.4, DC.5, DC.8) para que el cliente pueda
    comparar visualmente.

Tres contratos del item (Cierres):
    1) **Cierre 1** -- se exporta a CSV y a Excel, y al releerlos los
       valores coinciden exactamente con los de la tabla entregada.
    2) **Cierre 2** -- las columnas originales se conservan junto a
       las normalizadas: ``telefono`` convive con
       ``telefono_normalizado`` y ``telefono_tipo`` en el mismo
       archivo, en el mismo orden que el caller las paso.
    3) **Cierre 3** -- el CSV abre bien en un Excel en espanol:
       separador ``;`` y codificacion ``utf-8-sig`` (con BOM) para
       que el Excel-ES reconozca acentos y la "e�ne" sin pedir
       importacion.

Diseno y decisiones (las apunto en la bitacora):
    * **Una sola funcion publica, ``exportar_tabla``**, que detecta
      el formato por la extension de la ruta. Mismo patron que DC.1
      (``cargar_tabla``). El caller no aprende dos APIs.
    * **CSV con ``;`` y BOM.** El Excel en espanol espera ``;`` como
      separador (regionalizacion es-ES) y UTF-8 con BOM para abrir
      acentos bien a la primera sin pedir al usuario que elija
      codificacion. Pandas sabe hacer las dos cosas con
      ``sep=";"`` + ``encoding="utf-8-sig"``: no hace falta un
      escritor custom.
    * **No se muta la tabla.** DC.11 es un sologuarda, no una
      transformacion: escribe lo que el caller ya decidio.
    * **Regla 9.** Ningun motivo contiene un telefono, un nombre ni
      un correo en claro. Si la ruta no tiene una extension
      reconocida, el motivo dice "usa la extension .csv o .xlsx" y
      nada mas.
    * **Regla 8.** Si la escritura falla, se lanza una excepcion
      propia (``ErrorDeExportacion``, ValueError) con un mensaje
      legible -- nunca un traceback al cliente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


# --- Constantes -----------------------------------------------------------

# Separador que espera Excel en espanol (regionalizacion es-ES). Sin esto,
# el cliente ve todo el contenido de cada fila en una sola columna y
# piensa que el archivo esta roto.
SEPARADOR_CSV: Final[str] = ";"

# UTF-8 con BOM: Excel en espanol abre acentos y "e�ne" a la primera,
# sin pedir al usuario que elija codificacion. Es el mismo truco que
# aplica DC.1 al leer.
CODIFICACION_CSV: Final[str] = "utf-8-sig"

# Mensajes legibles para el caller / el usuario final (regla 8 del ENCARGO).
MENSAJE_EXTENSION_NO_RECONOCIDA: Final[str] = (
    "La ruta no tiene una extension reconocida: "
    "usa un archivo terminado en .csv o .xlsx para exportar."
)
MENSAJE_NO_SE_PUDO_ESCRIBIR: Final[str] = (
    "No se pudo escribir el archivo de salida. "
    "Comprueba que la carpeta exista y que tengas permisos de escritura."
)


# --- Excepcion publica ----------------------------------------------------


class ErrorDeExportacion(ValueError):
    """Se lanza cuando una tabla no se puede exportar.

    Es un ``ValueError`` (no ``RuntimeError``) porque el fallo es de
    los argumentos que nos pasan, no del estado interno. Asi, el
    caller puede hacer ``except ValueError`` si quiere tratar
    uniformemente los argumentos invalidos del pipeline.
    """


# --- Implementacion -------------------------------------------------------


def _extension_de(ruta: Path) -> str:
    """Devuelve la extension en minusculas, sin el punto.

    ``.CSV`` y ``.csv`` son lo mismo para este modulo.
    """
    return ruta.suffix.lower().lstrip(".")


def _escribir_csv(tabla: pd.DataFrame, ruta: Path) -> None:
    """Escribe la tabla como CSV separado por ``;`` con BOM UTF-8.

    Usa ``sep=SEPARADOR_CSV`` y ``encoding=CODIFICACION_CSV`` para que
    Excel en espanol lo abra sin pedir nada. Pandas escribe el BOM
    automaticamente con ``utf-8-sig``.

    ``float_format=str`` evita que ``3001234567`` se escriba como
    ``3001234567.0``: la columna canonica de DC.3 es texto y debe
    volver como texto. Si la dejara como float, el cliente veria
    el numero con un ``.0`` colgado al releer el archivo.
    """
    tabla.to_csv(
        ruta,
        sep=SEPARADOR_CSV,
        encoding=CODIFICACION_CSV,
        index=False,
        float_format=str,
    )


def _escribir_xlsx(tabla: pd.DataFrame, ruta: Path) -> None:
    """Escribe la tabla como XLSX usando openpyxl."""
    tabla.to_excel(ruta, index=False, engine="openpyxl")


def exportar_tabla(
    tabla: pd.DataFrame,
    ruta: str | Path,
) -> Path:
    """Exporta una tabla de contactos a CSV o XLSX.

    El formato se elige por la extension de la ruta:
      * ``.csv``  -> CSV con separador ``;`` y codificacion ``utf-8-sig``
        (abre bien en Excel en espanol sin pedir importacion).
      * ``.xlsx`` -> Excel con openpyxl.

    La tabla NO se modifica: se escribe tal cual la dio el caller, con
    todas sus columnas en el orden original. Esto cierra el Cierre 2:
    si el caller ya paso la tabla por ``normalizar_columna_telefono``
    (DC.3), ``clasificar_columna_telefono`` (DC.4),
    ``validar_columna_correo`` (DC.5) y
    ``detectar_duplicados_por_telefono`` (DC.8), las columnas
    originales (``telefono``, ``correo``) conviven en el archivo con
    las auxiliares (``telefono_normalizado``, ``telefono_tipo``,
    ``telefono_marcado``, ``correo_motivo``, ``grupo_id``,
    ``grupo_canonico``...). El cliente puede comparar columna a
    columna.

    Args:
        tabla: la tabla a exportar. No se muta.
        ruta: ruta del archivo de salida. Tiene que terminar en
            ``.csv`` o ``.xlsx``.

    Returns:
        La misma ``Path`` que se paso, por si el caller quiere
        encadenar (p. ej. moverla a otra carpeta).

    Raises:
        ErrorDeExportacion: si la extension no es ``.csv`` ni
            ``.xlsx`` o si la escritura falla por permisos / disco.
    """
    ruta_destino = Path(ruta)
    extension = _extension_de(ruta_destino)

    try:
        if extension == "csv":
            _escribir_csv(tabla, ruta_destino)
        elif extension == "xlsx":
            _escribir_xlsx(tabla, ruta_destino)
        else:
            raise ErrorDeExportacion(MENSAJE_EXTENSION_NO_RECONOCIDA)
    except ErrorDeExportacion:
        # Re-emitir tal cual: ya tiene el motivo legible.
        raise
    except OSError as error:
        # Regla 8: el cliente nunca ve un traceback ni un error tecnico.
        raise ErrorDeExportacion(MENSAJE_NO_SE_PUDO_ESCRIBIR) from error

    return ruta_destino