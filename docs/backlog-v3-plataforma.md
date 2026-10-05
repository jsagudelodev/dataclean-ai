# DataClean AI — Backlog V3: de limpiador a plataforma de Excel con IA

> **Qué es esto.** La visión y el backlog de la fase 3, redactado a petición
> del dueño del producto (2026-10-05). Mantiene el formato del ENCARGO: un
> ítem `DC.*` por tanda, y la línea `Cierre:` es lo único exigible. Respeta
> las reglas duras del proyecto: tests **sin red ni credenciales** (regla 7,
> todo proveedor externo tras interfaz sustituible con impl falsa), **cero
> falsos positivos** (criterio de vendible), **ni un dato de contacto en logs
> ni en la base** (regla 9), y **ante la duda, conservar** (regla 4).

## La tesis

El cliente no es "alguien con contactos": es **alguien que vive en Excel y
pierde horas con datos sucios.** Limpiar contactos es la primera plantilla de
una plataforma más grande: **"arregla y procesa tu Excel con IA — privado,
auditable y a escala."**

El moat **no es la IA** (ahí gana ChatGPT). Es: **determinismo + cero falsos
positivos + privacidad (los datos no salen) + escala + auditoría.** La IA solo
orquesta y ayuda donde una regla no alcanza; el motor ejecuta de forma exacta.

Mercado: **negocios con muchos contactos/datos** (inmobiliarias, call centers,
cobranzas, marketing, contabilidad) que **no pueden** pegar su base en ChatGPT
por privacidad ni por volumen.

---

## Fase A — Cimientos (sin esto, nada recurre)

- ⬜ **DC.19 — Persistencia tras interfaz (SQLite ahora, Supabase después).**
  Primer acceso a datos del proyecto. Un repositorio abstracto con impl SQLite
  y una impl en memoria para los tests.
  *Cierre:* (1) existe una interfaz `Repositorio*` con impl SQLite y una impl
  en memoria; (2) la suite usa la impl en memoria y corre **sin red ni
  archivos** (regla 7); (3) el motor de limpieza **no depende** de la impl
  concreta: se le inyecta.

- ⬜ **DC.20 — Monitoreo recurrente: salud de la base en el tiempo.**
  Cada proceso guarda un **snapshot de cifras agregadas** (fecha, total,
  % móviles/fijos/inválidos, duplicados, riesgo) por nombre de base. **Nunca
  PII** (refuerza el moat de privacidad y esquiva habeas data).
  *Cierre:* (1) procesar con un nombre de base guarda un snapshot y
  `GET /historial/{base}` devuelve la serie; (2) el snapshot **no contiene
  ningún dato de contacto**, solo cifras; (3) se calcula la variación vs. el
  snapshot anterior ("+12 inválidos este mes").

- ⬜ **DC.21 — Puntaje de riesgo oficial en el backend.**
  Promover el puntaje 0–100 que hoy calcula el frontend a una cifra del
  backend: determinista, rastreable y testeada como el resto del reporte.
  *Cierre:* (1) `generar_reporte` incluye un puntaje 0–100 y su nivel;
  (2) determinista y **rastreable** a las señales que lo componen; (3) **no
  inventa**: sin columna de teléfono evaluable, el puntaje es "no calculable",
  no 0.

## Fase B — Lo que generaliza el motor (de "contactos" a "Excel")

- ⬜ **DC.22 — Plantillas re-ejecutables (recetas de limpieza).**
  El usuario guarda *cómo* limpiar su export (columnas, reglas) y lo
  **re-ejecuta** sobre el archivo del mes siguiente con un clic. **Es el mayor
  generador de recurrencia.**
  *Cierre:* (1) una receta guardada se aplica a un archivo nuevo y produce el
  mismo tratamiento; (2) la receta se versiona/edita sin romper ejecuciones
  pasadas; (3) corre sin PII en la definición de la receta.

- ⬜ **DC.23 — Cruce / conciliación de dos archivos.**
  "Compara pagos vs. facturas y dime qué no cuadra." Lo que un contador hace
  cada cierre de mes, a mano. **La más vendible y 100% Excel.**
  *Cierre:* (1) dado dos archivos y una clave de cruce, devuelve coincidencias,
  faltantes en A y faltantes en B; (2) la clave de cruce tolera formatos
  distintos (reutiliza la normalización existente); (3) el resultado es
  **rastreable** fila a fila.

- ⬜ **DC.24 — Consolidar varios archivos con mapeo de columnas.**
  15 Excel de 15 sucursales con cabeceras distintas → una tabla unificada.
  *Cierre:* (1) une N archivos con cabeceras diferentes al mismo esquema;
  (2) una columna que no mapea se conserva y se marca, **no se descarta**;
  (3) el reporte dice cuántas filas aportó cada archivo.

