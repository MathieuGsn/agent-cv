"""Composants visuels du dashboard (HTML + CSS de dashboard/style.css)."""
from __future__ import annotations

import html
import pathlib

import streamlit as st

CSS_PATH = pathlib.Path(__file__).with_name("style.css")

# Couleurs du thème (clair). Le reste du style est dans style.css.
# Pas de mode sombre : Streamlit 1.50 ne gère qu'un seul thème personnalisé à la fois.
THEME = {
    "bg": "#f5f6fa", "surface": "#ffffff", "border": "#e5e7ef", "track": "#eceef4",
    "text": "#111827", "muted": "#6b7280",
    "primary": "#4f46e5", "primary-soft": "#eef0ff", "primary-shadow": "rgba(79,70,229,.45)",
    "good": "#16a34a", "gauge-avant": "#c7cad6",
    "shadow": "0 1px 2px rgba(16,24,40,.04), 0 4px 14px -4px rgba(16,24,40,.08)",
    "b-neutre-bg": "#eef0f3", "b-neutre-fg": "#3f4550",
    "b-attente-bg": "#e0ecff", "b-attente-fg": "#1d4ed8",
    "b-entretien-bg": "#fff3cd", "b-entretien-fg": "#8a5a00",
    "b-positif-bg": "#dcfce7", "b-positif-fg": "#166534",
    "b-negatif-bg": "#fee2e2", "b-negatif-fg": "#b42318",
}

FAMILLES = {
    "À postuler": "neutre", "Sans réponse": "neutre", "Abandonné": "neutre",
    "Postulé": "attente", "Relancé": "attente",
    "Entretien RH": "entretien", "Test technique": "entretien", "Entretien technique": "entretien",
    "Offre reçue": "positif", "Acceptée": "positif",
    "Refusé": "negatif",
}


def couleurs() -> dict:
    return THEME


def charger_style() -> None:
    """Variables du thème actif + style.css (à appeler une fois par rerun)."""
    vars_css = ";".join(f"--ac-{k}:{v}" for k, v in couleurs().items())
    st.html(f"<style>:root{{{vars_css}}}\n{CSS_PATH.read_text(encoding='utf-8')}</style>")


def e(s) -> str:
    return html.escape(str(s or ""))


# --------------------------------------------------------------------------- composants

def hero(eyebrow: str, titre: str, sous_titre: str = "") -> None:
    st.html(
        f'<div class="ac-hero"><span class="ac-eyebrow">{e(eyebrow)}</span>'
        f"<h1>{e(titre)}</h1>" + (f"<p>{e(sous_titre)}</p>" if sous_titre else "") + "</div>"
    )


def badge(texte: str, famille: str = "neutre", point: bool = False) -> str:
    pt = '<span class="pt"></span>' if point else ""
    long = " long" if len(str(texte)) > 45 else ""
    return f'<span class="ac-badge {famille}{long}">{pt}{e(texte)}</span>'


def badge_statut(statut: str) -> str:
    return badge(statut, FAMILLES.get(statut, "neutre"), point=True)


def badges(items: list[str], famille: str) -> None:
    if items:
        st.html('<div class="ac-badges">' + "".join(badge(i, famille) for i in items) + "</div>")


def stepper(etapes: list[str], etape: int, detail_actif: str = "") -> str:
    """etape = étape en cours (1-based) ; les précédentes sont faites."""
    actif = max(etape, 1)
    lignes = []
    for i, nom in enumerate(etapes, start=1):
        if i < actif:
            cls, dot = "fait", "✓"
        elif i == actif:
            cls, dot = "actif", str(i)
        else:
            cls, dot = "", str(i)
        sous = f"<small>{e(detail_actif)}</small>" if cls == "actif" and detail_actif else ""
        lignes.append(f'<li class="ac-step {cls}"><span class="ac-dot">{dot}</span>'
                      f'<span class="lbl">{e(nom)}{sous}</span></li>')
    return '<ol class="ac-stepper">' + "".join(lignes) + "</ol>"


def score(avant: float, apres: float) -> None:
    delta = apres - avant
    st.html(
        '<div class="ac-score-label">Score de correspondance</div>'
        '<div class="ac-score-row">'
        f'<span class="av">{avant:.0f}&nbsp;%</span><span class="fl">→</span>'
        f'<span class="ap">{apres:.0f}&nbsp;%</span>'
        f'<span class="delta{" neg" if delta < 0 else ""}">{delta:+.0f} pts</span></div>'
        '<div class="ac-gauge">'
        f'<div class="apres" style="width:{max(0, min(apres, 100)):.1f}%"></div>'
        f'<div class="avant" style="width:{max(0, min(avant, 100)):.1f}%"></div></div>'
        '<div class="ac-gauge-legend"><span><i style="background:var(--ac-gauge-avant)"></i>CV de base</span>'
        '<span><i style="background:var(--ac-primary)"></i>CV adapté</span></div>'
        '<p class="ac-muted" style="margin:.6rem 0 0">Part des mots-clés de l\'offre présents dans le CV.</p>'
    )


def liste(items: list[str]) -> None:
    st.html('<ul class="ac-list">' + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>")


def titre_section(t: str, n: int | None = None) -> None:
    cnt = f'<span class="cnt">{n}</span>' if n is not None else ""
    st.html(f'<div class="ac-section-title">{e(t)}{cnt}</div>')


def stat_cards(cartes: list[tuple[str, str, str, str]]) -> None:
    """Cartes de chiffres clés : (icône, valeur, libellé, ton) ; ton = '' | 'alerte' | 'bon'."""
    st.html(
        '<div class="ac-stats">'
        + "".join(
            f'<div class="ac-stat {ton}"><span class="ico">{icone}</span>'
            f'<span class="val">{e(valeur)}</span><span class="lbl">{e(libelle)}</span></div>'
            for icone, valeur, libelle, ton in cartes
        )
        + "</div>"
    )


def vide(icone: str, texte: str) -> None:
    st.html(f'<div class="ac-vide"><span>{icone}</span>{e(texte)}</div>')


def ligne_item(titre: str, sous_titre: str = "", badges_html: str = "") -> None:
    """Une ligne de liste : titre en gras, sous-titre discret, badges à droite."""
    st.html(
        f'<div class="ac-item"><div><b>{e(titre)}</b>'
        + (f'<span>{e(sous_titre)}</span>' if sous_titre else "")
        + f'</div><div class="ac-badges">{badges_html}</div></div>'
    )


def style_graphique(chart):
    """Altair aux couleurs du thème : pas de quadrillage vertical, axes discrets, police Inter."""
    t = THEME
    return (
        chart.configure(font="Inter, Segoe UI, sans-serif", background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            domain=False, ticks=False, labelColor=t["muted"], titleColor=t["muted"],
            labelFontSize=12, titleFontSize=12, titleFontWeight=500,
            gridColor=t["border"], gridDash=[3, 3], labelPadding=6,
        )
        .configure_axisX(grid=False)
        .configure_text(color=t["text"], fontSize=12, fontWeight=600)
    )
