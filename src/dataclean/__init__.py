"""DataClean AI — limpieza y reporte de listas de contactos."""

from dataclean.carga import ErrorDeCargaInesperado, cargar_tabla
from dataclean.clasificacion import RolColumna, clasificar_columnas
from dataclean.telefono import normalizar_columna_telefono, normalizar_telefono

__version__ = "0.1.0"

__all__ = [
    "cargar_tabla",
    "ErrorDeCargaInesperado",
    "clasificar_columnas",
    "RolColumna",
    "normalizar_telefono",
    "normalizar_columna_telefono",
]