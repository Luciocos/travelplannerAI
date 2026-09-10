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

## Candidatos previsibles, confirmar si pasan de verdad

No inventar entradas. Estos son los puntos donde es probable que algo falle, listados para que se registren bien si ocurren:

- POIs de OpenTripMap sin extracto de texto, o sea sin nada útil que embeber.
- Cuota o caída de la API de OpenTripMap durante el desarrollo.
- Extractos de Wikipedia en inglés mezclados con consultas en español, y el efecto en la recuperación.
- El agente eligiendo la tool equivocada por un docstring ambiguo.
- Slot filling que repregunta algo ya respondido, o que pisa un slot cargado con None.
- Rate limit del LLM gratuito en medio de una demo.
- Amadeus, resolución de hotelIds por ciudad antes de pedir ofertas.
- Open-Meteo sin pronóstico para fechas a más de 16 días.
