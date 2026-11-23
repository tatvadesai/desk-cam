#!/usr/bin/env python3
"""desk-cam: Capture handwritten math/notes from any camera -> Markdown + LaTeX."""
import argparse
import base64
import http.server
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

DEFAULT_OUT = os.path.expanduser(
    os.environ.get("DESK_CAM_OUT") or os.environ.get("LEARNING_INBOX") or "~/desk-cam"
)
DEFAULT_PORT = int(os.environ.get("DESK_CAM_PORT", "8765"))
DEFAULT_PROVIDER = os.environ.get("DESK_CAM_PROVIDER", "auto")
DEFAULT_MODEL = os.environ.get("DESK_CAM_MODEL", "")
DEFAULT_FILE = os.environ.get("DESK_CAM_FILE", "work.md")
MAX_BYTES = 15 * 1024 * 1024

OUT_DIR = DEFAULT_OUT
OUT_FILE = DEFAULT_FILE
PORT = DEFAULT_PORT
PROVIDER = DEFAULT_PROVIDER
MODEL = DEFAULT_MODEL
FRONTMATTER = False

TRANSCRIBE_PROMPT = """Transcribe the handwritten work in this image verbatim into Markdown with LaTeX ($...$ for inline math, $$...$$ for display math).
Rules:
1. Copy ONLY what is visibly written, including mistakes. NEVER correct errors, finish incomplete steps, or solve the problem.
2. Mark crossed-out parts outside math delimiters with ~~...~~ (never put ~~ inside $...$ or $$...$$). Mark illegible symbols or words as [?].
3. For diagrams: use Mermaid (```mermaid ... ```) for flowcharts/trees, equation + key features for graphs, or short structured text for sketches.
4. Output ONLY the transcribed Markdown. No preamble, no commentary, no wrapping code fence around the whole answer."""

PAGE = rb"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>desk-cam</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<style>
:root{
  color-scheme:light;
  --ss-canvas:#f6f5f4;--ss-surface:#fff;--ss-chrome:#fafaf9;--ss-well:#efeeec;--ss-raised:#fff;
  --ss-ink-1:rgba(0,0,0,.04);--ss-ink-2:rgba(0,0,0,.06);--ss-ink-3:rgba(0,0,0,.09);
  --ss-line:rgba(0,0,0,.07);--ss-line-faint:rgba(0,0,0,.045);
  --ss-text:#6e6e73;--ss-text-strong:#1d1d1f;--ss-text-faint:#9a9aa0;
  --ss-accent:#3b82f6;--ss-accent-h:#2563eb;--ss-accent-soft:rgba(59,130,246,.12);
  --ss-success:#22c55e;--ss-success-soft:rgba(34,197,94,.12);--ss-success-text:#15803d;
  --ss-danger:#ef4444;--ss-danger-soft:rgba(239,68,68,.1);--ss-danger-text:#b91c1c;
  --ss-warning-soft:rgba(245,158,11,.14);--ss-warning-text:#b45309;
  --ss-shadow-window:0 0 0 1px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.07);
  --ss-shadow-card:0 1px 2px rgba(0,0,0,.04);
  --ss-font:"Inter",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
  --ss-mono:"JetBrains Mono","SF Mono","SFMono-Regular",ui-monospace,Menlo,monospace;
  --ss-radius-sm:6px;--ss-radius-md:8px;--ss-radius-lg:10px;--ss-radius-window:12px;--ss-radius-pill:999px;
  --ease:cubic-bezier(.22,1,.36,1);
}
[data-theme="dark"]{
  color-scheme:dark;
  --ss-canvas:#111113;--ss-surface:#1a1a1d;--ss-chrome:#1f1f23;--ss-well:#0c0c0e;--ss-raised:#26262a;
  --ss-ink-1:rgba(255,255,255,.05);--ss-ink-2:rgba(255,255,255,.08);--ss-ink-3:rgba(255,255,255,.12);
  --ss-line:rgba(255,255,255,.08);--ss-line-faint:rgba(255,255,255,.05);
  --ss-text:#9d9da3;--ss-text-strong:#ececef;--ss-text-faint:#68686e;
  --ss-accent:#3b82f6;--ss-accent-h:#60a5fa;--ss-accent-soft:rgba(59,130,246,.22);
  --ss-success-soft:rgba(34,197,94,.16);--ss-success-text:#4ade80;
  --ss-danger-soft:rgba(239,68,68,.16);--ss-danger-text:#f87171;
  --ss-warning-soft:rgba(245,158,11,.18);--ss-warning-text:#fbbf24;
  --ss-shadow-window:0 0 0 1px rgba(255,255,255,.08),0 6px 20px rgba(0,0,0,.42);
  --ss-shadow-card:0 0 0 1px rgba(255,255,255,.06);
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{
  background:var(--ss-canvas);color:var(--ss-text-strong);
  font:400 13px/1.45 var(--ss-font);-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;overflow:hidden;padding:12px;gap:12px;
  transition:background .2s var(--ease),color .2s var(--ease);
}
header{
  height:48px;display:flex;align-items:center;gap:8px;padding:0 12px;
  background:var(--ss-chrome);border-radius:var(--ss-radius-window);flex-shrink:0;
  box-shadow:var(--ss-shadow-window);
}
.brand{display:flex;align-items:center;gap:8px;font-weight:600;font-size:13.5px;letter-spacing:-.015em;padding-right:10px;border-right:1px solid var(--ss-line);color:var(--ss-text-strong)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ss-danger);box-shadow:0 0 0 3px var(--ss-danger-soft);transition:all .22s var(--ease);cursor:pointer}
.dot.live{background:var(--ss-success);box-shadow:0 0 0 3px var(--ss-success-soft)}
select,button{
  font:inherit;font-size:12.5px;font-weight:500;height:30px;padding:0 11px;border-radius:var(--ss-radius-md);
  border:0;box-shadow:inset 0 0 0 1px var(--ss-line);background:var(--ss-surface);color:var(--ss-text-strong);cursor:pointer;
  display:inline-flex;align-items:center;gap:6px;text-box:trim-both cap alphabetic;
  transition:transform .16s var(--ease),background .16s var(--ease),box-shadow .16s var(--ease);
}
select{max-width:200px;padding-right:8px}
select:hover,button:hover:not(:disabled){background:var(--ss-ink-1);box-shadow:inset 0 0 0 1px var(--ss-ink-3)}
select:focus-visible,button:focus-visible,textarea:focus-visible{outline:2px solid var(--ss-accent);outline-offset:-1px}
button:active:not(:disabled){transform:scale(.97)}
button:disabled{opacity:.4;cursor:not-allowed}
button.run{background:var(--ss-text-strong);color:var(--ss-surface);font-weight:600;box-shadow:none}
button.run:hover:not(:disabled){opacity:.9;background:var(--ss-text-strong);box-shadow:var(--ss-shadow-card)}
button.primary{background:var(--ss-accent);color:#fff;font-weight:600;box-shadow:inset 0 1px 0 rgba(255,255,255,.18)}
button.primary:hover:not(:disabled){background:var(--ss-accent-h);box-shadow:0 2px 10px var(--ss-accent-soft)}
button.ghost-danger{background:transparent;box-shadow:none;color:var(--ss-danger-text)}
button.ghost-danger:hover:not(:disabled){background:var(--ss-danger-soft);box-shadow:none}
.kbd{font-size:10px;padding:1px 6px;border-radius:var(--ss-radius-pill);background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.22);font-family:var(--ss-mono)}
button.run .kbd{background:var(--ss-ink-2);border-color:var(--ss-ink-3);color:var(--ss-surface)}
.spacer{flex:1}

