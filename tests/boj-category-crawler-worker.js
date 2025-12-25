/**
 * Cloudflare Worker - BOJ (Baekjoon Online Judge) Category Crawler
 *
 * Fetches contest data from BOJ category pages
 *
 * Deploy at: https://workers.cloudflare.com
 *
 * Usage:
 *   https://your-worker.workers.dev?categoryUrl=https://www.acmicpc.net/category/1056
 *   https://your-worker.workers.dev?categoryId=1056
 *   https://your-worker.workers.dev?categoryId=1056&tableIdx=0,1,2
 *   https://your-worker.workers.dev?categoryId=1056&keywords=Day,Final
 *   https://your-worker.workers.dev?categoryId=1056&debug=true
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
    let categoryUrl = url.searchParams.get('categoryUrl')
    const categoryId = url.searchParams.get('categoryId')
    const tableIdxParam = url.searchParams.get('tableIdx')
    const keywordsParam = url.searchParams.get('keywords')
    const debug = url.searchParams.get('debug') === 'true'

    // Build category URL from ID if provided
    if (!categoryUrl && categoryId) {
      categoryUrl = `https://www.acmicpc.net/category/${categoryId}`
    }

    if (!categoryUrl) {
      return new Response(JSON.stringify({
        error: 'Missing categoryUrl or categoryId parameter',
        usage: '?categoryUrl=https://www.acmicpc.net/category/1056 or ?categoryId=1056'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    // Parse optional parameters
    const tableIdx = tableIdxParam ? tableIdxParam.split(',').map(i => parseInt(i.trim())) : []
    const keywords = keywordsParam ? keywordsParam.split(',').map(k => k.trim()) : []

    const errors = {}

    // Englify URL (switch to English language)
    categoryUrl = englifyUrl(categoryUrl)

    // Fetch HTML
    const html = await fetchBOJPage(categoryUrl, errors)
    if (!html) {
      return new Response(JSON.stringify({
        error: 'Failed to fetch BOJ page',
        details: errors.fetch
      }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    // Parse data
    const contestName = extractContestName(html)
    const tableIndices = keywords.length > 0 ? extractTablesByKeywords(html, keywords, tableIdx) : tableIdx
    const problems = extractProblems(html, tableIndices)
    const pdfLinks = extractPDFLinks(html, categoryUrl)

    // Extract category ID from URL
    const categoryIdMatch = categoryUrl.match(/\/category\/(?:detail\/)?(\d+)/)
    const extractedId = categoryIdMatch ? categoryIdMatch[1] : 'unknown'

    // Build contest data
    const contestData = buildContestData(
      extractedId,
      contestName,
      problems,
      pdfLinks,
      categoryUrl
    )

    if (debug) {
      return new Response(JSON.stringify({
        ...contestData,
        debug: {
          errors,
          categoryUrl,
          tableIndices,
          problemCount: problems.length,
          pdfCount: pdfLinks.length,
          requestedTableIdx: tableIdx,
          requestedKeywords: keywords
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

/**
 * Convert BOJ URL to English version
 */
function englifyUrl(url) {
  if (url.startsWith('https://www.acmicpc.net/')) {
    return url.replace('https://www.acmicpc.net/', 'https://www.acmicpc.net/lang?lang=1&next=/')
  }
  return url
}

/**
 * Fetch BOJ page with proper headers
 */
async function fetchBOJPage(url, errors) {
  try {
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      }
    })

    if (!response.ok) {
      errors.fetch = `HTTP ${response.status}: ${response.statusText}`
      return null
    }

    const contentType = response.headers.get('Content-Type') || ''
    if (!contentType.includes('text/html')) {
      errors.fetch = `Unexpected content type: ${contentType}`
      return null
    }

    return await response.text()
  } catch (error) {
    errors.fetch = error.message
    return null
  }
}

/**
 * Extract contest name from h1.pull-left
 */
function extractContestName(html) {
  const match = html.match(/<h1[^>]*class="[^"]*pull-left[^"]*"[^>]*>([^<]+)<\/h1>/i)
  if (match) {
    return match[1].trim().replace(/\s+/g, ' ')
  }
  return null
}

/**
 * Extract table indices by keywords in headlines
 */
function extractTablesByKeywords(html, keywords, existingIndices) {
  if (!keywords || keywords.length === 0) {
    return existingIndices
  }

  const headlineRegex = /<div[^>]*class="[^"]*headline[^"]*"[^>]*>([^<]+)<\/div>/gi
  const selectedIndices = []
  let match
  let index = 0

  while ((match = headlineRegex.exec(html)) !== null) {
    const headlineText = match[1].trim()
    if (keywords.some(keyword => headlineText.includes(keyword))) {
      selectedIndices.push(index)
    }
    index++
  }

  // If existingIndices is provided, return intersection
  if (existingIndices && existingIndices.length > 0) {
    return selectedIndices.filter(idx => existingIndices.includes(idx))
  }

  return selectedIndices
}

/**
 * Extract problems from tables
 */
