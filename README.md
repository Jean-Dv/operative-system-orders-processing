# Centro de procesamiento de pedidos

Simulador académico para estudiar procesos, hilos, concurrencia y
sincronización en Linux. El desarrollo se realiza de forma incremental.

## Estado actual: fase 1

La aplicación separa el sistema de los clientes. El proceso principal permanece
activo, recibe pedidos por TCP, los valida y los registra como pendientes. Cada
cliente es otro proceso que envía un pedido al sistema. El registro sigue siendo
local al proceso principal: todavía no existen trabajadores, memoria compartida
ni procesamiento concurrente interno.

Requisitos: Linux y Python 3.11 o posterior. No se necesitan dependencias
externas.

```bash
python -m src.main
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

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas validan el dominio, el ciclo de vida y tres procesos cliente que
envían pedidos al proceso principal.