#workspace{flex:1;display:grid;grid-template-columns:34% 1fr;min-height:0;gap:12px}
.pane{
  background:var(--ss-surface);border-radius:var(--ss-radius-window);display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;
  box-shadow:var(--ss-shadow-window);
}
.pane-head{height:40px;display:flex;align-items:center;gap:8px;padding:0 12px;background:var(--ss-chrome);border-bottom:1px solid var(--ss-line);flex-shrink:0}
.pane-title{font-size:12px;font-weight:600;color:var(--ss-text-strong);letter-spacing:-.01em}
.badge{height:22px;font-size:11px;font-weight:500;padding:0 8px;border-radius:var(--ss-radius-pill);background:var(--ss-ink-1);box-shadow:inset 0 0 0 1px var(--ss-line);color:var(--ss-text);display:inline-flex;align-items:center;text-box:trim-both cap alphabetic;font-family:var(--ss-mono);font-variant-numeric:tabular-nums}
.badge.busy{background:var(--ss-warning-soft);color:var(--ss-warning-text);box-shadow:none}
.badge.ok{background:var(--ss-success-soft);color:var(--ss-success-text);box-shadow:none}

#left-body{flex:1;display:flex;flex-direction:column;min-height:0;padding:12px;gap:10px}
.stage{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:var(--ss-well);box-shadow:inset 0 0 0 1px var(--ss-line);border-radius:var(--ss-radius-md);overflow:hidden;position:relative}
.stage-empty{position:absolute;font-size:12px;color:var(--ss-text-faint);pointer-events:none;display:none}
.stage.is-off .stage-empty{display:block}
video,#snap-img{max-width:100%;max-height:100%;object-fit:contain;display:block;position:relative;z-index:1}
#snap-img{display:none}
.cam-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}

