# Centro de procesamiento de pedidos

Simulador académico para estudiar procesos, hilos, concurrencia y
sincronización en Linux. El desarrollo se realiza de forma incremental.

## Estado actual: fases 4 y 5

La aplicación separa el sistema de los clientes. El proceso principal recibe
pedidos por TCP, los valida, los registra y los asigna en round-robin a procesos
trabajadores persistentes. Dentro de cada trabajador, un pool de hilos permite
procesar varios pedidos concurrentemente. El registro sigue siendo local al
proceso principal.

El inventario utiliza un `multiprocessing.RawArray` único: el proceso principal,
los trabajadores y sus hilos observan los mismos valores. La actualización es
intencionalmente insegura para demostrar una condición de carrera antes de
corregirla con exclusión mutua.

Cada trabajador ejecuta el pipeline completo:

1. valida que el producto exista;
2. comprueba y descuenta inventario;
3. genera una factura con el total del pedido;
4. genera una guía y deja el pedido listo para despacho.

Requisitos: Linux y Python 3.11 o posterior. No se necesitan dependencias
externas.

```bash
python -m src.main --workers 2 --threads-per-worker 2 --processing-delay 2
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
Pedido asignado | id=ORD-... worker=1 worker_pid=1235 total_pendientes=1
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

La demora indicada se reparte entre las cuatro etapas. Todos los trabajadores
acceden al mismo inventario. El modo normal no amplía artificialmente la ventana
de carrera, pero todavía carece de bloqueo.

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

No se utiliza `Lock` todavía; la exclusión mutua corresponde a la fase siguiente.

Al detener el sistema, los trabajadores devuelven los resultados por sus canales
`Pipe`. El proceso principal consolida entonces los estados finales
`ready_for_dispatch` o `rejected` antes de imprimir el resumen.

En Linux, la jerarquía puede observarse mientras el sistema está activo:

```bash
pstree -p <PID_DEL_SISTEMA>
ps -o pid,ppid,stat,cmd --ppid <PID_DEL_SISTEMA>
```

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas validan el dominio, los procesos e hilos, la visibilidad del
inventario compartido y la pérdida reproducible de una actualización.
