"""Suivi des candidatures : base SQLite locale (data/candidatures.db).

Module partagé par /adapter-cv, les commandes Claude (/postule, /statut,
/ajout-candidature, /relances, /bilan) et le dashboard Streamlit.

La base contient des données perso : elle est dans le .gitignore, ne jamais
la commiter.

Usage CLI (sortie JSON quand --json est passé) :
    python scripts/candidatures.py init
    python scripts/candidatures.py list [--statut "Postulé"] [--json]
    python scripts/candidatures.py find <texte> [--json]
    python scripts/candidatures.py upsert --json-file chemin.json
    python scripts/candidatures.py enregistrer offres/<dossier>   # fin de /adapter-cv
    python scripts/candidatures.py add --entreprise X --poste Y [--source ...] [...]
    python scripts/candidatures.py set <id> --date-entretien AAAA-MM-JJ [--contact-nom ...]
    python scripts/candidatures.py postule <id>
    python scripts/candidatures.py statut <id> "<statut>" [--note "..."]
    python scripts/candidatures.py relances [--json]
    python scripts/candidatures.py bilan [--json]
    python scripts/candidatures.py a-faire          # relances, entretiens, à postuler (JSON)
    python scripts/candidatures.py show <id>        # détail + historique (JSON)
    python scripts/candidatures.py auto            # applique la règle des 30 jours
    python scripts/candidatures.py import-csv offres/suivi.csv
    python scripts/candidatures.py demo-seed | demo-purge
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import sqlite3
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
# AGENT_CV_DB : autre base (tests, captures d'écran), sinon data/candidatures.db.
DB_PATH = pathlib.Path(os.environ["AGENT_CV_DB"]) if os.environ.get("AGENT_CV_DB") else ROOT / "data" / "candidatures.db"

# Parcours principal, dans l'ordre.
STATUTS_PARCOURS = [
    "À postuler",
    "Postulé",
    "Relancé",
    "Entretien RH",
    "Test technique",
    "Entretien technique",
    "Offre reçue",
    "Acceptée",
]
# Statuts de sortie, possibles à n'importe quel moment.
STATUTS_FIN = ["Refusé", "Sans réponse", "Abandonné"]
STATUTS = STATUTS_PARCOURS + STATUTS_FIN

# Statuts qui comptent comme "l'entreprise a répondu".
STATUTS_REPONSE = {
    "Entretien RH", "Test technique", "Entretien technique",
    "Offre reçue", "Acceptée", "Refusé",
}
STATUTS_ENTRETIEN = {"Entretien RH", "Test technique", "Entretien technique"}
STATUTS_ATTENTE = {"Postulé", "Relancé"}

SOURCES = [
    "Welcome to the Jungle",
    "LinkedIn",
    "Indeed",
    "JobTeaser",
    "Site entreprise",
    "Candidature spontanée",
    "HelloWork",
    "APEC",
    "Cooptation",
    "Autre",
]

TYPE_CONTRAT_DEFAUT = "Stage de fin d'études"
DELAI_RELANCE_JOURS = 10
DELAI_SANS_REPONSE_JOURS = 30

CHAMPS = [
    "entreprise", "poste", "lien_offre", "source", "ville", "type_contrat",
    "date_debut_souhaitee", "date_candidature", "statut", "date_statut",
    "date_derniere_maj", "score_avant", "score_apres", "chemin_cv_pdf",
    "chemin_dossier_offre", "contact_nom", "contact_email",
    "date_relance_prevue", "date_entretien", "notes", "est_demo",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidatures (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise           TEXT NOT NULL,
    poste                TEXT NOT NULL DEFAULT '',
    lien_offre           TEXT,
    source               TEXT,
    ville                TEXT,
    type_contrat         TEXT DEFAULT 'Stage de fin d''études',
    date_debut_souhaitee TEXT,
    date_candidature     TEXT,
    statut               TEXT NOT NULL DEFAULT 'À postuler',
    date_statut          TEXT,            -- date du dernier changement de statut
    date_derniere_maj    TEXT,
    score_avant          REAL,            -- score de correspondance mots-clés (keyword_score.py)
    score_apres          REAL,
    chemin_cv_pdf        TEXT,
    chemin_dossier_offre TEXT,
    contact_nom          TEXT,
    contact_email        TEXT,
    date_relance_prevue  TEXT,
    date_entretien       TEXT,
    notes                TEXT,
    est_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS historique (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidature_id  INTEGER NOT NULL REFERENCES candidatures(id) ON DELETE CASCADE,
    date            TEXT NOT NULL,
    ancien_statut   TEXT,
    nouveau_statut  TEXT NOT NULL,
    note            TEXT,
    automatique     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_hist_cand ON historique(candidature_id);
"""
# Dates stockées en ISO (AAAA-MM-JJ) pour pouvoir trier ; l'affichage peut les reformater.


