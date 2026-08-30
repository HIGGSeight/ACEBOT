"""
Génère data/marges.json à partir des cotes actuelles, pour alimenter le
site web (index.html). Reprend la même logique de détection que
arbitrage_bot.py, mais écrit un fichier JSON au lieu d'envoyer une alerte
Telegram, et ne garde que les 2 meilleures marges du jour.

Ce script est fait pour tourner automatiquement chaque jour via GitHub
Actions (voir .github/workflows/publier.yml), mais tu peux aussi le lancer
à la main pour tester.
"""

import json
import os
from datetime import date

import requests

# ============================================================
# CONFIGURATION
# ============================================================

# En local, tu peux mettre ta clé ici entre guillemets pour tester.
# En production (GitHub Actions), la clé vient d'un "secret" GitHub et
# n'est jamais écrite dans le code — voir les instructions de mise en ligne.
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "TA_CLE_THE_ODDS_API")

SPORTS = [
    "tennis_atp_us_open",
    "tennis_wta_us_open",
    "basketball_nba",
    "icehockey_nhl",
    "mma_mixed_martial_arts",
    "soccer_epl",
]
REGIONS = "eu"
MARKETS = "h2h"
SEUIL_MARGE_MIN = 2.3
NB_MARGES_A_PUBLIER = 2

FICHIER_SORTIE = os.path.join(os.path.dirname(__file__), "data", "marges.json")


# ============================================================
# LOGIQUE DE DÉTECTION (identique à arbitrage_bot.py)
# ============================================================

def recuperer_cotes(sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": "decimal",
    }
    reponse = requests.get(url, params=params, timeout=15)
    if reponse.status_code != 200:
        print(f"Erreur API pour {sport} ({reponse.status_code}) : {reponse.text}")
        return []
    return reponse.json()


def meilleures_cotes_par_issue(match):
    meilleures = {}
    for bookmaker in match.get("bookmakers", []):
        nom_bookmaker = bookmaker["title"]
        for marche in bookmaker.get("markets", []):
            if marche["key"] != "h2h":
                continue
            for issue in marche["outcomes"]:
                nom_issue = issue["name"]
                cote = issue["price"]
                if nom_issue not in meilleures or cote > meilleures[nom_issue][0]:
                    meilleures[nom_issue] = (cote, nom_bookmaker)
    return meilleures


def calculer_arbitrage(meilleures_cotes):
    if len(meilleures_cotes) < 2:
        return False, 0, {}

    somme_probabilites = sum(1 / cote for cote, _ in meilleures_cotes.values())
    if somme_probabilites >= 1:
        return False, 0, {}

    marge = (1 - somme_probabilites) * 100
    return True, marge, meilleures_cotes


# ============================================================
# GÉNÉRATION DU JSON POUR LE SITE
# ============================================================

def nom_lisible_sport(cle_sport):
    """Transforme 'tennis_atp_us_open' en 'Tennis · Atp Us Open' pour l'affichage."""
    morceaux = cle_sport.split("_")
    return morceaux[0].capitalize() + " · " + " ".join(m.upper() if len(m) <= 3 else m.capitalize() for m in morceaux[1:])


def construire_entree(sport, match, marge, meilleures_cotes):
    return {
        "sport": nom_lisible_sport(sport),
        "match": f"{match.get('home_team', '?')} vs {match.get('away_team', '?')}",
        "marge": round(marge, 2),
        "issues": [
            {"nom": nom_issue, "bookmaker": bookmaker, "cote": cote}
            for nom_issue, (cote, bookmaker) in meilleures_cotes.items()
        ],
    }


def main():
    toutes_les_marges = []

    for sport in SPORTS:
        matchs = recuperer_cotes(sport)
        for match in matchs:
            meilleures = meilleures_cotes_par_issue(match)
            existe, marge, cotes = calculer_arbitrage(meilleures)
            if existe and marge >= SEUIL_MARGE_MIN:
                toutes_les_marges.append(construire_entree(sport, match, marge, cotes))

    # On garde seulement les meilleures, triées par marge décroissante
    toutes_les_marges.sort(key=lambda m: m["marge"], reverse=True)
    top_marges = toutes_les_marges[:NB_MARGES_A_PUBLIER]

    donnees = {
        "date": date.today().isoformat(),
        "marges": top_marges,
    }

    os.makedirs(os.path.dirname(FICHIER_SORTIE), exist_ok=True)
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)

    print(f"{len(top_marges)} marge(s) écrite(s) dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()
