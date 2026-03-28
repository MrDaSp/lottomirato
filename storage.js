const SUPABASE_URL = 'https://kvwomwmnfrfohewadesg.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt2d29td21uZnJmb2hld2FkZXNnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2ODM1MDAsImV4cCI6MjA5MDI1OTUwMH0.26BXmGc3HMAmUO47FOYSk6EM6_t4j2qViLyoi1W8_S8';

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

// --- Funzionalità Legacy Lotto rimosse per BetMirato ---
