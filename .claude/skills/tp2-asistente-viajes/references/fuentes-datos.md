# Fuentes de datos y APIs externas

Todas las fuentes de acá cumplen la restricción del proyecto: alta self service, gratuita, sin tarjeta, sin proceso de aprobación.

## OpenTripMap, base de los corpus de atractivos y comercios

API de puntos de interés. Gratuita, 5.000 requests por día, sin tarjeta, requiere API key gratuita.

**Se consulta en dos pasos, y esto es lo central. No saltearlo.**

1. **Búsqueda por radio o bbox** alrededor del destino (`/0.1/en/places/radius`). Devuelve una lista liviana: `name`, `xid` (identificador), `kind` (categorías tipo `historic`, `museums`, `foods`, `natural`) y coordenadas. **No trae texto descriptivo**, o sea que esa lista sola no alcanza para embeber nada útil. Embeber el nombre pelado no sirve.
2. **Detalle por `xid`** (`/0.1/en/places/xid/{xid}`), uno por POI que interese. Trae dirección, imagen y, cuando existe, un **extracto de texto tomado de Wikipedia**. Ese extracto es lo que efectivamente se embebe.

Muchos POIs son sólo un punto en el mapa sin ningún texto. Consecuencias operativas:

- Filtrar y quedarse sólo con los que tengan descripción suficiente. Definir el mínimo (por ejemplo 200 caracteres) y dejarlo documentado.
- Completar a mano, en `data/curated/`, los lugares importantes para la demo que la API no cubra bien. Ejemplo típico: el Mercado Artesanal de Salta, con dirección y rango de precio. Marcar con `fuente='curado'`.
- Guardar la respuesta cruda en `data/raw/` **antes** de normalizar, para no depender de la API en cada corrida ni quemar cuota.
- Si la API no responde, el pipeline sigue corriendo desde `data/raw/` y `data/curated/`, y avisa. Una API caída no puede voltear la demo el día de la defensa.

**Separación en dos corpus según `kind`:**

- Atractivos: `historic`, `museums`, `natural`, `cultural`, `architecture`.
- Comercios y gastronomía: `foods`, `shops`, `marketplaces`.

**Documento final del RAG:** destino, nombre, categoría, texto descriptivo (lo que se embebe), coordenadas, y para comercios dirección y rango de precio.

## Open-Meteo, clima (RF8)

`https://api.open-meteo.com/v1/forecast`. Gratuita, **sin API key y sin registro**, uso no comercial permitido de forma explícita. Se le pasa lat y lon del destino mas el rango de fechas y devuelve el pronóstico.

Parámetros útiles: `latitude`, `longitude`, `daily=temperature_2m_max,temperature_2m_min,precipitation_sum`, `timezone=auto`.

**Limitación que hay que manejar, no ignorar:** el pronóstico llega hasta unos 16 días. Para fechas más lejanas hay que usar promedios históricos (endpoint de archivo o climate) o aclarar la limitación en la respuesta al usuario. Devolver un pronóstico falso para un viaje a seis meses es peor que decir que no hay dato.

El clima **no es RAG**. Es una llamada en vivo a una API, porque es un dato que cambia todo el tiempo. Esto hay que tenerlo claro para la defensa, no todo el sistema es RAG.

## Idioma y moneda (RF8)

No necesita RAG ni embeddings. Es un dato estructurado que casi no cambia: alcanza con una tabla chica de referencia (`data/reference/paises.json`), país a idioma oficial a moneda, cargada una vez.

Saber explicar por qué acá **no** se usa RAG es parte de la defensa. Meter embeddings donde alcanza un diccionario es un error de criterio, no una virtud.

## Amadeus for Developers — dado de baja, reemplazado por RapidAPI (D-05/D-06)

Amadeus cerró el portal self-service que sustentaba la decisión original: registro de usuarios nuevos pausado desde marzo/abril de 2026, portal decomisionado por completo el 2026-07-17, keys existentes desactivadas desde esa fecha (confirmado 2026-09-10 por cobertura de prensa especializada). No hay forma self-service de conseguir `client_id`/`client_secret` hoy. Reemplazado por RapidAPI, ver abajo.

## RapidAPI (Booking.com15), alojamiento y vuelos (RF6, RF7)

Reemplaza a Amadeus. Una sola suscripción de cuenta (`RAPIDAPI_KEY`) sirve para todo, pero **cada API requiere suscripción explícita al plan Free desde su página en el marketplace** (Pricing → Subscribe), no alcanza con tener la key de cuenta — sin eso, todas las llamadas devuelven `403 {"message":"You are not subscribed to this API."}`.

**Hallazgo central: Booking.com15 (`booking-com15.p.rapidapi.com`) sirve por sí sola para hoteles y vuelos.** Fly Scraper, evaluada en paralelo como fuente primaria de vuelos, no tiene ningún endpoint de búsqueda real funcionando bajo esta suscripción (ver más abajo) — quedó reducida a un dato complementario opcional.

