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
import pages_suivi as P  # noqa: E402
import ui  # noqa: E402
from _tools import find_tool  # noqa: E402

st.set_page_config(page_title="Agent CV", page_icon="📄", layout="wide")
ui.charger_style()


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


def prenom() -> str:
    nom = (P.personal().get("name") or "").split()
    return nom[0] if nom else ""


# Traitement en cours : gardé dans la session ET dans l'URL (?job=...), pour le
# retrouver après un rafraîchissement de la page ou un redémarrage du dashboard.
def job_courant() -> pathlib.Path | None:
    if st.session_state.get("job"):
        return pathlib.Path(st.session_state["job"])
    j = R.job_par_nom(st.query_params.get("job", ""))
    if j:
        st.session_state["job"] = str(j)
    return j


def definir_job(job: pathlib.Path | None) -> None:
    if job:
        st.session_state["job"] = str(job)
        st.query_params["job"] = job.name
    else:
        st.session_state.pop("job", None)
        st.query_params.pop("job", None)


# =========================================================================== page 1

def page_nouvelle():
    job = job_courant()
    if job:
        afficher_traitement(job)
        return

    p = prenom()
    ui.hero(
        f"Bonjour {p} 👋" if p else "Nouvelle candidature",
        "Colle une offre, je m'occupe du CV",
        "Même workflow que /adapter-cv : zéro invention, une page, vérification ATS. "
        "Compte 1 à 3 minutes.",
    )

    if not R.find_claude():
        st.error(R.CONSEILS_ERREUR["claude_introuvable"])

    with st.container(key="carte_offre"):
        with st.form("offre", border=False):
            texte = st.text_area(
                "Texte de l'offre",
                height=320,
                label_visibility="collapsed",
                placeholder=(
                    "Colle ici le texte complet de l'offre…\n\n"
                    "Missions, profil recherché, compétences, lieu, date de début : "
                    "plus le texte est complet, mieux le CV sera adapté."
                ),
            )
            with st.expander("Infos optionnelles — lien, entreprise, poste, source"):
                c1, c2 = st.columns(2)
                lien = c1.text_input("Lien de l'offre", placeholder="https://…")
                source = c2.selectbox(
                    "Source", [""] + C.SOURCES,
                    format_func=lambda s: s or "Détecter automatiquement",
                )
                c3, c4 = st.columns(2)
                entreprise = c3.text_input("Entreprise", placeholder="Détectée depuis le texte")
                poste = c4.text_input("Poste", placeholder="Détecté depuis le texte")
            go = st.form_submit_button("✨  Adapter mon CV", type="primary", width="stretch")

    st.html(
        '<div class="ac-how">'
        '<div><span class="n">1</span><span><b>Colle l\'offre</b>Le texte complet, copié depuis le site.</span></div>'
        '<div><span class="n">2</span><span><b>L\'agent adapte</b>Sélection, reformulation fidèle, compilation, vérif ATS.</span></div>'
        '<div><span class="n">3</span><span><b>Tu postules</b>Télécharge le PDF, puis « J\'ai postulé » : relance à J+10.</span></div>'
        "</div>"
    )

    if go:
        if len(texte.strip()) < 200:
            st.warning("Le texte de l'offre semble trop court : colle l'annonce complète (au moins quelques paragraphes).")
            return
        try:
            job = R.lancer(texte, lien, entreprise, poste, source)
        except FileNotFoundError:
            st.error(R.CONSEILS_ERREUR["claude_introuvable"])
            return
        definir_job(job)
        st.rerun()


