---
name: tp2-asistente-viajes
description: Contexto completo, restricciones y plan del TP2 de Inteligencia Artificial (UTN FRRo), un sistema experto conversacional de planificación de viajes construido con LangChain, RAG sobre PostgreSQL con pgvector, embeddings y un LLM gratuito. Consultá esta skill de forma obligatoria y antes de escribir cualquier línea de código o de tomar cualquier decisión técnica cuando se trabaje sobre este proyecto, o cuando aparezca cualquier mención a asistente de viajes, itinerarios, slot filling, completar_slots, recomendar_actividades, recomendar_locales, armar_plan, OpenTripMap, Amadeus, Open-Meteo, destinos piloto, RAG de atractivos o de comercios, TP2, la consigna de la cátedra, la defensa oral o el video explicativo. También es la fuente de verdad del estado del proyecto, así que consultala aunque el pedido parezca menor (agregar una tool, cambiar el vector store, tocar el notebook, redactar documentación).
---

# TP2 IA, Asistente de viajes

Fuente de verdad del proyecto. Todo el contexto estable vive acá, el contexto que cambia vive en `references/estado.md` y en `docs/` del repo.

## Protocolo de uso, leer primero

1. **Al empezar cualquier sesión de trabajo sobre este proyecto**, leer `references/estado.md`. Dice en qué fase está el proyecto, qué está cerrado, qué está abierto y qué decisiones ya se tomaron. Sin eso vas a reproponer cosas ya resueltas.
2. **Antes de codear una fase**, leer `references/plan-de-fases.md` (la fase que toca) y `references/arquitectura.md`.
3. **Antes de integrar cualquier API externa**, leer `references/fuentes-datos.md`. Tiene los dos pasos de OpenTripMap, los límites de Open-Meteo y las trampas de RapidAPI/Booking.com15 (reemplaza a Amadeus, dado de baja en 2026, ver D-05/D-06 en DECISIONES.md).
4. **Antes de discutir entregables, evaluación o fechas**, leer `references/consigna-catedra.md`. Es el texto de lo que pide el profesor, y lo que se evalúa.
5. **Al cerrar cada fase**, actualizar `references/estado.md` (fase, decisiones nuevas en una línea, bloqueos) y `docs/DECISIONES.md` del repo (decisión, alternativa descartada, motivo). Ese log es el insumo directo de la defensa oral y del video, no es burocracia.

Si algo de esta skill contradice lo que el usuario pide en el momento, gana el usuario, pero avisá la contradicción antes de ejecutar.

## Qué es el proyecto

Sistema experto conversacional de planificación de viajes. El usuario dice en lenguaje natural qué viaje busca (tipo de destino, intereses, presupuesto, fechas, cantidad de personas), el agente completa por preguntas lo que falta, arma un itinerario día a día con costo estimado, y responde consultas puntuales de recomendación dentro del destino (dónde comer bien y barato, dónde comprar algo típico).

El alcance está acotado a 2 o 3 **destinos piloto**, no a cualquier destino del mundo. Intentar cobertura global es el error que hunde el proyecto.

El entregable oficial es un **notebook interactivo reproducible** más una defensa oral. Consecuencia de diseño, no negociable: la lógica vive en el paquete Python bajo `src/asistente_viajes/`, el notebook importa ese paquete, lo ejecuta y lo documenta. Nada de lógica de negocio escrita dentro de celdas.

## Restricciones duras

