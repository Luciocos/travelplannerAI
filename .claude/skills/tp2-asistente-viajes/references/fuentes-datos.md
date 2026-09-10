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

## Amadeus for Developers, alojamiento y vuelos (RF6, RF7)

Entorno de **test**, self service, sin aprobación. Una sola cuenta para los dos módulos, dos endpoints distintos de la misma API, no hace falta alta separada.

- Autenticación: OAuth2 `client_credentials` contra `test.api.amadeus.com`. Cachear el token, tiene vencimiento.
- Hotel Search: hay que **resolver primero los `hotelIds` por ciudad** y recién después pedir ofertas. Es el paso que se olvida siempre.
- Flight Offers Search: búsqueda directa por origen, destino y fechas.

**Verificar los paths y versiones de los endpoints contra la documentación vigente antes de codear.** Los paths de Hotel Search cambiaron de versión más de una vez, no asumirlos de memoria.

Los datos del entorno de test son datos de prueba, no reales. Aclararlo en la demo y en la defensa.

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
