# Universal Print 404 Error - Diagnostic Report

## Error Summary

Your print job creation is **succeeding**, but document upload is **failing** with 404 `UnknownError` on multiple endpoints:

1. ❌ `/print/printers/{printerId}/jobs/{jobId}/documents/createUploadSession` → 404 UnknownError
2. ❌ `/print/printers/{printerId}/jobs/{jobId}/documents` → 404 UnknownError  
3. ❌ `/print/jobs/{jobId}/documents` (alternative endpoint) → 400 "Resource not found for the segment 'jobs'"

## Root Cause Analysis

### Issue #1: Missing or Ineffective Permissions

Your token shows **delegated permissions** (scopes), not application roles:
```
token.scp=openid PrintConnector.Read.All Printer.FullControl.All 
         Printer.Read.All PrinterShare.Read.All PrinterShare.ReadWrite.All 
         PrintJob.Create PrintJob.ReadWrite PrintJob.ReadWrite.All profile email
```

**Key findings:**
- You have `PrinterShare.ReadWrite.All` as a **delegated scope**
- This is from device code authentication (`--auth device`)
- The job creation works because `PrintJob.Create` is present
- Document upload fails despite having `PrintJob.ReadWrite.All`

**Why this matters:** In many Universal Print environments, the `/print/printers/{printerId}/jobs/{jobId}/documents` endpoint requires:
1. Either the printer to be directly accessible to your user account
2. Or the job to be created via a **printer share** rather than direct printer access

### Issue #2: Direct Printer Access vs Share-Based Access

Your error pattern suggests that:
- ✅ Job creation on printer endpoint succeeds
- ❌ Document operations on the same job fail
- ⚠️ The global `/print/jobs/{jobId}` endpoint doesn't exist in your environment

This typically indicates one of:
1. **Connector version mismatch**: Older Universal Print connectors may not support document operations on printer-based jobs
2. **Permission model mismatch**: Your tenant requires share-based access for document operations
3. **API surface limitation**: Some tenants don't expose the full print API surface

### Issue #3: Job State "uploadPending"

Your job status shows:
```json
{
  "state": "paused",
  "description": "The job is not a candidate for processing yet.",
  "isAcquiredByPrinter": false,
  "details": ["uploadPending"]
}
```

This confirms the job is waiting for a document, but the API won't accept it.

## Solution Implemented

I've updated `up_print.py` with a **3-strategy fallback approach**:

### Strategy 1: Modern Direct Upload (Original)
```
POST /print/printers/{printerId}/jobs/{jobId}/documents/createUploadSession
```
- Preferred method
- Single API call creates upload session
- Most efficient when it works

### Strategy 2: Legacy Two-Step (Original Fallback)
```
POST /print/printers/{printerId}/jobs/{jobId}/documents
POST /print/printers/{printerId}/jobs/{jobId}/documents/{docId}/createUploadSession
```
- Older API pattern
- Two-step process
- More widely supported

### Strategy 3: Share-Based Access (NEW)
```
1. GET /print/shares?$filter=printer/id eq '{printerId}'  (discover share)
2. POST /print/shares/{shareId}/jobs/{jobId}/documents     (create document)
3. POST /print/printers/{printerId}/jobs/{jobId}/documents/{docId}/createUploadSession
```
- **NEW**: Uses printer share endpoint
- May work when direct printer access doesn't
- Requires printer to be shared

### Enhanced Diagnostics

Added in debug mode:
- Share discovery and validation
- Strategy-by-strategy reporting
- Clear indication of which method worked
- Better error messages with remediation hints

## How to Test the Fix

Run with debug mode enabled:

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug \
  --auth device
