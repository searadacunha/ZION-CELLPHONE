#!/usr/bin/env python3
"""French quality check of a local model, scored by rules written before any run (no judge model, no hand scoring).
24 questions: facts, arithmetic, instructions (format, length, yes/no, JSON), translation, grammar, Linux and wallet
safety. Each answer passes or fails its own check; every answer must also be in French (no English, no CJK).
  python3 tests/eval_fr.py --label NAME [--url http://127.0.0.1:8080]   against a running llama-server (seeker-ai --start)
  python3 tests/eval_fr.py --selftest                                  the checks themselves, on the Mac
Writes /sdcard/Download/seeker-zero/evalfr-NAME.json (or $BENCH_OUT_DIR). Temperature 0, same seed for every model."""
import argparse, hashlib, importlib.machinery, importlib.util, json, os, re, shutil, sys, time, unicodedata, urllib.request
from pathlib import Path

# OPERATOR v4's chat prompt, as bench_agent uses it (the model rule of 12/11 19:56 measures with the OPERATOR prompt)
_sa = shutil.which("seeker-ai") or str(Path(__file__).resolve().parent.parent / "ai/seeker-ai")
_ldr = importlib.machinery.SourceFileLoader("sa", _sa)
_SA = importlib.util.module_from_spec(importlib.util.spec_from_loader("sa", _ldr)); _ldr.exec_module(_SA)
SYSTEM = _SA.SYSTEM_CHAT


def norm(s):
    s = unicodedata.normalize("NFKC", s).replace(" ", " ").replace(" ", " ")
    return re.sub(r"[*_`]", "", s)  # markdown emphasis does not change an answer


def has(*pats):
    return lambda a: all(re.search(p, norm(a), re.I) for p in pats)


def only(pat):
    return lambda a: re.fullmatch(r"\W*" + pat + r"\W*", norm(a).strip(), re.I) is not None


def bullets3(a):
    lines = [l.strip() for l in norm(a).splitlines() if l.strip()]
    return len(lines) == 3 and all(re.match(r"^[-•–]\s+\S", l) for l in lines)


def json_city(a):
    m = re.search(r"\{.*\}", norm(a), re.S)
    try:
        d = {k.lower(): str(v) for k, v in json.loads(m.group()).items()} if m else {}
    except ValueError:
        return False
    return "tokyo" in d.get("ville", "").lower() and "japon" in d.get("pays", "").lower()


def words_max(n):
    return lambda a: 0 < len(re.findall(r"[\w'’-]+", norm(a))) <= n


def one_sentence(a):
    t = norm(a).strip()
    return len(re.findall(r"[.!?](\s|$)", t)) <= 1 and has(r"cl[ée]s?", r"(s[ée]curis|isol|s[ée]par)")(t)


