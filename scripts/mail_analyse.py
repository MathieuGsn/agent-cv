"""Analyse d'un mail de recruteur (option C : sans connexion à la boîte mail).

Entrées : texte collé, fichier .eml ou .msg (Outlook). Tout est local.
Sortie : une *proposition* (candidature concernée, type de réponse, nouveau
statut, date d'entretien éventuelle). Rien n'est modifié ici : c'est le
dashboard qui applique, après validation de Mathieu.

Usage CLI (test) :
    python scripts/mail_analyse.py chemin/vers/mail.eml
"""
from __future__ import annotations

import datetime as dt
import email
import email.policy
import email.utils
import hashlib
import html
import os
import pathlib
import re
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import candidatures as C  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAILS_DIR = pathlib.Path(os.environ["AGENT_CV_MAILS"]) if os.environ.get("AGENT_CV_MAILS") else ROOT / "mails"

# --------------------------------------------------------------------------- lecture

def _html_vers_texte(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n\n", h)).strip()


def _adresse(valeur: str) -> tuple[str, str]:
    nom, adr = email.utils.parseaddr(valeur or "")
    return nom.strip().strip('"'), adr.strip().lower()


def lire_eml(data: bytes) -> dict:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    corps = ""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        contenu = part.get_content()
        corps = _html_vers_texte(contenu) if part.get_content_type() == "text/html" else contenu
    nom, adr = _adresse(str(msg.get("From", "")))
    date = None
    try:
        date = email.utils.parsedate_to_datetime(str(msg.get("Date"))).date()
    except (TypeError, ValueError):
        pass
    return {"expediteur_nom": nom, "expediteur_email": adr, "objet": str(msg.get("Subject", "") or ""),
            "date": date, "corps": corps.strip()}


def lire_msg(data: bytes) -> dict:
    try:
        import extract_msg
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Lecture des .msg impossible : installe-la avec  python -m pip install extract-msg") from e
    m = extract_msg.openMsg(data)
    try:
        corps = m.body or ""
        if not corps.strip() and m.htmlBody:
            h = m.htmlBody.decode("utf-8", "replace") if isinstance(m.htmlBody, bytes) else m.htmlBody
            corps = _html_vers_texte(h)
        nom, adr = _adresse(m.sender or "")
        date = m.date.date() if isinstance(m.date, dt.datetime) else None
        return {"expediteur_nom": nom, "expediteur_email": adr, "objet": m.subject or "",
                "date": date, "corps": corps.strip()}
    finally:
        m.close()


_ENTETES = {
    "expediteur": r"(?:de|from|exp[ée]diteur)",
    "objet": r"(?:objet|subject)",
    "date": r"(?:date|envoy[ée]|sent)",
}


def lire_texte(texte: str) -> dict:
    """Texte collé depuis Outlook/Gmail : on récupère les en-têtes s'ils sont là."""
    lignes = texte.strip().splitlines()
    infos = {"expediteur_nom": "", "expediteur_email": "", "objet": "", "date": None}
    corps_debut = 0
    for i, l in enumerate(lignes[:12]):
        m = re.match(r"^\s*(\w[\w ]*?)\s*:\s*(.+)$", l)
        if not m:
            continue
        cle, val = m.group(1).strip().lower(), m.group(2).strip()
        if re.fullmatch(_ENTETES["expediteur"], cle):
            infos["expediteur_nom"], infos["expediteur_email"] = _adresse(val)
            if not infos["expediteur_email"]:
                infos["expediteur_nom"] = val
            corps_debut = i + 1
        elif re.fullmatch(_ENTETES["objet"], cle):
            infos["objet"] = val
            corps_debut = i + 1
        elif re.fullmatch(_ENTETES["date"], cle):
            infos["date"] = _date_libre(val)
            corps_debut = i + 1
        elif cle in ("à", "a", "to", "cc"):
            corps_debut = i + 1
    if not infos["expediteur_email"]:
        m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texte)
        if m:
            infos["expediteur_email"] = m.group(0).lower()
    infos["corps"] = "\n".join(lignes[corps_debut:]).strip()
    return infos


