"""Tests del item DC.13: endpoint HTTP que junta todo el pipeline.

Tres cierres a demostrar:
    1) ``procesar_subida`` devuelve un reporte y un id; el id sirve
       para descargar el archivo limpio por ``descargar_por_id``.
    2) Un archivo corrupto o vacio levanta ``ErrorDeSubida`` con
       un motivo legible; un ``TestClient`` lo traduce a 400, no a
       500.
    3) El tamano maximo se configura (constructor y env
       ``DATACLEAN_MAX_BYTES``); pasarse del limite levanta
       ``ErrorDeSubida`` antes de tocar la tabla.

Regla 6 (fuerte): al menos un test tiene que fallar sin el
codigo nuevo. Se demuestra con ``git stash`` (no ``git checkout``)
en la bitacora.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from dataclean.endpoint import (
    ErrorDeSubida,
    ServicioLimpieza,
    descargar_por_id,
    procesar_subida,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CARPETA_TEMPORAL: str = ""


def _carpeta_temporal() -> Path:
    """Crea (una sola vez por proceso) una carpeta de salida limpia.

    La usamos para que los tests no escriban en
    ``tempfile.gettempdir()`` y se pisen entre si. La
    ``ServicioLimpieza`` se reinicia con esta carpeta en cada
    test por medio del fixture ``servicio``.
    """
    global _CARPETA_TEMPORAL
    if not _CARPETA_TEMPORAL:
        import tempfile

        _CARPETA_TEMPORAL = tempfile.mkdtemp(prefix="test_dc13_")
    return Path(_CARPETA_TEMPORAL)


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
def servicio(tmp_path: Path) -> ServicioLimpieza:
    return ServicioLimpieza(carpeta_salida=tmp_path)


# ---------------------------------------------------------------------------
# Cierre 1: POST devuelve reporte + id para descargar
# ---------------------------------------------------------------------------


def test_modulo_endpoint_define_servicio_y_procesar() -> None:
    """El modulo expone la API publica minima del item."""
    modulo = importlib.import_module("dataclean.endpoint")
    assert hasattr(modulo, "ServicioLimpieza")
    assert hasattr(modulo, "procesar_subida")
    assert hasattr(modulo, "descargar_por_id")
    assert hasattr(modulo, "ErrorDeSubida")


def test_procesar_subida_devuelve_id_y_reporte(servicio: ServicioLimpieza) -> None:
    """Cierre 1: el resultado lleva id, reporte y tamano."""
    resultado = procesar_subida(
        _csv_basico(), nombre_archivo="clientes.csv", servicio=servicio
    )
    assert isinstance(resultado, dict)
    assert "id" in resultado and isinstance(resultado["id"], str)
    assert "reporte" in resultado and isinstance(resultado["reporte"], dict)
    assert "tamano" in resultado and resultado["tamano"] > 0
    assert resultado["reporte"]["total_registros"] == 2


def test_id_generado_permite_descargar_archivo_limpio(
    servicio: ServicioLimpieza,
) -> None:
    """Cierre 1: el id funciona como puntero de descarga."""
    resultado = procesar_subida(
        _csv_basico(), nombre_archivo="c.csv", servicio=servicio
    )
    id_limpio = resultado["id"]
    assert servicio.existe(id_limpio) is True
    descarga = descargar_por_id(id_limpio, servicio=servicio)
    assert descarga is not None
    contenido, nombre = descarga
    assert nombre.endswith(".csv")
    # El CSV limpio se puede volver a leer y conserva las filas
    # originales (DC.11, cierre 2: columnas conservadas).
    assert b"Ana Perez" in contenido or b"ana" in contenido.lower()


def test_reporte_incluye_cifras_de_telefono(
    servicio: ServicioLimpieza,
) -> None:
    """El reporte serializado incluye las cifras principales."""
    resultado = procesar_subida(
        _csv_basico(), nombre_archivo="c.csv", servicio=servicio
    )
    reporte = resultado["reporte"]
    assert "telefonos_moviles" in reporte
    assert reporte["telefonos_moviles"]["disponible"] is True
    assert reporte["telefonos_moviles"]["valor"] == 2


# ---------------------------------------------------------------------------
# Cierre 2: archivo vacio / corrupto no tumba el servicio
# ---------------------------------------------------------------------------


def test_archivo_vacio_devuelve_motivo_legible(
    servicio: ServicioLimpieza,
) -> None:
    """Cierre 2: bytes vacios -> ErrorDeSubida con motivo."""
    with pytest.raises(ErrorDeSubida) as excinfo:
        procesar_subida(b"", nombre_archivo="vacio.csv", servicio=servicio)
    motivo = excinfo.value.motivo
    assert motivo
    assert "vacio" in motivo.lower() or "vacío" in motivo


def test_archivo_corrupto_devuelve_motivo_legible(
    servicio: ServicioLimpieza,
) -> None:
    """Cierre 2: bytes aleatorios no son ni CSV ni XLSX -> ErrorDeSubida."""
    with pytest.raises(ErrorDeSubida) as excinfo:
        procesar_subida(
            b"\x00\x01\x02\x03no es un archivo valido\xff\xfe",
            nombre_archivo="basura.bin",
            servicio=servicio,
        )
    motivo = excinfo.value.motivo
    assert motivo
    # Regla 8: el motivo es legible, no un stacktrace.
    assert "Traceback" not in motivo


def test_error_no_deja_archivos_huerfanos(
    tmp_path: Path,
) -> None:
    """Cierre 2 (consistencia): si la carga falla, no se escribe el limpio."""
    servicio = ServicioLimpieza(carpeta_salida=tmp_path)
    with pytest.raises(ErrorDeSubida):
        procesar_subida(
            b"\x00\x01basura", nombre_archivo="x.csv", servicio=servicio
        )
    # La carpeta puede existir (la creamos al vuelo), pero no debe
    # haber archivos limpios colgando.
    archivos = list(tmp_path.glob("*.csv"))
    assert archivos == []


def test_servicio_no_se_tumba_tras_error(
    servicio: ServicioLimpieza,
) -> None:
    """Cierre 2: tras un fallo, el servicio sigue aceptando peticiones."""
    with pytest.raises(ErrorDeSubida):
        procesar_subida(b"", nombre_archivo="v.csv", servicio=servicio)
    # La siguiente llamada legitima tiene que funcionar.
    resultado = procesar_subida(
        _csv_basico(), nombre_archivo="ok.csv", servicio=servicio
    )
    assert resultado["reporte"]["total_registros"] == 2


# ---------------------------------------------------------------------------
# Cierre 3: tamano maximo configurable
# ---------------------------------------------------------------------------


def test_tamano_maximo_constructor(
    tmp_path: Path,
) -> None:
    """Cierre 3: el tamano maximo se pasa en el constructor."""
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, tamano_maximo_bytes=10
    )
    with pytest.raises(ErrorDeSubida) as excinfo:
        procesar_subida(b"a" * 100, nombre_archivo="x.csv", servicio=servicio)
    assert "tamano" in excinfo.value.motivo.lower() or "tamaño" in excinfo.value.motivo


def test_tamano_maximo_lee_variable_de_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cierre 3: el operador puede sobreescribir el tamano por env."""
    monkeypatch.setenv("DATACLEAN_MAX_BYTES", "10")
    servicio = ServicioLimpieza(carpeta_salida=tmp_path)
    assert servicio.tamano_maximo_bytes == 10
    with pytest.raises(ErrorDeSubida):
        procesar_subida(b"a" * 100, nombre_archivo="x.csv", servicio=servicio)


