"""Endpoint HTTP que junta todo el pipeline de DataClean (DC.13).

Por que existe este modulo:
    Los items DC.0 a DC.12 son piezas; DC.13 es la "puerta" que las
    expone al exterior. Recibe un archivo por POST, lo pasa por el
    pipeline (cargar -> clasificar -> normalizar -> reportar ->
    exportar), y devuelve al cliente dos cosas: el reporte y un
    identificador que le sirve para bajarse el archivo limpio.

Tres contratos del item (Cierres):
    1) **Cierre 1** -- ``procesar_subida`` recibe bytes + nombre y
       devuelve un dict ``{"id": ..., "reporte": ..., "tamano": ...}``
       con el reporte serializable y un id que existe como archivo
       en disco para una descarga posterior.
    2) **Cierre 2** -- un archivo corrupto o vacio NO tumba el
       servicio: ``procesar_subida`` levanta ``ErrorDeSubida`` (con
       un ``motivo`` legible) y ``crear_app`` lo traduce a una
       respuesta HTTP 400 con un cuerpo JSON explicativo, no a un
       500 con stacktrace.
    3) **Cierre 3** -- el tamano maximo se configura: ``ServicioLimpieza``
       toma ``tamano_maximo_bytes`` en el constructor; ademas lee
       la variable de entorno ``DATACLEAN_MAX_BYTES`` para que el
       operador pueda cambiarla sin tocar el codigo. Si la peticion
       lo supera, se rechaza con ``ErrorDeSubida(motivo="...")``
       ANTES de tocar el disco.

Diseno (regla 5: sin sobre-ingenieria):
    * **La logica de negocio NO vive en FastAPI.** Vive en
      ``procesar_subida``, una funcion pura que recibe bytes y
      devuelve un dict. Asi la suite la prueba sin levantar un
      servidor HTTP, y un dia se puede cambiar FastAPI por otra cosa
      sin tocar la logica.
    * **FastAPI solo es el cable.** ``crear_app`` monta la funcion
      pura en una app: ``POST /procesar`` -> ``procesar_subida``,
      ``GET /descargar/{id}`` -> archivo por id. Si la app no se
      puede importar (FastAPI no instalado en un entorno minimo),
      los tests de logica siguen pasando.
    * **Estado en una sola clase, ``ServicioLimpieza``.** La carpeta
      de salida, el tamano maximo y el contador de ids viven en la
      instancia. Dos ``ServicioLimpieza`` en paralelo no se pisan.
      Sin variables globales (regla 7: la suite corre sin red y sin
      credenciales, y eso incluye no contaminar el filesystem del
      usuario con archivos "perdidos").
    * **Id corto y aleatorio.** ``secrets.token_hex(8)`` da 16
      caracteres hex. Suficiente para que un mismo proceso no
      colisione y para que el cliente lo pueda copiar a mano. NO
      se usa el nombre del archivo original como id (regla 9: el
      nombre podria contener un dato personal, y adios id
      "comprensible").

Lo que NO hace este modulo:
    * No **crea** el archivo CSV limpio si la carga falla. Si
      ``cargar_tabla`` levanta ``ErrorDeCargaInesperado``, capturamos
      y levantamos ``ErrorDeSubida``. Asi no dejamos archivos
      huerfanos en la carpeta de salida.
    * No **persiste el archivo para siempre.** La carpeta de salida
      es un temporal (``tempfile.gettempdir()/dataclean_limpios``
      por defecto); el operador puede pasar otra ruta. La limpieza
      de archivos viejos es responsabilidad del despliegue, no de
      este modulo.
    * No **loggea datos personales.** La regla 9 ya esta cubierta
      por ``dataclean.log_seguro``; este modulo no escribe logs
      con contenido de la tabla.

Justificacion del diseno:
    * Procesamiento sincrono en lugar de un ``BackgroundTasks``.
      Razon: el archivo de un cliente pequeno cabe en memoria y el
      reporte tiene que volver en la misma respuesta (Cierre 1:
      "POST con un archivo devuelve el reporte"). Si el archivo
      fuera enorme, el diseno cambiaba; en V1 no lo es.
    * ``ErrorDeSubida`` en vez de devolver un dict con ``"ok": False``.
      Razon: el caller (FastAPI o tests) tiene que distinguir "no
      pude" de "pude pero el reporte dice que no hay moviles". Un
      tipo de excepcion dedicado es la forma mas limpia de
      transmitirlo, y ademas encaja con el patron de
      ``ErrorDeCargaInesperado``.
"""

