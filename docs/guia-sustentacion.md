# Guía de sustentación: Proyecto 1

Material de apoyo para la presentación y la demostración en vivo. La presentación
es `presentacion-procesamiento-pedidos-uptc.pptx` (21 diapositivas, con notas del
orador) y el informe es `informe-tecnico-proyecto1.docx`.

## Antes de entrar

1. En la máquina virtual Debian: `cd ~/operative-system-orders-processing && git pull`.
2. Abrir 3 pestañas de terminal (Ctrl+Shift+T), todas en la carpeta del proyecto:
   **T1** sistema, **T2** clientes, **T3** observación.
3. Comprobar que nada ocupe el puerto: `ss -ltnp | grep 5000` no debe mostrar nada.
4. Tener abiertas las capturas de `evidence/Capturas/` como respaldo por si la
   demostración falla.

## Demostración en vivo (unos 8 minutos)

### 1. Procesos e hilos (2 min)

T1:

```bash
python3 -m src.main --workers 2 --threads-per-worker 4 --processing-delay 60
```

T2:

```bash
for i in $(seq 1 8); do python3 -m src.client --customer-id C-$i --product-id PRODUCT-001 --quantity 1 & done; wait
```

T3 (cambiar `PID` por el que muestra T1):

```bash
pstree -p PID
```

Qué decir: el servidor es padre de los dos trabajadores y del `resource_tracker`;
cada trabajador tiene 4 hilos entre llaves. Detener T1 con Ctrl+C.

### 2. Condición de carrera y corrección (3 min)

T1, con el error:

```bash
python3 -m src.main --workers 1 --threads-per-worker 2 --processing-delay 1 --scenario race --max-orders 2 2>&1 | grep -E "System ready|inventory_update|Condicion|Exclusion|stopped"
```

T2:

```bash
for i in A B; do python3 -m src.client --customer-id C-$i --product-id PRODUCT-001 --quantity 1 & done; wait
```

Qué decir: los dos hilos leen 100 y escriben 99; esperado 98, real 99. Repetir
con `--scenario safe`: 100 → 99 y 99 → 98, exclusión mutua verificada.

### 3. Interbloqueo y prevención (3 min)

T1:

```bash
python3 -m src.main --scenario deadlock --deadlock-timeout 20
```

T3, mientras está congelado:

```bash
DSRV=$(pgrep -f "scenario deadlock" | head -1); DCH=$(pgrep -P $DSRV -f spawn_main); ps -L -o pid,lwp,stat,wchan:22,pcpu,cmd:40 -p $DCH
```

Qué decir: los hilos duermen en `futex_wait_queue` con 0 % de CPU. Al terminar,
T1 muestra las 4 condiciones de Coffman en `true`. Luego:

```bash
python3 -m src.main --scenario deadlock-safe
```

Ambos pedidos terminan al instante.

## Preguntas probables y respuestas

**¿Por qué usaron procesos y además hilos?**
Por el GIL de CPython: los hilos de un mismo proceso no ejecutan código Python a
la vez, así que el paralelismo real lo dan los procesos (cada uno con su propio
intérprete). Los hilos sirven para solapar las esperas dentro de cada trabajador.

**¿Por qué el modo secuencial muestra 4 hilos si configuraron 1?**
El servidor tiene 2 (hilo principal y `QueueFeederThread` de la cola) y el
trabajador tiene 2 (hilo principal que consume de la cola y 1 hilo del pool).

**¿Qué es el proceso Python extra que aparece en `pstree`?**
El `resource_tracker` de `multiprocessing`: libera semáforos y memoria compartida
al terminar. No procesa pedidos.

**¿Por qué la CPU pasa de 100 %?**
Es la suma de varios procesos ejecutándose a la vez en distintos núcleos. Es la
evidencia del paralelismo.

**¿Cómo evitan los pedidos duplicados?**
`queue.get()` es atómico: cada pedido lo recibe un único consumidor. Además, el
servidor rechaza un `order_id` repetido.

**¿El interbloqueo puede pasar en su sistema real?**
No. El procesamiento real usa un solo lock (`inventory_lock`) y con un único
recurso no puede formarse una espera circular. La demostración modela qué pasaría
si se agregara un segundo recurso compartido sin una política de orden.

**¿Por qué orden global y no timeouts?**
El orden global elimina la espera circular sin depender del tiempo. Los timeouts
rompen la retención y espera, pero introducen reintentos y pueden provocar que los
hilos se cedan el paso indefinidamente.

**¿Cuánto cuesta el lock?**
Con 1.000 pedidos sobre un mismo producto, el rendimiento baja de 1.066 a 458
pedidos/s, pero las actualizaciones perdidas pasan de 827 a 0.

**¿Por qué la memoria no crece con más pedidos?**
Depende del número de procesos (unos 18 a 23 MB por intérprete), no de los
pedidos: estos no se acumulan en memoria.

**¿Qué hace `spawn` y por qué los trabajadores aparecen como `spawn_main`?**
`spawn` arranca un intérprete nuevo para cada trabajador en lugar de copiar el
proceso padre (`fork`); por eso su comando en `ps` es
`python3 -c from multiprocessing.spawn import spawn_main`.

## Reparto sugerido de la exposición

| Integrante | Diapositivas |
|---|---|
| Daniel Santiago Espinosa Castro | 1 a 8: problema, arquitectura, diseño y evidencia de procesos e hilos |
| Jean Carlos Valencia Barajas | 9 a 14: rendimiento, cola y condición de carrera |
| Maria Camila Figueredo Molano | 15 a 21: interbloqueo, síntomas, reproducción y conclusiones |

Ajustar el reparto según lo que acuerde el equipo.
