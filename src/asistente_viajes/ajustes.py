"""Ajustes que el cliente pide sobre un plan ya armado (Fase 7E, D-22).

Antes de esto, armar_plan era una funcion pura de los slots: mismos slots,
mismo plan byte por byte. Cualquier pedido que no fuera uno de los 9 campos
de PreferenciasViaje ("dejeme el ultimo dia libre", "sacame los teatros")
se descartaba en la extraccion, y el cliente recibia el MISMO plan de
nuevo, como si no hubiera dicho nada. Bug real reportado con capturas, ver
P-14 en DIFICULTADES.md.

Un ajuste es una restriccion sobre COMO se arma el plan, no un dato del
viaje. Vive igual en PreferenciasViaje porque asi hereda gratis las dos
mecanicas que ya existen: el merge no destructivo de fusionar_preferencias
(RF2) y la deteccion de cambios que re-arma el plan solo
(CAMPOS_QUE_AFECTAN_EL_PLAN, ver grafo.py).

`tipo="otro"` es deliberado: cuando el cliente pide algo que no sabemos
aplicar mecanicamente, se registra igual y se le avisa que no se aplico
(ver ajustes_no_aplicables). Callarse y devolver el mismo plan es
exactamente el bug que este modulo viene a arreglar.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from asistente_viajes.texto import normalizar

TipoAjuste = Literal["dia_libre", "excluir", "actividades_por_dia", "otro"]


class AjustePlan(BaseModel):
    """Una restriccion concreta sobre el armado del plan.

    `pedido_original` guarda lo que dijo el cliente con sus palabras: se usa
    para que la redaccion pueda acusar recibo citandolo ("le deje libre el
    ultimo dia, como pidio") y para poder explicar por que algo no se
    aplico, sin que el LLM tenga que reconstruirlo de memoria.
    """

    tipo: TipoAjuste
    # 1-based. Negativo cuenta desde el final (-1 = ultimo dia). None con
    # tipo="dia_libre" se interpreta como el ultimo dia, que es como se
    # pide casi siempre ("dejame el ultimo dia libre").
    dia: int | None = None
    # Para tipo="excluir": texto a excluir, puede ser el nombre de un lugar
    # o una categoria ("teatros", "museos").
    valor: str | None = None
    # Para tipo="actividades_por_dia".
    cantidad: int | None = None
    pedido_original: str = ""


def resolver_dia(dia: int | None, dias_totales: int) -> int | None:
    """Indice 1-based real de un dia, resolviendo los negativos contra el
    largo del plan. None se interpreta como el ultimo dia. Devuelve None si
    el dia pedido cae fuera del plan (por ejemplo, el dia 8 de un plan de 5),
    para que el llamador pueda avisar en vez de aplicar cualquier cosa."""
    if dias_totales < 1:
        return None
    if dia is None:
        return dias_totales
    resuelto = dias_totales + 1 + dia if dia < 0 else dia
    return resuelto if 1 <= resuelto <= dias_totales else None


def dias_libres(ajustes: list[AjustePlan], dias_totales: int) -> set[int]:
    """Numeros de dia (1-based) que el cliente pidio dejar sin actividades.
    Nunca deja el plan entero libre: si los ajustes piden liberar todos los
    dias, se ignora el pedido (un plan vacio no le sirve a nadie, y es mas
    honesto avisarlo que devolver una cascara)."""
    libres = set()
    for ajuste in ajustes:
        if ajuste.tipo != "dia_libre":
            continue
        resuelto = resolver_dia(ajuste.dia, dias_totales)
        if resuelto is not None:
            libres.add(resuelto)
    return set() if len(libres) >= dias_totales else libres


def dias_fuera_de_rango(ajustes: list[AjustePlan], dias_totales: int) -> list[AjustePlan]:
    """Ajustes de dia_libre que apuntan a un dia que el plan no tiene. Se
    reportan para poder avisarle al cliente, en vez de ignorarlos calladamente."""
    return [
        ajuste
        for ajuste in ajustes
        if ajuste.tipo == "dia_libre" and resolver_dia(ajuste.dia, dias_totales) is None
    ]


def _coincide(texto: str | None, patron: str) -> bool:
    return bool(texto) and normalizar(patron) in normalizar(texto)


def excluye(ajustes: list[AjustePlan], nombre: str | None, categoria: str | None) -> bool:
    """True si algun ajuste de exclusion matchea el nombre o la categoria de
    un candidato. Match por substring normalizado (sin tildes ni mayusculas):
    "teatro" tiene que sacar "Teatre Tivoli" y "theatres_and_entertainments"."""
    for ajuste in ajustes:
        if ajuste.tipo != "excluir" or not ajuste.valor:
            continue
        if _coincide(nombre, ajuste.valor) or _coincide(categoria, ajuste.valor):
            return True
    return False


def actividades_por_dia(ajustes: list[AjustePlan], por_defecto: int) -> int:
    """Cantidad de actividades por dia pedida por el cliente, acotada a un
    rango razonable. Gana el ultimo ajuste que la mencione."""
    elegida = por_defecto
    for ajuste in ajustes:
        if ajuste.tipo == "actividades_por_dia" and ajuste.cantidad:
            elegida = ajuste.cantidad
    return max(1, min(elegida, 6))


def ajustes_no_aplicables(ajustes: list[AjustePlan]) -> list[AjustePlan]:
    """Los que se registraron pero no sabemos aplicar mecanicamente. El
    orquestador se los pasa a la redaccion para que lo diga explicitamente."""
    return [ajuste for ajuste in ajustes if ajuste.tipo == "otro"]


def describir(ajuste: AjustePlan, dias_totales: int) -> str:
    """Frase corta y legible de lo que se aplico, para los supuestos del
    plan. No reemplaza a la redaccion del LLM, la alimenta."""
    if ajuste.tipo == "dia_libre":
        resuelto = resolver_dia(ajuste.dia, dias_totales)
        return f"dia {resuelto} sin actividades, a pedido suyo" if resuelto else ""
    if ajuste.tipo == "excluir":
        return f"se excluyo '{ajuste.valor}' a pedido suyo" if ajuste.valor else ""
    if ajuste.tipo == "actividades_por_dia":
        return f"{ajuste.cantidad} actividades por dia, a pedido suyo" if ajuste.cantidad else ""
    return ""


class ResultadoAjustes(BaseModel):
    """Que se aplico y que no, para que la redaccion pueda ser honesta sin
    adivinar."""

    aplicados: list[str] = Field(default_factory=list)
    no_aplicados: list[str] = Field(default_factory=list)
