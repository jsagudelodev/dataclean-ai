"""Tests del item DC.13: endpoint HTTP que junta todo el pipeline.

Cierres:
    1) ``procesar_subida`` devuelve un reporte y un id; el id sirve
       para descargar el archivo limpio por ``descargar_por_id``.
    2) Un archivo corrupto o vacio levanta ``ErrorDeSubida`` con
       un motivo legible; un TestClient lo traduce a 400.
    3) El tamano maximo se configura (constructor y env
       ``DATACLEAN_MAX_BYTES``); pasarse del limite levanta
       ``ErrorDeSubida`` antes de tocar la tabla.

Regla 6 (fuerte): el modulo se importa DENTRO de cada test (vía
``_cargar_modulo_endpoint()``). Asi, si el modulo no existe, los
tests se recolectan, se ejecutan y caen con ``ModuleNotFoundError``
como **failed** -- no como error de collection, no como passed.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


def _cargar_modulo_endpoint():
    """Importa ``dataclean.endpoint`` DENTRO de cada test.

    Sin este wrapper, un ``from dataclean.endpoint import ...`` en
    el header del archivo convertiria la falta del modulo en un
    error de collection, y los 17 tests no contarian como fallidos
    (algunos harnesses muestran "0 failed" aunque la collection
    aborte). Con el wrapper, los tests SE EJECUTAN y cada uno cae
    con ``ModuleNotFoundError`` como **failed**, que es lo que la
    Regla 6 exige: "la suite sigue verde" deja de ser cierto.
    """
    return importlib.import_module("dataclean.endpoint")


def _csv_basico() -> bytes:
    return (
        "nombre,telefono,correo\n"
        "Ana Perez,3001234567,ana@ejemplo.com\n"
        "Luis Gomez,300 123 4568,luis@ejemplo.com\n"
    ).encode("utf-8")


def _xlsx_basico() -> bytes:
    """Genera un xlsx minimo en memoria con dos columnas."""
    import io

    import pandas as pd

    buffer = io.BytesIO()
    tabla = pd.DataFrame(
        {
            "nombre": ["Maria", "Juan"],
            "telefono": ["3001234567", "300 123 4568"],
        }
    )
    tabla.to_excel(buffer, index=False)
    return buffer.getvalue()


@pytest.fixture
def servicio(tmp_path: Path):
    """Devuelve una ``ServicioLimpieza`` resuelta en tiempo de test."""
    modulo = _cargar_modulo_endpoint()
    return modulo.ServicioLimpieza(carpeta_salida=tmp_path)


# ---------------------------------------------------------------------------
# Cierre 1: POST devuelve reporte + id para descargar
# ---------------------------------------------------------------------------


def test_modulo_endpoint_define_servicio_y_procesar() -> None:
    """El modulo expone la API publica minima del item."""
    modulo = _cargar_modulo_endpoint()
    assert hasattr(modulo, "ServicioLimpieza")
    assert hasattr(modulo, "procesar_subida")
    assert hasattr(modulo, "descargar_por_id")
    assert hasattr(modulo, "ErrorDeSubida")


def test_procesar_subida_devuelve_id_y_reporte(servicio) -> None:
    """Cierre 1: el resultado lleva id, reporte y tamano."""
    modulo = _cargar_modulo_endpoint()
    resultado = modulo.procesar_subida(
        _csv_basico(),
        nombre_archivo="clientes.csv",
        servicio=servicio,
    )
    assert isinstance(resultado, dict)
    assert isinstance(resultado["id"], str) and resultado["id"]
    assert isinstance(resultado["reporte"], dict)
    assert resultado["tamano"] > 0
    assert resultado["reporte"]["total_registros"] == 2


def test_id_generado_permite_descargar_archivo_limpio(servicio) -> None:
    """Cierre 1: el id funciona como puntero de descarga."""
    modulo = _cargar_modulo_endpoint()
    resultado = modulo.procesar_subida(
        _csv_basico(), nombre_archivo="c.csv", servicio=servicio
    )
    id_limpio = resultado["id"]
    assert servicio.existe(id_limpio) is True
    descarga = modulo.descargar_por_id(id_limpio, servicio=servicio)
    assert descarga is not None
    contenido, nombre = descarga
    assert nombre.endswith(".csv")
    # El CSV limpio conserva al menos una fila original (DC.11).
    assert b"Ana" in contenido or b"ana" in contenido.lower()


def test_reporte_incluye_cifras_de_telefono(servicio) -> None:
    """El reporte serializado incluye las cifras principales."""
    modulo = _cargar_modulo_endpoint()
    resultado = modulo.procesar_subida(
        _csv_basico(), nombre_archivo="c.csv", servicio=servicio
    )
    reporte = resultado["reporte"]
    assert reporte["telefonos_moviles"]["disponible"] is True
    assert reporte["telefonos_moviles"]["valor"] == 2


def test_soporta_archivo_xlsx(servicio) -> None:
    """El endpoint acepta tanto CSV como XLSX (DC.1 + DC.13)."""
    modulo = _cargar_modulo_endpoint()
    resultado = modulo.procesar_subida(
        _xlsx_basico(),
        nombre_archivo="datos.xlsx",
        servicio=servicio,
    )
    assert resultado["reporte"]["total_registros"] == 2
    assert servicio.existe(resultado["id"]) is True


def test_id_inexistente_devuelve_none(servicio) -> None:
    """Un id que no fue emitido no apunta a ningun archivo."""
    modulo = _cargar_modulo_endpoint()
    assert modulo.descargar_por_id("nope", servicio=servicio) is None


# ---------------------------------------------------------------------------
# Cierre 2: archivo vacio / corrupto no tumba el servicio
# ---------------------------------------------------------------------------


def test_archivo_vacio_devuelve_motivo_legible(servicio) -> None:
    """Cierre 2: bytes vacios -> ErrorDeSubida con motivo."""
    modulo = _cargar_modulo_endpoint()
    with pytest.raises(modulo.ErrorDeSubida) as excinfo:
        modulo.procesar_subida(
            b"", nombre_archivo="vacio.csv", servicio=servicio
        )
    motivo = excinfo.value.motivo
    assert motivo
    assert "vacio" in motivo.lower() or "vacío" in motivo


def test_archivo_corrupto_devuelve_motivo_legible(servicio) -> None:
    """Cierre 2: bytes aleatorios no son ni CSV ni XLSX -> ErrorDeSubida."""
    modulo = _cargar_modulo_endpoint()
    with pytest.raises(modulo.ErrorDeSubida) as excinfo:
        modulo.procesar_subida(
            b"\x00\x01\x02\x03no es un archivo valido\xff\xfe",
            nombre_archivo="basura.bin",
            servicio=servicio,
        )
    motivo = excinfo.value.motivo
    assert motivo
    # Regla 8: el motivo es legible, no un stacktrace.
    assert "Traceback" not in motivo


def test_error_no_deja_archivos_huerfanos(tmp_path: Path) -> None:
    """Cierre 2: si la carga falla, no se escribe el limpio."""
    modulo = _cargar_modulo_endpoint()
    servicio = modulo.ServicioLimpieza(carpeta_salida=tmp_path)
    with pytest.raises(modulo.ErrorDeSubida):
        modulo.procesar_subida(
            b"\x00\x01basura",
            nombre_archivo="x.csv",
            servicio=servicio,
        )
    assert list(tmp_path.glob("*.csv")) == []


def test_servicio_no_se_tumba_tras_error(servicio) -> None:
    """Cierre 2: tras un fallo, el servicio sigue aceptando peticiones."""
    modulo = _cargar_modulo_endpoint()
    with pytest.raises(modulo.ErrorDeSubida):
        modulo.procesar_subida(
            b"", nombre_archivo="v.csv", servicio=servicio
        )
    resultado = modulo.procesar_subida(
        _csv_basico(), nombre_archivo="ok.csv", servicio=servicio
    )
    assert resultado["reporte"]["total_registros"] == 2


# ---------------------------------------------------------------------------
# Cierre 3: tamano maximo configurable
# ---------------------------------------------------------------------------


def test_tamano_maximo_constructor(tmp_path: Path) -> None:
    """Cierre 3: el tamano maximo se pasa en el constructor."""
    modulo = _cargar_modulo_endpoint()
    servicio = modulo.ServicioLimpieza(
        carpeta_salida=tmp_path, tamano_maximo_bytes=10
    )
    with pytest.raises(modulo.ErrorDeSubida) as excinfo:
        modulo.procesar_subida(
            b"a" * 100, nombre_archivo="x.csv", servicio=servicio
        )
    assert "tamano" in excinfo.value.motivo.lower() or "tamaño" in excinfo.value.motivo


def test_tamano_maximo_lee_variable_de_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cierre 3: el operador puede sobreescribir el tamano por env."""
    monkeypatch.setenv("DATACLEAN_MAX_BYTES", "10")
    modulo = _cargar_modulo_endpoint()
    servicio = modulo.ServicioLimpieza(carpeta_salida=tmp_path)
    assert servicio.tamano_maximo_bytes == 10
    with pytest.raises(modulo.ErrorDeSubida):
        modulo.procesar_subida(
            b"a" * 100, nombre_archivo="x.csv", servicio=servicio
        )


