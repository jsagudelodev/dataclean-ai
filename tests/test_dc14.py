"""Tests del item DC.14: correcciones criticas de la revision de V1.

Cada test reproduce un defecto que la suite de V1 dejaba pasar:
    1) Un telefono que llega como numero (``int64`` o ``3001234567.0``,
       lo que pandas produce en cuanto la columna tiene una celda vacia)
       se marcaba INVALIDO: falsos positivos en masa.
    2) ``procesar_subida`` reventaba con ``AttributeError`` en cuanto el
       archivo tenia un grupo de duplicados por telefono.
    3) DC.9 tardaba decenas de segundos con 1.000 filas.
    4) Un CSV mal formado devolvia al cliente el texto tecnico de pandas.

Regla 6 (fuerte): los modulos se importan DENTRO de cada test.
"""

from __future__ import annotations

import importlib
import io
import time
from pathlib import Path

import pytest


def _modulo(nombre: str):
    return importlib.import_module(f"dataclean.{nombre}")


# Moviles colombianos reales de operadores distintos, como enteros: asi
# los guarda Excel cuando la celda tiene formato numero.
_MOVILES_NUMERICOS = [
    3001234567, 3012345678, 3023456789, 3104567890, 3115678901,
    3126789012, 3137890123, 3148901234, 3159012345, 3160123456,
    3171234567, 3182345678, 3203456789, 3214567890, 3225678901,
    3236789012, 3507890123, 3518901234, 3029012345, 3050123456,
]


# ---------------------------------------------------------------------------
# 1) Telefonos numericos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    [3001234567, 3001234567.0],
    ids=["int", "float-entero"],
)
def test_telefono_numerico_se_normaliza(valor: object) -> None:
    telefono = _modulo("telefono")
    assert telefono.normalizar_telefono(valor) == ("3001234567", True)


def test_telefono_numpy_se_normaliza() -> None:
    import numpy as np

    telefono = _modulo("telefono")
    assert telefono.normalizar_telefono(np.int64(3001234567)) == ("3001234567", True)
    assert telefono.normalizar_telefono(np.float64(3001234567.0)) == ("3001234567", True)


@pytest.mark.parametrize(
    "valor",
    [3001234567.5, float("nan"), True, float("inf")],
    ids=["con-decimales", "nan", "booleano", "infinito"],
)
def test_numero_que_no_es_telefono_se_marca(valor: object) -> None:
    telefono = _modulo("telefono")
    assert telefono.normalizar_telefono(valor) == (None, False)


def test_columna_con_una_celda_vacia_no_marca_moviles_como_invalidos() -> None:
    """El caso real: pandas lee la columna como float64 por un hueco."""
    import pandas as pd

    telefono = _modulo("telefono")
    tabla = pd.read_csv(io.StringIO("nombre,tel\nAna,3001234567\nBeto,6015551234\nCarla,\n"))
    assert tabla["tel"].dtype == "float64"
    tipos = telefono.clasificar_columna_telefono(tabla, "tel")["tel_tipo"].tolist()
    assert tipos == [telefono.TIPO_MOVIL, telefono.TIPO_FIJO, telefono.TIPO_INVALIDO]


def test_excel_numerico_con_hueco_cero_falsos_positivos(tmp_path: Path) -> None:
    """Criterio de vendible sobre un .xlsx real: 20 moviles, cero invalidos."""
    import pandas as pd

    carga = _modulo("carga")
    telefono = _modulo("telefono")
    ruta = tmp_path / "contactos.xlsx"
    # El hueco va en medio y con nombre: Excel descarta una fila final vacia.
    telefonos = _MOVILES_NUMERICOS[:10] + [None] + _MOVILES_NUMERICOS[10:]
    nombres = [f"Contacto {i}" for i in range(len(telefonos))]
    pd.DataFrame({"nombre": nombres, "telefono": telefonos}).to_excel(ruta, index=False)

    tabla = carga.cargar_tabla(ruta)
    assert tabla["telefono"].dtype == "float64"
    tipos = telefono.clasificar_columna_telefono(tabla, "telefono")["telefono_tipo"].tolist()
    assert tipos.pop(10) == telefono.TIPO_INVALIDO
    assert tipos == [telefono.TIPO_MOVIL] * 20


# ---------------------------------------------------------------------------
# 2) El endpoint con duplicados
# ---------------------------------------------------------------------------


