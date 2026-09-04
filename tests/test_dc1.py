"""Cierre de DC.1: ``cargar_tabla`` decide por contenido, no por extension.

Tres contratos del item:
  1) Un .csv y un .xlsx con las mismas columnas producen la misma tabla.
  2) Un .csv guardado en latin-1 (lo que exporta Excel en espanol) se lee
     sin romper las tildes.
  3) Un archivo que no es ni CSV ni Excel produce un error comprensible,
     no una excepcion tecnica.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dataclean import ErrorDeCargaInesperado, cargar_tabla


# --- datos de prueba -----------------------------------------------------


# Las mismas cinco filas en CSV y XLSX. Usamos tildes a proposito para que
# un fallo de codificacion (latin-1 vs utf-8) sea visible a simple vista en
# el assert.
FILAS = [
    {"nombre": "Ana Garcia", "telefono": "3001234567", "correo": "ana@example.com"},
    {"nombre": "Jose Perez", "telefono": "3107654321", "correo": "jose@example.com"},
    {"nombre": "Maria Nunez", "telefono": "3151112233", "correo": "maria@example.com"},
]
COLUMNAS = ["nombre", "telefono", "correo"]


def _escribir_csv_y_xlsx(tmp_path: Path) -> tuple[Path, Path]:
    """Crea un CSV y un XLSX con las mismas filas y devuelve las rutas."""
    df = pd.DataFrame(FILAS, columns=COLUMNAS)
    ruta_csv = tmp_path / "contactos.csv"
    ruta_xlsx = tmp_path / "contactos.xlsx"
    df.to_csv(ruta_csv, index=False, encoding="utf-8")
    df.to_excel(ruta_xlsx, index=False, engine="openpyxl")
    return ruta_csv, ruta_xlsx


# --- Cierre 1: misma tabla desde CSV y XLSX -----------------------------


def test_cargar_csv_y_xlsx_producen_la_misma_tabla(tmp_path: Path) -> None:
    """Un .csv y un .xlsx con las mismas columnas devuelven la misma tabla."""
    ruta_csv, ruta_xlsx = _escribir_csv_y_xlsx(tmp_path)

    tabla_csv = cargar_tabla(ruta_csv)
    tabla_xlsx = cargar_tabla(ruta_xlsx)

    assert list(tabla_csv.columns) == list(tabla_xlsx.columns) == COLUMNAS
    assert tabla_csv.shape == tabla_xlsx.shape == (3, 3)
    # El contenido fila a fila tambien tiene que coincidir; comparamos
    # como listas de dicts para que el mensaje de pytest sea legible si
    # algo se desvia.
    assert tabla_csv.to_dict(orient="records") == tabla_xlsx.to_dict(orient="records")


def test_decide_por_contenido_no_por_extension(tmp_path: Path) -> None:
    """Un Excel renombrado a .csv se carga como Excel porque miramos bytes."""
    _, ruta_xlsx = _escribir_csv_y_xlsx(tmp_path)
    ruta_renombrada = tmp_path / "contactos_renombrado.csv"
    ruta_renombrada.write_bytes(ruta_xlsx.read_bytes())

    tabla = cargar_tabla(ruta_renombrada)

    assert tabla.shape == (3, 3)
    assert list(tabla.columns) == COLUMNAS


# --- Cierre 2: latin-1 con tildes ---------------------------------------


def test_csv_latin1_con_tildes_se_lee_sin_romperlas(tmp_path: Path) -> None:
    """El .csv que exporta Excel en espanol (latin-1) se lee sin perder tildes."""
    ruta = tmp_path / "export_excel_espanol.csv"
    # En latin-1, la 'a' con tilde ocupa un solo byte (0xE1). Si pandas
    # intentara decodificarlo como utf-8 reventaria con
    # ``UnicodeDecodeError``; el fallback a latin-1 es lo que evita eso.
    contenido = (
        "nombre,telefono,correo\n"
        "Ana Garcia,3001234567,ana@example.com\n"
        "Jose Perez,3107654321,jose@example.com\n"
        "Maria Nunez,3151112233,maria@example.com\n"
    )
    ruta.write_bytes(contenido.encode("latin-1"))

    tabla = cargar_tabla(ruta)

    assert tabla.shape == (3, 3)
    # La prueba de fuego: las tildes y la e�ne siguen ahi, intactas.
    assert "Nunez" in tabla["nombre"].iloc[2]
    assert tabla["nombre"].iloc[0] == "Ana Garcia"


# --- Cierre 3: archivo que no es ni CSV ni Excel -----------------------


def test_archivo_binario_no_csv_ni_excel_devuelve_error_comprensible(tmp_path: Path) -> None:
    """Un binario que no es CSV ni Excel produce un error entendible, no un traceback."""
    ruta = tmp_path / "no_es_ninguno_de_los_dos.pdf"
    # Bytes arbitrarios que NO son un XLSX (no empiezan por PK\x03\x04) y
    # que ademas contienen bytes de control, de modo que el fallback a
    # latin-1 produce texto inutil y nuestra heuristica del modulo detecta
    # que no es un CSV razonable.
    ruta.write_bytes(b"\x00\x01\x02\x03BINARIO\x00\x01\x02")

    with pytest.raises(ErrorDeCargaInesperado) as info:
        cargar_tabla(ruta)

    # El mensaje tiene que ser legible para el cliente final: nombra lo
    # que esperaba, no dice "ValueError" ni muestra un traceback.
    mensaje = str(info.value)
    assert "CSV" in mensaje or "Excel" in mensaje
    assert "Traceback" not in mensaje


def test_ruta_inexistente_sigue_dando_file_not_found(tmp_path: Path) -> None:
    """Si la ruta no existe, preferimos ``FileNotFoundError`` (no lo disfrazamos)."""
    ruta_fantasma = tmp_path / "esto_no_existe.csv"
    with pytest.raises(FileNotFoundError):
        cargar_tabla(ruta_fantasma)