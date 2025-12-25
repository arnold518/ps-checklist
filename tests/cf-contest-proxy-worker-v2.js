/**
 * Cloudflare Worker - Codeforces Contest Materials Proxy (v2 - Enhanced)
 *
 * Deploy at: https://workers.cloudflare.com
 * Test: https://your-worker.workers.dev?contestId=1891&type=contest&debug=true
 */

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  }

  if (request.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders })
  }

  try {
    const url = new URL(request.url)
    const contestId = url.searchParams.get('contestId')
    const contestType = url.searchParams.get('type') || 'contest'
    const debug = url.searchParams.get('debug') === 'true'

    if (!contestId) {
      return new Response(JSON.stringify({
        error: 'Missing contestId parameter',
        usage: '?contestId=1891&type=contest'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    // Fetch the contest page
    const contestUrl = `https://codeforces.com/${contestType}/${contestId}`
    const response = await fetch(contestUrl)

    if (!response.ok) {
      return new Response(JSON.stringify({
        error: `Failed to fetch contest: ${response.status} ${response.statusText}`,
        url: contestUrl
      }), {
        status: response.status,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    const html = await response.text()

    // Extract materials with enhanced debugging
    const materials = extractContestMaterials(html, debug)

    // If debug mode, return detailed info
    if (debug) {
      return new Response(JSON.stringify({
        ...materials,
        debug: {
          contestUrl,
          htmlLength: html.length,
          foundBlogLinks: findAllBlogLinks(html),
          sampleHtml: html.substring(0, 1000) + '...'
        }
      }, null, 2), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    return new Response(JSON.stringify(materials), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })

  } catch (error) {
    return new Response(JSON.stringify({
      error: error.message,
      stack: error.stack
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })
  }
}

function findAllBlogLinks(html) {
  const links = []
  const regex = /<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>([^<]+)<\/a>/gi
  let match

  while ((match = regex.exec(html)) !== null) {
    links.push({
      href: match[1],
      text: match[2].trim()
    })
  }

  return links
}

function extractContestMaterials(html, debug = false) {
  const materials = {
    announcement: null,
    editorial: null
  }

  // Strategy 1: Look for links in sidebar with specific text
  const allBlogLinks = findAllBlogLinks(html)

  for (const link of allBlogLinks) {
    const text = link.text.toLowerCase()

    // Match announcement (English or Russian)
    if (!materials.announcement &&
        (text.includes('announcement') ||
         text.includes('анонс') ||
         text === 'announcement' ||
         text === 'анонс')) {
      materials.announcement = `https://codeforces.com${link.href}`
    }

    // Match editorial/tutorial (English or Russian)
    if (!materials.editorial &&
        (text.includes('tutorial') ||
         text.includes('разбор') ||
         text.includes('editorial') ||
         text === 'tutorial' ||
         text === 'разбор' ||
         text === 'editorial')) {
      materials.editorial = `https://codeforces.com${link.href}`
    }
  }

  // Strategy 2: Look in specific sections
  if (!materials.announcement || !materials.editorial) {
    // Try to find "Contest materials" section
    const materialsMatch = html.match(/<div[^>]*>\s*Contest materials\s*<\/div>([\s\S]{0,2000})/i)

    if (materialsMatch) {
      const section = materialsMatch[1]
      const sectionLinks = findAllBlogLinksInText(section)

      for (const link of sectionLinks) {
        const text = link.text.toLowerCase()

        if (!materials.announcement && text.includes('announcement')) {
          materials.announcement = `https://codeforces.com${link.href}`
        }

        if (!materials.editorial && text.includes('tutorial')) {
          materials.editorial = `https://codeforces.com${link.href}`
        }
      }
    }
  }

  // Strategy 3: Look for common patterns in sidebar
  if (!materials.announcement) {
    const announcementPattern = /<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>\s*Announcement\s*<\/a>/i
    const match = html.match(announcementPattern)
    if (match) {
      materials.announcement = `https://codeforces.com${match[1]}`
    }
  }

  if (!materials.editorial) {
    const tutorialPattern = /<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>\s*Tutorial\s*<\/a>/i
    const match = html.match(tutorialPattern)
    if (match) {
      materials.editorial = `https://codeforces.com${match[1]}`
    }
  }

  return materials
}

function findAllBlogLinksInText(text) {
  const links = []
  const regex = /<a[^>]+href="(\/blog\/entry\/\d+)"[^>]*>([^<]+)<\/a>/gi
  let match

  while ((match = regex.exec(text)) !== null) {
    links.push({
      href: match[1],
      text: match[2].trim()
    })
  }

  return links
}