1. **LangChain es obligatorio** como framework base, es requisito textual de la cátedra. No reemplazarlo. Para flujos con más de un nodo de decisión, usar **LangGraph** (mismo ecosistema). **No usar CrewAI** salvo confirmación explícita del profesor, traída por el usuario.
2. **Vector store: PostgreSQL con pgvector**, no Chroma. Pedido explícito del profesor. La justificación técnica está en `references/arquitectura.md` y hay que saber defenderla.
3. **Ninguna API que requiera aprobación de partner.** Booking.com Demand API está descartada por eso. Todo lo externo tiene que ser self service, gratuito y sin tarjeta.
4. **Cero secretos en el repo.** Credenciales por `.env`, con `.env.example` versionado y `.env` en `.gitignore`.
5. **Nada de datos inventados.** Si un punto de interés no tiene descripción en la fuente, se descarta o se completa a mano y se marca con `fuente='curado'`. Ningún registro fabricado por el LLM entra a los corpus. Las justificaciones que el LLM genera salen sólo del contexto recuperado.
6. **Núcleo antes que extensiones.** Fases 0 a 6 (RF1, RF2, RF3, RF5, RF11, RF12) se terminan y se verifican antes de tocar una extensión. Si falta tiempo, se cortan extensiones, nunca núcleo. **RF4 (recomendación de comercios) se movió a extensión, ver D-07 en `docs/DECISIONES.md`**: OpenTripMap no da volumen confiable de datos comerciales sin curaduría manual de horas: se priorizó un RAG de atractivos robusto y testeado sobre dos RAGs parciales.
7. **Español.** Código, nombres de funciones y variables en español (los nombres de las tools están fijados por la propuesta y no se cambian). Documentación en español. Respuestas del sistema al usuario final en español rioplatense neutro.
8. **Ningún commit lleva coautoría.** Prohibido el trailer `Co-Authored-By`, la línea `Generated with Claude Code` y cualquier mención a la herramienta generadora, en el asunto o en el cuerpo. El autor es el usuario. Detalle y mecanismos de control en `references/ci-y-git.md`.
9. **Commitear cada unidad de trabajo terminada**, con formato `tipo(alcance): descripción`. No acumular una fase entera en un commit.
10. **Modelo chico y rotación de claves.** Gemini con un modelo Flash Lite, tres claves rotando por round robin con failover ante 429. Ningún proceso automático (tests, CI) consume cuota. Detalle en `references/llm-y-claves.md`.

## Mapa de requerimientos

Núcleo:

| RF | Qué pide | Tool | Archivo |
|----|----------|------|---------|
| RF1 | Interpretar preferencias en lenguaje natural | `completar_slots` | `tools/completar_slots.py` |
| RF2 | Preguntar incrementalmente sólo lo que falta | `completar_slots` | `tools/completar_slots.py` |
| RF3 | Recomendar actividades por intereses | `recomendar_actividades` | `tools/recomendar_actividades.py` |
| RF5 | Itinerario con costo estimado | `armar_plan` | `tools/armar_plan.py` |

Extensiones:

| RF | Qué pide | Tool | Fuente |
|----|----------|------|--------|
| RF4 | Recomendación local puntual (comer, comprar) | `recomendar_locales` | RAG de comercios (corpus parcial, ver D-07). Ya implementado y testeado, sin datos reales suficientes todavía. |
| RF6 | Alojamiento por destino y fechas | `buscar_alojamiento` | RapidAPI, Booking.com15 (reemplaza a Amadeus, D-06) |
| RF7 | Vuelos por destino y fechas | `buscar_vuelos` | RapidAPI, Booking.com15 (reemplaza a Amadeus, D-06) |
| RF8 | Clima, idioma y moneda al confirmar destino | `info_destino` | Open-Meteo mas tabla de referencia |
| RF9 | Seguridad y costumbres locales | `responder_faq_viajero` | RAG de FAQ (corpus curado) |
| RF10 | Gastos del viaje y división | `registrar_gasto`, `calcular_division_gastos` | **Omitido, ver D-11 en `docs/DECISIONES.md`.** No se implementa. |

Transversales:

- **RF11**: mantener el estado de la conversación durante la sesión (`estado.py` mas memoria del agente).
- **RF12**: el orquestador decide solo qué tool usar, sin que el usuario indique un modo. Única excepción, el módulo de información del destino se dispara automáticamente al confirmarse el destino.

## Los RAGs

Núcleo:

