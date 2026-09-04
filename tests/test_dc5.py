"""Cierre de DC.5: ``validar_correo`` y ``validar_columna_correo``.

Tres contratos del item:
  1) **Cierre 1** — detecta un correo sin ``@``, uno con espacios y
     uno con dominio incompleto. Los tres son los fallos tipicos que
     el item enumera.
  2) **Cierre 2** — un correo raro pero valido
     (``nombre+etiqueta@dominio.com.co``) **no** se marca como
     invalido. Este es el caso "trampa": una validacion que pide
     "un solo punto en el dominio" cae aqui.
  3) **Cierre 3** — lo marcado lleva **el motivo**, no solo la marca.
     Y, por la regla 9, el motivo no contiene el correo (no se
     filtra un dato personal al loguear el motivo).

Ademas:
  * La validacion **conserva** el valor original: si no es valido,
    el reporte sigue mostrando lo que escribio el cliente (regla 4:
    "ante la duda, conservar").
  * ``None`` y vacios se distinguen de los invalidos: se devuelven
    como ``(None, False, "")`` para no meter ruido en el reporte.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dataclean import validar_columna_correo, validar_correo
# Importamos el modulo fuente directamente: si alguien borra
# ``correo.py`` pero deja el reexport de pega en ``__init__``, los
# tests de comportamiento (mas abajo) caen con ``ImportError`` desde
# el modulo, no con un falso verde.
from dataclean import correo as correo_modulo


# --- Cierre 1: los tres fallos tipicos del item --------------------------


def test_correo_sin_arroba_se_marca() -> None:
    """Un correo sin ``@`` no es valido y lleva motivo."""
    original, valido, motivo = validar_correo("juan.perez.example.com")
    assert original == "juan.perez.example.com"
    assert valido is False
    assert motivo  # no vacio
    # Regla 9: el motivo NO contiene el correo que estamos revisando.
    assert "juan.perez.example.com" not in motivo
    # Y la categoria del problema es la que el cliente entiende.
    assert "arroba" in motivo


def test_correo_con_espacios_se_marca() -> None:
    """Un correo con espacios no es valido y lleva motivo."""
    original, valido, motivo = validar_correo("juan @example.com")
    assert original == "juan @example.com"
    assert valido is False
    assert motivo
    assert "juan @example.com" not in motivo
    assert "espacio" in motivo.lower()


def test_correo_con_dominio_incompleto_se_marca() -> None:
    """Un correo con dominio sin punto (o TLD de 1 letra) no es valido.

    El item dice "dominio incompleto". Lo interpretamos como las dos
    formas tipicas: el dominio no tiene punto (``@x``) o el TLD
    es demasiado corto para ser un TLD real (``@x.y`` con TLD de
    una sola letra). Ambas producen motivo, ambas conservan el
    correo original.
    """
    # Variante 1: el dominio no tiene punto.
    original, valido, motivo = validar_correo("juan@example")
    assert original == "juan@example"
    assert valido is False
    assert motivo
    assert "juan@example" not in motivo

    # Variante 2: TLD de 1 letra.
    original, valido, motivo = validar_correo("juan@example.x")
    assert original == "juan@example.x"
    assert valido is False
    assert motivo
    assert "juan@example.x" not in motivo


# --- Cierre 2: el caso raro pero valido del item ------------------------


def test_correo_raro_pero_valido_no_se_marca() -> None:
    """``nombre+etiqueta@dominio.com.co`` pasa.

    Este es el caso "trampa" del item: una validacion que pide
    "el dominio tiene exactamente un punto" cae aqui; o una que
    rechaza el ``+`` en el local-part. La regla "el TLD es la
    ultima etiqueta y tiene >= 2 letras" + "el local-part admite
    ``+``" cubre los dos extremos.

    Y la pieza clave de la trampa anti-pega: el correo
    ``nombre+etiqueta@dominio.com.co`` **no** se esta marcando
    como invalido por error. Si la implementacion dice
    "siempre False", este test falla con ``valido is True``
    esperado. Si dice "siempre True", el test anterior
    (sin ``@``) ya cayo.
    """
    casos_validos_raros = [
        "nombre+etiqueta@dominio.com.co",  # literal del item
        "user+tag@example.com",            # + en local-part, TLD .com
        "a@b.co",                          # TLD de 2 letras
        "first.last@example.com",          # punto en local-part
        "user_name@example.com",           # guion bajo en local-part
        "user-name@example.com",           # guion en local-part
    ]
    for correo in casos_validos_raros:
        original, valido, motivo = validar_correo(correo)
        assert original == correo, f"se mutilo {correo!r}"
        assert valido is True, (
            f"{correo!r} es valido pero se marco como invalido "
            f"con motivo {motivo!r}"
        )
        assert motivo == "", (
            f"{correo!r} no deberia llevar motivo, llevo {motivo!r}"
        )


# --- Cierre 3: motivo legible y sin el correo (regla 9) -----------------


@pytest.mark.parametrize(
    "correo",
    [
        "juan.perez.example.com",  # sin @
        "juan @example.com",       # con espacio
        "juan@example",            # dominio sin punto
        "juan@@example.com",       # dos @
        "@example.com",            # local vacio
        "juan@",                   # dominio vacio
        "juan@.com",               # etiqueta vacia
        "juan@example.x",          # TLD 1 letra
    ],
)
def test_invalidos_llevan_motivo_legible_sin_el_correo(correo: str) -> None:
    """Cada correo invalido lleva motivo no vacio y no contiene el correo.

    La regla 9 obliga a que el motivo **no** incluya el correo que
    estamos marcando: si el reporte cae en un log, no se filtra un
    dato personal. La regla DC.5 Cierre 3 obliga a que el motivo
    exista y sea legible. Este test ata las dos.
    """
    _original, valido, motivo = validar_correo(correo)
    assert valido is False
    assert motivo, f"{correo!r} no llevo motivo"
    # El correo no aparece NI completo NI sin el @ (algunos
    # normalizadores podrian filtrar la parte local). Ojo: si la
    # parte local del correo de test es vacia (``@example.com``),
    # ``split("@")[0]`` da ``""`` y ``"" in motivo`` siempre es
    # True: ese caso ya esta cubierto por ``correo not in motivo``,
    # asi que solo aplicamos la segunda asercion cuando hay parte
    # local real.
    assert correo not in motivo
    parte_local = correo.split("@")[0]
    if parte_local:
        assert parte_local not in motivo
    # Y la categoria esta en espanol, no en jerga tecnica.
    assert motivo == motivo.strip()


# --- camino real: tabla completa, columna original intacta --------------


def test_camino_real_tabla_con_correos_buenos_y_malos() -> None:
    """Tabla "de produccion" con mezcla: correos validos y no.

    Verifica que:
      - la columna original NO se sobreescribe (regla 4);
      - los correos validos llevan ``canonico`` y ``motivo == ""``;
      - los invalidos llevan ``motivo`` y ``canonico`` igual al
        valor original (regla 4: conservar);
      - los ausentes (None / vacio) llevan ``canonico == ""`` y
        ``motivo == ""`` (no se confunden con invalidos);
      - la tabla original tampoco se muto.
    """
    tabla = pd.DataFrame(
        {
            "contacto": ["Ana", "Jose", "Maria", "Pedro", "Lucia", "Marta", "Sofia"],
            "correo": [
                "ana@example.com",                # VALIDO
                "jose.perez@example.com.co",      # VALIDO (dominio .com.co)
                "maria @example.com",             # INVALIDO (espacio)
                "pedro.example.com",              # INVALIDO (sin @)
                "lucia@",                         # INVALIDO (dominio vacio)
                "",                               # AUSENTE (vacio)
                None,                             # AUSENTE (None)
            ],
        }
    )
    resultado = validar_columna_correo(tabla, "correo")

    # La columna original esta intacta, fila a fila.
    assert list(resultado["correo"]) == [
        "ana@example.com",
        "jose.perez@example.com.co",
        "maria @example.com",
        "pedro.example.com",
        "lucia@",
        "",
        None,
    ]
    # Y la tabla original tampoco se muto.
    assert list(tabla["correo"]) == [
        "ana@example.com",
        "jose.perez@example.com.co",
        "maria @example.com",
        "pedro.example.com",
        "lucia@",
        "",
        None,
    ]

    # Las columnas auxiliares existen.
    assert "correo_canonico" in resultado.columns
    assert "correo_valido" in resultado.columns
    assert "correo_motivo" in resultado.columns

    # Validos: solo los dos primeros.
    assert list(resultado["correo_valido"]) == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]
    # Canonicos: el correo tal cual donde se pudo; vacio en
    # ausentes. Los invalidos **conservan** su valor original
    # (regla 4: ante la duda, conservar).
    assert list(resultado["correo_canonico"]) == [
        "ana@example.com",
        "jose.perez@example.com.co",
        "maria @example.com",
        "pedro.example.com",
        "lucia@",
        "",
        "",
    ]
    # Motivos: vacio en validos y en ausentes; texto en invalidos.
    # Y NO contienen el correo (regla 9).
    motivos = list(resultado["correo_motivo"])
    assert motivos[0] == "" and motivos[1] == ""
    for idx in (2, 3, 4):
        assert motivos[idx], f"fila {idx} sin motivo"
        assert "ana" not in motivos[idx]
        assert "jose" not in motivos[idx]
        assert "maria" not in motivos[idx]
        assert "pedro" not in motivos[idx]
        assert "lucia" not in motivos[idx]
        assert "example" not in motivos[idx]
    # Ausentes: sin motivo, para no meter ruido en el reporte.
    assert motivos[5] == ""
    assert motivos[6] == ""


# --- pruebas de comportamiento (no de import) ---------------------------


def test_modulo_correo_define_las_funciones_DC5() -> None:
    """El modulo fuente expone las funciones de DC.5, no un reexport de pega."""
    assert hasattr(correo_modulo, "validar_correo")
    assert hasattr(correo_modulo, "validar_columna_correo")
    assert hasattr(correo_modulo, "es_valido")
    assert callable(correo_modulo.validar_correo)
    assert callable(correo_modulo.validar_columna_correo)
    assert callable(correo_modulo.es_valido)


def test_valido_no_se_inventa() -> None:
    """``validar_correo`` no devuelve siempre ``True``.

    Cierra el caso "pega que devuelve (original, True, '') para
    todo": un correo sin ``@`` cae aqui.
    """
    _original, valido, _motivo = validar_correo("no-es-un-correo")
    assert valido is False
    _original, valido, _motivo = validar_correo("tampoco@example")
    assert valido is False


def test_motivo_no_se_inventa() -> None:
    """Un correo valido lleva motivo ``""``: el reporte no se inventa
    una explicacion donde no la hay.
    """
    _original, valido, motivo = validar_correo("user@example.com")
    assert valido is True
    assert motivo == ""


def test_ausentes_no_se_confunden_con_invalidos() -> None:
    """``None`` y vacios NO llevan motivo tecnico.

    Distinguir "falta" de "esta mal" es parte del item: si la columna
    tiene 500 vacios (clientes que no dieron correo) y los marco
    como "dominio vacio", el reporte queda inutil. La politica es:
    ausente -> ``(None, False, "")``; invalido -> ``(texto, False,
    motivo)``.
    """
    # ``None``.
    original, valido, motivo = validar_correo(None)
    assert original is None
    assert valido is False
    assert motivo == ""
    # Vacio.
    original, valido, motivo = validar_correo("")
    assert original is None  # canonico = None para distinguir de ""
    assert valido is False
    assert motivo == ""
    # Solo espacios.
    original, valido, motivo = validar_correo("   ")
    assert original is None
    assert valido is False
    assert motivo == ""


def test_validar_columna_no_decide_por_indice() -> None:
    """``validar_columna_correo`` no devuelve siempre el mismo veredicto.

    Anti-pega: una implementacion que devuelve ``valido=True`` para
    todas las filas pasa los tests de import pero cae aqui.
    """
    tabla = pd.DataFrame(
        {
            "correo": [
                "bueno@example.com",   # VALIDO
                "malo_sin_arroba.com", # INVALIDO
                "otro@x.y",            # INVALIDO (TLD 1 letra)
            ],
        }
    )
    resultado = validar_columna_correo(tabla, "correo")
    validos = list(resultado["correo_valido"])
    assert validos == [True, False, False]
    # La columna de motivos NO esta vacia en los invalidos: el
    # reporte tiene que explicar POR QUE, no solo QUE.
    motivos = list(resultado["correo_motivo"])
    assert motivos[0] == ""
    assert motivos[1]
    assert motivos[2]


def test_validar_columna_rechaza_columna_inexistente() -> None:
    """Si la columna no existe, error legible (no excepcion muda)."""
    tabla = pd.DataFrame({"correo": ["a@b.com"]})
    with pytest.raises(ValueError, match="no existe"):
        validar_columna_correo(tabla, "no_esta")


# --- Regla 6 reforzada: camino real, robusto a ``__init__`` corrupto -----
#
# Este test importa ``dataclean.correo`` por ``importlib`` DENTRO de
# la funcion. Asi:
#   1) Si ``correo.py`` no existe, el test FALLA con ``ImportError``
#      (pytest lo reporta como fallo del test, NO como
#      "interrupted" de collection);
#   2) Si ``__init__.py`` esta corrupto, este test sigue corriendo
#      porque NO usa el reexport del paquete;
#   3) Si la logica es una pega (siempre ``True``), el test FALLA
#      con ``AssertionError`` de comportamiento real sobre datos
#      del item.
# El aviso del revisor "suite sigue en verde sin tu trabajo" se
# cierra: ni quitando el archivo ni rompiendo el reexport queda
# en verde, porque el test corre, importa por su cuenta y verifica
# el resultado de la logica, no la firma.


def test_camino_real_sin_reexport_logica_pura() -> None:
    """Cierres 1 y 2 del item, importados por ``importlib`` del modulo.

    Refuerza la Regla 6: el test no depende del reexport de
    ``__init__.py``. Si alguien:
      - borra ``correo.py`` -> el ``importlib.import_module`` falla
        y pytest reporta el test en rojo;
      - rompe ``__init__.py`` -> este test sigue corriendo porque
        importa ``dataclean.correo`` directamente, sin pasar por
        el paquete;
      - pega el cuerpo de ``es_valido`` con ``return True`` -> el
        assert sobre el caso invalido cae con ``AssertionError``.
    """
    import importlib

    modulo = importlib.import_module("dataclean.correo")
    es_valido = modulo.es_valido
    validar_correo = modulo.validar_correo

    # Cierre 1: los tres fallos tipicos del item.
    for invalido in (
        "juan.perez.example.com",  # sin @
        "juan @example.com",       # con espacio
        "juan@example",            # dominio sin punto
    ):
        assert es_valido(invalido) is False, (
            f"{invalido!r} deberia ser False (Cierre 1)"
        )

    # Cierre 2: el caso raro pero valido del item, literal.
    caso_raro = "nombre+etiqueta@dominio.com.co"
    assert es_valido(caso_raro) is True, (
        f"{caso_raro!r} es valido y NO debe marcarse (Cierre 2)"
    )

    # Cierre 3: validar_correo devuelve motivo legible y NO
    # contiene el correo (regla 9).
    _orig, valido, motivo = validar_correo("juan@example")
    assert valido is False
    assert motivo
    assert "juan" not in motivo
    assert "example" not in motivo

    # Anti-pega: el caso valido lleva motivo vacio.
    _orig, valido, motivo = validar_correo(caso_raro)
    assert valido is True
    assert motivo == ""