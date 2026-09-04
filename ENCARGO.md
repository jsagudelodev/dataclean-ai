# DataClean AI — encargo

> **Qué es esto.** El documento que gobierna el proyecto: qué se construye, con
> qué reglas y en qué orden. Lo escribe el evaluador humano; **Argos construye**.
> El backlog vivo es la sección final: un ítem `DC.*` por tanda, y su línea
> `Cierre:` es lo único exigible.

---

## 1. El problema, en una frase

Toda pyme tiene **un Excel de contactos heredado de años** —teléfonos con cinco
formatos distintos, fijos mezclados con móviles, nombres en MAYÚSCULAS,
duplicados y números que ya no existen—, y cuando lo carga en una herramienta de
difusión **le bloquean la cuenta por SPAM**. No sabe por qué: cree que el
problema es el mensaje, y es la lista.

**Lo que se vende no es el archivo limpio: es el reporte.** «De tus 50 contactos,
12 son fijos, 4 están duplicados y 3 no existen.» Ver el propio desorden
cuantificado en cinco segundos es el argumento de venta.

## 2. Qué se construye en V1

Un servicio que recibe un CSV o un Excel de contactos sucio y devuelve **dos
cosas**: el archivo normalizado y un **reporte de qué se cambió y por qué**.

**Fuera de V1, y no se hace aunque quede tiempo:** validación por envío real,
direcciones postales, API de terceros, interfaz web, multiusuario, cobro.

## 3. Stack

| Pieza | Elección | Por qué |
|---|---|---|
| Lenguaje | **Python 3.11** | El que hay en la máquina. No se exige otro |
| Datos | **pandas** + **openpyxl** | Excel y CSV sin escribir un parser |
| API | **FastAPI** + **uvicorn** | Igual que Invoxa: el motor ya conocido |
| Tests | **pytest** | Sin red y sin credenciales (regla 7) |
| LLM | **sustituible por interfaz** | Igual que Invoxa: la suite corre con una implementación falsa |

**Comando de validación del proyecto:** `python -m pytest -q`

## 4. El criterio de vendible (esto manda sobre todo lo demás)

Sobre un Excel real y sucio de 1.000 filas:

1. **Cero falsos positivos.** Ningún móvil bueno marcado como inválido. Un
   servicio que descarta contactos buenos no se puede vender, aunque acierte en
   todo lo demás.
2. **El reporte cuadra** con lo que un humano encuentra revisando 50 filas a
   mano.

**Ante la duda, conservar.** Marcar un dato como sospechoso y explicarlo siempre
es mejor que borrarlo: el cliente puede revisar lo dudoso, pero no puede
recuperar lo que se tiró.

---

## 5. Reglas de trabajo

1. **Un ítem `DC.*` por tanda.** No adelantes el siguiente aunque «ya esté casi».
2. **Cada ítem cierra con la suite en verde** más lo que diga su línea *Cierre:*.
   Un ítem sin su cierre demostrado no está cerrado.
3. **Todo en español:** nombres de archivo, módulos, clases, funciones,
   variables, comentarios y commits. Convenciones de Python (`snake_case` en
   funciones y variables, `PascalCase` en clases), con palabras en español.
4. **Commits en Conventional Commits** (`feat(telefonos): …`).
5. **Sin `print` de depuración, sin código comentado, sin TODO** que no apunte a
   un ítem de este backlog.
6. **Los tests prueban comportamiento, no que el archivo exista.** Para cerrar un
   ítem que pide código, **al menos un test nuevo tiene que fallar sin ese
   código**: «la suite sigue verde» no prueba nada cuando ya venía verde. Y la
   demostración se hace con **`git stash`**, nunca con `git checkout` sobre
   trabajo sin commitear — eso destruye lo que aún no está a salvo.
7. **La suite completa corre sin red y sin credenciales.** Ni un solo test puede
   necesitar internet, una clave de API ni un servicio externo. **No es
   negociable** y aplica desde el primer ítem hasta el último.
8. **Errores:** nunca se le muestra al usuario un rastro de excepción ni un
   mensaje técnico. Un archivo que no se puede procesar **no puede tumbar el
   servicio**: se registra y se responde con un motivo comprensible.
9. **Datos personales.** Un archivo de contactos ES una lista de datos
   personales: nombres, teléfonos y correos de gente real. **Ni un dato de
   contacto puede aparecer en un log**, ni la clave del proveedor de IA.
10. **Los tests nuevos van en archivo propio**, no ampliando uno existente que ya
    sea grande.
11. **Si una herramienta o un comando te es denegado, para y repórtalo.** Nunca
    imites a mano el resultado que ese comando habría producido. **Un ítem
    bloqueado y dicho es un resultado válido; uno simulado, no.**
