import os
import requests
import json
from datetime import datetime, timedelta

# Configurazione API-Football
API_KEY = os.environ.get('FOOTBALL_API_KEY')
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {
    'x-apisports-key': API_KEY
}

# ========================================
# NORMALIZZAZIONE NOMI (identica a scanner.py per garantire matching)
# ========================================

TEAM_ALIASES = {
    'wolverhampton wanderers': ['wolverhampton', 'wolves'],
    'brighton and hove albion': ['brighton'],
    'nottingham forest': ['nottingham forest', 'nott\'ham forest'],
    'leeds united': ['leeds'],
    'west ham united': ['west ham'],
    'tottenham hotspur': ['tottenham'],
    'newcastle united': ['newcastle'],
    'sheffield united': ['sheffield utd'],
    'leicester city': ['leicester'],
    'inter milan': ['inter', 'internazionale'],
    'ac milan': ['milan', 'ac milan'],
    'atalanta bc': ['atalanta'],
    'hellas verona': ['verona', 'hellas verona'],
    'as roma': ['roma', 'as roma'],
    'ssc napoli': ['napoli'],
    'juventus': ['juventus'],
    'ss lazio': ['lazio'],
    'afc bournemouth': ['bournemouth'],
    'crystal palace': ['crystal palace'],
    'manchester city': ['manchester city', 'man city'],
    'manchester united': ['manchester united', 'man united', 'man utd'],
    'burnley': ['burnley'],
}

def norm(name):
    """Normalizza il nome di una squadra rimuovendo suffissi comuni"""
    n = name.lower().strip()
    for s in [' fc', ' afc', ' sc', ' bc', ' cf', ' ssc', ' ss', ' ac', ' as']:
        n = n.replace(s, '')
    return n.strip()

def genera_chiavi_match(home_name, away_name):
    """
    Genera TUTTE le possibili chiavi per una partita, cosí il frontend
    ha molte più chance di trovare il match.
    Formato chiavi: "home-away" tutto minuscolo senza spazi.
    """
    chiavi = set()
    
    home_lower = home_name.lower()
    away_lower = away_name.lower()
    
    # Chiave base originale (come faceva prima)
    base = f"{home_name}-{away_name}".lower().replace(" ", "")
    chiavi.add(base)
    
    # Chiave normalizzata (senza suffissi FC, SC, etc.)
    norm_key = f"{norm(home_name)}-{norm(away_name)}".replace(" ", "")
    chiavi.add(norm_key)
    
    # Chiavi con alias per home
    home_aliases = [home_lower]
    for canonical, aliases in TEAM_ALIASES.items():
        if norm(home_name) in [norm(canonical)] + [norm(a) for a in aliases]:
            home_aliases.extend([canonical] + aliases)
    
    # Chiavi con alias per away
    away_aliases = [away_lower]
    for canonical, aliases in TEAM_ALIASES.items():
        if norm(away_name) in [norm(canonical)] + [norm(a) for a in aliases]:
            away_aliases.extend([canonical] + aliases)
    
    # Genera tutte le combinazioni
    for h in home_aliases:
        for a in away_aliases:
            chiavi.add(f"{h}-{a}".replace(" ", ""))
            chiavi.add(f"{norm(h)}-{norm(a)}".replace(" ", ""))
    
    return list(chiavi)


def fetch_recent_results():
    if not API_KEY:
        print("Errore: FOOTBALL_API_KEY non trovata.")
        return {}

    # Controlliamo i risultati degli ultimi 5 giorni (per coprire weekend + infrasettimanali)
    date_to = datetime.now().strftime('%Y-%m-%d')
    date_from = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    
    results_map = {}
    
    # Lista delle leghe che monitoriamo (solo quelle realmente usate dallo scanner)
    leagues = [135, 39]  # Serie A, Premier League
    
    # Determina la stagione corretta (anno di inizio della stagione in corso)
    now = datetime.now()
    season = now.year if now.month >= 8 else now.year - 1
    
    for league_id in leagues:
        print(f"Recupero risultati per Lega ID {league_id} (season {season})...")
        url = f"{BASE_URL}/fixtures?league={league_id}&season={season}&from={date_from}&to={date_to}&status=FT"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            data = response.json()
            
            # Log errori API per debug
            errors = data.get('errors', {})
            if errors:
                print(f"   ⚠️ API-Football errors: {errors}")
            remaining = data.get('paging', {}).get('total', '?')
            print(f"   API response status: {response.status_code}, results: {data.get('results', 0)}")
            
            fixtures = data.get('response', [])
            print(f"   -> {len(fixtures)} partite finite trovate")
            
            for fixture in fixtures:
                f_id = fixture['fixture']['id']
                home_name = fixture['teams']['home']['name']
                away_name = fixture['teams']['away']['name']
                goals_home = fixture['goals']['home']
                goals_away = fixture['goals']['away']
                
                # Determiniamo il segno finale
                if goals_home > goals_away: final_result = "1"
                elif goals_home < goals_away: final_result = "2"
                else: final_result = "X"
                
                result_data = {
                    "result": final_result,
                    "score": f"{goals_home}-{goals_away}",
                    "date": fixture['fixture']['date'],
                    "home": home_name,
                    "away": away_name
                }
                
                # Generiamo TUTTE le chiavi possibili per massimizzare il matching
                chiavi = genera_chiavi_match(home_name, away_name)
                for chiave in chiavi:
                    results_map[chiave] = result_data
                    
                print(f"   ✓ {home_name} {goals_home}-{goals_away} {away_name} ({final_result}) -> {len(chiavi)} chiavi")
                
        except Exception as e:
            print(f"Errore nel recupero della lega {league_id}: {e}")

    return results_map

if __name__ == "__main__":
    recent_results = fetch_recent_results()
    
    output = {
        "ultimo_aggiornamento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risultati": recent_results
    }
    
    with open('risultati.json', 'w') as f:
        json.dump(output, f, indent=4)
    
    # Conta risultati unici (non chiavi duplicate)
    unique_matches = len(set(r.get('date','') + r.get('score','') for r in recent_results.values()))
    print(f"\nCompletato! Salvati {len(recent_results)} chiavi ({unique_matches} partite uniche) in risultati.json")
