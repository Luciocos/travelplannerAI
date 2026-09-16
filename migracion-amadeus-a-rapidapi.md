# Migración de Amadeus → RapidAPI (Booking.com15 + Fly Scraper)

Documento de trabajo para Claude Code. Describe qué se da de baja, qué lo reemplaza y con qué forma, para los módulos `buscar_alojamiento` (RF6) y `buscar_vuelos` (RF7) del asistente de viajes.

---

## Prompt para pegarle a Claude Code

> Necesito migrar la integración de Amadeus a RapidAPI. Amadeus dio de baja su portal self-service en julio 2026 y las credenciales ya no sirven; Duffel, que era el reemplazo previsto, no acepta altas desde Argentina. Las dos APIs nuevas son **Booking.com15** (host `booking-com15.p.rapidapi.com`, para hoteles) y **Fly Scraper** (host `fly-scraper.p.rapidapi.com`, para vuelos), ambas en RapidAPI con plan Free y autenticación por headers `x-rapidapi-key` / `x-rapidapi-host`.
>
> Leé el documento `migracion-amadeus-a-rapidapi.md` completo antes de tocar código. Seguí el orden de las secciones 1 a 7 y no avances a la siguiente hasta terminar la anterior. Las secciones 3 (cache) y 6 (fixtures) no son opcionales: los planes Free tienen cuotas muy bajas y no podemos quemarlas en desarrollo ni depender de la red el día de la defensa.
>
> Antes de escribir los adaptadores, hacé **una** llamada real por endpoint contra el playground o con curl, guardá la respuesta como fixture y escribí el parser contra esa respuesta real — no contra lo que asumas que devuelve. Los paths y nombres de parámetros que figuran en el documento son los esperados, pero hay que verificarlos.

---

## 0. Antes de todo: rotar la API key

La key `3c20b7e4...cdb05` quedó visible en una captura de pantalla compartida. Antes de cualquier otra cosa:

1. Entrar a RapidAPI → **My Apps** → la app correspondiente → **Security** → regenerar la key.
2. Cargar la nueva en `.env` local (nunca versionado).
3. Verificar que `.gitignore` incluya `.env` y que la key vieja no haya quedado commiteada. Si quedó en el historial de git, no alcanza con borrarla en un commit nuevo — hay que reescribir historial o, más simple, dar por perdida esa key (ya rotada) y seguir.

---

## 1. Qué se da de baja

Buscar y eliminar del código y de la configuración:

- El cliente OAuth2 de Amadeus completo: el `POST /v1/security/oauth2/token`, el manejo de `access_token`, el refresh a los 30 minutos, el cacheo del token. **Nada de eso aplica ahora** — RapidAPI usa headers estáticos, no hay token que expire.
- Las variables `AMADEUS_CLIENT_ID` y `AMADEUS_CLIENT_SECRET` en `.env`, `.env.example`, `config.py` y donde estén referenciadas.
- Los llamados a `/v1/reference-data/locations/hotels/by-city`, `/v3/shopping/hotel-offers` y `/v2/shopping/flight-offers`.
- Cualquier lugar donde se pasen códigos IATA de ciudad (`BUE`, `EZE`, `MAD`) como identificador de destino. Las APIs nuevas **no usan IATA como clave de búsqueda**, usan identificadores propios que hay que resolver primero (ver sección 3).
- La dependencia `amadeus` en `requirements.txt` / `pyproject.toml`, si está.

Lo que **no** se toca: la firma de las tools de LangChain (`buscar_alojamiento`, `buscar_vuelos`), su docstring, y los modelos de dominio que el agente consume. Toda la migración tiene que quedar por debajo de esa frontera. Si al terminar cambió la firma de una tool, algo se hizo mal.

---

## 2. Variables de entorno

El `.env` de trabajo tiene los nombres escritos como headers HTTP (`X-RapidAPI-Key=...`). **Eso hay que renombrarlo**: los guiones no son válidos en nombres de variables de entorno en shell, y `python-dotenv` / `pydantic-settings` no los mapean a atributos. Nombres correctos:

```dotenv
# --- RapidAPI (reemplaza a Amadeus para RF6/RF7) ---
RAPIDAPI_KEY=

# Hosts por API (el valor va en el header x-rapidapi-host de cada request)
RAPIDAPI_HOST_BOOKING=booking-com15.p.rapidapi.com
RAPIDAPI_HOST_FLY_SCRAPER=fly-scraper.p.rapidapi.com

# Presupuesto de llamadas del plan Free, para el guard de cuota (sección 5)
RAPIDAPI_MONTHLY_QUOTA_BOOKING=100
RAPIDAPI_MONTHLY_QUOTA_FLY_SCRAPER=100

# Modo demo: si es true, no sale a la red, sirve todo desde fixtures
USE_FIXTURES=false
```