# --------------------------------------------------------------------------- utilitaires

def today() -> dt.date:
    return dt.date.today()


def iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


def parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def normaliser(s: str | None) -> str:
    """Minuscules, sans accents ni ponctuation : pour comparer des noms."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def trouver_statut(texte: str) -> str | None:
    """'entretien rh' -> 'Entretien RH', 'postule' -> 'Postulé'."""
    n = normaliser(texte)
    for s in STATUTS:
        if normaliser(s) == n:
            return s
    candidats = [s for s in STATUTS if normaliser(s).startswith(n)] if n else []
    return candidats[0] if len(candidats) == 1 else None


def chemin_relatif(p: str | None) -> str | None:
    """Stocke les chemins relativement au projet (portable)."""
    if not p:
        return p
    path = pathlib.Path(p)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# --------------------------------------------------------------------------- connexion

def connect(db_path: pathlib.Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def row_to_dict(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


# --------------------------------------------------------------------------- lecture

def get(conn, cid: int) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM candidatures WHERE id=?", (cid,)).fetchone())


def lister(conn, statut: str | None = None) -> list[dict]:
    if statut:
        rows = conn.execute(
            "SELECT * FROM candidatures WHERE statut=? ORDER BY date_derniere_maj DESC", (statut,)
        )
    else:
        rows = conn.execute("SELECT * FROM candidatures ORDER BY date_derniere_maj DESC, id DESC")
    return [dict(r) for r in rows]


def chercher(conn, texte: str) -> list[dict]:
    """Candidatures dont l'entreprise (ou le poste) contient le texte, sans accents/casse."""
    n = normaliser(texte)
    res = []
    for c in lister(conn):
        if n and (n in normaliser(c["entreprise"]) or n in normaliser(c["poste"])):
            res.append(c)
    # Correspondance exacte sur l'entreprise en premier.
    res.sort(key=lambda c: normaliser(c["entreprise"]) != n)
    return res


def historique(conn, cid: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM historique WHERE candidature_id=? ORDER BY date, id", (cid,)
    )
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- écriture

def _log(conn, cid, ancien, nouveau, note=None, auto=False, date=None):
    conn.execute(
        "INSERT INTO historique (candidature_id, date, ancien_statut, nouveau_statut, note, automatique)"
        " VALUES (?,?,?,?,?,?)",
        (cid, date or iso(today()), ancien, nouveau, note, int(auto)),
    )


def ajouter(conn, **champs) -> int:
    """Ajoute une candidature. Le statut par défaut est 'À postuler'."""
    if not champs.get("entreprise"):
        raise ValueError("Le champ 'entreprise' est obligatoire.")
    statut = champs.get("statut") or "À postuler"
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut}")
    d = iso(today())
    data = {k: v for k, v in champs.items() if k in CHAMPS and v not in (None, "")}
    data.setdefault("poste", "")
    data.setdefault("type_contrat", TYPE_CONTRAT_DEFAUT)
    data["statut"] = statut
    data.setdefault("date_statut", d)
    data["date_derniere_maj"] = data.get("date_derniere_maj") or d
    for k in ("chemin_cv_pdf", "chemin_dossier_offre"):
        if k in data:
            data[k] = chemin_relatif(data[k])
    cols = ", ".join(data)
    cur = conn.execute(
        f"INSERT INTO candidatures ({cols}) VALUES ({', '.join('?' * len(data))})",
        list(data.values()),
    )
    cid = cur.lastrowid
    _log(conn, cid, None, statut, champs.get("note_historique") or "Création", date=data["date_statut"])
    if statut == "Postulé":
        _appliquer_postule(conn, cid, data.get("date_candidature"))
    conn.commit()
    return cid


