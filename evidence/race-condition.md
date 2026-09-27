# Evidencia: condición de carrera en inventario

Fecha: 2026-09-27

## Preparación

Se inició un proceso trabajador con dos hilos y una ventana de carrera ampliada:

```bash
python -m src.main \
  --port 5000 \
  --max-orders 2 \
  --workers 1 \
  --threads-per-worker 2 \
  --processing-delay 1 \
  --scenario race \
  --json
```

En otra terminal se enviaron simultáneamente dos pedidos del mismo producto:

```bash
python -m src.client --port 5000 --order-id ORD-RACE-A \
  --customer-id CLIENTE-A --product-id PRODUCT-001 --quantity 1 &
python -m src.client --port 5000 --order-id ORD-RACE-B \
  --customer-id CLIENTE-B --product-id PRODUCT-001 --quantity 1 &
wait
```

## Resultado observado

Los hilos `worker-1-thread_0` y `worker-1-thread_1` leyeron ambos stock `100` y
registraron stock `99`. El proceso principal comparó el resultado con las dos
unidades facturadas:

```text
Condicion de carrera detectada |
esperado={'PRODUCT-001': 98, 'PRODUCT-002': 100, 'PRODUCT-003': 100}
real={'PRODUCT-001': 99, 'PRODUCT-002': 100, 'PRODUCT-003': 100}
```

La actualización perdida se debe a que leer, calcular y escribir no constituye
una operación atómica. Esta versión no usa exclusión mutua intencionalmente; se
conserva como evidencia previa a la corrección con `Lock`.
