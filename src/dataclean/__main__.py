"""Arranca DataClean AI: ``python -m dataclean`` (o el comando ``dataclean``).

La pagina queda en ``http://127.0.0.1:8000``. ``DATACLEAN_HOST`` y
``DATACLEAN_PUERTO`` cambian donde escucha; para exponerlo a otros equipos,
``DATACLEAN_HOST=0.0.0.0``.
"""

from __future__ import annotations

import os

from dataclean.endpoint import crear_app


def main() -> None:
    import uvicorn

    host = os.environ.get("DATACLEAN_HOST", "127.0.0.1")
    puerto = int(os.environ.get("DATACLEAN_PUERTO", "8000"))
    uvicorn.run(crear_app(), host=host, port=puerto)


if __name__ == "__main__":
    main()
