# Centro de procesamiento de pedidos

Simulador académico para estudiar procesos, hilos, concurrencia y
sincronización en Linux. El desarrollo se realiza de forma incremental.

## Estado actual: fase 9

La aplicación separa el sistema de los clientes. El proceso principal recibe
pedidos por TCP, los valida y actúa como productor al insertarlos en una
`multiprocessing.JoinableQueue`. Los procesos trabajadores compiten como
consumidores y entregan cada pedido a su pool de hilos. El registro permanece en
el proceso principal.

El inventario utiliza un `multiprocessing.RawArray` único: el proceso principal,
los trabajadores y sus hilos observan los mismos valores. Un
`multiprocessing.Lock` protege toda actualización de inventario en los modos
`normal` y `safe`. El modo `race` conserva la versión insegura como evidencia.

Cada trabajador ejecuta el pipeline completo:

1. valida que el producto exista;
2. comprueba y descuenta inventario;
3. genera una factura con el total del pedido;
4. genera una guía y deja el pedido listo para despacho.

Requisitos: Linux y Python 3.11 o posterior. No se necesitan dependencias
externas.

```bash
python -m src.main \
  --workers 2 \
  --threads-per-worker 2 \
  --queue-capacity 100 \
  --processing-delay 2
```

En otras terminales se pueden ejecutar uno o varios clientes:

```bash
python -m src.client \
  --customer-id CUSTOMER-001 \
  --product-id PRODUCT-001 \
  --quantity 2
```

El sistema escucha en `127.0.0.1:5000` y permanece activo hasta recibir
`Ctrl+C`. `--host` y `--port` permiten cambiar la dirección. Para demostraciones
automatizadas, `--max-orders N` hace que termine después de aceptar `N` pedidos.

Por cada solicitud, la terminal del sistema muestra su avance real:

```text
Cliente conectado | ip=127.0.0.1 puerto=54321
Pedido recibido | id=ORD-... cliente=CUSTOMER-001 producto=PRODUCT-001 cantidad=2
Validacion completada | id=ORD-... resultado=correcto
Pedido producido | productor=servidor cola=pedidos id=ORD-...
Pedido consumido | worker=1 pedido=ORD-...
Procesamiento iniciado | worker=1 hilo=worker-1-thread_0 pedido=ORD-...
Etapa finalizada | worker=1 hilo=worker-1-thread_0 pedido=ORD-... etapa=validation
Etapa finalizada | worker=1 hilo=worker-1-thread_0 pedido=ORD-... etapa=inventory_update previous_stock=100 current_stock=98
Etapa finalizada | worker=1 hilo=worker-1-thread_0 pedido=ORD-... etapa=invoice_generation invoice_id=INV-ORD-...
Etapa finalizada | worker=1 hilo=worker-1-thread_0 pedido=ORD-... etapa=dispatch_preparation status=ready_for_dispatch
Procesamiento finalizado | worker=1 pedido=ORD-... estado=ready_for_dispatch
```

Con dos trabajadores y dos hilos por trabajador pueden ejecutarse hasta cuatro
pedidos al mismo tiempo. El PID identifica el proceso y `hilo`/`THREAD` identifica
el hilo que atiende cada pedido. La demora puede cambiarse para observar mejor
el solapamiento:

```bash
python -m src.main --processing-delay 5
```

## Cola productor-consumidor

- **Productor:** el proceso principal ejecuta `queue.put(order)` después de
  validar y registrar la solicitud.
- **Búfer:** una `JoinableQueue` con capacidad configurable mediante
  `--queue-capacity` aplica espera al productor cuando está llena.
- **Consumidores:** los procesos trabajadores ejecutan `queue.get()` y delegan
  el pedido a un hilo disponible.
- **Finalización:** el hilo llama `task_done()` al terminar. El administrador usa
  `queue.join()` y envía un centinela por consumidor durante el cierre.

El cliente confirma que el pedido fue encolado; el consumidor concreto se conoce
cuando aparece `Pedido consumido` en las trazas del sistema.

## Demostración de interbloqueo

El escenario `deadlock` modela dos pedidos y dos recursos adquiridos en orden
inverso:

```text
ORDER-A conserva inventory_lock y espera invoice_lock
ORDER-B conserva invoice_lock y espera inventory_lock
```

Ejecútelo sin iniciar clientes ni el servidor TCP:

```bash
python -m src.main \
  --scenario deadlock \
  --deadlock-timeout 0.25 \
  --json
```

Los hilos se bloquean realmente al adquirir el segundo recurso. La simulación se
ejecuta en un proceso hijo aislado; el timeout solo permite al proceso padre
diagnosticar y finalizar la demostración.

El diagnóstico informa exclusión mutua, retención y espera, ausencia de
expropiación y espera circular: las cuatro condiciones de Coffman.

## Prevención del interbloqueo

La estrategia elegida es un **orden global de adquisición**. Todos los hilos
solicitan los recursos en esta secuencia:

```text
inventory_lock → invoice_lock
```

Como ningún hilo puede adquirir `invoice_lock` primero y después esperar
`inventory_lock`, se elimina la espera circular. Los locks continúan garantizando
exclusión mutua y no se depende de timeouts para completar los pedidos.

Ejecute la comparación corregida:

```bash
python -m src.main \
  --scenario deadlock-safe \
  --deadlock-timeout 0.25 \
  --json
```

El resultado debe indicar los dos pedidos completados, `prevented=true`,
`deadlock_detected=false` y `circular_wait=false`.

La demora indicada se reparte entre las cuatro etapas. Todos los trabajadores
acceden al mismo inventario. El modo predeterminado `normal` utiliza exclusión
mutua sin ampliar artificialmente la ventana de carrera.

## Demostración de la condición de carrera

Ejecute un proceso con dos hilos y amplíe la operación insegura mediante el
escenario `race`:

```bash
python -m src.main \
  --workers 1 \
  --threads-per-worker 2 \
  --scenario race \
  --processing-delay 2
```

Envíe simultáneamente dos pedidos de una unidad para `PRODUCT-001`. Ambos hilos
pueden leer stock `100` y escribir `99`. El resultado correcto sería `98`, por
lo que al cerrar el sistema se obtiene una evidencia como:

```text
Condicion de carrera detectada | esperado={'PRODUCT-001': 98, ...} real={'PRODUCT-001': 99, ...}
```

## Corrección con exclusión mutua

El escenario `safe` conserva la misma ventana ampliada, pero protege la secuencia
leer-validar-calcular-escribir con un único `Lock` compartido:

```bash
python -m src.main \
  --workers 1 \
  --threads-per-worker 2 \
  --scenario safe \
  --processing-delay 2
```

Para los mismos dos pedidos, las trazas muestran `100 → 99` y después `99 → 98`:

```text
Exclusion mutua verificada | esperado={'PRODUCT-001': 98, ...} real={'PRODUCT-001': 98, ...}
```

Al detener el sistema, los trabajadores devuelven los resultados por canales
`Pipe` reservados para control. El proceso principal consolida entonces los
estados finales `ready_for_dispatch` o `rejected` antes de imprimir el resumen.

En Linux, la jerarquía puede observarse mientras el sistema está activo:

```bash
pstree -p <PID_DEL_SISTEMA>
ps -o pid,ppid,stat,cmd --ppid <PID_DEL_SISTEMA>
```

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas verifican la cola, los escenarios `race`/`safe`, la detección del
interbloqueo y su prevención mediante orden global de recursos.
