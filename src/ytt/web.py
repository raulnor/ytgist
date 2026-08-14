import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from flask import Flask, Response, request, stream_with_context

from ytt.transcript import get_transcript_path, fetch_transcript_if_needed

HOST = os.environ.get("YTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("YTT_PORT", "5005"))
LLM_BIN = os.environ.get("YTT_LLM_BIN", shutil.which("llm") or "llm")
LLM_MODEL = os.environ.get("YTT_LLM_MODEL", "gpt-oss:20b")
PROMPT = os.environ.get(
    "YTT_LLM_PROMPT",
    "Summarize this video transcript."
)

app = Flask(__name__)

def ndjson(kind, text):
    return json.dumps({"type": kind, "text": text}, ensure_ascii=False) + "\n"
 
 
def run_capture(cmd):
    """Run to completion. Returns (stdout, stderr, returncode)."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout, p.stderr, p.returncode
 
 
def run_stream(cmd):
    """Yield stdout chunks as they arrive. Raises RuntimeError on failure.
 
    read1() returns as soon as any bytes are available; readline() would block
    until a newline, which a generated summary may not produce for a while.
    Children get PYTHONUNBUFFERED so a Python child doesn't block-buffer its
    pipe and hand us everything at the end.
    """
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        while chunk := p.stdout.read1(4096):
            yield chunk.decode("utf-8", errors="replace")
    finally:
        p.stdout.close()
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        err = p.stderr.read().decode("utf-8", errors="replace")
        p.stderr.close()
        if p.returncode not in (0, -15, -9):
            raise RuntimeError(err.strip() or f"{cmd[0]} exited {p.returncode}")

@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")

@app.post("/summarize")
def summarize():
    target = (request.json or {}).get("url", "").strip()
    if not target:
        return Response(ndjson("error", "No URL or video ID given."),
                        mimetype="application/x-ndjson", status=400)
 
    @stream_with_context
    def generate():
        tmp = None
        try:
            yield ndjson("status", "Fetching transcript")
            ts = fetch_transcript_if_needed(target)
            if not ts.strip():
                yield ndjson("error", err.strip() or "Transcript empty.")
                return
 
            yield ndjson("transcript", ts)
            yield ndjson("status", "Summarizing")
 
            path = get_transcript_path(target)
            is_empty = True
            for chunk in run_stream([LLM_BIN, "-m", LLM_MODEL, "-f", str(path), PROMPT]):
                if chunk.strip():
                    is_empty = False
                yield ndjson("delta", chunk)
            if is_empty:
                yield ndjson("error",
                             "Model returned nothing. Check `llm logs -n 1`.")
                return

 
            yield ndjson("done", "")
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            yield ndjson("error", str(e))
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)
 
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
<title>ytt</title>
<style></style>
</head>
<body>
<main>
  <h1>ytt</h1>
  <form id="f">
    <input id="url" name="url" placeholder="YouTube URL or video ID"
           autocomplete="off" autofocus>
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
const statusEl = document.getElementById('status');
const summaryEl = document.getElementById('summary');
const transcriptEl = document.getElementById('transcript');
const sw = document.getElementById('sw');
const tw = document.getElementById('tw');
const md = window.markdownit
    ? window.markdownit({html: false, linkify: true, breaks: false})
    : null;
 
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
      body: JSON.stringify({url})
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
        if (msg.type === 'status') setStatus(msg.text, false);
        else if (msg.type === 'transcript') {
          transcriptEl.textContent = msg.text;
          tw.hidden = false;
        }
        else if (msg.type === 'delta') {
          raw += msg.text;
          setNeedsPaint();
          sw.hidden = false;
        }
        else if (msg.type === 'error') setStatus(msg.text, true);
        else if (msg.type === 'done') setStatus('', false);
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