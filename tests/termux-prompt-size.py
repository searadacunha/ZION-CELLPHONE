#!/usr/bin/env python3
"""Inside Termux, llama-server running: how many tokens the fixed start of each request weighs (instructions + tool
descriptions), for one or more versions of seeker-ai. The model reads them once (about 20 tokens/s on the Seeker), then
they are kept; the number also says how much of the 4096-token context is left for the work.
  python3 termux-prompt-size.py $PREFIX/bin/seeker-ai [OLDER_COPY ...]"""
import importlib.machinery, importlib.util, json, sys, urllib.request


def count(path, serve=False, drive=False):
    l = importlib.machinery.SourceFileLoader("sa_" + str(abs(hash((path, serve, drive)))), path)
    sa = importlib.util.module_from_spec(importlib.util.spec_from_loader(l.name, l))
    l.exec_module(sa)
    conf = sa.serve_conf() if serve else sa.load_conf()
    if drive:
        conf["tools"] = {**conf["tools"], "ui": "auto"}
    if serve:
        conf["_human"] = True
    tools = sa.make_tools(conf)
    specs = sa.tool_specs(conf, tools)
    body = {"messages": [{"role": "system", "content": sa.system_text(conf, True)}, {"role": "user", "content": "x"}], "tools": specs,
            "chat_template_kwargs": {"enable_thinking": False}}
    post = lambda p, b: json.loads(urllib.request.urlopen(urllib.request.Request(conf["server"] + p, json.dumps(b).encode(),
                                                                                  {"Content-Type": "application/json"}), timeout=120).read())
    prompt = post("/apply-template", body)["prompt"]
    return len(post("/tokenize", {"content": prompt})["tokens"]), len(specs)


for path in sys.argv[1:]:
    for label, kw in (("terminal agent", {}), ("ai screen", {"serve": True}), ("ai screen, may drive apps", {"serve": True, "drive": True})):
        try:
            n, k = count(path, **kw)
            print(f"{path.rsplit('/', 1)[-1]:28} {label:26} {n:5} tokens, {k} tools")
        except Exception as e:
            print(f"{path.rsplit('/', 1)[-1]:28} {label:26} not measured: {type(e).__name__}: {e}")