Actualizar `config.py` para exponerlas, siguiendo el patrón que ya existe ahí para las claves de Gemini. Actualizar también `.env.example` con las mismas claves vacías y un comentario de dónde se saca cada una.

Una sola key sirve para las dos APIs — es la key de la cuenta de RapidAPI, no de la suscripción. Lo que cambia entre una y otra es únicamente el `x-rapidapi-host`.

---

## 3. Arquitectura objetivo

La estructura a construir, de abajo hacia arriba:

```
services/
  rapidapi/
    client.py         # cliente HTTP compartido: headers, retry, timeout, contador de cuota
    booking.py        # adaptador Booking.com15  → modelos normalizados
    fly_scraper.py    # adaptador Fly Scraper    → modelos normalizados
    models.py         # Alojamiento, OpcionVuelo, DestinoResuelto
    cache.py          # cache de resolución de destinos en Postgres
    fixtures/         # respuestas reales grabadas, una por endpoint
tools/
  buscar_alojamiento.py   # sin cambios de firma; adentro llama a booking, fallback fly_scraper
  buscar_vuelos.py        # sin cambios de firma; adentro llama a fly_scraper, fallback booking
```

### 3.1 Cliente HTTP compartido (`client.py`)

Una sola función/clase que todas las llamadas usan:

- Inyecta `x-rapidapi-key` (de `RAPIDAPI_KEY`) y `x-rapidapi-host` (el que reciba como parámetro).
- `timeout` explícito de 15 s. Fly Scraper responde en ~3 s y Booking en ~3,5 s en condiciones normales, pero los wrappers tienen picos.
- Retry con backoff exponencial **solo** en 429 y 5xx, máximo 2 reintentos. Nunca reintentar un 4xx que no sea 429 — es un error de parámetros y reintentarlo solo gasta cuota.
- Incrementa un contador persistente de llamadas por proveedor y mes (ver sección 5).
- Si `USE_FIXTURES=true`, no sale a la red: devuelve el fixture correspondiente al endpoint y los parámetros.
- Loguea cada request con proveedor, endpoint y latencia, sin loguear nunca la key.

### 3.2 Modelos normalizados (`models.py`)

Este es el punto clave del diseño: **la forma cruda de cada API no puede llegar al agente**. Los dos proveedores devuelven estructuras completamente distintas para lo mismo, y son wrappers no oficiales que pueden cambiar. Definir con `pydantic` o `dataclass`:

```python
class DestinoResuelto:
    proveedor: str  # "booking" | "fly_scraper"
    texto_consultado: str  # "Buenos Aires"
    id_externo: str  # dest_id (Booking) | entityId (Fly Scraper)
    tipo: str | None  # search_type en Booking: "CITY", "REGION", "district"...
    nombre: str
    pais: str | None
    lat: float | None
    lon: float | None


class Alojamiento:
    nombre: str
    precio_total: float | None
    moneda: str | None
    puntaje: float | None  # escala 0-10
    cantidad_resenias: int | None
    direccion: str | None
    url_imagen: str | None
    proveedor: str


class OpcionVuelo:
    origen: str  # IATA
    destino: str  # IATA
    fecha_salida: str  # ISO
    fecha_regreso: str | None
    precio_total: float | None
    moneda: str | None
    aerolineas: list[str]
    escalas: int
    duracion_minutos: int | None
    proveedor: str
```

Cada adaptador tiene una función `_a_modelo(raw) -> Alojamiento | OpcionVuelo` y **es el único lugar del proyecto que conoce la forma cruda**. Todos los campos son opcionales salvo el nombre y el proveedor: los wrappers omiten campos con frecuencia y un `KeyError` no puede tumbar la tool.

### 3.3 Cache de resolución de destinos (`cache.py`)

Sin esto la cuota Free se quema en un par de días de desarrollo. Ninguna de las dos APIs acepta "Buenos Aires" como parámetro de búsqueda: primero hay que traducirlo a un identificador propio, y esa traducción **no cambia nunca**.

Tabla en el Postgres que ya tiene el proyecto:

```sql
CREATE TABLE IF NOT EXISTS destino_externo (
    id              SERIAL PRIMARY KEY,
    proveedor       TEXT NOT NULL,        -- 'booking' | 'fly_scraper'
    texto_consultado TEXT NOT NULL,       -- normalizado: lower, sin tildes, trim
    id_externo      TEXT NOT NULL,
    tipo            TEXT,
    payload         JSONB NOT NULL,       -- respuesta cruda, para poder re-parsear sin volver a llamar
    creado_en       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (proveedor, texto_consultado)
);
```

