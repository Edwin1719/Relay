# Batch Processing Skill

Apply the same operation to multiple files.

## CRITICAL RULES

1. **NO DESCRIBIR. EJECUTAR.** No digas "voy a crear" o "el contenido sería". Usa `write_file` o `patch_file` directamente.
2. **RUTAS ABSOLUTAS SIEMPRE.** Usa la ruta completa del workspace, nunca rutas relativas.
3. **MUESTRA UN SAMPLE PRIMERO.** Lee 1 archivo, aplica el cambio, enséñalo al usuario, espera confirmación.
4. **VERIFICA AL FINAL.** Después de escribir, usa `list_files` para confirmar que los archivos existen.
5. **NO MEZCLES.** Una sola operación por batch.

## Flujo

**PASO 1** — Descubre archivos con `list_files` o `search`. Excluye node_modules/, dist/, .git/, __pycache__/.

**PASO 2** — Toma 1 archivo de muestra. Léelo. Aplica el cambio. Muestra el resultado al usuario. Pregunta: "¿Procedo con los demás?"

**PASO 3** — Si el usuario confirma: aplica el cambio a cada archivo restante usando `write_file` con **ruta absoluta**. Reporta éxito/fallo por cada uno.

**PASO 4** — Lista los archivos modificados con `list_files` para verificar que todos existen.

**PASO DE SEGURIDAD**: Si más del 30% falla, detente y reporta.
