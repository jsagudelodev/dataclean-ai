"""DC.14 -- El pipeline completo, de verdad.

Las piezas DC.7 (separar nombre y cargo) y DC.9 (duplicados por
nombre) estaban construidas y probadas, pero el endpoint no las
llamaba; y de varias columnas de telefono solo se procesaba la
primera. Estos tests prueban el **comportamiento visible desde el
endpoint**, no que las funciones existan: cada uno sube un archivo
y mira lo que el cliente recibe.

Regla 6: cada test importa lo suyo localmente y falla sin el
codigo de DC.14.
Regla 7: sin red, sin credenciales. El separador es la
implementacion falsa de DC.7.
"""


def _csv_bytes(filas: list[str]) -> bytes:
    """Arma un CSV en utf-8 a partir de lineas ya formateadas."""
    return "\n".join(filas).encode("utf-8")


# ---------------------------------------------------------------------------
# Cierre 1 -- nombre y cargo separados desde el endpoint
# ---------------------------------------------------------------------------


def test_subida_separa_nombre_y_cargo_en_campos_distintos(tmp_path):
    """Cierre 1: un nombre con el cargo pegado llega separado al limpio."""
    import pandas as pd
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO",
            "MARIA GOMEZ - GERENTE,3001234567",
            "Pedro Ruiz (Contador),3017654321",
        ]
    )
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    resultado = servicio.procesar(contenido, "contactos.csv")

    limpio = pd.read_csv(resultado["ruta"], sep=";", encoding="utf-8-sig")
    columna_nombre = "NOMBRE COMPLETO"
    assert f"{columna_nombre}_sin_cargo" in limpio.columns
    assert f"{columna_nombre}_cargo" in limpio.columns

    sin_cargo = list(limpio[f"{columna_nombre}_sin_cargo"])
    cargos = [str(c).upper() for c in limpio[f"{columna_nombre}_cargo"]]
    assert "GERENTE" not in sin_cargo[0].upper()
    assert cargos[0] == "GERENTE"
    assert "CONTADOR" not in sin_cargo[1].upper()
    assert cargos[1] == "CONTADOR"

    # La columna original se conserva intacta (DC.11 cierre 2).
    assert list(limpio[columna_nombre]) == [
        "MARIA GOMEZ - GERENTE",
        "Pedro Ruiz (Contador)",
    ]


def test_sin_separador_el_servicio_responde_y_conserva_el_campo(tmp_path):
    """Cierre 1 (parte 2): sin LLM el sistema sigue funcionando (DC.7 c3)."""
    import pandas as pd
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        ["NOMBRE COMPLETO,TELEFONO", "MARIA GOMEZ - GERENTE,3001234567"]
    )
    # separador=None == el LLM real no esta disponible.
    servicio = ServicioLimpieza(carpeta_salida=tmp_path, separador=None)

    resultado = servicio.procesar(contenido, "contactos.csv")

    assert resultado["reporte"]["total_registros"] == 1
    limpio = pd.read_csv(resultado["ruta"], sep=";", encoding="utf-8-sig")
    # El campo queda entero, no se rompe nada.
    assert list(limpio["NOMBRE COMPLETO_sin_cargo"]) == [
        "MARIA GOMEZ - GERENTE"
    ]
    assert limpio["NOMBRE COMPLETO_cargo"].isna().all()


# ---------------------------------------------------------------------------
# Cierre 2 -- duplicados por nombre en el reporte
# ---------------------------------------------------------------------------


def test_reporte_incluye_grupos_de_duplicados_por_nombre(tmp_path):
    """Cierre 2: el reporte del endpoint trae los grupos por nombre."""
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO",
            "Juan Pérez,3001112222",
            "JUAN PEREZ,3003334444",
            "Juana Pérez,3005556666",
        ]
    )
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    reporte = servicio.procesar(contenido, "contactos.csv")["reporte"]

    assert "grupos_duplicados_nombre" in reporte
    grupos = reporte["grupos_duplicados_nombre"]["grupos"]
    # Juan Perez / JUAN PEREZ agrupan; Juana Perez no entra.
    assert len(grupos) == 1
    assert sorted(grupos[0]["filas"]) == [0, 1]


