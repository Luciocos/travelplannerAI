# Plan de fases

Cada fase termina con: código funcionando, test o celda de verificación que lo demuestre, commit, entrada en `docs/DECISIONES.md`, y actualización de `references/estado.md` de esta skill.

**No avanzar a la fase siguiente sin confirmación del usuario.**

Calendario de referencia, contra la entrega del 30 de septiembre de 2026. Los días son relativos al arranque del proyecto.

---

## Fase 0, scaffolding y CI (día 1)

- Inicializar repo local, `git remote add origin <REPO_URL>`, trabajo en ramas `fase/N-nombre`.
- Copiar esta skill a `.claude/skills/` y versionarla con el repo.
- `.githooks/commit-msg` mas `git config core.hooksPath .githooks` (ver `ci-y-git.md`).
- Copiar los cuatro workflows de `assets/workflows/` a `.github/workflows/`.
- Cargar `GEMINI_API_KEY_1`, `_2` y `_3` como repository secrets en GitHub, y configurar la protección de `main`.
- `requirements.txt` con las dependencias de `arquitectura.md`.
- `.env.example` con todas las variables (nombres, nunca valores), `.env` y `.cache/` en `.gitignore`.
- `docker-compose.yml` con `pgvector/pgvector:pg16`, puerto y volumen.
- `config.py` que falle rápido y con mensaje claro si falta una variable requerida, y que arme la lista de claves de Gemini.
- `llm.py` con la factory y el rotador de claves, mas `scripts/smoke_llm.py`.
- Verificar contra la documentación oficial de Google cuál es el Flash Lite vigente y su límite diario, y anotarlo en `estado.md`.
- Copiar las plantillas de `assets/` a `docs/DECISIONES.md` y `docs/DIFICULTADES.md`.

**Aceptación:** `docker compose up -d` levanta Postgres, `python -c "from asistente_viajes import config"` no rompe, el hook rechaza un commit con trailer de coautoría, el CI corre en verde sobre la rama, y `smoke-llm` disparado a mano responde por las tres claves.

## Fase 1, ingesta de datos (días 2 a 4)

Implementar el flujo de dos pasos de OpenTripMap descripto en `fuentes-datos.md`, la separación en dos corpus por `kind`, el filtro por longitud mínima de descripción, la curaduría manual en `data/curated/` y el fallback cuando la API no responde.

**Aceptación (núcleo):** al menos **20** documentos de atractivos por destino piloto (bajado de 25 a 20, D-07: Cancún tiene poca densidad de contenido editorial incluso ampliando radio y relajando el filtro de significancia), todos con texto real, ninguno inventado. **El mínimo de 15 comercios por destino queda para cuando se retome RF4 como extensión (D-07)**: OpenTripMap no da volumen confiable de datos comerciales sin curaduría manual de horas (confirmado con los tres destinos piloto, ver `estado.md` y P-02 en `DIFICULTADES.md`), así que se prioriza un solo RAG (atractivos) robusto y testeado sobre dos RAGs parciales.

## Fase 2, vector store en pgvector (días 4 a 5)

Esquema, índices, embebido, carga. Resolver la decisión abierta entre `langchain_postgres.PGVector` y tabla propia, y documentarla.

**Aceptación:** una consulta tipo "museos de historia precolombina" contra destino Salta devuelve el Museo de Arqueología de Alta Montaña en el top 3.

## Fase 3, retrievers y tools de RAG (días 5 a 7)

`recomendar_actividades` como `@tool`, con `args_schema` y docstring precisa. Justificaciones generadas sólo sobre el contexto recuperado. `recomendar_locales` ya está escrito y testeado con mocks (RF4 movido a extensión, D-07), no bloquea esta fase.

**Aceptación (núcleo):** RF3 verificable por test, llamando la tool directo, todavía sin agente.

## Fase 4, estado y slot filling (días 7 a 9)

`PreferenciasViaje`, extracción estructurada, merge no destructivo, generación de la pregunta por lo que falta, máximo 2 slots por turno.

**Aceptación:** el ejemplo de la consigna funciona. Entrada "quiero un viaje para caminar y ver cosas históricas, presupuesto medio" produce intereses (variantes de `[caminar/caminatas, historia]`, la extracción exacta del LLM puede variar en la forma de la palabra) y presupuesto `medio`. **Corregido 2026-09-10 tras verificar con el LLM real**: como esa entrada no menciona destino, la pregunta del primer turno es por destino y tipo de destino (los dos primeros slots faltantes según el orden de `SLOTS_OBLIGATORIOS`), no por cantidad de personas y fechas — eso solo pasaría si destino y tipo_destino ya estuvieran cargados de un turno anterior. Segundo turno: no repregunta nada de lo ya cargado.

## Fase 5, orquestador (días 9 a 11)

Agente con memoria de sesión, decisión entre los tres caminos, disparo automático del módulo de información del destino al confirmarse el destino. Migrar a LangGraph si el flujo se vuelve difícil de controlar.

**Aceptación:** RF11 y RF12 verificados en una conversación de 6 turnos sin que el usuario indique nunca qué tool usar.

## Fase 6, armar_plan (días 11 a 13)

Itinerario día a día con 2 o 3 actividades por día, costo estimado calculado (no inventado), persistencia en `itinerario` e `itinerario_item`.

**Aceptación:** RF5 completo. **Con el núcleo cerrado el TP ya es aprobable.** Recién acá se abren las extensiones.

