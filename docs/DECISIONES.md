# Decisiones técnicas

Una entrada por decisión. Este documento es el insumo directo de la defensa oral y del punto 4 del video ("justificación de las decisiones tomadas"). Se escribe en el momento de decidir, no al final reconstruyendo de memoria.

Formato de cada entrada:

## D-NN, título de la decisión

- **Fecha:** 
- **Fase:** 
- **Contexto:** qué problema había que resolver.
- **Decisión:** qué se eligió.
- **Alternativas descartadas:** qué más se evaluó y por qué no.
- **Consecuencias:** qué se gana, qué se pierde, qué queda condicionado a esto.

---

## D-01, PostgreSQL con pgvector como vector store

- **Fecha:** 2026-09-10
- **Fase:** 0
- **Contexto:** el sistema necesita un vector store para tres corpus de RAG, con filtrado previo por destino.
- **Decisión:** PostgreSQL con la extensión pgvector.
- **Alternativas descartadas:** Chroma. Descartada por pedido explícito del profesor, y porque obliga a resolver el filtro por metadata y la búsqueda semántica en dos pasos separados.
- **Consecuencias:** el filtro por destino y la búsqueda por similitud se resuelven en una sola consulta SQL. Las tablas estructuradas (itinerarios, gastos) viven en la misma base que los vectores, un solo motor en vez de dos. Costo, hay que administrar una base de datos.

## D-02, Postgres gestionado en Supabase en vez de solo Docker local

- **Fecha:** 2026-09-10
- **Fase:** 0
- **Contexto:** se necesita una base Postgres con pgvector accesible por todo el equipo, no solo en la maquina de quien programa.
- **Decisión:** Supabase (Postgres 16 con pgvector) como base compartida, vía `DATABASE_URL`. `docker-compose.yml` queda como alternativa para desarrollo 100% local o para el CI.
- **Alternativas descartadas:** solo Docker local, descartado porque cada integrante tendría datos distintos y el trabajo en equipo se complica. Neon, no elegido por preferencia del equipo por Supabase.
- **Consecuencias:** todos apuntan a la misma base durante el desarrollo. Hay que evitar correr la ingesta completa en paralelo sin coordinarse, para no pisarse datos. La connection string va solo en `.env`, nunca en el repo.

## D-03, Modelo Gemini Flash-Lite, ID exacto pendiente de verificación final

- **Fecha:** 2026-09-10
- **Fase:** 0
- **Contexto:** el plan pide verificar contra la documentación oficial de Google cuál es el Flash-Lite vigente y su límite diario antes de cerrar la Fase 0.
- **Decisión:** se deja `gemini-2.5-flash-lite` como valor por defecto en `.env.example` y en los workflows, configurable por variable de entorno (`GEMINI_MODEL`), sin hardcodear el ID en el código.
- **Alternativas descartadas:** hardcodear un ID sin verificar. Una búsqueda rápida mostró fuentes de terceros con datos inconsistentes entre sí (algunas ya mencionan generaciones "Gemini 3.x Flash-Lite" con límites distintos, 1000 RPD vs otras cifras) y ninguna confirmación limpia contra `ai.google.dev`. No se quiso asumir el dato.
- **Consecuencias:** **queda como bloqueo abierto, ver `estado.md` de la skill.** Antes de usar cuota real (correr `smoke_llm.py` o cargar los tres `GEMINI_API_KEY_n`), alguien del equipo tiene que entrar a `https://ai.google.dev/gemini-api/docs/models` y `https://ai.google.dev/gemini-api/docs/rate-limits`, confirmar el ID vigente y el límite diario real, y actualizar `GEMINI_MODEL` en `.env.example`, los cuatro workflows y `estado.md`.

## D-04, Destinos piloto "Europa" y "Caribe" resueltos a ciudades puntuales

- **Fecha:** 2026-09-10
- **Fase:** 1
- **Contexto:** el handoff fija como destinos piloto "Europa, Miami, Caribe". OpenTripMap busca por radio alrededor de una coordenada puntual (`lat`/`lon` + radio en metros), no acepta un continente ni una región como unidad de búsqueda. Miami es una ciudad y funciona sin cambios; "Europa" y "Caribe" no.
- **Decisión:** "Europa" se resuelve a **Barcelona**. "Caribe" se resuelve a **Cancún / Riviera Maya**, México. Ambas confirmadas por el usuario tras propuesta de opciones.
- **Alternativas descartadas para Europa:** París (riesgo de sobrecarga de resultados en OpenTripMap, exige filtrado más agresivo), Roma (buena en histórico/patrimonio pero más floja en gastronomía/comercios curados que Barcelona).
- **Alternativas descartadas para Caribe:** Punta Cana, República Dominicana (destino caribeño "correcto" geográficamente, pero se prefirió Cancún/Riviera Maya); San Juan, Puerto Rico (buena mezcla histórico/playas pero menor volumen de POIs que las otras dos opciones).
- **Consecuencias:** Cancún/Riviera Maya está en el Golfo de México, no en el mar Caribe en sentido estricto; queda anotado para poder explicarlo en la defensa si se pregunta por qué "Caribe" resuelve a ese punto. Con las coordenadas ya decididas, se puede correr `python -m scripts.ingestar_destino --destino <nombre> --lat <lat> --lon <lon>` para Barcelona y Cancún en cuanto esté cargada `OPENTRIPMAP_API_KEY`.
