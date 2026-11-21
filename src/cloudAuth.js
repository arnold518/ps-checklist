// The SDK owns refresh rotation and PKCE. Hosted sessions use browser storage;
// the existing same-origin preview continues to use its HttpOnly cookies.
let clientPromise;
let callback = () => {};
let deliberate = false;
let listening = false;
export let recovering = false;

async function client() {
    const config = globalThis.PS_CHECKLIST_CONFIG || {};
    if (!config.apiBase) return null;
    if (!clientPromise) clientPromise = (async () => {
        if (!config.supabaseUrl || !config.supabaseAnonKey) throw new Error('Account configuration is missing.');
        const {createClient} = await import('@supabase/supabase-js');
        const supabase = createClient(config.supabaseUrl, config.supabaseAnonKey, {auth:{
            flowType:'pkce', detectSessionInUrl:true, persistSession:true, autoRefreshToken:true,
            storageKey:'ps-checklist-auth-' + new URL(config.supabaseUrl).hostname
        }});
        supabase.auth.onAuthStateChange((event) => {
            if (event === 'PASSWORD_RECOVERY') recovering = true;
            if (listening && !deliberate && ['SIGNED_IN','SIGNED_OUT','PASSWORD_RECOVERY'].includes(event)) {
                // SDK callbacks must return before calling other SDK methods.
                setTimeout(() => callback(event), 0);
            }
        });
        return supabase;
    })();
    return clientPromise;
}

export async function initialize(listener) {
    callback = listener;
    const supabase = await client();
    if (supabase) {
        const {error} = await supabase.auth.getSession();
        if (error) throw error;
    }
}

export function listen() { listening = true; }

export async function accessToken(refresh = false) {
    const supabase = await client();
    if (!supabase) return null;
    const {data, error} = refresh ? await supabase.auth.refreshSession() : await supabase.auth.getSession();
    if (error) {
        if (refresh) await supabase.auth.signOut({scope:'local'});
        return null;
    }
    return data.session?.access_token || null;
}

export async function signIn(email, password, signup) {
    const supabase = await client();
    deliberate = true;
    try {
        const result = signup ? await supabase.auth.signUp({email,password,options:{emailRedirectTo:redirect()}})
            : await supabase.auth.signInWithPassword({email,password});
        if (result.error) throw result.error;
        return {confirmationRequired:!result.data.session};
    } finally { deliberate = false; }
}

function redirect() { return location.origin + location.pathname; }

export async function signInProvider(provider) {
    const {error} = await (await client()).auth.signInWithOAuth({provider,options:{redirectTo:redirect()}});
    if (error) throw error;
}

export async function signOut() {
    deliberate = true;
    try {
        const {error} = await (await client()).auth.signOut({scope:'local'});
        if (error) throw error;
        recovering = false;
    } finally { deliberate = false; }
}

export async function resetPassword(email) {
    const {error} = await (await client()).auth.resetPasswordForEmail(email,{redirectTo:redirect()});
    if (error) throw error;
}

export async function updatePassword(password) {
    const {error} = await (await client()).auth.updateUser({password});
    if (error) throw error;
    recovering = false;
}
