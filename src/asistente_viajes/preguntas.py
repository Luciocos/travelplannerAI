"""Preguntas dirigidas y sugerencias, 100% deterministico (sin LLM).

D-14: en vez de pedirle al LLM que redacte la pregunta por los datos
faltantes (como hacia PROMPT_PREGUNTAR_SLOTS_FALTANTES), se arma en
Python a partir de una tabla fija de opciones por campo. Dos ventajas: no
hay riesgo de que el LLM invente una opcion que no esta en la tabla (por
ejemplo, preguntar por "montaña" cuando ningun destino piloto es de
montaña, o presuponer "la primera o segunda quincena de este mes" sin que
el usuario haya dicho nada de fechas), y es una llamada al LLM menos por
turno.

Cada campo faltante se pregunta con sus opciones concretas y, cuando
aplica, una sugerencia (marcada con una estrella) que el usuario puede
aceptar de una sola vez respondiendo "usar sugerencias" en vez de
contestar campo por campo.
"""

from __future__ import annotations

from asistente_viajes.destinos import buscar_destino_piloto, cargar_destinos_piloto

INTERESES_SUGERIDOS = [
    "historia",
    "naturaleza",
    "gastronomia",
    "compras",
    "descanso",
    "vida nocturna",
]
PRESUPUESTOS_VALIDOS = ["bajo", "medio", "alto"]

PRESUPUESTO_SUGERIDO = "medio"
CANTIDAD_PERSONAS_SUGERIDA = 2
DURACION_DIAS_SUGERIDA = 5


def _opciones_destino() -> list[str]:
    return sorted(cargar_destinos_piloto().keys())


# label, opciones (vacio si es texto libre), sugerencia legible
_CAMPO_A_PREGUNTA: dict[str, tuple[str, list[str], str | None]] = {
    "destino": ("a qué destino", [], None),
    "intereses": ("qué le interesa hacer", INTERESES_SUGERIDOS, None),
    "presupuesto": ("qué presupuesto tiene en mente", PRESUPUESTOS_VALIDOS, PRESUPUESTO_SUGERIDO),
    "cuando": (
        "para cuándo (fechas exactas o la cantidad de días)",
        [],
        f"{DURACION_DIAS_SUGERIDA} días, fecha a confirmar",
    ),
    "cantidad_personas": ("cuántas personas viajan", [], str(CANTIDAD_PERSONAS_SUGERIDA)),
}


def _normalizar_faltantes(faltantes: list[str]) -> list[str]:
    """fecha_inicio y fecha_fin se preguntan como un solo campo 'cuando'
    (ver PreferenciasViaje.tiene_cuando); tipo_destino no se pregunta
    nunca aca porque se deriva del destino (D-14, ver destinos.json)."""
    vistos: list[str] = []
    for campo in faltantes:
        if campo == "tipo_destino":
            continue
        clave = "cuando" if campo in ("fecha_inicio", "fecha_fin") else campo
        if clave not in vistos:
            vistos.append(clave)
    return vistos


def armar_pregunta_consolidada(faltantes: list[str]) -> str:
    """Una sola pregunta con todos los datos que faltan, opciones
    concretas por campo y una sugerencia cuando aplica."""
    claves = _normalizar_faltantes(faltantes)
    if not claves:
        return ""

    if "destino" in claves:
        destinos = _opciones_destino()
        partes_destino = f"¿A qué destino le gustaría viajar ({', '.join(destinos)})?"
    else:
        partes_destino = None

    partes = []
    for clave in claves:
        if clave == "destino":
            continue
        label, opciones, sugerido = _CAMPO_A_PREGUNTA[clave]
        if opciones:
            texto = f"¿{label.capitalize()} ({', '.join(opciones)})"
        else:
            texto = f"¿{label.capitalize()}"
        if sugerido:
            texto += f", le sugiero {sugerido}"
        texto += "?"
        partes.append(texto)

    pregunta = " ".join(([partes_destino] if partes_destino else []) + partes)
    if valores_sugeridos(faltantes):
        pregunta += (
            ' Si prefiere, dígame "usar sugerencias" y armo un primer borrador con esos valores.'
        )
    return pregunta


def valores_sugeridos(faltantes: list[str]) -> dict[str, object]:
    """Valores por defecto para 'usar sugerencias', solo para los campos
    que de verdad faltan y tienen una sugerencia definida. destino nunca
    se sugiere solo: sin destino no hay corpus real del que armar nada."""
    claves = _normalizar_faltantes(faltantes)
    sugeridos: dict[str, object] = {}
    if "intereses" in claves:
        sugeridos["intereses"] = [INTERESES_SUGERIDOS[0]]
    if "presupuesto" in claves:
        sugeridos["presupuesto"] = PRESUPUESTO_SUGERIDO
    if "cuando" in claves:
        sugeridos["duracion_dias"] = DURACION_DIAS_SUGERIDA
    if "cantidad_personas" in claves:
        sugeridos["cantidad_personas"] = CANTIDAD_PERSONAS_SUGERIDA
    return sugeridos


def destinos_piloto_destacados() -> str:
    """Texto deterministico con los 3 destinos piloto y su descripcion,
    para cuando el usuario todavia no eligio destino (o pidio uno que no
    es piloto): una respuesta util en el mismo turno, no solo la
    pregunta."""
    destinos = cargar_destinos_piloto()
    lineas = [
        f"- **{nombre}**: {datos['descripcion']}" for nombre, datos in sorted(destinos.items())
    ]
    return "Por ahora trabajo con estos destinos:\n" + "\n".join(lineas)


def tipo_destino_de(destino: str | None) -> str | None:
    """tipo_destino derivado del destino piloto (D-14): si el destino ya
    esta confirmado, no hace falta volver a preguntarlo. Devuelve el
    primer tipo de la lista (el mas representativo) o None si el destino
    no es piloto."""
    if not destino:
        return None
    encontrado = buscar_destino_piloto(destino)
    if encontrado is None:
        return None
    tipos = encontrado[1].get("tipos") or []
    return tipos[0] if tipos else None
