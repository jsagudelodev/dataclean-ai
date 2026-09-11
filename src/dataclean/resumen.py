"""El reporte en una frase: lo que el cliente lee en cinco segundos (DC.16).

Por que existe este modulo:
    ENCARGO §1: «De tus 50 contactos, 12 son fijos, 4 están duplicados y
    3 no existen.» Ver el propio desorden cuantificado es el argumento de
    venta. El reporte de DC.10 tiene las cifras; este modulo las convierte
    en la frase que abre la pagina de resultados.

Diseno:
    * Recibe el reporte **ya serializado** por el endpoint (un dict), no el
      ``Reporte`` de DC.10: la frase tambien cuenta los duplicados por
      nombre, que viven solo en el dict.
    * **No inventa** (DC.10 Cierre 3): si una cifra no esta disponible, la
      frase dice que no se pudo revisar, no la omite como si fuera cero.
    * **Regla 9**: la frase solo lleva conteos, nunca un dato de contacto.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _cuantos(n: int, singular: str, plural: str) -> str:
    """``_cuantos(1, "es fijo", "son fijos")`` -> ``"1 es fijo"``."""
    return f"{n} {singular if n == 1 else plural}"


def _enumerar(partes: list[str]) -> str:
    """``["a", "b", "c"]`` -> ``"a, b y c"``."""
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _valor(reporte: Mapping[str, Any], clave: str) -> int | None:
    cifra = reporte.get(clave) or {}
    if not cifra.get("disponible"):
        return None
    return cifra.get("valor")


def filas_repetidas_por_telefono(reporte: Mapping[str, Any]) -> int:
    """Filas sobrantes de los grupos de duplicados por telefono.

    Un grupo de 3 filas con el mismo numero son 2 contactos repetidos: se
    conserva uno.
    """
    grupos = (reporte.get("grupos_duplicados") or {}).get("grupos") or []
    return sum(len(grupo["filas"]) - 1 for grupo in grupos)


def redactar_resumen(reporte: Mapping[str, Any]) -> str:
    """Devuelve el resumen legible del reporte serializado."""
    total = reporte["total_registros"]
    if total == 0:
        return "Tu archivo no tiene contactos."
    inicio = "De tu único contacto" if total == 1 else f"De tus {total} contactos"

    frases: list[str] = []
    moviles = _valor(reporte, "telefonos_moviles")
    if moviles is None:
        frases.append(
            f"{inicio} no pudimos revisar los teléfonos: no encontramos "
            "una columna de teléfono."
        )
    else:
        problemas: list[str] = []
        fijos = _valor(reporte, "telefonos_fijos") or 0
        invalidos = _valor(reporte, "telefonos_invalidos") or 0
        repetidos = filas_repetidas_por_telefono(reporte)
        if fijos:
            problemas.append(
                _cuantos(
                    fijos,
                    "es fijo (no recibe WhatsApp ni SMS)",
                    "son fijos (no reciben WhatsApp ni SMS)",
                )
            )
        if repetidos:
            problemas.append(_cuantos(repetidos, "está repetido", "están repetidos"))
        if invalidos:
            problemas.append(
                _cuantos(invalidos, "no tiene un número válido", "no tienen un número válido")
            )
        base = f"{inicio}, " + _cuantos(
            moviles, "tiene un móvil válido", "tienen un móvil válido"
        )
        if problemas:
            frases.append(f"{base}; {_enumerar(problemas)}.")
        else:
            frases.append(f"{base} y no encontramos problemas en los teléfonos.")

    correos = _valor(reporte, "correos_marcados")
    if correos:
        frases.append(
            _cuantos(correos, "correo tiene problemas", "correos tienen problemas") + "."
        )

    por_nombre = _valor(reporte, "duplicados_por_nombre")
    if por_nombre:
        frases.append(
            _cuantos(
                por_nombre,
                "nombre aparece más de una vez",
                "nombres aparecen más de una vez",
            )
            + ": revísalos antes de borrar nada."
        )
    return " ".join(frases)