## Fase 7, extensiones (días 13 a 17)

Orden por valor sobre esfuerzo, de mayor a menor. Si el tiempo se acorta, se cortan de abajo hacia arriba:

1. **Clima, idioma y moneda (RF8).** Barato, visible, y permite explicar en la defensa que no todo es RAG. Hecho, D-05/D-06 adelantado.
2. **Alojamiento y vuelos (RF6, RF7).** RapidAPI/Booking.com15 (reemplaza a Amadeus, D-06). Hecho, adelantado.
3. **FAQ del viajero (RF9).** Tercer corpus, `corpus='faq'`, curado a mano. El menos diferencial de los RAGs, pero de esfuerzo bajo y acotado (a diferencia de RF4).
4. ~~**Gastos (RF10).**~~ **Omitido, decisión del usuario (D-11 en `docs/DECISIONES.md`).** No se implementa.
5. **Recomendación de comercios (RF4), retomar si hay tiempo.** Movido de núcleo a extensión (D-07). Tool y RAG ya implementados y testeados con mocks; falta corpus real, vía curaduría manual dedicada en `data/curated/` o una fuente con más volumen (ej. Yelp API). Es la de menor prioridad porque ya se probó que el esfuerzo para cerrarla es alto (8+ horas), no por falta de valor.

## Fase 7B, interfaz de chat (GUI)

**No forma parte de la consigna de la cátedra** (el entregable oficial sigue siendo el notebook, ver `consigna-catedra.md`). Se agrega por pedido explícito del usuario, para que la demo se vea mejor que un CLI de texto plano. No reemplaza al notebook ni a `scripts/chat.py`.

- **Stack:** Streamlit. Elegido sobre Gradio por dar más control fino sobre botones de opciones predefinidas junto al historial de chat, y porque `st.chat_message`/`st.chat_input` ya resuelven la UI de chat sin código propio. Nueva dependencia, agregada a `requirements.txt` y justificada en `arquitectura.md`.
- **Capa de presentación pura:** `ui/chat_app.py` importa `SesionAgente`/`procesar_mensaje` de `asistente_viajes.agente`, igual que `scripts/chat.py` y el notebook. **Cero lógica de negocio nueva en la UI** (mismo principio que ya aplica al notebook, ver "Qué es el proyecto" en `SKILL.md`).
- **Botones de opciones predefinidas:** disparadores de conversación (ej. "Quiero armar un viaje a Cancún", "¿Qué puedo visitar en Barcelona?", "¿Es seguro tomar un taxi en Cancún?") que mandan el mismo texto que tipearía un usuario. **No eligen una tool ni un modo**: pasan por `procesar_mensaje` igual que cualquier mensaje escrito a mano, así que el orquestador sigue siendo el único que decide (RF12 no se toca).
- **Formateo:** el historial se renderiza con `st.chat_message` (markdown nativo), aprovechando que `_resumen_actividades`/`_resumen_locales`/`_resumen_faq` ya devuelven listas con guiones (markdown válido). Se resalta el nombre de cada ítem en negrita para que se lea como tarjeta, no como bloque de texto plano.
- **Estado:** una `SesionAgente` por sesión de navegador (`st.session_state`), en memoria del proceso, mismo alcance que ya tiene RF11 (no se persiste entre sesiones).
- **Tests:** no hay tests de pytest para `ui/chat_app.py` (mismo criterio que `scripts/chat.py`: es una capa interactiva que necesita LLM y Postgres reales para correr, no lógica mockeable). Se verifica levantando el server y probándolo a mano/con navegador antes de dar la fase por cerrada.

**Aceptación:** `streamlit run ui/chat_app.py` levanta sin errores, una conversación de varios turnos por texto libre funciona igual que por `scripts/chat.py`, y al menos un botón de opción predefinida dispara correctamente la tool esperada a través del orquestador (no hardcodeado).

## Fase 8, notebook de demo (días 17 a 20)

`notebooks/demo_tp2.ipynb`, estructura fija:

1. Caso de negocio y arquitectura (markdown, con diagrama del flujo).
2. Setup: instalación, variables de entorno, verificación de conexión a la base.
3. Ingesta y construcción de los corpus, ejecutable, con salida de conteos.
4. Prueba de recuperación aislada: consulta, documentos recuperados, distancias.
5. Slot filling paso a paso.
6. Conversación completa de punta a punta, el caso de demo principal.
7. Consultas puntuales de recomendación local.
8. Extensiones implementadas.
9. Casos de prueba y resultados, incluido **al menos un caso donde el sistema falla o se limita**, con la explicación. Esto suma en el criterio de identificación de dificultades, no resta.

**Aceptación:** corre de arriba a abajo en una máquina limpia, con el kernel reiniciado. Verificarlo de verdad, no asumirlo.

## Fase 9, documentación y defensa (días 20 a 22)

- `README.md`: qué es, cómo se instala, cómo se corre, arquitectura, mapa de RF a tool a archivo.
- `docs/DECISIONES.md` cerrado. Mínimo: por qué pgvector y no Chroma, por qué LangGraph y no CrewAI, por qué ese LLM, por qué ese modelo de embeddings, por qué OpenTripMap, por qué Amadeus y no Booking.
- `docs/DIFICULTADES.md` cerrado.
- Guion del video de 10 a 15 minutos con los siete puntos de la cátedra y el reparto de tiempos.
- Repaso del TP1 (clasificación de alumnos con redes neuronales), que se pregunta en la defensa.
