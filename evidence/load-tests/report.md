# Resultados de pruebas concurrentes

Fecha: 2026-09-27

Se probaron 100, 500, 1000 pedidos con hasta 100 clientes TCP
concurrentes. CPU y memoria corresponden a la suma del proceso principal y sus
procesos trabajadores en cada muestra.

| Escenario | Pedidos | Total s | Aceptación req/s | Completados/s | p95 ms | CPU pico % | RSS pico MB | Hilos pico | Actualizaciones perdidas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sequential | 100 | 0.586 | 3169.92 | 170.68 | 20.834 | 124.9 | 46.2 | 4 | 0 |
| sequential | 500 | 2.628 | 346.11 | 190.28 | 479.956 | 147.0 | 46.8 | 4 | 0 |
| sequential | 1000 | 4.825 | 261.24 | 207.24 | 495.856 | 126.1 | 48.3 | 4 | 0 |
| concurrent | 100 | 0.157 | 3258.59 | 638.64 | 19.978 | 148.0 | 68.9 | 12 | 0 |
| concurrent | 500 | 0.365 | 2589.84 | 1371.49 | 62.487 | 146.3 | 70.0 | 12 | 0 |
| concurrent | 1000 | 0.68 | 1944.84 | 1470.54 | 62.13 | 152.6 | 71.2 | 12 | 0 |
| race | 100 | 0.157 | 3482.49 | 636.15 | 17.831 | 135.9 | 69.4 | 12 | 75 |
| race | 500 | 0.52 | 1829.84 | 961.44 | 88.848 | 152.6 | 69.8 | 12 | 396 |
| race | 1000 | 0.938 | 1421.95 | 1066.16 | 90.246 | 151.2 | 72.7 | 12 | 827 |
| mutex | 100 | 0.312 | 3608.7 | 320.19 | 16.033 | 151.2 | 68.9 | 12 | 0 |
| mutex | 500 | 1.145 | 784.76 | 436.83 | 211.517 | 152.6 | 71.0 | 12 | 0 |
| mutex | 1000 | 2.184 | 592.42 | 457.84 | 211.08 | 154.9 | 72.5 | 12 | 0 |


## Interbloqueo

El interbloqueo usa dos pedidos porque esa es la cantidad mínima suficiente para
detener todo progreso. Se ejecutaron el escenario circular y la versión con
orden global de locks; los resultados estructurados están en `summary.json`.

## Reproducción

```bash
python scripts/run_experiments.py --quantities 100 500 1000 --concurrency 100
```
