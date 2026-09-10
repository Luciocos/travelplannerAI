# Git y CI

## Regla de commits, prioritaria

**Ningún commit lleva coautoría.** Prohibido, en cualquier commit de este repo:

- El trailer `Co-Authored-By: Claude <noreply@anthropic.com>`, o cualquier otro trailer `Co-Authored-By`.
- La línea `🤖 Generated with Claude Code` o equivalente.
- Cualquier referencia a la herramienta que generó el código, en el mensaje o en el cuerpo del commit.

El autor del commit es el usuario, con su configuración de `git config user.name` y `user.email`. El historial del repo es parte de la entrega de un trabajo universitario, y un trailer de coautoría de una herramienta es exactamente lo que no tiene que aparecer ahí.

La regla se hace cumplir por tres vías, porque olvidarse es fácil:

1. Disciplina al escribir el mensaje.
2. Un hook local `commit-msg` que rechaza el commit (ver más abajo).
3. Un job de CI que revisa los mensajes de los commits del pull request.

## Formato de mensaje

`tipo(alcance): descripción en minúscula, imperativo, sin punto final`

Tipos permitidos:

| Tipo | Cuándo |
|------|--------|
| `feat` | funcionalidad nueva |
| `fix` | corrección de un bug |
| `docs` | documentación, README, DECISIONES, DIFICULTADES |
| `test` | tests nuevos o corregidos |
| `refactor` | cambio de código sin cambio de comportamiento |
| `data` | corpus, curaduría manual, datos de referencia |
| `ci` | workflows, hooks, configuración de CI |
| `chore` | dependencias, configuración, tareas de mantenimiento |

Nota: el tipo canónico para una corrección es `fix`, no `bugfix`. Es lo que entienden las herramientas de conventional commits, y mantiene el set corto.

Alcances habituales: `ingesta`, `rag`, `tools`, `agente`, `db`, `llm`, `notebook`, `ci`, `docs`.

Ejemplos:

```
feat(ingesta): cliente de OpenTripMap en dos pasos
feat(llm): rotador round robin de claves de Gemini con failover por 429
fix(tools): evitar que completar_slots pise un slot cargado con None
data(rag): curaduría manual de 12 comercios de Salta
test(rag): verificar filtro por destino antes de la busqueda semantica
docs(decisiones): registrar por que pgvector y no Chroma
ci: workflow de tests con postgres y pgvector como service
```

## Cadencia de commits

Commitear **cada unidad de trabajo terminada**, no una vez por fase. Una unidad es un archivo o un conjunto chico de archivos que deja el repo en un estado coherente: un módulo nuevo, un bug corregido, un lote de datos curados, un documento actualizado.

Criterio práctico: si el mensaje del commit necesita una `y` para describir lo que hace, son dos commits.

Cada fase cerrada termina con un commit de documentación que actualiza `.claude/skills/tp2-asistente-viajes/references/estado.md` y `docs/DECISIONES.md`.

## Ramas

- `main` protegida, no se commitea directo.
- Una rama por fase: `fase/0-scaffolding`, `fase/1-ingesta`, y así.
- Merge a `main` al cerrar la fase, con el CI en verde. Preferir merge commit para que quede visible el bloque de trabajo de cada fase en el historial.

## Hook local que bloquea la coautoría

`.githooks/commit-msg`, versionado en el repo:

```bash
#!/usr/bin/env bash
mensaje_archivo="$1"

if grep -qiE '^Co-Authored-By:' "$mensaje_archivo"; then
    echo "ERROR: este repo no admite trailers Co-Authored-By." >&2
    exit 1
fi

if grep -qiE 'generated with|claude code|noreply@anthropic' "$mensaje_archivo"; then
    echo "ERROR: el mensaje menciona la herramienta generadora. Sacalo." >&2
    exit 1
fi

primera_linea=$(head -n 1 "$mensaje_archivo")
if ! echo "$primera_linea" | grep -qE '^(feat|fix|docs|test|refactor|data|ci|chore)(\([a-z-]+\))?: .+'; then
    echo "ERROR: formato invalido. Usar: tipo(alcance): descripcion" >&2
    echo "Tipos: feat, fix, docs, test, refactor, data, ci, chore" >&2
    exit 1
fi
```

Se activa una sola vez, en la Fase 0:

```bash
chmod +x .githooks/commit-msg
git config core.hooksPath .githooks
```

El `git config` es local a cada clon, así que el README tiene que decirlo para el resto del equipo.

## Workflows de CI

Los cuatro archivos están en `assets/workflows/` de esta skill, listos para copiar a `.github/workflows/`.

| Workflow | Dispara | Qué hace |
|----------|---------|----------|
| `ci.yml` | push a cualquier rama, PR a `main` | lint con ruff, formato, tests con Postgres y pgvector como service container |
| `commits.yml` | PR a `main` | valida el formato de los mensajes y rechaza cualquier trailer de coautoría |
| `secretos.yml` | push, PR | escaneo de secretos con gitleaks, más un guard explícito contra claves de Gemini |
| `smoke-llm.yml` | manual (`workflow_dispatch`) | única cosa que usa las claves reales, verifica que la rotación funciona contra la API |

Principios de este CI:

- **Ningún workflow automático consume cuota de Gemini.** Los tests mockean el LLM. La verificación real contra la API es manual y explícita, y por eso vive en su propio workflow.
- Los secretos (`GEMINI_API_KEY_1`, `_2`, `_3`) se cargan como repository secrets y sólo los lee `smoke-llm.yml`.
- El CI corre Postgres con pgvector de verdad, no un mock. La consulta de similitud con filtro por metadata es el corazón del sistema y tiene que estar cubierta por un test que la ejecute contra una base real.
- Los tests que necesitan base se marcan con `@pytest.mark.db` para poder correr el resto sin Docker en local.

## Protección de main, configurar a mano en GitHub

En Settings, Branches, agregar regla para `main`:

- Require a pull request before merging.
- Require status checks to pass: `calidad`, `commits`, `secretos`.
- Do not allow bypassing the above settings, salvo que trabajar así te trabe con el grupo.
