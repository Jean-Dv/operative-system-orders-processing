# Evidencia: interbloqueo por espera circular

Fecha: 2026-09-27

## Ejecución

```bash
python -m src.main \
  --scenario deadlock \
  --deadlock-timeout 0.25 \
  --json
```

## Recursos y orden de adquisición

```text
ORDER-A: inventory_lock → invoice_lock
ORDER-B: invoice_lock   → inventory_lock
```

Una barrera sincroniza los hilos después de adquirir su primer recurso. Así,
ninguno puede obtener el segundo:

```text
ORDER-A (deadlock-order-a) holds inventory_lock and waits for invoice_lock
ORDER-B (deadlock-order-b) holds invoice_lock and waits for inventory_lock
```

## Diagnóstico

```json
{
  "detected": true,
  "mutual_exclusion": true,
  "hold_and_wait": true,
  "no_preemption": true,
  "circular_wait": true
}
```

Los locks no usan timeout: ambos hilos permanecen bloqueados. El escenario corre
en un proceso hijo con hilos daemon para que el detector externo pueda registrar
la evidencia y finalizar el proceso aislado sin congelar la aplicación ni los
tests. La estrategia preventiva se implementará en la fase siguiente.
