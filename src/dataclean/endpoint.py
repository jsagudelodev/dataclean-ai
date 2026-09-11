"""Endpoint HTTP que junta todo el pipeline de DataClean (DC.13, DC.15, DC.16).

Por que existe este modulo:
    Los items DC.0 a DC.12 son piezas; este modulo es la "puerta" que las
    expone al exterior. Recibe un archivo por POST, lo pasa por el
    pipeline (cargar -> clasificar -> normalizar -> marcar duplicados ->
    reportar -> exportar), y devuelve al cliente dos cosas: el reporte y
    un identificador que le sirve para bajarse el archivo limpio en CSV o
    en Excel.

Contratos:
    * **DC.13** -- ``procesar_subida`` recibe bytes + nombre y devuelve un
      dict con el reporte serializable y un id que existe como archivo en
      disco. Un archivo corrupto o vacio levanta ``ErrorDeSubida`` con un
      ``motivo`` legible; ``crear_app`` lo traduce a HTTP 400. El tamano
      maximo se configura (constructor o ``DATACLEAN_MAX_BYTES``).
    * **DC.15** -- listo para muchos usuarios a la vez: el procesamiento
      corre fuera del bucle de eventos, el cuerpo de la subida se limita
      antes de leerlo entero, los ids se validan antes de tocar el disco,
      los archivos limpios caducan (``DATACLEAN_HORAS_RETENCION``), y el
      archivo limpio lleva las marcas de duplicados que cuenta el reporte.
    * **DC.16** -- ``GET /`` sirve la pagina web de subida, que solo
      consume esta misma API (``/configuracion``, ``/procesar``,
      ``/descargar``).

Diseno:
    * **La logica de negocio NO vive en FastAPI.** Vive en
      ``ServicioLimpieza.procesar``, que recibe bytes y devuelve un dict.
      Asi la suite la prueba sin levantar un servidor HTTP. ``crear_app``
      solo es el cable.
    * **Id corto y aleatorio.** ``secrets.token_hex(8)`` da 16 caracteres
      hex. NO se usa el nombre del archivo original como id (regla 9: el
      nombre podria contener un dato personal).
    * **Regla 8.** Ningun motivo que llega al cliente contiene el texto de
      una excepcion ajena; los errores inesperados se registran solo por
      su tipo (regla 9: el mensaje de una excepcion puede llevar datos de
      la tabla) y el cliente recibe un motivo fijo y comprensible.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Final

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from dataclean.carga import ErrorDeCargaInesperado, cargar_tabla
from dataclean.clasificacion import RolColumna, clasificar_columnas
from dataclean.correo import validar_columna_correo
from dataclean.duplicados import (
    detectar_duplicados_por_nombre,
    detectar_duplicados_por_telefono,
)
from dataclean.exportar import ErrorDeExportacion, exportar_tabla
from dataclean.nombre import normalizar_columna_nombre
from dataclean.reporte import generar_reporte
from dataclean.resumen import redactar_resumen
from dataclean.telefono import clasificar_columna_telefono, normalizar_columna_telefono


# Nombre de la variable de entorno que el operador puede usar para
# sobreescribir el tamano maximo por defecto (DC.13 Cierre 3).
ENV_TAMANO_MAXIMO: Final[str] = "DATACLEAN_MAX_BYTES"

# Tamano maximo por defecto: 10 MiB. Es lo que un Excel de 50k filas
# suele pesar; subirlo exige intervencion del operador.
TAMANO_MAXIMO_POR_DEFECTO: Final[int] = 10 * 1024 * 1024

# Horas que un archivo limpio se conserva en disco antes de borrarse. Un
# archivo de contactos es una lista de datos personales (regla 9): no se
# guarda mas de lo que el cliente tarda en descargarlo.
ENV_HORAS_RETENCION: Final[str] = "DATACLEAN_HORAS_RETENCION"
HORAS_RETENCION_POR_DEFECTO: Final[int] = 24

# Subcarpeta dentro de ``tempfile.gettempdir()`` donde se guardan los
# archivos limpios por id.
CARPETA_POR_DEFECTO: Final[str] = "dataclean_limpios"

# Formatos en los que se puede descargar el archivo limpio. El primero es
# el que devuelve ``descargar_por_id`` si no se pide otro.
FORMATOS_DESCARGA: Final[tuple[str, ...]] = ("csv", "xlsx")

_TIPOS_MIME: Final[dict[str, str]] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Un id valido es exactamente lo que genera ``_generar_id``. Validarlo
# antes de construir una ruta impide que un id como ``../algo`` salga de
# la carpeta de salida.
_PATRON_ID: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{16}$")

# Holgura sobre el tamano maximo para las cabeceras del cuerpo multipart
# (limites, nombre del campo, tipo de contenido).
_MARGEN_MULTIPART: Final[int] = 64 * 1024

MOTIVO_NO_LEGIBLE: Final[str] = (
    "no se pudo leer el archivo: comprueba que sea un .csv o un .xlsx válido"
)
MOTIVO_SIN_FILAS: Final[str] = (
    "el archivo tiene cabecera pero ninguna fila de contactos"
)
MOTIVO_ERROR_INTERNO: Final[str] = (
    "No pudimos procesar el archivo por un error interno. Ya quedó "
    "registrado; vuelve a intentarlo en unos minutos."
)
MOTIVO_ID_NO_DISPONIBLE: Final[str] = (
    "Ese archivo ya no está disponible: los archivos limpios se borran "
    "pasado un tiempo para proteger tus datos. Vuelve a subir el original."
)
MOTIVO_FORMATO_NO_SOPORTADO: Final[str] = (
    "Formato de descarga no soportado: usa csv o xlsx."
)

# Columnas que DC.8 y DC.9 anaden con el mismo nombre (``grupo_id``,
# ``es_duplicado``...). En el archivo limpio conviven las dos marcas, asi
# que cada una se renombra con su prefijo.
_RENOMBRE_DUPLICADO_TELEFONO: Final[dict[str, str]] = {
    "grupo_id": "duplicado_telefono_grupo",
    "es_duplicado": "duplicado_telefono",
    "motivo_conservar": "duplicado_telefono_motivo",
}
_RENOMBRE_DUPLICADO_NOMBRE: Final[dict[str, str]] = {
    "grupo_id": "duplicado_nombre_grupo",
    "es_duplicado": "duplicado_nombre",
    "sospechoso": "duplicado_nombre_sospechoso",
    "motivo_conservar": "duplicado_nombre_motivo",
}
_MOTIVO_SIN_COLUMNA_NOMBRE: Final[str] = "la columna de nombre no esta en la tabla"

_logger = logging.getLogger("dataclean.endpoint")


class ErrorDeSubida(ValueError):
    """Error de la capa HTTP al recibir un archivo.

    Se levanta cuando:
      * el archivo viene vacio o sin filas,
      * el archivo excede el tamano maximo configurado,
      * ``cargar_tabla`` no puede leer el contenido (CSV mal formado,
        XLSX corrupto, binario aleatorio),
      * ``exportar_tabla`` no puede escribir el archivo limpio.

    El atributo ``motivo`` lleva la cadena legible que se devuelve al
    cliente. Regla 8: nada de stacktrace al usuario.
    """

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo: str = motivo


@dataclass
class _Normalizacion:
    """Resultado de la fase de normalizacion del pipeline."""

    tabla: pd.DataFrame
    columna_nombre: str | None
    columna_telefono: str | None
    columna_correo: str | None


def _entero_de_entorno(nombre: str, por_defecto: int) -> int:
    """Lee un entero de una variable de entorno; si no es valido, el defecto."""
    valor = os.environ.get(nombre)
    if valor is None or not valor.strip():
        return por_defecto
    try:
        return int(valor)
    except ValueError:
        return por_defecto


def _tamano_legible(bytes_: int) -> str:
    """``10485760`` -> ``"10 MB"``; por debajo de 1 KB, en bytes."""
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.0f} MB"
    if bytes_ >= 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_} bytes"


def motivo_tamano_excedido(tamano_maximo_bytes: int) -> str:
    """Motivo legible para una subida que supera el tamano maximo."""
    return (
        "el archivo supera el tamaño máximo permitido "
        f"({_tamano_legible(tamano_maximo_bytes)})"
    )


class ServicioLimpieza:
    """Orquesta el pipeline de DataClean para una peticion HTTP.

    La instancia concentra el estado de cada despliegue: carpeta donde se
    escriben los archivos limpios, tamano maximo aceptado y horas de
    retencion. El caller (FastAPI o tests) crea una instancia por app.
    """

    def __init__(
        self,
        carpeta_salida: str | os.PathLike[str] | None = None,
        tamano_maximo_bytes: int | None = None,
        horas_retencion: int | None = None,
    ) -> None:
        if carpeta_salida is None:
            base = Path(tempfile.gettempdir()) / CARPETA_POR_DEFECTO
        else:
            base = Path(carpeta_salida)
        self._carpeta_salida: Path = base
        if tamano_maximo_bytes is None:
            tamano_maximo_bytes = _entero_de_entorno(
                ENV_TAMANO_MAXIMO, TAMANO_MAXIMO_POR_DEFECTO
            )
        if tamano_maximo_bytes <= 0:
            raise ValueError("tamano_maximo_bytes debe ser positivo")
        self._tamano_maximo_bytes: int = tamano_maximo_bytes
        if horas_retencion is None:
            horas_retencion = _entero_de_entorno(
                ENV_HORAS_RETENCION, HORAS_RETENCION_POR_DEFECTO
            )
        if horas_retencion <= 0:
            raise ValueError("horas_retencion debe ser positivo")
        self._horas_retencion: int = horas_retencion

    @property
    def carpeta_salida(self) -> Path:
        return self._carpeta_salida

    @property
    def tamano_maximo_bytes(self) -> int:
        return self._tamano_maximo_bytes

    @property
    def horas_retencion(self) -> int:
        return self._horas_retencion

    def _asegurar_carpeta(self) -> None:
        self._carpeta_salida.mkdir(parents=True, exist_ok=True)

    def _generar_id(self) -> str:
        return secrets.token_hex(8)

    def _ruta_para_id(self, id_limpieza: str, formato: str = "csv") -> Path | None:
        """Ruta del archivo limpio, o ``None`` si el id o el formato no valen."""
        if not _PATRON_ID.match(id_limpieza) or formato not in FORMATOS_DESCARGA:
            return None
        return self._carpeta_salida / f"{id_limpieza}.{formato}"

    def existe(self, id_limpieza: str) -> bool:
        ruta = self._ruta_para_id(id_limpieza)
        return ruta is not None and ruta.exists()

    def ruta_de_descarga(
        self, id_limpieza: str, formato: str = "csv"
    ) -> Path | None:
        ruta = self._ruta_para_id(id_limpieza, formato)
        if ruta is not None and ruta.exists():
            return ruta
        return None

    def borrar_expirados(self) -> int:
        """Borra los archivos limpios mas viejos que la retencion.

        Solo toca archivos cuyo nombre es un id de este servicio, para no
        borrar nada ajeno si la carpeta de salida es compartida. Devuelve
        cuantos borro.
        """
        if not self._carpeta_salida.is_dir():
            return 0
        limite = time.time() - self._horas_retencion * 3600
        borrados = 0
        for ruta in self._carpeta_salida.iterdir():
            if not (ruta.is_file() and _PATRON_ID.match(ruta.stem)):
                continue
            try:
                if ruta.stat().st_mtime < limite:
                    ruta.unlink()
                    borrados += 1
            except OSError:
                continue
        return borrados

    def procesar(
        self,
        contenido: bytes,
        nombre_archivo: str | None = None,
        columna_telefono: str | None = None,
        columna_correo: str | None = None,
        columna_nombre: str | None = None,
    ) -> dict[str, Any]:
        if contenido is None:
            raise ErrorDeSubida("no se recibió contenido en la petición")
        if len(contenido) == 0:
            raise ErrorDeSubida("el archivo está vacío")
        if len(contenido) > self._tamano_maximo_bytes:
            raise ErrorDeSubida(motivo_tamano_excedido(self._tamano_maximo_bytes))
        nombre = nombre_archivo or "subida.csv"
        try:
            tabla = _cargar_tabla_desde_bytes(contenido, nombre)
        except ErrorDeCargaInesperado as exc:
            raise ErrorDeSubida(f"no se pudo leer el archivo: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            _logger.error("fallo inesperado al leer una subida: %s", type(exc).__name__)
            raise ErrorDeSubida(MOTIVO_NO_LEGIBLE) from exc
        if len(tabla) == 0:
            raise ErrorDeSubida(MOTIVO_SIN_FILAS)

        normalizacion = _normalizar(
            tabla,
            columna_telefono=columna_telefono,
            columna_correo=columna_correo,
            columna_nombre=columna_nombre,
        )
        reporte = generar_reporte(
            normalizacion.tabla,
            columna_telefono=normalizacion.columna_telefono,
            columna_correo=normalizacion.columna_correo,
        )
        reporte_dict = _reporte_a_dict(reporte)
        reporte_dict["duplicados_por_nombre"] = _duplicados_por_nombre_a_dict(
            normalizacion.tabla
        )
        reporte_dict["columnas_detectadas"] = {
            "telefono": normalizacion.columna_telefono,
            "correo": normalizacion.columna_correo,
            "nombre": normalizacion.columna_nombre,
        }
        reporte_dict["resumen"] = redactar_resumen(reporte_dict)

        self._asegurar_carpeta()
        self.borrar_expirados()
        id_limpieza = self._generar_id()
        rutas = [
            self._carpeta_salida / f"{id_limpieza}.{formato}"
            for formato in FORMATOS_DESCARGA
        ]
        try:
            for ruta in rutas:
                exportar_tabla(normalizacion.tabla, ruta)
        except Exception as exc:  # noqa: BLE001
            for ruta in rutas:
                ruta.unlink(missing_ok=True)
            if isinstance(exc, ErrorDeExportacion):
                raise ErrorDeSubida(
                    f"no se pudo escribir el archivo limpio: {exc}"
                ) from exc
            _logger.error("fallo inesperado al exportar: %s", type(exc).__name__)
            raise ErrorDeSubida("no se pudo escribir el archivo limpio") from exc

        return {
            "id": id_limpieza,
            "nombre_original": nombre,
            "tamano": rutas[0].stat().st_size,
            "ruta": str(rutas[0]),
            "formatos": list(FORMATOS_DESCARGA),
            "reporte": reporte_dict,
        }


def _cargar_tabla_desde_bytes(contenido: bytes, nombre_archivo: str) -> pd.DataFrame:
    """Vuelca los bytes a un temporal y delega en ``cargar_tabla``.

    ``cargar_tabla`` recibe una ruta; el endpoint recibe bytes. El puente
    minimo es un temporal que se borra al salir.
    """
    fd, ruta_temporal = tempfile.mkstemp(
        prefix="dataclean_subida_", suffix=_sufijo_de(nombre_archivo)
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(contenido)
        return cargar_tabla(ruta_temporal)
    finally:
        try:
            os.unlink(ruta_temporal)
        except OSError:
            pass


def _sufijo_de(nombre_archivo: str) -> str:
    """Devuelve la extension de ``nombre_archivo`` o ``.csv``."""
    _, _, sufijo = nombre_archivo.rpartition(".")
    if not sufijo or len(sufijo) > 5 or not sufijo.isalnum():
        return ".csv"
    return f".{sufijo.lower()}"


def _primera_columna_con_rol(
    roles: dict[str, RolColumna], rol: RolColumna
) -> str | None:
    for nombre, rol_columna in roles.items():
        if rol_columna == rol:
            return nombre
    return None


def _normalizar(
    tabla: pd.DataFrame,
    columna_telefono: str | None,
    columna_correo: str | None,
    columna_nombre: str | None,
) -> _Normalizacion:
    """DC.2 (clasificar) + DC.3/4 (tel) + DC.5 (correo) + DC.6 (nombre) + DC.8/9."""
    if columna_telefono is None or columna_correo is None or columna_nombre is None:
        roles = clasificar_columnas(tabla)
        columna_telefono = columna_telefono or _primera_columna_con_rol(
            roles, RolColumna.TELEFONO
        )
        columna_correo = columna_correo or _primera_columna_con_rol(
            roles, RolColumna.CORREO
        )
        columna_nombre = columna_nombre or _primera_columna_con_rol(
            roles, RolColumna.NOMBRE
        )
    if columna_telefono not in tabla.columns:
        columna_telefono = None
    if columna_correo not in tabla.columns:
        columna_correo = None
    if columna_nombre not in tabla.columns:
        columna_nombre = None

    if columna_telefono:
        tabla = normalizar_columna_telefono(tabla, columna_telefono)
        tabla = clasificar_columna_telefono(tabla, columna_telefono)
    if columna_correo:
        tabla = validar_columna_correo(tabla, columna_correo)
    if columna_nombre:
        tabla = normalizar_columna_nombre(tabla, columna_nombre)
    tabla = _marcar_duplicados(tabla, columna_telefono, columna_nombre)
    return _Normalizacion(
        tabla=tabla,
        columna_nombre=columna_nombre,
        columna_telefono=columna_telefono,
        columna_correo=columna_correo,
    )


def _marcar_duplicados(
    tabla: pd.DataFrame,
    columna_telefono: str | None,
    columna_nombre: str | None,
) -> pd.DataFrame:
    """Anade al archivo limpio las marcas de DC.8 y DC.9, con prefijo propio.

    Sin esto el reporte cuenta grupos de duplicados que el cliente no
    puede localizar en el archivo que descarga. El canonico que DC.8/DC.9
    calculan por su cuenta ya esta en las columnas de DC.3/DC.6, asi que
    no se duplica.
    """
    if columna_telefono:
        tabla = (
            detectar_duplicados_por_telefono(tabla, columna_telefono)
            .drop(columns=["telefono_canon"])
            .rename(columns=_RENOMBRE_DUPLICADO_TELEFONO)
        )
    if columna_nombre:
        tabla = (
            detectar_duplicados_por_nombre(tabla, columna_nombre)
            .drop(columns=[f"{columna_nombre}_nombre_canon"])
            .rename(columns=_RENOMBRE_DUPLICADO_NOMBRE)
        )
    return tabla


def _reporte_a_dict(reporte: Any) -> dict[str, Any]:
    """Serializa un :class:`Reporte` a un dict JSON-amigable."""
    return {
        "total_registros": reporte.registros_totales,
        "telefonos_normalizados": _cifra_a_dict(reporte.telefonos_normalizados),
        "telefonos_moviles": _cifra_a_dict(reporte.telefonos_moviles),
        "telefonos_fijos": _cifra_a_dict(reporte.telefonos_fijos),
        "telefonos_invalidos": _cifra_a_dict(reporte.telefonos_invalidos),
        "correos_marcados": _cifra_a_dict(reporte.correos_marcados),
        "grupos_duplicados": _grupos_a_dict(reporte.grupos_duplicados),
        "total_grupos_duplicados": _cifra_a_dict(reporte.total_grupos_duplicados),
    }


def _grupos_a_dict(grupos: Any) -> dict[str, Any]:
    """Serializa la tupla de ``GrupoDuplicados`` a un dict JSON."""
    serializados = [{"id": g.id, "filas": list(g.filas)} for g in grupos]
    return {"valor": len(serializados), "grupos": serializados}


def _cifra_a_dict(cifra: Any) -> dict[str, Any]:
    """Serializa una :class:`Cifra`, con sus filas (DC.10 Cierre 2)."""
    return {
        "valor": cifra.valor,
        "disponible": cifra.disponible,
        "motivo": cifra.motivo,
        "filas": list(cifra.filas),
    }


def _duplicados_por_nombre_a_dict(tabla: pd.DataFrame) -> dict[str, Any]:
    """Grupos de DC.9 con mas de una fila; cada uno dice si es sospechoso."""
    if "duplicado_nombre_grupo" not in tabla.columns:
        return {
            "valor": None,
            "disponible": False,
            "motivo": _MOTIVO_SIN_COLUMNA_NOMBRE,
            "grupos": [],
        }
    grupos: dict[str, dict[str, Any]] = {}
    pares = zip(tabla["duplicado_nombre_grupo"], tabla["duplicado_nombre_sospechoso"])
    for posicion, (grupo_id, sospechoso) in enumerate(pares):
        if not grupo_id:
            continue
        grupo = grupos.setdefault(grupo_id, {"filas": [], "sospechoso": False})
        grupo["filas"].append(posicion)
        grupo["sospechoso"] = grupo["sospechoso"] or bool(sospechoso)
    lista = [g for g in grupos.values() if len(g["filas"]) > 1]
    return {"valor": len(lista), "disponible": True, "motivo": "", "grupos": lista}


_servicio_por_defecto: ServicioLimpieza | None = None


def obtener_servicio() -> ServicioLimpieza:
    """Devuelve el ``ServicioLimpieza`` por defecto del proceso."""
    global _servicio_por_defecto
    if _servicio_por_defecto is None:
        _servicio_por_defecto = ServicioLimpieza()
    return _servicio_por_defecto


def _reiniciar_servicio(
    carpeta_salida: str | os.PathLike[str] | None = None,
    tamano_maximo_bytes: int | None = None,
) -> ServicioLimpieza:
    global _servicio_por_defecto
    _servicio_por_defecto = ServicioLimpieza(
        carpeta_salida=carpeta_salida,
        tamano_maximo_bytes=tamano_maximo_bytes,
    )
    return _servicio_por_defecto


def procesar_subida(
    contenido: bytes,
    nombre_archivo: str | None = None,
    columna_telefono: str | None = None,
    columna_correo: str | None = None,
    columna_nombre: str | None = None,
    servicio: ServicioLimpieza | None = None,
) -> dict[str, Any]:
    """Punto de entrada publico del endpoint (DC.13 Cierre 1)."""
    svc = servicio if servicio is not None else obtener_servicio()
    return svc.procesar(
        contenido,
        nombre_archivo=nombre_archivo,
        columna_telefono=columna_telefono,
        columna_correo=columna_correo,
        columna_nombre=columna_nombre,
    )


def descargar_por_id(
    id_limpieza: str,
    servicio: ServicioLimpieza | None = None,
    formato: str = "csv",
) -> tuple[bytes, str] | None:
    """Devuelve ``(contenido, nombre)`` del archivo limpio, o ``None``."""
    svc = servicio if servicio is not None else obtener_servicio()
    ruta = svc.ruta_de_descarga(id_limpieza, formato)
    if ruta is None:
        return None
    return ruta.read_bytes(), ruta.name


@lru_cache(maxsize=1)
def _pagina_web() -> str:
    """HTML de la pagina de subida (DC.16), empaquetado con el modulo."""
    return (
        resources.files("dataclean")
        .joinpath("web/index.html")
        .read_text(encoding="utf-8")
    )


def crear_app(servicio: ServicioLimpieza | None = None) -> FastAPI:
    """Crea la app FastAPI: la API y la pagina web que la consume.

    FastAPI se importa a nivel de modulo, no aqui dentro: con
    ``from __future__ import annotations`` las anotaciones de las rutas son
    cadenas que FastAPI resuelve contra los globales del modulo, y un
    ``UploadFile`` importado localmente no se encuentra (``POST /procesar``
    fallaba con ``PydanticUserError``).

    Las rutas de trabajo son ``def`` (no ``async def``): FastAPI las corre
    en su pool de hilos, asi un archivo grande de un usuario no congela
    las peticiones de los demas mientras pandas lo procesa.
    """
    svc = servicio if servicio is not None else ServicioLimpieza()
    app = FastAPI(
        title="DataClean AI",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def _limitar_y_proteger(request: Request, call_next: Any) -> Any:
        # Rechaza el cuerpo por su cabecera antes de que el parser
        # multipart lo escriba entero a disco.
        if request.url.path == "/procesar":
            longitud = request.headers.get("content-length", "")
            limite = svc.tamano_maximo_bytes + _MARGEN_MULTIPART
            if longitud.isdigit() and int(longitud) > limite:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": {
                            "motivo": motivo_tamano_excedido(svc.tamano_maximo_bytes),
                            "tamano_maximo": svc.tamano_maximo_bytes,
                        }
                    },
                )
        respuesta = await call_next(request)
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["X-Frame-Options"] = "DENY"
        return respuesta

    @app.exception_handler(Exception)
    async def _error_inesperado(request: Request, exc: Exception) -> Any:
        # Solo el tipo: el mensaje de una excepcion puede llevar datos de
        # la tabla (regla 9).
        _logger.error(
            "error inesperado en %s: %s", request.url.path, type(exc).__name__
        )
        return JSONResponse(
            status_code=500, content={"detail": {"motivo": MOTIVO_ERROR_INTERNO}}
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def _inicio() -> Any:
        return HTMLResponse(
            _pagina_web(),
            headers={
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                    "frame-ancestors 'none'"
                )
            },
        )

    @app.get("/configuracion")
    def _configuracion() -> dict[str, Any]:
        return {
            "tamano_maximo_bytes": svc.tamano_maximo_bytes,
            "horas_retencion": svc.horas_retencion,
            "formatos_descarga": list(FORMATOS_DESCARGA),
        }

    @app.post("/procesar")
    def _procesar(archivo: UploadFile = File(...)) -> dict[str, Any]:
        # Se lee un byte de mas: si llega, el archivo supera el limite y
        # ``procesar`` lo rechaza sin haber cargado el resto en memoria.
        contenido = archivo.file.read(svc.tamano_maximo_bytes + 1)
        try:
            resultado = procesar_subida(
                contenido, nombre_archivo=archivo.filename, servicio=svc
            )
        except ErrorDeSubida as exc:
            raise HTTPException(
                status_code=400,
                detail={"motivo": exc.motivo, "tamano_maximo": svc.tamano_maximo_bytes},
            ) from exc
        # La ruta en disco del servidor no es asunto del cliente.
        resultado.pop("ruta", None)
        return resultado

    @app.get("/descargar/{id_limpieza}")
    def _descargar(id_limpieza: str, formato: str = "csv") -> Any:
        if formato not in FORMATOS_DESCARGA:
            raise HTTPException(
                status_code=400, detail={"motivo": MOTIVO_FORMATO_NO_SOPORTADO}
            )
        resultado = descargar_por_id(id_limpieza, servicio=svc, formato=formato)
        if resultado is None:
            raise HTTPException(status_code=404, detail={"motivo": MOTIVO_ID_NO_DISPONIBLE})
        contenido, _ = resultado
        return Response(
            content=contenido,
            media_type=_TIPOS_MIME[formato],
            headers={
                "Content-Disposition": (
                    f'attachment; filename="contactos_limpios.{formato}"'
                )
            },
        )

    return app
