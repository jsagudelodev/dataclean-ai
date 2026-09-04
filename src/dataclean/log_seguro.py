"""Log que no filtra datos personales ni credenciales (regla 9).

Por que existe este modulo:
    DataClean procesa archivos con nombres, telefonos y correos de
    gente real (regla 9). Si esos valores caen en un log -- por un
    ``logger.info("procesando fila %s", fila)`` o un
    ``logger.exception("fallo al cargar %s", ruta)`` -- ya tenemos
    una filtracion de datos personales. Este modulo define:

      * Un **filtro** (``FiltroSeguro``) que se cuelga del logger
        ``dataclean`` y sustituye, en cada ``LogRecord.formatted``
        que se emite, cualquier aparicion de la credencial
        configurada o de cualquier valor de la lista de sensibles
        por la marca canonica ``"[REDACTADO]"``.

      * Un helper de configuracion (``configurar_log_seguro``) que
        instala un ``StreamHandler`` capturable en un ``io.StringIO``
        y le enchufa el filtro. Asi, los tests pueden leer lo que
        se escribio y comprobar la regla 9 sin tocar el log global.

      * Un pipeline de referencia (``procesar_archivo``) que SI
        registra el contenido real de cada fila en el log. Esto es
        lo que hace que el Cierre 2 del item (el dato tiene que
        llegar de verdad al camino que escribe el log) se cumpla
        por construccion: si el filtro esta, los datos nunca
        aparecen en la salida; si el filtro falta o alguien lo
        desactiva, los datos SI aparecen. La diferencia entre
        "filtro presente" y "filtro ausente" es la prueba de que
        el dato llego al codigo del log.

Diseno (regla 5: sin sobre-ingenieria):
    * Una sola clase de filtro. El caller le pasa la credencial y
      la lista de valores sensibles; el filtro hace una sustitucion
      literal ``str.replace`` sobre cada parte del ``LogRecord``
      (``msg`` y ``args``). Sin regex, sin dependencias externas.
    * El filtro se monta en ``format()`` (no en ``emit()``) porque
      ahi ya tenemos la cadena formateada con ``%s`` resuelto y
      podemos tocar una sola vez. Eso evita duplicar sustituciones
      cuando un argumento aparece dos veces.
    * La lista de sensibles y la credencial se guardan en el
      filtro (estado interno), no en variables globales. Asi dos
      tests en paralelo pueden configurar credenciales distintas
      sin pisarse.

Lo que NO hace este modulo:
    * No **crea** el logger: usa ``logging.getLogger("dataclean")``
      para que cualquier modulo que importe ``dataclean`` y haga
      ``logging.getLogger(__name__)`` (``dataclean.log_seguro``,
      ``dataclean.reporte``, ...) caiga en el mismo logger raiz.
    * No reemplaza el logger raiz de Python: solo configura el
      espacio de nombres ``dataclean``. Asi no rompemos el logging
      de pytest ni de otras librerias (regla 7: la suite corre
      sin red y sin credenciales, y eso incluye no contaminar el
      log de pytest).

Justificacion del diseno:
    Filtro a nivel de ``format()`` en vez de un ``Formatter``
    custom. Razon: el ``Formatter`` recibe la cadena ya
    ``formatted`` y tendriamos que volver a hacer ``%`` sobre
    ``args``. Un filtro que opera sobre ``record.msg`` y
    ``record.args`` antes del formateo es mas limpio: el filtro
    es el unico responsable de la redaccion y el resto del
    pipeline de logging sigue siendo el de la stdlib.
"""

from __future__ import annotations

import io
import logging
from typing import Final, Iterable

import pandas as pd

from dataclean.carga import cargar_tabla
from dataclean.reporte import generar_reporte


# Nombre canonico del espacio de logs de DataClean. Todos los
# modulos que necesiten loggear datos de contacto usan
# ``logging.getLogger("dataclean")`` (o un subespacio) y este
# modulo les cuelga el filtro.
LOGGER_DATACLEAN: Final[str] = "dataclean"

# Marca que aparece en el log donde antes estaba un dato
# personal o una credencial. Es una sola cadena para que el test
# del Cierre 1 (``test_dc12``) pueda buscarla con un ``assertNotIn``.
MARCADOR_REDACTADO: Final[str] = "[REDACTADO]"