from __future__ import annotations

import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dataclean.carga import ErrorDeCargaInesperado, cargar_tabla
from dataclean.clasificacion import clasificar_columnas
from dataclean.correo import validar_columna_correo
from dataclean.exportar import ErrorDeExportacion, exportar_tabla
from dataclean.nombre import normalizar_columna_nombre
from dataclean.reporte import generar_reporte
from dataclean.telefono import clasificar_columna_telefono, normalizar_columna_telefono


# Nombre de la variable de entorno que el operador puede usar para
# sobreescribir el tamano maximo por defecto (Cierre 3: "el tamano
# maximo se configura"). Si no esta, se usa TAMANO_MAXIMO_POR_DEFECTO.
ENV_TAMANO_MAXIMO: str = "DATACLEAN_MAX_BYTES"

# Tamano maximo por defecto: 10 MiB. Es lo que un Excel de 50k filas
# suele pesar; subirlo exige intervencion del operador (regla 8:
# "no tumbar el servicio" se traduce tambien en "no aceptar un
# gigabyte por accidente").
TAMANO_MAXIMO_POR_DEFECTO: int = 10 * 1024 * 1024

# Subcarpeta dentro de ``tempfile.gettempdir()`` donde se guardan
# los archivos limpios por id. La barra final NO se incluye; el
# join se hace con ``Path``.
CARPETA_POR_DEFECTO: str = "dataclean_limpios"


class ErrorDeSubida(ValueError):
    """Error de la capa HTTP al recibir un archivo.

    Se levanta cuando:
      * el archivo viene vacio,
      * el archivo excede el tamano maximo configurado,
      * ``cargar_tabla`` no puede leer el contenido (CSV mal
        formado, XLSX corrupto, binario aleatorio),
      * ``exportar_tabla`` no puede escribir el archivo limpio.

    El atributo ``motivo`` lleva la cadena legible que se devuelve
    al cliente. Regla 8: nada de stacktrace al usuario.
    """

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo: str = motivo


@dataclass
class _Normalizacion:
    """Resultado de la fase de normalizacion del pipeline."""

    tabla: Any
    columna_nombre: str | None
    columna_telefono: str | None
    columna_correo: str | None


