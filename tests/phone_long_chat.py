#!/usr/bin/env python3
"""In Termux: seeker-ai's handling of a conversation longer than the context, on the real llama-server.
The default model is started with a 1024-token context, then 14 questions are asked twice:
  reactive   seeker-ai believes the context is huge: the server refuses (HTTP 400), seeker-ai forgets and retries
  proactive  seeker-ai knows the real size: it forgets before the server refuses
Pass = every question gets an answer and old exchanges were forgotten at least once in each mode.
Run: python phone_long_chat.py   (leaves the server stopped)"""
import importlib.machinery, importlib.util, shutil, sys, time
from pathlib import Path

ldr = importlib.machinery.SourceFileLoader("sa", shutil.which("seeker-ai"))
SA = importlib.util.module_from_spec(importlib.util.spec_from_loader("sa", ldr)); ldr.exec_module(SA)
QUESTIONS = ["Présente Lisbonne en 4 phrases.", "Et Porto ?", "Et Faro ?", "Laquelle choisir pour un week-end ? 3 phrases.",
             "Quel plat goûter dans chacune ? 3 lignes.", "Quel budget prévoir ? 3 phrases.", "Comment aller de l'une à l'autre ?",
             "Quelle est la meilleure saison ? 2 phrases.", "Cite un musée dans chacune.", "Résume tes conseils en 3 lignes.",
             "Quelle plage choisir près de Lisbonne ? 2 phrases.", "Et près de Porto ?", "Quel quartier pour dormir à Faro ? 2 phrases.",
             "Donne un dernier conseil pour ce voyage."]  # 14: on 12/11, 10 questions only filled the 1024 tokens

conf = SA.load_conf()
model = Path(conf["model"]).expanduser()
conf.update(ctx=1024, _model=str(model), show_speed=False)
SA.stop_server()
SA.ensure_server(conf, model)
forgot, real = [], SA.forget_oldest
SA.forget_oldest = lambda c, m: (forgot.append(len(m)), real(c, m))[1]
ok = True
for mode, believed in (("reactive", 10 ** 9), ("proactive", 1024)):
    conf.update(ctx=believed, _used=0)
    messages, before, t0 = [{"role": "system", "content": SA.SYSTEM_CHAT}], len(forgot), time.time()
    for i, q in enumerate(QUESTIONS, 1):
        messages.append({"role": "user", "content": q})
        try:
            SA.turn(conf, messages, [], {})
        except SA.ServerError as e:
            print(f"\n[{mode}] question {i}: FAILED {e}")
            ok = False
            break
        print(f"\n[{mode}] question {i}: {len(messages)} messages kept, {conf.get('_used')} tokens in context", flush=True)
    n = len(forgot) - before
    print(f"== {mode}: {'PASS' if n and messages[-1]['role'] == 'assistant' else 'FAIL'}, old exchanges forgotten {n} time(s), "
          f"{time.time() - t0:.0f}s", flush=True)
    ok = ok and bool(n) and messages[-1]["role"] == "assistant"
SA.stop_server()
print("== long chat:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
