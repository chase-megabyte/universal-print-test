# Quick Fix for 404 UnknownError on Document Upload

## Your Error
```
[debug] collection createUploadSession failed: 404 code=UnknownError
[debug] create document response body: {"error":{"code":"UnknownError","message":"",...}}
[debug] alternative endpoint also failed: 400 code=BadRequest message=Resource not found for the segment 'jobs'
Error: Create document failed: 404 code=UnknownError
```

## Immediate Action Required

### Step 1: Re-run with the Updated Code

The script has been updated with a new **Strategy 3** that uses printer shares. Run:

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug \
  --auth device
```

### Step 2: Watch for New Debug Output

Look for these lines indicating Strategy 3 is being attempted:

```
[debug] discovered printer share: <share-id>
[debug] Strategy 1 failed: ...
[debug] Strategy 2 failed: ...
[debug] Strategy 3: Attempting via printer share endpoint
[debug] using share ID: <share-id>
[debug] POST https://graph.microsoft.com/v1.0/print/shares/.../jobs/.../documents
[debug] Strategy 3 succeeded!
```

### Step 3a: If Strategy 3 Succeeds ✅

**Great!** Your printer has a share configured and the workaround works. The document will upload and print successfully.

**What this means:**
- Your Universal Print environment requires share-based access for document operations
- Direct printer access works for job creation but not document upload
- This is a known limitation in some tenant/connector configurations

**No further action needed** - the script will now work automatically.

### Step 3b: If Strategy 3 Also Fails ❌

You'll see:
```
[debug] no shares found for printer
```
or
```
[debug] shares discovery failed: ...
```

**Action required:** Create a printer share in Azure Portal

1. Go to [Azure Portal](https://portal.azure.com) → Universal Print
2. Find printer `fb9f7465-597e-4ebf-990a-510052930107` (test-printer)
3. Click "Shares" → "Add share"
4. Create a share with a name like "test-printer-share"
5. Grant your user/group access to the share
6. Wait 2-3 minutes for replication
7. Re-run the script with `--debug`

## Why This Happens

Your error shows you're using **delegated permissions** (device code auth):
```
token.scp=PrinterShare.ReadWrite.All PrintJob.Create PrintJob.ReadWrite ...
```

In delegated mode, the Microsoft Graph API requires:
- Job creation can happen on direct printer endpoints
- Document upload often requires share-based endpoints
- This is by design for proper access control

The `/print/jobs/{jobId}` global endpoint doesn't exist in all tenants (your error confirms this).

## Alternative: Switch to Application Permissions

For automation/production, use app-only authentication:

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug \
  --auth app \
  --client-secret "$CLIENT_SECRET"
```

**Benefits:**
- Application roles instead of delegated scopes
- More predictable API behavior
- Better for unattended scenarios
- May work with direct printer endpoints

**Requirements:**
- `CLIENT_SECRET` environment variable set
- Application permissions in Azure AD:
  - `Printer.Read.All`
  - `PrintJob.ReadWrite.All` 
  - `PrintJob.Manage.All`
  - `PrinterShare.ReadWrite.All`
- Admin consent granted

## Verification Commands

### Check if share exists:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/shares?\$filter=printer/id eq 'fb9f7465-597e-4ebf-990a-510052930107'" \
  | jq '.value[].id'
```

### List all shares (if filter doesn't work):
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/shares" \
  | jq '.value[] | {id, displayName, printer: .printer.id}'
```

### Check printer details:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/printers/fb9f7465-597e-4ebf-990a-510052930107" \
  | jq '{id, displayName, shares: .shares}'
```

## Expected Timeline

1. **Immediate** (0 min): Re-run script with updated code
2. **If share exists**: Works immediately
3. **If creating share**: 2-5 minutes for Azure AD replication
4. **If permission changes**: 2-10 minutes for token cache refresh

## Success Indicators

When working correctly, you'll see:
```
[debug] printer ok: fb9f7465-597e-4ebf-990a-510052930107 test-printer
[debug] printer supported content types: ["application/oxps","application/pdf",...]
[debug] resolved contentType: application/pdf (source=extension)
[debug] job ok: 15
[debug] discovered printer share: <share-id>
[debug] Strategy 3 succeeded!
[debug] document created: <doc-id>
Uploading document...
Upload complete.
Starting job...
Job started.
```

## Still Not Working?

See `DIAGNOSTIC_REPORT.md` for comprehensive troubleshooting, or contact me with:
- Full debug output from latest run
- Share discovery results from curl commands above
- Your authentication mode (device vs app)
- Connector version if available