Patrón de dos pasos, igual en los dos dominios, verificado con llamadas reales el 2026-09-10:

- **Hoteles**: `GET /api/v1/hotels/searchDestination?query=<texto>` devuelve candidatos con `dest_id` y `search_type` (**en minúscula**: `"city"`, `"district"`, `"region"`, `"airport"` — ojo, la documentación de terceros y el código de ejemplo suelen asumir mayúscula). Con esos dos valores, `GET /api/v1/hotels/searchHotels` (parámetros: `dest_id`, `search_type`, `arrival_date`, `departure_date`, `adults`, `room_qty`, `currency_code`, `languagecode`) devuelve hoteles reales con precio, puntaje y reseñas. No trae dirección (hace falta `getHotelDetails`, no implementado).
- **Vuelos**: `GET /api/v1/flights/searchDestination?query=<texto>` (mismo nombre de endpoint que hoteles, pero bajo `/flights/`, no `/api/v1/flights/searchFlightLocation` como sugeriría el nombre "Search Flight Location" del playground) devuelve candidatos con `id` (ej. `"BUE.CITY"`, `"CUN.AIRPORT"`) y `type` (**en mayúscula**: `"CITY"`, `"AIRPORT"` — namespace de valores distinto al de hoteles). Con `fromId`/`toId`, `GET /api/v1/flights/searchFlights` (+ `departDate`, `adults`, `currency_code`, `cabinClass`, y `returnDate` si es ida y vuelta, sin verificar con llamada real) devuelve itinerarios reales con precio, aerolíneas y escalas.
- El envelope de Booking.com15 miente sobre el éxito: `{"status": true/false, "message", "data"}`, un error de parámetros puede volver con HTTP 200 y `status: false`. Nunca confiar solo en el código HTTP.
- Los dos dominios comparten host y key pero **no comparten namespace de id**: cachear la resolución de destino por separado (`booking_hoteles` / `booking_vuelos`).

**Fly Scraper (`fly-scraper.p.rapidapi.com`) — casi todos sus endpoints anunciados no funcionan.** Se probaron `auto-complete`, `search-oneway`, `search-roundtrip`, `get-airports`, `search-everywhere`, en variantes singular/plural y con/sin prefijo `v2`: todos devuelven 404 directo del proxy de RapidAPI (`X-RapidAPI-Proxy-Response: true`, ni llegan al backend real), pese a estar listados en el playground. El único que responde con datos reales es `GET /v2/flights/price-calendar?originSkyId=<IATA>&destinationSkyId=<IATA>` (acepta código IATA directo, sin resolución previa) — un calendario de precio mínimo por día, no una búsqueda de itinerarios. Se usa solo como dato complementario ("mejor día para viajar"), nunca como fuente de `buscar_vuelos`.

Implementado en `src/asistente_viajes/services/rapidapi/` (`client.py`, `booking.py`, `fly_scraper.py`, `cache.py`, `models.py`, `fixtures/`). Fixtures con respuestas reales grabadas para Barcelona/Cancún/Buenos Aires. Detalle completo del proceso de migración y verificación en `migracion-amadeus-a-rapidapi.md` (raíz del repo).

## Booking.com, descartada

La API oficial (Demand API) **no es de alta libre**: requiere ser aprobado como partner o afiliado, con un proceso de solicitud. No alcanza con registrarse. No es viable para el plazo del TP.

Alternativas, si el equipo específicamente quiere mostrar datos de Booking en la demo:

- **Wrappers no oficiales en RapidAPI**: freemium, alta inmediata, pero no son de Booking, scrapean o replican su catálogo. Pueden romperse si Booking cambia su sitio. Si se usan, se aclara en la defensa que es acceso no oficial.
- **StayAPI**: 50 requests gratis al registrarse, sin tarjeta, junta datos de Booking, Expedia y TripAdvisor. Sirve para probar rápido la calidad de los datos, pero el volumen gratuito es muy bajo para desarrollo sostenido.

Recomendación vigente: arrancar con Amadeus, que ya está evaluado y es confiable, y sumar el wrapper de RapidAPI sólo si hay una razón concreta de demo.

## LLM

Google Gemini con un modelo Flash Lite, y rotación de tres claves. Todo el detalle (elección del modelo, rotador, manejo de 429, higiene de secretos, ahorro de cuota) está en `llm-y-claves.md`. Groq con Llama 3.3 70B queda como alternativa evaluada y descartada, la decisión ya está tomada.

## Embeddings

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensiones, multilingüe (importante, los textos son en español y los extractos de Wikipedia pueden venir en inglés), corre en CPU. Alternativa: embeddings de Gemini, si se quiere evitar la descarga del modelo local.

Si se cambia el modelo de embeddings, cambia la dimensión del vector y hay que recrear la tabla y reindexar todo. No es un cambio menor, decidirlo temprano.

Los embeddings son **locales a propósito**, no de Gemini: embeber los corpus son cientos de llamadas y la cuota gratuita se reserva para el chat. Es un argumento de diseño para la defensa.