#right-split{flex:1;display:grid;grid-template-columns:1fr 1fr;min-height:0;gap:1px;background:var(--ss-line)}
.subpane{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--ss-surface)}
textarea#md{flex:1;width:100%;border:0;outline:none;resize:none;padding:16px 18px;background:var(--ss-surface);color:var(--ss-text-strong);font:400 13.5px/1.65 var(--ss-mono);tab-size:2}
textarea#md::placeholder{color:var(--ss-text-faint)}
#preview{flex:1;overflow:auto;padding:16px 20px;font:400 14.5px/1.7 var(--ss-font);background:var(--ss-surface);color:var(--ss-text-strong)}
#preview h1,#preview h2,#preview h3{margin:0 0 10px;font-weight:600;letter-spacing:-.015em;line-height:1.3}
#preview h1{font-size:18px}#preview h2{font-size:16px}#preview h3{font-size:14.5px}
#preview p{margin:0 0 10px}
#preview ul,#preview ol{margin:0 0 10px;padding-left:20px}
#preview blockquote{margin:0 0 10px;padding:6px 12px;border-left:2px solid var(--ss-ink-3);color:var(--ss-text)}
#preview pre{background:var(--ss-well);padding:12px 14px;border-radius:var(--ss-radius-md);border:1px solid var(--ss-line);overflow:auto}
#preview code{font-family:var(--ss-mono);font-size:.88em;background:var(--ss-ink-1);padding:1px 5px;border-radius:4px}
#preview pre code{background:none;padding:0}
#preview del{color:var(--ss-danger-text)}
#preview .katex-display{margin:12px 0;overflow-x:auto;overflow-y:hidden}

footer#console{
  height:34px;padding:0 12px;background:var(--ss-chrome);border-radius:var(--ss-radius-lg);
  box-shadow:var(--ss-shadow-card),0 0 0 1px var(--ss-line);
  display:flex;align-items:center;gap:10px;flex-shrink:0;
  font:400 12px/1 var(--ss-font);color:var(--ss-text);
}
#status-line{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#cursor-info{font-family:var(--ss-mono);font-size:11.5px;color:var(--ss-text-faint);font-variant-numeric:tabular-nums}
#status-line.ok{color:var(--ss-success-text)}
#status-line.warn{color:var(--ss-warning-text)}
#status-line.err{color:var(--ss-danger-text)}
input[type=file]{display:none}
@media (prefers-reduced-motion:reduce){*{transition:none !important}}
@media (max-width:1020px){
  #workspace{grid-template-columns:1fr;grid-template-rows:260px 1fr}
  #right-split{grid-template-columns:1fr;grid-template-rows:1fr 1fr}
}
</style>
</head>
<body>
<header>
  <span class="brand"><span class="dot" id="cam-dot" title="Click to toggle camera"></span>desk-cam</span>
  <select id="dev" title="Camera source"></select>
  <button id="rot" title="Rotate 90 degrees">Rotate <span id="deg">0</span>&deg;</button>
  <button id="upload-btn" title="Upload an image">Upload</button>
  <input id="file-in" type="file" accept="image/*">
  <span class="spacer"></span>
  <button id="theme-btn" title="Switch light or dark theme">Dark</button>
  <button id="cap" class="run">Capture <span class="kbd">Space</span></button>
  <button id="confirm" class="primary">Save &amp; copy <span class="kbd">&#8984;&#9166;</span></button>
</header>

<div id="workspace">
  <section class="pane">
    <div class="pane-head">
      <span class="pane-title" id="left-title">Camera</span>
      <span class="spacer"></span>
      <button class="badge" id="cam-pill" title="Toggle camera">off</button>
    </div>
    <div id="left-body">
      <div class="stage is-off" id="stage">
        <span class="stage-empty">Camera paused &mdash; press Space or click live</span>
        <video id="v" autoplay playsinline muted></video>
        <img id="snap-img" alt="Captured page">
      </div>
      <div class="cam-actions" id="photo-actions" style="display:none">
        <button id="retake">Retake</button>
        <button id="retranscribe">Re-transcribe</button>
        <span class="spacer"></span>
        <button id="discard" class="ghost-danger">Discard</button>
      </div>
    </div>
  </section>

  <section class="pane">
    <div id="right-split">
      <div class="subpane">
        <div class="pane-head">
          <span class="pane-title">Editor</span>
          <span class="spacer"></span>
          <span class="badge" id="ocr-badge">idle</span>
        </div>
        <textarea id="md" spellcheck="false" placeholder="Press Space to capture & transcribe, or write Markdown + LaTeX directly..."></textarea>
      </div>
      <div class="subpane">
        <div class="pane-head">
          <span class="pane-title">Preview</span>
          <span class="spacer"></span>
          <span class="badge">KaTeX</span>
        </div>
        <div id="preview"></div>
      </div>
    </div>
  </section>
</div>

<footer id="console">
  <span id="status-line">Starting camera...</span>
  <span id="cursor-info">0 chars</span>
</footer>

<script>
const $ = id => document.getElementById(id);
const v = $('v'), snapImg = $('snap-img'), dev = $('dev'), md = $('md'), preview = $('preview');
const camDot = $('cam-dot'), camPill = $('cam-pill'), degEl = $('deg');
const statusLine = $('status-line'), ocrBadge = $('ocr-badge');
const leftTitle = $('left-title'), photoActions = $('photo-actions'), themeBtn = $('theme-btn'), stage = $('stage');

