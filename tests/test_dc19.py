"""Tests del item DC.19: persistencia de snapshots tras interfaz.

Primer acceso a datos del proyecto. Verifica que las dos implementaciones
del repositorio -- en memoria y SQLite -- cumplen **el mismo contrato**, y
que la suite corre sin red ni archivos (regla 7): SQLite se prueba con
``":memory:"``.

Cierres:
    1) existe una interfaz con impl SQLite y una impl en memoria;
    2) la suite usa impls que no tocan red ni disco;
    3) el contrato es idéntico en ambas (el caller no depende de la concreta).

Regla 6 (fuerte): los modulos se importan DENTRO de cada test.
Regla 10: archivo propio.
"""

from __future__ import annotations

import importlib

import pytest


def _persistencia():
    return importlib.import_module("dataclean.persistencia")


def _snapshot(base: str, fecha: str, **extra):
    p = _persistencia()
    datos = dict(
        total=100, moviles=70, fijos=12, invalidos=18, duplicados=4, riesgo=55
    )
    datos.update(extra)
    return p.Snapshot(base=base, fecha=fecha, **datos)


def _fabricas():
    """Una fábrica por implementación; ambas sin red ni disco."""
    p = _persistencia()
    return [
        ("en_memoria", p.SnapshotsEnMemoria),
        ("sqlite_memoria", lambda: p.SnapshotsSQLite(":memory:")),
    ]


# Parametrizamos cada test sobre las dos implementaciones: el mismo
# contrato tiene que pasar en las dos (Cierre 3).
IMPLEMENTACIONES = [(nombre, fab) for nombre, fab in _fabricas()]


@pytest.mark.parametrize("nombre,fabrica", IMPLEMENTACIONES)
def test_guardar_y_listar_devuelve_lo_guardado(nombre, fabrica) -> None:
    repo = fabrica()
    repo.guardar(_snapshot("Clientes2026", "2026-09-01T10:00:00"))

    resultado = repo.listar("Clientes2026")

    assert len(resultado) == 1
    assert resultado[0].total == 100
    assert resultado[0].riesgo == 55


@pytest.mark.parametrize("nombre,fabrica", IMPLEMENTACIONES)
def test_listar_ordena_del_mas_viejo_al_mas_nuevo(nombre, fabrica) -> None:
    repo = fabrica()
    # Se guardan desordenados; deben salir cronológicos.
    repo.guardar(_snapshot("Base", "2026-09-15T10:00:00", invalidos=30))
    repo.guardar(_snapshot("Base", "2026-07-01T10:00:00", invalidos=10))
    repo.guardar(_snapshot("Base", "2026-08-10T10:00:00", invalidos=20))

    fechas = [s.fecha for s in repo.listar("Base")]

    assert fechas == [
        "2026-07-01T10:00:00",
        "2026-08-10T10:00:00",
        "2026-09-15T10:00:00",
    ]


@pytest.mark.parametrize("nombre,fabrica", IMPLEMENTACIONES)
def test_listar_filtra_por_base(nombre, fabrica) -> None:
    repo = fabrica()
    repo.guardar(_snapshot("BaseA", "2026-09-01T10:00:00"))
    repo.guardar(_snapshot("BaseB", "2026-09-01T10:00:00"))

    assert len(repo.listar("BaseA")) == 1
    assert len(repo.listar("BaseB")) == 1
    assert repo.listar("Inexistente") == []


@pytest.mark.parametrize("nombre,fabrica", IMPLEMENTACIONES)
def test_riesgo_puede_ser_no_calculable(nombre, fabrica) -> None:
    # No se inventa un 0: el riesgo ausente se guarda como None (regla 4).
    repo = fabrica()
    repo.guardar(_snapshot("Base", "2026-09-01T10:00:00", riesgo=None))

    assert repo.listar("Base")[0].riesgo is None


def test_el_snapshot_no_tiene_campos_de_pii() -> None:
    # Regla 9: el modelo no tiene dónde poner un dato de contacto.
    p = _persistencia()
    campos = set(p.Snapshot.__dataclass_fields__.keys())
    prohibidos = {"nombre", "telefono", "correo", "contacto", "email", "celular"}

    assert campos.isdisjoint(prohibidos)
    assert campos == {
        "base", "fecha", "total", "moviles", "fijos",
        "invalidos", "duplicados", "riesgo",
    }
