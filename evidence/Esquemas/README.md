# Esquemas del sistema

Diagramas de diseño del Proyecto 1 (sección 5.1 del enunciado). Cada esquema
está en dos formatos:

- `.svg`: editable y nítido a cualquier tamaño.
- `.png`: para insertar en el informe (Word) o en la presentación (PowerPoint).

| Archivo | Qué muestra | Dónde usarlo en el informe |
|---|---|---|
| `01-arquitectura` | Clientes TCP, proceso principal (productor), cola, trabajadores con sus hilos, inventario compartido, `inventory_lock` y canales `Pipe` | 4. Arquitectura de la solución |
| `02-jerarquia-procesos` | Árbol de procesos con PID/PPID reales de la corrida concurrente de 1.000 pedidos, hilos de cada proceso y conteo de hilos (12 concurrente, 4 secuencial) | 5. Procesos e hilos |
| `03-productor-consumidor` | `put()` / `get()` / `task_done()`, bloqueo con cola llena o vacía, las 4 etapas del pedido y el cierre con centinelas | 6. Recursos compartidos y 8. Mecanismo de sincronización |
| `04-condicion-de-carrera` | Línea de tiempo antes (`--scenario race`, esperado 98 / real 99) y después (`--scenario safe`, 98 / 98), con los resultados de las pruebas de carga | 7. Problema de concurrencia y 12. Comparación antes/después |
| `05-interbloqueo` | Grafo de espera circular, las 4 condiciones de Coffman y la prevención con orden global de locks | 9. Análisis del interbloqueo |

## Notas para la sustentación

- **Hilos extra:** el servidor tiene 2 hilos (`MainThread` y `QueueFeederThread`,
  que crea `multiprocessing` al hacer el primer `put()`), y cada trabajador tiene su
  `MainThread` más los hilos del pool. Por eso el modo secuencial (1 trabajador ×
  1 hilo) muestra 4 hilos en total.
- **Proceso extra en `pstree`:** `resource_tracker` lo crea `multiprocessing` para
  liberar semáforos y memoria compartida. No es un trabajador.
- **Interbloqueo:** es una demostración aislada con 2 hilos en un proceso hijo. En
  el procesamiento real solo existe `inventory_lock`, y con un único lock no puede
  formarse espera circular.
- Los PID del esquema 02 son de la corrida registrada en
  `evidence/load-tests/results.csv`; en cada ejecución cambian.

## Regenerar los PNG

Si editas un `.svg`, vuelve a exportarlo a PNG con cualquier editor (Inkscape,
navegador + captura) o con `sharp` en Node.js:

```bash
node -e "require('sharp')('01-arquitectura.svg',{density:144}).flatten({background:'#fff'}).png().toFile('01-arquitectura.png')"
```
