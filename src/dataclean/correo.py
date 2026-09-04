"""Revision de correos electronicos: marcar lo dudoso, no inventar.

Un correo puede llegar escrito de muchas formas y, a diferencia del
telefono, no hay un "canonico" al que reducirlo (la parte local es
case-sensitive en el RFC, asi que ``juan@x.com`` y ``Juan@x.com`` pueden
ser cuentas distintas en teoria). Lo que DC.5 pide es mas modesto y
mas util: **revisar** si la cadena tiene la forma minima de un correo
valido, y **marcar con motivo** lo que no la tiene, conservando el valor
original. El caller decide que hacer con la marca.

Por que existe este modulo (regla 4 del encargo):
    Ante la duda, **conservar**. Un correo que el revisor no sabe si es
    valido se queda como esta y se devuelve ``(None, False, motivo)``;
    no se sustituye por ``None``, no se borra. Asi, si un humano tiene
    que revisar lo dudoso, puede (regla 4); y un correo bueno nunca
    queda marcado como invalido (cero falsos positivos, regla 4).

Diseno (regla 9: nada de contactos en logs):
    El motivo **nunca** contiene el correo que estamos revisando: solo
    la categoria del problema ("falta arroba", "hay espacios", ...).
    Asi, si el reporte cae en un log, no se filtra un dato personal.

Decisiones de diseno explicitas:
    * **No** usamos una regex completa de RFC 5321/5322. Es
      sobre-ingenieria: cubre casos que nadie va a tener en una hoja
      de contactos, y mete falsos positivos (el RFC permite
      comentarios anidados, comillas escapadas, etc.). El item
      enumera los tres fallos tipicos (sin ``@``, con espacios,
      dominio incompleto) y un caso valido raro
      (``nombre+etiqueta@dominio.com.co``). Con eso basta.
    * La validacion es **conservadora**: si una regla no la podemos
      asegurar, marcamos. Un correo "raro pero valido" como
      ``nombre+etiqueta@dominio.com.co`` pasa porque solo pedimos
      las reglas minimas; un correo con caracteres Unicode
      acentuados en el local-part se marca (es conservador y
      consistente con DC.2 que ya normalizo cabeceras a ASCII).
    * ``None`` y vacios se tratan como ausentes (no como invalidos
      con motivo): la columna suele tenerlos y es ruido marcarlos
      con un motivo tecnico que el cliente no va a entender.
"""

from __future__ import annotations

import re
from typing import Final

import pandas as pd


# Caracteres validos en la **parte local** de un correo. Segun el RFC
# 5321 el conjunto es ASCII alfanumerico + ``!#$%&'*+-/=?^_`{|}~`` + ``.``;
# aqui lo dejamos en el subconjunto "razonable" que aparece en hojas
# de contactos reales y excluimos los raros que solo veria un parser
# estricto (comillas, corchetes, escapes). La idea es **no aceptar
# cualquier cosa** pero tampoco caer en sobre-validacion.
_LOCAL_PERMITIDOS: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9!#$%&'*+\-\=?^_`{|}~.]+$"
)

# Caracteres validos en el **dominio** (entre puntos): ASCII
# alfanumerico + guion. Sin puntos (los puntos se manejan al
# separar dominio en etiquetas).
_ETIQUETA_DOMINIO: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9\-]+$")


def _motivo_para(correo: str) -> str:
    """Devuelve el motivo legible por el que ``correo`` no es valido.

    El motivo NO contiene el correo (regla 9). Solo la categoria del
    problema, para que el reporte explique POR QUE se marco, no solo
    QUE se marco (Cierre 3).
    """
    if "@" not in correo:
        return "falta el arroba"
    if correo.count("@") > 1:
        return "hay mas de un arroba"
    # A partir de aqui hay exactamente un ``@``.
    local, _, dominio = correo.partition("@")
    if not local:
        return "la parte antes del arroba esta vacia"
    if not dominio:
        return "la parte despues del arroba esta vacia"
    if local != local.strip():
        return "hay espacios alrededor de la parte local"
    if dominio != dominio.strip():
        return "hay espacios alrededor del dominio"
    if " " in local or " " in dominio:
        return "hay espacios dentro del correo"
    if local.startswith(".") or local.endswith("."):
        return "la parte local empieza o termina en punto"
    if ".." in local:
        return "la parte local tiene dos puntos seguidos"
    if not _LOCAL_PERMITIDOS.match(local):
        return "la parte local tiene caracteres no permitidos"
    # Dominio: al menos un punto, y la ultima etiqueta (TLD) tiene
    # >= 2 letras. Esto cubre "dominio incompleto" (``@x.y`` no
    # aparece tipicamente, pero ``@x`` si: una sola etiqueta).
    if "." not in dominio:
        return "el dominio no tiene punto"
    etiquetas = dominio.split(".")
    if any(not etiq for etiq in etiquetas):
        return "el dominio tiene una etiqueta vacia"
    tld = etiquetas[-1]
    if len(tld) < 2:
        return "la terminacion del dominio es demasiado corta"
    if not tld.isalpha():
        return "la terminacion del dominio no es solo letras"
    for etiq in etiquetas:
        if not _ETIQUETA_DOMINIO.match(etiq):
            return "el dominio tiene caracteres no permitidos"
        if etiq.startswith("-") or etiq.endswith("-"):
            return "una etiqueta del dominio empieza o termina en guion"
    # Si llegamos aqui, no encontramos motivo: el caller decidira
    # que no hay motivo. Esto no deberia ocurrir si las reglas
    # estan alineadas con ``es_valido``, pero lo dejamos para
    # evitar devolver un motivo generico que pueda filtrar datos.
    return "no cumple el formato esperado"