def modifier(conn, cid: int, **champs) -> None:
    """Met à jour des champs (hors statut : utiliser changer_statut)."""
    data = {k: v for k, v in champs.items() if k in CHAMPS and k != "statut"}
    if not data:
        return
    for k in ("chemin_cv_pdf", "chemin_dossier_offre"):
        if data.get(k):
            data[k] = chemin_relatif(data[k])
    data["date_derniere_maj"] = iso(today())
    sets = ", ".join(f"{k}=?" for k in data)
    conn.execute(f"UPDATE candidatures SET {sets} WHERE id=?", [*data.values(), cid])
    conn.commit()


def ajouter_note(conn, cid: int, note: str) -> None:
    c = get(conn, cid)
    if not c or not note.strip():
        return
    ligne = f"[{today().strftime('%d/%m/%Y')}] {note.strip()}"
    notes = f"{c['notes']}\n{ligne}" if c["notes"] else ligne
    modifier(conn, cid, notes=notes)


def _appliquer_postule(conn, cid, date_candidature=None):
    d = parse_date(date_candidature) or today()
    conn.execute(
        "UPDATE candidatures SET date_candidature=?, date_relance_prevue=? WHERE id=?",
        (iso(d), iso(d + dt.timedelta(days=DELAI_RELANCE_JOURS)), cid),
    )


def changer_statut(conn, cid: int, nouveau: str, note: str | None = None,
                   auto: bool = False, date: str | None = None) -> dict:
    """Change le statut, l'enregistre dans l'historique et applique les règles."""
    statut = trouver_statut(nouveau) if nouveau not in STATUTS else nouveau
    if not statut:
        raise ValueError(f"Statut inconnu : '{nouveau}'. Statuts possibles : {', '.join(STATUTS)}")
    c = get(conn, cid)
    if not c:
        raise ValueError(f"Candidature {cid} introuvable.")
    d = date or iso(today())
    conn.execute(
        "UPDATE candidatures SET statut=?, date_statut=?, date_derniere_maj=? WHERE id=?",
        (statut, d, d, cid),
    )
    if statut == "Postulé":
        # J+10 à partir de la date de candidature (aujourd'hui sauf si déjà renseignée).
        _appliquer_postule(conn, cid, c["date_candidature"] if c["statut"] == "Postulé" else d)
    elif statut == "Relancé":
        # Relance faite : plus de relance prévue (le délai de 30 j repart de cette date).
        conn.execute("UPDATE candidatures SET date_relance_prevue=NULL WHERE id=?", (cid,))
    elif statut not in STATUTS_ATTENTE:
        conn.execute("UPDATE candidatures SET date_relance_prevue=NULL WHERE id=?", (cid,))
    _log(conn, cid, c["statut"], statut, note, auto=auto, date=d)
    if note and not auto:
        ajouter_note(conn, cid, note)
    conn.commit()
    return get(conn, cid)


def appliquer_regles_auto(conn) -> list[dict]:
    """Postulé/Relancé depuis plus de 30 jours sans nouvelle -> Sans réponse."""
    limite = today() - dt.timedelta(days=DELAI_SANS_REPONSE_JOURS)
    changes = []
    for c in lister(conn):
        if c["statut"] in STATUTS_ATTENTE:
            depuis = parse_date(c["date_statut"]) or parse_date(c["date_candidature"])
            if depuis and depuis < limite:
                changer_statut(
                    conn, c["id"], "Sans réponse",
                    note=f"Automatique : aucune nouvelle depuis le {depuis.strftime('%d/%m/%Y')} "
                         f"(plus de {DELAI_SANS_REPONSE_JOURS} jours).",
                    auto=True,
                )
                changes.append({"id": c["id"], "entreprise": c["entreprise"], "depuis": iso(depuis)})
    return changes


