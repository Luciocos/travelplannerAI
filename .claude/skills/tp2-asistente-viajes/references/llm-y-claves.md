# LLM, modelo y rotación de claves

## Proveedor y modelo

Proveedor: **Google Gemini**, vía `langchain-google-genai`.

Modelo por defecto: **`gemini-2.5-flash-lite`**. Es un modelo deliberadamente chico. Razones, en orden:

1. Es el que más cuota da en el tier gratuito (el límite diario de Flash Lite es varias veces el de Flash, y varias veces más el de los modelos Pro).
2. Las tareas del sistema son extracción estructurada de slots, clasificación de intención y redacción de justificaciones cortas sobre texto ya recuperado. Ninguna necesita razonamiento profundo. El trabajo pesado lo hace la recuperación, no el modelo.
3. Menor latencia, que se nota en una demo en vivo.

**El model ID vive en `.env` (`GEMINI_MODEL`), no hardcodeado.** Los IDs y los límites del tier gratuito de Gemini cambian seguido y hay generaciones nuevas de Flash Lite. Antes de cerrar la Fase 0, verificar contra la página oficial de rate limits de Google cuál es el Flash Lite vigente y cuál es su límite diario, y anotar el número real en `estado.md`. No asumir de memoria.

Escalón de fallback, sólo si la calidad no alcanza en alguna tarea puntual: `gemini-2.5-flash`. Se configura por variable, no se cambia el código.

## Rotación de claves

Hay **3 claves de Gemini** disponibles. Cada clave tiene su propia cuota, así que rotarlas multiplica por tres el techo diario efectivo.

### Configuración

```
GEMINI_API_KEY_1=...
GEMINI_API_KEY_2=...
GEMINI_API_KEY_3=...
GEMINI_MODEL=gemini-2.5-flash-lite
LLM_PROVIDER=gemini
```

`config.py` levanta todas las variables que matcheen `GEMINI_API_KEY_\d+`, en orden, y arma la lista. Si no hay ninguna, falla con mensaje claro. La cantidad de claves no está hardcodeada: agregar una cuarta tiene que ser sólo agregar la variable.

### Comportamiento del rotador

`llm.py` expone una factory que devuelve un ChatModel envuelto en un rotador. Reglas:

- **Round robin** entre las claves disponibles, una por request. Distribuye el consumo en vez de quemar la primera clave y recién ahí pasar a la segunda.
- **Ante un 429 o un error de cuota agotada**, marcar esa clave como no disponible y reintentar el mismo request con la siguiente clave, de forma transparente para quien llamó.
- **Distinguir los dos tipos de 429**, porque el manejo correcto es distinto:
  - Límite por minuto (RPM): es transitorio. La clave se marca no disponible por 60 segundos y vuelve sola.
  - Límite diario (RPD): la clave queda muerta hasta el reset de cuota de Google, que es a medianoche hora del Pacífico. No tiene sentido reintentarla en toda la sesión.
  - Si la respuesta de error no permite distinguirlos con certeza, tratar como RPM (más conservador) pero contar los fallos: tres 429 seguidos de la misma clave la degradan a RPD.
- **Si las tres claves están agotadas**, esperar el backoff más corto pendiente y reintentar una vez. Si vuelve a fallar, error explícito que diga cuántas claves hay, cuáles están agotadas y hasta cuándo. Nada de fallar en silencio ni de devolver una respuesta vacía.
- **Logging** de qué clave se usó (por índice, `clave_2`, nunca el valor de la clave) y de cada rotación. En la defensa esto se muestra, es una decisión de arquitectura defendible.

### Higiene de las claves

- Las claves van en `.env`, que está en `.gitignore`. **Nunca en el código, nunca en el notebook, nunca en un output de celda commiteado.**
- En GitHub van como **repository secrets** (`GEMINI_API_KEY_1`, `_2`, `_3`), y sólo las consume el workflow manual de smoke test. Los workflows que corren en pull request no las tocan.
- El notebook nunca imprime la clave, ni siquiera truncada. Si hay que mostrar que la rotación funciona, se imprime el índice.
- El escaneo de secretos en CI (ver `ci-y-git.md`) existe justamente para que una clave pegada por accidente no llegue a `main`.

## Ahorro de cuota, esto importa más de lo que parece

El tier gratuito se agota rápido si cada corrida del notebook rehace todas las llamadas. Tres medidas concretas:

1. **Los embeddings son locales** (`sentence-transformers`), no de Gemini. Embeber los corpus son cientos de llamadas, y no gastar cuota en eso es la razón principal de la elección. Es un argumento de diseño para la defensa, no una casualidad.
2. **Cache de LLM en disco durante el desarrollo:** `set_llm_cache(SQLiteCache(database_path=".cache/llm.sqlite"))` de LangChain. Reejecutar el notebook con los mismos prompts no consume cuota. El archivo de cache va en `.gitignore`.
3. **Ningún test toca la red.** Las llamadas al LLM se mockean. Un CI que consume cuota es un CI que va a dejar al equipo sin cuota justo el día de la entrega.

## Qué anotar en estado.md

Al cerrar la Fase 0: model ID exacto verificado, límite diario real por clave, cantidad de claves activas, y si el cache de LLM quedó habilitado.
