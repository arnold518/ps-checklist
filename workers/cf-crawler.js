/**
 * Cloudflare Worker - Complete Codeforces Contest Data Crawler (ROBUST VERSION)
 *
 * Fetches comprehensive contest data with improved error handling
 *
 * Deploy at: https://workers.cloudflare.com
 *
 * Usage:
 *   https://your-worker.workers.dev?contestId=2181&type=contest
 *   https://your-worker.workers.dev?contestId=104869&type=gym
 *   https://your-worker.workers.dev?contestId=2181&debug=true
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
        usage: '?contestId=2181&type=contest'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    const errors = {}

    // Fetch from API
    const apiData = await fetchFromAPI(contestId, errors)

    // Fetch from HTML
    const htmlData = await fetchFromHTML(contestId, contestType, errors)

    // Merge data
    const contestData = mergeContestData(apiData, htmlData, contestId, contestType)

    if (debug) {
      return new Response(JSON.stringify({
        ...contestData,
        debug: {
          errors,
          apiProblems: apiData?.problems?.length || 0,
          htmlProblems: htmlData?.problems?.length || 0,
          contestMaterials: htmlData?.materials?.contestMaterials || [],
          materialsFound: {
            announcement: !!htmlData?.materials?.announcement,
            editorial: !!htmlData?.materials?.editorial,
            totalMaterials: htmlData?.materials?.contestMaterials?.length || 0
          },
          sources: {
            api: apiData ? 'success' : 'failed',
            html: htmlData ? 'success' : 'failed'
          }
        }
      }, null, 2), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    return new Response(JSON.stringify(contestData), {
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

async function fetchFromAPI(contestId, errors) {
  try {
    const apiUrl = `https://codeforces.com/api/contest.standings?contestId=${contestId}&from=1&count=1`
    
    const response = await fetch(apiUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; CFWorker/1.0)'
      }
    })

    if (!response.ok) {
      errors.api = `HTTP ${response.status}: ${response.statusText}`
      return null
    }

    const data = await response.json()

    if (data.status !== 'OK') {
      errors.api = `API error: ${data.comment || 'Unknown error'}`
      return null
    }

    return {
      contest: data.result.contest,
      problems: data.result.problems
    }
  } catch (error) {
    errors.api = error.message
    return null
  }
}

async function fetchFromHTML(contestId, contestType, errors) {
  try {
    const contestUrl = `https://codeforces.com/${contestType}/${contestId}`
    
    const response = await fetch(contestUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://codeforces.com/',
        'Cache-Control': 'no-cache'
      }
    })

    if (!response.ok) {
      errors.html = `HTTP ${response.status}: ${response.statusText}`
      return null
    }

    const html = await response.text()

    if (!html || html.length < 1000) {
      errors.html = 'HTML too short or empty'
      return null
    }

    const problems = extractProblemsFromHTML(html, contestType, contestId)
    const materials = extractMaterialsFromHTML(html)
    const contestName = extractContestName(html)

    return {
      problems,
      materials,
      contestName
    }
  } catch (error) {
    errors.html = error.message
    return null
  }
}

function extractContestName(html) {
  // Remove HTML comments
  const cleaned = html.replace(/<!--[\s\S]*?-->/g, '')
  
  // Try title tag
  let match = cleaned.match(/<title>([^<]+?)\s*-\s*Codeforces<\/title>/i)
  if (match) {
    return match[1].trim().replace(/\s+/g, ' ')
  }

  // Try dashboard header
  match = cleaned.match(/Dashboard\s*-\s*([^<]+?)\s*-\s*Codeforces/i)
  if (match) {
    return match[1].trim()
  }

  return null
}

function extractProblemsFromHTML(html, contestType, contestId) {
  const problems = []

  // Remove HTML comments first
  const cleaned = html.replace(/<!--[\s\S]*?-->/g, '')

  // Find problems table
  const tableMatch = cleaned.match(/<table[^>]*class="problems"[^>]*>([\s\S]*?)<\/table>/i)
  if (!tableMatch) {
    return problems
  }

  const tableHtml = tableMatch[1]

  // Split by <tr> tags
  const rows = tableHtml.split(/<\/?tr[^>]*>/i)

  for (const row of rows) {
    if (!row.trim() || !row.includes('class="id')) continue

    // Extract problem index
    const indexMatch = row.match(/\/problem\/([A-Z]\d*)["'][^>]*>\s*([A-Z]\d*)\s*<\/a>/i)
    if (!indexMatch) continue

    const index = indexMatch[2].trim()

    // Extract problem name (after removing comments)
    const nameMatch = row.match(/\/problem\/[A-Z]\d*["'][^>]*>([^<]+)<\/a>/i)
    const name = nameMatch ? nameMatch[1].trim().replace(/\s+/g, ' ') : `Problem ${index}`

    // Extract time and memory limits
    const limitsMatch = row.match(/(\d+)\s*s,\s*(\d+)\s*MB/i)
    const timeLimit = limitsMatch ? parseInt(limitsMatch[1]) : null
    const memoryLimit = limitsMatch ? parseInt(limitsMatch[2]) : null

    // Extract solved count
    const solvedMatch = row.match(/x(\d+)/i)
    const solvedCount = solvedMatch ? parseInt(solvedMatch[1]) : null

    problems.push({
      index,
      name,
      timeLimit,
      memoryLimit,
      solvedCount
    })
  }

  return problems
}

function extractMaterialsFromHTML(html) {
  const materials = {
    announcement: null,
    editorial: null,
    contestMaterials: []
  }

  // Remove comments
  const cleaned = html.replace(/<!--[\s\S]*?-->/g, '')

  // Strategy 1: Extract from "Contest materials" section
  const contestMaterialsMatch = cleaned.match(/Contest materials[\s\S]*?<ul>([\s\S]*?)<\/ul>/i)
  if (contestMaterialsMatch) {
    const materialsSection = contestMaterialsMatch[1]

    // Extract all <li> elements
    const liRegex = /<li>([\s\S]*?)<\/li>/gi
    let liMatch

    while ((liMatch = liRegex.exec(materialsSection)) !== null) {
      const liContent = liMatch[1]

      // Extract href and title from <a> tag
      const aMatch = liContent.match(/<a[^>]*href=["']([^"']+)["'][^>]*title=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/i)

      if (aMatch) {
        const href = aMatch[1]
        const title = aMatch[2]
        const innerHtml = aMatch[3]

        // Extract text content (remove nested tags like <span>)
        const text = innerHtml.replace(/<[^>]*>/g, '').trim()

        // Store material
        const material = {
          url: href.startsWith('http') ? href : `https://codeforces.com${href}`,
          title: title,
          text: text
        }
        materials.contestMaterials.push(material)

        // Identify announcement
        const titleLower = title.toLowerCase()
        const textLower = text.toLowerCase()

        if (!materials.announcement &&
            (titleLower.includes('announcement') || titleLower.includes('анонс') ||
             textLower.includes('announcement') || textLower.includes('анонс') ||
             href.includes('/blog/entry/'))) {
          materials.announcement = material.url
        }

        // Identify editorial/tutorial
        if (!materials.editorial &&
            (titleLower.includes('tutorial') || titleLower.includes('editorial') ||
             titleLower.includes('разбор') || textLower.includes('tutorial') ||
             textLower.includes('editorial') || textLower.includes('разбор'))) {
          materials.editorial = material.url
        }
      }
    }
  }

  // Strategy 2: Fallback - Find all blog entry links in entire page
  if (!materials.announcement || !materials.editorial) {
    const blogRegex = /<a[^>]*href=["']?(\/blog\/entry\/\d+)["']?[^>]*>([\s\S]*?)<\/a>/gi

    let match
    while ((match = blogRegex.exec(cleaned)) !== null) {
      const href = match[1]
      const innerHtml = match[2]
      const text = innerHtml.replace(/<[^>]*>/g, '').trim().toLowerCase()

      if (!materials.announcement && (text.includes('announcement') || text.includes('анонс'))) {
        materials.announcement = `https://codeforces.com${href}`
      }

      if (!materials.editorial && (text.includes('tutorial') || text.includes('editorial') || text.includes('разбор'))) {
        materials.editorial = `https://codeforces.com${href}`
      }

      if (materials.announcement && materials.editorial) break
    }
  }

  return materials
}

function mergeContestData(apiData, htmlData, contestId, contestType) {
  const isGym = contestType === 'gym'

  const internalContestId = `Codeforces > ${isGym ? 'Gym' : 'Contest'} > ${contestId}`

  const contestName = apiData?.contest?.name || 
                      htmlData?.contestName || 
                      `${isGym ? 'Gym' : 'Contest'} ${contestId}`

  // Merge problems
  let problems = []

  if (apiData?.problems && apiData.problems.length > 0) {
    // Use API as primary source
    problems = apiData.problems.map(apiProblem => {
      const htmlProblem = htmlData?.problems?.find(p => p.index === apiProblem.index)
      
      return {
        id: apiProblem.index,
        title: apiProblem.name,
        CF: `https://codeforces.com/${contestType}/${contestId}/problem/${apiProblem.index}`,
        timeLimit: htmlProblem?.timeLimit || null,
        memoryLimit: htmlProblem?.memoryLimit || null,
        solvedCount: htmlProblem?.solvedCount || null
      }
    })
  } else if (htmlData?.problems && htmlData.problems.length > 0) {
    // Fallback to HTML
    problems = htmlData.problems.map(htmlProblem => ({
      id: htmlProblem.index,
      title: htmlProblem.name,
      CF: `https://codeforces.com/${contestType}/${contestId}/problem/${htmlProblem.index}`,
      timeLimit: htmlProblem.timeLimit,
      memoryLimit: htmlProblem.memoryLimit,
      solvedCount: htmlProblem.solvedCount
    }))
  }

  // Build links
  const links = {
    statements: `https://codeforces.com/${contestType}/${contestId}/problems`,
    standing: `https://codeforces.com/${contestType}/${contestId}/standings`,
    CF: `https://codeforces.com/${contestType}/${contestId}`
  }

  if (htmlData?.materials?.announcement) {
    links.official = htmlData.materials.announcement
  }
  if (htmlData?.materials?.editorial) {
    links.editorials = htmlData.materials.editorial
  }

  const result = {
    id: internalContestId,
    category: ['Codeforces', isGym ? 'Gym' : 'Contest'],
    contestNum: contestId,
    name: contestName,
    problems,
    link: links,
    source: 'codeforces'
  }

  // Add all contest materials if available
  if (htmlData?.materials?.contestMaterials && htmlData.materials.contestMaterials.length > 0) {
    result.materials = htmlData.materials.contestMaterials
  }

  return result
}
