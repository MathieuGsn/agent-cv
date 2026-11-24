"""Lance /adapter-cv via Claude Code en mode headless, depuis le dashboard.

Chaque traitement = un dossier offres/_jobs/<horodatage>/ (ignoré par git) :
    entree.txt     offre collée + en-tête (lien, entreprise, poste, source)
    events.jsonl   sortie stream-json de Claude Code (log en direct)
    stderr.txt     erreurs du processus
    meta.json      date de lancement, session, réponses aux questions

Permissions : passées en ligne de commande (--allowedTools), donc limitées à
ces lancements. Le reste du projet n'est pas modifiable par le headless :
lecture partout, écriture uniquement dans offres/, et seulement les scripts
Python du projet.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "offres" / "_jobs"
TIMEOUT_S = 15 * 60

ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Edit(./offres/**)",  # couvre Write/Edit : écriture uniquement dans offres/
    "Bash(python scripts/build.py:*)",
    "Bash(python scripts/ats_check.py:*)",
    "Bash(python scripts/keyword_score.py:*)",
    "Bash(python scripts/candidatures.py enregistrer:*)",
    "Bash(python scripts/candidatures.py find:*)",
]
DISALLOWED_TOOLS = ["AskUserQuestion", "WebSearch", "Agent", "Task", "NotebookEdit"]

SYSTEM_DASHBOARD = """\
Tu es lancé depuis le dashboard local de Mathieu, en mode non interactif :
personne ne peut te répondre pendant que tu travailles et l'outil
AskUserQuestion n'est pas disponible.
- Suis exactement le workflow /adapter-cv. Les règles de CLAUDE.md ne changent
  pas : zéro invention, une page maximum, vérification ATS.
- Lance les scripts avec l'outil Bash, depuis la racine du projet, sous la
  forme exacte `python scripts/<script>.py ...` : pas de `cd`, pas de `&&`,
  pas de PowerShell. Écris les fichiers avec Write/Edit, uniquement dans offres/.
- Si une question est vraiment indispensable (information manquante, ou
  compétence ambiguë dont la réponse change le CV), arrête-toi AVANT de
  compiler et termine ta réponse par une ligne
  `QUESTION_DASHBOARD: <question courte et compréhensible seule>`.
  Tu seras relancé avec la réponse.
- Si tu ne peux pas aller au bout (erreur de compilation non résolue, outil
  manquant, permission refusée...), termine par
  `ERREUR_DASHBOARD: <ce qui bloque et ce que Mathieu doit faire>`.
- Sinon, termine ton récap par une ligne `DOSSIER_OFFRE: offres/<dossier>`.
"""

ETAPES = [
    "Lecture de l'offre",
    "Analyse de l'offre",
    "Sélection du contenu (cv_adapte.yaml)",
    "Compilation du PDF",
    "Vérification ATS",
    "Score de correspondance",
    "Enregistrement dans le suivi",
]

# Processus en cours, gardés au niveau du module (survit aux reruns Streamlit).
_PROCS: dict[str, subprocess.Popen] = {}

SOURCES_PAR_DOMAINE = {
    "welcometothejungle": "Welcome to the Jungle",
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "jobteaser": "JobTeaser",
    "hellowork": "HelloWork",
    "apec": "APEC",
}


# --------------------------------------------------------------------------- Claude Code

def _version_key(path: str):
    m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", path)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def find_claude() -> str | None:
    """Cherche l'exécutable Claude Code (PATH, install native, npm, extension VS Code)."""
    found = shutil.which("claude")
    if found:
        return found
    home = pathlib.Path.home()
    for p in (
        home / ".local" / "bin" / "claude.exe",
        pathlib.Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
    ):
        if p.exists():
            return str(p)
    exts = []
    for base in (".vscode", ".cursor"):
        exts += glob.glob(str(
            home / base / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude.exe"
        ))
    return max(exts, key=_version_key) if exts else None


def detecter_source(lien: str) -> str:
    lien = (lien or "").lower()
    for domaine, source in SOURCES_PAR_DOMAINE.items():
        if domaine in lien:
            return source
    return ""