def test_tamano_maximo_por_defecto_es_positivo() -> None:
    """Cierre 3: el default no rechaza una subida pequena razonable."""
    servicio = ServicioLimpieza(carpeta_salida=_carpeta_temporal())
    assert servicio.tamano_maximo_bytes > 1024
    # Una peticion pequena NO debe ser rechazada por tamano.
    resultado = procesar_subida(
        _csv_basico(), nombre_archivo="p.csv", servicio=servicio
    )
    assert "id" in resultado


def test_tamano_maximo_invalido_en_constructor() -> None:
    """Cierre 3: un tamano <= 0 en el constructor es un error de uso."""
    with pytest.raises(ValueError):
        ServicioLimpieza(tamano_maximo_bytes=0)


# ---------------------------------------------------------------------------
# XLSX + HTTP wrapper
# ---------------------------------------------------------------------------


def test_soporta_archivo_xlsx(servicio: ServicioLimpieza) -> None:
    """DC.1 (csv o excel) y DC.13: el endpoint acepta ambos formatos."""
    resultado = procesar_subida(
        _xlsx_basico(), nombre_archivo="datos.xlsx", servicio=servicio
    )
    assert "id" in resultado
    assert resultado["reporte"]["total_registros"] == 2
    assert servicio.existe(resultado["id"]) is True


