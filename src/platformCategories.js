import {PLATFORMS, PLATFORM_GROUPS} from './constants.js';

const division = /\bdiv(?:ision)?\.?\s*([1-4])\b/gi;
const combined = /\bdiv(?:ision)?\.?\s*1\s*(?:\+|&|and)\s*(?:div(?:ision)?\.?\s*)?2\b/i;

export function platformGroup(source, contest) {
    const groups = PLATFORM_GROUPS[source];
    if (!groups) return null;
    let id = 'other';
    const url = contest.link?.[source];
    const path = url ? new URL(url).pathname : '';
    if (source === 'atcoder') {
        const match = /^\/contests\/(abc|arc|agc|ahc|awc)\d+\/?$/i.exec(path);
        if (match) id = match[1].toLowerCase();
    } else if (source === 'doj') {
        const title = contest.title || '';
        const series = /^DOJ (Starter|Beginner) Contest\s+\d+\b/i.exec(title);
        if (series) id = series[1].toLowerCase();
        else if (/^DOJ Contest(?:\+\+)?\s+\d+\b/i.test(title)) id = 'regular';
        else if (/(?:^|\()DOJ Team Contest\s+\d+\b/i.test(title)) id = 'team';
    } else if (source === 'cf') {
        if (/^\/gym\/\d+\/?$/.test(path)) id = 'gym';
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

export function platformGroupPath(source, contest) {
    const platform = PLATFORMS.find(item => item.id === source);
    const group = platformGroup(source, contest);
    return platform && group ? ['Platforms', platform.name, group.name] : null;
}
