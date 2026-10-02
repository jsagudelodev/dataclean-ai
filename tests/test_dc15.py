"""DC.15 -- Mil filas reales.

El criterio de vendible del ENCARGO (seccion 4) habla de "un Excel
real y sucio de 1.000 filas", y hasta este item nadie lo habia
medido: los tests eran sinteticos y por pieza. Este archivo **no
anade funcionalidad, mide la que hay**, y lo hace por donde entra
un cliente de verdad: el endpoint completo.

El archivo de prueba lo arma ``_generar_archivo_sucio``, que es
determinista y **sabe exactamente que metio**. Por eso el reporte
se puede contrastar cifra a cifra: si el reporte dice 700 moviles,
es porque el generador metio 700, no porque el reporte se mire a
si mismo.

Regla 7: sin red, sin credenciales, sin aleatoriedad no sembrada.
"""

import os
import time
from dataclasses import dataclass

# Composicion del archivo de prueba. Suman FILAS_TOTALES.
MOVILES_UNICOS = 650
FIJOS = 200
INVALIDOS = 100
DUPLICADOS = 50
FILAS_TOTALES = MOVILES_UNICOS + FIJOS + INVALIDOS + DUPLICADOS

# Moviles esperados: los unicos mas las copias (una copia de un
# movil sigue siendo un movil).
MOVILES_TOTALES = MOVILES_UNICOS + DUPLICADOS

# Correos invalidos sembrados: uno de cada cuatro moviles unicos.
# Se cuenta sobre el rango real para no repetir la aritmetica a
# mano (el primer intento dijo 162 donde hay 163).
CORREOS_MARCADOS = len([i for i in range(MOVILES_UNICOS) if i % 4 == 0])

# Techo de tiempo del pipeline completo, en segundos. Se configura
# por entorno (cierre 3); el default es holgado a proposito: lo que
# el test vigila es una regresion gorda, no el ruido de la maquina.
ENV_SEGUNDOS_MAXIMOS = "DATACLEAN_SEGUNDOS_MAXIMOS"
SEGUNDOS_MAXIMOS_POR_DEFECTO = 60.0

# Veinte formatos reales de movil colombiano (DC.4 cierre 2).
_FORMATOS_MOVIL = (
    "{p}{s}",
    "{p} {a} {b}",
    "+57 {p} {s}",
    "+57{p}{s}",
    "57 {p}{s}",
    "({p}){a}-{b}",
    "{p}-{a}-{b}",
    "{p} {a}{b}",
    " {p}{s} ",
    "{p}.{a}.{b}",
    "+57 ({p}) {a} {b}",
    "0057{p}{s}",
    "{p} - {a} - {b}",
    "({p}) {a}-{b}",
    "+57-{p}-{s}",
    "{p}/{a}/{b}",
    "57-{p}-{s}",
    "{p}  {a}  {b}",
    "+57 {p}-{a}-{b}",
    "{p}{a} {b}",
)

_VALORES_INVALIDOS = (
    "12345",
    "sin numero",
    "N/A",
    "---",
    "0",
    "no tiene",
    "123",
    "tel: pendiente",
    "?",
    "xxxx",
)

_CARGOS = ("GERENTE", "CONTADOR", "DIRECTOR", "ASISTENTE")


@dataclass(frozen=True)
class ArchivoSucio:
    """El CSV generado y lo que el generador sabe que metio."""

    contenido: bytes
    filas_moviles: tuple[int, ...]
    filas_fijos: tuple[int, ...]
    filas_invalidos: tuple[int, ...]
    filas_correos_marcados: tuple[int, ...]
    grupos_duplicados: int


def _movil_numero(indice: int) -> str:
    """Devuelve un movil colombiano unico y determinista."""
    # 3 + dos digitos de operador + siete de abonado.
    operador = 0 + (indice % 20)
    abonado = 1000000 + indice
    return f"3{operador:02d}{abonado % 10000000:07d}"


def _con_formato(numero: str, indice: int) -> str:
    """Escribe ``numero`` con uno de los veinte formatos reales."""
    plantilla = _FORMATOS_MOVIL[indice % len(_FORMATOS_MOVIL)]
    return plantilla.format(
        p=numero[:3], s=numero[3:], a=numero[3:6], b=numero[6:]
    )


