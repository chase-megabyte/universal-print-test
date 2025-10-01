# Universal Print Job Pause Issue - Fixed

## Problem Summary

The print job was being created successfully but immediately pausing with status `"uploadPending"`. All three strategies to attach documents were failing with **404 UnknownError** responses:
- Strategy 1 (createUploadSession on collection): 404
- Strategy 2 (create document then session): 404  
- Strategy 3 (fallback to shares): Skipped due to no shares found

The root cause: **No printer shares were discovered**, and the script was only attempting to create jobs through the printer endpoint, which is less reliable than the share endpoint in many Universal Print configurations.

## Solution Implemented

### 1. **Share-First Approach** (Primary Fix)
- Modified the workflow to discover printer shares **before** creating the job
- When shares are found, create the job via `/print/shares/{shareId}/jobs` instead of `/print/printers/{printerId}/jobs`
- This is the most reliable method according to Microsoft's Universal Print documentation

### 2. **Enhanced Share Discovery**
- Added retry logic (up to 3 attempts with 2-second delays)
- Used `$expand=printer` to get printer information directly in the shares query
- Added verbose debug logging showing total shares found and matching shares
- Improved error handling for transient failures

### 3. **Consistent Endpoint Usage**
- Once a share is selected for job creation, it's used consistently for:
  - Creating the job: `/print/shares/{shareId}/jobs`
  - Creating documents: `/print/shares/{shareId}/jobs/{jobId}/documents`
  - Creating upload sessions: `/print/shares/{shareId}/jobs/{jobId}/documents/createUploadSession`
  - Starting the job: `/print/shares/{shareId}/jobs/{jobId}/start`

### 4. **Improved Fallback Logic**
All three strategies now support both printer and share endpoints:
- **Strategy 1**: Try createUploadSession (single-call) via share first, then printer
- **Strategy 2**: Try two-step document creation via share first, then printer
- **Strategy 3**: Only runs if not already using share endpoint (avoids duplicate attempts)

### 5. **Better Error Messages**
Updated error guidance to:
- Explain that all strategies have been exhausted
- Provide step-by-step troubleshooting for each common cause
- Direct users to verify printer shares exist in Azure Portal
- Include permission requirements with all four needed permissions

## Code Changes

### Modified Functions:

1. **`_discover_printer_shares()`**
   - Added `retry_count` parameter (default 2 retries)
   - Uses `$expand=printer` for more reliable filtering
   - Added retry loop with 2-second delays
   - Enhanced debug output showing total shares and matches

2. **`create_print_job()`**
   - Added `share_id` parameter
   - Returns tuple `(job_dict, share_id_used)` to track which endpoint was used
   - Supports both printer and share endpoints
   - Added debug logging for endpoint selection

3. **`create_document_and_upload_session()`**
   - Added `share_id` parameter
   - All three strategies now check and use share endpoint when available
   - Strategy 3 only runs if not already using share endpoint
   - Consistent debug output showing which endpoint type is being used

4. **`start_print_job()`**
   - Added `share_id` and `debug` parameters
   - Supports both printer and share endpoints
   - Added debug logging for endpoint selection

5. **`main()`**
   - Discovers shares early in the workflow (before job creation)
   - Passes `share_id` through all operations for consistency
   - Shows clear debug messages about endpoint selection

### New Features:

- **Proactive share discovery**: Happens before job creation
- **Smart endpoint selection**: Prefers shares when available
- **Comprehensive retry logic**: Handles transient failures
- **Enhanced debugging**: Shows which endpoint is used for each operation

## How to Test

1. **With printer shares** (recommended):
   ```bash
   python up_print.py --file document.pdf --printer-id <guid> --debug
   ```
   Expected: Should find shares and use share endpoint throughout

2. **Without printer shares** (fallback):
   - Script will attempt printer endpoint first
   - Falls back to discovering shares if printer endpoint fails

3. **Debug output to look for**:
   ```
   [debug] total shares found: X
   [debug] found matching share: <share-id> (<name>)
   [debug] will use share endpoint for job creation: <share-id>
   [debug] creating job via share: <share-id>
   [debug] Strategy 1 (via share): POST https://...
   ```

## User Action Required

**Most likely cause of the original issue**: No printer shares exist or `PrinterShare.ReadWrite.All` permission is missing.

### To Fix:

1. **Create a printer share** (if none exist):
   - Azure Portal → Universal Print → Printers
   - Select your printer → Sharing tab
   - Create a new share
   - Wait 2-3 minutes for share to become active

2. **Add PrinterShare.ReadWrite.All permission**:
   - Azure Portal → App registrations → Your app
   - API permissions → Add a permission
   - Microsoft Graph → Application permissions
   - Find and add: `PrinterShare.ReadWrite.All`
   - Grant admin consent

3. **Verify connector is online**:
   - Azure Portal → Universal Print → Connectors
   - Check status is "Online"
   - If offline, restart the Universal Print Connector service on Windows

## Expected Behavior After Fix

With shares properly configured:
```
[debug] total shares found: 1
[debug] found matching share: abc-123 (test-printer)
[debug] will use share endpoint for job creation: abc-123
[debug] creating job via share: abc-123
Created job 22
[debug] resolved contentType: application/pdf (source=extension)
[debug] job ok: 22
[debug] job status: {"state":"paused","description":"The job is not a candidate for processing yet.","isAcquiredByPrinter":false,"details":["uploadPending"]}
[debug] Strategy 1 (via share): POST https://graph.microsoft.com/v1.0/print/shares/abc-123/jobs/22/documents/createUploadSession
[debug] Strategy 1 succeeded
Uploading document...
Upload complete.
Starting job...
[debug] starting job via share: abc-123
Job started.
```

The job should transition from "paused" → "processing" → "completed" instead of staying stuck at "paused".

## References

- [Microsoft Graph Universal Print API](https://learn.microsoft.com/en-us/graph/api/resources/print?view=graph-rest-1.0)
- [Universal Print Troubleshooting Guide](https://learn.microsoft.com/en-us/universal-print/fundamentals/universal-print-troubleshooting-support-howto)
- [Print Share Resource](https://learn.microsoft.com/en-us/graph/api/resources/printershare?view=graph-rest-1.0)
