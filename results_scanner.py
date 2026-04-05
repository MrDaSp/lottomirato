#!/usr/bin/env python3
"""
BetMirato Auto-Referee – Risultati Partite

Usa The-Odds-API /scores endpoint per recuperare i risultati
delle partite completate negli ultimi 3 giorni.
Non dipende più da API-Football (che ha limiti di stagione sul piano free).

Eseguito 3x/giorno via GitHub Actions.
Output: risultati.json (consumato dal frontend per l'auto-referee)
"""

import os
import requests
import json
from datetime import datetime, timedelta

# Configurazione - usa la stessa chiave dello scanner
ODDS_API_KEY = os.environ.get('ODDS_API_KEY') or 'a9bf7a15ce5ac0810b051d11d35dbc72'
ODDS_BASE_URL = "https://api.the-odds-api.com/v4/sports"

# I campionati che monitoriamo (stessi di scanner.py)
SPORT_KEYS = ['soccer_italy_serie_a', 'soccer_epl']

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
    Genera TUTTE le possibili chiavi per una partita, così il frontend
    ha molte più chance di trovare il match.
    Formato chiavi: "home-away" tutto minuscolo senza spazi.
    """
    chiavi = set()
    
    home_lower = home_name.lower()
    away_lower = away_name.lower()
    
    # Chiave base originale
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
    """
    Recupera i risultati delle partite completate usando The-Odds-API /scores.
    Supporta fino a 3 giorni nel passato.
    """
    if not ODDS_API_KEY:
        print("Errore: ODDS_API_KEY non trovata.")
        return {}
    
    results_map = {}
    
    for sport_key in SPORT_KEYS:
        print(f"\nRecupero risultati per {sport_key}...")
        
        url = f"{ODDS_BASE_URL}/{sport_key}/scores/"
        params = {
            'apiKey': ODDS_API_KEY,
            'daysFrom': 3  # Max lookback supportato dall'API
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            
            # Mostra quota rimanente
            remaining = response.headers.get('x-requests-remaining', '?')
            used = response.headers.get('x-requests-used', '?')
            print(f"   API Quota: usate={used}, rimanenti={remaining}")
            
            if response.status_code != 200:
                print(f"   ⚠️ Errore HTTP {response.status_code}: {response.text[:200]}")
                continue
                
            events = response.json()
            print(f"   -> {len(events)} eventi trovati")
            
            completed = 0
            for event in events:
                # Solo partite completate
                if not event.get('completed', False):
                    continue
                
                scores = event.get('scores', [])
                if not scores or len(scores) < 2:
                    continue
                
                home_team = event.get('home_team', '')
                away_team = event.get('away_team', '')
                
                # The-Odds-API restituisce scores come lista di oggetti {name, score}
                goals_home = None
                goals_away = None
                for score_entry in scores:
                    if score_entry.get('name') == home_team:
                        goals_home = int(score_entry.get('score', 0))
                    elif score_entry.get('name') == away_team:
                        goals_away = int(score_entry.get('score', 0))
                
                if goals_home is None or goals_away is None:
                    print(f"   ⚠️ Score mancante per {home_team} vs {away_team}")
                    continue
                
                # Determiniamo il segno finale
                if goals_home > goals_away:
                    final_result = "1"
                elif goals_home < goals_away:
                    final_result = "2"
                else:
                    final_result = "X"
                
                result_data = {
                    "result": final_result,
                    "score": f"{goals_home}-{goals_away}",
                    "date": event.get('commence_time', ''),
                    "home": home_team,
                    "away": away_team
                }
                
                # Generiamo TUTTE le chiavi possibili per massimizzare il matching
                chiavi = genera_chiavi_match(home_team, away_team)
                for chiave in chiavi:
                    results_map[chiave] = result_data
                
                completed += 1
                print(f"   ✓ {home_team} {goals_home}-{goals_away} {away_team} ({final_result}) -> {len(chiavi)} chiavi")
            
            print(f"   Totale completate: {completed}/{len(events)}")
                
        except Exception as e:
            print(f"Errore nel recupero di {sport_key}: {e}")

    return results_map

if __name__ == "__main__":
    print("=" * 60)
    print("[BOT] BetMirato Auto-Referee – Risultati via The-Odds-API")
    print("=" * 60)
    
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
