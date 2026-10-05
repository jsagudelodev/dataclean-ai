"""Persistencia de snapshots de salud: el cimiento del monitoreo (DC.19).

Primer acceso a datos del proyecto. Guarda **solo cifras agregadas** de
cada proceso (nunca PII: ni un nombre, teléfono ni correo entra aquí),
para poder mostrar cómo evoluciona la salud de una base en el tiempo
(DC.20). Esto refuerza el moat de privacidad y esquiva el habeas data:
la base de datos no contiene datos personales.

Diseño (el plan SQLite -> Supabase):
    * ``RepositorioSnapshots`` es un ``Protocol``. El resto del código
      habla con la interfaz, nunca con SQLite directo.
    * ``SnapshotsEnMemoria`` -> para los tests (regla 7: la suite corre
      sin red ni archivos).
    * ``SnapshotsSQLite`` -> la implementación de la fase 1. Acepta
      ``":memory:"`` para poder probarla también sin tocar disco.
    * Una futura ``SnapshotsSupabase`` entra sin cambiar el resto del
      código (fase 2).

Regla 9: un ``Snapshot`` solo lleva **cuentas**, jamás un dato de
contacto. Si alguien intentara guardar PII aquí, el modelo no tiene
dónde ponerla.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Snapshot:
    """Una foto agregada de la salud de una base, sin PII.

    Atributos (todos son cuentas o fechas, ningún dato de contacto):
        base: nombre que el cliente le da a su base (ej. "Clientes2026").
            Es una etiqueta, no un dato personal.
        fecha: instante del proceso en ISO 8601 (``YYYY-MM-DDTHH:MM:SS``).
            Se ordena lexicográficamente igual que cronológicamente.
        total: registros procesados.
        moviles / fijos / invalidos: conteos de teléfonos por tipo.
        duplicados: filas repetidas (sobrantes de los grupos).
        riesgo: puntaje 0-100, o ``None`` si no se pudo calcular (no se
            inventa un 0; ver regla 4 y DC.21).
    """

    base: str
    fecha: str
    total: int
    moviles: int
    fijos: int
    invalidos: int
    duplicados: int
    riesgo: int | None


class RepositorioSnapshots(Protocol):
    """Contrato de almacenamiento de snapshots.

    Cualquier implementación -- en memoria, SQLite, Supabase -- lo
    cumple. El motor y el endpoint reciben una instancia de esta
    interfaz; no saben (ni les importa) cuál es la concreta.
    """

    def guardar(self, snapshot: Snapshot) -> None:
        """Persiste un snapshot."""
        ...

    def listar(self, base: str) -> list[Snapshot]:
        """Devuelve los snapshots de una base, del más viejo al más nuevo."""
        ...


class SnapshotsEnMemoria:
    """Implementación en memoria: para los tests y para un arranque sin DB.

    No toca red ni disco (regla 7). Útil también como caché o para
    entornos efímeros donde no se quiere persistencia real.
    """

    def __init__(self) -> None:
        self._datos: list[Snapshot] = []

    def guardar(self, snapshot: Snapshot) -> None:
        self._datos.append(snapshot)

    def listar(self, base: str) -> list[Snapshot]:
        propios = [s for s in self._datos if s.base == base]
        return sorted(propios, key=lambda s: s.fecha)


class SnapshotsSQLite:
    """Implementación SQLite (fase 1 del plan de persistencia).

    Acepta una ruta de archivo o ``":memory:"``. Con ``":memory:"`` la
    base vive en la conexión y desaparece al cerrarla: así los tests la
    ejercitan sin tocar disco (regla 7). Se mantiene **una** conexión
    para que la base en memoria persista entre llamadas.
    """

    def __init__(self, ruta: str = ":memory:") -> None:
        self._conexion = sqlite3.connect(ruta)
        self._conexion.row_factory = sqlite3.Row
        self._crear_tabla()

    def _crear_tabla(self) -> None:
        self._conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                base       TEXT    NOT NULL,
                fecha      TEXT    NOT NULL,
                total      INTEGER NOT NULL,
                moviles    INTEGER NOT NULL,
                fijos      INTEGER NOT NULL,
                invalidos  INTEGER NOT NULL,
                duplicados INTEGER NOT NULL,
                riesgo     INTEGER
            )
            """
        )
        self._conexion.commit()

    def guardar(self, snapshot: Snapshot) -> None:
        self._conexion.execute(
            """
            INSERT INTO snapshots
                (base, fecha, total, moviles, fijos, invalidos, duplicados, riesgo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.base,
                snapshot.fecha,
                snapshot.total,
                snapshot.moviles,
                snapshot.fijos,
                snapshot.invalidos,
                snapshot.duplicados,
                snapshot.riesgo,
            ),
        )
        self._conexion.commit()

    def listar(self, base: str) -> list[Snapshot]:
        filas = self._conexion.execute(
            """
            SELECT base, fecha, total, moviles, fijos, invalidos, duplicados, riesgo
            FROM snapshots
            WHERE base = ?
            ORDER BY fecha ASC
            """,
            (base,),
        ).fetchall()
        return [
            Snapshot(
                base=fila["base"],
                fecha=fila["fecha"],
                total=fila["total"],
                moviles=fila["moviles"],
                fijos=fila["fijos"],
                invalidos=fila["invalidos"],
                duplicados=fila["duplicados"],
                riesgo=fila["riesgo"],
            )
            for fila in filas
        ]

    def cerrar(self) -> None:
        self._conexion.close()