def test_procesar_subida_con_duplicados_devuelve_los_grupos(tmp_path: Path) -> None:
    endpoint = _modulo("endpoint")
    servicio = endpoint.ServicioLimpieza(carpeta_salida=tmp_path)
    csv = (
        "nombre,telefono\n"
        "Ana,3001234567\n"
        "Beto,300 123 4567\n"
        "Carla,3109876543\n"
    ).encode("utf-8")

    resultado = endpoint.procesar_subida(csv, "c.csv", servicio=servicio)

    grupos = resultado["reporte"]["grupos_duplicados"]
    assert grupos["valor"] == 1
    assert grupos["grupos"] == [{"id": "tel-3001234567", "filas": [0, 1]}]


# ---------------------------------------------------------------------------
# 3) Rendimiento de DC.9
# ---------------------------------------------------------------------------


def _nombres_distintos(cantidad: int) -> list[str]:
    return [f"Nombre{i} Apellido{i * 7}" for i in range(cantidad)]


def test_duplicados_por_nombre_1000_filas_en_segundos() -> None:
    import pandas as pd

    duplicados = _modulo("duplicados")
    tabla = pd.DataFrame({"nombre": _nombres_distintos(1000)})

    inicio = time.perf_counter()
    duplicados.detectar_duplicados_por_nombre(tabla, "nombre")
    assert time.perf_counter() - inicio < 3.0


def test_nombre_repetido_se_une_a_su_grupo_aunque_el_representante_cambie() -> None:
    """Un canonico ya visto va a su grupo sin depender del parecido.

    Con umbral 0.8, ``Ana Gil`` abre el grupo, ``Ana Giles`` entra por
    parecido y pasa a ser el representante (es mas largo). El segundo
    ``Ana Gil`` tiene que caer en el mismo grupo que el primero.
    """
    import pandas as pd

    duplicados = _modulo("duplicados")
    tabla = pd.DataFrame({"nombre": ["Ana Gil", "Ana Giles", "Ana Gil"]})
    resultado = duplicados.detectar_duplicados_por_nombre(
        tabla, "nombre", similitud_minima=0.8
    )
    grupos = resultado["grupo_id"].tolist()
    assert grupos[0] == grupos[1] == grupos[2]
    assert resultado["sospechoso"].tolist() == [True, True, True]


def test_umbral_bajo_da_lo_mismo_que_la_comparacion_directa() -> None:
    """El atajo de cotas no cambia que pares se agrupan."""
    duplicados = _modulo("duplicados")
    grupos = {"g1": "Juan Perez", "g2": "Maria Lopez", "g3": "Pedro Ruiz"}
    for nombre in ["Juana Perez", "Mario Lopez", "Luisa Diaz", "Pedro Ruis"]:
        for umbral in (0.5, 0.8, 0.9):
            esperado = next(
                (gid for gid, otro in grupos.items()
                 if duplicados._similitud(nombre, otro) >= umbral),
                None,
            )
            assert duplicados._grupo_parecido(nombre, grupos, umbral) == esperado


# ---------------------------------------------------------------------------
# 4) Mensajes tecnicos
# ---------------------------------------------------------------------------


def test_csv_mal_formado_no_devuelve_el_texto_de_pandas(tmp_path: Path) -> None:
    carga = _modulo("carga")
    ruta = tmp_path / "roto.csv"
    ruta.write_bytes(b'a,b\n"x,1\n1,2,3,4\n')

    with pytest.raises(carga.ErrorDeCargaInesperado) as excinfo:
        carga.cargar_tabla(ruta)
    mensaje = str(excinfo.value)
    assert "tokenizing" not in mensaje
    assert "C error" not in mensaje
    assert mensaje == carga.MENSAJE_CSV_MAL_FORMADO


def test_excel_danado_devuelve_motivo_legible(tmp_path: Path) -> None:
    carga = _modulo("carga")
    ruta = tmp_path / "roto.xlsx"
    ruta.write_bytes(b"PK\x03\x04" + b"esto no es un libro de excel" * 10)

    with pytest.raises(carga.ErrorDeCargaInesperado) as excinfo:
        carga.cargar_tabla(ruta)
    assert str(excinfo.value) == carga.MENSAJE_EXCEL_DANADO


def test_csv_solo_con_espacios_dice_que_no_hay_datos(tmp_path: Path) -> None:
    carga = _modulo("carga")
    ruta = tmp_path / "vacio.csv"
    ruta.write_bytes(b"\n\n  \n")

    with pytest.raises(carga.ErrorDeCargaInesperado) as excinfo:
        carga.cargar_tabla(ruta)
    assert str(excinfo.value) == carga.MENSAJE_SIN_DATOS
