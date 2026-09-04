"""Cierre de DC.0: el paquete ``dataclean`` debe poder importarse."""

from __future__ import annotations


def test_paquete_importable() -> None:
    """El paquete ``dataclean`` se importa sin error.

    Es el contrato mínimo de DC.0: si no se puede importar, el proyecto no
    está levantado. Cualquier intento de usar el código (``from dataclean
    import ...``) depende de que este import funcione.
    """
    import dataclean  # noqa: F401

    assert dataclean.__version__ == "0.1.0"