def upsert(conn, **champs) -> tuple[int, bool]:
    """Ajoute ou met à jour (pas de doublon). Utilisé à la fin de /adapter-cv.

    Doublon = même dossier d'offre, ou même lien d'offre, ou même entreprise + poste.
    Le statut d'une candidature existante n'est jamais rétrogradé.
    Retourne (id, cree).
    """
    existant = None
    dossier = chemin_relatif(champs.get("chemin_dossier_offre"))
    for c in lister(conn):
        if dossier and c["chemin_dossier_offre"] == dossier:
            existant = c
            break
        if champs.get("lien_offre") and c["lien_offre"] == champs["lien_offre"]:
            existant = c
            break
        if (normaliser(c["entreprise"]) == normaliser(champs.get("entreprise"))
                and normaliser(c["poste"]) == normaliser(champs.get("poste"))):
            existant = c
            break
    if existant is None:
        return ajouter(conn, **champs), True
    maj = {k: v for k, v in champs.items() if k != "statut" and v not in (None, "")}
    modifier(conn, existant["id"], **maj)
    return existant["id"], False


def enregistrer_offre(conn, dossier: str | pathlib.Path) -> tuple[int, bool]:
    """Fin de /adapter-cv : lit resultat.json (+ score.json) d'un dossier d'offre et fait l'upsert.

    resultat.json (écrit par l'agent) : entreprise, poste, lien_offre, source,
    ville, type_contrat, date_debut_souhaitee, chemin_cv_pdf, modifications,
    competences_manquantes...
    score.json (écrit par keyword_score.py --json-out) : score_avant, score_apres.
    """
    d = pathlib.Path(dossier)
    if not d.is_absolute():
        d = ROOT / d
    resultat_path = d / "resultat.json"
    if not resultat_path.exists():
        raise FileNotFoundError(f"{resultat_path} introuvable.")
    champs = json.loads(resultat_path.read_text(encoding="utf-8"))
    score_path = d / "score.json"
    if score_path.exists():
        score = json.loads(score_path.read_text(encoding="utf-8"))
        champs.setdefault("score_avant", score.get("score_avant"))
        champs.setdefault("score_apres", score.get("score_apres"))
    champs["chemin_dossier_offre"] = str(d)
    if not champs.get("chemin_cv_pdf"):
        pdfs = sorted(d.glob("*.pdf"))
        if pdfs:
            champs["chemin_cv_pdf"] = str(pdfs[0])
    elif not pathlib.Path(champs["chemin_cv_pdf"]).is_absolute():
        p = pathlib.Path(champs["chemin_cv_pdf"])
        champs["chemin_cv_pdf"] = str(ROOT / p if (ROOT / p).exists() else d / p)
    if champs.get("source") and champs["source"] not in SOURCES:
        n = normaliser(champs["source"])
        champs["source"] = next((s for s in SOURCES if normaliser(s) == n), champs["source"])
    champs.pop("statut", None)  # une ré-adaptation ne change jamais le statut
    return upsert(conn, **champs)


def supprimer(conn, cid: int) -> None:
    conn.execute("DELETE FROM candidatures WHERE id=?", (cid,))
    conn.commit()


# --------------------------------------------------------------------------- vues / stats

def relances_dues(conn, jusqua: dt.date | None = None) -> list[dict]:
    limite = iso(jusqua or today())
    rows = conn.execute(
        "SELECT * FROM candidatures WHERE statut IN ('Postulé','Relancé')"
        " AND date_relance_prevue IS NOT NULL AND date_relance_prevue <= ?"
        " ORDER BY date_relance_prevue",
        (limite,),
    )
    res = []
    for r in rows:
        d = dict(r)
        d["jours_retard"] = (today() - parse_date(d["date_relance_prevue"])).days
        res.append(d)
    return res


