AUDITORÍA DE FONOTECA UMA-MERCURE
Fecha: 12 noviembre 2026
Modo: SOLO LECTURA. La base se consultó con SQLite mode=ro, incorporando el WAL existente. API consultada solo con GET. No se hicieron POST, cambios en DB, renombrados, movimientos ni reinicios.

ESTADO Y NÚMEROS VERIFICADOS

Inventario SQLite:
- track_metadata: 13.256 filas; 2.331 están referenciadas por fx_queue; 10.925 no están en fx_queue.
- Artistas distintos: 4.692. Álbumes distintos: 1.220.
- Cobertura sobre 13.256 filas: artist 13.256 (100%); title 13.256 (100%); genre 5.650 (42,6%); bpm>0 11.194 (84,4%); musical_key 4.859 (36,7%); duration>0 13.032 (98,3%); description 6.596 (49,8%); keywords 6.587 (49,7%).
- BPM por bandas: 0–60: 1; 60–90: 2.228; 90–100: 1.321; 100–110: 832; 110–120: 1.617; 120–130: 2.288; 130–140: 1.073; 140–150: 711; 150–160: 246; 160–170: 302; 170–180: 430; 180+: 145.
- bpm_source entre filas con BPM: librosa 5.832; tag 5.039; mixxx 322; nulo 1. Comparación emparejada tag frente a librosa/mixxx: solo 9 pares por artista+título; diferencia absoluta media 13,25 BPM y mediana 1,2 BPM. Muestra insuficiente para concluir sobre toda la biblioteca.
- 53 grupos de artista+título normalizados aparecen en rutas distintas (53 filas excedentes); no hay file duplicado dentro de la tabla. No se midieron tamaños porque no se confirmó raíz/montaje de medios.
- Duración nula o <=0: 224 filas. FX: 2.331 filas; mediana de duración 5,486 s; todas enlazan con una fila de track_metadata. Criterio artista vacío/Desconocido y duración <60 s: 2.204 filas, incluye SFX; no clasifica por sí solo toda la música.
- 57 rutas contienen “- Topic”. No se pudo establecer existencia física: la ruta relativa no se comprobó contra la raíz real de música. No interpretar 13.256 falsos `exists` relativos al repo como archivos perdidos.
- Uso: una fila con play_count NULL/0. Top artistas por suma play_count: Desconocido 33.843; Parov Stelar 5.837; Moby 5.449; Infected Mushroom 2.398; Blockhead 2.347; Ours Samplus 2.073; Moderator 1.618; Poranguí 1.453; Chinese Man 1.324; Bassnectar 1.269; Dysphemic 1.094; Panda Dub 1.010; Quantic 998; Mayd Hubb 995; Tricky 984; Temple Step 944; Astrix 930; Vertical Mode 927; Fatboy Slim 922; Balkan Beat Box 899; Shpongle 883; Sven Vath 797; Franz Ferdinand 779; Various Artists 748; La Raíz 746. A nivel de artista, 1.709 tienen alguna descripción y 2.983 no.
- Géneros más frecuentes: Electronic 996; Psychedelic 358; Psy-Trance 339; “Nu Jazz / Acid Jazz / Electro Swing / House” 331; Dubstep 241; Other 200; House 193; Nu Jazz 174; Jazz 153; Reggae 142; Funk 112; Trip-Hop 104; Rock 103; Dance 83; Trance 82; Techno 80; Lo-Fi 77; Electronic---Noise 64; Progressive Psy-Trance 62; Electronica/Dance 52.

Carpetas (primer/segundo nivel) con señales de cobertura desigual: Music/Music disco duro: 2.583 filas, género 8,1%, BPM 82,4%, descripción 59,9%; Music/fra: 1.692, 72,8%, 98,1%, 57,0%; _Serato_/Samples: 1.291, 27,4%, 92,3%, 7,2%. Music/AURORA_AMBIENT_CHILL (358) y Music/Sample Tools by Cr2 - Dark Acid Techno 2 (256) tienen 0% género. Son candidatos a revisión, no prueba de metadatos incorrectos.

API y estado observado (GET a localhost:8000, 12-11-2026 aprox. 22:49 CET):
- GET /api/session?sid=main: HTTP 200; estado play; Expression — “Saturn V”; índice 4/20; BPM 72,54 (mixxx), clave Fm. Posición observada 177,78 s y luego 196,41 s; el reloj avanzaba durante la auditoría. Shuffle y repeat activos.
- GET /api/session/fx_queue: HTTP 200, 2.331 ficheros. GET /api/sessions: HTTP 200, dos sesiones; main (Saturn V, play, 4/20) y 40ee85f3 (Sun Is Life — Emapea, play, 1/20).
- Búsquedas GET /api/music/search: dub 100 resultados (límite observado); trip hop 19; psy 100; deep house 100; dubstep 100. “psy” devolvió 86 rutas de Serato Samples; dub, una. dubstep incluyó Bassnectar — “Intro” en dos rutas. Señales de baja precisión: “dub” incluyó “07 — Grave” etiquetado Blues; “deep house” devolvió “Alle Farben — Drunken Sailor (Edit)” en carpeta Drum&Bass.
- No se encontraron entradas de journal para uma-api.service/mpd.service ni un log de reproducciones identificable en data. Por ello no se verifican horarios ni géneros escuchados desde logs.

10 DEFECTOS CONCRETOS (orden aproximado por impacto; evidencia)

