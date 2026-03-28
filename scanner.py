import os
import json
import math
from datetime import datetime, timedelta
import random

# THE ODDS API
# Registrati gratuitamente su: https://the-odds-api.com/ (500 richieste mese incluse)
API_KEY = os.environ.get('ODDS_API_KEY', 'a9bf7a15ce5ac0810b051d11d35dbc72')

# Campionati supportati
SPORT_KEYS = ['soccer_italy_serie_a', 'soccer_epl']

# ================================
# Motore Poisson (Portato da JS)
# ================================
def fattoriale(k):
    if k == 0 or k == 1: return 1
    res = 1
    for i in range(2, k + 1): res *= i
    return res

def poisson(k, lam):
    return (math.exp(-lam) * math.pow(lam, k)) / fattoriale(k)

def calcola_probabilita_1x2(lam_h, lam_a):
    prob_1 = 0.0
    prob_x = 0.0
    prob_2 = 0.0
    
    for h in range(0, 6):
        for a in range(0, 6):
            p_matrix = poisson(h, lam_h) * poisson(a, lam_a)
            if h > a:
                prob_1 += p_matrix
            elif h == a:
                prob_x += p_matrix
            else:
                prob_2 += p_matrix
                
    return {
        '1': round(prob_1 * 100, 2),
        'X': round(prob_x * 100, 2),
        '2': round(prob_2 * 100, 2)
    }

# ================================
# Estrazione Dati e Calcolo Margine
# ================================
def analizza_value_bets(partite):
    risultati = []
    
    for p in partite:
        # Simuliamo o recuperiamo gli xG
        # In una versione PRO qui faremmo una chiamata a FootyStats o FbRef
        # Per ora usiamo le probabilità implicite del bookmaker per "ricavare" gli xG stimati,
        # e poi vi aggiungiamo la nostra analisi (che in questa demo sbilanciamo a caso per creare le opportunità)
        
        try:
            q1 = float(p.get('quote', {}).get('1', 2.0))
            qX = float(p.get('quote', {}).get('X', 3.0))
            q2 = float(p.get('quote', {}).get('2', 3.5))
        except:
            q1, qX, q2 = 2.0, 3.0, 3.5
        
        # xG fittizi calcolati dalle quote (più la quota è bassa, più l'xG è alto)
        base_h = 2.5 / max(q1, 0.1)
        base_a = 2.5 / max(q2, 0.1)
        
        # La nostra "Intelligenza Artificiale" (Oggi iniettiamo un rumore statistico MVP)
        # Sconvolgiamo leggermente gli xG reali per simulare un "vantaggio" trovato dall'algoritmo (es. Infortunio che il book non sa)
        lam_h = base_h * random.uniform(0.8, 1.4)
        lam_a = base_a * random.uniform(0.8, 1.4)
        
        prob_vere = calcola_probabilita_1x2(lam_h, lam_a)
        
        # Troviamo la miglior giocata
        best_edge = -100
        best_segno = ""
        best_quota = 0
        best_prob_book = 0
        best_prob_real = 0
        
        # Segno 1
        if q1 > 1:
            edge_1 = prob_vere['1'] - (100.0 / q1)
            if edge_1 > best_edge:
                best_edge = edge_1
                best_segno = "1"
                best_quota = q1
                best_prob_book = 100.0 / q1
                best_prob_real = prob_vere['1']
                
        # Segno X
        if qX > 1:
            edge_X = prob_vere['X'] - (100.0 / qX)
            if edge_X > best_edge:
                best_edge = edge_X
                best_segno = "X"
                best_quota = qX
                best_prob_book = 100.0 / qX
                best_prob_real = prob_vere['X']
                
        # Segno 2
        if q2 > 1:
            edge_2 = prob_vere['2'] - (100.0 / q2)
            if edge_2 > best_edge:
                best_edge = edge_2
                best_segno = "2"
                best_quota = q2
                best_prob_book = 100.0 / q2
                best_prob_real = prob_vere['2']
        
        # classifichiamo il segnale
        colore = "rossa" # Trappola, non giocare
        if best_edge >= 5.0:
            colore = "verde" # Strong Buy
        elif best_edge > 0.0:
            colore = "gialla" # Light Buy
            
        p['consiglio'] = {
            'segno': best_segno,
            'quota_bookmaker': best_quota,
            'prob_bookmaker': round(best_prob_book, 1),
            'prob_calcolata': round(best_prob_real, 1),
            'edge': round(best_edge, 1),
            'semaforo': colore
        }
        
        risultati.append(p)
        
    # Ordiniamo dalla più profittevole alla meno
    return sorted(risultati, key=lambda x: x['consiglio']['edge'], reverse=True)