function extractProblems(html, tableIndices) {
  const problems = []

  // Find all problem tables
  const tableRegex = /<table[^>]*class="[^"]*table table-striped table-bordered clickable-table[^"]*"[^>]*>([\s\S]*?)<\/table>/gi
  const tables = []
  let tableMatch

  while ((tableMatch = tableRegex.exec(html)) !== null) {
    tables.push(tableMatch[1])
  }

  if (tables.length === 0) {
    return problems
  }

  // Determine which tables to parse
  const indicesToParse = tableIndices.length > 0 ? tableIndices : tables.map((_, i) => i)

  indicesToParse.forEach(tidx => {
    if (tidx >= tables.length) return

    const tableHtml = tables[tidx]
    const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi
    let rowMatch
    let isFirstRow = true

    while ((rowMatch = rowRegex.exec(tableHtml)) !== null) {
      // Skip header row
      if (isFirstRow) {
        isFirstRow = false
        continue
      }

      const rowHtml = rowMatch[1]
      const cellRegex = /<td[^>]*>([\s\S]*?)<\/td>/gi
      const cells = []
      let cellMatch

      while ((cellMatch = cellRegex.exec(rowHtml)) !== null) {
        cells.push(cellMatch[1])
      }

      // BOJ tables have 7 columns: number, letter, title, tags, solved, submitted, rate
      if (cells.length !== 7) continue

      // Extract problem number
      const numberMatch = cells[0].match(/>([^<]+)</i)
      const number = numberMatch ? numberMatch[1].trim() : ''

      // Extract letter
      const letterMatch = cells[1].match(/>([^<]+)</i)
      const rawLetter = letterMatch ? letterMatch[1].trim() : ''
      const letter = (tableIndices.length === 1 ? '' : `${tidx + 1}.`) + rawLetter

      // Extract title and link
      const titleMatch = cells[2].match(/<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/i)
      const title = titleMatch ? titleMatch[2].trim() : ''
      const link = titleMatch ? `https://www.acmicpc.net${titleMatch[1]}` : ''

      // Extract tags
      const tags = []
      const tagRegex = /<span[^>]*class="[^"]*problem-label[^"]*"[^>]*>([^<]+)<\/span>/gi
      let tagMatch
      while ((tagMatch = tagRegex.exec(cells[3])) !== null) {
        tags.push(tagMatch[1].trim())
      }

      const problem = {
        number,
        letter,
        title,
        link,
        tags: tags.join(', ')
      }

      // Check for existing problem with same letter (merge if found)
      const existingProblem = problems.find(p => p.letter === letter)
      if (existingProblem) {
        // Convert to arrays if not already
        if (!Array.isArray(existingProblem.number)) {
          existingProblem.number = [existingProblem.number]
        }
        if (!Array.isArray(existingProblem.link)) {
          existingProblem.link = [existingProblem.link]
        }

        existingProblem.number.push(number)
        existingProblem.link.push(link)

        // Update title to longest common prefix
        existingProblem.title = longestCommonPrefix(existingProblem.title, title).trim()

        // Merge tags
        const allTags = new Set([
          ...existingProblem.tags.split(', ').filter(t => t),
          ...tags
        ])
        existingProblem.tags = Array.from(allTags).sort().join(', ')
      } else {
        problems.push(problem)
      }
    }
  })

  return problems
}

/**
 * Find longest common prefix of two strings
 */
function longestCommonPrefix(str1, str2) {
  let i = 0
  while (i < str1.length && i < str2.length && str1[i] === str2[i]) {
    i++
  }
  return str1.substring(0, i)
}

/**
 * Extract PDF links from page
 */
function extractPDFLinks(html, baseUrl) {
  const pdfLinks = []
  const pdfRegex = /<a[^>]*href="([^"]+\.pdf)"[^>]*>([^<]*)<\/a>/gi
  let match

  while ((match = pdfRegex.exec(html)) !== null) {
    const href = match[1]
    const text = match[2].trim()

    // Build full URL
    let fullUrl = href
    if (!href.startsWith('http')) {
      if (href.startsWith('/')) {
        fullUrl = `https://www.acmicpc.net${href}`
      } else {
        fullUrl = new URL(href, baseUrl).href
      }
    }

    // Extract filename
    const filename = href.split('/').pop()

    pdfLinks.push({
      url: fullUrl,
      title: text || filename,
      text: text || filename,
      filename: 'boj-' + filename.replace(/\s+/g, '-')
    })
  }

  return pdfLinks
}

/**
 * Build contest data object
 */
function buildContestData(categoryId, contestName, problems, pdfLinks, categoryUrl) {
  const internalId = `BOJ > Category > ${categoryId}`

  // Transform problems to standard format
  const transformedProblems = problems.map(problem => {
    const problemData = {
      id: problem.letter,
      title: problem.title,
      BOJ: Array.isArray(problem.link) ? problem.link : [problem.link],
      number: problem.number
    }

    if (problem.tags) {
      problemData.tags = problem.tags
    }

    return problemData
  })

  // Build links
  const links = {
    category: categoryUrl
  }

  // Try to identify statements PDF
  const statementsPdf = pdfLinks.find(pdf =>
    pdf.text.toLowerCase().includes('statement') ||
    pdf.text.toLowerCase().includes('problem') ||
    pdf.filename.toLowerCase().includes('statement') ||
    pdf.filename.toLowerCase().includes('problem')
  )

  if (statementsPdf) {
    links.statements = statementsPdf.url
  }

  // Try to identify editorial PDF
  const editorialPdf = pdfLinks.find(pdf =>
    pdf.text.toLowerCase().includes('editorial') ||
    pdf.text.toLowerCase().includes('solution') ||
    pdf.text.toLowerCase().includes('tutorial') ||
    pdf.filename.toLowerCase().includes('editorial') ||
    pdf.filename.toLowerCase().includes('solution') ||
    pdf.filename.toLowerCase().includes('tutorial')
  )

  if (editorialPdf) {
    links.editorials = editorialPdf.url
  }

  const result = {
    id: internalId,
    category: ['BOJ', 'Category'],
    categoryId: categoryId,
    name: contestName || `BOJ Category ${categoryId}`,
    problems: transformedProblems,
    link: links,
    source: 'boj'
  }

  // Add materials if there are PDFs
  if (pdfLinks.length > 0) {
    result.materials = pdfLinks
  }

  return result
}
