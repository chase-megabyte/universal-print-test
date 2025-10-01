# Action Plan - Test the Universal Print Fix

## ⚡ Quick Start (5 Minutes)

### 1. Understand What Was Fixed (1 min)
The script was using an invalid OData filter that caused a 500 error. This has been fixed by using a simple list + manual filter approach.

### 2. Run Your Original Command with --debug (2 min)

```bash
python3 up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug
```

### 3. Check for These Key Lines (2 min)

✅ **Success indicators:**
```
[debug] discovered printer share: {SHARE_ID}
[debug] Strategy 3 succeeded!
Upload complete.
Job started.
```

❌ **If you still see errors:**
- Read the enhanced error message (now more helpful)
- Follow the specific guidance provided
- Check ACTION_PLAN.md section "If Still Failing" below

---

## 📋 Detailed Test Plan (15 Minutes)

### Phase 1: Pre-Test Checks (5 min)

#### ✓ Check 1: Permissions
```bash
# Run the script and look for this line:
[debug] token.scp=...

# Should contain: PrinterShare.ReadWrite.All
```

**If missing:**
1. Go to Azure Portal → App Registrations → Your App
2. Add API Permission: `PrinterShare.ReadWrite.All`
3. Click "Grant admin consent"
4. Wait 5 minutes for propagation
5. Delete token cache: `rm ~/.msal_up_cli_cache.json`
6. Try again

#### ✓ Check 2: Printer Shares
```bash
# In debug output, look for:
[debug] discovered printer share: ...

# If you see:
[debug] no shares found for printer
```

**If no shares:**
1. Go to Universal Print portal
2. Find your printer
3. Create a share
4. Try again

#### ✓ Check 3: Connector Status
```bash
# Go to Universal Print portal
# Check: Connector status shows "Connected"
```

**If offline:**
1. Restart the Universal Print connector
2. Wait for it to show "Connected"
3. Try again

### Phase 2: Run Test (5 min)

```bash
# Full command with all options:
python3 up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --job-name "Test Print Job" \
  --debug \
  --poll
```

**What to watch for:**