def entretiens_a_venir(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM candidatures WHERE date_entretien IS NOT NULL AND date_entretien >= ?"
        " ORDER BY date_entretien",
        (iso(today()),),
    )
    return [dict(r) for r in rows]


def a_postuler(conn) -> list[dict]:
    return lister(conn, "À postuler")


def _date_premiere_reponse(conn, cid) -> dt.date | None:
    for h in historique(conn, cid):
        if h["nouveau_statut"] in STATUTS_REPONSE:
            return parse_date(h["date"])
    return None


def bilan(conn) -> dict:
    cands = lister(conn)
    envoyees = [c for c in cands if c["statut"] != "À postuler" and c["date_candidature"]]
    repondu = [c for c in envoyees if _date_premiere_reponse(conn, c["id"]) is not None]
    delais = []
    for c in repondu:
        d0, d1 = parse_date(c["date_candidature"]), _date_premiere_reponse(conn, c["id"])
        if d0 and d1 and d1 >= d0:
            delais.append((d1 - d0).days)
    par_statut = {s: 0 for s in STATUTS}
    for c in cands:
        par_statut[c["statut"]] = par_statut.get(c["statut"], 0) + 1
    return {
        "total": len(cands),
        "envoyees": len(envoyees),
        "a_postuler": par_statut["À postuler"],
        "en_attente": sum(par_statut[s] for s in STATUTS_ATTENTE),
        "entretiens_en_cours": sum(par_statut[s] for s in STATUTS_ENTRETIEN),
        "offres": par_statut["Offre reçue"] + par_statut["Acceptée"],
        "refus": par_statut["Refusé"],
        "sans_reponse": par_statut["Sans réponse"],
        "taux_reponse": round(100 * len(repondu) / len(envoyees), 1) if envoyees else None,
        "delai_moyen_reponse_jours": round(sum(delais) / len(delais), 1) if delais else None,
        "par_statut": par_statut,
        "relances_dues": len(relances_dues(conn)),
        "entretiens_a_venir": len(entretiens_a_venir(conn)),
    }


def stats_par_source(conn) -> list[dict]:
    res = {}
    for c in lister(conn):
        if c["statut"] == "À postuler" or not c["date_candidature"]:
            continue
        s = c["source"] or "Non renseignée"
        r = res.setdefault(s, {"source": s, "envoyees": 0, "reponses": 0})
        r["envoyees"] += 1
        if _date_premiere_reponse(conn, c["id"]) is not None:
            r["reponses"] += 1
    for r in res.values():
        r["taux_reponse"] = round(100 * r["reponses"] / r["envoyees"], 1)
    return sorted(res.values(), key=lambda r: -r["taux_reponse"])


def a_repondu(conn, cid: int) -> bool:
    return _date_premiere_reponse(conn, cid) is not None


# --------------------------------------------------------------------------- import CSV

def importer_csv(conn, path: pathlib.Path) -> int:
    """Migre un ancien offres/suivi.csv (colonnes reconnues par leur nom)."""
    n = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            champs = {normaliser(k).replace(" ", "_"): v for k, v in row.items() if k}
            statut = trouver_statut(champs.get("statut", "")) or "À postuler"
            champs["statut"] = statut
            for k in ("date_candidature", "date_relance_prevue", "date_entretien", "date_debut_souhaitee"):
                if champs.get(k):
                    champs[k] = iso(parse_date(champs[k])) or champs[k]
            if champs.get("entreprise"):
                upsert(conn, **champs)
                n += 1
    return n


# --------------------------------------------------------------------------- données de démo

