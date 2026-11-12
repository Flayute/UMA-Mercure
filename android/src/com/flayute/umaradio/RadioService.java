package com.flayute.umaradio;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.PowerManager;

import org.json.JSONObject;

import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Reproduce la pista actual de la sesion via HTTP (Range/seek) y sincroniza con el
 * reloj del servidor cada 3 s. Corre como servicio en primer plano (mediaPlayback)
 * con MediaSession: suena con la pantalla apagada y expone play/pausa/siguiente
 * en la notificacion y en la pantalla de bloqueo.
 */
public class RadioService extends Service {
    public static final String CHANNEL = "uma_radio";
    public static final int NOTIF_ID = 1;
    public static final String PREFS = "uma";
    public static final String PREF_URL = "url";
    public static final String PREF_SID = "sid";

    private static RadioService instance;

    private MediaPlayer player;
    private MediaSession mediaSession;
    private AudioManager audioManager;
    private ScheduledExecutorService poller;
    private final Handler ui = new Handler();

    private String baseUrl;
    private String sid = "main";
    private String currentFile = null;
    private boolean playerPlaying = false;
    private volatile boolean serverPlaying = false;
    private double serverPos = 0, serverDur = 0;
    private String title = "", artist = "";
    private String metaLine = "";
    private float volume = 0.8f;
    private String skippedFile = null;
    private volatile boolean lastError = false;

