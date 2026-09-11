"""Tests del item DC.15: el endpoint, listo para muchos usuarios.

Cierres:
    1) ``POST /procesar`` funciona por HTTP real (antes fallaba con
       ``PydanticUserError``) y no expone la ruta del servidor.
    2) El archivo limpio se descarga en CSV y en Excel, y lleva las marcas
       de duplicados que cuenta el reporte.
    3) Un id o un formato invalidos no tocan el disco; un cuerpo demasiado
       grande se rechaza por su cabecera; un error inesperado devuelve un
       500 legible sin datos de contacto.
    4) Los archivos limpios caducan pasadas las horas de retencion.

Regla 6 (fuerte): los modulos se importan DENTRO de cada test.
"""

from __future__ import annotations

import importlib
import io
import logging
import os
import time
from pathlib import Path

import pytest


def _endpoint():
    return importlib.import_module("dataclean.endpoint")


def _cliente(servicio):
    from fastapi.testclient import TestClient

    return TestClient(_endpoint().crear_app(servicio), raise_server_exceptions=False)


def _csv_con_duplicados() -> bytes:
    return (
        "nombre,telefono,correo\n"
        "Ana Perez,3001234567,ana@ejemplo.com\n"
        "ANA PEREZ,300 123 4567,ana@ejemplo.com\n"
        "Luis Gomez,6015551234,luis@@ejemplo.com\n"
    ).encode("utf-8")


@pytest.fixture
def servicio(tmp_path: Path):
    return _endpoint().ServicioLimpieza(carpeta_salida=tmp_path)


# ---------------------------------------------------------------------------
# Cierre 1: HTTP real
# ---------------------------------------------------------------------------


def test_post_http_devuelve_el_reporte(servicio) -> None:
    respuesta = _cliente(servicio).post(
        "/procesar", files={"archivo": ("lista.csv", _csv_con_duplicados())}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["reporte"]["total_registros"] == 3
    assert cuerpo["reporte"]["telefonos_fijos"]["valor"] == 1
    assert cuerpo["formatos"] == ["csv", "xlsx"]


def test_post_http_no_expone_la_ruta_del_servidor(servicio) -> None:
    cuerpo = _cliente(servicio).post(
        "/procesar", files={"archivo": ("lista.csv", _csv_con_duplicados())}
    ).json()
    assert "ruta" not in cuerpo
    assert str(servicio.carpeta_salida) not in str(cuerpo)


def test_post_http_archivo_corrupto_da_400_con_motivo(servicio) -> None:
    respuesta = _cliente(servicio).post(
        "/procesar", files={"archivo": ("x.csv", b"\x00\x01\x02basura\xff")}
    )
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"]["motivo"]


def test_cabecera_sin_filas_da_motivo_legible(servicio) -> None:
    endpoint = _endpoint()
    with pytest.raises(endpoint.ErrorDeSubida) as excinfo:
        endpoint.procesar_subida(b"nombre,telefono\n", "c.csv", servicio=servicio)
    assert excinfo.value.motivo == endpoint.MOTIVO_SIN_FILAS


def test_cifras_serializadas_llevan_sus_filas(servicio) -> None:
    """DC.10 Cierre 2 tambien por HTTP: cada cifra dice que filas la componen."""
    reporte = _endpoint().procesar_subida(
        _csv_con_duplicados(), "c.csv", servicio=servicio
    )["reporte"]
    assert reporte["telefonos_moviles"]["filas"] == [0, 1]
    assert reporte["telefonos_fijos"]["filas"] == [2]
    assert reporte["correos_marcados"]["filas"] == [2]


# ---------------------------------------------------------------------------
# Cierre 2: descargas con las marcas de duplicados
# ---------------------------------------------------------------------------


def test_descarga_en_excel_y_en_csv(servicio) -> None:
    cliente = _cliente(servicio)
    identificador = cliente.post(
        "/procesar", files={"archivo": ("lista.csv", _csv_con_duplicados())}
    ).json()["id"]

    xlsx = cliente.get(f"/descargar/{identificador}?formato=xlsx")
    csv = cliente.get(f"/descargar/{identificador}")

    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK\x03\x04")
    assert "contactos_limpios.xlsx" in xlsx.headers["content-disposition"]
    assert csv.status_code == 200 and csv.content.startswith(b"\xef\xbb\xbf")


def test_archivo_limpio_lleva_las_marcas_que_cuenta_el_reporte(servicio) -> None:
    import pandas as pd

    endpoint = _endpoint()
    resultado = endpoint.procesar_subida(
        _csv_con_duplicados(), "c.csv", servicio=servicio
    )
    contenido, _ = endpoint.descargar_por_id(
        resultado["id"], servicio=servicio, formato="xlsx"
    )
    tabla = pd.read_excel(io.BytesIO(contenido))

    grupo = resultado["reporte"]["grupos_duplicados"]["grupos"][0]
    marcadas = tabla.index[tabla["duplicado_telefono_grupo"] == grupo["id"]].tolist()
    assert marcadas == grupo["filas"]
    assert tabla["duplicado_telefono"].tolist() == [False, True, False]
    assert tabla["duplicado_nombre"].tolist() == [False, True, False]
    # Las columnas originales siguen ahi (DC.11 Cierre 2).
    assert {"nombre", "telefono", "correo"} <= set(tabla.columns)


def test_duplicados_por_nombre_en_el_reporte(servicio) -> None:
    reporte = _endpoint().procesar_subida(
        _csv_con_duplicados(), "c.csv", servicio=servicio
    )["reporte"]
    por_nombre = reporte["duplicados_por_nombre"]
    assert por_nombre["disponible"] is True
    assert por_nombre["valor"] == 1
    assert por_nombre["grupos"] == [{"filas": [0, 1], "sospechoso": False}]


def test_sin_columna_de_nombre_los_duplicados_por_nombre_no_se_inventan(servicio) -> None:
    reporte = _endpoint().procesar_subida(
        b"telefono\n3001234567\n", "c.csv", servicio=servicio
    )["reporte"]
    assert reporte["duplicados_por_nombre"]["disponible"] is False
    assert reporte["duplicados_por_nombre"]["valor"] is None


# ---------------------------------------------------------------------------
# Cierre 3: entradas hostiles y errores inesperados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", ["../../etc/passwd", "..", "ABCDEF0123456789", "123"])
def test_id_invalido_no_construye_ruta(servicio, identificador: str) -> None:
    assert servicio._ruta_para_id(identificador) is None
    assert servicio.existe(identificador) is False


def test_http_id_desconocido_da_404_legible(servicio) -> None:
    respuesta = _cliente(servicio).get("/descargar/0123456789abcdef")
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["motivo"] == _endpoint().MOTIVO_ID_NO_DISPONIBLE


def test_http_formato_no_soportado_da_400(servicio) -> None:
    respuesta = _cliente(servicio).get("/descargar/0123456789abcdef?formato=pdf")
    assert respuesta.status_code == 400


def test_cuerpo_demasiado_grande_se_rechaza_por_cabecera(tmp_path: Path) -> None:
    endpoint = _endpoint()
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path, tamano_maximo_bytes=1000)
    respuesta = _cliente(servicio).post(
        "/procesar", files={"archivo": ("grande.csv", b"a" * 200_000)}
    )
    assert respuesta.status_code == 413
    assert "tamaño" in respuesta.json()["detail"]["motivo"]


