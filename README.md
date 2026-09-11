# DataClean AI

Sube el Excel o CSV de contactos de tu empresa y descubre en segundos por qué te
bloquean por SPAM: cuántos números son fijos, cuántos están repetidos, cuántos no
sirven y qué correos están mal. Te devuelve el archivo ordenado, **sin borrar
ningún contacto**: lo dudoso queda marcado para que tú decidas.

> «De tus 50 contactos, 31 tienen un móvil válido; 12 son fijos (no reciben
> WhatsApp ni SMS), 4 están repetidos y 3 no tienen un número válido.»

El documento que gobierna el proyecto es [ENCARGO.md](ENCARGO.md); el historial
de cada tanda, [docs/bitacora.md](docs/bitacora.md).

## Arrancar

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
python -m dataclean             # o simplemente: dataclean
```

Abre <http://127.0.0.1:8000>, arrastra tu archivo y descarga el resultado en
Excel o CSV.

## API

La página web solo consume esta API; cualquier otra integración puede usarla
igual. Documentación interactiva en `/api/docs`.

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/` | Página de subida |
| `GET` | `/configuracion` | Tamaño máximo, horas de retención y formatos de descarga |
| `POST` | `/procesar` | Campo `archivo` (multipart). Devuelve `id`, `reporte` (con `resumen` y las filas de cada cifra) y `formatos` |
| `GET` | `/descargar/{id}?formato=xlsx` | Archivo limpio (`csv` por defecto, o `xlsx`) |

Los errores llegan como `{"detail": {"motivo": "..."}}` con un texto pensado para
el usuario final: 400 archivo ilegible o vacío, 404 id caducado, 413 archivo
demasiado grande, 500 error interno.

```bash
curl -F "archivo=@contactos.xlsx" http://127.0.0.1:8000/procesar
```

## Configuración

| Variable | Por defecto | Qué controla |
|---|---|---|
| `DATACLEAN_HOST` | `127.0.0.1` | Interfaz donde escucha (`0.0.0.0` para exponerlo) |
| `DATACLEAN_PUERTO` | `8000` | Puerto |
| `DATACLEAN_MAX_BYTES` | `10485760` (10 MB) | Tamaño máximo de subida |
| `DATACLEAN_HORAS_RETENCION` | `24` | Horas antes de borrar los archivos limpios del servidor |

## Qué revisa

- **Teléfonos** (Colombia por defecto): normaliza `300 123 4567`, `+57 300 1234567`,
  `(300)123-4567` y números guardados como número en Excel; los clasifica en móvil,
  fijo o inválido.
- **Correos**: sin `@`, con espacios o con dominio incompleto, con el motivo.
- **Nombres**: `JUAN PEREZ` → `Juan Perez`, respetando partículas y siglas (`SAS`).
- **Duplicados**: por teléfono (propone cuál conservar) y por nombre (como posibles).

Las columnas se reconocen solas (`Cel`, `móvil 2`, `Correo electrónico`,
`NOMBRE COMPLETO`…). El archivo limpio conserva las originales y añade al lado
las revisadas.

## Tests

```bash
python -m pytest -q
```

La suite corre sin red y sin credenciales.