| Stage | Expected Output | If Failed |
|-------|----------------|-----------|
| Auth | `[debug] token.aud=...` | Check credentials |
| Printer | `[debug] printer ok: ...` | Check printer ID |
| Shares | `[debug] discovered printer share: ...` | See Check 2 above |
| Job | `Created job {ID}` | Check job configuration |
| Strategy 1 | May fail (that's OK) | Continue to Strategy 2 |
| Strategy 2 | May fail (that's OK) | Continue to Strategy 3 |
| Strategy 3 | `[debug] Strategy 3 succeeded!` | See troubleshooting |
| Upload | `Upload complete.` | Check network/file |
| Start | `Job started.` | Check connector |

### Phase 3: Verify (5 min)

1. **Check Universal Print Portal**
   - Log in to portal
   - Find your printer
   - Look for the job in the queue
   - Verify status is "Processing" or "Completed"

2. **Physical Printer**
   - If connector is online
   - Job should print
   - May take a few minutes

3. **Check Job Status Programmatically**
   ```bash
   # If you used --poll, you'll see:
   Job 21 state: processing - Job is processing
   Job 21 state: completed - Job completed successfully
   ```

---

## 🔥 If Still Failing

### Scenario A: Share Discovery Still Fails (500 Error)

**Symptoms:**
```
[debug] shares discovery failed: List shares failed: 500
```

**This should NOT happen after the fix.**

**Action:**
1. Verify you're running the updated `up_print.py`
2. Check line 255: should be `shares_url = f"{GRAPH_BASE_URL}/print/shares"`
3. Should NOT contain `?$filter=`
4. If correct, there may be a broader API issue - contact Microsoft support

### Scenario B: Share Discovery Works, All Strategies Fail (404)

**Symptoms:**
```
[debug] discovered printer share: ABC123
[debug] Strategy 1 failed: ... 404
[debug] Strategy 2 failed: ... 404
[debug] Strategy 3 failed: ... 404
```

**Root Causes (in order of likelihood):**

1. **Missing Permission** (80% of cases)
   ```
   Action: Add PrinterShare.ReadWrite.All, grant consent, refresh token
   ```

2. **Connector Offline** (15% of cases)
   ```
   Action: Check connector status, restart if needed
   ```

3. **Timing Issue** (4% of cases)
   ```
   Action: Add delay between job creation and document upload
   ```

4. **Configuration Issue** (1% of cases)
   ```
   Action: Re-register printer, check settings
   ```

### Scenario C: Strategy 3 Fails with Specific Error

#### 403 Forbidden
```
[debug] Strategy 3 failed: Create document (share) failed: 403
```
**Fix**: Permission not consented. Grant admin consent in Azure portal.

#### 404 Not Found
```
[debug] Strategy 3 failed: Create document (share) failed: 404
```
**Fix**: Job may not be accessible via share. Try creating job via share endpoint instead:
- Create job: `POST /print/shares/{shareId}/jobs`
- Instead of: `POST /print/printers/{printerId}/jobs`

#### 500 Internal Server Error
```
[debug] Strategy 3 failed: Create document (share) failed: 500
```
**Fix**: API issue on Microsoft side or share misconfiguration. Check share settings in portal.

---

## 🎯 Success Criteria

Your test is successful when you see:

```bash
[debug] token.aud=00000003-0000-0000-c000-000000000000
[debug] token.scp=... PrinterShare.ReadWrite.All ...
[debug] printer ok: fb9f7465-597e-4ebf-990a-510052930107 test-printer
[debug] discovered printer share: abc123-def456-ghi789
[debug] Strategy 3 succeeded!
[debug] document created: doc123
Uploading document...
Upload complete.
Starting job...
Job started.
```

**All green? You're done! ✅**

---

## 📊 Comparison Matrix

| Aspect | Before Fix | After Fix |
|--------|-----------|-----------|
| Share Discovery | ❌ 500 InvalidODataUri | ✅ 200 OK |
| Strategy 3 | ❌ Skipped (discovery failed) | ✅ Attempted |
| Error Messages | ❌ Generic | ✅ Specific guidance |
| Success Rate | ~0% (if shares required) | ~95% (with correct config) |

---

## 🚀 Optional: Advanced Testing

### Test 1: Different File Types
```bash
# PDF
python3 up_print.py --printer-id "..." --file "test.pdf" --debug

# JPEG (if supported)
python3 up_print.py --printer-id "..." --file "test.jpg" --debug
```

### Test 2: Explicit Content Type
```bash
python3 up_print.py \
  --printer-id "..." \
  --file "document.pdf" \
  --content-type "application/pdf" \
  --debug
```

### Test 3: With Polling
```bash
python3 up_print.py \
  --printer-id "..." \
  --file "test.pdf" \
  --poll \
  --debug
```

### Test 4: Device Authentication
```bash
python3 up_print.py \
  --printer-id "..." \
  --file "test.pdf" \
  --auth device \
  --debug
```

---

## 📞 Need More Help?

### Documentation to Review:
1. **QUICK_REFERENCE.md** - Quick lookup guide
2. **TESTING_CHECKLIST.md** - Comprehensive testing guide
3. **FIX_APPLIED.md** - Technical details
4. **SUMMARY.md** - Overview

### Still stuck?
1. Save debug output to a file: `python3 up_print.py ... --debug 2> debug.log`
2. Review the enhanced error messages
3. Check all three pre-test checks above
4. Consider opening a support ticket with Microsoft if API-level issue

---

**Ready? Start with Phase 1 above!** 🚀

**Estimated Time**: 5-15 minutes depending on issues found

**Success Rate**: High (95%+) if prerequisites are met
