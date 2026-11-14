# Estudio: Metrica Sports y cómo replicarlo con código abierto

> Alcance: la parte de **vídeo táctico**. Se basa en información pública (centro de ayuda de Metrica, prensa especializada, artículos académicos y repositorios de GitHub) y en pruebas propias con sus datos abiertos. Lo que no es público (su pipeline interno) se marca como *no conocido*.

## 1. Qué ofrece Metrica Sports (según su web)
| Producto | Para qué sirve |
|---|---|
| **PlayBase** (antes *Play*) | Gestión de vídeo, etiquetado/codificación de eventos, dibujo sobre vídeo y análisis. Pensado para clubes sin analista de datos; funciona con cualquier tipo de vídeo (retransmisión, cámara táctica, grabación manual, dron). |
| **Nexus** | Versión para élite: eventos, códigos, etiquetas y secuencias, análisis en tiempo real y conexión con datos de terceros. |
| **GameCloud** | Servicio en la nube de **datos de seguimiento automáticos (ATD)** a partir de vídeo: reconoce a los jugadores de cada equipo, el campo y el balón. |
| **Datos abiertos** | Tres partidos anonimizados con seguimiento y eventos sincronizados (`github.com/metrica-sports/sample-data`). |

**Tecnología — lo que no sabemos:** Metrica no publica cómo funciona GameCloud (modelos, datos de entrenamiento, calibración). Todo lo que sigue sobre «cómo se hace» sale de la literatura abierta, no de ellos.

## 2. Mapa de funcionalidades
| Funcionalidad | Equivalente abierto | Qué tenemos | Hueco |
|---|---|---|---|
| Seguimiento automático desde vídeo | Detectores YOLO + ByteTrack; `SoccerNet/sn-gamestate` (TrackLab) | `football-vision-analyzer` (detector, ByteTrack, equipos, homografía, API, React) | IDs estables en partido completo (ver §4) |
| Calibración del campo | Modelos de puntos clave del campo (`roboflow/sports`, MIT, con conjuntos de datos en Roboflow Universe); NBJW / PnLCalib en `sn-gamestate` | Calibración **manual** con ≥ 4 marcas (cámara fija) | Calibración automática y cámara móvil |
| Equipo por camiseta | Embeddings (SigLIP) + UMAP + K-Means (`roboflow/sports`) | K-Means sobre color LAB del torso | Más robusto con embeddings |
| Dorsales / reidentificación | Retos abiertos (los reconoce el propio `roboflow/sports`) | — | Pendiente |
| Eventos desde vídeo | Investigación (*ball action spotting*, SoccerNet) | Eventos de StatsBomb cruzados con el vídeo | — |
| Analítica sobre seguimiento | `floodlight`, `kloppy`, `mplsoccer` | Hub: calor, distancia/velocidad, forma, **control del espacio**, **líneas**, **fases de posesión**, cruce con eventos | Pitch control con velocidades |
| Etiquetado manual de vídeo | Herramientas de etiquetado de código abierto (hay que evaluar licencia y estado) | — | Pendiente (módulo opcional) |

## 3. Lo que hemos construido y validado con datos reales de Metrica
Con el partido de muestra 1 (25 Hz, 145.000 fotogramas por equipo, reducido a 5 Hz):
- **Adaptador** `metrica_data.py` al contrato del hub. Detectó un fallo real (el balón viene duplicado en los dos archivos) que los datos sintéticos no mostraban.
- **Métricas físicas**: mediana de 9,8 km por jugador de campo y velocidad máxima de 38,9 km/h (valores plausibles). La distribución real de velocidades (p99,9 = 8 m/s) llevó a bajar el filtro de saltos de 12,5 a 11 m/s.
- **Sincronización vídeo-eventos**: con eventos reales de pase, recupera el desfase aplicado a propósito (+37 s y −12 s) con una distancia mediana de 0,34 m; sigue acertando con 1,5 m de ruido añadido. Es un caso favorable (en Metrica los datos ya vienen sincronizados): con vídeo real habrá más error.
- **Cosido de identidades** (`track_repair.py`): se partió a los 28 jugadores del partido en trozos con huecos (movimiento real, 1 de cada 5 fotogramas de 25 Hz) y se midió cuántas uniones verdaderas recupera. Con huecos de 0,4-1,5 s acierta el **99 %** de las uniones con **97-99 %** de precisión (582 trayectorias → 30); con huecos de 1-3 s y parámetros por defecto (hueco ≤ 4 s, error ≤ 8 m) recupera el **95 %** con **99 %** de precisión (574 → 53); con huecos de 2-5 s baja al 53 %. **Advertencia:** es un caso favorable (posiciones sin ruido, sin detecciones falsas y con el equipo bien etiquetado). Con vídeo real habrá más errores, por eso se ofrece también la corrección manual y la opción de deshacer.
- **Fases de posesión** (245 en el partido), **líneas del equipo** y **control del espacio** (Voronoi), en tiempos de décimas de segundo.

