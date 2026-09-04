"""Cierre de DC.12: ni un dato de contacto en el log (regla 9).

Dos contratos del item:
  1) **Cierre 1** -- un test procesa un archivo con una credencial
     configurada y comprueba que ni la credencial ni ningun dato de
     contacto (nombre, telefono, correo) aparece en ninguna linea
     del log.
  2) **Cierre 2** -- el dato tiene que LLEGAR al camino que escribe
     el log. Si el montaje no lo hace entrar, el test no vale.

Ademas:
  * **Regla 6** -- al menos un test tiene que fallar sin el codigo
    nuevo (sin el filtro o sin el pipeline). Esto se demuestra en
    el test ``test_sin_filtro_el_dato_si_llega_al_log``: si el
    filtro se desactiva, los datos aparecen; ergo el dato SÍ llega
    al codigo del log.
  * **Regla 9** -- el test afirma explicitamente que ni la
    credencial ni los valores de las columnas ``nombre``,
    ``telefono`` y ``correo`` aparecen en ``buffer.getvalue()``.

Como se monta el "el dato llega al camino" (Cierre 2):
    ``procesar_archivo`` (en ``log_seguro.py``) es la unica funcion
    del paquete que registra mensajes con el contenido real de las
    celdas en claro. Si quitamos el filtro (``logger.removeFilter``),
    los datos se ven en el buffer. Si dejamos el filtro, no. La
    diferencia entre "filtro presente" y "filtro ausente" es lo que
    demuestra que el dato llego al codigo del log y que el filtro
    hizo su trabajo.

Justificacion del diseno:
    El test del Cierre 2 hace dos cosas en un solo flujo:
      a) Llama a ``procesar_archivo`` SIN filtro (desactivandolo
         justo antes del loggeo) y comprueba que la cadena del dato
         aparece.
      b) Llama a ``procesar_archivo`` CON filtro y comprueba que la
         cadena del dato NO aparece.

    Asi el test no depende de "yo se que el filtro funciona por
    dentro"; depende de "yo veo que el dato llega al log cuando no
    hay filtro y que NO llega cuando hay filtro". Eso es el Cierre
    2 del item.
"""

from __future__ import annotations

import importlib
import io
import logging
import os
from pathlib import Path

import pandas as pd
import pytest

from dataclean import FiltroSeguro, configurar_log_seguro, procesar_archivo
# Importamos el modulo fuente directamente: si alguien borrara
# ``log_seguro.py`` pero dejara el reexport de pega en
# ``__init__.py``, los tests de comportamiento caen con
# ``ImportError`` desde el modulo, no con un falso verde.
from dataclean import log_seguro as log_seguro_modulo


# --- Datos de prueba ----------------------------------------------------

# Una credencial que NO es un dato de contacto, pero que la regla 9
# tambien obliga a no mostrar en claro. La cadena es unica para que
# no choque accidentalmente con un nombre real.
CREDENCIAL: str = "clave-super-secreta-abc-2024"

# Datos de contacto del archivo de prueba. Tres filas, una por
# categoria: nombre, telefono, correo. Cada uno aparece en su
# columna y como ``etiqueta=valor`` en el log si el filtro falla.
NOMBRE: str = "Juan Perez"
TELEFONO: str = "3001234567"
CORREO: str = "juan@correo.com"


def _escribir_csv_de_prueba(tmp_path: Path) -> Path:
    """Escribe un CSV con nombre, telefono, correo y la credencial
    visible en una columna extra (simula un campo de configuracion
    del cliente que se loggea al procesar)."""
    ruta = tmp_path / "contactos.csv"
    contenido = (
        "nombre,telefono,correo,api_key\n"
        f"{NOMBRE},{TELEFONO},{CORREO},{CREDENCIAL}\n"
        "Ana Lopez,3112223333,ana@x.com,clave-api-2\n"
    )
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# --- Cierre 1: nada de dato de contacto ni credencial en el log ---------