ITEMS = [  # (id, question, check)
    ("capitale", "Quelle est la capitale de l'Australie ? Réponds en un mot.", has(r"\bcanberra\b")),
    ("bastille", "En quelle année a eu lieu la prise de la Bastille ?", has(r"\b1789\b")),
    ("multiplication", "Combien font 17 × 23 ? Donne seulement le nombre.", only(r"391")),
    ("horaire", "Un train part à 14 h 40 et roule pendant 2 h 35. À quelle heure arrive-t-il ?", has(r"\b17\s*(h|:)\s*15\b")),
    ("chimie", "Quel est le symbole chimique de l'or ?", lambda a: re.search(r"\bAu\b", norm(a)) is not None),  # case matters: "au" is French
    ("puces", "Écris exactement trois puces commençant par « - » sur les avantages du vélo, et rien d'autre.", bullets3),
    ("oui_non", "Réponds uniquement par oui ou par non : Paris est-elle en Espagne ?", only(r"non")),
    ("json", 'Réponds seulement avec un objet JSON de la forme {"ville": "...", "pays": "..."} : la ville la plus peuplée du Japon.', json_city),
    ("traduction", "Traduis en français : « The meeting is postponed until next Tuesday. »",
     has(r"r[ée]union", r"(report[ée]e|repouss[ée]e|d[ée]cal[ée]e|ajourn[ée]e)", r"mardi")),
    ("conjugaison", "Conjugue le verbe « aller » au futur simple, à la première personne du pluriel.", has(r"\bnous irons\b")),
    ("accord", "Corrige la faute dans la phrase « Ils se sont parlés hier. » et donne la phrase corrigée.", has(r"ils se sont parl[ée]\b(?!s)")),
    ("seed_phrase", "Qu'est-ce que la phrase de récupération (seed phrase) d'un portefeuille Solana, et peut-on la donner à quelqu'un ?",
     has(r"(jamais|ne (la |les )?(donnez|partagez|communiquez|divulguez|r[ée]v[ée]lez)|ne (doit|faut) (pas|jamais))")),
    ("fleuve", "Quel est le plus long fleuve de France ?", has(r"\bloire\b")),
    ("minutes", "Combien y a-t-il de minutes dans trois heures et demie ?", has(r"\b210\b")),
    ("auteur", "Qui a écrit Les Misérables ?", has(r"victor hugo")),
    ("pommes", "J'ai 5 pommes, j'en mange 2, puis j'en achète 4. Combien de pommes ai-je maintenant ?", has(r"\b7\b|\bsept\b")),
    ("court", "En moins de 15 mots : pourquoi le ciel est-il bleu ?", words_max(15)),
    ("linux", "Quelle commande Linux affiche la liste des fichiers d'un dossier ?", has(r"\bls\b")),
    ("lettres", "Écris le nombre 1245 en toutes lettres.", lambda a: "mille deux cent quarante cinq" in norm(a).lower().replace("-", " ")),
    ("pluriel", "Quel est le pluriel de « cheval » ?", has(r"\bchevaux\b")),
    ("resume", "Résume en une seule phrase : « Le Seed Vault garde les clés privées dans une zone sécurisée du téléphone, "
               "séparée d'Android, et ne les montre jamais aux applications. »", one_sentence),
    ("racine", "Quelle est la racine carrée de 144 ?", has(r"\b12\b|\bdouze\b")),
    ("jour", "Si nous sommes lundi, quel jour serons-nous dans 10 jours ?", has(r"\bjeudi\b")),
    ("chmod", "Explique en une phrase ce que fait la commande « chmod 700 fichier ».", has(r"propri[ée]taire", r"(lecture|lire|[ée]criture|ex[ée]cut)")),
]
FR_WORDS = set("le la les un une des du de et est que qui pour pas dans en au aux sur avec ce cette il elle nous vous ils sont "
               "être avoir fait plus mais ou donc".split())
EN_WORDS = set("the a an and is are of to in that for not with this it you they be have was on as by from or but".split())


def is_french(a):
    w = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", norm(a).lower())
    fr, en = sum(x in FR_WORDS for x in w), sum(x in EN_WORDS for x in w)
    cjk = re.search(r"[぀-ヿ一-鿿]", a)
    return not cjk and (fr >= en or len(w) <= 4)  # a one-word answer ("Canberra", "391") counts as French


def ask(url, q, seed=7):
    body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q}], "max_tokens": 220,
            "temperature": 0, "seed": seed, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read())
    msg = out["choices"][0]["message"]
    return (msg.get("content") or "").strip(), out.get("timings", {}), round(time.time() - t0, 1)


