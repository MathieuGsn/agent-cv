"""Onglets de suivi : Vue d'ensemble, Mes candidatures, À faire, Statistiques."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib

import altair as alt
import pandas as pd
import streamlit as st
import yaml

import candidatures as C
import claude_runner as R
import ui

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIMAIRE = ui.THEME["primary"]


def conn():
    c = C.connect()
    C.appliquer_regles_auto(c)
    return c


def fmt_date(s) -> str:
    d = C.parse_date(s)
    return d.strftime("%d/%m/%Y") if d else ""


def bandeau_demo(cands: list[dict]):
    n = sum(1 for c in cands if c["est_demo"])
    if n:
        st.caption(f"🧪 {n} candidature(s) de démo affichée(s) : elles seront supprimées quand tu valides le dashboard.")


def personal() -> dict:
    for nom in ("master_cv.yaml", "master_cv.example.yaml"):
        p = ROOT / "data" / nom
        if p.exists():
            return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("personal", {}) or {}
    return {}


def langue_offre(c: dict) -> str:
    if c.get("chemin_dossier_offre"):
        r = ROOT / c["chemin_dossier_offre"] / "resultat.json"
        if r.exists():
            try:
                return json.loads(r.read_text(encoding="utf-8")).get("langue") or "fr"
            except json.JSONDecodeError:
                pass
    return "fr"


def mail_relance(c: dict) -> tuple[str, str]:
    """Mail de relance court et poli (modèle fixe, rien d'inventé). Jamais envoyé."""
    p = personal()
    signature = "\n".join(x for x in (p.get("name"), p.get("phone"), p.get("email")) if x)
    poste = c["poste"] or "le poste proposé"
    date = fmt_date(c["date_candidature"])
    if langue_offre(c) == "en":
        hello = f"Dear {c['contact_nom']}," if c.get("contact_nom") else "Dear Hiring Team,"
        objet = f"Follow-up on my application – {poste}"
        corps = (
            f"{hello}\n\n"
            f"I am writing to follow up on my application for the {poste} position at {c['entreprise']}, "
            f"submitted on {date}.\n\n"
            "I am still very interested in this opportunity and remain available for a 6-month "
            "end-of-studies internship starting in March 2027.\n\n"
            "I would be glad to discuss my application with you, and I am happy to provide any "
            "additional information you may need.\n\n"
            f"Kind regards,\n{signature}"
        )
    else:
        hello = f"Bonjour {c['contact_nom']}," if c.get("contact_nom") else "Bonjour,"
        objet = f"Suivi de ma candidature – {poste}"
        corps = (
            f"{hello}\n\n"
            f"Je me permets de revenir vers vous au sujet de ma candidature au poste de {poste} "
            f"chez {c['entreprise']}, envoyée le {date}.\n\n"
            "Ce poste m'intéresse toujours beaucoup et je reste disponible pour un stage de fin "
            "d'études de 6 mois à partir de mars 2027.\n\n"
            "Je serais ravi d'échanger avec vous sur ma candidature et reste à votre disposition "
            "pour toute information complémentaire.\n\n"
            f"Bien cordialement,\n{signature}"
        )
    return objet, corps


def ouvrir_fichier(chemin: str):
    p = ROOT / chemin
    if p.exists() and hasattr(os, "startfile"):
        os.startfile(p)  # ouvre dans l'application par défaut (lecteur PDF)
    else:
        st.warning(f"Fichier introuvable : {chemin}")


# =========================================================================== Vue d'ensemble

def page_vue_ensemble():
    ui.hero("Vue d'ensemble", "Où en sont mes candidatures", "Les chiffres clés et l'activité des dernières semaines.")
    c = conn()
    cands = C.lister(c)
    bandeau_demo(cands)
    if not cands:
        ui.vide("📭", "Aucune candidature pour l'instant. Commence par l'onglet Nouvelle candidature.")
        return
    b = C.bilan(c)
    taux = f"{b['taux_reponse']:.0f} %" if b["taux_reponse"] is not None else "—"
    delai = f"{b['delai_moyen_reponse_jours']:.0f} j" if b["delai_moyen_reponse_jours"] is not None else "—"
    ui.stat_cards([
        ("📁", str(b["total"]), "Candidatures", ""),
        ("📤", str(b["envoyees"]), "Postulées", ""),
        ("⏳", str(b["en_attente"]), "En attente", ""),
        ("🎙️", str(b["entretiens_en_cours"]), "Entretiens en cours", "bon" if b["entretiens_en_cours"] else ""),
        ("✖️", str(b["refus"]), "Refus", ""),
        ("💬", taux, "Taux de réponse", ""),
        ("⏱️", delai, "Délai moyen de réponse", ""),
    ])

    gauche, droite = st.columns([3, 2], gap="medium")
    with gauche, st.container(key="carte_semaines"):
        ui.titre_section("Candidatures envoyées par semaine")
        dates = [C.parse_date(x["date_candidature"]) for x in cands
                 if x["statut"] != "À postuler" and x["date_candidature"]]
        if dates:
            lundi = lambda d: d - dt.timedelta(days=d.weekday())  # noqa: E731
            fin = lundi(C.today())
            debut = min(lundi(min(dates)), fin - dt.timedelta(weeks=11))
            semaines = pd.date_range(debut, fin, freq="7D").date
            compte = pd.Series([lundi(d) for d in dates]).value_counts()
            df = pd.DataFrame({"semaine": semaines, "n": [int(compte.get(s, 0)) for s in semaines]})
            df["libelle"] = [f"Semaine du {s.strftime('%d/%m')}" for s in df["semaine"]]
            df["sem"] = [s.strftime("%d/%m") for s in df["semaine"]]
            chart = (
                alt.Chart(df)
                .mark_bar(color=PRIMAIRE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, width={"band": 0.55})
                .encode(
                    x=alt.X("sem:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("n:Q", title=None, scale=alt.Scale(domain=[0, max(2, int(df["n"].max()))]),
                            axis=alt.Axis(values=list(range(0, max(2, int(df["n"].max())) + 1)), format="d")),
                    tooltip=[alt.Tooltip("libelle:N", title="Semaine"), alt.Tooltip("n:Q", title="Envoyées")],
                )
                .properties(height=260)
            )
            st.altair_chart(ui.style_graphique(chart), use_container_width=True, theme=None)
        else:
            ui.vide("📤", "Aucune candidature envoyée pour l'instant.")

    with droite, st.container(key="carte_statuts"):
        ui.titre_section("Répartition par statut")
        lignes = [(s, n) for s, n in b["par_statut"].items() if n]
        maxi = max(n for _, n in lignes)
        st.html(
            '<div class="ac-repart">'
            + "".join(
                f'<div class="r"><span class="s">{ui.badge_statut(s)}</span>'
                f'<span class="bar"><i style="width:{100 * n / maxi:.0f}%"></i></span><b>{n}</b></div>'
                for s, n in lignes
            )
            + "</div>"
        )


# =========================================================================== Mes candidatures

def _df_candidatures(cands: list[dict]) -> pd.DataFrame:
    rows = []
    for c in cands:
        rows.append({
            "id": c["id"],
            "Entreprise": c["entreprise"],
            "Poste": c["poste"],
            "Statut": c["statut"],
            "Source": c["source"] or "",
            "Ville": c["ville"] or "",
            "Candidature": C.parse_date(c["date_candidature"]),
            "Relance": C.parse_date(c["date_relance_prevue"]),
            "Entretien": C.parse_date(c["date_entretien"]),
            "Score": c["score_apres"],
        })
    return pd.DataFrame(rows)


def _df_affichage(df: pd.DataFrame) -> pd.DataFrame:
    """Version texte pour le tableau : Streamlit affiche « None » dans les cellules vides,
    donc dates en AAAA-MM-JJ (tri correct) et score en texte, vides = ""."""
    out = df.copy()
    for col in ("Candidature", "Relance", "Entretien"):
        out[col] = out[col].map(lambda d: d.isoformat() if d else "")
    out["Score"] = out["Score"].map(lambda v: f"{v:>3.0f} %" if v is not None and pd.notna(v) else "")
    return out


def _style_statut(val: str) -> str:
    fam = ui.FAMILLES.get(val, "neutre")
    t = ui.THEME
    return f"background-color: {t[f'b-{fam}-bg']}; color: {t[f'b-{fam}-fg']}; font-weight: 600"


def page_candidatures():
    ui.hero("Suivi", "Mes candidatures", "Filtre, trie, clique sur une ligne pour voir le détail et mettre à jour.")
    c = conn()
    cands = C.lister(c)
    bandeau_demo(cands)

    if not cands:
        ui.vide("📭", "Aucune candidature pour l'instant.")
        with st.expander("➕ Ajouter une candidature faite sans l'agent"):
            formulaire_ajout()
        return

    with st.container(key="carte_filtres"):
        f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
        statuts = f1.multiselect("Statut", C.STATUTS, placeholder="Tous")
        sources = f2.multiselect("Source", sorted({x["source"] for x in cands if x["source"]}), placeholder="Toutes")
        periode = f3.date_input("Période de candidature", value=(), format="DD/MM/YYYY")
        recherche = f4.text_input("Recherche", placeholder="🔎  Entreprise ou poste…")

    df = _df_candidatures(cands)
    if statuts:
        df = df[df["Statut"].isin(statuts)]
    if sources:
        df = df[df["Source"].isin(sources)]
    if isinstance(periode, tuple) and len(periode) == 2:
        df = df[df["Candidature"].map(lambda d: d is not None and periode[0] <= d <= periode[1])]
    if recherche:
        n = C.normaliser(recherche)
        df = df[df.apply(lambda r: n in C.normaliser(f"{r['Entreprise']} {r['Poste']}"), axis=1)]

    with st.container(key="carte_tableau"):
        h1, h2, h3 = st.columns([4, 1.4, 1.6], vertical_alignment="center")
        with h1:
            ui.titre_section("Candidatures", len(df))
        export = _df_candidatures(cands)
        for col in ("Candidature", "Relance", "Entretien"):
            export[col] = export[col].map(lambda d: d.strftime("%d/%m/%Y") if d else "")
        h3.download_button(
            "⬇  Exporter en CSV", export.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"candidatures_{C.today().isoformat()}.csv", mime="text/csv", width="stretch",
        )
        evt = st.dataframe(
            _df_affichage(df).style.map(_style_statut, subset=["Statut"]),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "id": None,
                "Entreprise": st.column_config.Column(width=160),
                "Poste": st.column_config.Column(width=150),
                "Statut": st.column_config.Column(width=112),
                "Source": st.column_config.Column(width=150),
                "Ville": None,  # visible dans le détail
                "Candidature": st.column_config.Column(width=92),
                "Relance": st.column_config.Column(width=92),
                "Entretien": st.column_config.Column(width=92),
                "Score": st.column_config.Column("Score", width=60,
                                                 help="Score de correspondance mots-clés après adaptation"),
            },
            key="table_candidatures",
        )
        st.caption("Clique sur une ligne pour ouvrir le détail. Clique sur un en-tête de colonne pour trier.")

    with st.expander("➕ Ajouter une candidature faite sans l'agent"):
        formulaire_ajout()

    lignes = evt.selection.rows if evt and evt.selection else []
    if lignes:
        detail_candidature(int(df.iloc[lignes[0]]["id"]))