def _generar_archivo_sucio() -> ArchivoSucio:
    """Arma un CSV de 1.000 filas sucio pero de composicion conocida."""
    cabecera = "NOMBRE COMPLETO,TELEFONO,CORREO"
    lineas = [cabecera]
    moviles: list[int] = []
    fijos: list[int] = []
    invalidos: list[int] = []
    correos_malos: list[int] = []
    # Los moviles que luego se repetiran, con su formato original.
    repetibles: list[str] = []

    for i in range(MOVILES_UNICOS):
        fila = len(lineas) - 1
        numero = _movil_numero(i)
        repetibles.append(numero)
        telefono = _con_formato(numero, i)
        # Un nombre de cada tres trae el cargo pegado (DC.7).
        nombre = f"Contacto Numero {i:04d}"
        if i % 3 == 0:
            nombre = f"{nombre} - {_CARGOS[i % len(_CARGOS)]}"
        # Uno de cada cuatro correos viene roto (DC.5).
        if i % 4 == 0:
            correo = f"contacto{i:04d}#dominio"
            correos_malos.append(fila)
        else:
            correo = f"contacto{i:04d}@dominio.com.co"
        lineas.append(f"{nombre},{telefono},{correo}")
        moviles.append(fila)

    for i in range(FIJOS):
        fila = len(lineas) - 1
        numero = f"60{1 + (i % 8)}{2000000 + i:07d}"[:10]
        lineas.append(
            f"Oficina Numero {i:04d},{numero},"
            f"oficina{i:04d}@dominio.com.co"
        )
        fijos.append(fila)

    for i in range(INVALIDOS):
        fila = len(lineas) - 1
        valor = _VALORES_INVALIDOS[i % len(_VALORES_INVALIDOS)]
        lineas.append(
            f"Dudoso Numero {i:04d},{valor},"
            f"dudoso{i:04d}@dominio.com.co"
        )
        invalidos.append(fila)

    for i in range(DUPLICADOS):
        fila = len(lineas) - 1
        numero = repetibles[i]
        # El mismo numero, otro formato: es el caso que DC.8 existe
        # para cazar. Mismo nombre, porque es la misma persona.
        telefono = _con_formato(numero, i + 7)
        lineas.append(
            f"Contacto Numero {i:04d},{telefono},"
            f"contacto{i:04d}@otrodominio.com"
        )
        moviles.append(fila)

    contenido = "\n".join(lineas).encode("utf-8")
    return ArchivoSucio(
        contenido=contenido,
        filas_moviles=tuple(moviles),
        filas_fijos=tuple(fijos),
        filas_invalidos=tuple(invalidos),
        filas_correos_marcados=tuple(correos_malos),
        grupos_duplicados=DUPLICADOS,
    )


def _segundos_maximos() -> float:
    """Techo de tiempo, configurable por entorno (cierre 3)."""
    crudo = os.environ.get(ENV_SEGUNDOS_MAXIMOS, "").strip()
    if not crudo:
        return SEGUNDOS_MAXIMOS_POR_DEFECTO
    try:
        valor = float(crudo)
    except ValueError:
        return SEGUNDOS_MAXIMOS_POR_DEFECTO
    return valor if valor > 0 else SEGUNDOS_MAXIMOS_POR_DEFECTO


# ---------------------------------------------------------------------------
# El generador tiene que ser de fiar antes de usarlo como vara de medir
# ---------------------------------------------------------------------------


def test_el_generador_produce_mil_filas_de_composicion_conocida():
    """Si el generador miente, el resto del archivo no mide nada."""
    archivo = _generar_archivo_sucio()

    lineas = archivo.contenido.decode("utf-8").splitlines()
    assert len(lineas) - 1 == FILAS_TOTALES == 1000
    assert len(archivo.filas_moviles) == MOVILES_TOTALES
    assert len(archivo.filas_fijos) == FIJOS
    assert len(archivo.filas_invalidos) == INVALIDOS
    # Ninguna fila esta en dos categorias a la vez.
    todas = (
        set(archivo.filas_moviles)
        | set(archivo.filas_fijos)
        | set(archivo.filas_invalidos)
    )
    assert len(todas) == FILAS_TOTALES


# ---------------------------------------------------------------------------
# Cierre 1 -- el reporte cuadra, de extremo a extremo
# ---------------------------------------------------------------------------


def test_mil_filas_por_el_endpoint_y_el_reporte_cuadra(tmp_path):
    """Cierre 1: lo que sale del endpoint es lo que el generador metio."""
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    archivo = _generar_archivo_sucio()
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    resultado = servicio.procesar(archivo.contenido, "sucio.csv")
    reporte = resultado["reporte"]

    assert reporte["total_registros"] == FILAS_TOTALES
    assert reporte["telefonos_moviles"]["valor"] == MOVILES_TOTALES
    assert reporte["telefonos_fijos"]["valor"] == FIJOS
    assert reporte["telefonos_invalidos"]["valor"] == INVALIDOS
    assert (
        reporte["telefonos_normalizados"]["valor"]
        == MOVILES_TOTALES + FIJOS
    )
    assert reporte["correos_marcados"]["valor"] == CORREOS_MARCADOS
    assert (
        reporte["grupos_duplicados"]["valor"] == archivo.grupos_duplicados
    )
    # Y el archivo limpio existe y se puede bajar.
    assert servicio.existe(resultado["id"])


def test_el_archivo_limpio_tiene_las_mil_filas(tmp_path):
    """Cierre 1: no se pierde ni se inventa ninguna fila por el camino."""
    import pandas as pd
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    archivo = _generar_archivo_sucio()
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    resultado = servicio.procesar(archivo.contenido, "sucio.csv")

    limpio = pd.read_csv(resultado["ruta"], sep=";", encoding="utf-8-sig")
    assert len(limpio) == FILAS_TOTALES
    # Las columnas originales se conservan (DC.11 cierre 2).
    for columna in ("NOMBRE COMPLETO", "TELEFONO", "CORREO"):
        assert columna in limpio.columns


