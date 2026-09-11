"""Tests del item DC.16: la pagina web de subida y el resumen en una frase.

Cierres:
    1) ``GET /`` sirve una pagina que consume la API (``configuracion``,
       ``procesar``, ``descargar``) y pinta los datos del archivo sin
       ``innerHTML`` (un nombre de columna es texto del cliente).
    2) El resumen dice en una frase lo que el ENCARGO promete («De tus 50
       contactos, 12 son fijos...»), en singular o plural segun toque, y
       no inventa cifras que no se pudieron calcular.
    3) El resumen no contiene ningun dato de contacto (regla 9).

Regla 6 (fuerte): los modulos se importan DENTRO de cada test.
"""

from __future__ import annotations

import importlib
from pathlib import Path


def _modulo(nombre: str):
    return importlib.import_module(f"dataclean.{nombre}")


def _cliente(tmp_path: Path):
    from fastapi.testclient import TestClient

    endpoint = _modulo("endpoint")
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path)
    return TestClient(endpoint.crear_app(servicio))


def _cifra(valor: int, filas: list[int] | None = None) -> dict:
    return {"valor": valor, "disponible": True, "motivo": "", "filas": filas or []}


def _no_disponible() -> dict:
    return {"valor": None, "disponible": False, "motivo": "no esta", "filas": []}


def _reporte(
    total: int = 50,
    moviles: int = 31,
    fijos: int = 12,
    invalidos: int = 3,
    grupos: list[list[int]] | None = None,
    correos: int = 0,
    por_nombre: int = 0,
) -> dict:
    grupos = grupos if grupos is not None else [[0, 1], [2, 3], [4, 5, 6]]
    return {
        "total_registros": total,
        "telefonos_moviles": _cifra(moviles),
        "telefonos_fijos": _cifra(fijos),
        "telefonos_invalidos": _cifra(invalidos),
        "correos_marcados": _cifra(correos),
        "grupos_duplicados": {
            "valor": len(grupos),
            "grupos": [{"id": f"tel-{i}", "filas": g} for i, g in enumerate(grupos)],
        },
        "duplicados_por_nombre": _cifra(por_nombre),
    }


# ---------------------------------------------------------------------------
# Cierre 1: la pagina
# ---------------------------------------------------------------------------


def test_inicio_sirve_la_pagina_de_subida(tmp_path: Path) -> None:
    respuesta = _cliente(tmp_path).get("/")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/html")
    assert "default-src 'self'" in respuesta.headers["content-security-policy"]
    assert 'type="file"' in respuesta.text


def test_la_pagina_consume_la_api(tmp_path: Path) -> None:
    html = _cliente(tmp_path).get("/").text
    assert 'fetch("configuracion")' in html
    assert 'fetch("procesar"' in html
    assert '"descargar/"' in html
    assert 'append("archivo"' in html


def test_la_pagina_no_pinta_con_innerhtml(tmp_path: Path) -> None:
    html = _cliente(tmp_path).get("/").text
    assert "innerHTML" not in html
    assert "insertAdjacentHTML" not in html


def test_configuracion_expone_los_limites(tmp_path: Path) -> None:
    config = _cliente(tmp_path).get("/configuracion").json()
    assert config["tamano_maximo_bytes"] > 0
    assert config["horas_retencion"] > 0
    assert config["formatos_descarga"] == ["csv", "xlsx"]


def test_la_pagina_viaja_con_el_paquete() -> None:
    from importlib import resources

    assert resources.files("dataclean").joinpath("web/index.html").is_file()


# ---------------------------------------------------------------------------
# Cierre 2: el resumen
# ---------------------------------------------------------------------------


def test_resumen_con_la_frase_del_encargo() -> None:
    resumen = _modulo("resumen")
    assert resumen.redactar_resumen(_reporte()) == (
        "De tus 50 contactos, 31 tienen un móvil válido; 12 son fijos "
        "(no reciben WhatsApp ni SMS), 4 están repetidos y 3 no tienen "
        "un número válido."
    )


def test_resumen_en_singular() -> None:
    resumen = _modulo("resumen")
    texto = resumen.redactar_resumen(
        _reporte(total=4, moviles=1, fijos=1, invalidos=1, grupos=[[0, 3]], correos=1, por_nombre=1)
    )
    assert texto == (
        "De tus 4 contactos, 1 tiene un móvil válido; 1 es fijo (no recibe "
        "WhatsApp ni SMS), 1 está repetido y 1 no tiene un número válido. "
        "1 correo tiene problemas. 1 nombre aparece más de una vez: "
        "revísalos antes de borrar nada."
    )


def test_resumen_sin_problemas() -> None:
    resumen = _modulo("resumen")
    texto = resumen.redactar_resumen(
        _reporte(total=2, moviles=2, fijos=0, invalidos=0, grupos=[])
    )
    assert texto == (
        "De tus 2 contactos, 2 tienen un móvil válido y no encontramos "
        "problemas en los teléfonos."
    )


def test_resumen_no_inventa_si_no_hay_columna_de_telefono() -> None:
    resumen = _modulo("resumen")
    reporte = _reporte(grupos=[])
    for clave in ("telefonos_moviles", "telefonos_fijos", "telefonos_invalidos"):
        reporte[clave] = _no_disponible()
    texto = resumen.redactar_resumen(reporte)
    assert "no pudimos revisar los teléfonos" in texto
    for cifra_inventada in ("móvil válido", "fijo", "repetido", "número válido"):
        assert cifra_inventada not in texto


def test_resumen_de_un_archivo_sin_contactos() -> None:
    resumen = _modulo("resumen")
    assert resumen.redactar_resumen(_reporte(total=0)) == "Tu archivo no tiene contactos."


# ---------------------------------------------------------------------------
# Cierre 3: regla 9
# ---------------------------------------------------------------------------


def test_resumen_real_no_contiene_datos_de_contacto(tmp_path: Path) -> None:
    endpoint = _modulo("endpoint")
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path)
    csv = (
        "nombre,telefono,correo\n"
        "Rosa Quintero,3001234567,rosa@ejemplo.com\n"
        "ROSA QUINTERO,3001234567,rosa@@ejemplo.com\n"
    ).encode("utf-8")

    texto = endpoint.procesar_subida(csv, "c.csv", servicio=servicio)["reporte"]["resumen"]

    assert texto.startswith("De tus 2 contactos")
    for dato in ("Rosa", "ROSA", "Quintero", "3001234567", "ejemplo.com"):
        assert dato not in texto
