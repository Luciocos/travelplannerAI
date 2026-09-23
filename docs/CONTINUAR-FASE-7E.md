# Cómo retomar la Fase 7E

Documento de traspaso. Sirve para seguir el trabajo sin el contexto de la
sesión en la que se hizo. Si ya terminó la fase, este archivo se borra.

**Rama:** `fase/7e-flexibilidad`. Nada mergeado a `main`.
**Última verificación:** suite en verde (248 passed, 5 skipped) y `ruff check` limpio.

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

### 1. Itinerarios multi-ciudad y multi-país (pedido explícito)

Hoy `PreferenciasViaje.destino` es un único `str`. Diseño ya pensado, sin
implementar:

- Agregar `tramos: list[Tramo] | None` a `PreferenciasViaje`, con
  `Tramo = {destino: str, dias: int | None}`. **Mantener** el campo `destino`
  como el destino "actual" para no romper `conversaciones.py`, la UI, ni los
  248 tests de un saque: `recomendar_actividades`, `info_destino` y
  `buscar_alojamiento` lo siguen usando.
- Ojo con el merge (RF2): igual que `ajustes`, `tramos` tiene que distinguir
  `None` ("este turno no habló de tramos") de `[]` ("se dieron de baja"). Con
  `default_factory=list` cualquier turno sin tramos borraría los anteriores.
  Ver el comentario largo en `PreferenciasViaje.ajustes`.
- Sumar `tramos` a `CAMPOS_QUE_AFECTAN_EL_PLAN` en `estado.py`, para que
  cambiarlos dispare el re-armado que ya existe.
- `armar_plan` itera los tramos, numera los días de corrido y suma costos por
  tramo: `estimar_gasto_diario` es **por destino**, así que no se puede usar un
  único valor para todo el viaje.
- Cada tramo se carga con `asegurar_destino()` (D-23), que ya resuelve ciudad
  nueva → geocodificar → ingerir → cachear.
- La tarjeta tiene que mostrar a qué ciudad corresponde cada día
  (`_resumen_plan` en `grafo.py` usa `tarjeta_detallada`, la columna de
  etiqueta ya admite dos líneas).
- El prompt de extracción tiene que capturar "quiero ir a Roma y Florencia,
  3 días en cada una".

### 2. Etapa 2: agente de tool-calling (lo más importante)

Es lo que falta para que se sienta como ChatGPT/Claude. Hoy `grafo.py` decide
todo con `if`s de precondición en `nodo_planificar` y llama las funciones de
Python directo.

**El dato clave:** el proyecto **ya tiene las `@tool` construidas**
(`crear_tool_armar_plan()` en `tools/armar_plan.py` y equivalentes), con sus
docstrings escritos para que el agente los lea... y `grafo.py` las esquiva. La
pieza existe y está desconectada.

- Reemplazar el pipeline rígido por un loop de tool-calling de LangGraph.
  LangChain/LangGraph es requisito textual de la cátedra, no se cambia.
- El LLM decide solo qué tools llamar y puede encadenar varias. Eso cumple RF12
  mejor que el diseño actual.
- **Conservar** lo que ya funciona y costó encontrar: la redacción libre (D-22),
  los ajustes del plan, el disparo automático de `info_destino` (RF12), la
  persistencia de chats, y que ningún dato duro salga del LLM (regla dura 5).
- El usuario se quejó de que *"no extiende más ni es más flexible"*: tiene que
  poder **agregar** atractivos a un plan existente, no solo rearmarlo entero.

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