def test_tamano_maximo_invalido_en_constructor() -> None:
    """Cierre 3: un tamano <= 0 en el constructor es un error de uso."""
    modulo = _cargar_modulo_endpoint()
    with pytest.raises(ValueError):
        modulo.ServicioLimpieza(tamano_maximo_bytes=0)


# ---------------------------------------------------------------------------
# Regla 6 fuerte: comportamiento, no solo firma
# ---------------------------------------------------------------------------


def test_regla6_fuerte_resultado_incluye_cifras_reales(servicio) -> None:
    """Las cifras tienen que venir del pipeline, no ser un placeholder."""
    modulo = _cargar_modulo_endpoint()
    resultado = modulo.procesar_subida(
        _csv_basico(), nombre_archivo="c.csv", servicio=servicio
    )
    moviles = resultado["reporte"]["telefonos_moviles"]
    assert moviles["disponible"] is True
    assert moviles["valor"] == 2
    descarga = modulo.descargar_por_id(resultado["id"], servicio=servicio)
    assert descarga is not None
    contenido, _ = descarga
    assert len(contenido) > 0
    assert b"nombre" in contenido.lower()


def test_regla6_fuerte_id_es_efimeramente_unico(servicio) -> None:
    """Dos subidas seguidas reciben ids distintos."""
    modulo = _cargar_modulo_endpoint()
    r1 = modulo.procesar_subida(
        _csv_basico(), nombre_archivo="a.csv", servicio=servicio
    )
    r2 = modulo.procesar_subida(
        _csv_basico(), nombre_archivo="b.csv", servicio=servicio
    )
    assert r1["id"] != r2["id"]
    assert servicio.existe(r1["id"]) is True
    assert servicio.existe(r2["id"]) is True


def test_regla6_fuerte_motivo_no_es_stacktrace(servicio) -> None:
    """Regla 8: el motivo de un fallo NO contiene un Traceback de Python."""
    modulo = _cargar_modulo_endpoint()
    with pytest.raises(modulo.ErrorDeSubida) as excinfo:
        modulo.procesar_subida(
            b"\x00\x01basura", nombre_archivo="m.csv", servicio=servicio
        )
    motivo = excinfo.value.motivo
    assert "Traceback (most recent call last)" not in motivo
    assert 'File "' not in motivo
    assert len(motivo) > 5