let theme = localStorage.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
function applyTheme(t) {
  theme = t;
  document.documentElement.dataset.theme = t;
  localStorage.theme = t;
  themeBtn.textContent = t === 'dark' ? 'Light' : 'Dark';
}
applyTheme(theme);
themeBtn.onclick = () => applyTheme(theme === 'dark' ? 'light' : 'dark');

let rot = +(localStorage.rot || 0);
let stream = null;
let idleTimer = null;
let currentPhotoName = sessionStorage.currentPhotoName || '';
let currentPhotoUrl = currentPhotoName ? '/file?name=' + encodeURIComponent(currentPhotoName) : '';
let activeTab = 'cam';

function log(text, kind = '') {
  statusLine.textContent = text;
  statusLine.className = kind;
}

function camLive() {
  return Boolean(stream && stream.getVideoTracks().some(t => t.readyState === 'live'));
}

function syncCamUi() {
  const live = camLive();
  camDot.classList.toggle('live', live);
  stage.classList.toggle('is-off', activeTab === 'cam' && !live);
  if (activeTab === 'photo') {
    camPill.textContent = 'frozen';
    camPill.className = 'badge';
  } else {
    camPill.textContent = live ? 'live' : 'off';
    camPill.className = live ? 'badge ok' : 'badge';
  }
}

function resetIdleTimer() {
  clearTimeout(idleTimer);
  if (camLive()) {
    idleTimer = setTimeout(() => {
      if (camLive()) stopCam('Camera paused after 2m idle to save battery.');
    }, 120000);
  }
}

function applyRot() {
  v.style.transform = `rotate(${rot}deg)`;
  degEl.textContent = rot;
  localStorage.rot = rot;
}

function setLeftTab(tab) {
  activeTab = tab;
  if (tab === 'photo' && currentPhotoUrl) {
    leftTitle.textContent = 'Captured';
    v.style.display = 'none';
    snapImg.src = currentPhotoUrl;
    snapImg.style.display = 'block';
    photoActions.style.display = 'flex';
  } else {
    leftTitle.textContent = 'Camera';
    snapImg.style.display = 'none';
    v.style.display = 'block';
    photoActions.style.display = 'none';
  }
  syncCamUi();
}

function setCurrentPhoto(name, url) {
  currentPhotoName = name || '';
  if (name) sessionStorage.currentPhotoName = name;
  else sessionStorage.removeItem('currentPhotoName');
  currentPhotoUrl = url || '';
}

function renderPreview() {
  const raw = md.value;
  $('cursor-info').textContent = `${raw.length} chars`;
  if (!raw.trim()) {
    preview.innerHTML = '<p style="color:var(--ss-text-faint)">Preview appears here as you capture or type.</p>';
    return;
  }
  if (window.marked) {
    const math = [];
    const safe = raw
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => { math.push('$$' + m + '$$'); return `@@MATH${math.length - 1}@@`; })
      .replace(/\$([^\n$]+?)\$/g, (_, m) => { math.push('$' + m + '$'); return `@@MATH${math.length - 1}@@`; });
    let html = window.marked.parse(safe, { breaks: true, gfm: true });
    html = html.replace(/@@MATH(\d+)@@/g, (_, i) => math[+i]);
    preview.innerHTML = html;
  } else {
    preview.textContent = raw;
  }
  if (window.renderMathInElement) {
    try {
      window.renderMathInElement(preview, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false }
        ],
        throwOnError: false
      });
    } catch (_) {}
  }
}

function stopCam(reason = 'Camera stopped.') {
  clearTimeout(idleTimer);
  if (stream) {
    stream.getTracks().forEach(t => { t.onended = null; t.stop(); });
    stream = null;
  }
  v.srcObject = null;
  syncCamUi();
  log(reason, 'warn');
}

async function startCam(id) {
  clearTimeout(idleTimer);
  if (stream) {
    stream.getTracks().forEach(t => { t.onended = null; t.stop(); });
    stream = null;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { deviceId: id ? { exact: id } : undefined, width: { ideal: 1920 }, height: { ideal: 1080 } }
    });
  } catch (err) {
    syncCamUi();
    throw err;
  }
  v.srcObject = stream;
  const track = stream.getVideoTracks()[0];
  if (track) {
    const activeId = track.getSettings().deviceId;
    if (activeId) localStorage.dev = activeId;
    track.onended = () => {
      clearTimeout(idleTimer);
      stream = null;
      v.srcObject = null;
      syncCamUi();
      log('Camera disconnected. Click Camera or Capture to reconnect.', 'warn');
    };
  }
  syncCamUi();
  resetIdleTimer();
}

async function listCams() {
  const cams = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
  dev.innerHTML = cams.map(c => `<option value="${c.deviceId}">${c.label || 'Camera'}</option>`).join('');
  return cams;
}