def afficher_traitement(job: pathlib.Path):
    @st.fragment(run_every=2)
    def suivi():
        e = R.etat(job)
        if e["statut"] != "en_cours":
            st.rerun(scope="app")
        etape = max(e["etape"], 1)
        with st.container(key="carte_suivi"):
            st.html(
                '<div class="ac-job-head"><h3>Adaptation en cours…</h3>'
                f'<span class="ac-chrono">⏱ {e["duree"] // 60} min {e["duree"] % 60:02d} s · compte 1 à 3 min</span></div>'
                + ui.stepper(e["etapes"], etape, "en cours…")
            )
        with st.expander("Log technique"):
            st.code("\n".join(e["log"][-30:]) or "Démarrage de Claude Code…", language=None)

    e = R.etat(job)
    if e["statut"] == "en_cours":
        ui.hero("Nouvelle candidature", "Je prépare ton CV", "Tu peux changer d'onglet : le traitement continue.")
        gauche, droite = st.columns([2, 1], gap="large")
        with gauche:
            suivi()
        with droite:
            st.html('<p class="ac-muted">L\'agent suit exactement le workflow /adapter-cv. '
                    "Rien n'est inventé : les compétences absentes de ton master CV sont listées à part.</p>")
            if st.button("Arrêter le traitement", width="stretch"):
                R.arreter(job)
                st.rerun()
    elif e["statut"] == "question":
        afficher_question(job, e)
    elif e["statut"] == "termine":
        afficher_resultat(e)
    else:
        afficher_erreur(e)


def afficher_question(job: pathlib.Path, e: dict):
    with st.container(key="carte_question"):
        st.html(f'<div class="ac-callout"><b>💬 L\'agent a besoin d\'une précision avant de finir le CV</b>'
                f"{ui.e(e['question'])}</div>")
        with st.form("reponse", border=False):
            rep = st.text_area("Ta réponse", height=110)
            ok = st.form_submit_button("Envoyer la réponse et continuer", type="primary", width="stretch")
    if ok and rep.strip():
        R.repondre(job, rep.strip())
        st.rerun()
    bouton_nouvelle(secondaire=True)


def afficher_erreur(e: dict):
    with st.container(key="carte_erreur"):
        st.html(f'<div class="ac-callout err"><b>Le traitement n\'a pas abouti</b>{ui.e(e.get("message", ""))}</div>')
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
    entreprise = res.get("entreprise") or (cand or {}).get("entreprise", "?")
    poste = res.get("poste") or (cand or {}).get("poste", "")

    pdf = pathlib.Path(ROOT / res["chemin_cv_pdf"]) if res.get("chemin_cv_pdf") else None
    if not pdf or not pdf.exists():
        pdfs = sorted(dossier.glob("*.pdf"))
        pdf = pdfs[0] if pdfs else None

    # ---- en-tête
    infos = [x for x in (res.get("ville"), res.get("source") or (cand or {}).get("source"), res.get("type_contrat")) if x]
    statut = (cand or {}).get("statut")
    with st.container(key="carte_entete"):
        st.html(
            '<div class="ac-result-head"><div class="ico">✓</div><div>'
            f"<h2>CV prêt pour {ui.e(entreprise)}</h2><p>{ui.e(poste)}</p>"
            '<div class="ac-badges">'
            + "".join(ui.badge(i, "info") for i in infos)
            + (ui.badge_statut(statut) if statut else "")
            + "</div></div></div>"
        )

    # ---- aperçu | score + détails
    gauche, droite = st.columns([5, 6], gap="medium")
    with gauche:
        with st.container(key="carte_apercu"):
            ui.titre_section("Aperçu du CV")
            png = apercu_pdf(pdf) if pdf else None
            if png:
                st.image(png.read_bytes(), width="stretch")
            elif pdf:
                st.caption("Aperçu indisponible (pdftoppm introuvable) : télécharge le PDF.")
            else:
                st.warning("PDF introuvable dans le dossier de l'offre.")

    with droite:
        av, ap = score.get("score_avant"), score.get("score_apres")
        if av is not None and ap is not None:
            with st.container(key="carte_score"):
                ui.score(av, ap)
        if res.get("modifications"):
            with st.container(key="carte_modifs"):
                ui.titre_section("Ce qui a été adapté")
                ui.liste(res["modifications"])
        if res.get("competences_manquantes") or res.get("a_confirmer"):
            with st.container(key="carte_competences"):
                if res.get("competences_manquantes"):
                    ui.titre_section("Demandé par l'offre, absent de ton profil")
                    ui.badges(res["competences_manquantes"], "negatif")
                    st.caption("Jamais ajoutées au CV.")
                if res.get("a_confirmer"):
                    ui.titre_section("À confirmer")
                    ui.badges(res["a_confirmer"], "entretien")
                    st.caption("Tu les as peut-être : ajoute-les à data/master_cv.yaml si c'est vrai, puis régénère.")

    # ---- actions
    with st.container(key="carte_actions"):
        a1, a2, a3 = st.columns(3)
        if pdf:
            a1.download_button("⬇  Télécharger le PDF", pdf.read_bytes(), file_name=pdf.name,
                               mime="application/pdf", width="stretch")
        if cand and cand["statut"] == "À postuler":
            if a2.button("✅  J'ai postulé", type="primary", width="stretch"):
                c = C.changer_statut(conn(), cand["id"], "Postulé")
                st.session_state["flash"] = (
                    f"{c['entreprise']} passé en Postulé — relance prévue le "
                    f"{C.parse_date(c['date_relance_prevue']).strftime('%d/%m/%Y')}."
                )
                definir_job(None)
                st.rerun()
            if a3.button("Pas maintenant", width="stretch"):
                st.session_state["flash"] = f"{cand['entreprise']} reste en « À postuler »."
                definir_job(None)
                st.rerun()
        else:
            if not cand:
                a2.warning("Candidature introuvable dans le suivi.")
            if a3.button("Nouvelle offre", type="primary", width="stretch"):
                definir_job(None)
                st.rerun()

    with st.expander("Récap complet de l'agent"):
        st.markdown(e.get("texte", ""))
        if e.get("cout_usd"):
            st.caption(f"Coût estimé de ce traitement : {e['cout_usd']:.2f} $")


