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
