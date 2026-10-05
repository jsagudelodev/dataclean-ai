"""Tests del separador de cargo con LLM real (DC.7 via interfaz sustituible).

Conectar un LLM real al separador de cargo es el punto donde el "AI" del
producto se vuelve literal. Estos tests verifican el contrato SIN red ni
credenciales (regla 7): el cliente de Anthropic se **inyecta** falso.

Cierres que cubren:
    * DC.7 Cierre 2 (sustituible): la clase recibe el cliente por
      parametro; la suite corre sin red ni credenciales.
    * DC.7 Cierre 3 (tolerante): ante cualquier error, conserva el campo.
    * Regla 4 (conservar): no inventa un cargo; null se respeta.
    * El factory del endpoint elige LLM solo si hay credencial.

Regla 6 (fuerte): los modulos se importan DENTRO de cada test.
Regla 10: archivo propio.
"""

from __future__ import annotations

import importlib


def _modulo(nombre: str):
    return importlib.import_module(f"dataclean.{nombre}")


class _BloqueFalso:
    """Imita un bloque de contenido de la respuesta del SDK."""

    def __init__(self, texto: str) -> None:
        self.type = "text"
        self.text = texto


class _RespuestaFalsa:
    def __init__(self, texto: str) -> None:
        self.content = [_BloqueFalso(texto)]


class _ClienteFalso:
    """Imita ``anthropic.Anthropic``: expone ``.messages.create``."""

    def __init__(self, texto: str | None = None, excepcion: Exception | None = None) -> None:
        self._texto = texto
        self._excepcion = excepcion
        self.messages = self  # asi ``.messages.create`` cae en ``create``

    def create(self, **_kwargs):
        if self._excepcion is not None:
            raise self._excepcion
        return _RespuestaFalsa(self._texto or "")


# ---------------------------------------------------------------------------
# DC.7 Cierre 2 + Cierre 1: separa con el LLM (cliente inyectado)
# ---------------------------------------------------------------------------


def test_separador_llm_parsea_nombre_y_cargo() -> None:
    cargo = _modulo("cargo")
    cliente = _ClienteFalso('{"nombre": "MARIA GOMEZ", "cargo": "GERENTE"}')
    separador = cargo.SeparadorLLM(cliente=cliente)

    nombre, puesto = separador.separar("MARIA GOMEZ - GERENTE")

    assert nombre == "MARIA GOMEZ"
    assert puesto == "GERENTE"


def test_separador_llm_tolera_json_entre_texto() -> None:
    cargo = _modulo("cargo")
    # El modelo a veces envuelve el JSON; el parseo debe aguantarlo.
    cliente = _ClienteFalso('Claro:\n{"nombre": "Ana Lopez", "cargo": "contadora"}\n')
    separador = cargo.SeparadorLLM(cliente=cliente)

    nombre, puesto = separador.separar("Ana Lopez Contadora")

    assert nombre == "Ana Lopez"
    assert puesto == "CONTADORA"  # se normaliza a mayusculas


# ---------------------------------------------------------------------------
# Regla 4: no inventa un cargo
# ---------------------------------------------------------------------------


def test_separador_llm_respeta_cargo_null() -> None:
    cargo = _modulo("cargo")
    cliente = _ClienteFalso('{"nombre": "Juan Perez", "cargo": null}')
    separador = cargo.SeparadorLLM(cliente=cliente)

    nombre, puesto = separador.separar("Juan Perez")

    assert nombre == "Juan Perez"
    assert puesto is None


# ---------------------------------------------------------------------------
# DC.7 Cierre 3: ante cualquier error, conserva el campo (no se cae)
# ---------------------------------------------------------------------------


def test_separador_llm_conserva_ante_error() -> None:
    cargo = _modulo("cargo")
    cliente = _ClienteFalso(excepcion=RuntimeError("sin red"))
    separador = cargo.SeparadorLLM(cliente=cliente)

    nombre, puesto = separador.separar("MARIA GOMEZ - GERENTE")

    assert nombre == "MARIA GOMEZ - GERENTE"
    assert puesto is None


def test_separador_llm_conserva_ante_json_invalido() -> None:
    cargo = _modulo("cargo")
    cliente = _ClienteFalso("no es json")
    separador = cargo.SeparadorLLM(cliente=cliente)

    nombre, puesto = separador.separar("Pedro Ruiz")

    assert nombre == "Pedro Ruiz"
    assert puesto is None


# ---------------------------------------------------------------------------
# El factory del endpoint: LLM solo si hay credencial
# ---------------------------------------------------------------------------


def test_factory_sin_credencial_usa_separador_falso(monkeypatch) -> None:
    endpoint = _modulo("endpoint")
    cargo = _modulo("cargo")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert isinstance(endpoint._crear_separador(), cargo.SeparadorFalso)


def test_factory_con_credencial_usa_llm(monkeypatch) -> None:
    endpoint = _modulo("endpoint")
    cargo = _modulo("cargo")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-de-prueba")

    # SeparadorLLM no crea cliente en el constructor (es perezoso), asi que
    # esto no toca la red ni exige la libreria anthropic.
    assert isinstance(endpoint._crear_separador(), cargo.SeparadorLLM)