def detail_candidature(cid: int):
    c = conn()
    cand = C.get(c, cid)
    if not cand:
        return
    with st.container(key=f"carte_detail_entete_{cid}"):
        st.html(
            '<div class="ac-item"><div>'
            f'<b style="font-size:1.25rem">{ui.e(cand["entreprise"])}</b><span>{ui.e(cand["poste"])}</span>'
            f'</div><div class="ac-badges">{ui.badge_statut(cand["statut"])}</div></div>'
        )

    g, d = st.columns([3, 2], gap="medium")
    with g:
        with st.container(key=f"carte_detail_infos_{cid}"):
            ui.titre_section("Informations")
            infos = {
                "Source": cand["source"], "Ville": cand["ville"], "Contrat": cand["type_contrat"],
                "Début souhaité": fmt_date(cand["date_debut_souhaitee"]),
                "Date de candidature": fmt_date(cand["date_candidature"]),
                "Relance prévue": fmt_date(cand["date_relance_prevue"]),
                "Entretien": fmt_date(cand["date_entretien"]),
                "Contact": " — ".join(x for x in (cand["contact_nom"], cand["contact_email"]) if x),
                "Score de correspondance": (f"{cand['score_avant']:.0f} % → {cand['score_apres']:.0f} %"
                                            if cand["score_avant"] is not None and cand["score_apres"] is not None else ""),
            }
            st.html('<dl class="ac-dl">' + "".join(
                f"<dt>{ui.e(k)}</dt><dd>{ui.e(v)}</dd>" for k, v in infos.items() if v) + "</dl>")
            b1, b2, b3 = st.columns(3)
            if cand["lien_offre"]:
                b1.link_button("🔗  Voir l'offre", cand["lien_offre"], width="stretch")
            if cand["chemin_cv_pdf"] and (ROOT / cand["chemin_cv_pdf"]).exists():
                if b2.button("📄  Ouvrir le CV", key=f"open{cid}", width="stretch"):
                    ouvrir_fichier(cand["chemin_cv_pdf"])
                b3.download_button("⬇  CV PDF", (ROOT / cand["chemin_cv_pdf"]).read_bytes(),
                                   file_name=pathlib.Path(cand["chemin_cv_pdf"]).name,
                                   mime="application/pdf", key=f"dl{cid}", width="stretch")
        with st.container(key=f"carte_detail_hist_{cid}"):
            ui.titre_section("Historique")
            hist = C.historique(c, cid)
            st.html('<ol class="ac-timeline">' + "".join(
                f'<li><span class="d">{fmt_date(h["date"])}</span>'
                f'<span class="c">{ui.badge_statut(h["nouveau_statut"])}'
                + (' <span class="ac-badge">auto</span>' if h["automatique"] else "")
                + (f'<em>{ui.e(h["note"])}</em>' if h["note"] else "")
                + "</span></li>"
                for h in reversed(hist)) + "</ol>")
            if cand["notes"]:
                ui.titre_section("Notes")
                st.text(cand["notes"])

    with d, st.container(key=f"carte_detail_maj_{cid}"):
        ui.titre_section("Mettre à jour")
        with st.form(f"maj{cid}", border=False):
            nouveau = st.selectbox("Statut", C.STATUTS, index=C.STATUTS.index(cand["statut"]))
            note = st.text_area("Ajouter une note", height=80)
            d_ent = st.date_input("Date d'entretien", value=C.parse_date(cand["date_entretien"]), format="DD/MM/YYYY")
            contact_nom = st.text_input("Contact (nom)", value=cand["contact_nom"] or "")
            contact_email = st.text_input("Contact (email)", value=cand["contact_email"] or "")
            ok = st.form_submit_button("Enregistrer", type="primary", width="stretch")
        if ok:
            champs = {}
            if d_ent != C.parse_date(cand["date_entretien"]):
                champs["date_entretien"] = d_ent.isoformat() if d_ent else None
            if contact_nom != (cand["contact_nom"] or ""):
                champs["contact_nom"] = contact_nom or None
            if contact_email != (cand["contact_email"] or ""):
                champs["contact_email"] = contact_email or None
            if champs:
                C.modifier(c, cid, **champs)
            if nouveau != cand["statut"]:
                C.changer_statut(c, cid, nouveau, note=note.strip() or None)
            elif note.strip():
                C.ajouter_note(c, cid, note.strip())
            st.session_state["flash"] = "Candidature mise à jour."
            st.rerun()

        with st.popover("🗑  Supprimer cette candidature", width="stretch"):
            st.warning("Supprime la ligne et son historique du suivi (le dossier de l'offre et le PDF restent sur le disque).")
            if st.button("Confirmer la suppression", key=f"del{cid}", type="primary"):
                C.supprimer(c, cid)
                st.session_state["flash"] = "Candidature supprimée."
                st.rerun()