1. **Atractivos turísticos**, por destino: museos, sitios históricos, caminatas, parques, con descripción y tags de interés (histórico, naturaleza, gastronómico, familiar). Alimenta `recomendar_actividades` y `armar_plan`. Es el RAG que se prioriza con volumen y calidad real de datos (ver D-07).

Extensión:

2. **Comercios y gastronomía local**, por destino: locales, ferias, restaurantes, con descripción, categoría y rango de precio. Alimenta `recomendar_locales` (RF4, movido a extensión por D-07: OpenTripMap no da volumen confiable de datos comerciales sin curaduría manual de horas). Ya implementado y testeado con mocks; falta corpus real.
3. **FAQ del viajero**, texto curado por destino sobre seguridad, estafas comunes y costumbres. Es el menos diferencial de los tres, se puede dejar afuera sin que se note en la defensa.

Patrón común a los tres, y esto es lo que hay que poder explicar: **primero se filtra por destino (metadata), recién ahí se busca semánticamente por interés**. Con pgvector las dos cosas pasan en una sola consulta SQL, que es exactamente el argumento a favor de pgvector sobre Chroma.

## Convenciones de trabajo

- Commits en español, formato `tipo(alcance): descripción`, por ejemplo `feat(ingesta): cliente de OpenTripMap en dos pasos`. Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `data`, `ci`, `chore`. **Sin trailers de coautoría, ver `references/ci-y-git.md`.**
- Una rama por fase (`fase/N-nombre`), merge a `main` al cerrar la fase. No commitear directo a `main`.
- Tests con `pytest`. Toda llamada a API externa se mockea, ningún test toca la red. Un CI que consume cuota de Gemini es un CI que deja al equipo sin cuota el día de la entrega.
- Anotaciones de tipo en todas las funciones públicas.
- `logging`, no `print`, en `src/`.
- Los prompts del LLM viven en constantes con nombre, en un módulo dedicado, no inline en el medio de la lógica. Se van a citar en la defensa y hay que poder encontrarlos.
- El docstring de cada `@tool` es lo que lee el agente para decidir cuándo llamarla. Tratalo como código, no como comentario.

## Reglas de interacción con el usuario

1. Antes de escribir código de una fase nueva, mostrar el plan de archivos y funciones, y esperar confirmación.
2. Si una API externa se comporta distinto a lo documentado acá, parar y avisar. No improvisar una alternativa.
3. Si algo de esta skill es ambiguo o está mal, decirlo antes de codear.
4. No agregar dependencias fuera de la lista de `references/arquitectura.md` sin justificarlo.
5. Registro técnico: conciso y directo, sin relleno.

## Índice de referencias

- `references/estado.md`, **archivo vivo**: fase actual, decisiones tomadas, bloqueos abiertos, próximo paso. Leer al empezar, actualizar al cerrar cada fase.
- `references/consigna-catedra.md`: texto de lo que pide el profesor, criterios de evaluación, entregables, fechas, requisitos del video.
- `references/arquitectura.md`: estructura del repo, esquema SQL, patrón de consulta, contratos de las tools, modelo de estado, dependencias.
- `references/fuentes-datos.md`: OpenTripMap en dos pasos, Open-Meteo, RapidAPI/Booking.com15 (reemplaza a Amadeus), por qué Booking directo queda afuera, embeddings.
- `references/llm-y-claves.md`: elección del modelo, rotador de 3 claves de Gemini, manejo de 429, higiene de secretos, ahorro de cuota.
- `references/ci-y-git.md`: convención de commits, prohibición de coautoría, hook local, ramas, los cuatro workflows de CI.
- `references/plan-de-fases.md`: las 10 fases con criterios de aceptación y calendario.
- `assets/DECISIONES.plantilla.md` y `assets/DIFICULTADES.plantilla.md`: plantillas para los documentos del repo.
- `assets/workflows/`: `ci.yml`, `commits.yml`, `secretos.yml`, `smoke-llm.yml`, listos para copiar a `.github/workflows/`.
