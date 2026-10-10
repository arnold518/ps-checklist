export function parseRoundInput(source, input) {
    const value = input.trim();
    const host = source === 'cf' ? 'codeforces.com' : 'atcoder.jp';
    let url;
    try {
        if (source === 'cf' && /^[1-9]\d*$/.test(value)) url = new URL(`https://${host}/contest/${value}`);
        else if (source === 'atcoder' && /^[A-Za-z0-9_-]+$/.test(value)) url = new URL(`https://${host}/contests/${value}`);
        else url = new URL(value);
    } catch {
        throw new Error('Enter a valid contest ID or URL.');
    }
    const pattern = source === 'cf' ? /^\/(contest|gym)\/[1-9]\d*\/?$/ : /^\/contests\/[A-Za-z0-9_-]+\/?$/;
    if (!['cf', 'atcoder'].includes(source) || url.hostname !== host || url.protocol !== 'https:'
            || url.username || url.password || url.port || url.hash
            || [...url.searchParams.keys()].some(key => !['lang', 'locale'].includes(key))
            || !pattern.test(url.pathname)) throw new Error('Use a contest URL from the selected platform.');
    return url.origin + url.pathname.replace(/\/$/, '');
}

async function readResponse(response) {
    let body;
    try {
        body = await response.json();
    } catch {
        throw new Error('The fetch service is unavailable. Please try again.');
    }
    if (!body || typeof body !== 'object') throw new Error('The fetch service returned an invalid response.');
    if (!response.ok || body.ok !== true) throw new Error(body.error?.message || 'Could not fetch this round.');
    if (body.schemaVersion !== 1) throw new Error('The fetch service returned an unsupported response.');
    return body;
}

function pause(signal) {
    return new Promise((resolve, reject) => {
        if (signal.aborted) return reject(signal.reason);
        const abort = () => { clearTimeout(timer); reject(signal.reason); };
        const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 1000);
        signal.addEventListener('abort', abort, {once: true});
    });
}

export async function fetchRound(source, url, onStatus, signal) {
    onStatus('Fetching round…');
    let response = await fetch(`api/enqueue/fetch/${source}/contest`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}), signal
    });
    let body = await readResponse(response);
    const jobId = body.job?.jobId;
    if (response.status !== 202 || !/^[a-f0-9]{32}$/.test(jobId || '')) throw new Error('The fetch service did not accept the round.');
    const deadline = Date.now() + 300000;
    while (Date.now() < deadline) {
        response = await fetch(`api/job/result?id=${jobId}`, {cache: 'no-store', signal});
        body = await readResponse(response);
        if (response.status !== 202) {
            if (body.data?.source !== source || body.data?.url !== url) throw new Error('The fetch service returned a different round.');
            return {...body, jobId};
        }
        onStatus(body.job?.status === 'QUEUED' ? 'Waiting to fetch round…' : 'Fetching round…');
        await pause(signal);
    }
    throw new Error('Fetching took too long. Please try again.');
}
