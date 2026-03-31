#!/usr/bin/env python3
"""
BetMirato Scanner v2 – Motore Predittivo con Dati Reali

Fonti dati:
- The-Odds-API: Quote reali dei bookmaker (mercato H2H)
- API-Football v3: Statistiche squadra, infortuni, forma

Eseguito 3x/giorno via GitHub Actions.
Output: valuebets.json (consumato dal frontend)
"""

import os
import json
import math
import requests
from datetime import datetime, timedelta

# ==========================================
# CONFIGURAZIONE
# ==========================================

ODDS_API_KEY = os.environ.get('ODDS_API_KEY') or 'a9bf7a15ce5ac0810b051d11d35dbc72'
FOOTBALL_API_KEY = os.environ.get('FOOTBALL_API_KEY') or ''

FOOTBALL_API_BASE = 'https://v3.football.api-sports.io'
FOOTBALL_HEADERS = {'x-apisports-key': FOOTBALL_API_KEY}

# Mapping campionati
LEAGUES = {
    'soccer_italy_serie_a': {'id': 135, 'name': 'Serie A', 'season': 2025},
    'soccer_epl':           {'id': 39,  'name': 'Premier League', 'season': 2025}
}
SPORT_KEYS = list(LEAGUES.keys())

# Aliases nomi squadre: odds-api (lower) → possibili nomi api-football (lower)
TEAM_ALIASES = {
    'wolverhampton wanderers': ['wolverhampton', 'wolves'],
    'brighton and hove albion': ['brighton'],
    'nottingham forest': ['nottingham forest'],
    'leeds united': ['leeds'],
    'west ham united': ['west ham'],
    'tottenham hotspur': ['tottenham'],
    'newcastle united': ['newcastle'],
    'sheffield united': ['sheffield utd'],
    'leicester city': ['leicester'],
    'inter milan': ['inter'],
    'ac milan': ['milan', 'ac milan'],
    'atalanta bc': ['atalanta'],
    'hellas verona': ['verona', 'hellas verona'],
    'as roma': ['roma', 'as roma'],
}

CACHE_FILE = 'team_cache.json'
CACHE_TTL_HOURS = 24

# ==========================================
# MOTORE POISSON
# ==========================================

def fattoriale(k):
    if k <= 1: return 1
    r = 1
    for i in range(2, k + 1): r *= i
    return r

def poisson(k, lam):
    lam = max(lam, 0.05)
    return (math.exp(-lam) * math.pow(lam, k)) / fattoriale(k)

def calcola_prob_1x2(lam_h, lam_a):
    p1, px, p2 = 0.0, 0.0, 0.0
    for h in range(6):
        for a in range(6):
            p = poisson(h, lam_h) * poisson(a, lam_a)
            if h > a:   p1 += p
            elif h == a: px += p
            else:        p2 += p
    return {'1': round(p1*100, 2), 'X': round(px*100, 2), '2': round(p2*100, 2)}

# ==========================================
# CACHE
# ==========================================

def load_cache():
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'teams': {}, 'ts': {}}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def cache_fresh(cache, key):
    ts = cache.get('ts', {}).get(str(key))
    if not ts: return False
    try:
        return (datetime.now() - datetime.fromisoformat(ts)).total_seconds() < CACHE_TTL_HOURS * 3600
    except:
        return False

# ==========================================
# API-FOOTBALL
# ==========================================

