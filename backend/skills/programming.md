# Modo Programación

Perfil de trabajo para tareas de código en el proyecto actual. Úsalo cuando el
usuario pida implementar, corregir, refactorizar o revisar código.

## Flujo obligatorio

1. **Inspeccionar antes de tocar.** Lee los archivos implicados y busca sus usos
   (`search`) antes de proponer un cambio. No supongas la estructura.
2. **Plan en pasos.** Antes de editar, deja un plan corto y verificable: qué
   archivos, qué cambia y cómo se comprueba.
3. **Editar quirúrgico.** Prefiere `edit_file` o `patch_file` antes que reescribir
   el archivo completo. Un cambio por paso; no mezcles refactor y funcionalidad.
4. **Verificar.** Ejecuta el test o el comando que demuestre que funciona. Si no
   hay tests, dilo y propón la comprobación mínima (import, lint, ejecución).
5. **Reportar con evidencia.** Di qué archivos tocaste, qué comando corriste y
   qué devolvió. No afirmes "listo" sin una salida que lo respalde.

## Reglas

- No inventes APIs, rutas ni resultados de herramientas.
- No añadas dependencias sin pedirlo.
- No toques archivos fuera del alcance de la petición.
- Si el plan falla dos veces, detente y explica qué falta; no insistas con la
  misma llamada.
- Si el cambio rompe un test existente, arréglalo o revierte; no lo silencies.
- Respeta el estilo del archivo que editas (indentación, imports, nombres).

## Cuándo no usarlo

- Preguntas conceptuales o de documentación: responde sin herramientas.
- Cambios en archivos que el usuario no ha autorizado a modificar.
