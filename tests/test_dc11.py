"""Cierre de DC.11: ``exportar_tabla``.

Tres contratos del item:
  1) **Cierre 1** -- se exporta a CSV y a XLSX, y al releerlos con
     ``cargar_tabla`` los valores coinciden exactamente con los de la
     tabla entregada.
  2) **Cierre 2** -- las columnas originales conviven en el archivo
     con las normalizadas. El cliente tiene que poder comparar la
     columna ``telefono`` (lo que escribio) con
     ``telefono_normalizado`` (lo que el sistema entendio) en una
     misma hoja.
  3) **Cierre 3** -- el CSV abre bien en Excel en espanol: separador
     ``;`` y codificacion ``utf-8-sig`` (BOM). Esto se demuestra
     mirando los bytes crudos: el archivo lleva BOM y cada linea
     termina con un ``;`` antes del salto.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dataclean import (
    ErrorDeExportacion,
    cargar_tabla,
    clasificar_columna_telefono,
    detectar_duplicados_por_telefono,
    exportar_tabla,
    normalizar_columna_telefono,
    validar_columna_correo,
)
# Importamos el modulo fuente: si alguien borra ``exportar.py`` pero
# deja un reexport de pega en ``__init__``, los tests siguen rojos.
from dataclean import exportar as exportar_modulo


# --- Datos de prueba -----------------------------------------------------


# Misma tabla "de produccion" que usa test_dc10.py: 6 filas con un
# duplicado por telefono (Ana + Beto), un fijo, un invalido y un correo
# marcado. Es la tabla minima que ejercita TODO el pipeline (DC.3 +
# DC.4 + DC.5 + DC.8) en una sola corrida: cualquier corte de
# columna se ve a la primera.
FILAS = [
    {
        "nombre": "Ana Garcia",
        "telefono": "3001234567",
        "correo": "ana@example.com",
    },
    {
        "nombre": "Beto Lopez",
        "telefono": "+57 300 1234567",
        "correo": "con espacio@example.com",
    },
    {
        "nombre": "Cris Diaz",
        "telefono": "6011234567",
        "correo": "cris@example.com",
    },
    {
        "nombre": "Dani Ruiz",
        "telefono": "12345",
        "correo": "sin@dominio",
    },
    {
        "nombre": "Eli Mora",
        "telefono": "3112223333",
        "correo": "eli@example.com",
    },
    {
        "nombre": "Fer Soto",
        "telefono": "",
        "correo": "f@x",
    },
]
COLUMNAS = ["nombre", "telefono", "correo"]


def _tabla_pasada_por_todo_el_pipeline() -> pd.DataFrame:
    """Aplica DC.3 + DC.4 + DC.5 + DC.8 sobre la tabla de prueba.

    DC.11 NO transforma: escribe lo que el caller le pase. Para que
    el test del Cierre 2 tenga sentido, primero tenemos que tener una
    tabla con columnas originales + auxiliares. Este helper es ese
    montaje.
    """
    tabla = pd.DataFrame(FILAS, columns=COLUMNAS)
    tabla = normalizar_columna_telefono(tabla, "telefono")
    tabla = clasificar_columna_telefono(tabla, "telefono")
    tabla = validar_columna_correo(tabla, "correo")
    tabla = detectar_duplicados_por_telefono(tabla, "telefono")
    return tabla


# --- Cierre 1: relectura tras exportar ----------------------------------


def _comparable(tabla: pd.DataFrame) -> list[dict[str, str]]:
    """Convierte una tabla a una lista de dicts comparables como strings.

    Al reparsear un archivo (CSV o XLSX) pandas puede reinterpretar
    los tipos: vacios como ``NaN``, una columna de numeros puros
    como ``float`` (3001234567.0 en vez de "3001234567"), un booleano
    como ``True``. Para comparar contenido, no tipos, proyectamos
    todo a string y vaciamos los NaN; ademas, ``"3001234567.0"`` se
    normaliza a ``"3001234567"`` para no penalizar la perdida de
    tipo numerico.
    """
    def _a_texto(valor: object) -> str:
        if pd.isna(valor):
            return ""
        if isinstance(valor, bool):
            return "True" if valor else "False"
        if isinstance(valor, float):
            # Si el float es entero (3001234567.0), mostramos la
            # parte entera: no penalizamos la perdida de tipo
            # numerico al reparsear.
            if valor.is_integer():
                return str(int(valor))
            return str(valor)
        return str(valor)

    return [
        {k: _a_texto(v) for k, v in fila.items()}
        for fila in tabla.to_dict(orient="records")
    ]


def test_exportar_y_releer_csv_coincide_exactamente(tmp_path) -> None:
    """Tras exportar a CSV y releer con ``cargar_tabla``, todo coincide."""
    tabla = _tabla_pasada_por_todo_el_pipeline()
    ruta = tmp_path / "contactos_limpios.csv"

    exportar_tabla(tabla, ruta)
    recargada = cargar_tabla(ruta)

    # Mismas columnas, en el mismo orden.
    assert list(recargada.columns) == list(tabla.columns)
    # Mismas formas, mismas filas, mismos valores fila a fila.
    assert recargada.shape == tabla.shape
    # En CSV los tipos se conservan: igualdad estricta, contenido
    # comparable.
    assert _comparable(recargada) == _comparable(tabla)


def test_exportar_y_releer_xlsx_coincide_exactamente(tmp_path) -> None:
    """Tras exportar a XLSX y releer con ``cargar_tabla``, todo coincide."""
    tabla = _tabla_pasada_por_todo_el_pipeline()
    ruta = tmp_path / "contactos_limpios.xlsx"

    exportar_tabla(tabla, ruta)
    recargada = cargar_tabla(ruta)

    assert list(recargada.columns) == list(tabla.columns)
    assert recargada.shape == tabla.shape
    # XLSX reinterpreta vacios como NaN y numeros como float:
    # comparamos el contenido como string.
    assert _comparable(recargada) == _comparable(tabla)


def test_exportar_devuelve_la_ruta_para_encadenar(tmp_path) -> None:
    """``exportar_tabla`` devuelve la ``Path`` que escribio."""
    tabla = pd.DataFrame(FILAS, columns=COLUMNAS)
    ruta = tmp_path / "salida.csv"

    resultado = exportar_tabla(tabla, ruta)

    assert resultado == ruta
    assert ruta.exists()


# --- Cierre 2: columnas originales + normalizadas conviven -------------


def test_columnas_originales_y_normalizadas_coexisten_en_csv(tmp_path) -> None:
    """``telefono`` y ``telefono_normalizado`` estan las dos en el CSV."""
    tabla = _tabla_pasada_por_todo_el_pipeline()
    ruta = tmp_path / "comparar.csv"

    exportar_tabla(tabla, ruta)
    recargada = cargar_tabla(ruta)

    # La columna original (lo que el cliente escribio) sigue ahi.
    assert "telefono" in recargada.columns
    # La normalizada (lo que el sistema entendio) tambien.
    assert "telefono_normalizado" in recargada.columns
    # Y de DC.4 / DC.5 / DC.8.
    assert "telefono_tipo" in recargada.columns
    assert "correo" in recargada.columns
    assert "correo_motivo" in recargada.columns
    assert "grupo_id" in recargada.columns
    # El cliente puede comparar las dos columnas fila a fila.
    for i, fila in recargada.iterrows():
        original = fila["telefono"]
        normalizado = fila["telefono_normalizado"]
        # Si el original estaba vacio, el normalizado tambien (DC.3).
        if pd.isna(original) or str(original).strip() == "":
            assert pd.isna(normalizado) or str(normalizado).strip() == ""


def test_columnas_originales_y_normalizadas_coexisten_en_xlsx(tmp_path) -> None:
    """Misma garantia para XLSX."""
    tabla = _tabla_pasada_por_todo_el_pipeline()
    ruta = tmp_path / "comparar.xlsx"

    exportar_tabla(tabla, ruta)
    recargada = cargar_tabla(ruta)

    assert "telefono" in recargada.columns
    assert "telefono_normalizado" in recargada.columns
    assert "telefono_tipo" in recargada.columns
    assert "grupo_id" in recargada.columns


def test_orden_de_columnas_se_conserva(tmp_path) -> None:
    """El orden de columnas con el que el caller llamo es el orden del archivo."""
    tabla = _tabla_pasada_por_todo_el_pipeline()
    ruta = tmp_path / "orden.csv"

    exportar_tabla(tabla, ruta)
    recargada = cargar_tabla(ruta)

    # La primera columna tiene que seguir siendo la primera.
    assert recargada.columns[0] == tabla.columns[0]
    # Y la lista completa, en el mismo orden, tiene que sobrevivir.
    assert list(recargada.columns) == list(tabla.columns)


# --- Cierre 3: el CSV abre bien en Excel en espanol ---------------------


def test_csv_tiene_bom_para_que_excel_es_reconozca_acentos(tmp_path) -> None:
    """El CSV arranca con la marca BOM (EF BB BF) de utf-8-sig."""
    tabla = pd.DataFrame(FILAS, columns=COLUMNAS)
    ruta = tmp_path / "acentos.csv"

    exportar_tabla(tabla, ruta)
    bytes_iniciales = ruta.read_bytes()[:3]

    assert bytes_iniciales == b"\xef\xbb\xbf"


def test_csv_usa_separador_punto_y_coma(tmp_path) -> None:
    """El separador de campos es ``;`` (lo que espera Excel en espanol).

    Lo demostramos mirando los bytes: las lineas tienen que contener
    ``;`` entre campos. Si el archivo usara ``,`` (el default de
    pandas) este assert caeria.
    """
    tabla = pd.DataFrame(FILAS, columns=COLUMNAS)
    ruta = tmp_path / "separador.csv"

    exportar_tabla(tabla, ruta)
    contenido = ruta.read_text(encoding="utf-8-sig")
    primera_linea = contenido.splitlines()[0]

    # Cabecera: tiene que haber un ';' entre "nombre" y "telefono".
    assert primera_linea == "nombre;telefono;correo"
    # Y la primera fila de datos tambien: el ";" tiene que estar donde
    # va, no como un caracter suelto.
    segunda_linea = contenido.splitlines()[1]
    assert segunda_linea == "Ana Garcia;3001234567;ana@example.com"


def test_csv_con_tildes_y_enhe_se_releen_sin_romperse(tmp_path) -> None:
    """Tildes y enhe llegan al Excel en espanol intactas tras la relectura.

    DC.1 ya cubre latin-1 al leer; DC.11 cierra el camino inverso:
    exportamos con utf-8-sig y al releer (que ``cargar_tabla`` hara
    tambien con utf-8-sig primero), las tildes se conservan.
    """
    filas = [
        {
            "nombre": "Maria Nunez",
            "telefono": "3001234567",
            "correo": "maria@example.com",
        },
        {
            "nombre": "Jose Perez",
            "telefono": "3107654321",
            "correo": "jose@example.com",
        },
    ]
    tabla = pd.DataFrame(filas)
    ruta = tmp_path / "tildes.csv"

    exportar_tabla(tabla, ruta)
    recargada = cargar_tabla(ruta)

    # Las tildes que estaban en la tabla siguen en la tabla recargada.
    assert recargada.loc[0, "nombre"] == "Maria Nunez"
    assert recargada.loc[1, "nombre"] == "Jose Perez"


# --- Errores legibles (regla 8) ------------------------------------------


def test_extension_no_reconocida_lanza_error_legible(tmp_path) -> None:
    """Una extension rara da un motivo comprensible, no un traceback."""
    tabla = pd.DataFrame(FILAS, columns=COLUMNAS)
    ruta_rara = tmp_path / "salida.txt"

    with pytest.raises(ErrorDeExportacion) as info:
        exportar_tabla(tabla, ruta_rara)

    # El motivo menciona .csv y .xlsx para que el cliente sepa que
    # hacer. No contiene un telefono, un nombre ni un correo (regla 9).
    mensaje = str(info.value).lower()
    assert ".csv" in mensaje
    assert ".xlsx" in mensaje
    assert "ana" not in mensaje
    assert "3001234567" not in mensaje


# --- El modulo expone lo que el caller necesita --------------------------


def test_modulo_exportar_define_las_funciones_publicas() -> None:
    """El modulo expone ``exportar_tabla`` y ``ErrorDeExportacion``."""
    assert callable(exportar_modulo.exportar_tabla)
    assert callable(exportar_modulo.ErrorDeExportacion)


def test_dataclean_reexporta_exportar_tabla() -> None:
    """El paquete raiz reexporta la funcion de DC.11."""
    from dataclean import ErrorDeExportacion as ErrorReexportado
    from dataclean import exportar_tabla as exportar_reexportada

    assert exportar_reexportada is exportar_modulo.exportar_tabla
    assert ErrorReexportado is exportar_modulo.ErrorDeExportacion