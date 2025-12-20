/**
 * Cloudflare Worker: solved.ac API Proxy with CORS
 *
 * This worker proxies requests to the solved.ac API and adds proper CORS headers
 * to allow requests from your frontend application.
 *
 * Deploy this to: https://solved-ac-proxy.arnoldpark03.workers.dev
 *
 * Usage: https://solved-ac-proxy.arnoldpark03.workers.dev?problemId=1000
 */

addEventListener('fetch', event => {
    event.respondWith(handleRequest(event.request))
})

/**
 * Handles OPTIONS preflight requests for CORS
 */
function handleOptions(request) {
    return new Response(null, {
        status: 204,
        headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '86400',
        }
    })
}

/**
 * Main request handler
 */
async function handleRequest(request) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
        return handleOptions(request)
    }

    // Parse URL and get problemId parameter
    const url = new URL(request.url)
    const problemId = url.searchParams.get('problemId')

    // Validate problemId
    if (!problemId) {
        return new Response(
            JSON.stringify({
                error: 'Missing problemId parameter',
                usage: 'Add ?problemId=XXXX to the URL'
            }),
            {
                status: 400,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json',
                    'Cache-Control': 'no-cache'
                }
            }
        )
    }

    // Construct solved.ac API URL
    const apiUrl = `https://solved.ac/api/v3/problem/show?problemId=${problemId}`

    try {
        // Fetch from solved.ac API
        const response = await fetch(apiUrl, {
            headers: {
                'Accept': 'application/json',
                'User-Agent': 'PS-Checklist-Proxy/1.0'
            }
        })

        // Get response data
        const data = await response.json()

        // Check if API returned error
        if (!response.ok) {
            return new Response(
                JSON.stringify({
                    error: 'solved.ac API error',
                    status: response.status,
                    message: data.message || 'Unknown error',
                    problemId: problemId
                }),
                {
                    status: response.status,
                    headers: {
                        'Access-Control-Allow-Origin': '*',
                        'Content-Type': 'application/json',
                        'Cache-Control': 'no-cache'
                    }
                }
            )
        }

        // Return successful response with CORS headers
        return new Response(JSON.stringify(data), {
            status: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Content-Type': 'application/json',
                'Cache-Control': 'public, max-age=3600', // Cache for 1 hour
                'X-Proxy-By': 'Cloudflare Workers'
            }
        })

    } catch (error) {
        // Handle fetch errors
        return new Response(
            JSON.stringify({
                error: 'Proxy error',
                message: error.message,
                problemId: problemId,
                timestamp: new Date().toISOString()
            }),
            {
                status: 500,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json',
                    'Cache-Control': 'no-cache'
                }
            }
        )
    }
}

/**
 * Example responses:
 *
 * Success:
 * {
 *   "problemId": 1000,
 *   "titleKo": "A+B",
 *   "level": 1,
 *   "acceptedUserCount": 123456,
 *   "tags": [...]
 * }
 *
 * Error - Missing parameter:
 * {
 *   "error": "Missing problemId parameter",
 *   "usage": "Add ?problemId=XXXX to the URL"
 * }
 *
 * Error - API error:
 * {
 *   "error": "solved.ac API error",
 *   "status": 404,
 *   "message": "Problem not found"
 * }
 */