    public interface Listener { void onUi(); }
    private Listener listener;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        baseUrl = p.getString(PREF_URL, getString(R.string.default_url));
        sid = p.getString(PREF_SID, "main");
        // una sesion propia ya borrada (o vacia) no es recuperable: vuelve a la radio comun
        if (!"main".equals(sid)) {
            try {
                JSONObject s = new JSONObject(get("/api/session?sid=" + sidSafe(sid)));
                if (s.optInt("queue_len", 0) == 0 && s.optString("file", "").isEmpty()) sid = "main";
            } catch (Exception e) { sid = "main"; }
        }

        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "UMA Radio",
                NotificationManager.IMPORTANCE_LOW));

        audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);
        mediaSession = new MediaSession(this, "uma-radio");
        mediaSession.setActive(true);
        mediaSession.setMediaButtonReceiver(PendingIntent.getService(this, 3,
                new Intent(this, RadioService.class).setAction("toggle"),
                PendingIntent.FLAG_IMMUTABLE));
        mediaSession.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { api("/api/session/play"); }
            @Override public void onPause() { api("/api/session/pause"); }
            @Override public void onSkipToNext() { api("/api/session/next"); }
            @Override public void onSkipToPrevious() { api("/api/session/previous"); }
            @Override public void onSeekTo(long pos) { seek(pos / 1000.0); }
        });

        player = new MediaPlayer();
        player.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build());
        try { player.setWakeMode(getApplicationContext(), PowerManager.PARTIAL_WAKE_LOCK); }
        catch (Exception ignored) {}
        player.setOnPreparedListener(mp -> {
            mp.setVolume(volume, volume);
            mp.start();
            playerPlaying = true;
            notifyUi();
        });
        player.setOnCompletionListener(mp -> {
            playerPlaying = false;
            // el servidor avanza solo cuando su reloj llega al final; si aun cree
            // que estamos a mitad de pista, pide el salto explicito
            if (serverPlaying && serverPos < serverDur - 1.0) api("/api/session/next");
            notifyUi();
        });
        player.setOnErrorListener((mp, what, extra) -> {
            lastError = true;
            if (currentFile != null && !currentFile.equals(skippedFile)) {
                skippedFile = currentFile;
                api("/api/session/next");
            }
            return true;
        });

        startForegroundNotif();
        poller = Executors.newSingleThreadScheduledExecutor();
        poller.scheduleWithFixedDelay(this::poll, 0, 3, TimeUnit.SECONDS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForegroundNotif();
        if (intent != null && intent.getAction() != null) {
            String a = intent.getAction();
            if ("play".equals(a)) api("/api/session/play");
            else if ("pause".equals(a)) api("/api/session/pause");
            else if ("next".equals(a)) api("/api/session/next");
            else if ("toggle".equals(a)) api(serverPlaying ? "/api/session/pause" : "/api/session/play");
        }
        return START_STICKY;
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onDestroy() {
        if (poller != null) poller.shutdownNow();
        if (player != null) { try { player.release(); } catch (Exception ignored) {} }
        if (mediaSession != null) { mediaSession.setActive(false); mediaSession.release(); }
        instance = null;
        super.onDestroy();
    }

    // ── API ────────────────────────────────────────────────────────────

    private String get(String path) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(6000);
        c.setRequestProperty("Accept", "application/json");
        try {
            java.io.InputStream in = c.getResponseCode() >= 400 ? c.getErrorStream() : c.getInputStream();
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while (in != null && (n = in.read(buf)) > 0) bos.write(buf, 0, n);
            return bos.toString("UTF-8");
        } finally { c.disconnect(); }
    }

    /** Manda un mensaje al LLM de la Pi (/api/chat). Si ownSession es false, va a la radio comun (main). */
    public String chat(String message, boolean ownSession) throws Exception {
        JSONObject body = new JSONObject();
        body.put("message", message);
        body.put("sid", sidSafe(ownSession ? sid : "main"));
        String resp = postSync("/api/chat", body.toString());
        JSONObject j = new JSONObject(resp);
        return j.optString("message", "No entendido");
    }

    /** POST sin body a los endpoints de transporte (son POST, no GET) */
    private void api(String path) {
        String full = path + (path.contains("?") ? "&" : "?") + "sid=" + sidSafe(sid);
        new Thread(() -> {
            try { rawGetPost(full); } catch (Exception e) {
                android.util.Log.w("uma-radio", "api fallo " + path + ": " + e);
            }
        }).start();
    }

    private void seek(double seconds) {
        try {
            String body = "{\"seconds\":" + seconds + "}";
            HttpURLConnection c = (HttpURLConnection)
                    new URL(baseUrl + "/api/session/seek?sid=" + sidSafe(sid)).openConnection();
            c.setConnectTimeout(4000);
            c.setReadTimeout(4000);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/json");
            c.setDoOutput(true);
            c.getOutputStream().write(body.getBytes("UTF-8"));
            c.getResponseCode();
            c.disconnect();
        } catch (Exception ignored) {}
        try { if (player != null && playerPlaying) player.seekTo((int) (seconds * 1000)); }
        catch (Exception ignored) {}
    }

    private static String nz(String s) { return s == null || "null".equals(s) ? "" : s; }

    private static String sidSafe(String s) {
        try { return URLEncoder.encode(s, "UTF-8"); } catch (Exception e) { return s; }
    }

    private void poll() {
        try {
            String json = get("/api/session?sid=" + sidSafe(sid));
            JSONObject j = new JSONObject(json);
            String file = j.optString("file", "");
            String state = j.optString("state", "stop");
            double pos = j.optDouble("position", 0);
            double dur = j.optDouble("duration", 0);
            String t = j.optString("title", "");
            String a = j.optString("artist", "");
            if (t.isEmpty() && !file.isEmpty()) {
                String n = file.substring(file.lastIndexOf('/') + 1);
                int dot = n.lastIndexOf('.');
                t = dot > 3 ? n.substring(0, dot) : n;
            }
            serverPlaying = "play".equals(state);
            serverPos = pos; serverDur = dur;
            title = t; artist = nz(a);
            StringBuilder m = new StringBuilder();
            double bpm = j.optDouble("bpm", 0);
            if (bpm > 0) m.append(String.format("%.0f bpm", bpm));
            String k = nz(j.optString("musical_key", ""));
            if (!k.isEmpty()) m.append(m.length() > 0 ? " · " : "").append(k);
            String g = nz(j.optString("genre", ""));
            if (!g.isEmpty()) m.append(m.length() > 0 ? " · " : "").append(g);
            String src = nz(j.optString("bpm_source", ""));
            if (bpm > 0 && !src.isEmpty()) m.append("  (").append(src).append(")");
            metaLine = m.toString();
            lastError = false;

            if (!file.equals(currentFile)) {
                currentFile = file;
                loadTrack(file);
            } else {
                syncPlayback(pos);
            }
            notifyUi();
        } catch (Exception e) {
            lastError = true;
            android.util.Log.w("uma-radio", "poll fallo: " + e);
            notifyUi();
        }
    }

    private void loadTrack(String file) {
        try { player.reset(); } catch (Exception ignored) {}
        playerPlaying = false;
        if (file == null || file.isEmpty()) { stopLocal(); return; }
        try {
            requestFocus();
            player.setDataSource(baseUrl + "/api/music/stream?file=" + sidSafe(file));
            player.prepareAsync();
        } catch (Exception e) {
            lastError = true;
        }
    }

    private void syncPlayback(double pos) {
        if (serverPlaying && !playerPlaying) {
            requestFocus();
            try { player.start(); playerPlaying = true; } catch (Exception ignored) {}
        } else if (!serverPlaying && playerPlaying) {
            try { player.pause(); playerPlaying = false; } catch (Exception ignored) {}
        }
        if (playerPlaying && serverDur > 0 && Math.abs(player.getCurrentPosition() / 1000.0 - pos) > 1.5) {
            try { player.seekTo((int) (pos * 1000)); } catch (Exception ignored) {}
        }
    }

    private void stopLocal() {
        try { player.reset(); } catch (Exception ignored) {}
        playerPlaying = false;
    }

    private void requestFocus() {
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                audioManager.requestAudioFocus(new android.media.AudioFocusRequest.Builder(
                        AudioManager.AUDIOFOCUS_GAIN)
                        .setAudioAttributes(new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                        .setWillPauseWhenDucked(true).build());
            } else {
                audioManager.requestAudioFocus(l -> {}, AudioManager.AUDIOFOCUS_GAIN,
                        AudioManager.AUDIOFOCUS_GAIN);
            }
        } catch (Exception ignored) {}
    }

    // ── interfaz publica para MainActivity ─────────────────────────────

    public static RadioService get() { return instance; }

    public void setListener(Listener l) { listener = l; }

    public String baseUrl() { return baseUrl; }
    public String sid() { return sid; }
    public boolean serverPlaying() { return serverPlaying; }
    public boolean connected() { return !lastError; }
    public double pos() { return serverPos; }
    public double dur() { return serverDur; }
    public String title() { return title; }
    public String artist() { return artist; }
    public String metaLine() { return metaLine; }

    public void setUrl(String url) {
        baseUrl = url.replaceAll("/+$", "");
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(PREF_URL, baseUrl).commit();
    }

    public void setSid(String newSid) {
        sid = newSid;
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(PREF_SID, sid).commit();
        currentFile = null;
    }

    public void command(String what) { api("/api/session/" + what); }

    public void seekTo(double seconds) { seek(seconds); }

    public void setVolume(float v) {
        volume = v;
        try { if (playerPlaying) player.setVolume(v, v); } catch (Exception ignored) {}
    }

    /** Anade una pista buscada al final de la cola y salta a ella (sin borrar la cola). */
    public void playSearchFile(String file) {
        new Thread(() -> {
            try {
                int len = 0;
                try {
                    len = new JSONObject(rawGet("/api/session?sid=" + sidSafe(sid))).optInt("queue_len", 0);
                } catch (Exception ignored) {}
                postJson("/api/session/add_files", "{\"files\":[\"" + esc(file) + "\"]}");
                try { Thread.sleep(700); } catch (InterruptedException ignored) {}
                postJson("/api/session/play_index", "{\"index\":" + len + "}");
            } catch (Exception ignored) {}
        }).start();
    }

    private static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    /** POST con body JSON (play_file, play_index, add_files) */
    public void postJson(String path, String body) {
        new Thread(() -> {
            try { postSync(path, body); } catch (Exception ignored) {}
        }).start();
    }

    /** POST sincrónico con respuesta (usado por chat). Añade sid si el endpoint lo admite. */
    public String postSync(String path, String body) throws Exception {
        String full = path.startsWith("/api/chat") ? path : path + "?sid=" + sidSafe(sid);
        HttpURLConnection c = (HttpURLConnection) new URL(baseUrl + full).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(90000);   // el LLM de la Pi puede tardar
        c.setRequestMethod("POST");
        c.setRequestProperty("Content-Type", "application/json");
        c.setDoOutput(true);
        c.getOutputStream().write(body.getBytes("UTF-8"));
        java.io.InputStream in = c.getResponseCode() >= 400 ? c.getErrorStream() : c.getInputStream();
        java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while (in != null && (n = in.read(buf)) > 0) bos.write(buf, 0, n);
        c.disconnect();
        return bos.toString("UTF-8");
    }

    /** GET de lista JSON para la cola/busqueda (bloqueante: usar en hilo) */
    public String rawGet(String path) throws Exception { return get(path); }

    /** POST sin body (fork/drop) desde un hilo */
    public String rawGetPost(String path) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(6000);
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.getOutputStream().write(new byte[0]);
        java.io.InputStream in = c.getResponseCode() >= 400 ? c.getErrorStream() : c.getInputStream();
        java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while (in != null && (n = in.read(buf)) > 0) bos.write(buf, 0, n);
        c.disconnect();
        return bos.toString("UTF-8");
    }

    private void notifyUi() {
        ui.post(() -> {
            if (listener != null) listener.onUi();
            updateNotifAndSession();
        });
    }

    private void updateNotifAndSession() {
        mediaSession.setMetadata(new android.media.MediaMetadata.Builder()
                .putString(android.media.MediaMetadata.METADATA_KEY_TITLE,
                        title.isEmpty() ? "UMA Radio" : title)
                .putString(android.media.MediaMetadata.METADATA_KEY_ARTIST,
                        artist.isEmpty() ? "UMA Mercure" : artist)
                .putLong(android.media.MediaMetadata.METADATA_KEY_DURATION,
                        (long) (serverDur * 1000))
                .build());
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT
                | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_SEEK_TO;
        mediaSession.setPlaybackState(new PlaybackState.Builder().setActions(actions)
                .setState(serverPlaying ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        (long) (serverPos * 1000), 1.0f)
                .build());
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.notify(NOTIF_ID, buildNotif());
    }

    private Notification buildNotif() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_IMMUTABLE);
        String state = serverPlaying ? "Sonando" : (lastError ? "sin conexion" : "En pausa");
        Notification.Builder b = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat)
                .setContentTitle(title.isEmpty() ? "UMA Radio" : title)
                .setContentText(artist.isEmpty() ? state : artist + " · " + state)
                .setContentIntent(pi)
                .setOngoing(true)
                .addAction(serverPlaying ? R.drawable.ic_stat : R.drawable.ic_stat,
                        serverPlaying ? "Pausa" : "Sonar",
                        PendingIntent.getService(this, 1,
                                new Intent(this, RadioService.class).setAction(
                                        serverPlaying ? "pause" : "play"),
                                PendingIntent.FLAG_IMMUTABLE))
                .addAction(R.drawable.ic_stat, "Siguiente",
                        PendingIntent.getService(this, 2,
                                new Intent(this, RadioService.class).setAction("next"),
                                PendingIntent.FLAG_IMMUTABLE));
        if (Build.VERSION.SDK_INT >= 29) b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        return b.build();
    }

    private void startForegroundNotif() {
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIF_ID, buildNotif(),
                        android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            } else {
                startForeground(NOTIF_ID, buildNotif());
            }
        } catch (Exception e) {
            startForeground(NOTIF_ID, buildNotif());
        }
    }
}