async function ensureCam() {
  if (camLive()) return true;
  const cams = await listCams();
  const preferred = dev.value || localStorage.dev;
  const match = cams.find(c => c.deviceId === preferred) || cams.find(c => /iphone/i.test(c.label));
  await startCam(match ? match.deviceId : undefined).catch(() => startCam());
  const activeId = stream?.getVideoTracks()[0]?.getSettings().deviceId;
  if (activeId) dev.value = activeId;
  if (v.readyState < 2) {
    await new Promise(resolve => v.addEventListener('loadeddata', resolve, { once: true }));
  }
  return camLive();
}

async function streamResponse(res, t0) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let text = '';
  let model = '';
  md.value = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const events = buf.split('\n\n');
    buf = events.pop() || '';
    for (const ev of events) {
      for (const line of ev.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const msg = JSON.parse(line.slice(6));
        if (msg.error) throw new Error(msg.error);
        if (msg.name) {
          setCurrentPhoto(msg.name, '/file?name=' + encodeURIComponent(msg.name));
        }
        if (msg.delta) {
          text += msg.delta;
          md.value = text;
          renderPreview();
        }
        if (msg.done) {
          model = msg.model || model;
          if (msg.markdown !== undefined) {
            md.value = msg.markdown;
            renderPreview();
          }
        }
      }
    }
  }
  const secs = ((performance.now() - t0) / 1000).toFixed(2);
  ocrBadge.textContent = `${model || 'ready'} (${secs}s)`;
  ocrBadge.className = 'badge ok';
  log(`Transcribed in ${secs}s (${model}). Edit if needed, then Cmd+Enter.`, 'ok');
  md.focus();
}

async function transcribePhoto(name) {
  ocrBadge.textContent = 'streaming...';
  ocrBadge.className = 'badge busy';
  log('Transcribing ' + name + '...');
  const t0 = performance.now();
  try {
    const res = await fetch('/transcribe?stream=1&name=' + encodeURIComponent(name), { method: 'POST' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Transcription failed');
    }
    await streamResponse(res, t0);
  } catch (err) {
    ocrBadge.textContent = 'manual';
    ocrBadge.className = 'badge';
    log('OCR error: ' + err.message + ' - edit Markdown manually.', 'err');
  }
}

async function saveAndTranscribe(blob) {
  const localUrl = URL.createObjectURL(blob);
  setCurrentPhoto(currentPhotoName || 'capturing...', localUrl);
  setLeftTab('photo');
  ocrBadge.textContent = 'streaming...';
  ocrBadge.className = 'badge busy';
  log('Capturing & transcribing...');
  const t0 = performance.now();
  try {
    const oldName = currentPhotoName && currentPhotoName.startsWith('snap-') ? currentPhotoName : '';
    const res = await fetch('/capture' + (oldName ? '?replace=' + encodeURIComponent(oldName) : ''), { method: 'POST', body: blob });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Capture failed');
    }
    await streamResponse(res, t0);
  } catch (err) {
    ocrBadge.textContent = 'manual';
    ocrBadge.className = 'badge';
    log('OCR error: ' + err.message + ' - edit Markdown manually.', 'err');
  }
}

async function rotateCapturedPhoto() {
  if (!currentPhotoUrl) return;
  const img = new Image();
  img.onload = async () => {
    const c = document.createElement('canvas');
    c.width = img.naturalHeight;
    c.height = img.naturalWidth;
    const ctx = c.getContext('2d');
    ctx.translate(c.width / 2, c.height / 2);
    ctx.rotate(Math.PI / 2);
    ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2);
    const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.85));
    await saveAndTranscribe(blob);
  };
  img.src = currentPhotoUrl + (currentPhotoUrl.includes('?') ? '&' : '?') + 't=' + Date.now();
}

async function capture() {
  if (!camLive()) {
    log('Starting camera...', 'warn');
    try { await ensureCam(); } catch (e) { log('Could not start camera: ' + e.message, 'err'); return; }
  }
  if (!v.videoWidth) { log('Camera frame not ready yet.', 'warn'); return; }
  const w = v.videoWidth, h = v.videoHeight, sideRot = rot % 180 !== 0;
  const s = Math.min(1, 1200 / Math.max(w, h));
  const c = document.createElement('canvas');
  c.width = Math.round((sideRot ? h : w) * s);
  c.height = Math.round((sideRot ? w : h) * s);
  const ctx = c.getContext('2d');
  ctx.translate(c.width / 2, c.height / 2);
  ctx.rotate(rot * Math.PI / 180);
  ctx.drawImage(v, -w * s / 2, -h * s / 2, w * s, h * s);
  const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.80));
  stopCam('Camera paused after capture to save battery.');
  await saveAndTranscribe(blob);
}