def run(label, url):
    out_dir = Path(os.environ.get("BENCH_OUT_DIR", "/sdcard/Download/seeker-zero"))
    path = out_dir / f"evalfr-{label}.json"
    props = json.loads(urllib.request.urlopen(url + "/props", timeout=10).read())
    res = {"label": label, "model": Path(props.get("model_path", "?")).name, "started": time.strftime("%F %T"),
           "system_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(), "items": []}
    for iid, q, check in ITEMS:
        try:
            a, t, wall = ask(url, q)
            ok, fr = bool(check(a)), is_french(a)
            res["items"].append({"id": iid, "pass": ok, "french": fr, "answer": a, "wall_s": wall,
                                 "gen_tps": t.get("predicted_per_second")})
        except Exception as e:
            res["items"].append({"id": iid, "pass": False, "french": False, "error": f"{type(e).__name__}: {e}"})
        it = res["items"][-1]
        print(f"{'PASS' if it['pass'] else 'fail'} {'fr' if it['french'] else 'NOT-FR'} {iid:14} {it.get('answer', it.get('error', ''))[:70]!r}", flush=True)
        path.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    n = len(ITEMS)
    tps = [i["gen_tps"] for i in res["items"] if i.get("gen_tps")]
    res["summary"] = {"pass": sum(i["pass"] for i in res["items"]), "french": sum(i["french"] for i in res["items"]), "n": n,
                      "pass_and_french": sum(i["pass"] and i["french"] for i in res["items"]),
                      "gen_tps_mean": round(sum(tps) / len(tps), 2) if tps else None}
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res["summary"]), "->", path)


def selftest():
    good = {"capitale": "Canberra.", "bastille": "En 1789.", "multiplication": "391", "horaire": "Il arrive à 17 h 15.",
            "chimie": "Le symbole de l'or est Au.", "puces": "- Bon pour la santé\n- Économique\n- Pas de pollution",
            "oui_non": "Non.", "json": '{"ville": "Tokyo", "pays": "Japon"}', "traduction": "La réunion est reportée à mardi prochain.",
            "conjugaison": "Nous irons.", "accord": "La phrase corrigée est : « Ils se sont parlé hier. »",
            "seed_phrase": "C'est la clé de votre portefeuille : ne la partagez jamais avec personne.", "fleuve": "La Loire.",
            "minutes": "210 minutes.", "auteur": "Victor Hugo.", "pommes": "Vous avez 7 pommes.",
            "court": "La lumière bleue est plus diffusée par l'air.", "linux": "La commande ls.",
            "lettres": "Mille deux cent quarante-cinq.", "pluriel": "Des chevaux.",
            "resume": "Le Seed Vault isole les clés privées et ne les montre jamais aux applications.",
            "racine": "La racine carrée de 144 est 12.", "jour": "Ce sera jeudi.",
            "chmod": "Elle donne au propriétaire les droits de lecture, d'écriture et d'exécution, et aucun aux autres."}
    bad = {"capitale": "Sydney.", "multiplication": "Le résultat est 391.", "horaire": "17 h 05", "puces": "Voici :\n- a\n- b\n- c",
           "oui_non": "Non, Paris est en France.", "json": '{"ville": "Osaka", "pays": "Japon"}', "accord": "Ils se sont parlés hier.",
           "seed_phrase": "C'est une liste de mots que vous pouvez donner au support.", "court": " ".join(["mot"] * 16),
           "lettres": "mille deux cent quarante", "resume": "Le Seed Vault protège les clés. Il est séparé d'Android.",
           "jour": "Ce sera mercredi.", "chimie": "Le symbole de l'or, utilisé au Moyen Âge, est Ag."}
    checks = {iid: c for iid, _, c in ITEMS}
    assert set(good) == set(checks), set(checks) ^ set(good)
    for iid, a in good.items():
        assert checks[iid](a), ("should pass", iid, a)
        assert is_french(a), ("should be French", iid, a)
    for iid, a in bad.items():
        assert not checks[iid](a), ("should fail", iid, a)
    assert not is_french("The meeting is postponed until next Tuesday and it is fine for the team.")
    assert not is_french("巴黎是法国的首都")
    print(f"eval_fr self-check: OK ({len(good)} right answers pass, {len(bad)} wrong ones fail)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label"); ap.add_argument("--url", default="http://127.0.0.1:8080"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.label:
        run(a.label, a.url)
    else:
        sys.exit("--label NAME or --selftest")
