import argparse
import json
import os
import sys
import traceback
from flask import Flask, Response, request, stream_with_context

from ytgist.db import add_summary, ensure_video
from ytgist.llm import stream_summary_for_transcript_file, get_llm_models_if_needed
from ytgist.metadata import fetch_title, get_youtube_url
from ytgist.transcript import fetch_transcript_if_needed, get_transcript_path, get_video_id

HOST = os.environ.get("YTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("YTT_PORT", "5005"))
LLM_MODEL = os.environ.get("YTT_LLM_MODEL", "gpt-oss:20b")
LLM_PROMPT = os.environ.get(
    "YTT_LLM_PROMPT",
    "Summarize this video transcript."
)

app = Flask(__name__)

def ndjson(kind, text):
    return json.dumps({"type": kind, "text": text}, ensure_ascii=False) + "\n"

@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")

@app.get("/models")
def models():
    try:
        ms = get_llm_models_if_needed()
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return Response(json.dumps({"error": str(e)}),
                        mimetype="application/json", status=500)
    ids = [m["id"] for m in ms]
    default = LLM_MODEL if LLM_MODEL in ids else (ids[0] if ids else "")
    return Response(json.dumps({"models": ms, "default": default}),
                    mimetype="application/json")

@app.post("/summarize")
def summarize():
    body = request.json or {}
    target = body.get("url", "").strip()
    model = (body.get("model") or LLM_MODEL).strip()
    if not target:
        return Response(ndjson("error", "No URL or video ID given."),
                        mimetype="application/x-ndjson", status=400)

    @stream_with_context
    def generate():
        try:
            yield ndjson("status", "Fetching transcript")
            video_id = get_video_id(target)
            url = get_youtube_url(video_id)
            title = fetch_title(video_id)
            ensure_video(video_id, url, title)
            ts = fetch_transcript_if_needed(target)
            if not ts.strip():
                yield ndjson("error", "Transcript empty.")
                return
 
            yield ndjson("transcript", ts)
            yield ndjson("status", "Summarizing")
 
            path = get_transcript_path(target)
            is_empty = True
            summary = ""
            for chunk in stream_summary_for_transcript_file(path, model, LLM_PROMPT):
                summary += chunk
                if chunk.strip():
                    is_empty = False
                yield ndjson("delta", chunk)
            if is_empty:
                yield ndjson("error",
                             "Model returned nothing. Check `llm logs -n 1`.")
                return
            add_summary(video_id, model, LLM_PROMPT, summary)
            yield ndjson("done", "")
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            yield ndjson("error", str(e))
 
    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Gist</title>
<style>
:root { 
    color-scheme: light dark; 
    --muted: light-dark(#595959, #9e9e9e);
    --danger: light-dark(#b3261e, #ff6b6b);
}
body { font: 16px/1.5 system-ui, sans-serif; margin: 0; }
main { max-width: 46rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { font-size: 1.25rem; }
#f { display: flex; gap: .5rem; margin-bottom: 1rem; }
#url { flex: 1; min-width: 0; padding: .5rem; font: inherit; }
#model { flex: 0 1 auto; max-width: 14rem; padding: .5rem; font: inherit; }
#go { padding: .5rem 1rem; font: inherit; cursor: pointer; }
#go:disabled { opacity: .75; cursor: progress; }
#status { min-height: 1.5em; color: var(--muted); font-size: .875rem; }
#status.error { color: var(--danger); }
summary { cursor: pointer; font-weight: 600; margin: 1rem 0 .5rem; }
#summary > :first-child { margin-top: 0; }
#summary.raw, #transcript { white-space: pre-wrap; font: inherit; }
#transcript { max-height: 60vh; overflow: auto; color: var(--muted); }
</style>
</head>
<body>
<main>
  <h1>YouTube Gist</h1>
  <form id="f">
    <input id="url" name="url" placeholder="YouTube URL or video ID"
           autocomplete="off" autofocus>
    <select id="model" disabled><option value="">Loading models…</option></select>
    <button id="go">Summarize</button>
  </form>
  <div id="status"></div>
  <details id="sw" open hidden>
    <summary>Summary</summary>
    <div id="summary"></div>
  </details>
  <details id="tw" open hidden>
    <summary>Transcript</summary>
    <pre id="transcript"></pre>
  </details>
</main>
<script src="/static/markdown-it.min.js" onerror="window.__noMd = true"></script>
<script>

const f = document.getElementById('f');
const go = document.getElementById('go');
const modelEl = document.getElementById('model');
const statusEl = document.getElementById('status');
const summaryEl = document.getElementById('summary');
const transcriptEl = document.getElementById('transcript');
const sw = document.getElementById('sw');
const tw = document.getElementById('tw');
const md = window.markdownit
    ? window.markdownit({html: false, linkify: true, breaks: false})
    : null;

async function loadModels() {
    try {
        const res = await fetch('/models');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const groups = new Map();
        for (const m of data.models) {
            if (!groups.has(m.provider)) groups.set(m.provider, []);
            groups.get(m.provider).push(m.id);
        }
        modelEl.innerHTML = '';
        for (const [provider, ids] of groups) {
            const og = document.createElement('optgroup');
            og.label = provider;
            for (const id of ids) {
                const o = document.createElement('option');
                o.value = id;
                o.textContent = id;
                og.appendChild(o);
            }
        modelEl.appendChild(og);
    }
    const saved = localStorage.getItem('ytt.model');
    modelEl.value = data.models.some(m => m.id === saved) ? saved : data.default;
    modelEl.disabled = false;
    } catch (err) {
        setStatus('Could not list models: ' + err.message, true);
    }
}
loadModels();
modelEl.addEventListener('change', () => localStorage.setItem('ytt.model', modelEl.value));

function setStatus(text, isError) {
    statusEl.textContent = text;
    statusEl.classList.toggle('error', !!isError);
}

let needsPaint = false;
let raw = '';

function setNeedsPaint() {
    if (needsPaint) { return; }
    needsPaint = true;
    requestAnimationFrame(paintIfNeeded);
}

function paintIfNeeded() {
    if (needsPaint) { paint(); }
}

function paint() {
    if (md) {
        summaryEl.classList.remove('raw');
        summaryEl.innerHTML = md.render(raw);
    } else {
        summaryEl.classList.add('raw');
        summaryEl.textContent = raw;
    }
    needsPaint = false;
}
 
f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = document.getElementById('url').value.trim();
    if (!url) return;
    const model = document.getElementById('model').value.trim();
 
    go.disabled = true;
    raw = '';
    summaryEl.textContent = '';
    transcriptEl.textContent = '';
    sw.hidden = true;
    tw.hidden = true;
    setStatus('Starting', false);
 
    try {
        const res = await fetch('/summarize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url, model})
        });
     
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
     
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            buf += decoder.decode(value, {stream: true});
            const lines = buf.split('\\n');
            buf = lines.pop();
            for (const line of lines) {
                if (!line.trim()) continue;
                const msg = JSON.parse(line);
                if (msg.type === 'status') {
                    setStatus(msg.text, false);
                } else if (msg.type === 'transcript') {
                    transcriptEl.textContent = msg.text;
                    tw.hidden = false;
                } else if (msg.type === 'delta') {
                    raw += msg.text;
                    setNeedsPaint();
                    sw.hidden = false;
                } else if (msg.type === 'error') {
                    setStatus(msg.text, true);
                } else if (msg.type === 'done') {
                    setStatus('', false);
                }
            }
        }
    } catch (err) {
        setStatus(String(err), true);
    } finally {
        go.disabled = false;
    }
});
</script>
</body>
</html>
"""

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ytt-web")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--dev", action="store_true",
        help="Flask reloader; single process, no waitress")
    args = ap.parse_args(argv)

    if args.dev:
        app.run(host=args.host, port=args.port, debug=True, threaded=True)
    else:
        from waitress import serve
        print(f"ytt-web: http://{args.host}:{args.port}", file=sys.stderr)
        serve(app, host=args.host, port=args.port, threads=4)
    return 0