def demo_seed(conn) -> list[int]:
    """3 candidatures fictives (est_demo=1) pour voir le dashboard rempli."""
    t = today()
    j = lambda n: iso(t - dt.timedelta(days=n))  # noqa: E731
    ids = []
    # 1. Postulé il y a 12 jours -> relance en retard
    cid = ajouter(conn, entreprise="Nimbus Analytics (démo)", poste="Stagiaire Data Engineer",
                  source="Welcome to the Jungle", ville="Paris", statut="À postuler",
                  score_avant=48, score_apres=79, est_demo=1, date_statut=j(14),
                  lien_offre="https://example.com/offre-nimbus")
    changer_statut(conn, cid, "Postulé", date=j(12))
    _appliquer_postule(conn, cid, j(12))
    conn.commit()
    ids.append(cid)
    # 2. Entretien RH prévu dans 3 jours
    cid = ajouter(conn, entreprise="Orbital Energie (démo)", poste="Stage Data Analyst",
                  source="LinkedIn", ville="Lyon", statut="À postuler", score_avant=55,
                  score_apres=83, est_demo=1, date_statut=j(25),
                  contact_nom="Recruteur Fictif", contact_email="rh@example.com",
                  date_entretien=iso(t + dt.timedelta(days=3)))
    changer_statut(conn, cid, "Postulé", date=j(20))
    _appliquer_postule(conn, cid, j(20))
    changer_statut(conn, cid, "Entretien RH", note="Appel du recruteur, entretien calé", date=j(6))
    ids.append(cid)
    # 3. Refusé après 9 jours
    cid = ajouter(conn, entreprise="Quanta Bank (démo)", poste="Stage Data Scientist",
                  source="JobTeaser", ville="Paris", statut="À postuler", score_avant=40,
                  score_apres=66, est_demo=1, date_statut=j(18))
    changer_statut(conn, cid, "Postulé", date=j(16))
    _appliquer_postule(conn, cid, j(16))
    changer_statut(conn, cid, "Refusé", note="Mail de refus standard", date=j(7))
    ids.append(cid)
    return ids


def demo_purge(conn) -> int:
    n = conn.execute("DELETE FROM candidatures WHERE est_demo=1").rowcount
    conn.commit()
    return n


# --------------------------------------------------------------------------- CLI

def _fmt(c: dict) -> str:
    d = parse_date(c.get("date_candidature"))
    extra = f", postulé le {d.strftime('%d/%m/%Y')}" if d else ""
    return f"#{c['id']} {c['entreprise']} — {c['poste'] or '?'} [{c['statut']}{extra}]"


def _sortie(obj, as_json: bool, texte: str):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str) if as_json else texte)