# ---------------------------------------------------------------------------
# Cierre 2 -- cero falsos positivos a escala
# ---------------------------------------------------------------------------


def test_cero_falsos_positivos_en_mil_filas(tmp_path):
    """Cierre 2: ni UN movil bueno marcado como invalido.

    Es el criterio de vendible de la seccion 4 del ENCARGO: un
    servicio que descarta contactos buenos no se puede vender,
    acierte lo que acierte en lo demas.
    """
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    archivo = _generar_archivo_sucio()
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    reporte = servicio.procesar(archivo.contenido, "sucio.csv")["reporte"]

    marcadas_invalidas = set(reporte["telefonos_invalidos"]["filas"])
    falsos_positivos = sorted(
        set(archivo.filas_moviles) & marcadas_invalidas
    )
    assert not falsos_positivos, (
        f"{len(falsos_positivos)} movil(es) bueno(s) marcados como "
        f"invalidos; primeras filas: {falsos_positivos[:10]}"
    )

    # Y el reves: ningun invalido coló como movil o fijo.
    buenos = set(reporte["telefonos_moviles"]["filas"]) | set(
        reporte["telefonos_fijos"]["filas"]
    )
    colados = sorted(set(archivo.filas_invalidos) & buenos)
    assert not colados, f"basura clasificada como telefono: {colados[:10]}"


def test_el_prefijo_de_salida_internacional_no_es_un_falso_positivo():
    """El falso positivo concreto que destapo la medicion de DC.15.

    ``0057`` es el prefijo de SALIDA internacional, y es como
    exporta la agenda de muchos moviles. Se marcaba como invalido
    mientras que ``+57`` y ``57`` si se reconocian: uno de cada
    veinte formatos, ~50 contactos buenos tirados por cada 1.000.
    """
    from dataclean.telefono import clasificar_telefono

    for crudo in ("00573001234567", "0057 300 1234567", "0057-300-1234567"):
        canonico, tipo, _ = clasificar_telefono(crudo)
        assert tipo == "MOVIL", f"{crudo!r} quedo como {tipo}"
        assert canonico == "3001234567"

    # Y no se gana a costa de inventar: un numero de otro pais con
    # el mismo prefijo de salida se sigue marcando, no se fuerza.
    _, tipo_extranjero, _ = clasificar_telefono("00349112345678")
    assert tipo_extranjero == "INVALIDO"


def test_ningun_correo_bueno_queda_marcado(tmp_path):
    """Cierre 2, el mismo criterio aplicado al correo (DC.5 cierre 2)."""
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    archivo = _generar_archivo_sucio()
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    reporte = servicio.procesar(archivo.contenido, "sucio.csv")["reporte"]

    marcados = set(reporte["correos_marcados"]["filas"])
    esperados = set(archivo.filas_correos_marcados)
    assert not (marcados - esperados), (
        "correos buenos marcados: "
        f"{sorted(marcados - esperados)[:10]}"
    )


# ---------------------------------------------------------------------------
# Cierre 3 -- el tiempo, medido y con techo configurable
# ---------------------------------------------------------------------------


def test_mil_filas_dentro_del_techo_de_tiempo(tmp_path, record_property):
    """Cierre 3: deja escrito cuanto tardo y falla si pasa el techo.

    El tiempo queda en las propiedades del test (``--junitxml`` las
    recoge), no en un ``print`` (regla 5). Si el techo se incumple,
    se anota en la bitacora en vez de subirlo.
    """
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    archivo = _generar_archivo_sucio()
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    comienzo = time.perf_counter()
    servicio.procesar(archivo.contenido, "sucio.csv")
    segundos = time.perf_counter() - comienzo

    techo = _segundos_maximos()
    record_property("filas", FILAS_TOTALES)
    record_property("segundos", round(segundos, 3))
    record_property("techo_segundos", techo)

    assert segundos < techo, (
        f"el pipeline tardo {segundos:.1f}s con {FILAS_TOTALES} filas, "
        f"por encima del techo de {techo:.1f}s"
    )


def test_el_techo_de_tiempo_se_configura(monkeypatch):
    """Cierre 3: el techo sale del entorno, no esta escrito en el codigo."""
    monkeypatch.setenv(ENV_SEGUNDOS_MAXIMOS, "12.5")
    assert _segundos_maximos() == 12.5

    # Un valor absurdo no deja el test sin techo: se cae al default.
    monkeypatch.setenv(ENV_SEGUNDOS_MAXIMOS, "-3")
    assert _segundos_maximos() == SEGUNDOS_MAXIMOS_POR_DEFECTO

    monkeypatch.setenv(ENV_SEGUNDOS_MAXIMOS, "ni idea")
    assert _segundos_maximos() == SEGUNDOS_MAXIMOS_POR_DEFECTO

    monkeypatch.delenv(ENV_SEGUNDOS_MAXIMOS)
    assert _segundos_maximos() == SEGUNDOS_MAXIMOS_POR_DEFECTO