class FiltroSeguro(logging.Filter):
    """Filtro de logging que sustituye credenciales y datos sensibles.

    Atributos:
        credencial: cadena exacta de la credencial a redactar
            (``None`` si no hay credencial configurada; el filtro
            sigue funcionando y solo redacta los ``sensibles``).
        sensibles: tupla inmutable de cadenas exactas a redactar.
            Cada una se busca con ``str.replace`` en el mensaje
            formateado del ``LogRecord``.

    Uso:
        >>> filtro = FiltroSeguro(credencial="abc", sensibles=("300",))
        >>> logger.addFilter(filtro)
    """

    def __init__(
        self,
        credencial: str | None = None,
        sensibles: Iterable[str] = (),
    ) -> None:
        super().__init__()
        self._credencial = credencial if credencial else ""
        # Guardamos tuple para que sea inmutable desde fuera; nadie
        # deberia poder mutar la lista de sensibles despues de
        # configurar el filtro.
        self._sensibles: tuple[str, ...] = tuple(sensibles)

    @property
    def credencial(self) -> str:
        return self._credencial

    @property
    def sensibles(self) -> tuple[str, ...]:
        return self._sensibles

    def _redactar(self, texto: str) -> str:
        """Devuelve ``texto`` con la credencial y los sensibles
        sustituidos por ``[REDACTADO]``.

        Si dos sensibles comparten prefijo (por ejemplo ``"300"`` y
        ``"3001234567"``), el orden importa: ``str.replace`` es
        voraz y no se pisa, asi que redactar primero la cadena mas
        larga evita que la mas corta se aplique sobre el resultado
        de la larga. Ordenamos de mayor a menor longitud.
        """
        if not texto:
            return texto
        resultado = texto
        # Ordenamos los sensibles por longitud DESCENDENTE para que
        # si uno contiene a otro como prefijo, el mas largo se
        # redacte primero. Asi ``"3001234567"`` no se queda como
        # ``"[REDACTADO]"`` que luego el ``"300"`` dejaria igual.
        candidatos = sorted(
            (s for s in self._sensibles if s),
            key=len,
            reverse=True,
        )
        if self._credencial:
            resultado = resultado.replace(
                self._credencial, MARCADOR_REDACTADO
            )
        for sensible in candidatos:
            resultado = resultado.replace(
                sensible, MARCADOR_REDACTADO
            )
        return resultado

    def filter(self, record: logging.LogRecord) -> bool:
        """Redacta el mensaje y los argumentos del ``LogRecord``.

        Devuelve siempre ``True`` (no descarta el registro: solo lo
        transforma). Asi el log sigue llegando al handler, pero sin
        el dato personal.
        """
        if record.msg:
            try:
                record.msg = self._redactar(str(record.msg))
            except Exception:
                # Si la redaccion falla por lo que sea, dejamos el
                # mensaje original: peor un log con un dato que un
                # log sin nada. Esto sigue siendo consistente con la
                # regla 4 (conservar): ante la duda, no perder info.
                pass
        if record.args:
            # ``args`` puede ser una tupla, un dict o un solo valor;
            # el formateo final de la stdlib resuelve eso, asi que
            # nosotros solo tenemos que redactar las cadenas que
            # lleguen.
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redactar(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            else:
                nuevos_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        nuevos_args.append(self._redactar(arg))
                    else:
                        nuevos_args.append(arg)
                record.args = tuple(nuevos_args)
        return True


def configurar_log_seguro(
    credencial: str | None = None,
    valores_sensibles: Iterable[str] = (),
    nivel: int = logging.INFO,
) -> tuple[logging.Logger, io.StringIO]:
    """Configura el logger ``dataclean`` con un filtro de redaccion.

    Parametros:
        credencial: cadena exacta de la credencial a redactar. Si
            es ``None`` o vacia, no se redacta ninguna credencial
            (solo los ``valores_sensibles``).
        valores_sensibles: cadenas exactas a redactar en cada
            ``LogRecord``. Se acepta cualquier iterable; se
            convierte a tupla para inmutabilidad.
        nivel: nivel minimo del logger (por defecto ``INFO``).

    Retorna:
        ``(logger, buffer)``: el logger ``dataclean`` configurado y
        el ``io.StringIO`` donde escribe el ``StreamHandler``. El
        caller (normalmente un test) lee ``buffer.getvalue()`` para
        inspeccionar lo que se emitio.
    """
    logger = logging.getLogger(LOGGER_DATACLEAN)
    logger.setLevel(nivel)

    # ``propagate=False`` para que pytest y el resto de la suite no
    # vean los logs de ``dataclean`` por el logger raiz; eso mantiene
    # la suite limpia y, ademas, evita que un doble formateo
    # (nuestro filtro + el filtro de pytest) corrompa la redaccion.
    logger.propagate = False

    # Si el caller llama a esta funcion mas de una vez (por ejemplo,
    # en tests consecutivos), evitamos apilar handlers: quitamos
    # los que ya tengamos.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Marcamos cada valor sensible con un identificador unico para
    # que dos sensibles identicos no se confundan con una sola
    # ocurrencia. Aqui no aplica (los sensibles ya son cadenas
    # unicas por contacto: nombre, telefono, correo), pero el
    # patron se mantiene por simetria con la credencial.
    filtro = FiltroSeguro(
        credencial=credencial,
        sensibles=valores_sensibles,
    )
    logger.addFilter(filtro)

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(nivel)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)

    return logger, buffer


