# Cloudflare Worker Setup Guide

**Goal**: Deploy a simple serverless function to fetch Codeforces contest materials (announcement/editorial links) without CORS issues.

**Cost**: ✅ 100% FREE (100,000 requests/day on free tier)

---

## 📋 Prerequisites

- A Cloudflare account (free): https://dash.cloudflare.com/sign-up
- No credit card required
- Takes 5 minutes

---

## 🚀 Step-by-Step Deployment

### 1. Create Cloudflare Account

1. Go to https://dash.cloudflare.com/sign-up
2. Sign up with email (no credit card needed)
3. Verify your email

### 2. Create a Worker

1. Go to https://dash.cloudflare.com
2. Click **"Workers & Pages"** in the left sidebar
3. Click **"Create Application"**
4. Click **"Create Worker"**
5. Name it: `cf-contest-proxy` (or any name)
6. Click **"Deploy"**

### 3. Edit the Worker Code

1. After deployment, click **"Edit Code"**
2. **Delete all the default code**
3. **Copy the entire contents** of `cf-contest-proxy-worker-v3.js` (use v3 for most robust extraction)
4. **Paste it** into the editor
5. Click **"Save and Deploy"**

**Note**: There are 3 versions available:
- `cf-contest-proxy-worker.js` - Original simple version
- `cf-contest-proxy-worker-v2.js` - Enhanced with debugging
- `cf-contest-proxy-worker-v3.js` - Most robust with flexible HTML parsing ✅ **Recommended**

### 4. Get Your Worker URL

After deployment, you'll see a URL like:
```
https://cf-contest-proxy.YOUR-SUBDOMAIN.workers.dev
```

**Copy this URL** - you'll need it!

---

## 🔧 Update the Demo

### Option A: Update the HTML file directly

Open `tests/codeforces-api-demo.html` and find this line (~line 580):

```javascript
async function fetchContestMaterials(contestId, isGym = false) {
    const contestType = isGym ? 'gym' : 'contest';
    const contestUrl = `https://codeforces.com/${contestType}/${contestId}`;
```

**Replace the entire function** with:

```javascript
async function fetchContestMaterials(contestId, isGym = false) {
    const contestType = isGym ? 'gym' : 'contest';

    try {
        // Use Cloudflare Worker proxy
        const workerUrl = 'https://cf-contest-proxy.YOUR-SUBDOMAIN.workers.dev';
        const response = await fetch(`${workerUrl}?contestId=${contestId}&type=${contestType}`);
        const materials = await response.json();

        return materials;
    } catch (error) {
        console.warn('Could not fetch contest materials:', error);
        return { announcement: null, editorial: null };
    }
}
```

**⚠️ Important**: Replace `YOUR-SUBDOMAIN` with your actual Cloudflare Workers subdomain!

### Option B: Use the update script (I'll create this)

I can create an automated script to update the demo with your worker URL.

---

## ✅ Test It

1. **Test the Worker directly**:
   ```
   https://cf-contest-proxy.YOUR-SUBDOMAIN.workers.dev?contestId=1891&type=contest
   ```

   You should see JSON output like:
   ```json
   {
     "announcement": "https://codeforces.com/blog/entry/149276",
     "editorial": "https://codeforces.com/blog/entry/149318"
   }
   ```

2. **Test the Demo**:
   - Open `tests/codeforces-api-demo.html`
   - Load a contest (e.g., contest 1891)
   - Click the contest ID
   - You should now see **Announcement** and **Editorial** links!

---

## 🎉 Done!

Your demo will now work with:
- ✅ Statements link
- ✅ Standings link
- ✅ Codeforces link
- ✅ **Announcement link** (via Worker)
- ✅ **Editorial link** (via Worker)

---

## 💡 Alternative: Vercel Serverless Function

If you prefer Vercel (also free):

1. Create a Vercel account: https://vercel.com/signup
2. Install Vercel CLI: `npm install -g vercel`
3. Create `api/contest-materials.js`:

```javascript
export default async function handler(req, res) {
  const { contestId, type = 'contest' } = req.query;

  if (!contestId) {
    return res.status(400).json({ error: 'Missing contestId' });
  }

  const contestUrl = `https://codeforces.com/${type}/${contestId}`;
  const response = await fetch(contestUrl);
  const html = await response.text();

  // Extract materials (same logic as Cloudflare Worker)
  const materials = extractMaterials(html);

  res.json(materials);
}

function extractMaterials(html) {
  // Same extraction logic...
}
```

4. Deploy: `vercel --prod`

---

## 📊 Comparison

| Feature | Cloudflare Workers | Vercel Functions |
|---------|-------------------|------------------|
| Free tier | 100k requests/day | 100 GB-hours/month |
| Setup time | 5 minutes | 10 minutes |
| Speed | Very fast (global edge) | Fast |
| Best for | Simple API proxy | Full API routes |

**Recommendation**: Use **Cloudflare Workers** for this simple use case!

---

## 🔍 Troubleshooting

### Common Errors

**Problem**: "Fetch is not defined" error
- **Solution**: Make sure you're using the latest Worker code

**Problem**: "CORS error" still appearing
- **Solution**: Check that CORS headers are set in the Worker (they are in the provided code)

**Problem**: Worker URL not working
- **Solution**: Make sure the Worker is deployed (green status in Cloudflare dashboard)

**Problem**: `{"error":"Failed to fetch contest: 403 Forbidden"}`
- **Cause**: Codeforces blocking Cloudflare Workers due to missing browser headers
- **Solution**: Use the updated v3 worker which includes browser-like headers to bypass bot detection
- **Action**: Delete all code in the worker editor and paste the latest `cf-contest-proxy-worker-v3.js` code, then click "Save and Deploy"

**Problem**: Wrong URL format - `{"error":"Missing contestId parameter"}`
- **Cause**: Using `/` instead of `?` for query parameters
- **Wrong**: `https://your-worker.workers.dev/contestId=1891`
- **Correct**: `https://your-worker.workers.dev?contestId=1891&type=contest`

### Debugging Null Results

**Problem**: `{"announcement":null,"editorial":null}`

This means the worker successfully fetched the HTML but couldn't extract the blog links.

**Solution**: Use debug mode to inspect what the worker is actually finding:

1. Add `&debug=true` to your URL:
   ```
   https://your-worker.workers.dev?contestId=1891&type=contest&debug=true
   ```

2. The response will include:
   ```json
   {
     "announcement": null,
     "editorial": null,
     "debug": {
       "contestUrl": "https://codeforces.com/contest/1891",
       "htmlLength": 123456,
       "foundBlogLinks": [
         {"href": "/blog/entry/149276", "text": "Announcement"},
         {"href": "/blog/entry/149318", "text": "Tutorial"}
       ],
       "sidebarLinks": [...],
       "sampleHtml": "<html>..."
     }
   }
   ```

3. Check the `foundBlogLinks` array:
   - **If empty**: The contest page doesn't have announcement/editorial links in the sidebar (some contests don't have them)
   - **If populated but announcement/editorial still null**: The link text doesn't match expected patterns
   - **If links found correctly**: The extraction logic is working!

4. **If links are found but not extracted**, check the link text:
   - Look for variations like "Contest Announcement", "Editorial", etc.
   - Report the issue with the debug output

5. **Upgrade to v3**: If using v1 or v2, upgrade to `cf-contest-proxy-worker-v3.js` which has more flexible pattern matching

---

## 📝 Next Steps

After deployment:
1. Test the worker with different contest IDs
2. Update your demo HTML with the worker URL
3. Push to GitHub Pages
4. Enjoy fully functional contest material links! 🎉
