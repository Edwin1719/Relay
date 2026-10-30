# Scheduled Automation Skill

Programa tareas recurrentes en Windows con `schtasks.exe`.

## CRITICAL RULES

1. **RUTAS ABSOLUTAS SIEMPRE.** El script debe escribirse en el workspace con ruta completa. La ruta de salida del log debe ser absoluta.
2. **VERIFICA EL SCRIPT.** Antes de programar la tarea: ejecuta el script una vez con `run_shell` para confirmar que funciona.
3. **VERIFICA LA TAREA.** Después de `schtasks /CREATE`, ejecuta `schtasks /QUERY /TN "Kodama\..."` para confirmar.
4. **NO ASUMAS.** Si un comando falla, muestra el error al usuario. No digas "se creó correctamente" sin verificar.

## Flujo

**PASO 1** — Escribe el script `.py` en el workspace usando `write_file` con ruta absoluta. El script debe:
   - Usar rutas absolutas para archivos de salida
   - Incluir logging con timestamp
   - Probarse con `python.exe` real (no el stub de la Tienda)

**PASO 2** — Ejecuta el script con la ruta completa:
   ```
   <ruta-a-python.exe> C:\ruta\completa\script.py
   ```
   Si falla, busca Python con `where python` y usa la ruta real, no el alias.

**PASO 3** — Programa con `schtasks /CREATE /SC MINUTE /MO 30 /TN "Kodama\Nombre" /TR "ruta completa del comando" /F`

**PASO 4** — Verifica con `schtasks /QUERY /TN "Kodama\Nombre" /V`. Muestra el resultado al usuario.

**PASO 5** — Confirma con el usuario cuándo cancelar o si quiere que se ejecute ahora.
