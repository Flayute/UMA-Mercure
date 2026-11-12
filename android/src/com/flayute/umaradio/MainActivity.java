package com.flayute.umaradio;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.text.TextUtils;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ListView;
import android.widget.SeekBar;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private RadioService svc;
    private final Handler ui = new Handler();

    private TextView brand, statusChip, trackTitle, trackArtist, metaLine, tPos, tDur;
    private SeekBar seek, vol;
    private Button btnPlay, btnPrev, btnNext, btnStop, btnSession, btnShuffle, tabQueue, tabSearch, tabDJ;
    private EditText searchBox;
    private ListView list;

    private boolean queueMode = true;          // true=Cola, false=Buscar
    private boolean djMode = false;            // pestaña DJ (LLM) activa
    private boolean djBusy = false;
    private boolean userSeeking = false;
    private List<String> listFiles = new ArrayList<>();
    private List<String> listLabels = new ArrayList<>();
    private ArrayAdapter<String> adapter;
    private int listOffset = 0;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        setContentView(R.layout.activity_main);

        brand = findViewById(R.id.brand);
        statusChip = findViewById(R.id.statusChip);
        trackTitle = findViewById(R.id.trackTitle);
        trackArtist = findViewById(R.id.trackArtist);
        metaLine = findViewById(R.id.metaLine);
        tPos = findViewById(R.id.tPos);
        tDur = findViewById(R.id.tDur);
        seek = findViewById(R.id.seek);
        vol = findViewById(R.id.vol);
        btnPlay = findViewById(R.id.btnPlay);
        btnPrev = findViewById(R.id.btnPrev);
        btnNext = findViewById(R.id.btnNext);
        btnStop = findViewById(R.id.btnStop);
        btnSession = findViewById(R.id.btnSession);
        btnShuffle = findViewById(R.id.btnShuffle);
        tabQueue = findViewById(R.id.tabQueue);
        tabSearch = findViewById(R.id.tabSearch);
        tabDJ = findViewById(R.id.tabDJ);
        searchBox = findViewById(R.id.searchBox);
        list = findViewById(R.id.list);

        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                        != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 7);
        }

        adapter = new ArrayAdapter<>(this, R.layout.item_track, R.id.itemTitle, listLabels);
        list.setAdapter(adapter);
        list.setOnItemClickListener((a, v, i, id) -> {
            if (i >= listLabels.size()) return;   // el adapter puede ir por delante de los datos tras un swap
            String label = listLabels.get(i);
            String f = i < listFiles.size() ? listFiles.get(i) : "";
            if (djMode) {                                   // chips de sugerencias / respuesta del LLM
                if (label.startsWith("◆ ")) djAsk(label.substring(2).trim());
                else if (!f.isEmpty()) svc.postJson("/api/session/play_index", "{\"index\":" + (listOffset + i) + "}");
                return;
            }
            if (queueMode) svc.postJson("/api/session/play_index", "{\"index\":" + (listOffset + i) + "}");
            else svc.playSearchFile(f);   // anade a la cola y salta al final: no borra la cola actual
        });

        btnPlay.setOnClickListener(v -> svc.command(svc.serverPlaying() ? "pause" : "play"));
        btnPrev.setOnClickListener(v -> svc.command("previous"));
        btnNext.setOnClickListener(v -> svc.command("next"));
        btnStop.setOnClickListener(v -> svc.command("stop"));
        btnShuffle.setOnClickListener(v -> svc.command("shuffle_all"));
        btnSession.setOnClickListener(v -> toggleSession());

        ImageButton settings = findViewById(R.id.btnSettings);
        settings.setOnClickListener(v -> settingsDialog());

        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int p, boolean fromUser) {}
            @Override public void onStartTrackingTouch(SeekBar s) { userSeeking = true; }
            @Override public void onStopTrackingTouch(SeekBar s) {
                userSeeking = false;
                double dur = svc.dur();
                if (dur > 0) svc.seekTo(s.getProgress() / 1000.0 * dur);
            }
        });

        vol.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int p, boolean fromUser) {
                if (fromUser) svc.setVolume(p / 100f);
            }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });

        tabQueue.setOnClickListener(v -> { djMode = false; queueMode = true; setSearchVisible(false); tabs(); refreshList(); });
        tabSearch.setOnClickListener(v -> {
            djMode = false; queueMode = false; setSearchVisible(true); tabs();
            searchBox.setHint("busca artista, título, género, bpm…");
            searchBox.requestFocus();
            if (listLabels.isEmpty()) search("");
        });
        tabDJ.setOnClickListener(v -> {
            djMode = true; queueMode = true; setSearchVisible(true);
            searchBox.setHint("pide algo: deep house 120 bpm, algo que encaje ahora…");
            tabs(); searchBox.requestFocus();
            showDjChips();
        });
        // La caja es multi-linea a proposito: en esta tablet el teclado virtual no
        // dispara IME_ACTION_SEARCH y el texto quedaba tapado por el teclado. Enter
        // = salto de linea (no ejecutar); se ejecuta con btnGo, que esta a la derecha
        // de la caja y siempre visible.
        searchBox.setOnKeyListener((v, keyCode, event) -> {
            if (event.getAction() == android.view.KeyEvent.ACTION_DOWN &&
                    (keyCode == android.view.KeyEvent.KEYCODE_ENTER || keyCode == android.view.KeyEvent.KEYCODE_NUMPAD_ENTER)) {
                if (!djMode) {          // en busqueda simple si ejecuta
                    String q = searchBox.getText().toString().trim();
                    search(q);
                    hideKeyboard();
                    return true;
                }
            }
            return false;
        });

        ImageButton goBtn = findViewById(R.id.btnGo);
        goBtn.setOnClickListener(v -> {
            String q = searchBox.getText().toString().trim();
            if (djMode) djAsk(q); else search(q);
            hideKeyboard();
        });

        // limpiar: vacia la caja y devuelve la radio comun a su aleatorio completo
        ImageButton clearBtn = findViewById(R.id.btnClear);
        clearBtn.setOnClickListener(v -> {
            searchBox.setText("");
            hideKeyboard();
            if (djMode) {
                // vaciar la caja y recuperar las sugerencias; la cola del DJ se deja
                // intacta salvo que el usuario vuelva a pedir o a Aleatorio
                showDjChips();
            } else {
                refreshList();
            }
        });

        vol.setProgress(80);
        startService();
    }

    @Override
    protected void onResume() {
        super.onResume();
        svc = RadioService.get();
        if (svc != null) svc.setListener(this::refresh);
        refreshList();
        ui.postDelayed(ticker, 700);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (svc != null) svc.setListener(null);
        ui.removeCallbacks(ticker);
    }

    private final Runnable ticker = new Runnable() {
        @Override public void run() { refresh(); ui.postDelayed(this, 700); }
    };

    private void startService() {
        Intent i = new Intent(this, RadioService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i); else startService(i);
        svc = RadioService.get();
        if (svc == null) {
            ui.postDelayed(() -> { svc = RadioService.get(); if (svc != null) svc.setListener(this::refresh); refresh(); }, 500);
        }
    }

    private void refresh() {
        if (svc == null) return;
        boolean playing = svc.serverPlaying();
        boolean connected = svc.connected();
        statusChip.setText(connected ? (playing ? "● Sonando" : "● En pausa") : "● sin conexión");
        statusChip.setTextColor(connected ? getColor(R.color.ok) : getColor(R.color.text_muted));
        trackTitle.setText(svc.title().isEmpty() ? "Sin reproducción" : svc.title());
        trackArtist.setText(TextUtils.isEmpty(svc.artist()) ? "—" : svc.artist());
        btnPlay.setText(playing ? "⏸" : "▶");
        metaLine.setText(svc.metaLine());
        btnPlay.setTextColor(getColor(R.color.text_primary));

        double pos = svc.pos(), dur = svc.dur();
        if (!userSeeking && dur > 0) seek.setProgress((int) (pos / dur * 1000));
        tPos.setText(fmt(pos));
        tDur.setText(fmt(dur));
        btnSession.setText("main".equals(svc.sid()) ? "Crear sesión propia" : "Volver a la radio común");
    }

    private void setSearchVisible(boolean on) {
        searchBox.setVisibility(on ? View.VISIBLE : View.GONE);
        findViewById(R.id.btnGo).setVisibility(on ? View.VISIBLE : View.GONE);
        findViewById(R.id.btnClear).setVisibility(djMode ? View.VISIBLE : View.GONE);
    }

    private void tabs() {
        tabQueue.setTextColor(getColor(!djMode && queueMode ? R.color.accent : R.color.text_secondary));
        tabSearch.setTextColor(getColor(!djMode && !queueMode ? R.color.accent : R.color.text_secondary));
        tabDJ.setTextColor(getColor(djMode ? R.color.accent : R.color.text_secondary));
    }

    /** Pregunta al LLM de la Pi (endpoint /api/chat) y refresca la cola con lo que monte. */
    private void djAsk(String question) {
        if (svc == null) svc = RadioService.get();
        if (djBusy || svc == null || question.isEmpty()) return;
        djBusy = true;                          // bandera ya, antes de cualquier refresh programado
        final List<String> labels = new ArrayList<>();
        final List<String> files = new ArrayList<>();
        djChips = false;
        labels.add("… pidiendo al cerebro: \"" + question + "\" · escribe en " +
                ("main".equals(svc.sid()) ? "la RADIO COMUN" : "tu sesion " + svc.sid()));
        ui.post(() -> swap(labels, files));
        Executors.newSingleThreadExecutor().execute(() -> {
            String msg = null;
            try {
                // El master es tuyo: el DJ escribe en la sesion en la que estas (main por defecto).
                // Si quieres compartir sin tocar la radio comun, pulsa antes "Crear sesion propia".
                msg = svc.chat(question, true);
            } catch (Exception e) { android.util.Log.w("uma-radio", "dj fallo: " + e); }
            final String reply = msg;
            ui.postDelayed(() -> {
                djBusy = false;
                refreshList();   // cola del LLM, pintada sobre la pestaña DJ
                if (reply != null && reply.toLowerCase().startsWith("no encontr")) statusChip.setText("◆ " + reply);
            }, 1200);
        });
    }

    private void addDjHint(String text) {
        listLabels.clear(); listFiles.clear();
        listLabels.add(text);
        adapter.notifyDataSetChanged();
    }

    /** Chips de sugerencias: escribir un criterio en la caja NO los borra. */
    private void showDjChips() {
        djChips = true;
        listLabels.clear(); listFiles.clear();
        String sidActual = svc == null ? "main" : svc.sid();
        String destino = "main".equals(sidActual) ? "la RADIO COMUN (tu master)" : "tu sesion " + sidActual;
        listLabels.add("El DJ escribe en " + destino + " · toca una sugerencia o escribe y pulsa →:");
        String[] chips = {
            "deep house entre 118 y 124 bpm",
            "techno dura alrededor de 140 bpm",
            "dubstep y bass",
            "trip hop relajado",
            "algo que encaje con lo que suena ahora",
            "jazz electrónico",
        };
        for (String c : chips) listLabels.add("◆ " + c);
        adapter.notifyDataSetChanged();
    }

    private boolean djChips = false;

    private boolean sessionBusy = false;

    private void toggleSession() {
        if (sessionBusy) return;
        sessionBusy = true;
        ui.postDelayed(() -> sessionBusy = false, 1500);
        if ("main".equals(svc.sid())) {
            Executors.newSingleThreadExecutor().execute(() -> {
                try {
                    JSONObject cur = new JSONObject(svc.rawGet("/api/session?sid=" + svc.sid()));
                    if (cur.optInt("queue_len", 0) == 0) {
                        // sesion huérfana abandonada a medias: no se puede bifurcar una cola vacia
                        svc.setSid("main");
                        ui.post(() -> refresh());
                        return;
                    }
                    String r = svc.rawGetPost("/api/session/fork?sid=" + svc.sid());
                    JSONObject j = new JSONObject(r);
                    String newSid = j.optString("sid", "");
                    if (!newSid.isEmpty()) svc.setSid(newSid);
                    ui.post(this::refresh);
                } catch (Exception ignored) {}
            });
        } else {
            String old = svc.sid();
            svc.setSid("main");
            Executors.newSingleThreadExecutor().execute(() -> {
                try { svc.rawGetPost("/api/session/drop?sid=" + old); } catch (Exception ignored) {}
            });
            refresh();
        }
    }

    private void refreshList() {
        if (djBusy) return;
        if (djMode && djChips) return;   // las sugerencias siguen visibles hasta pedir
        if (svc == null) svc = RadioService.get();
        if (svc == null) { ui.postDelayed(this::refreshList, 800); return; }
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                if (queueMode) {
                    int cur = 0;
                    try {
                        cur = new JSONObject(svc.rawGet("/api/session?sid=" + enc(svc.sid())))
                                .optInt("queue_index", 0);
                    } catch (Exception ignored) {}
                    int off = Math.max(0, cur - 15);
                    String json = svc.rawGet("/api/session/queue?sid=" + enc(svc.sid())
                            + "&limit=120&offset=" + off);
                    JSONObject j = new JSONObject(json);
                    cur = j.optInt("current_index", cur);
                    JSONArray items = j.optJSONArray("items");
                    final List<String> labels = new ArrayList<>();
                    final List<String> files = new ArrayList<>();
                    listOffset = off;
                    if (items != null) {
                        for (int i = 0; i < items.length(); i++) {
                            JSONObject it = items.getJSONObject(i);
                            int idx = it.optInt("index", off + i);
                            String t = nz(it.optString("title", ""));
                            if (t.isEmpty()) t = nz(it.optString("file", "?"));
                            String a = nz(it.optString("artist", ""));
                            String label = (idx == cur ? "▸ " : "") + t + (a.isEmpty() ? "" : " — " + a);
                            labels.add(label); files.add(it.optString("file", ""));
                        }
                    }
                    ui.post(() -> swap(labels, files));
                } else {
                    String json = svc.rawGet("/api/music/library?q=" + enc(searchBox.getText().toString().trim())
                            + "&limit=80");
                    JSONArray rows = new JSONArray(json);
                    final List<String> labels = new ArrayList<>();
                    final List<String> files = new ArrayList<>();
                    for (int i = 0; i < rows.length(); i++) {
                        JSONObject r = rows.getJSONObject(i);
                        String t = nz(r.optString("title", "?"));
                        String a = nz(r.optString("artist", ""));
                        StringBuilder meta = new StringBuilder();
                        if (r.optDouble("bpm", 0) > 0) meta.append(String.format("%.0f bpm", r.optDouble("bpm")));
                        String k = nz(r.optString("musical_key", ""));
                        if (!k.isEmpty()) meta.append(meta.length() > 0 ? " · " : "").append(k);
                        String g = nz(r.optString("genre", ""));
                        if (!g.isEmpty()) meta.append(meta.length() > 0 ? " · " : "").append(g);
                        labels.add(t + (a.isEmpty() ? "" : " — " + a) +
                                (meta.length() > 0 ? "  (" + meta + ")" : ""));
                        files.add(r.optString("file", ""));
                    }
                    ui.post(() -> swap(labels, files));
                }
            } catch (Exception e) {
                android.util.Log.w("uma-radio", "lista fallo: " + e);
                ui.post(() -> swap(new ArrayList<>(), new ArrayList<>()));
            }
        });
    }

    private void search(String q) { refreshList(); }

    private void swap(List<String> labels, List<String> files) {
        listFiles = files;
        listLabels.clear();
        listLabels.addAll(labels);
        adapter.notifyDataSetChanged();
    }

    private void settingsDialog() {
        EditText e = new EditText(this);
        e.setText(svc.baseUrl());
        e.setTextColor(getColor(R.color.text_primary));
        new AlertDialog.Builder(this)
                .setTitle("API de la radio")
                .setView(e)
                .setPositiveButton("Guardar", (d, w) -> {
                    svc.setUrl(e.getText().toString().trim());
                    refreshList();
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private void hideKeyboard() {
        InputMethodManager im = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        im.hideSoftInputFromWindow(searchBox.getWindowToken(), 0);
    }

    private static String nz(String s) { return s == null || "null".equals(s) ? "" : s; }

    private static String fmt(double s) {
        if (s <= 0 || Double.isNaN(s)) return "0:00";
        int t = (int) s;
        return (t / 60) + ":" + String.format("%02d", t % 60);
    }

    private static String enc(String s) {
        try { return java.net.URLEncoder.encode(s, "UTF-8"); } catch (Exception e) { return s; }
    }

    private static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private void startServiceIfNeeded() { startService(); }
}
