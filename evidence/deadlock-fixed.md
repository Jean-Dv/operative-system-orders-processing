# Evidencia: prevención del interbloqueo

Fecha: 2026-09-27

## Estrategia

Se definió el orden global `inventory_lock → invoice_lock`. Tanto `ORDER-A` como
`ORDER-B` deben respetarlo, independientemente de la operación que realizan.
Esto elimina la espera circular: ningún hilo puede conservar factura mientras
espera inventario.

## Ejecución

```bash
python -m src.main \
  --scenario deadlock-safe \
  --deadlock-timeout 0.25 \
  --json
```

## Resultado observado

```text
Interbloqueo evitado=True |
estrategia=global_lock_order |
orden=inventory_lock->invoice_lock
```

```json
{
  "prevented": true,
  "strategy": "global_lock_order",
  "acquisition_order": ["inventory_lock", "invoice_lock"],
  "completed_orders": ["ORDER-A", "ORDER-B"],
  "deadlock_detected": false,
  "circular_wait": false
}
```

El timeout solo limita cuánto espera el detector por la finalización de la
simulación; los locks se adquieren de forma bloqueante. Ambos pedidos completan
porque siguen el mismo orden, no porque una adquisición expire.
