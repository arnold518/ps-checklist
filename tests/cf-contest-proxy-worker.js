/**
 * Cloudflare Worker - Codeforces Contest Materials Proxy
 *
 * This worker fetches contest HTML and extracts announcement/editorial links
 * Deploy at: https://workers.cloudflare.com
 *
 * Usage: https://your-worker.workers.dev?contestId=1891&type=contest
 */

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  // Enable CORS
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  }

  // Handle preflight request
  if (request.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders })
  }

  try {
    // Parse query parameters
    const url = new URL(request.url)
    const contestId = url.searchParams.get('contestId')
    const contestType = url.searchParams.get('type') || 'contest' // 'contest' or 'gym'

    if (!contestId) {
      return new Response(JSON.stringify({
        error: 'Missing contestId parameter'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    // Fetch the contest page
    const contestUrl = `https://codeforces.com/${contestType}/${contestId}`
    const response = await fetch(contestUrl)
    const html = await response.text()

    // Extract announcement and editorial links
    const materials = extractContestMaterials(html)

    return new Response(JSON.stringify(materials), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })

  } catch (error) {
    return new Response(JSON.stringify({
      error: error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })
  }
}

function extractContestMaterials(html) {
  const materials = {
    announcement: null,
    editorial: null
  }

  // Method 1: Look for "Announcement" and "Tutorial" in sidebar
  // Pattern: <a href="/blog/entry/123456">Announcement</a>
  const announcementMatch = html.match(/<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>[^<]*Announcement[^<]*<\/a>/i) ||
                           html.match(/<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>[^<]*Анонс[^<]*<\/a>/i)

  const editorialMatch = html.match(/<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>[^<]*Tutorial[^<]*<\/a>/i) ||
                         html.match(/<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>[^<]*Разбор[^<]*<\/a>/i)

  if (announcementMatch) {
    materials.announcement = `https://codeforces.com${announcementMatch[1]}`
  }

  if (editorialMatch) {
    materials.editorial = `https://codeforces.com${editorialMatch[1]}`
  }

  // Method 2: Look in contest materials section specifically
  // Find the "Contest materials" section and extract links
  const materialsSection = html.match(/<div[^>]*class="[^"]*contest-materials[^"]*"[^>]*>([\s\S]*?)<\/div>/i)
  if (materialsSection) {
    const section = materialsSection[1]

    // Extract all blog entry links from this section
    const blogLinks = section.matchAll(/<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>([^<]+)<\/a>/gi)

    for (const match of blogLinks) {
      const link = match[1]
      const text = match[2].toLowerCase()

      if ((text.includes('announcement') || text.includes('анонс')) && !materials.announcement) {
        materials.announcement = `https://codeforces.com${link}`
      }

      if ((text.includes('tutorial') || text.includes('разбор')) && !materials.editorial) {
        materials.editorial = `https://codeforces.com${link}`
      }
    }
  }

  return materials
}
