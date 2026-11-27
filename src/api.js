import * as cloud from './cloudAuth.js';

export const config = globalThis.PS_CHECKLIST_CONFIG || {};
export const hosted = Boolean(config.apiBase);

export function apiUrl(route) {
    const base = hosted ? config.apiBase.replace(/\/$/, '').replace(/\/api$/, '') + '/api' : 'api';
    return base + route;
}

export async function fetchCatalog(signal) {
    let failure;
    for (const delay of [0, 500, 1500]) {
        if (delay) await pause(delay, signal);
        signal.throwIfAborted();
        try {
            // The catalog is public. Custom headers would add a CORS preflight
            // in hosted mode, and refreshing an auth session can delay the read.
            const response = await fetch(apiUrl('/catalog'), {
                credentials: hosted ? 'omit' : 'same-origin',
                cache: 'no-store',
                signal: AbortSignal.any([signal, AbortSignal.timeout(25000)])
            });
            if (response.ok) {
                const result = await response.json();
                signal.throwIfAborted();
                if (result?.ok && Array.isArray(result.data?.contests) && Array.isArray(result.data?.problems)) {
                    return result.data;
                }
                throw new Error('Invalid contest catalog response.');
            }
            failure = new Error(`Contest catalog request returned HTTP ${response.status}.`);
            if (response.status < 500 && response.status !== 408 && response.status !== 429) break;
        } catch (error) {
            signal.throwIfAborted();
            failure = error;
        }
    }
    throw failure;
}

let guest;
function guestKey() {
    if (!guest) {
        try { guest = sessionStorage.getItem('ps-checklist-guest'); } catch {}
        if (!/^[0-9a-f]{64}$/.test(guest || '')) {
            guest = [...crypto.getRandomValues(new Uint8Array(32))].map(byte => byte.toString(16).padStart(2, '0')).join('');
            try { sessionStorage.setItem('ps-checklist-guest', guest); } catch {}
        }
    }
    return guest;
}

export async function apiFetch(route, options = {}) {
    const headers = new Headers(options.headers);
    headers.set('X-PS-Checklist', '1');
    if (hosted) {
        headers.set('X-PS-Guest', guestKey());
        const token = await cloud.accessToken();
        if (token) headers.set('Authorization', `Bearer ${token}`);
    }
    let response = await fetch(apiUrl(route), {...options, headers,
        credentials: hosted ? 'omit' : 'same-origin', cache: 'no-store'});
    if (hosted && response.status === 401 && headers.has('Authorization')) {
        const token = await cloud.accessToken(true);
        if (token) {
            headers.set('Authorization', `Bearer ${token}`);
            response = await fetch(apiUrl(route), {...options, headers, credentials: 'omit', cache: 'no-store'});
        }
    }
    return response;
}

export function pause(milliseconds, signal) {
    return new Promise((resolve, reject) => {
        if (signal?.aborted) return reject(signal.reason);
        const abort = () => { clearTimeout(timer); reject(signal.reason); };
        const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, milliseconds);
        signal?.addEventListener('abort', abort, {once: true});
    });
}