def lire_fichier(nom: str, data: bytes) -> dict:
    ext = pathlib.Path(nom).suffix.lower()
    if ext == ".eml":
        return lire_eml(data)
    if ext == ".msg":
        return lire_msg(data)
    return lire_texte(data.decode("utf-8", "replace"))


def empreinte(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:20]


# --------------------------------------------------------------------------- classification

# (type, mots-clés normalisés sans accents, poids). Le type le plus « fort » gagne.
TYPES = {
    "offre": {
        "libelle": "Offre", "statut": "Offre reçue", "famille": "positif",
        "mots": [("proposition de stage", 4), ("offre de stage", 3), ("pleased to offer", 4), ("offer letter", 4),
                 ("convention de stage", 3), ("nous sommes heureux de vous proposer", 4),
                 ("ravis de vous accueillir", 3), ("bienvenue dans l equipe", 3), ("welcome aboard", 3)],
    },
    "refus": {
        "libelle": "Refus", "statut": "Refusé", "famille": "negatif",
        "mots": [("malheureusement", 3), ("ne pas donner suite", 4), ("pas donner une suite favorable", 4),
                 ("ne donnerons pas suite", 4), ("pas pu donner une suite favorable", 4), ("suite defavorable", 4),
                 ("pas ete retenue", 4), ("pas ete retenu", 4), ("autre candidat", 3), ("d autres candidats", 3),
                 ("regret", 2), ("unfortunately", 3), ("not moving forward", 4), ("not to move forward", 4),
                 ("other candidates", 3), ("will not be progressing", 4), ("not been successful", 4),
                 ("position has been filled", 3), ("poste a ete pourvu", 3)],
    },
    "test": {
        "libelle": "Test technique", "statut": "Test technique", "famille": "entretien",
        "mots": [("test technique", 4), ("exercice technique", 4), ("cas pratique", 3), ("etude de cas", 3),
                 ("coding challenge", 4), ("codingame", 4), ("hackerrank", 4), ("codility", 4),
                 ("take home", 3), ("technical test", 4), ("technical assessment", 4), ("case study", 3)],
    },
    "entretien": {
        "libelle": "Entretien", "statut": "Entretien RH", "famille": "entretien",
        "mots": [("entretien", 3), ("echanger avec vous", 3), ("vos disponibilites", 3), ("creneau", 2),
                 ("rencontrer", 2), ("appel telephonique", 2), ("visio", 1), ("calendly", 3), ("interview", 3),
                 ("schedule a call", 3), ("your availability", 3), ("meet you", 2), ("phone screen", 3)],
    },
    "accuse": {
        "libelle": "Accusé de réception", "statut": None, "famille": "attente",
        "mots": [("bien recu votre candidature", 4), ("accuse de reception", 4), ("nous avons bien recu", 3),
                 ("merci pour votre candidature", 2), ("merci de votre candidature", 2),
                 ("votre candidature a bien ete", 3), ("thank you for applying", 3), ("application has been received", 4),
                 ("we have received your application", 4), ("thank you for your application", 2)],
    },
}
PRIORITE = ["offre", "refus", "test", "entretien", "accuse"]


def _norm(s: str) -> str:
    return " " + C.normaliser(s) + " "


def classer(mail: dict) -> dict:
    texte = _norm(f"{mail.get('objet', '')} {mail.get('corps', '')}")
    scores, indices = {}, {}
    for t, cfg in TYPES.items():
        trouves = [m for m, _ in cfg["mots"] if f" {m} " in texte]
        scores[t] = sum(p for m, p in cfg["mots"] if m in trouves)
        indices[t] = trouves
    # Un refus mentionne souvent "entretien"/"candidature" : on le fait passer avant.
    meilleur = max(PRIORITE, key=lambda t: (scores[t], -PRIORITE.index(t)))
    if scores[meilleur] == 0:
        return {"type": "autre", "libelle": "Autre", "famille": "neutre", "statut": None,
                "confiance": "faible", "indices": []}
    # "test technique" contient aussi souvent "entretien technique" : on précise.
    statut = TYPES[meilleur]["statut"]
    if meilleur == "entretien" and " entretien technique " in texte:
        statut = "Entretien technique"
    second = max((s for t, s in scores.items() if t != meilleur), default=0)
    confiance = "haute" if scores[meilleur] >= 4 and scores[meilleur] >= 2 * max(second, 1) else (
        "moyenne" if scores[meilleur] > second else "faible")
    return {"type": meilleur, "libelle": TYPES[meilleur]["libelle"], "famille": TYPES[meilleur]["famille"],
            "statut": statut, "confiance": confiance, "indices": indices[meilleur]}