Regla: **toda** resolución de destino pasa por el cache primero. Solo si no hay hit se llama a la API, y el resultado se guarda. Precargar de entrada los 2-3 destinos piloto del proyecto para que la demo no dependa de resolverlos en vivo.

---

## 4. Endpoints

> Los paths y nombres de parámetros de abajo son los esperados según la documentación de cada API. **Verificar cada uno con una llamada real en el playground de RapidAPI antes de escribir el parser**, y guardar esa respuesta como fixture. Si alguno difiere, corregir acá el documento.

### 4.1 Booking.com15 — hoteles (primario para RF6)

Base: `https://booking-com15.p.rapidapi.com`

| Paso | Endpoint | Parámetros clave | Devuelve |
|---|---|---|---|
| 1. Resolver destino | `GET /api/v1/hotels/searchDestination` | `query` | `dest_id` + `search_type` |
| 2. Buscar hoteles | `GET /api/v1/hotels/searchHotels` | `dest_id`, `search_type`, `arrival_date`, `departure_date`, `adults`, `room_qty`, `currency_code`, `languagecode` | lista de hoteles con precio |
| 3. Detalle (opcional) | `GET /api/v1/hotels/getHotelDetails` | `hotel_id`, `arrival_date`, `departure_date` | descripción, servicios, fotos |

**Gotcha importante:** `searchHotels` necesita `dest_id` **y** `search_type` juntos. El `search_type` viene en la respuesta del paso 1 (`"CITY"`, `"REGION"`, `"district"`, `"hotel"`) y mandarlo mal devuelve resultados vacíos sin error. Guardar los dos en el cache.

Formato de fechas: `YYYY-MM-DD`. Para pesos argentinos: `currency_code=ARS`, `languagecode=es`.

### 4.2 Fly Scraper — vuelos (primario para RF7)

Base: `https://fly-scraper.p.rapidapi.com`

Usar la familia **v2**, que es la mantenida:

| Paso | Endpoint | Parámetros clave | Devuelve |
|---|---|---|---|
| 1. Resolver origen y destino | `GET /v2/flight/auto-complete` | `query` | `skyId` + `entityId` por aeropuerto/ciudad |
| 2a. Ida sola | `GET /v2/flight/search-oneway` | origen/destino (entityId), `departDate`, `adults`, `currency`, `market`, `locale` | itinerarios con precio |
| 2b. Ida y vuelta | `GET /v2/flight/search-roundtrip` | lo anterior + `returnDate` | itinerarios con precio |
| 3. Calendario (opcional) | `GET /v2/flights/price-calendar` | origen/destino, mes | precio mínimo por día |

**Gotcha:** el autocompletado devuelve `skyId` y `entityId`, que son cosas distintas. Verificar en el playground cuál de los dos espera el endpoint de búsqueda y cachear ambos.

`market`/`locale`/`currency` para Argentina: `AR` / `es-AR` / `ARS`. Ojo que estas rutas pueden requerir dos llamadas (una que inicia la búsqueda y otra que la completa — está el endpoint `search-incomplete` justamente para eso): confirmar en el playground si la primera respuesta ya viene completa o hay que hacer polling.

### 4.3 Fallbacks cruzados

Cada API cubre también el dominio de la otra. Implementar el fallback una vez que los caminos primarios funcionen, no antes:

- `buscar_alojamiento`: Booking `searchHotels` → si falla, Fly Scraper `GET /hotel/search` (previo `GET /hotel/auto-complete`).
- `buscar_vuelos`: Fly Scraper `search-oneway`/`search-roundtrip` → si falla, Booking `GET /api/v1/flights/searchFlights` (previo `GET /api/v1/flights/searchDestination`).

Como ambos adaptadores devuelven los mismos modelos normalizados, el fallback es un `try/except` en la tool, no una rama de lógica duplicada.

---

## 5. Gotchas y manejo de errores

**El envelope de Booking miente sobre el éxito.** Todas las respuestas vienen como:

```json
{ "status": true, "message": "Success", "timestamp": 1698332419875, "data": [ ... ] }
```

Un error de parámetros puede volver con **HTTP 200** y `"status": false`. Nunca confiar solo en `response.status_code`: verificar `body["status"] is True` antes de leer `data`, y tratar `status: false` como error, propagando `message`.

**`data` cambia de tipo.** Según el endpoint es una lista o un objeto con la lista adentro (`data.hotels`, `data.result`). Verificar por endpoint contra el fixture, no asumir.

**429 = cuota agotada, no congestión.** En el plan Free un 429 normalmente significa que se acabó la cuota del mes, no que haya que esperar. Reintentar dos veces y después cortar: activar el fallback, y si el fallback también da 429, servir el fixture y marcar la respuesta como datos de ejemplo. La tool debe devolverle al agente una señal clara de que son datos de fixture, para que el LLM no le afirme al usuario que son precios reales.