def es_valido(correo: str) -> bool:
    """Devuelve ``True`` si ``correo`` pasa las reglas minimas de DC.5.

    Reglas (alineadas con el item):
      * exactamente un ``@``;
      * sin espacios en ninguna parte;
      * parte local no vacia, sin punto al principio ni al final,
        sin dos puntos seguidos, solo caracteres permitidos;
      * dominio no vacio, con al menos un punto, TLD de >= 2 letras
        ASCII, y cada etiqueta solo con caracteres permitidos
        (alfanumerico + guion, sin guion al borde).

    Esta funcion es auxiliar: la API publica es :func:`validar_correo`,
    que devuelve motivo. Esta existe para reutilizarla desde ahi sin
    reescribir las reglas.
    """
    if not isinstance(correo, str) or not correo:
        return False
    if correo != correo.strip():
        return False
    if correo.count("@") != 1:
        return False
    local, _, dominio = correo.partition("@")
    if not local or not dominio:
        return False
    if " " in local or " " in dominio:
        return False
    if local.startswith(".") or local.endswith("."):
        return False
    if ".." in local:
        return False
    if not _LOCAL_PERMITIDOS.match(local):
        return False
    if "." not in dominio:
        return False
    etiquetas = dominio.split(".")
    if any(not etiq for etiq in etiquetas):
        return False
    tld = etiquetas[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False
    for etiq in etiquetas:
        if not _ETIQUETA_DOMINIO.match(etiq):
            return False
        if etiq.startswith("-") or etiq.endswith("-"):
            return False
    return True


def validar_correo(valor: object) -> tuple[str | None, bool, str]:
    """Revisa un correo y devuelve ``(original, valido, motivo)``.

    DC.5 Cierre 1, 2 y 3. La funcion **conserva**: nunca destruye
    el valor de entrada. La tripleta tiene este contrato:

      * ``original``: el valor tal cual llego, o ``None`` si era
        ausente. Asi el reporte puede mostrar el correo real al
        cliente.
      * ``valido``: ``True`` si pasa las reglas, ``False`` si no.
      * ``motivo``: texto legible cuando ``valido`` es ``False``
        explicando la categoria del problema; ``""`` cuando
        ``valido`` es ``True``. **No** contiene el correo
        (regla 9).

    Args:
        valor: cualquier valor. ``None`` y vacios se tratan como
            ausentes (``(None, False, "")``): la columna suele
            tenerlos y marcarlos con un motivo tecnico mete ruido
            en el reporte. No-string se convierte a ``str``;
            si la conversion falla (p.ej. un objeto raro), se
            devuelve ``(None, False, "")``.

    Returns:
        Tupla ``(original, valido, motivo)``.
    """
    # 1) Ausentes: ``None``, ``NaN`` de pandas, vacios.
    if valor is None:
        return None, False, ""
    try:
        if pd.isna(valor):  # type: ignore[arg-type]
            return None, False, ""
    except (TypeError, ValueError):
        pass
    # No-string: intentamos convertir; si no, ausente.
    if not isinstance(valor, str):
        try:
            valor = str(valor)
        except Exception:
            return None, False, ""
    texto = valor.strip()
    if not texto:
        return None, False, ""
    # 2) Validacion.
    if es_valido(texto):
        return texto, True, ""
    return texto, False, _motivo_para(texto)


def validar_columna_correo(
    tabla: pd.DataFrame, columna: str
) -> pd.DataFrame:
    """Revisa una columna completa de correos y devuelve un ``DataFrame``
    con tres columnas auxiliares (``_canonico``, ``_valido``, ``_motivo``).

    DC.5 aplicado a una tabla. La columna original **no se muta**: el
    ``DataFrame`` de salida es una copia. Esto es la misma politica que
    :func:`dataclean.telefono.normalizar_columna_telefono`: el cliente
    tiene que poder comparar lo que escribio con lo que el sistema
    decidio.

    Args:
        tabla: ``DataFrame`` con una columna de correos.
        columna: nombre de la columna a revisar.

    Returns:
        Copia de ``tabla`` con las tres columnas auxiliares anadidas:
          * ``{columna}_canonico``: el correo tal cual (o ``""`` si
            ausente).
          * ``{columna}_valido``: ``True`` / ``False``.
          * ``{columna}_motivo``: motivo legible cuando no es valido;
            ``""`` cuando lo es.
    """
    if columna not in tabla.columns:
        raise ValueError(
            f"La columna {columna!r} no existe en la tabla "
            f"(hay: {list(tabla.columns)})."
        )
    resultados = tabla[columna].map(validar_correo)
    canonicos = [r[0] if r[0] is not None else "" for r in resultados]
    validos = [bool(r[1]) for r in resultados]
    motivos = [r[2] for r in resultados]
    copia = tabla.copy()
    copia[f"{columna}_canonico"] = canonicos
    copia[f"{columna}_valido"] = validos
    copia[f"{columna}_motivo"] = motivos
    return copia


# --- Alias de un solo token, utiles para reportes ------------------------
# El reporte suele consumir ``es_valido`` como bandera; exportamos
# tambien el nombre ``CORREO_VALIDO`` para que el caller no tenga
# que recordar el nombre del boolean.
CORREO_VALIDO: Final[bool] = True
CORREO_INVALIDO: Final[bool] = False