"""Tests de l'analyse de mails (scripts/mail_analyse.py).

Lancer : python -m unittest discover -s tests
"""
import datetime as dt
import pathlib
import sys
import unittest
from email.message import EmailMessage

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import mail_analyse as M  # noqa: E402


def cand(id_, entreprise, poste="Stage Data Engineer", statut="Postulé"):
    return {"id": id_, "entreprise": entreprise, "poste": poste, "statut": statut}


CANDS = [
    cand(1, "Nimbus Analytics"),
    cand(2, "Orbital Energie", "Stage Data Analyst", "Entretien RH"),
    cand(3, "Quanta Bank", "Stage Data Scientist"),
]


def mail(objet="", corps="", exp="", nom=""):
    return {"objet": objet, "corps": corps, "expediteur_email": exp, "expediteur_nom": nom, "date": dt.date(2026, 11, 24)}


class Classement(unittest.TestCase):
    def test_refus_fr(self):
        t = M.classer(mail("Votre candidature", "Malheureusement, nous ne donnerons pas suite à votre candidature."))
        self.assertEqual(t["type"], "refus")
        self.assertEqual(t["statut"], "Refusé")

    def test_refus_avant_entretien(self):
        # Un refus après entretien parle d'entretien : c'est quand même un refus.
        t = M.classer(mail("Suite à notre entretien", "Merci pour l'entretien. Malheureusement votre profil n'a pas été retenu."))
        self.assertEqual(t["type"], "refus")

    def test_entretien(self):
        t = M.classer(mail("Stage Data", "Nous aimerions échanger avec vous. Pouvez-vous nous donner vos disponibilités ?"))
        self.assertEqual(t["type"], "entretien")
        self.assertEqual(t["statut"], "Entretien RH")

    def test_entretien_technique(self):
        t = M.classer(mail("Prochaine étape", "Nous vous proposons un entretien technique avec l'équipe."))
        self.assertEqual(t["statut"], "Entretien technique")

    def test_test_technique_en(self):
        t = M.classer(mail("Next step", "Please complete the following HackerRank coding challenge within 5 days."))
        self.assertEqual(t["type"], "test")

    def test_accuse_reception(self):
        t = M.classer(mail("Candidature reçue", "Nous avons bien reçu votre candidature et revenons vers vous rapidement."))
        self.assertEqual(t["type"], "accuse")

    def test_offre(self):
        t = M.classer(mail("Proposition", "Nous sommes heureux de vous proposer une proposition de stage à partir de mars."))
        self.assertEqual(t["type"], "offre")

    def test_autre(self):
        self.assertEqual(M.classer(mail("Newsletter", "Découvrez nos actualités du mois."))["type"], "autre")


class Association(unittest.TestCase):
    def test_domaine_expediteur(self):
        a = M.associer(mail("Votre candidature", "Bonjour", exp="rh@nimbus-analytics.com"), CANDS)
        self.assertEqual(a[0]["candidature"]["id"], 1)

    def test_nom_dans_objet_via_plateforme(self):
        m = mail("Quanta Bank - Votre candidature", "Merci", exp="no-reply@teamtailor.com")
        a = M.associer(m, CANDS)
        self.assertEqual(a[0]["candidature"]["id"], 3)
        self.assertEqual(M.plateforme(m), "Teamtailor")

    def test_aucune(self):
        self.assertEqual(M.associer(mail("Bonjour", "Rien à voir", exp="x@autre.fr"), CANDS), [])


class StatutPropose(unittest.TestCase):
    def test_pas_de_retour_en_arriere(self):
        t = M.classer(mail("", "Nous avons bien reçu votre candidature."))
        self.assertIsNone(M.statut_propose(t, "Entretien RH"))

    def test_accuse_sur_a_postuler(self):
        t = M.classer(mail("", "Nous avons bien reçu votre candidature."))
        self.assertEqual(M.statut_propose(t, "À postuler"), "Postulé")

    def test_refus_toujours_possible(self):
        t = M.classer(mail("", "Malheureusement nous ne donnerons pas suite."))
        self.assertEqual(M.statut_propose(t, "Entretien technique"), "Refusé")

    def test_analyse_complete(self):
        a = M.analyser(mail("Orbital Energie : entretien", "Seriez-vous disponible pour un entretien le 03/12 à 14h ?",
                            exp="talent@orbital-energie.fr"), CANDS)
        self.assertEqual(a["candidature"]["id"], 2)
        self.assertIsNone(a["statut_propose"])  # déjà en Entretien RH
        self.assertEqual(a["date_entretien"], dt.date(2026, 12, 3))


class Lecture(unittest.TestCase):
    def test_eml(self):
        msg = EmailMessage()
        msg["From"] = "Équipe RH <rh@quanta-bank.com>"
        msg["Subject"] = "Votre candidature"
        msg["Date"] = "Tue, 24 Nov 2026 10:00:00 +0100"
        msg.set_content("Malheureusement, nous ne donnerons pas suite.")
        m = M.lire_eml(msg.as_bytes())
        self.assertEqual(m["expediteur_email"], "rh@quanta-bank.com")
        self.assertEqual(m["date"], dt.date(2026, 11, 24))
        self.assertIn("Malheureusement", m["corps"])

    def test_texte_colle_avec_entetes(self):
        m = M.lire_texte("De : Julie Martin <julie@nimbus.io>\nObjet : Entretien\nDate : 24/11/2026\n\nBonjour Mathieu,\nOn se parle ?")
        self.assertEqual(m["expediteur_email"], "julie@nimbus.io")
        self.assertEqual(m["objet"], "Entretien")
        self.assertTrue(m["corps"].startswith("Bonjour"))

    def test_date_libre(self):
        ref = dt.date(2026, 11, 24)
        self.assertEqual(M._date_libre("le 3 décembre à 10h", ref), dt.date(2026, 12, 3))
        self.assertEqual(M._date_libre("le 15 janvier", ref), dt.date(2027, 1, 15))


if __name__ == "__main__":
    unittest.main()
