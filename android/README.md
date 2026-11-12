# App nativa UMA-Mercure (Android)

Mando a distancia de la radio: control remoto de la sesión `main`, cola con
ventana alrededor de la pista actual, búsqueda que añade a la cola, pestaña DJ
(pide listas al LLM por cantidad/estilo/BPM) y reproducción en segundo plano con
notificación y botones de auriculares/bluetooth.

No es una PWA: es una Activity con `Service` en `foreground` de tipo
`mediaPlayback`, `MediaSession` de Android y `AudioTrack` sobre el stream
`Range` del backend. Por eso sigue sonando con la pantalla apagada y responde a
los botones de media aunque la app esté cerrada.

## Construir

Requiere Android SDK (build-tools 35.x + platform android-35) y un keystore. No
usa Gradle ni Android Studio: `aapt2` → `javac` → `d8` → `zipalign` → `apksigner`.

```bash
# rutas configurables por entorno
export ANDROID_BUILD_TOOLS=$HOME/Android/build-tools/35.0.0
export ANDROID_PLATFORM_JAR=$HOME/Android/platforms/android-35/android.jar
export DEBUG_KEYSTORE=$HOME/.android/debug.keystore
export DEBUG_KEYSTORE_PASS=pass:android     # debug por USB; cambia para firmar de verdad

bash build.sh            # genera out/uma-radio.apk
adb install -r out/uma-radio.apk            # o copia a ../web/dist/uma-radio.apk y descargala del navegador
```

Telegram no permite descargar `.apk`: se sirve desde la propia radio en
`http://<host>:8000/uma-radio.apk` (ver `build.sh`).

## Uso

- Pestaña **Radio**: controla la sesión `main` (la radio común). Play/pausa,
  siguiente, anterior, stop, seek, shuffle, barajar.
- **Crear sesión propia** bifurca `main`: ahí puedes barajar, pedir listas al DJ
  y escuchar tu sesión sin tocar la radio común. «Volver a la radio común» te
  devuelve a `main`. La sesión `main` es el master.
- **Buscar** añade el archivo a la cola y salta a él; no reemplaza la cola.
- **DJ**: escribe un criterio («crea una lista de 50 canciones de dub», «deep
  house entre 118 y 124») o toca una sugerencia. Escribe en la sesión en la que
  estés; la cabecera te dice dónde va a escribir.

## Notas técnicas

- Los endpoints de transporte son `POST` (`/api/session/play|pause|next|previous|stop|…`);
  un `GET` devuelve `405` y los botones quedan mudos.
- `POST /api/chat` acepta `sid`; sin `sid` escribe en `main`.
- La cola se lee con `offset` para ver un tramo alrededor de la pista actual.
- Los packs de efectos/SFX viven en `fx_queue` y no entran en listas ni en el
  barajado de la radio común.
- `compileSdk`/`minSdk` en `AndroidManifest.xml` (minSdk 26). `versionCode` sube
  en cada build para poder reinstalar sobre la versión anterior.
