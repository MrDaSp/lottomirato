// LottoMirato - Supabase Storage Layer
const SUPABASE_URL = 'https://kvwomwmnfrfohewadesg.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt2d29td21uZnJmb2hld2FkZXNnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2ODM1MDAsImV4cCI6MjA5MDI1OTUwMH0.26BXmGc3HMAmUO47FOYSk6EM6_t4j2qViLyoi1W8_S8';
const STORICO_URL = 'https://raw.githubusercontent.com/MrDaSp/lottomirato/main/storico01-oggi.txt';

let sbClient;
let currentUser = null;
let currentSession = null;

function initSupabase() {
    sbClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    sbClient.auth.onAuthStateChange((event, session) => {
        currentSession = session;
        currentUser = session?.user || null;
    });
}

// --- Auth ---
async function sbSignUp(email, password, displayName) {
    const { data, error } = await sbClient.auth.signUp({
        email, password,
        options: { data: { display_name: displayName || email.split('@')[0] } }
    });
    if (error) throw error;
    // Create default plan
    if (data.user) {
        await sbClient.from('user_plans').upsert({
            user_id: data.user.id, budget_per_estrazione: 6, estrazioni_pianificate: 10
        });
    }
    return data;
}

async function sbSignIn(email, password) {
    const { data, error } = await sbClient.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data;
}

async function sbSignOut() {
    await sbClient.auth.signOut();
    currentUser = null; currentSession = null;
}

async function sbGetSession() {
    const { data } = await sbClient.auth.getSession();
    currentSession = data.session;
    currentUser = data.session?.user || null;
    return data.session;
}

function getDisplayName() {
    return currentUser?.user_metadata?.display_name || currentUser?.email?.split('@')[0] || 'Utente';
}

// --- Strategies ---
async function sbGetStrategies() {
    const { data, error } = await sbClient.from('strategies').select('*').eq('attiva', true);
    if (error) throw error;
    return data || [];
}

async function sbSaveStrategies(strategies) {
    const uid = currentUser.id;
    await sbClient.from('strategies').delete().eq('user_id', uid);
    const rows = strategies.map(s => ({
        user_id: uid, ruota: s.ruota, ambo_1: s.ambo[0], ambo_2: s.ambo[1], estratto: s.estratto, attiva: true
    }));
    const { error } = await sbClient.from('strategies').insert(rows);
    if (error) throw error;
}

function strategiesToGiocata(strategies) {
    const giocata = {};
    for (const s of strategies) {
        giocata[s.ruota] = { ambo: [s.ambo_1, s.ambo_2], estratto: s.estratto };
    }
    return giocata;
}

// --- Plans ---
async function sbGetPlan() {
    const { data } = await sbClient.from('user_plans').select('*').single();
    return data || { budget_per_estrazione: 6, estrazioni_pianificate: 10 };
}

async function sbSavePlan(budget, estrazioni) {
    const { error } = await sbClient.from('user_plans').upsert({
        user_id: currentUser.id, budget_per_estrazione: budget, estrazioni_pianificate: estrazioni
    });
    if (error) throw error;
}

// --- Extractions Played ---
async function sbGetPlayed() {
    const { data } = await sbClient.from('extractions_played').select('*').order('data_estrazione');
    return data || [];
}

async function sbToggleExtraction(dataEstr, giocata, budgetPerEstr) {
    const { error } = await sbClient.from('extractions_played').upsert({
        user_id: currentUser.id, data_estrazione: dataEstr,
        giocata, speso: giocata ? budgetPerEstr : 0
    }, { onConflict: 'user_id,data_estrazione' });
    if (error) throw error;
}

async function sbGetBudgetSpent() {
    const { data } = await sbClient.from('extractions_played').select('speso').eq('giocata', true);
    return (data || []).reduce((sum, r) => sum + (r.speso || 0), 0);
}

// --- Storico Download ---
async function downloadStorico() {
    try {
        const resp = await fetch(STORICO_URL);
        if (!resp.ok) throw new Error('Download failed');
        return await resp.text();
    } catch (e) {
        console.error('Errore download storico:', e);
        throw e;
    }
}
