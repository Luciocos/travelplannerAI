"""Modelo de embeddings locales, sentence-transformers, deliberadamente no
Gemini: embeber los corpus son cientos de llamadas y la cuota gratuita del
LLM se reserva para el chat (ver llm-y-claves.md).

Modelo: paraphrase-multilingual-MiniLM-L12-v2, 384 dimensiones, multilingue
(los extractos de Wikipedia pueden venir en ingles, las consultas en
espanol). Vectores normalizados, se usa distancia coseno (<=> en pgvector).

Cambiar el modelo cambia la dimension del vector y obliga a recrear la
tabla y reindexar todo. No es un cambio menor, ver arquitectura.md.
"""

from __future__ import annotations

NOMBRE_MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSION_EMBEDDING = 384

_modelo_cacheado = None


def _cargar_modelo():
    global _modelo_cacheado
    if _modelo_cacheado is None:
        # Import diferido: sentence-transformers/torch son pesados y no hacen
        # falta para el resto del paquete ni para los tests que no embeben.
        from sentence_transformers import SentenceTransformer

        _modelo_cacheado = SentenceTransformer(NOMBRE_MODELO)
    return _modelo_cacheado


def embeber_textos(textos: list[str]) -> list[list[float]]:
    """Embebe una lista de textos, vectores normalizados (norma L2 = 1)."""
    modelo = _cargar_modelo()
    vectores = modelo.encode(textos, normalize_embeddings=True, convert_to_numpy=True)
    return vectores.tolist()


def embeber_texto(texto: str) -> list[float]:
    return embeber_textos([texto])[0]
