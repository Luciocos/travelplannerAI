# Cómo retomar la Fase 7E

Documento de traspaso. Sirve para seguir el trabajo sin el contexto de la
sesión en la que se hizo. Si ya terminó la fase, este archivo se borra.

**Ramas:** `fase/7e-flexibilidad` (funcional, todo verificado en vivo) y
`fase/7e-tool-calling` (la Etapa 2, sin verificar). Nada mergeado a `main`.
**Última verificación:** suite en verde (316 passed, 5 skipped) y `ruff check` limpio.

---

## De dónde salió esta fase

El usuario reportó, con capturas de una conversación real, que el agente era
rígido: pidió "armame un borrador, pero dejá el último día libre" y recibió un
plan con actividades todos los días; lo reclamó dos veces más, cada vez más
explícito, y recibió **el mismo plan byte por byte las tres veces**.

El diagnóstico fue más de fondo que un bug puntual (ver `P-14` en
`DIFICULTADES.md`): de las 5 llamadas al LLM del sistema, 4 eran
`con_salida_estructurada` (rellenar un schema, no redactar) y el 100% del texto
que veía el cliente salía de plantillas de Python. El modelo solo escribía
cuando no había pasado nada en el turno.

El objetivo que fijó el usuario, textual: *"un chatbot que pueda responder todo
sobre viajes y sea capaz de planificármelos"*, que *"se asemeje lo más posible a
charlar con un chatbot normal"*.

---

## Lo que ya está hecho y verificado en vivo

Todo commiteado en la rama, con su decisión documentada.

| Qué | Dónde | Doc |
|---|---|---|
| El LLM redacta la respuesta de **todos** los turnos; las tarjetas de datos van debajo de su prosa | `grafo.py:nodo_redactar`, `prompts.py:PROMPT_REDACTAR` | D-22 |
| El plan acepta ajustes del cliente (días libres, exclusiones, ritmo) y reporta qué aplicó y qué no | `ajustes.py`, `tools/armar_plan.py` | D-22 |
| Ingesta bajo demanda: responde por **cualquier** ciudad, la carga la primera vez y la cachea | `destinos_bajo_demanda.py`, `ingesta/opentripmap.py:geolocalizar` | D-23 |
| Calidad del corpus: kinds faltantes, puntaje de relevancia, reintento ante 429 | `ingesta/normalizar.py`, `destinos_bajo_demanda.py` | commit `5a59672` |
| Tarjetas de tres columnas (día, actividades, costo) | `presentacion.py:tarjeta_detallada` | D-20 (ampliada) |
| Iconos Material en la sidebar (los emoji salían vacíos en Chrome/macOS) | `ui/chat_app.py` | — |
| Off-by-one de fechas: un viaje de 5 días salía de 6 | `prompts.py` | P-14 |

Verificado hablándole a la app con Gemini y Postgres reales: Lisboa (nunca
precargada) arma plan, y pedir "dejame el último día libre" deja el día 5 sin
actividades, baja el total de USD 556 a 526 y lo confirma en palabras.

---

## Lo que queda pendiente

### 1. Itinerarios multi-ciudad — HECHO (commit `187c345`)

`PreferenciasViaje` tiene `tramos` (ciudad + días opcionales) y `armar_plan`
los recorre. Probar con *"Roma y Florencia, 3 días en cada una"*. Lo único
pendiente de este punto es escribir **D-24** en `docs/DECISIONES.md`.

### 2. Etapa 2: agente de tool-calling — YA ESCRITA, SIN VERIFICAR EN VIVO

**Está implementada en la rama `fase/7e-tool-calling`** (commit `ddce4d3`), no
en esta. Compila, la suite pasa (316) y `ruff` está limpio, pero **nunca se
probó contra Gemini real**. Eso es lo primero al retomar:

```bash
git checkout fase/7e-tool-calling
AGENTE_TOOL_CALLING=1 streamlit run ui/chat_app.py
```

Sin esa variable de entorno el sistema usa el orquestador de precondiciones de
siempre, que sí está verificado. Se hizo así a propósito: cambia de fondo cómo
se decide qué hacer en cada turno, y dejar el camino viejo como default evita
romper algo que funciona a días de la defensa.

Qué se agregó:

- `herramientas.py` (nuevo): el catálogo de tools de LangChain, con la conexión
  y el rotador inyectados por closure. El estado del viaje **no** se le pide al
  modelo como argumento: son datos que el sistema ya tiene, y hacérselos
  repetir es una invitación a que los altere.
- `llm.py`: `RotadorClavesGemini.con_herramientas()`, el equivalente rotado de
  `bind_tools()`, con el mismo failover que el resto.
