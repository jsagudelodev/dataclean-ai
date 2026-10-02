"""DC.17 -- El movil marcado con el prefijo de salida internacional.

``0057 300 1234567`` es la forma en que exporta la agenda de
muchos moviles, y se marcaba **invalido** mientras que ``+57`` y
``57`` si se reconocian. Es un falso positivo contra el criterio
de vendible (seccion 4 del ENCARGO): uno de cada veinte formatos,
~50 contactos buenos descartados por cada 1.000.

Regla 7: sin red ni credenciales. Regla 6: cada test importa lo
suyo y falla sin el arreglo.
"""


# ---------------------------------------------------------------------------
# Cierre 1 -- las tres formas son el mismo numero
# ---------------------------------------------------------------------------


def test_el_prefijo_de_salida_produce_el_mismo_movil_que_mas_y_crudo():
    """Cierre 1: ``0057…``, ``+57…`` y ``57…`` son el mismo contacto."""
    from dataclean.telefono import normalizar_telefono

    formas = (
        "00573001234567",
        "0057 300 1234567",
        "0057-300-1234567",
        "+57 300 1234567",
        "57 3001234567",
        "3001234567",
    )
    normalizados = {normalizar_telefono(f)[0] for f in formas}
    assert normalizados == {"3001234567"}, normalizados


def test_el_prefijo_de_salida_se_clasifica_como_movil():
    """Cierre 1: y ademas queda clasificado, no solo normalizado."""
    from dataclean.telefono import clasificar_telefono

    for crudo in ("00573001234567", "0057 300 1234567", "0057-300-1234567"):
        canonico, tipo, motivo = clasificar_telefono(crudo)
        assert tipo == "MOVIL", f"{crudo!r} quedo como {tipo} ({motivo})"
        assert canonico == "3001234567"


def test_el_fijo_con_prefijo_de_salida_tambien_se_reconoce():
    """Cierre 1: el arreglo no es solo para moviles."""
    from dataclean.telefono import clasificar_telefono

    canonico, tipo, _ = clasificar_telefono("0057 601 234 5678")
    assert tipo == "FIJO"
    assert canonico == "6012345678"


# ---------------------------------------------------------------------------
# Cierre 2 -- no se gana inventando
# ---------------------------------------------------------------------------


def test_un_numero_de_otro_pais_se_sigue_marcando():
    """Cierre 2: ``0034…`` NO se fuerza al mercado colombiano.

    "Ante la duda, conservar" y marcar; nunca recortar digitos
    hasta que encajen.
    """
    from dataclean.telefono import clasificar_telefono

    for extranjero in ("00349112345678", "0034 911 234 567", "001 555 0100"):
        _, tipo, _ = clasificar_telefono(extranjero)
        assert tipo == "INVALIDO", f"{extranjero!r} colo como {tipo}"


def test_los_ceros_sueltos_no_se_vuelven_telefonos():
    """Cierre 2: el arreglo no abre la puerta a basura con ceros."""
    from dataclean.telefono import normalizar_telefono

    for basura in ("0057", "00", "000", "0057abc", "00 00 00"):
        normalizado, marcado = normalizar_telefono(basura)
        assert normalizado is None, f"{basura!r} -> {normalizado!r}"
        assert marcado is False


def test_el_pais_se_sigue_configurando():
    """Cierre 2: el arreglo respeta ``codigo_pais`` (DC.3 cierre 2)."""
    from dataclean.telefono import normalizar_telefono

    # Con el mercado espanol configurado, el que vale es el 0034.
    normalizado, marcado = normalizar_telefono(
        "0034 911234567", codigo_pais="+34", longitud_esperada=9
    )
    assert (normalizado, marcado) == ("911234567", True)

    # Y el colombiano pasa a ser el marcado.
    _, marcado_colombiano = normalizar_telefono(
        "00573001234567", codigo_pais="+34", longitud_esperada=9
    )
    assert marcado_colombiano is False


# ---------------------------------------------------------------------------
# Cierre 3 -- el pipeline completo deja de tirar esos contactos
# ---------------------------------------------------------------------------


def test_el_endpoint_no_descarta_los_moviles_con_prefijo_de_salida(tmp_path):
    """El falso positivo, visto por donde entra el cliente."""
    from dataclean.endpoint import ServicioLimpieza

    filas = ["NOMBRE COMPLETO,TELEFONO"]
    for i in range(20):
        filas.append(f"Contacto {i:02d},0057 300 123 {4000 + i:04d}")
    contenido = "\n".join(filas).encode("utf-8")

    servicio = ServicioLimpieza(carpeta_salida=tmp_path)
    reporte = servicio.procesar(contenido, "contactos.csv")["reporte"]

    assert reporte["telefonos_moviles"]["valor"] == 20
    assert reporte["telefonos_invalidos"]["valor"] == 0
