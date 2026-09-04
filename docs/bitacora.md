# Bitácora de DataClean AI

> Una fila por tanda, lo más reciente arriba. **Solo-añadir:** no se borra ni se
> reescribe nada. Lo único editable en una fila existente es su estado.
>
> La escribe Argos al cerrar cada tanda. Si un ítem no cerró, **también se
> anota** — un rojo explicado vale tanto como un verde.

| Fecha | Ítem | Qué se hizo | Iteraciones | Tests añadidos | Qué quedó pendiente |
|---|---|---|---|---|---|
| 2026-09-04 | DC.0 | Paquete `dataclean` levantando: `pyproject.toml` con `pandas`/`openpyxl`/`fastapi`/`uvicorn`/`pytest` fijadas, `src/dataclean/__init__.py` con `__version__`, `tests/test_dc0.py` con un test de import. Suite 1/1 verde. Regla 6 demostrada con `git stash` sobre `__init__.py` — el test cayó con `AttributeError: module 'dataclean' has no attribute '__version__'`. Decisión de diseño: editable install en `src/` (no paquete plano) para que `import dataclean` funcione sin tocar `PYTHONPATH` y los tests vivan en `tests/` como marca la regla 10. Añadí `.argos/`, `grafo.db*` y `pip.log` a `.gitignore` (basura que apareció al instalar y que no debe commitearse). | 1 | 1 | Nada para DC.0. |
