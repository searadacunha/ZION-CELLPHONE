#!/usr/bin/env python3
"""Fake llama-server for dry runs of tests/bench_agent.py on the Mac (same CLI flags; only --port matters).
Answers tool calls for a few prompts, drives the fib agent task to success, returns code for 'premiers'."""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[sys.argv.index("--port") + 1])


def call(name, args):
    return [{"tool_calls": [{"index": 0, "id": "c1", "function": {"name": name, "arguments": json.dumps(args)}}]}]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = {"/props": {"model_path": "/fake/model.gguf"}}.get(self.path, {"status": "ok"})
        self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs, tools = b["messages"], b.get("tools")
        first = next(m["content"] for m in msgs if m["role"] == "user")
        n_tool = sum(m["role"] == "tool" for m in msgs)
        if tools and msgs[-1]["role"] == "user" and "batterie" in first:
            chunks = call("android", {"action": "battery"})
        elif tools and "fib" in first and n_tool == 0:
            chunks = call("write_file", {"path": "~/seeker-work/bench/fib.py", "content": "print('0 1 1 2 3 5 8 13 21 34')"})
        elif tools and "fib" in first and n_tool == 1 and "git" not in first:
            chunks = call("shell", {"command": "python fib.py"})
        elif "premiers" in first:
            chunks = [{"content": "```python\ndef premiers(n):\n    return [p for p in range(2, n + 1) if all(p % d for d in range(2, p))]\n```"}]
        else:
            chunks = [{"content": "Réponse de test en français."}]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for c in chunks:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': c}]})}\n\n".encode())
        t = {"cache_n": 281, "prompt_n": 40, "prompt_per_second": 30.0, "predicted_n": 12, "predicted_per_second": 6.0}
        self.wfile.write(f"data: {json.dumps({'choices': [], 'timings': t})}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