12. **Prohibido borrar o debilitar un test existente, y prohibido tocar un ítem
    ya cerrado** para que encaje tu diseño de hoy. Si un test viejo te estorba,
    eso es una tensión de diseño real: resuélvela o repórtala. **No la borres.**
13. **Cierra en este orden, y no otro: COMMIT primero, anotaciones después.**
    1. **`git commit`** en cuanto la suite esté en verde. Es lo único que no se
       puede rehacer desde fuera, así que va delante de todo.
    2. **`docs/bitacora.md`** — una fila por tanda, **solo-añadir** y **breve**:
       qué hiciste, iteraciones, tests añadidos, qué quedó pendiente. La fecha se
       saca de `git log -1 --date=short --pretty=%ad`, nunca se deduce. **Si el
       ítem NO cerró, también se anota**, con el motivo.
    3. **El backlog de este documento** — cambia el ⬜ del ítem por ✅ (o 🔄 si
       quedó a medias).
    4. **Un segundo `git commit` con esas anotaciones.**
    *Por qué este orden:* si se agota el turno, que se pierda la anotación —que
    cuesta un minuto reponer— y no el trabajo.
14. **`ENCARGO.md` y `docs/` son de solo lectura para ti**, con **dos únicas
    excepciones**, las de la regla 13: añadir tu fila en `docs/bitacora.md` y
    cambiar el **estado** de un ítem del backlog. **Nada más.** Si crees que un
    ítem está mal escrito o pide algo imposible, **dilo en tu fila de la
    bitácora** — eso es información valiosa— pero no lo reescribas tú.

---

## 6. Backlog V1

> **14 ítems, de `DC.0` a `DC.13`.** Cada uno pide **una** cosa. Lo que no está
> en la línea `Cierre:` no se hace.

- ⬜ **DC.0 — Levantar el proyecto.**
  Estructura del paquete, dependencias declaradas y la suite corriendo en vacío.
  *Cierre:* (1) `python -m pytest -q` corre y pasa desde un clon limpio;
  (2) existe un `pyproject.toml` con las dependencias fijadas;
  (3) hay un test que comprueba que el paquete `dataclean` se importa.

- ⬜ **DC.1 — Cargar el archivo, sea CSV o Excel.**
  Una sola función recibe una ruta y devuelve una tabla, decidiendo por el
  contenido y no por la extensión.
  *Cierre:* (1) carga un `.csv` y un `.xlsx` con las mismas columnas y devuelve
  la misma tabla; (2) un `.csv` guardado en **latin-1** (el que exporta Excel en
  español) se lee sin romper las tildes; (3) un archivo que no es ni CSV ni Excel
  devuelve un error **comprensible**, no una excepción.

- ⬜ **DC.2 — Saber qué es cada columna.**
  Las columnas llegan con nombres que nadie pactó: `TELEFONO`, `Cel`, `móvil 2`,
  `Correo electrónico`, `NOMBRE COMPLETO`. Hay que decidir qué es cada una.
  *Cierre:* (1) sobre una tabla con las cinco cabeceras de arriba, identifica
  cuáles son teléfono, cuáles correo y cuál nombre; (2) una columna que no
  reconoce se conserva **intacta** y se marca como no clasificada — no se
  descarta; (3) la clasificación **no distingue** mayúsculas, tildes ni espacios
  sobrantes.

- ⬜ **DC.3 — El teléfono, normalizado.**
  Un mismo número llega como `3001234567`, `300 123 4567`, `+57 300 1234567`,
  `(300)123-4567`. Todos son el mismo contacto.
  *Cierre:* (1) las cuatro formas de arriba producen **el mismo** valor
  normalizado; (2) el país se configura y no está escrito en el código;
  (3) un número que no se puede normalizar se conserva tal cual y se marca, **no
  se borra**.

- ⬜ **DC.4 — Móvil, fijo o inválido.**
  *Cierre:* (1) clasifica correctamente un móvil colombiano (10 dígitos que
  empiezan por 3), un fijo con indicativo y un número de 5 dígitos que no es ni
  una cosa ni otra; (2) **la trampa, y es el criterio de vendible:** ningún móvil
  válido puede quedar clasificado como inválido — hay un test con al menos 20
  móviles reales de formatos distintos y **cero falsos positivos**.

- ⬜ **DC.5 — El correo, revisado sin inventar.**
  *Cierre:* (1) detecta un correo sin `@`, uno con espacios y uno con dominio
  incompleto; (2) un correo **raro pero válido** (`nombre+etiqueta@dominio.com.co`)
  **no** se marca como inválido; (3) lo que se marca lleva **el motivo**, no solo
  la marca.

