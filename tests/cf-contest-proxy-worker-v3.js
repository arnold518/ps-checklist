/**
 * Cloudflare Worker - Codeforces Contest Materials Proxy (v3 - More Robust)
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

    // Fetch the contest page with browser-like headers to bypass bot detection
    const contestUrl = `https://codeforces.com/${contestType}/${contestId}`
    const response = await fetch(contestUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://codeforces.com/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
      }
    })

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
          sidebarLinks: extractSidebarLinks(html),
          sampleHtml: html.substring(0, 2000) + '...'
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

  // More flexible regex - handles both single and double quotes, optional spaces
  const patterns = [
    /<a[^>]*href=["']?(\/blog\/entry\/\d+)["']?[^>]*>([^<]+)<\/a>/gi,
    /<a[^>]*href=["']?(https?:\/\/codeforces\.com\/blog\/entry\/\d+)["']?[^>]*>([^<]+)<\/a>/gi
  ]

  for (const regex of patterns) {
    let match
    while ((match = regex.exec(html)) !== null) {
      const href = match[1].startsWith('http') ? match[1] : match[1]
      const text = match[2].trim()

      // Avoid duplicates
      if (!links.some(l => l.href === href)) {
        links.push({ href, text })
      }
    }
  }

  return links
}

function extractSidebarLinks(html) {
  // Try to extract the sidebar section specifically
  const sidebarMatch = html.match(/<div[^>]*id=["']?sidebar["']?[^>]*>([\s\S]*?)<\/div>\s*<\/div>/i)

  if (sidebarMatch) {
    const sidebarHtml = sidebarMatch[1]
    return findAllBlogLinks(sidebarHtml)
  }

  return []
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
    // English: "announcement", "contest announcement"
    // Russian: "анонс"
    if (!materials.announcement) {
      if (text.includes('announcement') ||
          text.includes('анонс') ||
          text === 'announcement' ||
          text === 'анонс' ||
          /^(contest\s+)?announcement$/i.test(link.text)) {
        materials.announcement = link.href.startsWith('http')
          ? link.href
          : `https://codeforces.com${link.href}`
      }
    }

    // Match editorial/tutorial (English or Russian)
    // English: "tutorial", "editorial"
    // Russian: "разбор", "editorial"
    if (!materials.editorial) {
      if (text.includes('tutorial') ||
          text.includes('разбор') ||
          text.includes('editorial') ||
          text === 'tutorial' ||
          text === 'разбор' ||
          text === 'editorial' ||
          /^(contest\s+)?(tutorial|editorial)$/i.test(link.text)) {
        materials.editorial = link.href.startsWith('http')
          ? link.href
          : `https://codeforces.com${link.href}`
      }
    }

    // Early exit if both found
    if (materials.announcement && materials.editorial) {
      break
    }
  }

  // Strategy 2: Look specifically in sidebar
  if (!materials.announcement || !materials.editorial) {
    const sidebarLinks = extractSidebarLinks(html)

    for (const link of sidebarLinks) {
      const text = link.text.toLowerCase()

      if (!materials.announcement &&
          (text.includes('announcement') || text.includes('анонс'))) {
        materials.announcement = link.href.startsWith('http')
          ? link.href
          : `https://codeforces.com${link.href}`
      }

      if (!materials.editorial &&
          (text.includes('tutorial') || text.includes('разбор') || text.includes('editorial'))) {
        materials.editorial = link.href.startsWith('http')
          ? link.href
          : `https://codeforces.com${link.href}`
      }

      if (materials.announcement && materials.editorial) {
        break
      }
    }
  }

  // Strategy 3: Look for "Contest materials" section
  if (!materials.announcement || !materials.editorial) {
    // Try different variations of the section header
    const materialsSectionPatterns = [
      /<div[^>]*>\s*Contest materials\s*<\/div>([\\s\\S]{0,3000})/i,
      /<div[^>]*>\s*Материалы соревнования\s*<\/div>([\\s\\S]{0,3000})/i,
      /<h3[^>]*>\s*Contest materials\s*<\/h3>([\\s\\S]{0,3000})/i
    ]

    for (const pattern of materialsSectionPatterns) {
      const materialsMatch = html.match(pattern)

      if (materialsMatch) {
        const section = materialsMatch[1]
        const sectionLinks = findAllBlogLinks(section)

        for (const link of sectionLinks) {
          const text = link.text.toLowerCase()

          if (!materials.announcement &&
              (text.includes('announcement') || text.includes('анонс'))) {
            materials.announcement = link.href.startsWith('http')
              ? link.href
              : `https://codeforces.com${link.href}`
          }

          if (!materials.editorial &&
              (text.includes('tutorial') || text.includes('разбор') || text.includes('editorial'))) {
            materials.editorial = link.href.startsWith('http')
              ? link.href
              : `https://codeforces.com${link.href}`
          }

          if (materials.announcement && materials.editorial) {
            break
          }
        }

        if (materials.announcement && materials.editorial) {
          break
        }
      }
    }
  }

  return materials
}