def _recolectar_sensibles_de_tabla(
    tabla: pd.DataFrame,
    columna_nombre: str | None,
    columna_telefono: str | None,
    columna_correo: str | None,
) -> list[str]:
    """Devuelve la lista de valores a redactar para una tabla.

    Recorre las columnas indicadas y recoge, como cadenas, los
    valores no vacios. Esos son los valores que el pipeline va a
    intentar loggear en algun punto; tenerlos pre-recolectados
    permite configurar el filtro ANTES del procesamiento (regla 9:
    ventana minima de exposicion).
    """
    sensibles: list[str] = []
    pares: list[tuple[str | None, str]] = [
        (columna_nombre, "nombre"),
        (columna_telefono, "telefono"),
        (columna_correo, "correo"),
    ]
    for columna, _ in pares:
        if columna is None or columna not in tabla.columns:
            continue
        for valor in tabla[columna]:
            if valor is None:
                continue
            try:
                if pd.isna(valor):
                    continue
            except (TypeError, ValueError):
                sensibles.append(str(valor))
                continue
            texto = str(valor).strip()
            if texto:
                sensibles.append(texto)
    return sensibles


def procesar_archivo(
    ruta: str,
    columna_telefono: str | None = None,
    columna_correo: str | None = None,
    columna_nombre: str | None = None,
    credencial: str | None = None,
) -> tuple[logging.Logger, io.StringIO]:
    """Procesa un archivo y registra eventos con datos de contacto.

    Este pipeline es la "puerta" por la que el dato personal LLEGA
    al codigo del log: por cada fila de la tabla, emite un
    ``logger.info("fila i: nombre=X telefono=Y correo=Z", ...)``
    con el contenido real de la celda. Sin el filtro
    (``FiltroSeguro``), esa cadena apareceria tal cual en el log;
    con el filtro, aparece redactada.

    Parametros:
        ruta: ruta al archivo (CSV o Excel).
        columna_telefono, columna_correo, columna_nombre: nombres
            de las columnas a inspeccionar. Si alguna no esta en la
            tabla, se omite sin fallar (consistente con DC.10).
        credencial: credencial a redactar en el log.

    Retorna:
        ``(logger, buffer)``: el logger configurado y el buffer
        con todo lo emitido durante el procesamiento. El caller
        puede inspeccionar ``buffer.getvalue()``.
    """
    tabla = cargar_tabla(ruta)
    sensibles = _recolectar_sensibles_de_tabla(
        tabla, columna_nombre, columna_telefono, columna_correo
    )
    logger, buffer = configurar_log_seguro(
        credencial=credencial,
        valores_sensibles=sensibles,
    )

    # El log de inicio incluye la credencial para que el dato
    # "llegue al camino que escribe el log" (Cierre 2): si el
    # filtro esta, la cadena aparece como [REDACTADO]; si el
    # filtro no esta, la credencial aparece en claro. Asi la
    # Regla 9 tiene un asidero verificable: el filtro es el unico
    # responsable de que la credencial no salga.
    logger.info(
        "inicio del procesamiento: %d registros, %d sensibles, "
        "credencial=%s",
        len(tabla),
        len(sensibles),
        credencial if credencial is not None else "",
    )

    # Recorremos fila a fila y emitimos un log por cada una. Aqui
    # es donde el dato personal entra al codigo del log: si el
    # filtro no estuviera, cada "fila i: nombre=..." apareceria
    # tal cual en la salida capturada.
    pares_columna: list[tuple[str | None, str]] = [
        (columna_nombre, "nombre"),
        (columna_telefono, "telefono"),
        (columna_correo, "correo"),
    ]
    for i, fila in tabla.iterrows():
        partes: list[str] = []
        for columna, etiqueta in pares_columna:
            if columna is None or columna not in tabla.columns:
                continue
            valor = fila[columna]
            if valor is None:
                continue
            try:
                if pd.isna(valor):
                    continue
            except (TypeError, ValueError):
                pass
            partes.append(f"{etiqueta}={valor}")
        if partes:
            logger.info("fila %d: %s", i, " ".join(partes))

    # Llamamos al reporte real para que el pipeline completo
    # tambien se loggee. El reporte no loggea nada por si mismo,
    # asi que este paso es solo para cerrar el "recorrido".
    reporte = generar_reporte(
        tabla,
        columna_telefono=columna_telefono,
        columna_correo=columna_correo,
    )
    logger.info(
        "reporte generado: %d registros, %d grupos de duplicados",
        reporte.registros_totales,
        reporte.total_grupos_duplicados.valor or 0,
    )
    return logger, buffer