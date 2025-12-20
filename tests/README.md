# PS-Checklist Tests

This directory contains test utilities for the PS-Checklist application.

## Files

### 1. `difficulty-api-test.html`
Interactive test page for debugging the solved.ac API proxy.

**How to use:**
1. Open the file in a browser: `file:///path/to/tests/difficulty-api-test.html`
2. Or serve it locally: `python -m http.server 8000` and visit `http://localhost:8000/tests/difficulty-api-test.html`

**Features:**
- Test fetching problem difficulty
- Check CORS headers
- Test direct API (to confirm solved.ac is working)
- Batch test multiple problems
- Shows detailed error messages and solutions

### 2. `cloudflare-worker-fixed.js`
Fixed Cloudflare Worker code with proper CORS headers.

**How to deploy:**
1. Go to your Cloudflare Dashboard
2. Navigate to Workers & Pages
3. Click on your `solved-ac-proxy` worker
4. Replace the code with the contents of `cloudflare-worker-fixed.js`
5. Click "Save and Deploy"

**What it fixes:**
- Adds `Access-Control-Allow-Origin: *` header
- Handles OPTIONS preflight requests
- Proper error handling
- Response caching for better performance

## Current Issue

### CORS Error
```
Access-Control-Allow-Origin' header is present on the requested resource
```

**Root Cause:** The Cloudflare Worker at `https://solved-ac-proxy.arnoldpark03.workers.dev` is not returning CORS headers.

**Solution:** Deploy the fixed worker code from `cloudflare-worker-fixed.js`

## Testing Steps

1. **Before Fix - Identify the problem:**
   ```bash
   # Open the test page
   open tests/difficulty-api-test.html

   # Click "Check CORS Headers"
   # Expected: FAIL - Missing CORS headers
   ```

2. **Deploy the Fix:**
   - Copy code from `cloudflare-worker-fixed.js`
   - Update your Cloudflare Worker
   - Deploy

3. **After Fix - Verify it works:**
   ```bash
   # Refresh the test page
   # Click "Check CORS Headers"
   # Expected: PASS - CORS headers present

   # Click "Test Fetch"
   # Expected: SUCCESS - Problem data returned
   ```

## Quick Fix Commands

If you have `wrangler` CLI installed:

```bash
# Navigate to your worker directory
cd /path/to/cloudflare-worker

# Copy the fixed code
cp /path/to/ps-checklist/tests/cloudflare-worker-fixed.js ./worker.js

# Deploy
wrangler publish
```

## Expected Behavior After Fix

### Working Request:
```javascript
fetch('https://solved-ac-proxy.arnoldpark03.workers.dev?problemId=1000')
  .then(res => res.json())
  .then(data => console.log(data))
// Output: { problemId: 1000, titleKo: "A+B", level: 1, ... }
```

### Response Headers:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Content-Type: application/json
Cache-Control: public, max-age=3600
```

## Troubleshooting

### Still getting CORS errors after deploying?
1. Clear browser cache (Ctrl+Shift+R)
2. Wait 1-2 minutes for Cloudflare to propagate changes
3. Check worker logs in Cloudflare dashboard

### Worker not responding?
1. Check if worker is deployed and active in Cloudflare dashboard
2. Test worker directly: `curl https://solved-ac-proxy.arnoldpark03.workers.dev?problemId=1000`
3. Check worker logs for errors

### Different error message?
1. Open browser DevTools (F12)
2. Go to Network tab
3. Try fetching difficulty
4. Click on the failed request
5. Check Response headers and Preview tabs
6. Share the error details for further debugging

## Contact

If you need help, check:
1. Cloudflare Workers documentation: https://developers.cloudflare.com/workers/
2. solved.ac API documentation: https://solvedac.github.io/unofficial-documentation/