def formulaire_ajout():
    with st.form("ajout", clear_on_submit=True, border=False):
        a, b = st.columns(2)
        entreprise = a.text_input("Entreprise *")
        poste = b.text_input("Poste *")
        a, b, c3 = st.columns(3)
        statut = a.selectbox("Statut", C.STATUTS, index=C.STATUTS.index("Postulé"))
        date_c = b.date_input("Date de candidature", value=C.today(), format="DD/MM/YYYY")
        source = c3.selectbox("Source", [""] + C.SOURCES, format_func=lambda s: s or "—")
        a, b = st.columns(2)
        lien = a.text_input("Lien de l'offre")
        ville = b.text_input("Ville")
        a, b = st.columns(2)
        contact_nom = a.text_input("Contact (nom)")
        contact_email = b.text_input("Contact (email)")
        notes = st.text_area("Notes", height=70)
        ok = st.form_submit_button("Ajouter la candidature", type="primary")
    if ok:
        if not entreprise.strip() or not poste.strip():
            st.error("L'entreprise et le poste sont obligatoires.")
            return
        doublons = [x for x in C.chercher(conn(), entreprise)
                    if C.normaliser(x["entreprise"]) == C.normaliser(entreprise)]
        cid = C.ajouter(
            conn(), entreprise=entreprise.strip(), poste=poste.strip(), statut=statut,
            date_candidature=date_c.isoformat() if statut != "À postuler" else None,
            source=source, lien_offre=lien, ville=ville, contact_nom=contact_nom,
            contact_email=contact_email, notes=notes, chemin_cv_pdf=None,
        )
        msg = f"Candidature #{cid} ajoutée."
        if doublons:
            msg += f" Attention : {len(doublons)} autre(s) candidature(s) chez {entreprise} existai(en)t déjà."
        st.session_state["flash"] = msg
        st.rerun()