def bouton_nouvelle(secondaire: bool = False):
    if st.button("Nouvelle offre", type="secondary" if secondaire else "primary"):
        definir_job(None)
        st.rerun()


# =========================================================================== sidebar + navigation

def sidebar_resume():
    try:
        c = conn()
        nb_rel = len(C.relances_dues(c))
        nb_ent = len(C.entretiens_a_venir(c))
        nb_todo = len(C.a_postuler(c))
    except Exception:  # la sidebar ne doit jamais casser la page
        return
    lignes = [
        ("🔔 Relances à faire", nb_rel, nb_rel > 0),
        ("📅 Entretiens à venir", nb_ent, False),
        ("📝 À postuler", nb_todo, False),
    ]
    st.sidebar.html(
        '<div class="ac-side-sum">'
        + "".join(f'<div class="{"alerte" if alerte else ""}"><span>{lbl}</span><b>{n}</b></div>'
                  for lbl, n, alerte in lignes)
        + "</div>"
    )


st.logo(str(ROOT / "dashboard" / "assets" / "logo.svg"), size="large")

if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"), icon="✅")

p_nouvelle = st.Page(page_nouvelle, title="Nouvelle candidature", icon="✨", default=True)
st.session_state["page_nouvelle"] = p_nouvelle
pages = [
    p_nouvelle,
    st.Page(P.page_vue_ensemble, url_path="vue-ensemble", title="Vue d'ensemble", icon="📊"),
    st.Page(P.page_candidatures, url_path="candidatures", title="Mes candidatures", icon="📋"),
    st.Page(P.page_a_faire, url_path="a-faire", title="À faire", icon="🔔"),
    st.Page(P.page_stats, url_path="statistiques", title="Statistiques", icon="📈"),
]
nav = st.navigation(pages, position="sidebar")
sidebar_resume()
nav.run()
