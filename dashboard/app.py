"""Dashboard local de candidatures (Streamlit).

Lancement : double-clic sur Lancer_Dashboard.bat, ou
    python -m streamlit run dashboard/app.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dashboard"))

import candidatures as C  # noqa: E402
import claude_runner as R  # noqa: E402
from _tools import find_tool  # noqa: E402

st.set_page_config(page_title="Candidatures", page_icon="📄", layout="wide")


def conn():
    """Connexion à la base ; la règle des 30 jours est appliquée à chaque chargement."""
    c = C.connect()
    C.appliquer_regles_auto(c)
    return c


# =========================================================================== utilitaires

def apercu_pdf(pdf: pathlib.Path) -> pathlib.Path | None:
    """PNG de la première page (pdftoppm), mis en cache à côté du PDF dans le dossier de l'offre."""
    png = pdf.with_suffix(".apercu.png")
    if png.exists() and png.stat().st_mtime >= pdf.stat().st_mtime:
        return png
    try:
        exe = find_tool("pdftoppm")
    except FileNotFoundError:
        return None
    r = subprocess.run(
        [exe, "-png", "-r", "110", "-f", "1", "-l", "1", "-singlefile", str(pdf), str(png.with_suffix(""))],
        capture_output=True,
    )
    return png if r.returncode == 0 and png.exists() else None


