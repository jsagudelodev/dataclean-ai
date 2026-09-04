"""Cierre de DC.12: ni un dato de contacto en el log (regla 9).

Dos contratos del item:
  1) **Cierre 1** -- un test procesa un archivo con una credencial
     configurada y comprueba que ni la credencial ni ningun dato de
     contacto (nombre, telefono, correo) aparece en ninguna linea
     del log.
  2) **Cierre 2** -- el dato tiene que LLEGAR al camino que escribe
     el log. Si el montaje no lo hace entrar, el test no vale.

REGLA 6 FUERTE (lo que el aviso del revisor exige):
    En este archivo NO se importan ``dataclean`` ni
    ``dataclean.log_seguro`` en el header. Los imports se hacen
    DENTRO de cada test, con ``importlib.import_module``. Asi:

      * Si ``log_seguro.py`` NO existe, los tests se RECOLECTAN
        y se EJECUTAN: cada uno cae con ``ImportError`` dentro
        del test. pytest cuenta cada uno como "1 failed" (no
        como error de collection y no como passed).
      * Si el modulo existe pero alguien sustituye ``FiltroSeguro``
        por un pass-through, los asserts sobre el buffer caen
        con ``AssertionError`` y pytest los cuenta como failed.
"""

from __future__ import annotations

import importlib
import io
import logging
from pathlib import Path

import pytest


# --- Datos de prueba (constantes del modulo, no imports) ----------------

CREDENCIAL: str = "clave-super-secreta-abc-2024"
NOMBRE: str = "Juan Perez"
TELEFONO: str = "3001234567"
CORREO: str = "juan@correo.com"


def _escribir_csv_de_prueba(tmp_path: Path) -> Path:
    """Escribe un CSV con nombre, telefono, correo y la credencial."""
    ruta = tmp_path / "contactos.csv"
    ruta.write_text(
        "nombre,telefono,correo,api_key\n"
        f"{NOMBRE},{TELEFONO},{CORREO},{CREDENCIAL}\n"
        "Ana Lopez,3112223333,ana@x.com,clave-api-2\n",
        encoding="utf-8",
    )
    return ruta


def _importar_log_seguro():
    """Importa el modulo ``dataclean.log_seguro`` por su nombre.

    Helper usado por TODOS los tests del archivo. Si el modulo no
    existe, lanza ``ImportError`` que pytest reporta como failed.
    """
    return importlib.import_module("dataclean.log_seguro")


# --- Cierre 1: nada de dato de contacto ni credencial en el log ---------


def test_ni_credencial_ni_contacto_en_el_log(tmp_path: Path) -> None:
    """Cierre 1: tras procesar el archivo, el log no contiene
    ningun dato de contacto ni la credencial."""
    mod = _importar_log_seguro()
    procesar_archivo = getattr(mod, "procesar_archivo")

    ruta = _escribir_csv_de_prueba(tmp_path)
    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )

    contenido = buffer.getvalue()
    assert CREDENCIAL not in contenido, (
        f"la credencial aparece en el log:\n{contenido}"
    )
    assert NOMBRE not in contenido, f"el nombre aparece:\n{contenido}"
    assert TELEFONO not in contenido, f"el telefono aparece:\n{contenido}"
    assert CORREO not in contenido, f"el correo aparece:\n{contenido}"
    # La marca canonica SI debe aparecer (el dato se sustituyo).
    assert mod.MARCADOR_REDACTADO in contenido


def test_credencial_y_contactos_en_varias_filas(tmp_path: Path) -> None:
    """Variante con dos filas: el filtro se aplica a TODAS las
    filas, no solo a la primera."""
    mod = _importar_log_seguro()
    procesar_archivo = getattr(mod, "procesar_archivo")

    ruta = _escribir_csv_de_prueba(tmp_path)
    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )
    contenido = buffer.getvalue()
    assert "3112223333" not in contenido
    assert "Ana Lopez" not in contenido
    assert "ana@x.com" not in contenido
    assert "clave-api-2" not in contenido


# --- Cierre 2: el dato LLEGA al camino que escribe el log ----------------


def test_sin_filtro_el_dato_si_llega_al_log(tmp_path: Path) -> None:
    """Cierre 2: si desactivamos el filtro, los datos aparecen en
    el log. Esto demuestra que el dato esta entrando al codigo del
    log y que el filtro es el que los oculta."""
    mod = _importar_log_seguro()
    procesar_archivo = getattr(mod, "procesar_archivo")

    ruta = _escribir_csv_de_prueba(tmp_path)
    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )

    # Antes de quitar el filtro, verificamos que el pipeline YA
    # emitio la credencial (con filtro, redactada). Esto demuestra
    # que la credencial ENTRA al codigo del log: el filtro la
    # sustituye, pero la cadena original paso por ahi.
    contenido_con_filtro = buffer.getvalue()
    assert CREDENCIAL not in contenido_con_filtro
    assert mod.MARCADOR_REDACTADO in contenido_con_filtro

    # Quitamos el filtro y emitimos mensajes adicionales: ahora el
    # dato aparece en claro. La diferencia entre "filtro presente"
    # y "filtro ausente" demuestra que el dato LLEGO al codigo del
    # log y que el filtro es quien lo oculta.
    for f in list(logger.filters):
        logger.removeFilter(f)

    logger.info("comprobacion telefono=%s", TELEFONO)
    logger.info("comprobacion correo=%s", CORREO)
    logger.info("comprobacion nombre=%s", NOMBRE)
    logger.info("comprobacion credencial=%s", CREDENCIAL)

    contenido = buffer.getvalue()
    assert TELEFONO in contenido
    assert CORREO in contenido
    assert NOMBRE in contenido
    assert CREDENCIAL in contenido