async function confirmWork() {
  const text = md.value.trim();
  if (!text) { log('Nothing to save yet.', 'warn'); return; }
  const res = await fetch('/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ markdown: text, photoName: currentPhotoName })
  });
  const data = await res.json();
  if (!res.ok) { log(data.error || 'Save failed.', 'err'); return; }
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
  setCurrentPhoto('', '');
  setLeftTab('cam');
  ocrBadge.textContent = 'saved';
  ocrBadge.className = 'badge ok';
  const note = data.overwrote ? ' (replaced previous unread file)' : '';
  log(`Saved ${data.workPath} & copied to clipboard${note}.`, 'ok');
}

async function discardWork() {
  if (currentPhotoName) {
    await fetch('/delete?name=' + encodeURIComponent(currentPhotoName), { method: 'POST' });
  }
  setCurrentPhoto('', '');
  md.value = '';
  renderPreview();
  ocrBadge.textContent = 'idle';
  ocrBadge.className = 'badge';
  setLeftTab('cam');
  log('Discarded draft.');
}

async function init() {
  syncCamUi();
  if (!navigator.mediaDevices) {
    log('Camera unavailable in this browser context. Use Upload or type Markdown.', 'warn');
    return;
  }
  await startCam(localStorage.dev).catch(() => startCam());
  const cams = await listCams();
  const current = stream?.getVideoTracks()[0]?.getSettings().deviceId;
  const phone = cams.find(c => /iphone/i.test(c.label));
  if (!localStorage.dev && phone && phone.deviceId !== current) await startCam(phone.deviceId);
  const activeId = stream?.getVideoTracks()[0]?.getSettings().deviceId;
  if (activeId) dev.value = activeId;
  applyRot();
  setLeftTab('cam');
  log('Ready. Space to capture, Cmd+Enter to save & copy.', 'ok');
}

const toggleCam = () => {
  if (activeTab === 'photo') {
    setLeftTab('cam');
    ensureCam().then(() => log('Camera started.', 'ok')).catch(e => log('Camera error: ' + e.message, 'err'));
    return;
  }
  camLive() ? stopCam() : ensureCam().then(() => { setLeftTab('cam'); log('Camera started.', 'ok'); }).catch(e => log('Camera error: ' + e.message, 'err'));
};
camPill.onclick = toggleCam;
camDot.onclick = toggleCam;
$('retake').onclick = () => {
  setLeftTab('cam');
  ensureCam().then(() => log('Align page and press Space to capture.', 'ok')).catch(e => log('Camera error: ' + e.message, 'err'));
};
dev.onchange = () => startCam(dev.value).then(() => log('Switched camera.')).catch(e => log('Camera error: ' + e.message, 'err'));
$('rot').onclick = () => {
  if (activeTab === 'photo' && currentPhotoUrl) {
    rotateCapturedPhoto();
    return;
  }
  rot = (rot + 90) % 360;
  applyRot();
};
$('cap').onclick = capture;
$('retranscribe').onclick = () => currentPhotoName && transcribePhoto(currentPhotoName);
$('confirm').onclick = confirmWork;
$('discard').onclick = discardWork;
$('upload-btn').onclick = () => $('file-in').click();
$('file-in').onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  const img = new Image();
  img.onload = async () => {
    const s = Math.min(1, 1200 / Math.max(img.width, img.height));
    const c = document.createElement('canvas');
    c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.80));
    await saveAndTranscribe(blob);
  };
  img.src = URL.createObjectURL(f);
  e.target.value = '';
};

md.addEventListener('input', renderPreview);
function handleKey(e) {
  if ((e.metaKey || e.ctrlKey) && (e.key === 'Enter' || e.code === 'Enter')) {
    e.preventDefault();
    e.stopPropagation();
    confirmWork();
    return;
  }
  const tag = document.activeElement?.tagName;
  if (e.code === 'Space' && document.activeElement !== md && tag !== 'BUTTON' && tag !== 'SELECT' && tag !== 'INPUT') {
    e.preventDefault();
    capture();
  }
}
document.addEventListener('keydown', handleKey, true);
md.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && (e.key === 'Enter' || e.code === 'Enter')) {
    e.preventDefault();
    e.stopPropagation();
    confirmWork();
  }
}, true);