```

Watch for these new debug messages:

```
[debug] discovered printer share: <share-id>
[debug] Strategy 1: POST https://graph.microsoft.com/v1.0/print/printers/.../documents/createUploadSession
[debug] Strategy 1 failed: ...
[debug] Strategy 2: POST https://graph.microsoft.com/v1.0/print/printers/.../documents
[debug] Strategy 2 failed: ...
[debug] Strategy 3: Attempting via printer share endpoint
[debug] using share ID: <share-id>
[debug] POST https://graph.microsoft.com/v1.0/print/shares/.../jobs/.../documents
[debug] Strategy 3 succeeded!
[debug] document created: <doc-id>
```

## Expected Outcomes

### If Strategy 3 Works (Most Likely)
- ✅ Document creation will succeed via share endpoint
- ✅ Upload will complete
- ✅ Job will start and print
- **Action needed**: Update your workflow to use share-based job creation going forward

### If All Strategies Fail
You'll see a comprehensive error message:
```
All strategies failed. This may indicate:
1. Missing PrinterShare.ReadWrite.All permission
2. Job was created but is not accessible for document upload
3. Printer or connector configuration issue
4. API version incompatibility

Try running with --debug for detailed diagnostics.
```

**Next steps:**
1. Check if the printer has any shares created
2. Verify connector is running and up-to-date
3. Try creating the job via share endpoint instead (see below)

## Alternative Workaround: Use Share Endpoint for Job Creation

If Strategy 3 works but you want a cleaner solution, modify your workflow to create jobs via the share endpoint from the start:

```python
# Instead of:
job = create_print_job(token, printer_id, job_name, config)

# Use:
# 1. Discover share
shares = requests.get(f"{GRAPH_BASE_URL}/print/shares?$filter=printer/id eq '{printer_id}'", ...).json()
share_id = shares['value'][0]['id']

# 2. Create job via share
job = requests.post(f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs", ...).json()

# 3. Documents will work on this job
```

## Technical Deep Dive

### Why Shares Might Work When Direct Access Doesn't

The Universal Print permission model has two access paths:

**Direct Printer Access:**
- Requires: `Printer.Read.All` + `PrintJob.ReadWrite.All`
- Use case: Admin/service accounts managing all printers
- Limitation: May not support document operations in some environments

**Share-Based Access:**
- Requires: `PrinterShare.ReadWrite.All` + `PrintJob.ReadWrite.All`
- Use case: Users accessing shared printers
- Advantage: More complete API surface in delegated scenarios

Your environment appears to require share-based access for document operations, even though direct printer access works for job creation.

### API Version Considerations

The Microsoft Graph Print API has evolved:
- **v1.0**: Conservative, stable, but may lack newer features
- **Beta**: More complete, but subject to change

Your error suggests you're hitting a limitation in the v1.0 API surface for your specific tenant/connector configuration.

## Recommended Long-Term Solution

1. **Verify share exists:**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     "https://graph.microsoft.com/v1.0/print/shares?\$filter=printer/id eq 'fb9f7465-597e-4ebf-990a-510052930107'"
   ```

2. **If no share exists, create one:**
   - Go to Azure Portal → Universal Print
   - Find your printer
   - Create a printer share
   - Grant appropriate permissions

3. **Update your workflow to use share-based job creation:**
   - More reliable across different tenant configurations
   - Better permission model for delegated access
   - Clearer access control

4. **Consider app-only authentication for production:**
   ```bash
   python up_print.py \
     --printer-id "..." \
     --file "low.pdf" \
     --auth app \
     --client-secret "$CLIENT_SECRET"
   ```
   - Application permissions (roles) instead of delegated scopes
   - More predictable behavior
   - Better for automation

## Testing Checklist

- [ ] Run with `--debug` to see which strategy works
- [ ] Check if share endpoint (Strategy 3) succeeds
- [ ] Verify printer has at least one share configured
- [ ] Test with both `--auth device` and `--auth app`
- [ ] Confirm document upload and job start succeed
- [ ] Monitor job status to completion

## Support Information

If the issue persists after these fixes, provide Microsoft Support with:
- Request IDs from debug output
- Token claims (aud, tid, appid, roles/scp)
- Printer ID and share ID (if available)
- Connector version
- Tenant region/configuration

The detailed debug output will capture all necessary diagnostic information.
