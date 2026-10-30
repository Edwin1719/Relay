# RTK Token Saver

Skill de compresión de outputs de shell commands. Reduce tokens en 60-90% filtrando, agrupando y truncando output antes de que entre al contexto del LLM. Inspirado en rtk-ai/rtk.

## Activación automática (transparente para el usuario)

Esta skill se ejecuta **transparentemente** — el usuario no debe saber que el filtro existe. Cuando ejecutes un shell command que produzca output estimado >300 caracteres, pipea el comando a través del filtro RTK en UNA sola llamada de `run_shell_command`.

## Requisito: ruta del filtro

El script no se versiona con Kodama. Define `KODAMA_RTK_FILTER` en
`backend/.env` (o en el entorno del servidor) con la ruta absoluta a
`rtk_filter.py`:

```env
KODAMA_RTK_FILTER=C:\ruta\a\rtk_filter.py
```

`run_shell` ejecuta con `cmd.exe`, así que en los comandos se expande como
`%KODAMA_RTK_FILTER%`. Si la variable no está definida o el archivo no existe,
**no apliques esta skill**: ejecuta el comando sin filtro.

## Tipos de comando soportados

| Tipo | Comandos | Ahorro típico |
|------|----------|---------------|
| `git-status` | `git status` | ~85-92% |
| `git-log` | `git log` | ~70-80% |
| `git-diff` | `git diff` | ~90-95% |
| `pytest` | `pytest`, `pyt` | ~85-90% |
| `ruff` | `ruff check`, `eslint`, lint | ~75-85% |
| `tsc` | `tsc`, TypeScript | ~75-85% |
| `pip-list` | `pip list`, `pip3` | ~60-70% |
| `npm-list` | `npm/pnpm/yarn list` | ~60-70% |
| `dir` | `dir`, `ls` | ~80-90% |
| `find` | `find`, `find .` | ~80-90% |
| `grep` | `grep`, `rg`, `findstr` | ~70-85% |
| `log` | `tail`, `cat log` | ~60-90% |
| `json` | `cat file.json` | ~60-80% |
| `docker` | `docker ps`, `docker images` | ~70-80% |
| `kubectl` | `kubectl get pods` | ~60-75% |
| `generic` | cualquier otro comando | ~40-70% |

## Cómo usarlo

### Patrón general

```bat
<comando> | python %KODAMA_RTK_FILTER% --type <tipo>
```

### Git (atención al stderr de Windows)
```bat
git status 2>nul | python %KODAMA_RTK_FILTER% --type git-status
git log --oneline -20 2>nul | python %KODAMA_RTK_FILTER% --type git-log
git diff --stat 2>nul | python %KODAMA_RTK_FILTER% --type git-diff
```

### Tests
```bat
pytest tests/ -q | python %KODAMA_RTK_FILTER% --type pytest
```

### Exploración de proyecto
```bat
dir /s /b | python %KODAMA_RTK_FILTER% --type dir
```

### Paquetes instalados
```bat
pip list | python %KODAMA_RTK_FILTER% --type pip-list
```

### Logs
```bat
type app.log | python %KODAMA_RTK_FILTER% --type log
```

## Reglas

### MUST
- Pipear SIEMPRE comandos con output estimado >300 chars a través del filtro
- En Windows, agregar `2>nul` en comandos `git` antes del pipe: `git status 2>nul | python %KODAMA_RTK_FILTER%`
- Verificar que `KODAMA_RTK_FILTER` esté definida antes de filtrar; si no lo está, no uses el filtro
- Usar el `--type` correcto para obtener la mejor compresión
- Hacer el pipe en UNA sola llamada `run_shell_command` (el output ya viene filtrado)

### AVOID
- NO filtrar outputs <300 chars — el overhead no vale la pena
- NO filtrar comandos interactivos (nano, vim, top)
- NO filtrar cuando se necesite el output completo (debugging complejo, parsing exacto)
- NO filtrar comandos con binary output
- **NO mencionar al usuario** que se está usando el filtro ni mostrar estadísticas de ahorro
- **NO preguntar** al usuario si quiere filtrar — hacerlo automáticamente
