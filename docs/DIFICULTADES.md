# Dificultades encontradas

"Identificación de dificultades" es un criterio de evaluación con peso propio, y es el punto 6 de los contenidos mínimos del video. Anotar cada problema real en el momento en que aparece. Un TP que no puede contar ningún problema pierde puntos en ese criterio.

Formato de cada entrada:

## P-NN, título del problema

- **Fecha:** 
- **Fase:** 
- **Síntoma:** qué se vio, con el error concreto si lo hubo.
- **Causa:** qué lo estaba produciendo.
- **Solución:** qué se hizo.
- **Aprendizaje:** qué cambia de acá en adelante por esto.

---

## P-01, destinos piloto del handoff no son coordenadas utilizables

- **Fecha:** 2026-09-10
- **Fase:** 1
- **Síntoma:** el handoff inicial define los destinos piloto como "Europa, Miami, Caribe". Al escribir el cliente de OpenTripMap se vio que la búsqueda por radio necesita una coordenada puntual, no sirve un continente ni una región.
- **Causa:** el handoff se escribió pensando en el caso de negocio (tipos de viaje que el sistema cubre) y no en el requisito técnico de la fuente de datos.
- **Solución:** el pipeline de ingesta (`ingerir_destino`, `scripts/ingestar_destino.py`) se dejó parametrizado por destino + `lat`/`lon`, listo para correr apenas el equipo defina ciudades concretas. No se inventó una ciudad por decisión unilateral, ver D-04 en `DECISIONES.md`.
- **Aprendizaje:** un destino piloto para este sistema tiene que ser una ciudad o localidad puntual, no una región. Repasar esto en la defensa como parte de las decisiones de alcance.

---

## P-02, corpus de comercios (y de atractivos en Cancún) por debajo del mínimo con solo la API

- **Fecha:** 2026-09-10
- **Fase:** 1
- **Síntoma:** al correr `scripts/ingestar_destino.py` contra los tres destinos piloto: Barcelona 41 atractivos / **2 comercios**, Miami 75 atractivos / **2 comercios**, Cancún **7 atractivos** / **0 comercios** (mínimo pedido: 25 y 15 respectivamente). Se probó relajar el filtro de significancia (`rate=1`) y ampliar el radio a 50km para Cancún: subió de 0 a 7 atractivos, comercios siguió en 0.
- **Causa:** la mayoría de los POIs de `foods`/`shops`/`marketplaces` en OpenTripMap no tienen extracto de Wikipedia (fuente del texto que se embebe), independientemente de la ciudad. En Cancún además hay poca densidad de contenido editorial también para atractivos, incluso en un radio de 50km.
- **Solución:** se aceptó el número real de la API como está, sin seguir ajustando parámetros (decisión explícita del usuario, para no perder tiempo de desarrollo persiguiendo un dato que la fuente no tiene). El faltante se completa con curaduría manual en `data/curated/`, marcado `fuente='curado'`, como prevé la skill del proyecto para este caso exacto.
- **Aprendizaje:** para este tipo de fuente (POIs geográficos con texto opcional de Wikipedia), el corpus de comercios va a depender de curaduría manual en cualquier destino, no es un problema de parámetros de búsqueda. Dimensionar el tiempo de curaduría en el cronograma en función de esto, no como una tarea chica de "completar lo que falte".

## P-03, Amadeus for Developers discontinuado, migración a RapidAPI

- **Fecha:** 2026-09-10
- **Fase:** 0 (afecta Fase 7)
- **Síntoma:** al ir a generar las credenciales de Amadeus documentadas para RF6/RF7, el registro self-service ya no existía.
- **Causa:** Amadeus decidió discontinuar el portal self-service de su API (pausa de altas nuevas desde marzo/abril de 2026, decomisionado por completo el 2026-07-17), sin relación con nada del proyecto.
- **Solución:** migración completa a RapidAPI (Booking.com15 + Fly Scraper), documentada en `migracion-amadeus-a-rapidapi.md` y D-05/D-06 de este documento. Antes de escribir los adaptadores se verificó cada endpoint con llamadas reales, lo que reveló que Fly Scraper tampoco funciona como se esperaba (ver P-04).
- **Aprendizaje:** una decisión de arquitectura basada en "API self-service gratuita de un tercero" puede quedar invalidada por una decisión de negocio del proveedor, sin aviso. Vale la pena, para la defensa, tener el argumento de por qué el diseño (tools con firma estable, adaptador único por debajo) permitió absorber el cambio sin tocar el resto del sistema.

## P-04, la mayoría de los endpoints anunciados de Fly Scraper no funcionan

- **Fecha:** 2026-09-10
- **Fase:** 0 (afecta Fase 7)
- **Síntoma:** `auto-complete`, `search-oneway`, `search-roundtrip`, `get-airports`, `search-everywhere` (probados en variantes singular/plural, con y sin prefijo `v2`) devuelven `404` con el mensaje `"Endpoint '...' does not exist"`, directo del proxy de RapidAPI (header `X-RapidAPI-Proxy-Response: true`, nunca llegan al backend real), a pesar de estar listados en el Playground de la API con esos nombres exactos.
- **Causa:** desconocida (no es un problema de suscripción ni de la key, confirmado con otro endpoint de la misma API que sí responde). Aparentemente el Playground anuncia rutas que no están realmente registradas en el backend de este proveedor.
- **Solución:** se descartó Fly Scraper como fuente de búsqueda de vuelos. El único endpoint que responde con datos reales, `v2/flights/price-calendar`, se usa solo como dato complementario. Booking.com15 quedó como fuente única de RF6 y RF7 (D-06).
- **Aprendizaje:** con wrappers no oficiales o de terceros en marketplaces como RapidAPI, la documentación del Playground no es garantía de que el endpoint funcione. Verificar cada endpoint con una llamada real antes de comprometer una arquitectura a él, que es justo lo que pedía el documento de migración y lo que permitió detectar esto a tiempo.

---

## Candidatos previsibles, confirmar si pasan de verdad

No inventar entradas. Estos son los puntos donde es probable que algo falle, listados para que se registren bien si ocurren:

- Cuota o caída de la API de OpenTripMap durante el desarrollo.
- Extractos de Wikipedia en inglés mezclados con consultas en español, y el efecto en la recuperación.
- El agente eligiendo la tool equivocada por un docstring ambiguo.
- Slot filling que repregunta algo ya respondido, o que pisa un slot cargado con None.
- Rate limit del LLM gratuito en medio de una demo.
- Open-Meteo sin pronóstico para fechas a más de 16 días.