def lire_json(p: pathlib.Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def candidature_du_dossier(dossier: pathlib.Path) -> dict | None:
    rel = C.chemin_relatif(str(dossier))
    for c in C.lister(conn()):
        if c["chemin_dossier_offre"] == rel:
            return c
    return None


# =========================================================================== page 1

def page_nouvelle():
    st.title("Nouvelle candidature")
    st.caption(
        "Colle l'offre, clique sur **Adapter mon CV** : l'agent lance le même workflow que "
        "`/adapter-cv` (zéro invention, une page, vérification ATS) et ajoute la candidature au suivi."
    )

    job = st.session_state.get("job")
    if job:
        afficher_traitement(pathlib.Path(job))
        return

    if not R.find_claude():
        st.error(R.CONSEILS_ERREUR["claude_introuvable"])

    with st.form("offre"):
        texte = st.text_area(
            "Texte complet de l'offre",
            height=320,
            placeholder="Colle ici tout le texte de l'offre (missions, profil, compétences, lieu…)",
        )
        c1, c2 = st.columns(2)
        lien = c1.text_input("Lien de l'offre (optionnel)")
        source = c2.selectbox(
            "Source (optionnel)", [""] + C.SOURCES,
            format_func=lambda s: s or "Détecter automatiquement",
        )
        c3, c4 = st.columns(2)
        entreprise = c3.text_input("Entreprise (optionnel, détectée sinon)")
        poste = c4.text_input("Poste (optionnel, détecté sinon)")
        go = st.form_submit_button("Adapter mon CV", type="primary", width="stretch")

    if go:
        if len(texte.strip()) < 200:
            st.warning("Le texte de l'offre semble trop court : colle l'annonce complète (au moins quelques paragraphes).")
            return
        try:
            job = R.lancer(texte, lien, entreprise, poste, source)
        except FileNotFoundError:
            st.error(R.CONSEILS_ERREUR["claude_introuvable"])
            return
        st.session_state["job"] = str(job)
        st.rerun()


def afficher_traitement(job: pathlib.Path):
    @st.fragment(run_every=2)
    def suivi():
        e = R.etat(job)
        if e["statut"] == "en_cours":
            fait = e["etape"]
            st.progress(fait / len(e["etapes"]),
                        text=f"⏳ {e['etapes'][max(fait - 1, 0)] if fait else 'Démarrage de Claude Code'}… "
                             f"({e['duree'] // 60} min {e['duree'] % 60:02d} s — compte 1 à 3 minutes)")
            cols = st.columns(len(e["etapes"]))
            for i, (col, nom) in enumerate(zip(cols, e["etapes"]), start=1):
                col.caption(("✅ " if i <= fait else "◻️ ") + nom)
            with st.expander("Log en direct", expanded=True):
                st.code("\n".join(e["log"][-25:]) or "Démarrage…", language=None)
            if st.button("Arrêter le traitement"):
                R.arreter(job)
                st.rerun()
        else:
            st.rerun(scope="app")

    e = R.etat(job)
    if e["statut"] == "en_cours":
        suivi()
    elif e["statut"] == "question":
        afficher_question(job, e)
    elif e["statut"] == "termine":
        afficher_resultat(e)
    else:
        afficher_erreur(e)


def afficher_question(job: pathlib.Path, e: dict):
    st.info("**L'agent a besoin d'une précision avant de finir le CV :**")
    st.markdown(f"> {e['question']}")
    with st.form("reponse"):
        rep = st.text_area("Ta réponse", height=100)
        ok = st.form_submit_button("Envoyer la réponse et continuer", type="primary")
    if ok and rep.strip():
        R.repondre(job, rep.strip())
        st.rerun()
    bouton_nouvelle(secondaire=True)


def afficher_erreur(e: dict):
    st.error(f"**Le traitement n'a pas abouti.** {e.get('message', '')}")
    st.markdown("**Quoi faire :** " + R.CONSEILS_ERREUR.get(e.get("type_erreur"), R.CONSEILS_ERREUR["autre"]))
    with st.expander("Détails techniques"):
        st.code("\n".join(e["log"][-40:]) or "(pas de log)", language=None)
        if e.get("stderr"):
            st.code(e["stderr"][-3000:], language=None)
    bouton_nouvelle()


def afficher_resultat(e: dict):
    dossier: pathlib.Path = e["dossier"]
    res = lire_json(dossier / "resultat.json")
    score = lire_json(dossier / "score.json")
    cand = candidature_du_dossier(dossier)

    titre = f"{res.get('entreprise') or (cand or {}).get('entreprise', '?')} — {res.get('poste') or (cand or {}).get('poste', '')}"
    st.success(f"CV adapté : **{titre}**")

    gauche, droite = st.columns([3, 2], gap="large")
    pdf = pathlib.Path(ROOT / res["chemin_cv_pdf"]) if res.get("chemin_cv_pdf") else None
    if not pdf or not pdf.exists():
        pdfs = sorted(dossier.glob("*.pdf"))
        pdf = pdfs[0] if pdfs else None

    with gauche:
        if pdf:
            png = apercu_pdf(pdf)
            if png:
                st.image(str(png), width="stretch")
            else:
                st.caption("Aperçu indisponible (pdftoppm introuvable) : télécharge le PDF.")
        else:
            st.warning("PDF introuvable dans le dossier de l'offre.")

    with droite:
        if pdf:
            st.download_button("⬇ Télécharger le PDF", pdf.read_bytes(), file_name=pdf.name,
                               mime="application/pdf", type="primary", width="stretch")
        av, ap = score.get("score_avant"), score.get("score_apres")
        if av is not None and ap is not None:
            c1, c2 = st.columns(2)
            c1.metric("Score de correspondance avant", f"{av:.0f} %")
            c2.metric("Après adaptation", f"{ap:.0f} %", delta=f"{ap - av:+.0f} pts")
            st.caption("Part des mots-clés de l'offre présents dans le CV (keyword_score.py).")

        if res.get("modifications"):
            st.subheader("Modifications")
            st.markdown("\n".join(f"- {m}" for m in res["modifications"]))
        if res.get("competences_manquantes"):
            st.subheader("Compétences demandées que tu n'as pas")
            st.markdown("\n".join(f"- {m}" for m in res["competences_manquantes"]))
            st.caption("Jamais ajoutées au CV. À toi de voir si tu veux les travailler.")
        if res.get("a_confirmer"):
            st.subheader("À confirmer")
            st.markdown("\n".join(f"- {m}" for m in res["a_confirmer"]))
            st.caption("Tu les as peut-être, mais elles ne sont pas dans ton master CV : "
                       "ajoute-les à data/master_cv.yaml si c'est vrai, puis régénère.")

        st.divider()
        if cand:
            if cand["statut"] == "À postuler":
                b1, b2 = st.columns(2)
                if b1.button("✅ J'ai postulé", type="primary", width="stretch"):
                    c = C.changer_statut(conn(), cand["id"], "Postulé")
                    st.session_state["flash"] = (
                        f"{c['entreprise']} passé en Postulé — relance prévue le "
                        f"{C.parse_date(c['date_relance_prevue']).strftime('%d/%m/%Y')}."
                    )
                    st.session_state.pop("job", None)
                    st.rerun()
                if b2.button("Pas maintenant", width="stretch"):
                    st.session_state["flash"] = f"{cand['entreprise']} reste en « À postuler »."
                    st.session_state.pop("job", None)
                    st.rerun()
            else:
                st.caption(f"Statut actuel dans le suivi : **{cand['statut']}**")
                bouton_nouvelle()
        else:
            st.warning("La candidature n'a pas été trouvée dans le suivi.")
            bouton_nouvelle()

    with st.expander("Récap complet de l'agent"):
        st.markdown(e.get("texte", ""))
        if e.get("cout_usd"):
            st.caption(f"Coût estimé de ce traitement : {e['cout_usd']:.2f} $")


def bouton_nouvelle(secondaire: bool = False):
    if st.button("Nouvelle offre", type="secondary" if secondaire else "primary"):
        st.session_state.pop("job", None)
        st.rerun()


# =========================================================================== pages suivantes (étape 4, suite)

def page_a_venir(nom):
    def _p():
        st.title(nom)
        st.info("Cette page arrive dans la suite de l'étape 4.")
    _p.__name__ = "page_" + "".join(ch for ch in nom.lower() if ch.isalnum())
    return _p


# =========================================================================== navigation

if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"), icon="✅")

pages = [
    st.Page(page_nouvelle, title="Nouvelle candidature", icon="✏️", default=True),
    st.Page(page_a_venir("Vue d'ensemble"), title="Vue d'ensemble", icon="📊"),
    st.Page(page_a_venir("Mes candidatures"), title="Mes candidatures", icon="📋"),
    st.Page(page_a_venir("À faire"), title="À faire", icon="🔔"),
    st.Page(page_a_venir("Statistiques"), title="Statistiques", icon="📈"),
]
st.navigation(pages, position="top").run()