**Guard de cuota.** Llevar un contador persistido por proveedor y mes. Si se pasa del 80% del presupuesto declarado en `.env`, loguear un warning bien visible; al 100%, no llamar más y pasar directo a fixtures. Es la diferencia entre enterarse a tiempo y descubrirlo durante la demo.

**Nunca loguear la key.** El cliente HTTP debe enmascararla en cualquier log o traceback.

---

## 6. Fixtures

Grabar una respuesta real por cada endpoint que se use, en `services/rapidapi/fixtures/`, con nombre `<proveedor>_<endpoint>.json`. Se generan una sola vez, con los destinos piloto del proyecto y fechas fijas.

Sirven para tres cosas: escribir los parsers contra datos reales en vez de suposiciones, correr los tests sin gastar cuota ni depender de la red, y tener un modo demo (`USE_FIXTURES=true`) que funcione aunque el wi-fi del aula falle o la API esté caída ese día.

Tests mínimos: un test por adaptador que cargue el fixture y verifique que el parser produce el modelo normalizado con los campos esperados, más un test de que un fixture con campos faltantes no rompe el parser.

---

## 7. Checklist de aceptación

- [x] La key vieja está rotada y la nueva solo vive en `.env` (no versionado). Confirmado, no llegó a quedar committeada en ningún momento.
- [x] No queda ninguna referencia a `amadeus`, `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET` ni al flujo OAuth2 en el repo (fuera de menciones históricas en docs/decisiones).
- [x] `.env.example` y `config.py` exponen `RAPIDAPI_KEY`, los dos hosts, las cuotas y `USE_FIXTURES`, con nombres válidos como variables de entorno.
- [x] La tabla `destino_externo` existe (en `sql/001_schema.sql`) y toda resolución de destino la consulta antes de salir a la red. Pendiente crearla en la Postgres real (no hay `DATABASE_URL` todavía, ver `estado.md`).
- [x] `buscar_alojamiento` devuelve `list[Alojamiento]` y `buscar_vuelos` devuelve `list[OpcionVuelo]` (no había firma previa, es la primera implementación real de RF6/RF7).
- [x] Hay un fixture grabado por endpoint usado, y los tests corren sin red (67 tests, `pytest`).
- [~] Con `USE_FIXTURES=true` no hay llamada externa a RapidAPI. Sigue habiendo dependencia de Postgres para el cache de destinos (infra que el proyecto ya necesita para todo lo demás, no es un requisito nuevo).
- [x] **Revisado, ya no aplica como estaba pensado**: no hay fallback cruzado real entre Booking.com15 y Fly Scraper (ver addendum abajo, sección 4 de Fly Scraper no funciona). Un fallo de Booking.com15 (429 u otro) cae directo a fixture marcado como dato de ejemplo.
- [ ] Los destinos piloto están precargados en el cache. Pendiente, requiere Postgres real.

## Addendum, hallazgos reales de la verificación (2026-09-10)

Antes de escribir los adaptadores se verificó cada endpoint con llamadas reales (curl / RapidAPI Playground), como pedía este documento. El resultado difiere bastante de lo asumido en las secciones 1 a 6:

- **RapidAPI exige suscripción explícita por API** (Pricing → Subscribe al plan Free), no alcanza con la key de cuenta. Sin eso, 403 `"You are not subscribed to this API"`.
- **Booking.com15 funciona para hoteles y para vuelos.** `search_type` de `searchDestination` (hoteles) viene en minúscula (`"city"`, no `"CITY"`). El endpoint de resolución de destino de vuelos es `/api/v1/flights/searchDestination` (mismo nombre que hoteles, no `searchFlightLocation`), y devuelve `type` en mayúscula (`"CITY"`, `"AIRPORT"`) — namespace de valores distinto al de hoteles, aunque sea la misma API.
- **Fly Scraper no tiene ningún endpoint de búsqueda real funcionando** bajo esta suscripción: `auto-complete`, `search-oneway`, `search-roundtrip`, `get-airports`, `search-everywhere` (variantes singular/plural, con/sin `v2`) devuelven 404 directo del proxy de RapidAPI (`X-RapidAPI-Proxy-Response: true`, nunca llegan al backend), pese a estar listados en el playground. El único que responde de verdad es `v2/flights/price-calendar`.
- **Decisión resultante (D-06 en `docs/DECISIONES.md`):** Booking.com15 es la fuente única de RF6 y RF7. Fly Scraper queda reducido a `price-calendar` como dato complementario opcional. No hay fallback cruzado real como proponía la sección 4.3 — si Booking.com15 falla, se sirve fixture directamente.

Detalle completo, con los comandos usados y las respuestas, en `docs/DECISIONES.md` (D-05, D-06) y `fuentes-datos.md` de la skill del proyecto.