def apif_get(endpoint, params):
    """Singola richiesta a API-Football con gestione errori"""
    if not FOOTBALL_API_KEY:
        return None
    try:
        r = requests.get(f"{FOOTBALL_API_BASE}/{endpoint}",
                         headers=FOOTBALL_HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            return r.json().get('response')
        print(f"  ⚠️ API-Football {r.status_code} su /{endpoint}")
        return None
    except Exception as e:
        print(f"  ❌ API-Football errore: {e}")
        return None

def get_fixtures(league_id, season):
    """Prossime partite (non ancora iniziate)"""
    today = datetime.now().strftime('%Y-%m-%d')
    future = (datetime.now() + timedelta(days=21)).strftime('%Y-%m-%d')
    return apif_get('fixtures', {
        'league': league_id, 'season': season,
        'from': today, 'to': future, 'status': 'NS'
    }) or []

def get_team_stats(team_id, league_id, season, cache):
    """Statistiche squadra con caching 24h. Ritorna dict con gol/partita e forma."""
    k = str(team_id)
    if cache_fresh(cache, k):
        return cache['teams'].get(k)

    raw = apif_get('teams/statistics', {
        'team': team_id, 'league': league_id, 'season': season
    })
    # /teams/statistics ritorna un dict, non una lista
    if not raw or not isinstance(raw, dict):
        return None

    goals = raw.get('goals', {})
    try:
        stats = {
            'gf_home': float(goals.get('for',{}).get('average',{}).get('home') or 0),
            'gf_away': float(goals.get('for',{}).get('average',{}).get('away') or 0),
            'ga_home': float(goals.get('against',{}).get('average',{}).get('home') or 0),
            'ga_away': float(goals.get('against',{}).get('average',{}).get('away') or 0),
            'form': raw.get('form', ''),
            'name': raw.get('team',{}).get('name','')
        }
    except:
        return None

    cache['teams'][k] = stats
    cache.setdefault('ts', {})[k] = datetime.now().isoformat()
    return stats

def get_injuries(fixture_id):
    """Infortuni e squalifiche per un fixture"""
    return apif_get('injuries', {'fixture': fixture_id}) or []

# ==========================================
# MATCHING NOMI SQUADRE
# ==========================================

def norm(name):
    n = name.lower().strip()
    for s in [' fc', ' afc', ' sc', ' bc', ' cf']:
        n = n.replace(s, '')
    return n.strip()

def teams_match(odds_name, football_name):
    a, b = norm(odds_name), norm(football_name)
    if a == b or a in b or b in a:
        return True
    for alias in TEAM_ALIASES.get(a, []):
        if alias in b or b in alias:
            return True
    return False

def find_fixture(match, fixtures):
    h, a = match['squadra_casa'], match['squadra_ospite']
    for f in fixtures:
        t = f.get('teams', {})
        fh = t.get('home',{}).get('name','')
        fa = t.get('away',{}).get('name','')
        if teams_match(h, fh) and teams_match(a, fa):
            return f
    return None

# ==========================================
# MODIFICATORI AUTOMATICI
# ==========================================

def mod_infortuni(injuries, home_team_id):
    """Genera modificatori e penalità da infortuni"""
    mods = []
    h_count, a_count = 0, 0

    for inj in injuries:
        player = inj.get('player', {})
        team = inj.get('team', {})
        # Skip "Questionable"
        if player.get('type','') == 'Questionable':
            continue
        is_home = team.get('id') == home_team_id
        tag = 'casa' if is_home else 'ospite'
        mods.append({
            'tipo': 'infortunio', 'squadra': tag,
            'testo': f"⚠️ {player.get('name','?')} OUT – {player.get('reason','N/D')}",
            'impatto_pct': -4
        })
        if is_home: h_count += 1
        else:        a_count += 1

    h_pen = min(h_count * -4, 0) + (-8 if h_count >= 4 else 0)
    a_pen = min(a_count * -4, 0) + (-8 if a_count >= 4 else 0)
    return mods, max(h_pen, -30), max(a_pen, -30)

def mod_forma(form_str, tag):
    """Modificatore basato sulla forma recente (ultimi 5 risultati)"""
    if not form_str or len(form_str) < 3:
        return None, 0
    r = form_str[-5:]
    score = sum(1 if c=='W' else (-1 if c=='L' else 0) for c in r)
    w, l = r.count('W'), r.count('L')
    if score >= 3:
        return {'tipo':'forma','squadra':tag,
                'testo':f"🔥 {w}V nelle ultime {len(r)} ({r})",'impatto_pct':5}, 5
    elif score <= -3:
        return {'tipo':'forma','squadra':tag,
                'testo':f"❄️ {l}S nelle ultime {len(r)} ({r})",'impatto_pct':-8}, -8
    return None, 0

# ==========================================
# FETCH QUOTE (THE-ODDS-API)
# ==========================================

def fetch_odds():
    partite = []
    for sport in SPORT_KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
        try:
            r = requests.get(url, params={
                'apiKey': ODDS_API_KEY, 'regions': 'eu', 'markets': 'h2h'
            }, timeout=15)
            if r.status_code != 200:
                print(f"  Errore Odds-API {sport}: {r.status_code}")
                continue
            for ev in r.json():
                bk = ev.get('bookmakers', [])
                if not bk: continue
                ht, at = ev['home_team'], ev['away_team']
                
                best_q = {'1':0, 'X':0, '2':0}
                best_bk = {'1':'N/D', 'X':'N/D', '2':'N/D'}
                
                # Elenco bookmaker vietati in Italia o offshore non autorizzati
                banned_bks = ['pinnacle', '1xbet', 'stake', 'mybookieag', 'bovada', 'betonlineag']
                
                for b in bk:
                    if b['key'].lower() in banned_bks:
                        continue # Evita bookmaker inaccessibili
                        
                    h2h = next((m for m in b.get('markets',[]) if m['key']=='h2h'), None)
                    if not h2h: continue
                    
                    q = {'1':0,'X':0,'2':0}
                    for o in h2h['outcomes']:
                        if o['name']==ht: q['1']=o['price']
                        elif o['name']==at: q['2']=o['price']
                        elif o['name'].lower()=='draw': q['X']=o['price']
                        
                    # Salva la quota massima trovata per questo segno
                    for segno in ['1', 'X', '2']:
                        if q[segno] > best_q[segno]:
                            best_q[segno] = q[segno]
                            best_bk[segno] = b.get('title', 'N/D')
                            
                if 0 in best_q.values(): continue
                
                try:
                    dt = datetime.strptime(ev['commence_time'],"%Y-%m-%dT%H:%M:%SZ")
                    ds = (dt+timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
                except: ds = ev['commence_time']
                
                partite.append({
                    'id':ev['id'], 'campionato':LEAGUES[sport]['name'],
                    'squadra_casa':ht, 'squadra_ospite':at,
                    'data_inizio':ds, 'quote':best_q, 'bookies':best_bk, '_sk':sport
                })
        except Exception as e:
            print(f"  Eccezione Odds-API {sport}: {e}")
    return partite

# ==========================================
# ANALISI PRINCIPALE
# ==========================================

def analizza(partite):
    cache = load_cache()
    risultati = []

    # Scarica fixtures API-Football per ogni lega
    all_fix = {}
    for sk, li in LEAGUES.items():
        if FOOTBALL_API_KEY:
            print(f"  [GET] Fixtures {li['name']}...")
            fx = get_fixtures(li['id'], li['season'])
            all_fix[sk] = fx
            print(f"     -> {len(fx)} trovate")
        else:
            all_fix[sk] = []

    for p in partite:
        sk = p.pop('_sk', '')
        li = LEAGUES.get(sk, {})
        lid, seas = li.get('id',0), li.get('season',2025)
        q1 = float(p['quote'].get('1',2.0))
        qX = float(p['quote'].get('X',3.0))
        q2 = float(p['quote'].get('2',3.5))

        fix = find_fixture(p, all_fix.get(sk, []))
        mods, verified, stats_info = [], False, {}

        if fix and FOOTBALL_API_KEY:
            hid = fix['teams']['home']['id']
            aid = fix['teams']['away']['id']
            fid = fix['fixture']['id']

            hs = get_team_stats(hid, lid, seas, cache)
            aws = get_team_stats(aid, lid, seas, cache)

            if hs and aws:
                verified = True
                # xG REALI (Dixon-Coles: media attacco casa + difesa trasferta avversaria)
                lam_h = (hs['gf_home'] + aws['ga_away']) / 2
                lam_a = (aws['gf_away'] + hs['ga_home']) / 2
                lam_h, lam_a = max(lam_h, 0.3), max(lam_a, 0.3)
                xg_raw_h, xg_raw_a = lam_h, lam_a

                # Forma
                fm_h, fp_h = mod_forma(hs.get('form',''), 'casa')
                fm_a, fp_a = mod_forma(aws.get('form',''), 'ospite')
                if fm_h: mods.append(fm_h); lam_h *= (1 + fp_h/100)
                if fm_a: mods.append(fm_a); lam_a *= (1 + fp_a/100)

                # Infortuni
                injs = get_injuries(fid)
                if injs:
                    im, hp, ap = mod_infortuni(injs, hid)
                    mods.extend(im)
                    lam_h *= (1 + hp/100)
                    lam_a *= (1 + ap/100)

                stats_info = {
                    'xg_casa': round(xg_raw_h,2), 'xg_ospite': round(xg_raw_a,2),
                    'xg_casa_mod': round(lam_h,2), 'xg_ospite_mod': round(lam_a,2)
                }
            else:
                lam_h = 2.5 / max(q1, 1.01)
                lam_a = 2.5 / max(q2, 1.01)
        else:
            # Fallback: xG impliciti dalle quote (senza random!)
            lam_h = 2.5 / max(q1, 1.01)
            lam_a = 2.5 / max(q2, 1.01)

        prob = calcola_prob_1x2(lam_h, lam_a)
        prob_raw = calcola_prob_1x2(stats_info.get('xg_casa', lam_h),
                                     stats_info.get('xg_ospite', lam_a)) if stats_info else prob

        # Miglior scommessa
        best = {'edge':-100,'segno':'','quota':0,'pb':0,'pr':0,'eg':0}
        for segno, quota in [('1',q1),('X',qX),('2',q2)]:
            if quota <= 1: continue
            imp = 100.0 / quota
            edge = float(prob[segno]) - imp
            eg   = float(prob_raw[segno]) - imp
            if edge > best['edge']:
                best = {'edge':edge,'segno':segno,'quota':quota,
                        'pb':imp,'pr':float(prob[segno]),'eg':eg}

        sem = 'rossa'
        if best['edge'] >= 5.0: sem = 'verde'
        elif best['edge'] > 0: sem = 'gialla'

        p['stats'] = stats_info
        p['modificatori'] = mods
        p['dati_verificati'] = verified
        # Probabilità complete per tutti e 3 i segni (usate dal frontend per cambiare modalità)
        p['prob_full'] = {
            '1': float(prob['1']),
            'X': float(prob['X']),
            '2': float(prob['2'])
        }
        bookies_dict = p.get('bookies', {})
        best_bk_name = bookies_dict.get(best['segno'], 'N/D')

        p['consiglio'] = {
            'segno': best['segno'], 'quota_bookmaker': best['quota'],
            'prob_bookmaker': round(best['pb'],1),
            'prob_calcolata': round(best['pr'],1),
            'edge': round(best['edge'],1),
            'edge_grezzo': round(best['eg'],1),
            'semaforo': sem,
            'bookmaker': best_bk_name
        }

        risultati.append(p)

    save_cache(cache)
    return sorted(risultati, key=lambda x: x['consiglio']['edge'], reverse=True)

# ==========================================
# MOCK DATA (fallback totale)
# ==========================================

def genera_mock():
    import random
    squA = ["Inter","Juventus","Milan","Roma","Napoli","Lazio","Atalanta","Fiorentina","Torino","Bologna"]
    squB = ["Lecce","Empoli","Verona","Cagliari","Genoa","Udinese","Monza","Parma","Como","Pisa"]
    ora = datetime.now()
    partite = []
    for i in range(12):
        h = random.choice(squA if i<6 else squB)
        a = random.choice(squB if i<6 else squA)
        if h==a: continue
        if i < 6:
            q1,qX,q2 = round(random.uniform(1.3,2.0),2), round(random.uniform(3.2,4.5),2), round(random.uniform(4.0,8.0),2)
        else:
            q1,qX,q2 = round(random.uniform(2.2,3.0),2), round(random.uniform(2.9,3.4),2), round(random.uniform(2.5,3.2),2)
        partite.append({
            'id':f"mock_{i}", 'campionato':'Serie A',
            'squadra_casa':h, 'squadra_ospite':a,
            'data_inizio':(ora+timedelta(hours=random.randint(1,72))).strftime("%Y-%m-%d %H:%M"),
            'quote':{'1':q1,'X':qX,'2':q2}, '_sk':'soccer_italy_serie_a'
        })
    return partite

# ==========================================
# MAIN
# ==========================================

def genera_dashboard():
    print("=" * 60)
    print("[BOT] BetMirato Scanner v2 - Motore con Dati Reali")
    print("=" * 60)

    print("\n[1/3] Quote da The-Odds-API...")
    partite = fetch_odds()
    print(f"   -> {len(partite)} partite trovate")

    if not partite:
        print("   [!] Nessuna partita, genero mock...")
        partite = genera_mock()

    print("\n[2/3] Arricchimento dati...")
    if FOOTBALL_API_KEY:
        print(f"   [OK] FOOTBALL_API_KEY presente ({FOOTBALL_API_KEY[:8]}...)")
    else:
        print("   [!] FOOTBALL_API_KEY assente - xG calcolati dalle quote (no modificatori)")

    analizzate = analizza(partite)

    v = sum(1 for p in analizzate if p['consiglio']['semaforo']=='verde')
    g = sum(1 for p in analizzate if p['consiglio']['semaforo']=='gialla')
    r = sum(1 for p in analizzate if p['consiglio']['semaforo']=='rossa')
    ok = sum(1 for p in analizzate if p.get('dati_verificati'))

    output = {
        "ultimo_aggiornamento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "versione_scanner": "2.0",
        "fonti_dati": {
            "quote": "The-Odds-API",
            "statistiche": "API-Football v3" if FOOTBALL_API_KEY else "N/D",
            "infortuni": "API-Football v3" if FOOTBALL_API_KEY else "N/D"
        },
        "partite": analizzate
    }

    with open('valuebets.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print(f"\n[3/3] Riepilogo: VERDI={v} GIALLI={g} ROSSI={r} | Verificati: {ok}/{len(analizzate)}")
    print("[DONE] valuebets.json generato!")

if __name__ == "__main__":
    genera_dashboard()