def test_error_inesperado_da_500_legible_sin_datos(
    servicio, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    endpoint = _endpoint()

    def _revienta(*_args, **_kwargs):
        raise RuntimeError("fallo con el dato 3001234567 dentro")

    monkeypatch.setattr(endpoint, "generar_reporte", _revienta)
    # El handler va directo al logger: DC.12 deja ``propagate=False`` en
    # ``dataclean`` y el registro no llegaria al handler raiz de caplog.
    logger = logging.getLogger("dataclean.endpoint")
    logger.addHandler(caplog.handler)
    try:
        respuesta = _cliente(servicio).post(
            "/procesar", files={"archivo": ("lista.csv", _csv_con_duplicados())}
        )
    finally:
        logger.removeHandler(caplog.handler)

    assert respuesta.status_code == 500
    assert respuesta.json()["detail"]["motivo"] == endpoint.MOTIVO_ERROR_INTERNO
    assert "3001234567" not in respuesta.text
    assert "RuntimeError" in caplog.text
    assert "3001234567" not in caplog.text


def test_respuestas_llevan_cabeceras_de_seguridad(servicio) -> None:
    respuesta = _cliente(servicio).get("/configuracion")
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert respuesta.headers["x-frame-options"] == "DENY"


# ---------------------------------------------------------------------------
# Cierre 4: retencion
# ---------------------------------------------------------------------------


def test_borrar_expirados_solo_toca_archivos_viejos_del_servicio(tmp_path: Path) -> None:
    endpoint = _endpoint()
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path, horas_retencion=1)
    viejo = tmp_path / "0123456789abcdef.csv"
    reciente = tmp_path / "fedcba9876543210.csv"
    ajeno = tmp_path / "notas.txt"
    for ruta in (viejo, reciente, ajeno):
        ruta.write_text("x")
    hace_dos_horas = time.time() - 2 * 3600
    for ruta in (viejo, ajeno):
        os.utime(ruta, (hace_dos_horas, hace_dos_horas))

    assert servicio.borrar_expirados() == 1
    assert not viejo.exists()
    assert reciente.exists() and ajeno.exists()


def test_horas_de_retencion_se_configuran_por_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATACLEAN_HORAS_RETENCION", "3")
    servicio = _endpoint().ServicioLimpieza(carpeta_salida=tmp_path)
    assert servicio.horas_retencion == 3


def test_horas_de_retencion_invalidas_se_rechazan(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _endpoint().ServicioLimpieza(carpeta_salida=tmp_path, horas_retencion=0)
