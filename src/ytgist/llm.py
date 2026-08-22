import os
import shutil
import subprocess

LLM_BIN = os.environ.get("YTT_LLM_BIN", shutil.which("llm") or "llm")

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

def parse_models(out):
    """`llm models list` prints 'Provider: model-id (aliases: x, y)'."""
    models = []
    for line in out.splitlines():
        provider, sep, rest = line.partition(": ")
        if not sep:
            continue
        model_id = rest.split(" (aliases:")[0].strip()
        if model_id:
            models.append({"id": model_id, "provider": provider.strip()})
    return models

_llm_models_cache = None

def get_llm_models():
    global _llm_models_cache
    out, err, rc = run_capture([LLM_BIN, "models", "list"])
    if rc != 0:
        raise RuntimeError(err.strip() or f"llm models list exited {rc}")
    _llm_models_cache = parse_models(out)
    return _llm_models_cache

def get_llm_models_if_needed():
    global _llm_models_cache
    if _llm_models_cache is None:
        return get_llm_models()
    else:
        return _llm_models_cache

def stream_summary_for_transcript_file(path, model, prompt):
    return run_stream([LLM_BIN, "-m", model, "-f", str(path), "-o", "num_ctx", "32768", prompt])
