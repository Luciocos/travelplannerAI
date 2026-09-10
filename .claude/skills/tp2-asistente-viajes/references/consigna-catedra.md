# Consigna de la cátedra

Trabajo Práctico N°2, Sistemas Inteligentes con RAG o Agentes. UTN FRRo, Inteligencia Artificial, 5° año.
Tipo de trabajo: práctico con defensa oral.

## Objetivo

Diseñar y construir un sistema experto funcional que resuelva un problema real o simulado dentro de un caso de negocio elegido por el equipo. Se espera que el sistema tome decisiones, recupere información relevante, interactúe en lenguaje natural y demuestre inteligencia contextual.

Los cuatro pilares que se evalúan: **agentes, RAG, embeddings, NLP con LLM**.

## Requisitos técnicos, textuales

- El sistema debe estar construido usando **Langchain como framework principal**.
- Puede estar basado en un agente inteligente que actúe sobre múltiples herramientas (search, APIs, bases de datos), o en un sistema de RAG que enriquezca respuestas mediante recuperación de información. Este proyecto hace las dos cosas.
- El modelo de lenguaje puede ser GPT vía API de OpenAI, LLaMA local o por API alternativa, u otros modelos no vistos en clase.
- De ser necesario, usar embeddings de texto para representar documentos o consultas.
- La lógica del sistema debe estar documentada y ser **reproducible en un notebook interactivo**.

Agregado del profesor sobre el vector store: usar **PostgreSQL con pgvector** en lugar de Chroma.

## Entregables

1. **Notebook interactivo** con el sistema desarrollado, código y comentarios.
2. **Presentación oral** (defensa) sobre: caso de negocio elegido, cómo se resolvió con IA, qué decisiones se tomaron y por qué, qué dificultades se encontraron, qué resultados se obtuvieron.
3. **Video explicativo** de 10 a 15 minutos, si el docente lo solicita.

## Criterios de evaluación

| Criterio | Qué mira |
|----------|----------|
| Funcionamiento del sistema | Que funcione correctamente con casos de prueba |
| Aplicación del marco teórico | Uso adecuado de RAG, agentes, NLP, embeddings |
| Creatividad y originalidad | Valoración del caso de negocio y la solución |
| Documentación técnica | Claridad del código, explicaciones y decisiones |
| Identificación de dificultades | Capacidad de explicar errores, problemas y cómo se resolvieron |
| Presentación y defensa | Calidad de la presentación, dominio del tema, respuestas |

Consecuencia operativa: **"identificación de dificultades" es un criterio con peso propio**. Cada problema real que aparezca durante el desarrollo se anota en `docs/DIFICULTADES.md` en el momento, no se reconstruye de memoria al final. Un TP que anduvo perfecto y no puede contar ningún problema pierde puntos en ese criterio.

## Requisitos del video, si se solicita

Duración: mínimo 10 minutos, máximo 15. Formato: pantalla mas voz, o con los integrantes en cámara. Herramientas sugeridas: OBS, Zoom, Loom, Google Meet, o grabación de celular o computadora. El link (YouTube, Drive o similar, con permisos correctos) se envía en la fecha que indique el docente por mail.

Contenidos mínimos, los siete puntos:

1. Presentación del equipo y del caso de negocio elegido.
2. Descripción general del sistema experto desarrollado.
3. Explicación técnica de cómo se aplicó RAG o agentes con Langchain.
4. Justificación de las decisiones tomadas (modelo, arquitectura, herramientas).
5. Demostración básica del sistema funcionando.
6. Principales dificultades encontradas y cómo fueron abordadas.
7. Reflexión final, aprendizajes y posibles mejoras.

Se evalúa claridad conceptual y técnica, capacidad de comunicar, dominio del sistema y las herramientas, y nivel de reflexión.

## Fechas

- Entrega del video, para todos los grupos aceptados: **30 de septiembre de 2026**.
- Defensa oral, obligatoria y presencial:
  - Turno tarde y noche: miércoles 30 de septiembre de 2026, y miércoles 14 de octubre de 2026.
  - Turno mañana: jueves 1 de octubre de 2026, y jueves 8 de octubre de 2026.

Aviso de la cátedra: durante la defensa del TP2 también se hacen una o dos preguntas sobre el **TP1** (clasificación de alumnos con redes neuronales), para evaluar comprensión global de la cursada. Repasar TP1 antes de la defensa, no es parte del código pero sí de la nota.

La asistencia el día de la defensa es obligatoria y forma parte de la evaluación.
