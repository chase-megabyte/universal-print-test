# Testing Checklist for Universal Print Fix

## Pre-Flight Checks

Before testing, verify the following prerequisites:

### 1. Azure App Registration Permissions ✓

Ensure your app registration has these permissions:

**Application Permissions (for `--auth app`):**
- [ ] `Printer.Read.All`
- [ ] `PrintJob.ReadWrite.All` 
- [ ] `PrintJob.Manage.All`
- [ ] `PrinterShare.ReadWrite.All` ⚠️ **CRITICAL - Often missing**

**Delegated Permissions (for `--auth device`):**
- [ ] `Printer.Read.All`
- [ ] `PrintJob.ReadWrite.All`
- [ ] `PrinterShare.ReadWrite.All` ⚠️ **CRITICAL - Often missing**
- [ ] `offline_access` (for token caching)

**IMPORTANT**: After adding permissions, you MUST:
1. Click "Grant admin consent" in the Azure portal
2. Wait a few minutes for propagation
3. Acquire a new token (delete cache if using device auth)

### 2. Universal Print Configuration ✓

- [ ] Printer is registered in Universal Print portal
- [ ] Printer has at least one **active share**
- [ ] Universal Print connector is **online and connected**
- [ ] Test file exists and is in a supported format (PDF recommended)

### 3. Environment Variables ✓

Check your `.env` file or environment variables:

```bash
TENANT_ID=your-tenant-id
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret  # Only for --auth app
PRINTER_ID=your-printer-id
FILE_PATH=path/to/test.pdf
```

## Test Procedure

### Test 1: Basic Smoke Test with Debug

```bash
python3 up_print.py \
  --printer-id "YOUR_PRINTER_ID" \
  --file "test.pdf" \
  --debug
```

**Expected Output:**
```
[debug] token.aud=...
[debug] printer ok: YOUR_PRINTER_ID printer-name
[debug] printer supported content types: ["application/pdf", ...]
[debug] printer defaults: {...}
[debug] job configuration: {...}
Created job 123
[debug] resolved contentType: application/pdf (source=extension)
[debug] job ok: 123
[debug] job status: {...}
[debug] discovered printer share: SHARE_ID  ← KEY: Should see this now
[debug] job accessible via share endpoint   ← KEY: Should see this now
[debug] Strategy 1: POST .../documents/createUploadSession
[debug] Strategy 1 failed: ...                (may still fail, that's OK)
[debug] Strategy 2: POST .../documents
[debug] body={"displayName":"test.pdf",...}
[debug] Strategy 2 failed: ...                (may still fail, that's OK)
[debug] Strategy 3: Attempting via printer share endpoint
[debug] using share ID: SHARE_ID            ← KEY: Should see this now
[debug] POST .../print/shares/SHARE_ID/jobs/123/documents
[debug] Strategy 3 succeeded!                ← KEY: This should work now
[debug] document created: DOC_ID
Uploading document...
Upload complete.
Starting job...
Job started.
```

### Test 2: Verify Share Discovery Works

Run this to confirm shares are discoverable:

```bash
# If you have curl and jq installed:
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/shares" | jq '.value[] | {id, displayName, printer: .printer.id}'
```

Or use the script's debug output to check for share discovery messages.

### Test 3: Test with Different File Types

```bash
# PDF (most reliable)
python3 up_print.py --printer-id "..." --file "test.pdf" --debug

# JPEG (if supported)
python3 up_print.py --printer-id "..." --file "test.jpg" --debug

# With explicit content type override
python3 up_print.py --printer-id "..." --file "test.pdf" \
  --content-type "application/pdf" --debug
```

### Test 4: Test with Polling

```bash
python3 up_print.py \
  --printer-id "YOUR_PRINTER_ID" \
  --file "test.pdf" \
  --poll \
  --debug
```

This will wait for the job to complete and show status updates.

## Expected Results

### ✅ Success Indicators

1. **Share Discovery Works**: 
   - See `[debug] discovered printer share: ...`
   - No 500 error about "InvalidODataUri"

2. **Strategy 3 Succeeds**:
   - See `[debug] Strategy 3 succeeded!`
   - Document gets created via share endpoint

3. **Upload Completes**:
   - See "Upload complete."
   - No errors during chunked upload

4. **Job Starts**:
   - See "Job started."
   - Job ID accessible via GET request

### ❌ Failure Indicators and Fixes

#### If share discovery still fails:

**Symptom**: `[debug] shares discovery failed: ...`

**Fix**:
- Check PrinterShare.ReadWrite.All permission
- Verify permission is admin-consented
- Check token claims: should see PrinterShare.ReadWrite.All in scope

#### If "no shares found":

**Symptom**: `[debug] no shares found for printer`

**Fix**:
- Go to Universal Print portal
- Create a share for your printer
- Make sure share is active/enabled

#### If all strategies still fail with 404:

**Symptom**: All 3 strategies return 404

**Possible Causes**:
1. Connector is offline → Check connector status in portal
2. Timing issue → Add delay between job creation and document upload
3. Printer misconfigured → Re-register printer
4. Scope mismatch → Job created with one endpoint, accessed with another

## Troubleshooting Commands

### Check token claims:
```bash
# The script already does this with --debug
# Look for: [debug] token.scp=... or [debug] token.roles=...
```

### Verify printer exists:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/printers/YOUR_PRINTER_ID"
```

### List all shares:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/shares"
```

### Check job status:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/printers/PRINTER_ID/jobs/JOB_ID"
```

## Success Criteria

The fix is confirmed working when:

- [x] Share discovery completes without 500 error
- [x] At least one strategy successfully creates a document
- [x] Document uploads without errors
- [x] Job starts successfully
- [x] Job appears in Universal Print portal
- [x] Printer eventually prints the document (if connector is online)

## Contact Points

If issues persist after confirming all prerequisites:

1. Review enhanced error messages in the script output
2. Check `/workspace/FIX_APPLIED.md` for technical details
3. Review `/workspace/SUMMARY.md` for overview
4. Consider opening a support ticket with Microsoft if the issue appears to be on their side

## Additional Notes

- The fix doesn't change any API calls to the printer endpoints
- It only fixes how shares are discovered
- All three strategies are still attempted in order
- The script is now more resilient to API changes
