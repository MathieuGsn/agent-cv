"""Onglet « Analyser un mail » (option C : sans connexion à la boîte mail).

Mathieu colle un mail ou dépose un .eml / .msg (ou les range dans mails/).
L'analyse est locale (scripts/mail_analyse.py) et produit une PROPOSITION :
rien n'est modifié tant qu'il n'a pas cliqué sur « Appliquer ». Aucun mail
n'est jamais supprimé ni envoyé.
"""
from __future__ import annotations

import datetime as dt
import os
import uuid

import streamlit as st

import candidatures as C
import claude_runner as R
import mail_analyse as M
import ui

PAS_DE_CHANGEMENT = "— Ne pas changer le statut —"
CONFIANCE = {"haute": ("Confiance haute", "positif"), "moyenne": ("Confiance moyenne", "entretien"),
             "faible": ("Confiance faible", "neutre")}


def conn():
    c = C.connect()
    C.appliquer_regles_auto(c)
    return c


def _ajouter_analyse(mail: dict, empreinte: str, fichier: str | None) -> None:
    analyses = st.session_state.setdefault("analyses_mails", [])
    if any(a["empreinte"] == empreinte for a in analyses):
        return
    analyses.insert(0, {"id": uuid.uuid4().hex[:8], "empreinte": empreinte, "fichier": fichier,
                        "analyse": M.analyser(mail, C.lister(conn()))})


def _retirer(aid: str) -> None:
    st.session_state["analyses_mails"] = [a for a in st.session_state.get("analyses_mails", []) if a["id"] != aid]


# =========================================================================== page

def page_mails():
    ui.hero("Mails", "Analyser un mail",
            "Colle un mail reçu ou dépose un .eml / .msg exporté d'Outlook : je retrouve la candidature "
            "et je propose la mise à jour. Rien n'est modifié sans ta validation.")
    M.MAILS_DIR.mkdir(exist_ok=True)

    gauche, droite = st.columns([3, 2], gap="medium")
    with gauche, st.container(key="carte_mail_entree"):
        onglet_texte, onglet_fichier = st.tabs(["✍️  Coller le texte", "📎  Déposer un fichier"])
        with onglet_texte:
            with st.form("mail_texte", border=False, clear_on_submit=True):
                texte = st.text_area(
                    "Texte du mail", height=210, label_visibility="collapsed",
                    placeholder="Colle ici le mail reçu, idéalement avec les lignes De / Objet / Date…",
                )
                ok_texte = st.form_submit_button("Analyser ce mail", type="primary", width="stretch")
            if ok_texte:
                if len(texte.strip()) < 30:
                    st.warning("Le texte est trop court pour être analysé.")
                else:
                    _ajouter_analyse(M.lire_texte(texte), M.empreinte(texte.encode("utf-8")), None)
                    st.rerun()
        with onglet_fichier:
            fichiers = st.file_uploader("Fichiers .eml ou .msg", type=["eml", "msg"], accept_multiple_files=True,
                                        label_visibility="collapsed")
            if st.button("Analyser les fichiers", type="primary", width="stretch", disabled=not fichiers):
                for f in fichiers:
                    data = f.getvalue()
                    try:
                        _ajouter_analyse(M.lire_fichier(f.name, data), M.empreinte(data), f.name)
                    except Exception as e:  # fichier illisible : on le dit, on continue
                        st.error(f"{f.name} : lecture impossible ({e}).")
                st.rerun()
            st.caption("Dans Outlook : ouvre le mail → Fichier → Enregistrer sous (.msg), "
                       "ou glisse le mail depuis Outlook vers un dossier.")

    with droite, st.container(key="carte_dossier_mails"):
        nouveaux = M.nouveaux_fichiers(conn())
        ui.titre_section("Dossier mails/", len(nouveaux))
        st.caption("Dépose tes mails exportés (.eml, .msg) dans le dossier mails/ du projet, "
                   "puis analyse-les ici. Les fichiers ne sont jamais supprimés.")
        b1, b2 = st.columns(2)
        if b1.button(f"Analyser ({len(nouveaux)})", type="primary", width="stretch",
                     disabled=not nouveaux):
            for p in nouveaux:
                data = p.read_bytes()
                try:
                    _ajouter_analyse(M.lire_fichier(p.name, data), M.empreinte(data), p.name)
                except Exception as e:
                    st.error(f"{p.name} : lecture impossible ({e}).")
            st.rerun()
        if b2.button("📂  Ouvrir", width="stretch") and hasattr(os, "startfile"):
            os.startfile(M.MAILS_DIR)

    analyses = st.session_state.get("analyses_mails", [])
    if analyses:
        st.html('<div style="height:.4rem"></div>')
        ui.titre_section("Propositions à valider", len(analyses))
        for a in list(analyses):
            carte_proposition(a)
    else:
        ui.vide("📨", "Aucun mail en cours d'analyse.")