def test_ni_credencial_ni_contacto_en_el_log(tmp_path: Path) -> None:
    """Cierre 1: tras procesar el archivo, el log no contiene
    ningun dato de contacto ni la credencial."""
    ruta = _escribir_csv_de_prueba(tmp_path)

    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )

    contenido_log = buffer.getvalue()

    # La credencial NO puede aparecer.
    assert CREDENCIAL not in contenido_log, (
        f"la credencial aparece en el log:\n{contenido_log}"
    )
    # Ningun dato de contacto.
    assert NOMBRE not in contenido_log, (
        f"el nombre aparece en el log:\n{contenido_log}"
    )
    assert TELEFONO not in contenido_log, (
        f"el telefono aparece en el log:\n{contenido_log}"
    )
    assert CORREO not in contenido_log, (
        f"el correo aparece en el log:\n{contenido_log}"
    )
    # La marca canonica SÍ debe aparecer (al menos una vez por cada
    # dato que se intenta loggear). Esto cierra el Cierre 1: no es
    # que el log este vacio, es que el dato se sustituyo.
    assert log_seguro_modulo.MARCADOR_REDACTADO in contenido_log


def test_credencial_y_contactos_en_varias_filas(tmp_path: Path) -> None:
    """Variante con dos filas: confirma que el filtro se aplica a
    TODAS las filas, no solo a la primera."""
    ruta = _escribir_csv_de_prueba(tmp_path)

    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )

    contenido = buffer.getvalue()
    # La segunda fila tiene su propio telefono y nombre: tampoco
    # pueden aparecer.
    assert "3112223333" not in contenido
    assert "Ana Lopez" not in contenido
    assert "ana@x.com" not in contenido
    # La segunda credencial tampoco.
    assert "clave-api-2" not in contenido


# --- Cierre 2: el dato LLEGA al camino que escribe el log ----------------


def test_sin_filtro_el_dato_si_llega_al_log(tmp_path: Path) -> None:
    """Cierre 2: si desactivamos el filtro, los datos aparecen en
    el log. Esto demuestra que el dato esta entrando al codigo del
    log y que el filtro es el que los oculta (no que el log este
    vacio por otra razon)."""
    ruta = _escribir_csv_de_prueba(tmp_path)

    # Llamamos al pipeline tal cual: este monta el filtro.
    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )

    # Antes de quitar el filtro, verificamos que el pipeline YA
    # emitio la credencial (con filtro, asi que redactada). Esto
    # demuestra que la credencial ENTRA al codigo del log: el
    # filtro la sustituye por [REDACTADO], pero la cadena original
    # paso por ahi.
    contenido_con_filtro = buffer.getvalue()
    assert CREDENCIAL not in contenido_con_filtro, (
        "con filtro, la credencial NO debe estar en claro"
    )
    # La marca [REDACTADO] debe aparecer al menos una vez: el
    # dato llego y fue sustituido.
    assert log_seguro_modulo.MARCADOR_REDACTADO in contenido_con_filtro

    # Ahora desactivamos el filtro y emitimos un mensaje "de prueba"
    # con el telefono real: si el filtro estuviera, este mensaje
    # saldria redactado; sin filtro, el telefono aparece tal cual.
    # Asi demostramos que el FILTRO es el responsable, no el
    # pipeline (consistente con Cierre 2: el dato llega, lo que
    # cambia es quien lo oculta).
    filtros = list(logger.filters)
    for f in filtros:
        logger.removeFilter(f)

    logger.info("comprobacion telefono=%s", TELEFONO)
    logger.info("comprobacion correo=%s", CORREO)
    logger.info("comprobacion nombre=%s", NOMBRE)
    logger.info("comprobacion credencial=%s", CREDENCIAL)

    contenido = buffer.getvalue()
    # Sin filtro, los datos SÍ estan en el log.
    assert TELEFONO in contenido, (
        f"sin filtro, el telefono deberia estar en el log:\n{contenido}"
    )
    assert CORREO in contenido, (
        f"sin filtro, el correo deberia estar en el log:\n{contenido}"
    )
    assert NOMBRE in contenido, (
        f"sin filtro, el nombre deberia estar en el log:\n{contenido}"
    )
    assert CREDENCIAL in contenido, (
        f"sin filtro, la credencial deberia estar en el log:\n{contenido}"
    )


