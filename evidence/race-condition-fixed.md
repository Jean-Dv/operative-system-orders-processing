# Evidencia: corrección de la condición de carrera

Fecha: 2026-09-27

Se repitieron los dos pedidos concurrentes de `PRODUCT-001` usados en la prueba
insegura, cambiando únicamente `--scenario race` por `--scenario safe`:

```bash
python -m src.main \
  --port 5000 \
  --max-orders 2 \
  --workers 1 \
  --threads-per-worker 2 \
  --processing-delay 1 \
  --scenario safe \
  --json
```

## Resultado observado

Los hilos comenzaron concurrentemente, pero actualizaron inventario dentro de la
sección crítica protegida:

```text
worker-1-thread_0 | previous_stock=100 current_stock=99 mutex=lock
worker-1-thread_1 | previous_stock=99 current_stock=98 mutex=lock

Exclusion mutua verificada |
esperado={'PRODUCT-001': 98, 'PRODUCT-002': 100, 'PRODUCT-003': 100}
real={'PRODUCT-001': 98, 'PRODUCT-002': 100, 'PRODUCT-003': 100}
```

El resumen estructurado confirmó `lock_enabled=true` y `race_detected=false`.
El `Lock` serializa únicamente la actualización del inventario; validación,
facturación y preparación de despacho continúan ejecutándose concurrentemente.
