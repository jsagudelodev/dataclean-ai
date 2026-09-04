"""DataClean AI — limpieza y reporte de listas de contactos."""

from dataclean.carga import ErrorDeCargaInesperado, cargar_tabla
from dataclean.cargo import (
    SeparadorFalso,
    SeparadorNombreCargo,
    SeparadorPorPrefijo,
    separar_nombre_y_cargo,
)
from dataclean.clasificacion import RolColumna, clasificar_columnas
from dataclean.correo import (
    validar_columna_correo,
    validar_correo,
)
from dataclean.duplicados import (
    detectar_duplicados_por_nombre,
    detectar_duplicados_por_telefono,
)
from dataclean.exportar import ErrorDeExportacion, exportar_tabla
from dataclean.nombre import (
    normalizar_columna_nombre,
    normalizar_nombre,
)
from dataclean.reporte import (
    Cifra,
    GrupoDuplicados,
    Reporte,
    generar_reporte,
)
from dataclean.telefono import (
    TIPO_FIJO,
    TIPO_INVALIDO,
    TIPO_MOVIL,
    clasificar_columna_telefono,
    clasificar_telefono,
    normalizar_columna_telefono,
    normalizar_telefono,
)

__version__ = "0.1.0"

__all__ = [
    "cargar_tabla",
    "ErrorDeCargaInesperado",
    "clasificar_columnas",
    "RolColumna",
    "normalizar_telefono",
    "normalizar_columna_telefono",
    "clasificar_telefono",
    "clasificar_columna_telefono",
    "TIPO_MOVIL",
    "TIPO_FIJO",
    "TIPO_INVALIDO",
    "validar_correo",
    "validar_columna_correo",
    "separar_nombre_y_cargo",
    "SeparadorNombreCargo",
    "SeparadorFalso",
    "SeparadorPorPrefijo",
    "detectar_duplicados_por_telefono",
    "exportar_tabla",
    "ErrorDeExportacion",
    "generar_reporte",
    "Cifra",
    "GrupoDuplicados",
    "Reporte",
]