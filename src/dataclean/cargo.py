"""Separacion del cargo pegado al nombre: con un LLM sustituible.

Caso real en hojas de contactos (DC.7): el cliente escribe en una
sola celda el nombre y el cargo, separados por muy distintos
formatos:

    ``MARIA GOMEZ GERENTE``
    ``Pedro Ruiz (Contador)``
    ``ANA LOPEZ - DIRECTORA COMERCIAL``
    ``Juan Perez / Ventas``
    ``CARLOS RUIZ|COORDINADOR``

Ninguna regla deterministica acierta con todos los formatos: por
eso el item dice "aqui es donde entra el LLM". Pero el item
tambien exige dos cosas mas que son el corazon de V1:

  * **Cierre 2** -- el LLM es sustituible: la suite corre con una
    implementacion falsa, sin red ni credenciales.
  * **Cierre 3** -- si el LLM no esta disponible, el sistema sigue
    funcionando y deja el campo sin separar en vez de fallar.

Diseno explicito:

  * La interfaz ``SeparadorNombreCargo`` es un ``Protocol`` con un
    solo metodo ``separar(texto) -> (nombre, cargo)``. Cualquier
    implementacion (LLM, regla, heuristica, mock de tests) la
    cumple. El modulo exporta ``SeparadorFalso`` y
    ``SeparadorPorPrefijo`` como implementaciones de referencia
    que viven en este archivo (sin red, sin credenciales).
  * ``separar_nombre_y_cargo(valor, separador=None)`` es la
    **funcion de cara al reporte**: si no se le pasa separador
    (o se le pasa ``None`` explicito), **conserva el campo sin
    separar** y devuelve ``(valor, None)``. Asi el reporte sigue
    funcionando aunque el LLM no este disponible (Cierre 3: el
    sistema no falla).
  * ``SeparadorFalso`` aplica una heuristica **conservadora**:
    solo corta cuando la **ultima palabra en MAYUSCULAS** o un
    token entre parentesis al final se parece a un cargo tipico.
    Si no se atreve, devuelve ``(texto, None)``. Esto cumple
    Cierre 2 (la suite corre sin LLM) **y** la regla 4 (ante la
    duda, conservar).
  * Regla 9 (datos personales en logs): los metodos que reciben
    el nombre+cargo jamas lo incluyen en un log; las excepciones
    o mensajes de error llevan solo la categoria del problema
    ("no se reconoce el formato", etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    import pandas as pd


# --- Interfaz: cualquier "LLM" que sepa separar nombre y cargo ----------


class SeparadorNombreCargo(Protocol):
    """Contrato de un separador de nombre y cargo.

    Cualquier implementacion -- un LLM real, una heuristica
    deterministica, un mock de tests -- cumple este contrato.
    El modulo exporta ``SeparadorFalso`` y ``SeparadorPorPrefijo``
    como implementaciones concretas **sin red ni credenciales**
    que sirven para que la suite corra y para que el reporte
    funcione si el LLM real no esta disponible (Cierre 2 y 3).
    """

    def separar(self, texto: str) -> tuple[str, str | None]:
        """Devuelve ``(nombre, cargo)``.

        Si la implementacion **no se atreve** a cortar (no esta
        segura del formato), devuelve ``(texto, None)``. Es la
        politica "ante la duda, conservar" (regla 4): mejor
        dejar el campo entero que cortar mal y meter un falso
        positivo en el reporte.
        """
        ...


# --- Implementacion falsa: conservadora, sin red ni credenciales ---------


# Palabras tipicas que indican que lo que viene es un cargo y no
# un nombre propio. La lista esta en MAYUSCULAS y la comparacion
# se hace en MAYUSCULAS. Es una lista **cerrada y pequena** por la
# misma razon que en DC.6: cualquier heuristica de patron
# (longitud, mayusculas, terminacion) falla en al menos uno de los
# dos extremos (falsos positivos en nombres como ``DIRECTORA`` que
# a la vez es nombre, o falsos negativos en cargos como ``CEO``).
_CARGOS_CONOCIDOS: Final[frozenset[str]] = frozenset({
    # Direccion.
    "GERENTE", "DIRECTOR", "DIRECTORA", "SUBDIRECTOR", "SUBDIRECTORA",
    "PRESIDENTE", "VICEPRESIDENTE", "CEO", "CFO", "CTO", "COO",
    "JEFE", "COORDINADOR", "COORDINADORA",
    # Administracion.
    "CONTADOR", "CONTADORA", "TESORERO", "TESORERA",
    "SECRETARIA", "SECRETARIO", "ASISTENTE", "AUXILIAR",
    "ADMINISTRADOR", "ADMINISTRADORA",
    # Comercial / ventas.
    "VENDEDOR", "VENDEDORA", "COMERCIAL", "EJECUTIVO", "EJECUTIVA",
    # Tecnico / operaciones.
    "INGENIERO", "INGENIERA", "TECNICO", "TECNICA", "ANALISTA",
    "PROGRAMADOR", "PROGRAMADORA", "DESARROLLADOR", "DESARROLLADORA",
    "OPERARIO", "OPERARIA",
    # RRHH / legal / consultoria.
    "RECLUTADOR", "RECLUTADORA", "ABOGADO", "ABOGADA",
    "CONSULTOR", "CONSULTORA", "ASESOR", "ASESORA",
})


def _es_cargo_conocido(token: str) -> bool:
    """True si ``token`` (ya en MAYUSCULAS) esta en la lista cerrada."""
    return token.upper() in _CARGOS_CONOCIDOS


class SeparadorFalso:
    """Implementacion falsa del separador: heuristica conservadora.

    Estrategia: solo corta cuando hay una senal **clara** de que
    el ultimo token (o el contenido entre parentesis al final) es
    un cargo conocido. En cualquier otro caso devuelve
    ``(texto, None)`` -- mejor dejar el campo entero que cortar
    mal (regla 4: cero falsos positivos).

    Senales que reconoce:

      * ``Pedro Ruiz (Contador)`` -- parentesis al final con un
        cargo conocido dentro.
      * ``ANA LOPEZ GERENTE`` -- ultimo token en MAYUSCULAS que
        esta en la lista de cargos conocidos.
      * ``MARIA GOMEZ - GERENTE`` -- guion, barra o pipe antes
        del cargo.

    Senales que **NO** reconoce (devuelve ``(texto, None)``):

      * Un cargo que no esta en la lista.
      * Un cargo en minusculas (``gerente``) -- podria ser parte
        del nombre; conservador = no cortar.
      * Dos cargos concatenados sin senal clara.
      * Un texto sin cargo al final (solo nombre).
    """

    def separar(self, texto: str) -> tuple[str, str | None]:
        """Aplica la heuristica conservadora al texto.

        Args:
            texto: nombre+cargo pegado en una sola cadena. Si ya
                es ``None`` o vacio, devuelve ``("", None)``.

        Returns:
            Tupla ``(nombre, cargo)``. ``cargo`` es ``None`` si
            la heuristica no se atreve a cortar. Cuando corta,
            el cargo se devuelve en **MAYUSCULAS** (para que el
            reporte pueda agrupar / contar facil).
        """
        if texto is None:
            return "", None
        limpio = " ".join(texto.split())
        if not limpio:
            return "", None

        # Caso 1: cargo entre parentesis al final.
        #   ``Pedro Ruiz (Contador)`` -> ``Pedro Ruiz``, ``CONTADOR``
        if limpio.endswith(")"):
            apertura = limpio.rfind("(")
            if apertura > 0:
                dentro = limpio[apertura + 1:-1].strip()
                if dentro and _es_cargo_conocido(dentro):
                    nombre = limpio[:apertura].strip()
                    return nombre, dentro.upper()

        # Caso 2: guion, barra o pipe antes del ultimo token.
        #   ``ANA LOPEZ - GERENTE`` -> ``ANA LOPEZ``, ``GERENTE``
        for sep in (" - ", " / ", " | "):
            if sep in limpio:
                cabeza, _, cola = limpio.rpartition(sep)
                cola = cola.strip()
                if cola and _es_cargo_conocido(cola):
                    return cabeza.strip(), cola.upper()

        # Caso 3: ultimo token en MAYUSCULAS conocido como cargo.
        #   ``MARIA GOMEZ GERENTE`` -> ``MARIA GOMEZ``, ``GERENTE``
        # Solo cortamos si la ultima palabra esta **en MAYUSCULAS**;
        # si esta en minusculas (``Maria Gomez gerente``) podria
        # ser parte del nombre -- conservamos el campo entero
        # (regla 4: cero falsos positivos).
        tokens = limpio.split(" ")
        if len(tokens) >= 2:
            ultimo = tokens[-1]
            if ultimo.isupper() and _es_cargo_conocido(ultimo):
                nombre = " ".join(tokens[:-1])
                return nombre, ultimo

        # Sin senal clara: conservar el campo entero (regla 4).
        return limpio, None


class SeparadorPorPrefijo:
    """Implementacion alternativa: parte por un prefijo literal.

    Util cuando el reporte sabe que el formato del archivo es
    estable (ej.: todos los nombres llegan como
    ``"APELLIDO NOMBRE - CARGO"``) y no hace falta un LLM.

    Args:
        prefijo: cadena literal que separa nombre y cargo
            (ej.: ``" - "``, ``" / "``). Si el prefijo no esta
            en el texto, devuelve ``(texto, None)`` -- igual
            que el resto, sin fallar.
    """

    def __init__(self, prefijo: str) -> None:
        self._prefijo = prefijo

    def separar(self, texto: str) -> tuple[str, str | None]:
        if texto is None:
            return "", None
        limpio = " ".join(texto.split())
        if not limpio:
            return "", None
        if self._prefijo not in limpio:
            return limpio, None
        cabeza, _, cola = limpio.rpartition(self._prefijo)
        return cabeza.strip(), cola.strip() or None


# --- Funcion de cara al reporte: tolerante a "sin LLM" -------------------


def separar_nombre_y_cargo(
    valor: object,
    separador: SeparadorNombreCargo | None = None,
) -> tuple[object, str | None]:
    """Separa ``valor`` en ``(nombre, cargo)``.

    DC.7 Cierres 1, 2 y 3:

      * **Cierre 1** -- sobre los formatos del item
        (``MARIA GOMEZ GERENTE``, ``Pedro Ruiz (Contador)``) el
        separador devuelve nombre y cargo separados.
      * **Cierre 2** -- si el caller pasa un ``SeparadorFalso``
        (o cualquier implementacion local), la suite corre sin
        red ni credenciales. La firma del modulo **no** depende
        de un proveedor externo.
      * **Cierre 3** -- si el caller pasa ``separador=None``
        (porque el LLM real no esta disponible), el sistema sigue
        funcionando y devuelve ``(valor, None)``: el campo
        original queda **conservado** sin separar, en vez de
        fallar.

    Args:
        valor: cualquier valor. ``None`` y vacios se devuelven
            como ``(None, None)`` -- "ausente" no se confunde
            con "separable". Si el valor no es ``str`` se intenta
            convertir; si falla, ``(valor, None)``.
        separador: implementacion de ``SeparadorNombreCargo``.
            Si es ``None``, el sistema **no falla**: conserva
            el campo entero. Esto es el Cierre 3.

    Returns:
        Tupla ``(nombre, cargo)``. ``nombre`` es ``str`` (o el
        valor original si no se pudo separar); ``cargo`` es
        ``str | None``.
    """
    # Ausentes: ``None``, ``NaN`` y vacios se devuelven como
    # ``(None, None)`` consistente. Se chequea **antes** del
    # "sin separador" para que ``""`` no se confunda con un
    # valor separable (regla 4: ausente no es "separable").
    if valor is None:
        return None, None
    try:
        import pandas as pd  # noqa: PLC0415
        if bool(pd.isna(valor)):
            return None, None
    except Exception:
        # Pandas no instalado: los ausentes ya estan filtrados
        # por el ``None`` de arriba. Esto es defensa en profundidad
        # (pandas SI esta declarado en pyproject.toml).
        pass
    if isinstance(valor, str) and not valor.strip():
        return None, None

    # Sin separador -> conservar el campo entero (Cierre 3).
    if separador is None:
        return valor, None

    if isinstance(valor, str):
        limpio = valor.strip()
    else:
        # No-string: intentamos convertir. Si falla, conservamos.
        try:
            limpio = str(valor).strip()
        except Exception:
            return valor, None

    nombre, cargo = separador.separar(limpio)
    if cargo is None or cargo == "":
        return nombre, None
    return nombre, cargo


# --- Wrapper de columna: lo que el endpoint conecta (DC.18) ---------------


def separar_columna_nombre_cargo(
    tabla: "pd.DataFrame",
    columna: str,
    separador: SeparadorNombreCargo | None = None,
) -> "pd.DataFrame":
    """Anade a ``tabla`` el nombre sin cargo y el cargo, en campos separados.

    DC.18 (Cierre 1): el pipeline ya tenia DC.7 construida y probada,
    pero el endpoint nunca la llamaba, asi que el cliente recibia
    ``MARIA GOMEZ - GERENTE`` pegado. Esta funcion conecta lo que ya
    existe (:func:`separar_nombre_y_cargo`) a nivel de columna,
    siguiendo el patron de ``normalizar_columna_telefono`` /
    ``normalizar_columna_nombre``.

    Crea (sin mutar ``tabla``):
      * ``f"{columna}_sin_cargo"``: el nombre sin el cargo pegado, o el
        valor original cuando el separador no se atreve a cortar.
      * ``f"{columna}_cargo"``: el cargo detectado (``str``), o ``None``
        cuando no hay cargo o no se pudo separar.

    Args:
        tabla: ``DataFrame`` con la columna de nombres.
        columna: nombre de la columna a separar.
        separador: implementacion de :class:`SeparadorNombreCargo`. Si
            es ``None``, cada fila conserva el campo entero
            (``sin_cargo=valor``, ``cargo=None``): el sistema sigue
            funcionando sin un LLM disponible (DC.7 Cierre 3).

    Returns:
        Un ``DataFrame`` nuevo con las dos columnas auxiliares anadidas.
    """
    sin_cargo: list[object] = []
    cargos: list[str | None] = []
    for valor in tabla[columna]:
        nombre, cargo = separar_nombre_y_cargo(valor, separador)
        sin_cargo.append(nombre)
        cargos.append(cargo)
    resultado = tabla.copy()
    resultado[f"{columna}_sin_cargo"] = sin_cargo
    resultado[f"{columna}_cargo"] = cargos
    return resultado