# =========================================================================== une proposition

def carte_proposition(item: dict):
    a = item["analyse"]
    mail, t = a["mail"], a["type"]
    aid = item["id"]
    cands = C.lister(conn())

    with st.container(key=f"carte_prop_{aid}"):
        exp = " ".join(x for x in (mail.get("expediteur_nom"), f"<{mail['expediteur_email']}>" if mail.get("expediteur_email") else "") if x)
        date = mail.get("date")
        sous = " · ".join(x for x in (f"De {exp}" if exp else "", f"reçu le {date.strftime('%d/%m/%Y')}" if date else "",
                                       item["fichier"] or "") if x)
        conf_lbl, conf_fam = CONFIANCE[t["confiance"]]
        badges = ui.badge(t["libelle"], t["famille"], point=True) + ui.badge(conf_lbl, conf_fam)
        if a.get("plateforme"):
            badges += ui.badge(a["plateforme"], "info")
        if a.get("source_claude"):
            badges += ui.badge("Analysé par Claude", "info")
        ui.ligne_item(mail.get("objet") or "(sans objet)", sous, badges)

        if a.get("explication"):
            st.caption(f"🤖 {a['explication']}")
        elif t["indices"]:
            st.caption("Indices : " + ", ".join(f"« {i} »" for i in t["indices"][:5]))

        # Candidatures : celles qui correspondent d'abord.
        ordre = [x["candidature"] for x in a["associations"]] + [c for c in cands if c["id"] not in
                                                                    {x["candidature"]["id"] for x in a["associations"]}]
        options = [None] + [c["id"] for c in ordre]
        libelles = {c["id"]: f"{c['entreprise']} — {c['poste']} ({c['statut']})" for c in ordre}
        defaut = options.index(a["candidature"]["id"]) if a.get("candidature") and a["candidature"]["id"] in options else 0

        if not a.get("candidature"):
            st.warning("Je n'ai pas trouvé à quelle candidature ce mail correspond : choisis-la ci-dessous "
                       "ou demande à Claude.")

        with st.form(f"form_prop_{aid}", border=False):
            c1, c2 = st.columns(2)
            cid = c1.selectbox("Candidature", options, index=defaut,
                               format_func=lambda i: "— Choisir —" if i is None else libelles[i])
            statuts = [PAS_DE_CHANGEMENT] + C.STATUTS
            s_def = statuts.index(a["statut_propose"]) if a.get("statut_propose") in statuts else 0
            nouveau = c2.selectbox("Nouveau statut", statuts, index=s_def)
            c3, c4 = st.columns(2)
            d_ent = c3.date_input("Date d'entretien", value=a.get("date_entretien"), format="DD/MM/YYYY")
            note_def = f"Mail du {date.strftime('%d/%m') if date else C.today().strftime('%d/%m')} : {t['libelle'].lower()}"
            if mail.get("objet"):
                note_def += f" (« {mail['objet'][:80]} »)"
            note = c4.text_input("Note", value=note_def)
            contact_ok = bool(mail.get("expediteur_email")) and not any(
                x in mail["expediteur_email"] for x in ("noreply", "no-reply", "notification", "donotreply"))
            garder_contact = st.checkbox(
                f"Enregistrer l'expéditeur comme contact ({mail.get('expediteur_nom') or ''} {mail.get('expediteur_email') or ''})",
                value=contact_ok and t["type"] in ("entretien", "test", "offre"), disabled=not contact_ok,
            )
            b1, b2, _ = st.columns([1.3, 1, 1.7])
            appliquer = b1.form_submit_button("✅  Appliquer la mise à jour", type="primary", width="stretch")
            ignorer = b2.form_submit_button("Ignorer ce mail", width="stretch")

        if appliquer:
            if cid is None:
                st.error("Choisis d'abord la candidature concernée.")
            else:
                appliquer_proposition(item, cid, nouveau, d_ent, note, garder_contact)
        if ignorer:
            M.marquer_traite(conn(), item["empreinte"], item["fichier"], "ignoré")
            _retirer(aid)
            st.session_state["flash"] = "Mail ignoré : aucune modification."
            st.rerun()

        e1, e2 = st.columns([3, 1.2], vertical_alignment="center")
        with e1.expander("Voir le mail"):
            st.text((mail.get("corps") or "")[:5000])
        if e2.button("🤖  Demander à Claude", key=f"claude_{aid}", width="stretch",
                     help="Envoie ce mail à Claude pour une seconde analyse (sans aucun outil). Rien n'est modifié."):
            demander_a_claude(item, cands)