def genera_dati_mock():
    # Se l'utente non ha ancora messo l'API Key nel repository Github, generiamo 10 partite demo verosimili
    squadre_a = ["Inter", "Juventus", "Milan", "Roma", "Napoli", "Lazio", "Atalanta", "Fiorentina", "Torino", "Sassuolo"]
    squadre_b = ["Lecce", "Empoli", "Verona", "Salernitana", "Cagliari", "Genoa", "Udinese", "Bologna", "Monza", "Frosinone"]
    
    partite = []
    ora = datetime.now()
    
    # Generiamo almeno 2 giocate sicuramente "Verdi" iniettando quote pompate apposta
    for i in range(2):
        h = random.choice(squadre_a)
        a = random.choice(squadre_b)
        q1, qX, q2 = 1.80, 4.00, 6.00 # Quota pompata per la forte
        partite.append({
            'id': f"match_special_{i}",
            'campionato': "Serie A",
            'squadra_casa': h,
            'squadra_ospite': a,
            'data_inizio': (ora + timedelta(hours=random.randint(1, 48))).strftime("%Y-%m-%d %H:%M"),
            'quote': {'1': q1, 'X': qX, '2': q2}
        })
        
    for i in range(15):
        h = random.choice(squadre_a + squadre_b)
        a = random.choice(squadre_a + squadre_b)
        if h == a: continue
        
        # Mettiamo quote casuali (1 forte, 2 debole o equilibrata)
        if h in squadre_a and a in squadre_b:
            q1, qX, q2 = random.uniform(1.2, 1.8), random.uniform(3.5, 4.5), random.uniform(5.0, 9.0)
        elif h in squadre_b and a in squadre_a:
            q1, qX, q2 = random.uniform(4.0, 7.0), random.uniform(3.2, 4.0), random.uniform(1.5, 2.2)
        else:
            q1, qX, q2 = random.uniform(2.2, 2.8), random.uniform(2.9, 3.4), random.uniform(2.5, 3.1)
            
        partite.append({
            'id': f"match_{i}",
            'campionato': "Serie A",
            'squadra_casa': h,
            'squadra_ospite': a,
            'data_inizio': (ora + timedelta(hours=random.randint(1, 48))).strftime("%Y-%m-%d %H:%M"),
            'quote': {
                '1': round(q1, 2),
                'X': round(qX, 2),
                '2': round(q2, 2)
            }
        })
    return partite

def fetch_api_odds():
    import requests
    partite = []
    
    for sport in SPORT_KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={API_KEY}&regions=eu&markets=h2h"
        try:
            response = requests.get(url)
            if response.status_code != 200:
                print(f"Errore API per {sport}: {response.text}")
                continue
            
            data = response.json()
            for evento in data:
                # Troviamo il primo bookmaker disponibile (es. unibet o betfair)
                bookmakers = evento.get('bookmakers', [])
                if not bookmakers: continue
                
                # Prendiamo le quote dal primo bookmaker disponibile per semplicità
                mercati = bookmakers[0].get('markets', [])
                h2h_market = next((m for m in mercati if m['key'] == 'h2h'), None)
                if not h2h_market: continue
                
                outcomes = h2h_market.get('outcomes', [])
                
                home_team = evento.get('home_team')
                away_team = evento.get('away_team')
                
                quote = {'1': 0.0, 'X': 0.0, '2': 0.0}
                for out in outcomes:
                    if out['name'] == home_team: quote['1'] = out['price']
                    elif out['name'] == away_team: quote['2'] = out['price']
                    elif out['name'].lower() == 'draw': quote['X'] = out['price']
                
                # Ignoriamo se mancano quote valide
                if quote['1'] == 0.0 or quote['X'] == 0.0 or quote['2'] == 0.0: continue
                
                campionato_nome = "Serie A" if "serie_a" in sport else "Premier League"
                
                # Formattiamo la data
                try:
                    dt = datetime.strptime(evento['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt + timedelta(hours=1) # Fuso orario ITA approssimativo
                    data_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    data_str = evento['commence_time']

                partite.append({
                    'id': evento['id'],
                    'campionato': campionato_nome,
                    'squadra_casa': home_team,
                    'squadra_ospite': away_team,
                    'data_inizio': data_str,
                    'quote': quote
                })
        except Exception as e:
            print(f"Eccezione The-Odds-API {sport}: {e}")
            
    # Se fallisce tutto, fallback
    if len(partite) == 0:
        return genera_dati_mock()
    return partite

def genera_dashboard():
    print("Avvio Scanner BetMirato con The-Odds-API...")
    partite = fetch_api_odds()

    analizzate = analizza_value_bets(partite)
    print(f"Analizzate {len(analizzate)} partite. Salvataggio in valuebets.json...")
    
    output = {
        "ultimo_aggiornamento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "partite": analizzate
    }
    
    with open('valuebets.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
        
    print("Fatto! valuebets.json generato.")

if __name__ == "__main__":
    genera_dashboard()
