"""Tests del item DC.18: conectar el cargo y las columnas de telefono ignoradas.

DC.7 (separar cargo) y DC.3/DC.4 (normalizar y clasificar telefonos) ya
estaban construidos y probados, pero el endpoint no los usaba del todo:

  * el cargo pegado al nombre (``MARIA GOMEZ - GERENTE``) nunca se
    separaba, el cliente lo recibia entero;
  * de varias columnas de telefono (``telefono``, ``Cel``, ``movil 2``)
    solo se procesaba la primera; las demas se perdian.

Cierres:
    1) una subida con ``MARIA GOMEZ - GERENTE`` devuelve nombre y cargo
       en campos separados, y sin LLM disponible sigue respondiendo sin
       fallar (DC.7 Cierre 3);
    2) una tabla con tres columnas de telefono se normaliza y clasifica
       en las tres, y las cifras del reporte las cuentan todas;
    3) el caso de una sola columna no cambia de comportamiento.

Regla 6 (fuerte): los modulos se importan DENTRO de cada test.
Regla 10: los tests nuevos van en archivo propio.
"""

from __future__ import annotations

import importlib
import io
from pathlib import Path


def _modulo(nombre: str):
    return importlib.import_module(f"dataclean.{nombre}")


def _tabla_del_limpio(servicio, id_limpieza: str):
    """Lee el CSV limpio que el servicio dejo en disco como DataFrame."""
    import pandas as pd

    endpoint = _modulo("endpoint")
    contenido, _ = endpoint.descargar_por_id(id_limpieza, servicio=servicio, formato="csv")
    # El limpio se exporta para Excel en espanol: separador ';' y utf-8-sig.
    return pd.read_csv(io.BytesIO(contenido), dtype=str, sep=";", encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Cierre 1: el cargo pegado al nombre se separa
# ---------------------------------------------------------------------------


def test_endpoint_separa_el_cargo_del_nombre(tmp_path: Path) -> None:
    endpoint = _modulo("endpoint")
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path)
    csv = (
        "nombre,telefono\n"
        "MARIA GOMEZ - GERENTE,3001234567\n"
        "Pedro Ruiz (Contador),3009998877\n"
    ).encode("utf-8")

    resultado = endpoint.procesar_subida(csv, "c.csv", servicio=servicio)
    tabla = _tabla_del_limpio(servicio, resultado["id"])

    assert "nombre_cargo" in tabla.columns
    assert "nombre_sin_cargo" in tabla.columns
    cargos = list(tabla["nombre_cargo"])
    sin_cargo = list(tabla["nombre_sin_cargo"])
    assert cargos == ["GERENTE", "CONTADOR"]
    assert sin_cargo == ["MARIA GOMEZ", "Pedro Ruiz"]


def test_separar_columna_sin_llm_conserva_el_campo(tmp_path: Path) -> None:
    # DC.7 Cierre 3: sin separador (sin LLM disponible) el sistema no
    # falla; conserva el nombre entero y deja el cargo sin separar.
    import pandas as pd

    cargo = _modulo("cargo")
    tabla = pd.DataFrame({"nombre": ["MARIA GOMEZ - GERENTE", "Ana Lopez"]})

    resultado = cargo.separar_columna_nombre_cargo(tabla, "nombre", separador=None)

    assert list(resultado["nombre_cargo"]) == [None, None]
    assert list(resultado["nombre_sin_cargo"]) == [
        "MARIA GOMEZ - GERENTE",
        "Ana Lopez",
    ]


# ---------------------------------------------------------------------------
# Cierre 2: las tres columnas de telefono se cuentan
# ---------------------------------------------------------------------------


def test_reporte_cuenta_las_tres_columnas_de_telefono(tmp_path: Path) -> None:
    endpoint = _modulo("endpoint")
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path)
    # Una fila con tres columnas de telefono: movil en 'telefono', fijo en
    # 'Cel' (10 digitos que no empiezan por 3) y movil en 'movil 2'.
    csv = (
        "nombre,telefono,Cel,movil 2\n"
        "Ana Lopez,3001112233,6012345678,3009998877\n"
    ).encode("utf-8")

    resultado = endpoint.procesar_subida(csv, "c.csv", servicio=servicio)
    reporte = resultado["reporte"]

    # Si el pipeline procesara solo la primera columna, seria 1 movil,
    # 0 fijos y 1 normalizado. Con las tres: 2 moviles, 1 fijo, 3 normalizados.
    assert reporte["telefonos_normalizados"]["valor"] == 3
    assert reporte["telefonos_moviles"]["valor"] == 2
    assert reporte["telefonos_fijos"]["valor"] == 1

    # Las tres columnas quedan normalizadas y clasificadas en el limpio.
    tabla = _tabla_del_limpio(servicio, resultado["id"])
    for columna in ("telefono", "Cel", "movil 2"):
        assert f"{columna}_normalizado" in tabla.columns
        assert f"{columna}_tipo" in tabla.columns


# ---------------------------------------------------------------------------
# Cierre 3: una sola columna no cambia de comportamiento
# ---------------------------------------------------------------------------


def test_una_sola_columna_de_telefono_no_cambia(tmp_path: Path) -> None:
    endpoint = _modulo("endpoint")
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path)
    csv = (
        "nombre,telefono\n"
        "Ana Lopez,3001112233\n"
        "Luis Soto,6012345678\n"
        "Eva Paz,123\n"
    ).encode("utf-8")

    reporte = endpoint.procesar_subida(csv, "c.csv", servicio=servicio)["reporte"]

    # Con una sola columna: valor == numero de filas que aportan (no se
    # inflan las cifras). 2 normalizados (el '123' no), 1 movil, 1 fijo,
    # 1 invalido.
    assert reporte["telefonos_normalizados"]["valor"] == 2
    assert reporte["telefonos_moviles"]["valor"] == 1
    assert reporte["telefonos_fijos"]["valor"] == 1
    assert reporte["telefonos_invalidos"]["valor"] == 1
    # El rastreo sigue siendo una fila por cuenta (valor == len(filas)).
    assert reporte["telefonos_moviles"]["filas"] == [0]
    assert reporte["telefonos_fijos"]["filas"] == [1]