# --------------------------------------------------------------------------- association à une candidature

PLATEFORMES = {
    "welcometothejungle": "Welcome to the Jungle", "wttj": "Welcome to the Jungle", "teamtailor": "Teamtailor",
    "myworkday": "Workday", "workday": "Workday", "jobteaser": "JobTeaser", "smartrecruiters": "SmartRecruiters",
    "lever.co": "Lever", "greenhouse": "Greenhouse", "recruitee": "Recruitee", "linkedin": "LinkedIn",
    "indeed": "Indeed", "hellowork": "HelloWork", "apec": "APEC", "taleo": "Taleo", "successfactors": "SuccessFactors",
    "jobaffinity": "Jobaffinity", "flatchr": "Flatchr", "digitalrecruiters": "Digital Recruiters",
}
_MOTS_VIDES = {"demo", "sas", "sa", "sarl", "group", "groupe", "france", "the", "de", "la", "le", "les", "et",
               "and", "company", "inc", "ltd", "gmbh", "consulting", "technologies", "technology"}


def plateforme(mail: dict) -> str | None:
    dom = (mail.get("expediteur_email") or "").split("@")[-1]
    texte = f"{dom} {mail.get('corps', '')[:3000]}".lower()
    for cle, nom in PLATEFORMES.items():
        if cle in texte:
            return nom
    return None


def _mots_entreprise(nom: str) -> list[str]:
    return [m for m in C.normaliser(nom).split() if len(m) >= 3 and m not in _MOTS_VIDES]


def associer(mail: dict, cands: list[dict]) -> list[dict]:
    """Candidatures triées par pertinence : [{candidature, score, raisons}]."""
    objet, corps = _norm(mail.get("objet", "")), _norm(mail.get("corps", ""))
    exp_nom = _norm(mail.get("expediteur_nom", ""))
    domaine = (mail.get("expediteur_email") or "").split("@")[-1].lower()
    dom_compact = re.sub(r"[^a-z0-9]", "", domaine.rsplit(".", 1)[0]) if domaine else ""
    res = []
    for c in cands:
        mots = _mots_entreprise(c["entreprise"])
        if not mots:
            continue
        nom_complet = " ".join(mots)
        compact = "".join(mots)
        score, raisons = 0, []
        if dom_compact and (compact in dom_compact or (len(mots[0]) >= 4 and mots[0] in dom_compact)):
            score += 5; raisons.append(f"domaine {domaine}")
        if f" {nom_complet} " in objet:
            score += 4; raisons.append("nom dans l'objet")
        if f" {nom_complet} " in exp_nom:
            score += 4; raisons.append("nom de l'expéditeur")
        if f" {nom_complet} " in corps:
            score += 3; raisons.append("nom dans le mail")
        elif len(mots) > 1 and f" {mots[0]} " in corps and len(mots[0]) >= 5:
            score += 1; raisons.append("nom partiel dans le mail")
        if score == 0:
            continue
        mots_poste = [m for m in C.normaliser(c["poste"]).split() if len(m) >= 5]
        if mots_poste and sum(f" {m} " in objet + corps for m in mots_poste) >= max(1, len(mots_poste) // 2):
            score += 1; raisons.append("poste mentionné")
        if c["statut"] in ("Postulé", "Relancé", "Entretien RH", "Test technique", "Entretien technique"):
            score += 1
        res.append({"candidature": c, "score": score, "raisons": raisons})
    return sorted(res, key=lambda r: -r["score"])


# --------------------------------------------------------------------------- dates d'entretien

_MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
         "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "january": 1, "february": 2,
         "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
         "october": 10, "november": 11, "december": 12}