def _commande(claude: str, prompt: str, resume: str | None = None) -> list[str]:
    cmd = [claude, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if resume:
        cmd += ["--resume", resume]
    cmd += ["--append-system-prompt", SYSTEM_DASHBOARD]
    cmd += ["--allowedTools", *ALLOWED_TOOLS]
    cmd += ["--disallowedTools", *DISALLOWED_TOOLS]
    return cmd


def _demarrer(job: pathlib.Path, cmd: list[str]) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = open(job / "events.jsonl", "ab")
    err = open(job / "stderr.txt", "ab")
    proc = subprocess.Popen(
        cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
        env=env, creationflags=flags,
    )
    _PROCS[str(job)] = proc
    meta = _meta(job)
    meta["pid"] = proc.pid
    _ecrire_meta(job, meta)


def _pid_vivant(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _en_cours(job: pathlib.Path, meta: dict) -> bool:
    proc = _PROCS.get(str(job))
    if proc is not None:
        return proc.poll() is None
    # Dashboard relancé pendant un traitement : on se fie au pid enregistré.
    return _pid_vivant(meta.get("pid"))


def job_par_nom(nom: str) -> pathlib.Path | None:
    """Retrouve un traitement depuis son nom (paramètre ?job= de l'URL)."""
    if not nom or "/" in nom or "\\" in nom or ".." in nom:
        return None
    j = JOBS_DIR / nom
    return j if (j / "meta.json").exists() else None


def _meta(job: pathlib.Path) -> dict:
    p = job / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _ecrire_meta(job: pathlib.Path, meta: dict) -> None:
    (job / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def lancer(texte: str, lien: str = "", entreprise: str = "", poste: str = "", source: str = "") -> pathlib.Path:
    """Démarre un /adapter-cv en arrière-plan. Retourne le dossier du traitement."""
    claude = find_claude()
    if not claude:
        raise FileNotFoundError("claude")
    job = JOBS_DIR / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    job.mkdir(parents=True, exist_ok=True)
    source = source or detecter_source(lien)
    entete = (
        "---\n"
        f"lien: {lien.strip()}\n"
        f"entreprise: {entreprise.strip()}\n"
        f"poste: {poste.strip()}\n"
        f"source: {source.strip()}\n"
        "---\n"
    )
    (job / "entree.txt").write_text(entete + texte.strip() + "\n", encoding="utf-8")
    rel = (job / "entree.txt").relative_to(ROOT).as_posix()
    _ecrire_meta(job, {"debut": time.time(), "claude": claude, "reponses": []})
    _demarrer(job, _commande(claude, f"/adapter-cv {rel}"))
    return job


def repondre(job: pathlib.Path, reponse: str) -> None:
    """Relance la même session avec la réponse de Mathieu à une question."""
    meta = _meta(job)
    etat_job = etat(job)
    sid = etat_job.get("session_id")
    if not sid:
        raise RuntimeError("Session introuvable : relance le traitement depuis le début.")
    meta.setdefault("reponses", []).append({"question": etat_job.get("question"), "reponse": reponse})
    meta["debut_reprise"] = time.time()
    _ecrire_meta(job, meta)
    prompt = (
        f"Réponse de Mathieu à ta question : {reponse}\n"
        "Reprends le workflow /adapter-cv là où tu t'es arrêté, jusqu'au bout."
    )
    _demarrer(job, _commande(meta.get("claude") or find_claude(), prompt, resume=sid))


def arreter(job: pathlib.Path) -> None:
    proc = _PROCS.get(str(job))
    meta = _meta(job)
    if proc and proc.poll() is None:
        proc.kill()
    elif _pid_vivant(meta.get("pid")):
        subprocess.run(["taskkill", "/PID", str(meta["pid"]), "/T", "/F"], capture_output=True)
    meta["arrete"] = True
    _ecrire_meta(job, meta)


# --------------------------------------------------------------------------- lecture de l'état

def _court(texte: str, n: int = 140) -> str:
    texte = " ".join(str(texte).split())
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def _rel(p: str) -> str:
    try:
        return pathlib.Path(p).resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return p


def _decrire_outil(nom: str, inp: dict) -> str:
    if nom == "Bash":
        return "▶ " + _court(inp.get("command", ""), 160)
    if nom in ("Write", "Edit"):
        return f"✎ {'Écrit' if nom == 'Write' else 'Modifie'} {_rel(inp.get('file_path', ''))}"
    if nom == "Read":
        return f"📖 Lit {_rel(inp.get('file_path', ''))}"
    if nom in ("Glob", "Grep"):
        return f"🔎 {nom} {inp.get('pattern', '')}"
    return f"• {nom}"


def _etape_de(texte: str) -> int:
    """Indice (1-based) de l'étape atteinte, d'après un appel d'outil."""
    t = texte.lower()
    if "candidatures.py enregistrer" in t:
        return 7
    if "keyword_score.py" in t:
        return 6
    if "ats_check.py" in t:
        return 5
    if "build.py" in t:
        return 4
    if "cv_adapte.yaml" in t:
        return 3
    if "analyse.md" in t or "keywords.txt" in t:
        return 2
    if "offre.txt" in t or "entree.txt" in t:
        return 1
    return 0


def _trouver_dossier(texte_final: str, debut: float) -> pathlib.Path | None:
    m = re.search(r"DOSSIER_OFFRE:\s*`?([^\s`]+)", texte_final or "")
    if m:
        d = ROOT / m.group(1).strip().rstrip("/")
        if d.exists():
            return d
    # Repli : dossier d'offre dont resultat.json a été écrit pendant ce traitement.
    best = None
    for r in (ROOT / "offres").glob("*/resultat.json"):
        if r.parent.name.startswith("_"):
            continue
        if r.stat().st_mtime >= debut - 5 and (best is None or r.stat().st_mtime > best.stat().st_mtime):
            best = r
    return best.parent if best else None


def etat(job: pathlib.Path) -> dict:
    """Lit les fichiers du traitement et résume où il en est."""
    meta = _meta(job)
    log, etape, session_id, resultat = [], 0, None, None
    events = job / "events.jsonl"
    if events.exists():
        for ligne in events.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            session_id = ev.get("session_id") or session_id
            if ev.get("type") == "assistant":
                for bloc in ev.get("message", {}).get("content", []):
                    if bloc.get("type") == "tool_use":
                        desc = _decrire_outil(bloc.get("name", ""), bloc.get("input", {}))
                        log.append(desc)
                        etape = max(etape, _etape_de(json.dumps(bloc.get("input", {}), ensure_ascii=False)))
                    elif bloc.get("type") == "text" and bloc.get("text", "").strip():
                        log.append("💬 " + _court(bloc["text"], 300))
            elif ev.get("type") == "user":
                for bloc in ev.get("message", {}).get("content", []) or []:
                    if isinstance(bloc, dict) and bloc.get("type") == "tool_result" and bloc.get("is_error"):
                        contenu = bloc.get("content")
                        if isinstance(contenu, list):
                            contenu = " ".join(c.get("text", "") for c in contenu if isinstance(c, dict))
                        log.append("⚠ " + _court(contenu or "erreur d'outil", 240))
            elif ev.get("type") == "result":
                resultat = ev  # le dernier "result" (après une reprise) gagne

    proc = _PROCS.get(str(job))
    en_cours = _en_cours(job, meta)
    stderr = (job / "stderr.txt").read_text(encoding="utf-8", errors="replace") if (job / "stderr.txt").exists() else ""
    debut = meta.get("debut_reprise") or meta.get("debut") or time.time()

    base = {"log": log, "etape": etape, "session_id": session_id, "etapes": ETAPES,
            "duree": int(time.time() - (meta.get("debut") or time.time())), "stderr": stderr}

    if en_cours:
        if time.time() - debut > TIMEOUT_S:
            arreter(job)
            return {**base, "statut": "erreur", "type_erreur": "timeout",
                    "message": f"Le traitement a dépassé {TIMEOUT_S // 60} minutes et a été arrêté."}
        return {**base, "statut": "en_cours"}

    if meta.get("arrete"):
        return {**base, "statut": "erreur", "type_erreur": "arrete", "message": "Traitement arrêté."}

    # Après une reprise, le dernier "result" du fichier est celui de la reprise.
    texte = (resultat or {}).get("result") or ""

    if not resultat:
        if not events.exists():
            return {**base, "statut": "erreur", "type_erreur": "perdu",
                    "message": "Ce traitement n'est plus suivi (le dashboard a été redémarré)."}
        return {**base, "statut": "erreur", "type_erreur": _type_erreur(stderr, ""),
                "message": "Claude Code s'est arrêté sans résultat."}

    m_q = re.search(r"QUESTION_DASHBOARD:\s*(.+)", texte)
    m_e = re.search(r"ERREUR_DASHBOARD:\s*(.+)", texte, re.S)
    if resultat.get("is_error") or resultat.get("subtype") not in (None, "success"):
        return {**base, "statut": "erreur", "type_erreur": _type_erreur(stderr, texte),
                "message": texte or resultat.get("subtype", "Erreur inconnue"), "texte": texte}
    if m_q:
        return {**base, "statut": "question", "question": m_q.group(1).strip(), "texte": texte}
    if m_e:
        return {**base, "statut": "erreur", "type_erreur": _type_erreur(stderr, texte),
                "message": m_e.group(1).strip(), "texte": texte}
    dossier = _trouver_dossier(texte, meta.get("debut") or 0)
    if not dossier:
        return {**base, "statut": "erreur", "type_erreur": "dossier",
                "message": "Le traitement est terminé mais aucun dossier d'offre n'a été trouvé.",
                "texte": texte}
    return {**base, "statut": "termine", "dossier": dossier, "texte": texte,
            "cout_usd": resultat.get("total_cost_usd")}


def _type_erreur(stderr: str, texte: str) -> str:
    t = f"{stderr}\n{texte}".lower()
    if "login" in t or "api key" in t or "authenticat" in t or "unauthorized" in t:
        return "connexion"
    if "pdflatex" in t or "latex" in t or ".log" in t and "compil" in t:
        return "latex"
    if "permission" in t or "not allowed" in t or "denied" in t:
        return "permission"
    if "usage limit" in t or "rate limit" in t:
        return "limite"
    return "autre"


CONSEILS_ERREUR = {
    "claude_introuvable": (
        "Claude Code est introuvable sur ce PC. Ouvre VS Code une fois (l'extension Claude Code "
        "contient l'exécutable), ou installe la version terminal : "
        "`irm https://claude.ai/install.ps1 | iex` dans PowerShell, puis relance le dashboard."
    ),
    "connexion": (
        "Claude Code n'est pas connecté à ton compte. Ouvre un terminal, tape `claude`, "
        "fais `/login`, puis relance le traitement."
    ),
    "latex": (
        "La compilation LaTeX a échoué. Ouvre le dossier de l'offre et regarde le fichier `.log` "
        "à côté du `.tex`, ou lance `/adapter-cv` dans VS Code pour corriger avec l'agent. "
        "Si MiKTeX demande d'installer un paquet, accepte-le puis relance."
    ),
    "permission": (
        "L'agent a voulu faire une action non autorisée en mode dashboard. "
        "Relance le traitement ; si ça se reproduit, lance `/adapter-cv` depuis VS Code."
    ),
    "limite": "Limite d'utilisation de Claude atteinte. Réessaie plus tard.",
    "timeout": "Le traitement a pris trop de temps. Relance-le ; si ça recommence, essaie depuis VS Code.",
    "dossier": "Regarde le log ci-dessous, puis relance le traitement ou lance `/adapter-cv` depuis VS Code.",
    "perdu": "Relance le traitement.",
    "arrete": "Tu peux relancer le traitement quand tu veux.",
    "autre": "Regarde le log ci-dessous. Si le problème persiste, lance `/adapter-cv` depuis VS Code.",
}
