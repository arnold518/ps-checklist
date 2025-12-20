#!/usr/bin/env node

/**
 * Command-line tester for solved.ac API proxy
 *
 * Usage:
 *   node test-api.js              # Test default problem (1000)
 *   node test-api.js 2000         # Test specific problem ID
 *   node test-api.js batch        # Test multiple problems
 */

const https = require('https');
const http = require('http');

const PROXY_URL = 'https://solved-ac-proxy.arnoldpark03.workers.dev';
const COLORS = {
    reset: '\x1b[0m',
    green: '\x1b[32m',
    red: '\x1b[31m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    cyan: '\x1b[36m'
};

/**
 * Fetch wrapper for Node.js
 */
function fetchAPI(url) {
    return new Promise((resolve, reject) => {
        const urlObj = new URL(url);
        const client = urlObj.protocol === 'https:' ? https : http;

        const req = client.get(url, (res) => {
            let data = '';

            res.on('data', chunk => {
                data += chunk;
            });

            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    resolve({
                        status: res.statusCode,
                        headers: res.headers,
                        data: parsed
                    });
                } catch (e) {
                    reject(new Error(`Failed to parse JSON: ${e.message}`));
                }
            });
        });

        req.on('error', (e) => {
            reject(e);
        });

        req.setTimeout(10000, () => {
            req.destroy();
            reject(new Error('Request timeout'));
        });
    });
}

/**
 * Test a single problem
 */
async function testProblem(problemId) {
    console.log(`\n${COLORS.cyan}Testing Problem ID: ${problemId}${COLORS.reset}`);
    console.log('='.repeat(50));

    const url = `${PROXY_URL}?problemId=${problemId}`;
    console.log(`URL: ${url}\n`);

    try {
        const result = await fetchAPI(url);

        // Check CORS headers
        const corsHeaders = {
            'access-control-allow-origin': result.headers['access-control-allow-origin'],
            'access-control-allow-methods': result.headers['access-control-allow-methods']
        };

        console.log(`${COLORS.blue}Response Status:${COLORS.reset} ${result.status}`);
        console.log(`${COLORS.blue}CORS Headers:${COLORS.reset}`);
        console.log(`  Allow-Origin: ${corsHeaders['access-control-allow-origin'] || COLORS.red + 'MISSING!' + COLORS.reset}`);
        console.log(`  Allow-Methods: ${corsHeaders['access-control-allow-methods'] || 'Not set'}`);

        if (result.status === 200) {
            console.log(`\n${COLORS.green}✓ SUCCESS${COLORS.reset}`);
            console.log(`${COLORS.blue}Problem Data:${COLORS.reset}`);
            console.log(`  ID: ${result.data.problemId}`);
            console.log(`  Title: ${result.data.titleKo || result.data.title}`);
            console.log(`  Level: ${result.data.level}`);
            console.log(`  Accepted Users: ${result.data.acceptedUserCount}`);

            if (!corsHeaders['access-control-allow-origin']) {
                console.log(`\n${COLORS.yellow}⚠ WARNING: CORS headers missing!${COLORS.reset}`);
                console.log('This will cause errors in browser even though API works in Node.js');
            }

            return { success: true, problemId, level: result.data.level };
        } else {
            console.log(`\n${COLORS.red}✗ FAILED${COLORS.reset}`);
            console.log(`Error: HTTP ${result.status}`);
            console.log(JSON.stringify(result.data, null, 2));
            return { success: false, problemId, error: `HTTP ${result.status}` };
        }

    } catch (error) {
        console.log(`\n${COLORS.red}✗ FAILED${COLORS.reset}`);
        console.log(`Error: ${error.message}`);
        return { success: false, problemId, error: error.message };
    }
}

/**
 * Test multiple problems
 */
async function testBatch(problemIds) {
    console.log(`\n${COLORS.cyan}Batch Testing ${problemIds.length} Problems${COLORS.reset}`);
    console.log('='.repeat(50));

    const results = [];

    for (const problemId of problemIds) {
        const result = await testProblem(problemId);
        results.push(result);
        // Small delay to avoid rate limiting
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    // Summary
    const successCount = results.filter(r => r.success).length;
    const failCount = results.filter(r => !r.success).length;

    console.log(`\n${'='.repeat(50)}`);
    console.log(`${COLORS.cyan}Batch Test Summary${COLORS.reset}`);
    console.log(`${COLORS.green}Successful: ${successCount}/${problemIds.length}${COLORS.reset}`);
    console.log(`${COLORS.red}Failed: ${failCount}/${problemIds.length}${COLORS.reset}`);

    if (failCount > 0) {
        console.log(`\n${COLORS.red}Failed Problems:${COLORS.reset}`);
        results.filter(r => !r.success).forEach(r => {
            console.log(`  - Problem ${r.problemId}: ${r.error}`);
        });
    }
}

/**
 * Main
 */
async function main() {
    const args = process.argv.slice(2);

    console.log(`${COLORS.cyan}solved.ac API Proxy Tester${COLORS.reset}`);
    console.log(`Proxy URL: ${PROXY_URL}\n`);

    if (args[0] === 'batch') {
        await testBatch([1000, 2000, 3000, 10000, 20000]);
    } else {
        const problemId = args[0] || '1000';
        await testProblem(problemId);
    }

    console.log(`\n${COLORS.cyan}Tips:${COLORS.reset}`);
    console.log('- If CORS headers are missing, update your Cloudflare Worker');
    console.log('- See tests/cloudflare-worker-fixed.js for the correct code');
    console.log('- Open tests/difficulty-api-test.html for browser testing');
    console.log();
}

// Run
main().catch(error => {
    console.error(`${COLORS.red}Unhandled error:${COLORS.reset}`, error);
    process.exit(1);
});