def appliquer_proposition(item: dict, cid: int, nouveau: str, d_ent, note: str, garder_contact: bool):
    c = conn()
    mail = item["analyse"]["mail"]
    cand = C.get(c, cid)
    champs = {}
    if d_ent and d_ent != C.parse_date(cand["date_entretien"]):
        champs["date_entretien"] = d_ent.isoformat()
    if garder_contact:
        champs["contact_email"] = mail.get("expediteur_email") or cand["contact_email"]
        if mail.get("expediteur_nom"):
            champs["contact_nom"] = mail["expediteur_nom"]
    if champs:
        C.modifier(c, cid, **champs)
    if nouveau != PAS_DE_CHANGEMENT and nouveau != cand["statut"]:
        C.changer_statut(c, cid, nouveau, note=note.strip() or None)
        msg = f"{cand['entreprise']} : {cand['statut']} → {nouveau}."
    else:
        if note.strip():
            C.ajouter_note(c, cid, note.strip())
        msg = f"{cand['entreprise']} : note ajoutée, statut inchangé."
    M.marquer_traite(c, item["empreinte"], item["fichier"], "appliqué", cid)
    _retirer(item["id"])
    st.session_state["flash"] = msg
    st.rerun()


def demander_a_claude(item: dict, cands: list[dict]):
    a = item["analyse"]
    with st.spinner("Claude analyse le mail… (20 à 40 secondes)"):
        try:
            rep = R.analyser_mail_claude(a["mail"], cands, C.STATUTS)
        except FileNotFoundError:
            st.error(R.CONSEILS_ERREUR["claude_introuvable"])
            return
        except Exception as e:
            st.error(f"Claude n'a pas pu analyser ce mail : {e}")
            return
    par_id = {c["id"]: c for c in cands}
    cand = par_id.get(rep.get("candidature_id"))
    t = dict(M.TYPES.get(rep.get("type"), {}), type=rep.get("type", "autre"))
    t.setdefault("libelle", "Autre"); t.setdefault("famille", "neutre")
    t.update(confiance="moyenne", indices=[], statut=rep.get("statut") if rep.get("statut") in C.STATUTS else None)
    statut = M.statut_propose(t, cand["statut"]) if cand else t["statut"]
    a.update(type=t, candidature=cand or a.get("candidature"), statut_propose=statut,
             explication=rep.get("explication"), source_claude=True)
    try:
        a["date_entretien"] = dt.date.fromisoformat(rep["date_entretien"]) if rep.get("date_entretien") else a.get("date_entretien")
    except ValueError:
        pass
    st.rerun()