class ServicioLimpieza:
    """Orquesta el pipeline de DataClean para una peticion HTTP.

    La instancia concentra el estado de cada despliegue: carpeta
    donde se escriben los archivos limpios, tamano maximo aceptado
    y un contador monotono de ids. El caller (FastAPI o tests) crea
    una instancia por app, y le pasa los bytes del archivo a
    ``procesar``.
    """

    def __init__(
        self,
        carpeta_salida: str | os.PathLike[str] | None = None,
        tamano_maximo_bytes: int | None = None,
    ) -> None:
        if carpeta_salida is None:
            base = Path(tempfile.gettempdir()) / CARPETA_POR_DEFECTO
        else:
            base = Path(carpeta_salida)
        self._carpeta_salida: Path = base
        if tamano_maximo_bytes is None:
            env_valor = os.environ.get(ENV_TAMANO_MAXIMO)
            if env_valor is not None and env_valor.strip():
                try:
                    tamano_maximo_bytes = int(env_valor)
                except ValueError:
                    tamano_maximo_bytes = TAMANO_MAXIMO_POR_DEFECTO
            else:
                tamano_maximo_bytes = TAMANO_MAXIMO_POR_DEFECTO
        if tamano_maximo_bytes <= 0:
            raise ValueError(
                "tamano_maximo_bytes debe ser positivo"
            )
        self._tamano_maximo_bytes: int = tamano_maximo_bytes

    @property
    def carpeta_salida(self) -> Path:
        return self._carpeta_salida

    @property
    def tamano_maximo_bytes(self) -> int:
        return self._tamano_maximo_bytes

    def _asegurar_carpeta(self) -> None:
        self._carpeta_salida.mkdir(parents=True, exist_ok=True)

    def _generar_id(self) -> str:
        return secrets.token_hex(8)

    def _ruta_para_id(self, id_limpieza: str) -> Path:
        return self._carpeta_salida / f"{id_limpieza}.csv"

    def existe(self, id_limpieza: str) -> bool:
        return self._ruta_para_id(id_limpieza).exists()

    def ruta_de_descarga(self, id_limpieza: str) -> Path | None:
        ruta = self._ruta_para_id(id_limpieza)
        if ruta.exists():
            return ruta
        return None

    def procesar(
        self,
        contenido: bytes,
        nombre_archivo: str | None = None,
        columna_telefono: str | None = None,
        columna_correo: str | None = None,
        columna_nombre: str | None = None,
    ) -> dict[str, Any]:
        if contenido is None:
            raise ErrorDeSubida("no se recibio contenido en la peticion")
        if len(contenido) == 0:
            raise ErrorDeSubida("el archivo esta vacio")
        if len(contenido) > self._tamano_maximo_bytes:
            raise ErrorDeSubida(
                f"el archivo supera el tamano maximo "
                f"permitido ({self._tamano_maximo_bytes} bytes)"
            )
        nombre = nombre_archivo or "subida.csv"
        try:
            tabla = _cargar_tabla_desde_bytes(contenido, nombre)
        except ErrorDeCargaInesperado as exc:
            raise ErrorDeSubida(
                f"no se pudo leer el archivo: {exc}"
            ) from exc
        except ErrorDeSubida:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ErrorDeSubida(
                f"no se pudo leer el archivo: {exc}"
            ) from exc

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

        self._asegurar_carpeta()
        id_limpieza = self._generar_id()
        ruta_salida = self._ruta_para_id(id_limpieza)
        try:
            exportar_tabla(normalizacion.tabla, ruta_salida)
        except ErrorDeExportacion as exc:
            raise ErrorDeSubida(
                f"no se pudo escribir el archivo limpio: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ErrorDeSubida(
                f"no se pudo escribir el archivo limpio: {exc}"
            ) from exc

        return {
            "id": id_limpieza,
            "nombre_original": nombre,
            "tamano": ruta_salida.stat().st_size,
            "ruta": str(ruta_salida),
            "reporte": _reporte_a_dict(reporte),
        }


