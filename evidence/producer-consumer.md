# Evidencia: cola productor-consumidor

Fecha: 2026-09-27

Se inició el sistema con una cola compartida, dos consumidores y un hilo por
consumidor:

```bash
python -m src.main \
  --port 5000 \
  --max-orders 4 \
  --workers 2 \
  --threads-per-worker 1 \
  --queue-capacity 10 \
  --processing-delay 1 \
  --json
```

Cuatro clientes enviaron pedidos simultáneamente. El proceso principal produjo
los cuatro elementos antes de que terminara el primer lote:

```text
Pedido producido | cola=pedidos id=ORD-QUEUE-2
Pedido consumido | worker=1 pedido=ORD-QUEUE-2
Pedido producido | cola=pedidos id=ORD-QUEUE-3
Pedido consumido | worker=2 pedido=ORD-QUEUE-3
Pedido producido | cola=pedidos id=ORD-QUEUE-1
Pedido producido | cola=pedidos id=ORD-QUEUE-4
```

Cuando finalizaron los primeros pedidos, los consumidores retiraron los dos
restantes:

```text
Pedido consumido | worker=1 pedido=ORD-QUEUE-1
Pedido consumido | worker=2 pedido=ORD-QUEUE-4
```

El resumen final registró cuatro pedidos `ready_for_dispatch`. El cierre después
de completar todos los elementos evidencia el uso de `task_done()` y
`JoinableQueue.join()`; un centinela por trabajador detuvo los consumidores.