# =========================================================================== À faire

def page_a_faire():
    ui.hero("Actions", "À faire", "Relances, entretiens et candidatures pas encore envoyées.")
    c = conn()
    bandeau_demo(C.lister(c))
    relances = C.relances_dues(c)
    ent = C.entretiens_a_venir(c)
    todo = C.a_postuler(c)

    ui.titre_section("Relances à envoyer", len(relances))
    if not relances:
        ui.vide("✅", "Aucune relance à faire aujourd'hui.")
    for cand in relances:
        retard = cand["jours_retard"]
        with st.container(key=f"carte_relance_{cand['id']}"):
            ui.ligne_item(
                f"{cand['entreprise']} — {cand['poste']}",
                f"Postulé le {fmt_date(cand['date_candidature'])} · relance prévue le "
                f"{fmt_date(cand['date_relance_prevue'])} · à : "
                f"{cand['contact_email'] or 'via la plateforme ou le service recrutement'}",
                ui.badge("Aujourd'hui" if retard == 0 else f"En retard de {retard} j",
                         "entretien" if retard == 0 else "negatif", point=True),
            )
            objet, corps = mail_relance(cand)
            st.code(f"Objet : {objet}", language=None)
            st.code(corps, language=None)
            m, bt = st.columns([3, 1.2], vertical_alignment="center")
            m.caption("Copie avec l'icône en haut à droite de chaque bloc. Rien n'est envoyé automatiquement.")
            if bt.button("J'ai envoyé la relance", key=f"rel{cand['id']}", type="primary", width="stretch"):
                C.changer_statut(c, cand["id"], "Relancé", note="Relance envoyée")
                st.session_state["flash"] = f"{cand['entreprise']} passé en Relancé."
                st.rerun()

    st.html('<div style="height:.6rem"></div>')
    gauche, droite = st.columns(2, gap="medium")
    with gauche, st.container(key="carte_entretiens"):
        ui.titre_section("Entretiens à venir", len(ent))
        if not ent:
            ui.vide("📅", "Aucun entretien prévu.")
        for cand in ent:
            jours = (C.parse_date(cand["date_entretien"]) - C.today()).days
            quand = "Aujourd'hui" if jours == 0 else ("Demain" if jours == 1 else f"Dans {jours} jours")
            ui.ligne_item(f"{cand['entreprise']}", f"{cand['poste']} · {fmt_date(cand['date_entretien'])}",
                          ui.badge(quand, "entretien", point=True) + ui.badge_statut(cand["statut"]))

    with droite, st.container(key="carte_todo"):
        ui.titre_section("Candidatures à envoyer", len(todo))
        if not todo:
            ui.vide("🎉", "Tout est envoyé.")
        for cand in todo:
            ui.ligne_item(
                f"{cand['entreprise']}",
                f"{cand['poste']} · ajoutée le {fmt_date(cand['date_statut'])}",
                ui.badge(f"{cand['score_apres']:.0f} %", "info") if cand["score_apres"] is not None else "",
            )
            d1, d2 = st.columns(2)
            if d1.button("✅  J'ai postulé", key=f"post{cand['id']}", type="primary", width="stretch"):
                C.changer_statut(c, cand["id"], "Postulé")
                st.session_state["flash"] = f"{cand['entreprise']} passé en Postulé (relance à J+10)."
                st.rerun()
            offre = ROOT / (cand["chemin_dossier_offre"] or "_") / "offre.txt"
            if d2.button("🔄  Régénérer le CV", key=f"regen{cand['id']}", width="stretch",
                         disabled=not offre.exists(),
                         help=None if offre.exists() else "Pas d'offre enregistrée pour cette candidature."):
                try:
                    job = R.lancer(offre.read_text(encoding="utf-8"), cand["lien_offre"] or "",
                                   cand["entreprise"], cand["poste"], cand["source"] or "")
                except FileNotFoundError:
                    st.error(R.CONSEILS_ERREUR["claude_introuvable"])
                else:
                    st.session_state["job"] = str(job)
                    st.switch_page(st.session_state["page_nouvelle"], query_params={"job": job.name})