if (navigator.mediaDevices) navigator.mediaDevices.ondevicechange = () => listCams();
document.addEventListener('visibilitychange', () => {
  if (document.hidden && camLive()) stopCam('Camera paused (tab hidden) to save battery.');
});
['click', 'keydown'].forEach(ev => document.addEventListener(ev, resetIdleTimer, true));
window.addEventListener('load', renderPreview);
init().catch(e => log('Camera error: ' + e.message + ' (use Upload or editor)', 'err'));
</script>
</body>
</html>
"""


def _copy_clipboard(text: str) -> bool:
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                return True
            except Exception:
                pass
    return False


def resolve_provider(provider: str = PROVIDER) -> str:
    if provider != "auto":
        return provider
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return "gemini"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.environ.get("OLLAMA_HOST", "").strip():
        return "ollama"
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1):
            return "ollama"
    except Exception:
        pass
    return "gemini"


def active_model(provider: str, model: str = MODEL) -> str:
    if model:
        return model
    return {
        "gemini": "gemini-3.5-flash-lite",
        "openai": "gpt-4.1-mini",
        "anthropic": "claude-sonnet-4-5",
        "ollama": "qwen2.5vl",
    }.get(provider, "gemini-3.5-flash-lite")


def _stream_gemini(key: str, model: str, b64: str, gen_cfg: dict):
    payload = {
        "contents": [{
            "parts": [
                {"text": TRANSCRIBE_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ]
        }],
        "generationConfig": gen_cfg,
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse",
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data: "):
                continue
            chunk = json.loads(line[6:])
            parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            delta = "".join(p.get("text", "") for p in parts)
            if delta:
                yield delta


def _stream_openai(key: str, model: str, b64: str):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "stream": True,
        "temperature": 0.1,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": TRANSCRIBE_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content") or ""
            if delta:
                yield delta


def _stream_anthropic(key: str, model: str, b64: str):
    payload = {
        "model": model,
        "max_tokens": 2048,
        "stream": True,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": TRANSCRIBE_PROMPT},
            ],
        }],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data: "):
                continue
            chunk = json.loads(line[6:])
            if chunk.get("type") == "content_block_delta":
                delta = chunk.get("delta", {}).get("text") or ""
                if delta:
                    yield delta


def _stream_ollama(model: str, b64: str):
    host = (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": True,
        "messages": [{"role": "user", "content": TRANSCRIBE_PROMPT, "images": [b64]}],
    }
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            chunk = json.loads(line)
            delta = chunk.get("message", {}).get("content") or ""
            if delta:
                yield delta


def stream_transcribe_chunks(image_bytes: bytes):
    prov = resolve_provider(PROVIDER)
    model = active_model(prov, MODEL)
    b64 = base64.b64encode(image_bytes).decode("ascii")

    if prov == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("No API key set (GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, or OLLAMA_HOST)")
        attempts = [
            (model, {"temperature": 0.1}),
            ("gemini-3.1-flash-lite-preview", {"temperature": 0.1}),
            ("gemini-3-flash-preview", {"temperature": 0.1, "thinkingConfig": {"thinkingLevel": "minimal"}}),
        ]
        last_err: Exception | None = None
        for m, gen_cfg in attempts:
            sent_any = False
            full = []
            try:
                for delta in _stream_gemini(key, m, b64, gen_cfg):
                    sent_any = True
                    full.append(delta)
                    yield {"delta": delta, "model": m}
                cleaned = "".join(full).strip("\u200b\ufeff \r\n\t") or "[Blank or unreadable page]"
                yield {"done": True, "markdown": cleaned, "model": m}
                return
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="ignore")[:200]
                last_err = RuntimeError(f"Gemini HTTP {e.code}: {detail}")
            except Exception as e:
                last_err = e
            if sent_any:
                raise last_err
        raise last_err or RuntimeError("Transcription failed")

    if prov == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        it = _stream_openai(key, model, b64)
    elif prov == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        it = _stream_anthropic(key, model, b64)
    elif prov == "ollama":
        it = _stream_ollama(model, b64)
    else:
        raise RuntimeError(f"Unknown provider: {prov}")

    full = []
    for delta in it:
        full.append(delta)
        yield {"delta": delta, "model": model}
    cleaned = "".join(full).strip("\u200b\ufeff \r\n\t") or "[Blank or unreadable page]"
    yield {"done": True, "markdown": cleaned, "model": model}


def transcribe_sync(image_bytes: bytes) -> tuple[str, str]:
    full = []
    used_model = active_model(resolve_provider(PROVIDER), MODEL)
    for ev in stream_transcribe_chunks(image_bytes):
        if "delta" in ev:
            full.append(ev["delta"])
        if ev.get("done"):
            return ev["markdown"], ev["model"]
    return ("".join(full).strip("\u200b\ufeff \r\n\t") or "[Blank or unreadable page]"), used_model


class Handler(http.server.BaseHTTPRequestHandler):
    def send_json(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _stream_sse(self, image_bytes: bytes, initial: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            if initial:
                self.wfile.write(f"data: {json.dumps(initial)}\n\n".encode("utf-8"))
                self.wfile.flush()
            for ev in stream_transcribe_chunks(image_bytes):
                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                self.wfile.flush()
        except Exception as exc:
            self.wfile.write(f"data: {json.dumps({'error': str(exc)})}\n\n".encode("utf-8"))
            self.wfile.flush()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            prov = resolve_provider(PROVIDER)
            self.send_json(200, {
                "ok": True,
                "outDir": OUT_DIR,
                "outFile": OUT_FILE,
                "provider": prov,
                "model": active_model(prov, MODEL),
                "frontmatter": FRONTMATTER,
            })
            return

        if parsed.path == "/file":
            name = os.path.basename((qs.get("name") or [""])[0])
            target = os.path.join(OUT_DIR, name)
            if not (name and name.endswith((".jpg", ".jpeg", ".png", ".md")) and os.path.isfile(target)):
                self.send_error(404)
                return
            ctype = "text/markdown; charset=utf-8" if name.endswith(".md") else "image/jpeg"
            with open(target, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"):
            self.send_json(403, {"error": "Forbidden origin"})
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/capture":
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BYTES:
                self.send_json(400, {"error": "Invalid body size"})
                return
            data = self.rfile.read(length)
            if not data.startswith(b"\xff\xd8"):
                self.send_json(400, {"error": "Expected JPEG"})
                return
            os.makedirs(OUT_DIR, exist_ok=True)
            replace = os.path.basename((qs.get("replace") or [""])[0])
            if replace.startswith("snap-") and replace.endswith(".jpg"):
                old_path = os.path.join(OUT_DIR, replace)
                if os.path.isfile(old_path):
                    os.remove(old_path)
            name = time.strftime("snap-%Y%m%d-%H%M%S.jpg")
            path = os.path.join(OUT_DIR, name)
            with open(path, "wb") as f:
                f.write(data)
            print(path, flush=True)
            self._stream_sse(data, initial={"name": name, "path": path})
            return

        if parsed.path == "/transcribe":
            name = os.path.basename((qs.get("name") or [""])[0])
            target = os.path.join(OUT_DIR, name)
            if not (name.startswith("snap-") and name.endswith(".jpg") and os.path.isfile(target)):
                self.send_json(404, {"error": "Photo not found"})
                return
            with open(target, "rb") as f:
                data = f.read()
            if (qs.get("stream") or ["0"])[0] == "1":
                self._stream_sse(data)
                return
            try:
                md_text, used_model = transcribe_sync(data)
                self.send_json(200, {"markdown": md_text, "model": used_model})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/confirm":
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 2 * 1024 * 1024:
                self.send_json(400, {"error": "Invalid payload"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self.send_json(400, {"error": "Invalid JSON"})
                return
            markdown = (payload.get("markdown") or "").strip()
            if not markdown:
                self.send_json(400, {"error": "Empty markdown"})
                return
            photo_name = os.path.basename(payload.get("photoName") or "")
            os.makedirs(OUT_DIR, exist_ok=True)
            work_path = os.path.join(OUT_DIR, OUT_FILE)
            overwrote = os.path.isfile(work_path)
            if FRONTMATTER:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                doc = f"---\nstatus: ready\nverified_by_learner: true\ncaptured_at: {ts}\n---\n\n{markdown}\n"
            else:
                doc = f"{markdown}\n"
            with open(work_path, "w", encoding="utf-8") as f:
                f.write(doc)
            copied = _copy_clipboard(markdown)
            if photo_name.startswith("snap-") and photo_name.endswith(".jpg"):
                photo_path = os.path.join(OUT_DIR, photo_name)
                if os.path.isfile(photo_path):
                    os.remove(photo_path)
            print(f"saved -> {work_path}", flush=True)
            self.send_json(200, {"ok": True, "workPath": work_path, "copied": copied, "overwrote": overwrote})
            return

        if parsed.path == "/delete":
            name = os.path.basename((qs.get("name") or [""])[0])
            target = os.path.join(OUT_DIR, name)
            if name and (name == OUT_FILE or (name.startswith("snap-") and name.endswith(".jpg"))) and os.path.isfile(target):
                os.remove(target)
                self.send_json(200, {"deleted": name})
                return
            self.send_json(404, {"error": "Not found"})
            return

        self.send_json(404, {"error": "Unknown route"})

    def log_message(self, *args):
        pass


def main(argv=None):
    global OUT_DIR, OUT_FILE, PORT, PROVIDER, MODEL, FRONTMATTER
    p = argparse.ArgumentParser(description="Capture handwritten work into Markdown + LaTeX.")
    p.add_argument("--out", default=DEFAULT_OUT, help="Output directory (default: ~/desk-cam or DESK_CAM_OUT)")
    p.add_argument("--file", default=DEFAULT_FILE, help="Output Markdown filename (default: work.md)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local port (default: 8765)")
    p.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["auto", "gemini", "openai", "anthropic", "ollama"], help="Vision provider")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Override model ID")
    p.add_argument("--frontmatter", action="store_true", help="Prepend YAML frontmatter to saved Markdown")
    p.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    args = p.parse_args(argv)
    OUT_DIR = os.path.expanduser(args.out)
    OUT_FILE = os.path.basename(args.file) or DEFAULT_FILE
    PORT = args.port
    PROVIDER = args.provider
    MODEL = args.model
    FRONTMATTER = args.frontmatter

    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"desk-cam: {url} -> {os.path.join(OUT_DIR, OUT_FILE)}  (Ctrl-C to stop)", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