- ⬜ **DC.25 — Texto libre → columnas estructuradas (LLM, sustituible).**
  Generaliza el separador de cargo: *"Juan Pérez, gerente, Bogotá"* → columnas.
  Donde la IA se gana la letra y ChatGPT no puede (privado, a escala).
  *Cierre:* (1) una columna de texto libre se parte en los campos pedidos;
  (2) el LLM es **sustituible** y la suite corre con una impl falsa, sin red;
  (3) sin LLM disponible, **conserva** el campo sin romper (como DC.7).

- ⬜ **DC.26 — Categorización automática (LLM, sustituible).**
  "Clasifícame estos 8.000 gastos / productos / leads en categorías."
  *Cierre:* (1) asigna cada fila a una categoría de un conjunto dado; (2) LLM
  sustituible, suite sin red; (3) ante baja confianza, marca "sin clasificar",
  **no inventa** una categoría (regla 4).

- ⬜ **DC.27 — Auditor de Excel contra reglas.**
  Semáforo de errores: NIT inválido, fecha imposible, monto negativo, correo
  roto. Marca filas problemáticas **antes** de que causen un daño.
  *Cierre:* (1) dado un conjunto de reglas, marca las filas que las violan con
  el motivo; (2) las reglas se configuran, no están escritas en el código;
  (3) no modifica datos: solo marca (regla 4).

## Fase C — Escala y plataforma B2B

- ⬜ **DC.28 — Archivos grandes sin caerse (volumen).**
  La promesa es "muchos contactos": el motor tiene que aguantarlos. Proceso
  asíncrono para archivos grandes, el request no se cuelga.
  *Cierre:* (1) un archivo de 100.000+ filas se procesa async y se consulta por
  id; (2) el request no bloquea mientras procesa; (3) hay una medición de
  tiempo/memoria documentada en la bitácora.

- ⬜ **DC.29 — Cuentas, API keys y uso (modelo lector-ia).**
  Multiusuario real siguiendo el molde de la plataforma de documentos: login,
  aislamiento de datos, API keys, panel de uso.
  *Cierre:* (1) un usuario no ve ni procesa los datos de otro; (2) la API se
  consume con una key por cuenta; (3) el uso (procesos, volumen) se mide por
  cuenta. Regla 9 intacta.

- ⬜ **DC.30 — Benchmarks agregados de industria.**
  Como solo se guardan cifras (DC.20), con el tiempo se acumulan comparativas:
  "la base promedio de tu sector tiene 18% de números muertos; la tuya 31%".
  Moat que crece con el uso, legal porque es agregado.
  *Cierre:* (1) un reporte compara las cifras de una base contra el agregado de
  su sector; (2) el agregado **no permite** reidentificar a ningún cliente
  (mínimo N por grupo); (3) se calcula solo con cifras, nunca con PII.

## Fase D — La visión (lo que emerge del núcleo)

- ⬜ **DC.31 — Agente de Excel (el LLM orquesta, el motor ejecuta).**
  "Cruza estos dos, quita duplicados, deja solo móviles válidos y expórtame el
  resultado." El LLM decide *qué* herramientas llamar; el motor las ejecuta de
  forma **exacta y auditable**. El diferenciador frente a ChatGPT.
  *Cierre:* (1) una instrucción en español se traduce a una secuencia de
  operaciones del motor y se ejecuta; (2) el LLM **solo orquesta**: toda
  transformación la hace el motor determinista, no el modelo; (3) LLM
  sustituible, con un plan de operaciones verificable antes de ejecutar.

- ⬜ **DC.32 — Tubería documento → datos limpios (familia lector-ia + dataclean).**
  PDF/documento desordenado → (lector-ia extrae) → tabla → (dataclean
  limpia/cruza) → datos listos. Un flujo de extremo a extremo que casi nadie
  puede copiar porque ya existen las dos piezas.
  *Cierre:* (1) una tabla extraída por lector-ia entra al pipeline de dataclean
  y sale limpia; (2) el contrato entre ambas plataformas está tipado; (3) cada
  paso conserva la trazabilidad (qué cambió y por qué).

---

## Prioridad recomendada (no construir todo; una cosa terminada a la vez)

1. **DC.19 → DC.20** — cimiento + monitoreo recurrente (la razón para pagar
   cada mes). *Elegido por el dueño.*
2. **DC.23** — cruce/conciliación (lo más vendible, puro Excel).
3. **DC.25** — texto → columnas con IA (donde el "AI" se gana la letra).

> **Aviso honesto (va en el backlog a propósito):** esto es visión, y la
> visión no paga la luz. El riesgo real del proyecto hoy no es técnico —el
> motor es sólido— es que **nadie ha pagado todavía.** Más features no
> responden "¿quién paga?"; un cliente real sí. Construir una pieza pequeña,
> terminada y puesta frente a un negocio concreto vale más que avanzar cinco
> ítems de este backlog en paralelo.