def main(argv=None):
    p = argparse.ArgumentParser(description="Suivi des candidatures (SQLite).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    s = sub.add_parser("list"); s.add_argument("--statut"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("find"); s.add_argument("texte"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("show"); s.add_argument("id", type=int)
    s = sub.add_parser("upsert"); s.add_argument("--json-file", required=True)
    s = sub.add_parser("enregistrer"); s.add_argument("dossier")
    s = sub.add_parser("add")
    for champ in CHAMPS:
        if champ not in ("est_demo", "date_derniere_maj", "date_statut"):
            s.add_argument(f"--{champ.replace('_', '-')}", dest=champ)
    s = sub.add_parser("set"); s.add_argument("id", type=int)
    for champ in CHAMPS:
        if champ not in ("est_demo", "date_derniere_maj", "date_statut", "statut", "notes"):
            s.add_argument(f"--{champ.replace('_', '-')}", dest=champ)
    s = sub.add_parser("postule"); s.add_argument("id", type=int); s.add_argument("--date")
    s = sub.add_parser("statut"); s.add_argument("id", type=int); s.add_argument("statut")
    s.add_argument("--note"); s.add_argument("--date")
    s = sub.add_parser("note"); s.add_argument("id", type=int); s.add_argument("note")
    s = sub.add_parser("relances"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bilan"); s.add_argument("--json", action="store_true")
    sub.add_parser("a-faire")
    sub.add_parser("auto")
    s = sub.add_parser("import-csv"); s.add_argument("chemin")
    sub.add_parser("demo-seed")
    sub.add_parser("demo-purge")
    sub.add_parser("statuts")

    a = p.parse_args(argv)
    conn = connect()

    # La règle des 30 jours s'applique à chaque utilisation.
    if a.cmd not in ("init", "statuts", "demo-purge"):
        for ch in appliquer_regles_auto(conn):
            print(f"(auto) #{ch['id']} {ch['entreprise']} -> Sans réponse", file=sys.stderr)

    if a.cmd == "init":
        print(f"Base prête : {DB_PATH}")
    elif a.cmd == "statuts":
        print("\n".join(STATUTS))
    elif a.cmd == "list":
        rows = lister(conn, a.statut)
        _sortie(rows, a.json, "\n".join(_fmt(c) for c in rows) or "Aucune candidature.")
    elif a.cmd == "find":
        rows = chercher(conn, a.texte)
        _sortie(rows, a.json, "\n".join(_fmt(c) for c in rows) or "Aucune correspondance.")
    elif a.cmd == "show":
        c = get(conn, a.id)
        _sortie({"candidature": c, "historique": historique(conn, a.id)}, True, "")
    elif a.cmd == "upsert":
        with open(a.json_file, encoding="utf-8") as f:
            champs = json.load(f)
        cid, cree = upsert(conn, **champs)
        print(f"{'Ajoutée' if cree else 'Mise à jour'} : {_fmt(get(conn, cid))}")
    elif a.cmd == "enregistrer":
        cid, cree = enregistrer_offre(conn, a.dossier)
        c = get(conn, cid)
        print(f"{'Ajoutée au suivi' if cree else 'Déjà suivie, mise à jour'} : {_fmt(c)}")
    elif a.cmd == "add":
        champs = {k: v for k, v in vars(a).items() if k in CHAMPS and v}
        cid = ajouter(conn, **champs)
        print(f"Ajoutée : {_fmt(get(conn, cid))}")
    elif a.cmd == "set":
        champs = {k: v for k, v in vars(a).items() if k in CHAMPS and v is not None}
        modifier(conn, a.id, **champs)
        print(f"Mis à jour : {_fmt(get(conn, a.id))} ({', '.join(champs) or 'rien'})")
    elif a.cmd == "postule":
        c = changer_statut(conn, a.id, "Postulé", date=a.date)
        print(f"{_fmt(c)} — relance prévue le {parse_date(c['date_relance_prevue']).strftime('%d/%m/%Y')}")
    elif a.cmd == "statut":
        c = changer_statut(conn, a.id, a.statut, note=a.note, date=a.date)
        print(_fmt(c))
    elif a.cmd == "note":
        ajouter_note(conn, a.id, a.note)
        print(f"Note ajoutée à #{a.id}")
    elif a.cmd == "relances":
        rows = relances_dues(conn)
        _sortie(rows, a.json, "\n".join(
            f"{_fmt(c)} — relance prévue le {parse_date(c['date_relance_prevue']).strftime('%d/%m/%Y')}"
            f" ({c['jours_retard']} j de retard)" for c in rows) or "Aucune relance à faire.")
    elif a.cmd == "bilan":
        b = bilan(conn)
        _sortie(b, a.json, json.dumps(b, ensure_ascii=False, indent=2))
    elif a.cmd == "a-faire":
        _sortie({
            "relances": relances_dues(conn),
            "entretiens_a_venir": entretiens_a_venir(conn),
            "a_postuler": a_postuler(conn),
        }, True, "")
    elif a.cmd == "auto":
        print("Règles automatiques appliquées.")
    elif a.cmd == "import-csv":
        print(f"{importer_csv(conn, pathlib.Path(a.chemin))} ligne(s) importée(s).")
    elif a.cmd == "demo-seed":
        print(f"Candidatures de démo ajoutées : {demo_seed(conn)}")
    elif a.cmd == "demo-purge":
        print(f"{demo_purge(conn)} candidature(s) de démo supprimée(s).")


if __name__ == "__main__":
    main()