1. Artist/título genérico en un bloque de álbum: filas del EP The Catastrophists aparecen como artist=Desconocido, title=“01 The Devil's Infantry” etc. Ruta real: `Music/[WEB] Parov Stelar - The Burning Spider (2017) FLAC/2021 Tom Morello & The Bloody Beetroots - The Catastrophists EP flac/01 The Devil's Infantry.flac`. No inferir ni sobrescribir el artista sin inspeccionar tags/fichero.
2. 224 filas carecen de duración válida. Ejemplo de arriba: “01 The Devil's Infantry.flac” con duration NULL; también “02 Radium Girls.flac” y “03 Lightning Over Mexico.flac” en la misma carpeta.
3. Género ausente en 7.606 filas (57,4%); por ejemplo Music/Music disco duro tiene solo 8,1% con género (2.583 filas). Afecta filtrado y calidad de búsquedas por estilo.
4. Clave musical presente en solo 4.859/13.256 (36,7%). Es un hueco de cobertura, no justificación para completar mediante inferencia.
5. Search “psy” contamina resultados con efectos: 86 de 100 fueron rutas bajo `_Serato_/Samples`; resultado concreto de FX también visible en `GET /api/session/fx_queue` bajo BTPRT Psytrance Ultra Pack. La búsqueda temática mezcla SFX y música.
6. Etiquetas de género inconsistentes o compuestas: `Nu Jazz` (174), `Nu-Jazz` (46), `Electronic` (996), `Electronica` (47), `Electronic---Noise` (64), y `House/Techno/Deep House/Progressive House/Electro/Minimal` (47). No fusionar automáticamente: pueden codificar información distinta.
7. 53 pares artista+título repetidos en rutas distintas. Evidencia: Bassnectar — “Intro” en `Music/fra/10. Dubstep/Bassnectar/06_11_2 - Fox Theater, Boulder, CO/01 Intro.mp3` y `Music/fra/10. Dubstep/Bassnectar/Mesmerizing The Ultra/BassNectar - Intro.mp3`. Podrían ser versiones distintas; no borrar sin comparación.
8. 57 rutas tienen residuo `- Topic`; ejemplo `Music/Music disco duro/- Uploads from Dysphemic - Topic/8 Bit Yogi.m4a`. El nombre de carpeta no demuestra que el campo artist sea erróneo: revisar por lote con tags reales.
9. Artistas con descripciones: 1.709; sin descripción: 2.983. Es un vacío de enriquecimiento y no una invitación a inventar biografías; el prompt de auditoría prohíbe inventar metadatos.
10. Precisión imperfecta de búsqueda y mezcla potencial de categorías: “dub” devolvió “07 — Grave” (Blues); “deep house” devolvió Alle Farben — “Drunken Sailor (Edit)” desde una carpeta Drum&Bass. Son resultados observados, no medida completa de precisión del endpoint.

LO QUE ESTÁ BIEN / NO SE DEBE TOCAR
- La separación de 2.331 efectos en fx_queue funciona y GET los devuelve; no vaciar ni reconstruir esa cola como parte de una limpieza de géneros.
- Los valores reales de Mixxx/librosa y las rutas existentes son evidencia; no sobrescribir BPM/clave por heurísticas ni por nombres de archivo. La comparación tag es de solo 9 pares.
- No borrar duplicados por artista+título únicamente: hay rutas de álbum/recopilación y posibles versiones distintas. No renombrar automáticamente los 57 “- Topic”.
- No modificar el estado de reproducción, cola, shuffle/repeat ni sesiones; la sesión main estaba reproduciendo durante la observación.
- No tocar artistas underground sin fuente verificable. “Sin descripción” no equivale a artista desconocido.

5 ACCIONES PEQUEÑAS Y REVERSIBLES (propuestas, NO ejecutadas)

1. Exportar a CSV una lista de las 224 filas con duración inválida, clasificada NULL/0 y con file/artist/title. Cambio: solo archivo de revisión. Tiempo: 10–20 min. Backup: ninguno para la DB; conservar el CSV original si se anota.
2. Generar un informe de colisiones de género (valor exacto, recuento, rutas de muestra) y aprobar manualmente un mapa de alias antes de cualquier cambio. Cambio: sidecar de propuesta, sin UPDATE. Tiempo: 30–60 min. Backup: ninguno para DB; versionar/copia del sidecar.
3. Exportar los 53 grupos duplicados con rutas y duración/tamaño una vez confirmada la raíz de medios. Cambio: solo informe comparativo. Tiempo: 20–40 min. Backup: ninguno mientras no se borre nada; antes de cualquier deduplicación, backup DB y medios.
4. Afinar una copia/prueba de la consulta de búsqueda para excluir explícitamente rutas que estén en fx_queue, comparar las cinco consultas y medir precisión; no desplegar todavía. Cambio: código de prueba, reversible al descartarlo. Tiempo: 30–60 min. Backup: diff/commit del código antes de promover; no requiere backup DB.
5. Calcular y exportar el reporte de completitud por carpeta y campo para priorizar revisión manual. Cambio: CSV de solo lectura. Tiempo: 15–30 min. Backup: ninguno para DB; guardar el CSV previo si se regenera.

NO ARREGLABLE CON ESTA AUDITORÍA
- No se puede decidir qué copia es master sin validar tamaño, duración y escucha de los ficheros con raíz de medios montada.
- No se puede completar bio de 2.983 artistas sin investigación y fuentes fiables; no inventar.
- No se puede determinar si rutas relativas faltan físicamente hasta confirmar montaje/root del HDD. No se afirma que estén perdidas.
- Archivos corruptos no se identifican de forma concluyente con los datos SQLite consultados; requieren verificación de lectura/decodificación sobre medios, fuera de esta ejecución.

Integridad del alcance: este informe se escribió después de terminar las consultas. Ninguna corrección de datos o acción propuesta fue aplicada.