- ⬜ **DC.6 — El nombre, presentable.**
  `JUAN PEREZ`, `juan perez` y `Juan  Pérez ` son la misma persona escrita de
  tres formas.
  *Cierre:* (1) las tres formas producen el mismo nombre normalizado, con las
  tildes conservadas; (2) las partículas (`de`, `del`, `la`) **no** se ponen en
  mayúscula; (3) una sigla que ya venía en mayúsculas (`SAS`, `LTDA`) se
  conserva en mayúsculas.

- ⬜ **DC.7 — El cargo pegado al nombre, separado.**
  En estas listas es normal encontrar `MARIA GOMEZ - GERENTE` o
  `Pedro Ruiz (Contador)` en la misma celda. **Aquí es donde entra el LLM**,
  porque ninguna regla acierta con todos los formatos.
  *Cierre:* (1) el nombre y el cargo quedan en campos separados en los dos
  formatos de arriba; (2) **el LLM es sustituible**: la suite corre con una
  implementación falsa, sin red ni credenciales; (3) si el LLM no está
  disponible, el sistema **sigue funcionando** y deja el campo sin separar en vez
  de fallar.

- ⬜ **DC.8 — Duplicados por teléfono.**
  *Cierre:* (1) dos filas con el mismo teléfono en formatos distintos se
  detectan como duplicadas (esto solo funciona si DC.3 normalizó antes);
  (2) **no se borra ninguna**: se agrupan y se dice cuál se propone conservar y
  por qué; (3) dos filas con el teléfono vacío **no** son duplicadas entre sí.

- ⬜ **DC.9 — Duplicados por nombre parecido.**
  `Juan Pérez` y `JUAN PEREZ` son la misma persona; `Juan Pérez` y `Juana Pérez`
  no lo son.
  *Cierre:* (1) el primer par se agrupa y el segundo no; (2) el umbral de
  parecido se configura y no está escrito en el código; (3) un grupo de
  duplicados por nombre se marca como **sospechoso**, no como confirmado — ante
  la duda, conservar.

- ⬜ **DC.10 — El reporte, que es lo que se vende.**
  *Cierre:* (1) sobre un archivo de prueba, el reporte dice cuántos registros
  entraron, cuántos teléfonos se normalizaron, cuántos son móvil / fijo /
  inválido, cuántos correos se marcaron y cuántos grupos de duplicados hay;
  (2) **cada cifra se puede rastrear**: por cada una se puede pedir la lista de
  filas que la componen; (3) el reporte **no inventa**: si un dato no se pudo
  calcular dice que no se pudo, no pone cero.

- ⬜ **DC.11 — El archivo limpio, de vuelta.**
  *Cierre:* (1) se exporta a CSV y a Excel, y al releerlos los valores coinciden
  exactamente con los del reporte; (2) **las columnas originales se conservan**
  junto a las normalizadas — el cliente tiene que poder comparar; (3) el CSV se
  abre bien en un Excel en español (separador y codificación correctos).

- ⬜ **DC.12 — Ni un dato de contacto en el log.**
  *Cierre:* (1) test que procesa un archivo con una credencial configurada y
  comprueba que **ni la credencial ni ningún dato de contacto** —nombre,
  teléfono, correo— aparece en ninguna línea del log; (2) para que el test
  pruebe algo, el dato tiene que **llegar de verdad** al camino que escribe el
  log: si el montaje no lo hace entrar, el test no vale.

- ⬜ **DC.13 — Subir el archivo y recibir el resultado.**
  El endpoint que junta todo lo anterior.
  *Cierre:* (1) `POST` con un archivo devuelve el reporte y un identificador para
  descargar el limpio; (2) un archivo corrupto o vacío devuelve un motivo
  comprensible y **no tumba el servicio**; (3) el tamaño máximo se configura.

---

## 7. Cómo se mide esta tanda (para el evaluador, no para el agente)

- **Qué debe romper de Argos:** transformación masiva determinista con reglas
  encadenadas. El caso de uso de `codigo` con acceso a archivos (CH.2): miles de
  filas dentro, un resumen fuera. Si el modelo prefiere `ejecutar_comando` a la
  herramienta nueva, **eso es el dato**.
- **Piezas de núcleo sin tanda real que este proyecto estrena:** CH.2, la
  contraprueba (ARG-25b), el aviso de zona de cierre (ARG-28), la guarda del
  trabajo del turno (ARG-29), el alcance declarado (ARG-30) y los barridos de
  listas (ARG-31, ARG-33).
- **La pregunta de negocio que este proyecto existe para responder:** ¿alguien
  paga $3 por esto? Se responde **antes** de terminarlo: limpiando a mano la
  lista de un cliente real y cobrándosela.