def _date_libre(s: str, ref: dt.date | None = None) -> dt.date | None:
    ref = ref or C.today()
    n = C.normaliser(s)
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", s)
    if m:
        j, mo, a = int(m.group(1)), int(m.group(2)), m.group(3)
        an = (int(a) + 2000 if a and len(a) == 2 else int(a)) if a else ref.year
        try:
            d = dt.date(an, mo, j)
            return d if a or d >= ref - dt.timedelta(days=7) else dt.date(an + 1, mo, j)
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})(?:er)? (" + "|".join(_MOIS) + r")\b(?: (\d{4}))?", n)
    if m:
        j, mo = int(m.group(1)), _MOIS[m.group(2)]
        an = int(m.group(3)) if m.group(3) else ref.year
        try:
            d = dt.date(an, mo, j)
            return d if m.group(3) or d >= ref - dt.timedelta(days=7) else dt.date(an + 1, mo, j)
        except ValueError:
            return None
    return None


def date_entretien(mail: dict) -> dt.date | None:
    """Première date future citée près d'un mot comme entretien/rendez-vous."""
    texte = mail.get("corps", "")
    ref = mail.get("date") or C.today()
    for m in re.finditer(r"(?i)(entretien|rendez-vous|rdv|interview|call|rencontre|échange|echange|visio)", texte):
        d = _date_libre(texte[m.start(): m.start() + 160], ref)
        if d and d >= ref:
            return d
    return None


# --------------------------------------------------------------------------- proposition

def statut_propose(type_reponse: dict, statut_actuel: str) -> str | None:
    """Statut à proposer, sans jamais faire reculer la candidature."""
    s = type_reponse.get("statut")
    if type_reponse["type"] == "accuse":
        return "Postulé" if statut_actuel == "À postuler" else None
    if not s or s == statut_actuel:
        return None
    parcours = C.STATUTS_PARCOURS
    if s in parcours and statut_actuel in parcours and parcours.index(s) < parcours.index(statut_actuel):
        return None  # pas de retour en arrière
    return s


def analyser(mail: dict, cands: list[dict]) -> dict:
    t = classer(mail)
    assoc = associer(mail, cands)
    meilleure = assoc[0] if assoc and assoc[0]["score"] >= 3 else None
    prop = None
    if meilleure:
        prop = statut_propose(t, meilleure["candidature"]["statut"])
    return {
        "mail": mail, "type": t, "plateforme": plateforme(mail), "associations": assoc[:5],
        "candidature": meilleure["candidature"] if meilleure else None,
        "statut_propose": prop,
        "date_entretien": date_entretien(mail) if t["type"] in ("entretien", "test") else None,
    }


# --------------------------------------------------------------------------- dossier mails/ et suivi des mails traités

SCHEMA_MAILS = """
CREATE TABLE IF NOT EXISTS mails_traites (
    empreinte       TEXT PRIMARY KEY,
    fichier         TEXT,
    date_traitement TEXT NOT NULL,
    decision        TEXT NOT NULL,      -- 'appliqué' | 'ignoré'
    candidature_id  INTEGER
);
"""


def _conn_mails(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.executescript(SCHEMA_MAILS)
    return conn


def marquer_traite(conn, empreinte_: str, fichier: str | None, decision: str, cid: int | None = None) -> None:
    _conn_mails(conn).execute(
        "INSERT OR REPLACE INTO mails_traites VALUES (?,?,?,?,?)",
        (empreinte_, fichier, C.iso(C.today()), decision, cid),
    )
    conn.commit()


def nouveaux_fichiers(conn) -> list[pathlib.Path]:
    """Fichiers .eml/.msg/.txt du dossier mails/ pas encore traités. Les fichiers ne sont jamais supprimés."""
    if not MAILS_DIR.exists():
        return []
    deja = {r[0] for r in _conn_mails(conn).execute("SELECT empreinte FROM mails_traites")}
    return [p for p in sorted(MAILS_DIR.iterdir())
            if p.suffix.lower() in (".eml", ".msg", ".txt") and empreinte(p.read_bytes()) not in deja]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = pathlib.Path(sys.argv[1])
    a = analyser(lire_fichier(p.name, p.read_bytes()), C.lister(C.connect()))
    print("Type :", a["type"]["libelle"], f"({a['type']['confiance']})", a["type"]["indices"])
    print("Candidature :", a["candidature"]["entreprise"] if a["candidature"] else "non trouvée")
    print("Statut proposé :", a["statut_propose"], "| date d'entretien :", a["date_entretien"])