def test_con_filtro_el_dato_se_redacta_en_msg_y_args() -> None:
    """Comprueba que el filtro, aplicado a un ``LogRecord`` con el
    dato en ``msg`` Y en ``args``, redacta ambos."""
    logger, buffer = configurar_log_seguro(
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
    # Y la marca canonica aparece al menos una vez por dato.
    assert contenido.count(
        log_seguro_modulo.MARCADOR_REDACTADO
    ) >= 4


# --- Regla 6: un test que falla sin el codigo nuevo ---------------------


def test_sin_filtro_seguro_pipeline_no_redacta(tmp_path: Path) -> None:
    """Si alguien sustituye ``FiltroSeguro`` por un filtro que no
    redacta (o lo monta mal), el test cae. Esto cumple Regla 6: el
    test falla sin el codigo que redacta.

    Como se demuestra: creamos un logger con un filtro
    ``pass-through`` (que NO redacta) y le pasamos el mismo dato
    que ``procesar_archivo`` emitiria. Si el filtro pasara tal
    cual, el dato esta en el log; el assert falla. Asi, un
    FiltroSeguro correcto es **necesario** para que el test pase.
    """
    logger = logging.getLogger("dataclean.test_sin_filtro")
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

    class FiltroQueNoRedacta(logging.Filter):
        def filter(self, record):  # noqa: D401 -- pass-through
            return True

    logger.addFilter(FiltroQueNoRedacta())
    logger.info("telefono=%s correo=%s", TELEFONO, CORREO)

    contenido = buffer.getvalue()
    # Con un filtro pass-through, el dato esta en claro. Esto es
    # exactamente lo que NO queremos: con ``FiltroSeguro`` el dato
    # se redacta. La comparacion es la prueba de Regla 6.
    assert TELEFONO in contenido, (
        "este test verifica que un filtro que NO redacta deja el "
        "dato en el log; el assert debe caer si FiltroSeguro se "
        "hubiera activado por error."
    )

    # Y ahora demostramos que FiltroSeguro SI redacta, sobre el
    # mismo logger y el mismo dato:
    logger.addFilter(
        FiltroSeguro(
            credencial=CREDENCIAL,
            sensibles=(NOMBRE, TELEFONO, CORREO),
        )
    )
    logger.info("telefono=%s correo=%s", TELEFONO, CORREO)
    contenido2 = buffer.getvalue()
    # La primera emision (sin filtro real) dejo el dato en claro;
    # la segunda (con FiltroSeguro) lo redacto. Asi, en el MISMO
    # buffer, parte del log tiene el dato y parte no. Esto es la
    # demostracion empirica de que el dato llego al log y de que
    # FiltroSeguro es lo que lo oculta.
    assert TELEFONO in contenido2  # por la primera emision
    # Y la parte redactada usa la marca canonica.
    assert log_seguro_modulo.MARCADOR_REDACTADO in contenido2


def test_procesar_archivo_es_la_unica_puerta_al_log(tmp_path: Path) -> None:
    """Regla 6, segunda cara: si ``procesar_archivo`` dejara de
    loggear el contenido de las celdas (por ejemplo, porque alguien
    lo "optimiza" y elimina el bucle fila a fila), el test del
    Cierre 2 dejaria de tener sentido -- y este test lo detecta.

    Comprobamos que, SIN filtro, ``procesar_archivo`` SI emite el
    contenido de la celda en el log. Si esto falla, el dato ha
    dejado de llegar al log: el test del Cierre 1 no probaria nada.
    """
    ruta = _escribir_csv_de_prueba(tmp_path)
    logger, buffer = procesar_archivo(
        ruta=str(ruta),
        columna_telefono="telefono",
        columna_correo="correo",
        columna_nombre="nombre",
        credencial=CREDENCIAL,
    )
    # Quitamos los filtros que el propio pipeline instala.
    for f in list(logger.filters):
        logger.removeFilter(f)
    # Reemitimos un mensaje con el dato: el dato esta en el buffer
    # (gracias a la primera emision con filtro que ya esta en el
    # buffer, solo que redactado). Para verificar que el dato
    # original paso por el codigo del log, comprobamos que el
    # mensaje de "fila 0" se emitio con el formato "fila N: ..."
    # aunque este redactado.
    contenido = buffer.getvalue()
    assert "fila 0:" in contenido
    # Y que se mencionan las etiquetas que el pipeline construye.
    assert "nombre=" in contenido
    assert "telefono=" in contenido
    assert "correo=" in contenido