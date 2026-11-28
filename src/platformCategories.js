import {PLATFORMS, PLATFORM_GROUPS} from './constants.js';

const division = /\bdiv(?:ision)?\.?\s*([1-4])\b/gi;
const combined = /\bdiv(?:ision)?\.?\s*1\s*(?:\+|&|and)\s*(?:div(?:ision)?\.?\s*)?2\b/i;
const codeforcesRound = /^\/(?:contest|gym)\/(\d+)\/?$/;
const atcoderRound = /^\/contests\/(abc|arc|agc|ahc|awc)(\d+)\/?$/i;
const dojSeries = /^DOJ (Starter|Beginner) Contest\s+(\d+)\b/i;
const dojRegular = /^DOJ Contest(?:\+\+)?\s+(\d+)\b/i;
const dojTeam = /(?:^|\()DOJ Team Contest\s+(\d+)\b/i;
const titleOrder = new Intl.Collator('en', {numeric:true, sensitivity:'base'});

function roundPath(source, contest) {
    const url = contest.link?.[source];
    return url ? new URL(url).pathname : '';
}

export function platformGroup(source, contest) {
    const groups = PLATFORM_GROUPS[source];
    if (!groups) return null;
    let id = 'other';
    if (source === 'atcoder') {
        const match = atcoderRound.exec(roundPath(source, contest));
        if (match) id = match[1].toLowerCase();
    } else if (source === 'doj') {
        const title = contest.title || '';
        const series = dojSeries.exec(title);
        if (series) id = series[1].toLowerCase();
        else if (dojRegular.test(title)) id = 'regular';
        else if (dojTeam.test(title)) id = 'team';
    } else if (source === 'cf') {
        if (/^\/gym\/\d+\/?$/.test(roundPath(source, contest))) id = 'gym';
        else {
            const title = contest.title || '';
            if (combined.test(title)) id = 'div1div2';
            else {
                const matches = [...title.matchAll(division)];
                if (matches.length === 1) id = `div${matches[0][1]}`;
            }
        }
    }
    return groups.find(group => group.id === id);
}

function roundNumber(source, contest) {
    let value;
    if (source === 'cf') value = codeforcesRound.exec(roundPath(source, contest))?.[1];
    else if (source === 'atcoder') value = atcoderRound.exec(roundPath(source, contest))?.[2];
    else if (source === 'doj') {
        const {title} = contest;
        value = dojSeries.exec(title)?.[2] ?? dojRegular.exec(title)?.[1] ?? dojTeam.exec(title)?.[1];
    }
    const number = Number(value);
    return Number.isSafeInteger(number) ? number : -1;
}

export function comparePlatformContests(source, left, right) {
    return roundNumber(source, right) - roundNumber(source, left)
        || titleOrder.compare(left.title, right.title)
        || left.id.localeCompare(right.id);
}

export function platformGroupPath(source, contest) {
    const platform = PLATFORMS.find(item => item.id === source);
    const group = platformGroup(source, contest);
    return platform && group ? ['Platforms', platform.name, group.name] : null;
}