- `grafo.py`: `nodo_agente_herramientas` corre el loop (máximo 4 vueltas) y un
  `add_conditional_edges` después de `planificar` elige camino según el flag.
- `prompts.py`: `PROMPT_AGENTE`, que **solo** decide qué tools llamar. La
  redacción sigue siendo la de D-22, así que ningún dato duro sale del modelo.

Qué falta:

1. **Probarlo en vivo** con las dos cosas que lo motivaron: pedir un cambio
   sobre un plan ya armado, y pedir "más opciones" (la queja textual fue *"no
   extiende más ni es más flexible"*).
2. Decidir si pasa a ser el default. Ojo: `nodo_planificar` sigue corriendo
   antes del agente y es el que arma `pedir_datos`, así que el slot filling
   (RF1/RF2) quedó intacto; hay que definir qué se hace con eso.
3. Tests del nodo nuevo, con el rotador mockeado.
4. Escribir **D-25** en `docs/DECISIONES.md`: el código ya la referencia pero la
   entrada no está.

El dato que lo hizo barato: el proyecto **ya tenía las `@tool` construidas**
(`crear_tool_armar_plan()` y equivalentes), con sus docstrings escritos para que
un agente los leyera, y `grafo.py` las esquivaba llamando las funciones de
Python directo. La pieza existía y estaba desconectada.

### 3. Corpus de Barcelona (conocido, sin resolver)

Barcelona es el caso patológico. OpenTripMap tiene cientos de edificios
catalogados con `rate=7` (el máximo) en el Eixample, así que esa señal **no
discrimina** y el corpus queda lleno de "Casa X" en vez de la Sagrada Família.

Se probaron y descartaron, midiendo contra las APIs reales:

- **Pageviews de Wikipedia**: vuelven vacíos para artículos que claramente
  tienen visitas (Plaza de Cataluña daba 0).
- **SPARQL a Wikidata** por cantidad de idiomas del artículo (que sería la
  mejor señal de "icónico"): timeout sobre una búsqueda geográfica.
- **Muestreo desde un anillo de 4 puntos** alrededor del centro: empeoró las dos
  ciudades de prueba, quedó documentado en `_puntos_de_muestreo`.

Dato comprobado: la Sagrada Família **sí** está en la API (`rate=7`, kinds
`religion,churches`); el problema es puramente de selección. El camino que
queda es curaduría a mano, como se hizo con Miami y Cancún (D-17), en
`data/curated/barcelona_atractivos.json` con `fuente='curado'`.

Tokio, en cambio, quedó bien tras los arreglos: Meiji Jingu, Edo Castle,
Palacio de Akasaka, jardines Koishikawa.

### 4. Pendientes heredados

- Cargar los repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y proteger
  `main`. Requiere acceso del equipo a GitHub, no se resuelve desde el código.
- Mergear `fase/7e-flexibilidad` a `main` cuando el usuario dé el visto bueno.
- Documentar **D-24** (multi-destino) en `docs/DECISIONES.md`: el código está
  hecho y commiteado, pero la entrada de la decisión no se escribió.

---

## Cómo levantar todo para probar

```bash
open -a Docker                       # el daemon tiene que estar corriendo
docker compose up -d                 # Postgres + pgvector
source .venv/bin/activate
streamlit run ui/chat_app.py         # GUI en localhost:8501
# alternativa sin navegador:
python -m scripts.chat
```

Verificación rápida antes de commitear: `ruff check src/ tests/ ui/` y
`python -m pytest tests/ -q`.

**Probar en vivo no es opcional en este proyecto.** Los bugs que importaron
(P-11, P-12, P-13, P-14) los encontró alguien hablándole a la app, no la suite:
los 248 tests verificaban que las funciones hicieran lo que hacían, no que el
asistente hiciera caso. Hay un patrón de script útil para esto: instanciar
`SesionAgente`, llamar `procesar_mensaje` turno a turno e imprimir con
`presentacion.texto_terminal`.

## Reglas del proyecto que conviene no olvidar

- Commits en español, `tipo(alcance): descripción`, **sin ningún trailer de
  coautoría ni mención a la herramienta generadora**.
- Una rama por fase, no commitear directo a `main`.
- Ningún test toca la red ni consume cuota de Gemini.
- Nada de datos inventados: lo que no está en el corpus o en una API, no se
  afirma.
- Las decisiones nuevas van a `docs/DECISIONES.md` (siguiente libre: **D-24**) y
  los bugs reales a `docs/DIFICULTADES.md` (siguiente libre: **P-15**).