## 4. Veredicto de replicabilidad
- **Alta**: analítica y visualización sobre seguimiento, cruce con eventos, gestión de datos. Ya está hecha.
- **Media**: seguimiento automático en **clips** o con **cámara fija** (táctica/panorámica) y calibración manual. Es nuestro módulo; la calidad real hay que medirla con el hito V0.
- **Difícil (investigación abierta)**: seguimiento fiable de **un partido completo** con identidades estables, dorsales y cámara móvil, sin intervención humana. Evidencia pública: la línea base de *SoccerTrack v2* (cámara panorámica fija) baja de **31,35** (clips de 30 s) a **12,25** (mitad completa) en GS-HOTA, genera **123–422 tracklets** por mitad para 22–35 identidades reales, acierta el dorsal en el **45,95 %** y costó unas **37 horas de GPU por mitad**. Metrica ofrece este servicio como producto comercial; no hay una receta abierta equivalente.

El cosido automático de trayectorias (hecho) ataca justo ese problema de fragmentación, pero **no sustituye** a la reidentificación ni a los dorsales.

**Recomendación:** apuntar a **cámara táctica fija** (el caso más favorable: sin movimiento de cámara, calibración una sola vez), procesar por tramos o **con corrección humana de IDs**, y evaluar cada mejora contra datos con verdad terreno antes de fiarse.

## 5. Licencias y legalidad (comprobar antes de usar)
- `roboflow/sports`: licencia **MIT** (verificado). Los conjuntos de datos de Roboflow Universe tienen cada uno su licencia.
- **Ultralytics YOLO**: se distribuye con licencia AGPL-3.0 y una licencia comercial aparte (confirma la vigente en su web; condiciona un servicio comercial).
- `sn-gamestate` / TrackLab: algún derivado declara GPL-3.0; revisa el repositorio original.
- **Datos de Metrica**: «uso responsable»; no los redistribuimos, se descargan de GitHub al usarlos.
- **SoccerTrack v2** (vídeo panorámico fijo con verdad terreno): el artículo está bajo CC BY 4.0; **comprueba la licencia del conjunto de datos** al descargarlo.
- **YouTube**: descargar partidos con `yt-dlp` suele incumplir sus términos salvo permiso del titular. Por eso la descarga por URL está desactivada por defecto y exige confirmar derechos.

## 6. Material de prueba recomendado para V0
1. **SoccerTrack v2**: 10 partidos, cámara panorámica fija 4K, coordenadas métricas 105 × 68, dorsales, identidades y eventos. Es lo más parecido a una cámara táctica con verdad terreno; permite medir objetivamente.
2. **Un clip propio** (o con permiso) de cámara táctica.
3. **Datos de Metrica**: tracking real sin vídeo (ya integrado en el hub) para el análisis.

## Fuentes consultadas
Centro de ayuda de Metrica Sports (software y servicios); `github.com/metrica-sports/sample-data`; `github.com/roboflow/sports`; `github.com/SoccerNet/sn-gamestate` (CVPRW 2024); *SoccerTrack v2* (arXiv 2508.01802).