def test_grupos_por_nombre_se_marcan_sospechosos_y_no_se_confunden(tmp_path):
    """Cierre 2: sospechoso, y distinguible de los grupos por telefono."""
    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO",
            "Juan Pérez,3001112222",
            "JUAN PEREZ,300 111 2222",
        ]
    )
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    reporte = servicio.procesar(contenido, "contactos.csv")["reporte"]

    por_nombre = reporte["grupos_duplicados_nombre"]["grupos"]
    por_telefono = reporte["grupos_duplicados"]["grupos"]
    # Las mismas dos filas caen en ambos, pero son listas separadas.
    assert len(por_nombre) == 1 and len(por_telefono) == 1
    assert por_nombre is not por_telefono
    # Ante la duda, conservar: el grupo por nombre es sospechoso (DC.9 c3).
    assert por_nombre[0]["sospechoso"] is True
    # Y el de telefono no expone la misma forma: no tiene 'sospechoso'.
    assert "sospechoso" not in por_telefono[0]


def test_el_reporte_por_nombre_no_filtra_datos_personales(tmp_path):
    """Regla 9: ni el nombre ni el canonico salen en el reporte."""
    import json

    from dataclean.cargo import SeparadorFalso
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO",
            "Juan Pérez,3001112222",
            "JUAN PEREZ,3003334444",
        ]
    )
    servicio = ServicioLimpieza(
        carpeta_salida=tmp_path, separador=SeparadorFalso()
    )

    reporte = servicio.procesar(contenido, "contactos.csv")["reporte"]

    serializado = json.dumps(
        reporte["grupos_duplicados_nombre"], ensure_ascii=False
    ).lower()
    assert "juan" not in serializado
    assert "pérez" not in serializado
    assert "perez" not in serializado


# ---------------------------------------------------------------------------
# Cierre 3 -- las tres columnas de telefono
# ---------------------------------------------------------------------------


def test_se_procesan_todas_las_columnas_de_telefono(tmp_path):
    """Cierre 3: tres columnas de telefono, las tres normalizadas."""
    import pandas as pd
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO,Cel,móvil 2",
            "Juan Pérez,(300)123-4567,300 765 4321,+57 3009998888",
        ]
    )
    servicio = ServicioLimpieza(carpeta_salida=tmp_path)

    resultado = servicio.procesar(contenido, "contactos.csv")

    limpio = pd.read_csv(resultado["ruta"], sep=";", encoding="utf-8-sig")
    for columna in ("TELEFONO", "Cel", "móvil 2"):
        assert f"{columna}_normalizado" in limpio.columns, columna
        assert f"{columna}_tipo" in limpio.columns, columna
        assert str(limpio[f"{columna}_tipo"][0]) == "MOVIL", columna


def test_las_cifras_del_reporte_cuentan_las_tres_columnas(tmp_path):
    """Cierre 3: una fila con tres moviles cuenta tres moviles, no uno."""
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO,Cel,móvil 2",
            "Juan Pérez,(300)123-4567,300 765 4321,+57 3009998888",
        ]
    )
    servicio = ServicioLimpieza(carpeta_salida=tmp_path)

    reporte = servicio.procesar(contenido, "contactos.csv")["reporte"]

    assert reporte["total_registros"] == 1
    assert reporte["telefonos_moviles"]["valor"] == 3
    assert reporte["telefonos_normalizados"]["valor"] == 3
    # Rastreo (DC.10 cierre 2): la unica fila que las compone es la 0.
    assert list(reporte["telefonos_moviles"]["filas"]) == [0]


def test_una_sola_columna_de_telefono_sigue_contando_igual(tmp_path):
    """Regla 12: el caso de una columna no cambia de comportamiento."""
    from dataclean.endpoint import ServicioLimpieza

    contenido = _csv_bytes(
        [
            "NOMBRE COMPLETO,TELEFONO",
            "Juan Pérez,3001234567",
            "Ana Lopez,6012345678",
        ]
    )
    servicio = ServicioLimpieza(carpeta_salida=tmp_path)

    reporte = servicio.procesar(contenido, "contactos.csv")["reporte"]

    assert reporte["telefonos_moviles"]["valor"] == 1
    assert reporte["telefonos_fijos"]["valor"] == 1