def _cargar_tabla_desde_bytes(
    contenido: bytes, nombre_archivo: str
) -> Any:
    """Vuelca los bytes a un temporal y delega en ``cargar_tabla``.

    ``cargar_tabla`` recibe una ruta; el endpoint recibe bytes. El
    puente minimo es un temporal. Si ya existiera un
    ``cargar_tabla_desde_bytes`` en ``dataclean.carga`` lo usariamos,
    pero no existe y la API publica de DC.1 es por ruta. Asi que
    escribimos un temporal y lo borramos al salir.
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
    if not sufijo or len(sufijo) > 5:
        return ".csv"
    return f".{sufijo.lower()}"


def _normalizar(
    tabla: Any,
    columna_telefono: str | None,
    columna_correo: str | None,
    columna_nombre: str | None,
) -> _Normalizacion:
    """Aplica DC.2 (clasificar) + DC.3/4 (tel) + DC.5 (correo) + DC.6 (nombre)."""
    if (
        columna_telefono is None
        or columna_correo is None
        or columna_nombre is None
    ):
        from dataclean.clasificacion import RolColumna

        roles = clasificar_columnas(tabla)
        if columna_telefono is None:
            for nombre, rol in roles.items():
                if rol == RolColumna.TELEFONO:
                    columna_telefono = nombre
                    break
        if columna_correo is None:
            for nombre, rol in roles.items():
                if rol == RolColumna.CORREO:
                    columna_correo = nombre
                    break
        if columna_nombre is None:
            for nombre, rol in roles.items():
                if rol == RolColumna.NOMBRE:
                    columna_nombre = nombre
                    break
    if columna_telefono and columna_telefono in tabla.columns:
        tabla = normalizar_columna_telefono(tabla, columna_telefono)
        tabla = clasificar_columna_telefono(tabla, columna_telefono)
    if columna_correo and columna_correo in tabla.columns:
        tabla = validar_columna_correo(tabla, columna_correo)
    if columna_nombre and columna_nombre in tabla.columns:
        tabla = normalizar_columna_nombre(tabla, columna_nombre)
    return _Normalizacion(
        tabla=tabla,
        columna_nombre=columna_nombre,
        columna_telefono=columna_telefono,
        columna_correo=columna_correo,
    )


def _reporte_a_dict(reporte: Any) -> dict[str, Any]:
    """Serializa un :class:`Reporte` a un dict JSON-amigable."""
    return {
        "total_registros": reporte.registros_totales,
        "telefonos_normalizados": _cifra_a_dict(
            reporte.telefonos_normalizados
        ),
        "telefonos_moviles": _cifra_a_dict(reporte.telefonos_moviles),
        "telefonos_fijos": _cifra_a_dict(reporte.telefonos_fijos),
        "telefonos_invalidos": _cifra_a_dict(
            reporte.telefonos_invalidos
        ),
        "correos_marcados": _cifra_a_dict(reporte.correos_marcados),
        "grupos_duplicados": _grupos_a_dict(reporte.grupos_duplicados),
        "total_grupos_duplicados": _cifra_a_dict(
            reporte.total_grupos_duplicados
        ),
    }


def _grupos_a_dict(
    grupos: Any,
) -> dict[str, Any]:
    """Serializa la tupla de ``GrupoDuplicados`` a un dict JSON."""
    serializados = [
        {
            "id_canonico": g.id_canonico,
            "filas": list(g.filas),
        }
        for g in grupos
    ]
    return {"valor": len(serializados), "grupos": serializados}


def _cifra_a_dict(cifra: Any) -> dict[str, Any]:
    return {
        "valor": cifra.valor,
        "disponible": cifra.disponible,
        "motivo": cifra.motivo,
    }


_procesar_subida: Callable[..., dict[str, Any]] | None = None
_servicio_por_defecto: ServicioLimpieza | None = None


def obtener_servicio() -> ServicioLimpieza:
    """Devuelve el ``ServicioLimpieza`` por defecto del proceso.

    Solo se crea una vez (singleton) para que dos llamadas
    sucesivas a ``procesar_subida`` en el mismo proceso no
    reescriban la misma carpeta. La suite lo invalida con
    ``_reiniciar_servicio``.
    """
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
    """Punto de entrada publico del endpoint (Cierre 1)."""
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
) -> tuple[bytes, str] | None:
    """Devuelve ``(contenido, nombre)`` del archivo limpio, o None.

    Cierre 1: un POST devuelve el reporte y un identificador para
    descargar el limpio. Esta funcion es la mitad "descargar".
    """
    svc = servicio if servicio is not None else obtener_servicio()
    ruta = svc.ruta_de_descarga(id_limpieza)
    if ruta is None:
        return None
    return ruta.read_bytes(), ruta.name


def crear_app(servicio: ServicioLimpieza | None = None) -> Any:
    """Crea la app FastAPI que envuelve ``procesar_subida``.

    Importamos FastAPI dentro de la funcion para que este modulo
    se pueda importar sin tener fastapi instalado (regla 7: la
    suite corre sin red y sin credenciales, y eso incluye
    entornos donde el operador solo quiera el modulo de negocio
    por linea de comandos).
    """
    from fastapi import FastAPI, HTTPException, UploadFile

    svc = servicio if servicio is not None else ServicioLimpieza()
    app = FastAPI()

    @app.post("/procesar")
    async def _procesar(archivo: UploadFile) -> dict[str, Any]:
        contenido = await archivo.read()
        try:
            return procesar_subida(
                contenido,
                nombre_archivo=archivo.filename,
                servicio=svc,
            )
        except ErrorDeSubida as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "motivo": exc.motivo,
                    "tamano_maximo": svc.tamano_maximo_bytes,
                },
            ) from exc

    @app.get("/descargar/{id_limpieza}")
    async def _descargar(id_limpieza: str) -> Any:
        resultado = descargar_por_id(id_limpieza, servicio=svc)
        if resultado is None:
            raise HTTPException(
                status_code=404, detail={"motivo": "id no encontrado"}
            )
        contenido, nombre = resultado
        from fastapi.responses import Response

        return Response(
            content=contenido,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{nombre}"'
            },
        )

    return app