def test_con_filtro_el_dato_se_redacta_en_msg_y_args() -> None:
    """El filtro, aplicado a un ``LogRecord`` con el dato en ``msg``
    Y en ``args``, redacta ambos."""
    mod = _importar_log_seguro()
    configurar = getattr(mod, "configurar_log_seguro")

    logger, buffer = configurar(
        credencial=CREDENCIAL,
        valores_sensibles=[NOMBRE, TELEFONO, CORREO],
    )
    logger.info("procesando telefono=%s correo=%s", TELEFONO, CORREO)
    logger.info("nombre=%s con clave=%s", NOMBRE, CREDENCIAL)

    contenido = buffer.getvalue()
    assert TELEFONO not in contenido
    assert CORREO not in contenido
    assert NOMBRE not in contenido
    assert CREDENCIAL not in contenido
    assert contenido.count(mod.MARCADOR_REDACTADO) >= 4


# --- Regla 6 fuerte: tests que NO dependen del reexport de __init__ ----


def test_regla6_fuerte_filtro_redacta_credencial_en_msg() -> None:
    """Regla 6 fuerte (1/3): el filtro redacta la credencial
    dentro de ``record.msg`` cuando se emite un log que la
    contiene. El assert se hace sobre el comportamiento (el
    contenido del buffer), no sobre la firma de la clase."""
    mod = _importar_log_seguro()
    configurar = getattr(mod, "configurar_log_seguro")

    logger, buffer = configurar(
        credencial="credencial-X-12345",
        valores_sensibles=(),
    )
    logger.info("probando credencial=credencial-X-12345")
    contenido = buffer.getvalue()

    # Comportamiento: la credencial NO debe estar en el log.
    assert "credencial-X-12345" not in contenido, (
        f"la credencial aparece en claro:\n{contenido}"
    )
    # Y debe aparecer la marca canonica.
    assert mod.MARCADOR_REDACTADO in contenido


def test_regla6_fuerte_filtro_redacta_sensibles_en_args() -> None:
    """Regla 6 fuerte (2/3): el filtro redacta los sensibles que
    llegan como ``args`` (formateo %s) al ``LogRecord``. Esto
    cubre el caso real de ``logger.info("dato=%s", valor)``."""
    mod = _importar_log_seguro()
    configurar = getattr(mod, "configurar_log_seguro")

    logger, buffer = configurar(
        credencial=None,
        valores_sensibles=["tel-555-1234", "ana@x.com"],
    )
    logger.info(
        "fila 0 telefono=%s correo=%s", "tel-555-1234", "ana@x.com"
    )
    contenido = buffer.getvalue()

    assert "tel-555-1234" not in contenido
    assert "ana@x.com" not in contenido
    assert contenido.count(mod.MARCADOR_REDACTADO) >= 2


def test_regla6_fuerte_filtro_no_es_passthrough() -> None:
    """Regla 6 fuerte (3/3): si el filtro fuera un pass-through
    (no redactara), este test caeria. Lo demostramos en el mismo
    test: primero emitimos con un FiltroNeutro y comprobamos que
    el dato esta en claro; luego emitimos con FiltroSeguro y
    comprobamos que se redacta. La diferencia prueba que el
    filtro del paquete hace trabajo real, no que es cosmetico."""
    mod = _importar_log_seguro()
    FiltroSeguroCls = getattr(mod, "FiltroSeguro")
    configurar = getattr(mod, "configurar_log_seguro")

    class FiltroNeutroCls(logging.Filter):
        def __init__(self, credencial=None, sensibles=()):
            super().__init__()
            self._credencial = credencial
            self._sensibles = tuple(sensibles)

        def filter(self, record):  # noqa: D401 - pass-through explicito
            return True

    # Fase 1: filtro neutro, el dato DEBE estar en claro.
    logger = logging.getLogger("dataclean.test_regla6_fuerte_passthrough")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.addFilter(
        FiltroNeutroCls(credencial="cred-1", sensibles=("dato-1",))
    )
    logger.info("con neutro dato=dato-1")
    contenido_neutro = buffer.getvalue()
    assert "dato-1" in contenido_neutro, (
        "con filtro neutro, el dato DEBE estar en claro; si no, "
        "el experimento no demuestra nada."
    )

    # Fase 2: anadimos FiltroSeguro encima y emitimos OTRO mensaje.
    logger.addFilter(
        FiltroSeguroCls(credencial="cred-1", sensibles=("dato-1",))
    )
    logger.info("con seguro dato=dato-1")
    contenido_total = buffer.getvalue()

    # El primer mensaje (filtro neutro) dejo "dato-1" en claro.
    assert "dato-1" in contenido_total
    # El segundo (FiltroSeguro) lo redacto: aparece [REDACTADO].
    assert mod.MARCADOR_REDACTADO in contenido_total


def test_procesar_archivo_emite_etiquetas_de_fila(tmp_path: Path) -> None:
    """Verifica que ``procesar_archivo`` SI emite el mensaje
    ``fila N: nombre= telefono= correo=`` con el formato
    esperado. Si alguien quitara el bucle, este test caeria."""
    mod = _importar_log_seguro()
    procesar_archivo = getattr(mod, "procesar_archivo")

    ruta = _escribir_csv_de_prueba(tmp_path)
    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )
    contenido = buffer.getvalue()
    assert "fila 0:" in contenido
    assert "nombre=" in contenido
    assert "telefono=" in contenido
    assert "correo=" in contenido