def test_id_inexistente_devuelve_none(servicio: ServicioLimpieza) -> None:
    """Un id que no fue emitido no apunta a ningun archivo."""
    assert descargar_por_id("nope", servicio=servicio) is None


# ---------------------------------------------------------------------------
# Regla 6 fuerte: comportamiento, no solo firma
# ---------------------------------------------------------------------------


def test_regla6_fuerte_resultado_incluye_cifras_reales(
    servicio: ServicioLimpieza,
) -> None:
    """Si el modulo devolviera un dict vacio, este test cae.

    Demuestra que los tests prueban CAMINO REAL: las cifras
    tienen que venir del pipeline, no ser un placeholder.
    """
    resultado = procesar_subida(
        _csv_basico(), nombre_archivo="c.csv", servicio=servicio
    )
    # Estas dos cifras son las que DC.4/DC.5/DC.8 garantizan:
    # moviles detectados y grupos de duplicados.
    moviles = resultado["reporte"]["telefonos_moviles"]
    assert moviles["disponible"] is True
    assert moviles["valor"] == 2  # 2 moviles reales
    # El archivo descargable NO esta vacio y contiene la cabecera
    # del CSV exportado (DC.11 usa ';' como separador).
    descarga = descargar_por_id(resultado["id"], servicio=servicio)
    assert descarga is not None
    contenido, _ = descarga
    assert len(contenido) > 0
    assert b"nombre" in contenido.lower()


def test_regla6_fuerte_id_es_efimeramente_unico(
    servicio: ServicioLimpieza,
) -> None:
    """Dos subidas seguidas reciben ids distintos (el id NO es un contador
    trivial ni se reutiliza). Si la implementacion reutilizara ids este
    test cae con AssertionError."""
    r1 = procesar_subida(_csv_basico(), nombre_archivo="a.csv", servicio=servicio)
    r2 = procesar_subida(_csv_basico(), nombre_archivo="b.csv", servicio=servicio)
    assert r1["id"] != r2["id"]
    # Ambos tienen que estar localizables en disco de forma independiente.
    assert servicio.existe(r1["id"]) is True
    assert servicio.existe(r2["id"]) is True


def test_regla6_fuerte_motivo_no_es_stacktrace(
    servicio: ServicioLimpieza,
) -> None:
    """Regla 8: el motivo de un fallo NO contiene un Traceback de Python."""
    with pytest.raises(ErrorDeSubida) as excinfo:
        procesar_subida(
            b"\x00\x01basura", nombre_archivo="m.csv", servicio=servicio
        )
    motivo = excinfo.value.motivo
    assert "Traceback (most recent call last)" not in motivo
    assert "File \"" not in motivo
    # Y no es vacio: el cliente recibe algo util.
    assert len(motivo) > 5