# =========================================================================== Statistiques

def page_stats():
    ui.hero("Analyse", "Statistiques", "Ce qui marche le mieux pour toi.")
    c = conn()
    cands = C.lister(c)
    bandeau_demo(cands)

    with st.container(key="carte_sources"):
        ui.titre_section("Taux de réponse par source")
        st.caption("Part des candidatures envoyées qui ont reçu une réponse (entretien, test, offre ou refus).")
        par_source = C.stats_par_source(c)
        if not par_source:
            ui.vide("📤", "Pas encore de candidature envoyée.")
        else:
            df = pd.DataFrame(par_source)
            df["libelle"] = df.apply(lambda r: f"{r['taux_reponse']:.0f} %  ({r['reponses']}/{r['envoyees']})", axis=1)
            base = alt.Chart(df).encode(
                y=alt.Y("source:N", sort="-x", title=None, axis=alt.Axis(labelFontSize=13, labelColor=ui.THEME["text"])),
                x=alt.X("taux_reponse:Q", title=None, scale=alt.Scale(domain=[0, 115]),
                        axis=alt.Axis(values=[0, 25, 50, 75, 100], format="d", labelExpr="datum.value + ' %'")),
                tooltip=[alt.Tooltip("source:N", title="Source"),
                         alt.Tooltip("envoyees:Q", title="Envoyées"),
                         alt.Tooltip("reponses:Q", title="Réponses"),
                         alt.Tooltip("taux_reponse:Q", title="Taux (%)", format=".0f")],
            )
            bars = base.mark_bar(color=PRIMAIRE, cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                 height={"band": 0.55})
            txt = base.mark_text(align="left", dx=6).encode(text="libelle:N")
            st.altair_chart(ui.style_graphique((bars + txt).properties(height=max(140, 48 * len(df)))),
                            use_container_width=True, theme=None)
            if df["envoyees"].max() < 5:
                st.caption("Peu de candidatures par source : ces taux deviendront parlants avec plus de données.")

    envoyees = [x for x in cands if x["statut"] != "À postuler" and x["date_candidature"]
                and x["score_apres"] is not None]
    rep = [x["score_apres"] for x in envoyees if C.a_repondu(c, x["id"])]
    sans = [x["score_apres"] for x in envoyees if not C.a_repondu(c, x["id"])]
    with st.container(key="carte_scores"):
        ui.titre_section("Score de correspondance et réponses")
        st.caption("Score moyen après adaptation, selon que l'entreprise a répondu ou non.")
        ui.stat_cards([
            ("💬", f"{sum(rep) / len(rep):.0f} %" if rep else "—", f"Avec réponse ({len(rep)})", "bon"),
            ("⏳", f"{sum(sans) / len(sans):.0f} %" if sans else "—", f"Sans réponse pour l'instant ({len(sans)})", ""),
        ])
        st.caption("Seules les candidatures passées par l'agent ont un score.")
