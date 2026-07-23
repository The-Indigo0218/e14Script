# Instrucciones del proyecto

## Restricción por modelo: Haiku nunca escribe en la base de datos

Si el modelo activo de esta sesión es **Haiku**, tiene PROHIBIDO ejecutar
cualquier `INSERT`/`UPDATE`/`DELETE` directo sobre `actas.db` (vía sqlite3,
scripts del proyecto, o cualquier otro medio). Esto incluye correcciones
manuales de votos, eliminar filas, marcar `verificado_manualmente`, etc.

Si una tarea requiere modificar la base de datos (corregir una discrepancia,
eliminar una mesa mal identificada, aplicar un fix tipo A/B de los que se
documentan en notas, etc.), Haiku debe:

1. Hacer todo el trabajo de solo lectura que pueda (leer fotos, diagnosticar,
   preparar el plan de qué cambiar y por qué).
2. Delegar la escritura real a un subagente con `model: "sonnet"` vía la
   herramienta Agent, pasándole el diagnóstico completo (mesa, valores
   correctos, justificación) para que ejecute el cambio.

**Por qué:** esta es una auditoría electoral real (segunda vuelta presidencial
2026, Bolívar). Una escritura incorrecta en la base por una lectura visual
apresurada de un modelo más liviano puede introducir errores en los datos de
la auditoría sin el razonamiento necesario para detectarlos. Las operaciones
de solo lectura (cargar archivos, lanzar OCR, monitorear, generar
comparaciones/Excel) sí son seguras para Haiku.

Esta regla no aplica a Sonnet/Opus — ellos pueden escribir en la DB
directamente cuando el diagnóstico ya está hecho con cuidado.
