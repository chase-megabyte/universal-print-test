# Document Upload Strategy Flowchart

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ START: create_document_and_upload_session()                     │
│ Inputs: token, printer_id, job_id, file_path, content_type      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Detect Content │
                    │ Type (PDF, etc)│
                    └────────┬───────┘
                             │
                      ┌──────▼────────┐
                      │  Debug Mode?  │
                      └──────┬────────┘
                             │
                   Yes ◄─────┴─────► No
                    │                 │
        ┌───────────▼──────────┐      │
        │ Verify Job Exists:   │      │
        │ • Printer endpoint   │      │
        │ • Share discovery    │      │
        └───────────┬──────────┘      │
                    │                 │
                    └────────┬────────┘
                             │
┌────────────────────────────▼──────────────────────────────┐
│                    STRATEGY 1                              │
│ POST /print/printers/{pid}/jobs/{jid}/documents/          │
│      createUploadSession                                   │
│                                                            │
│ Body: {documentName, contentType, size}                   │
└────────────────────────────┬──────────────────────────────┘
                             │
                    ┌────────▼──────────┐
                    │  Status 200/201?  │
                    └────────┬──────────┘
                             │
                   Yes ◄─────┴─────► No (404/other)
                    │                 │
        ┌───────────▼──────────┐      │
        │ Extract document_id  │      │
        │ Extract upload_url   │      │
        │ [debug] Strategy 1   │      │
        │         succeeded    │      │
        └───────────┬──────────┘      │
                    │                 │
                    │          ┌──────▼─────────────────────┐
                    │          │ [debug] Strategy 1 failed  │
                    │          │ Show error details         │
                    │          └──────┬─────────────────────┘
                    │                 │
                    │      ┌──────────▼──────────────────────────────┐
                    │      │            STRATEGY 2                   │
                    │      │ POST /print/printers/{pid}/jobs/{jid}/  │
                    │      │      documents                          │
                    │      │                                         │
                    │      │ Body: {displayName, contentType}        │
                    │      └──────────┬──────────────────────────────┘
                    │                 │
                    │        ┌────────▼──────────┐
                    │        │  Status 200/201?  │
                    │        └────────┬──────────┘
                    │                 │
                    │       Yes ◄─────┴─────► No (404/other)
                    │        │                 │
                    │        │          ┌──────▼─────────────────────┐
                    │        │          │ [debug] Strategy 2 failed  │
                    │        │          │ Show error details         │
                    │        │          └──────┬─────────────────────┘
                    │        │                 │
                    │        │      ┌──────────▼──────────────────────────────┐
                    │        │      │            STRATEGY 3 (NEW)            │
                    │        │      │ Step 1: Discover Printer Share         │
                    │        │      │ GET /print/shares?$filter=             │
                    │        │      │     printer/id eq '{pid}'              │
                    │        │      └──────────┬──────────────────────────────┘
                    │        │                 │
                    │        │        ┌────────▼──────────┐
                    │        │        │  Shares Found?    │
                    │        │        └────────┬──────────┘
                    │        │                 │
                    │        │       Yes ◄─────┴─────► No
                    │        │        │                 │
                    │        │    ┌───▼───────────┐  ┌─▼──────────────────┐
                    │        │    │ Extract       │  │ [debug] no shares  │
                    │        │    │ share_id      │  │ found for printer  │
                    │        │    │ (first share) │  │ Strategy 3 skipped │
                    │        │    └───┬───────────┘  └─┬──────────────────┘
                    │        │        │                 │
                    │        │    ┌───▼────────────────────────────────┐    │
                    │        │    │ [debug] using share ID: {sid}      │    │
                    │        │    │                                    │    │
                    │        │    │ Step 2: Create Document via Share │    │
                    │        │    │ POST /print/shares/{sid}/jobs/     │    │
                    │        │    │      {jid}/documents               │    │
                    │        │    │                                    │    │
                    │        │    │ Body: {displayName, contentType}   │    │
                    │        │    └───┬────────────────────────────────┘    │
                    │        │        │                                     │
                    │        │   ┌────▼──────────┐                          │
                    │        │   │ Status 200/   │                          │
                    │        │   │     201?      │                          │
                    │        │   └────┬──────────┘                          │
                    │        │        │                                     │
                    │        │  Yes ◄─┴─────► No                            │
                    │        │   │              │                           │
        ┌───────────┼────────┼───▼──────┐  ┌───▼────────────────┐          │
        │ Extract   │        │ [debug]  │  │ [debug] Strategy 3 │          │
        │ document_ │        │ Strategy │  │ failed             │          │
        │ id from   │        │ 3        │  └───┬────────────────┘          │
        │ response  │        │ succeeded│      │                           │
        └───────────┼────────┼───┬──────┘      │                           │
                    │        │   │             │                           │
                    │        └───┼─────────────┘                           │
                    │            │                                         │
                    └────────────┼─────────────────────────────────────────┘
                                 │
                        ┌────────▼──────────┐
                        │  document_id      │
                        │  available?       │
                        └────────┬──────────┘
                                 │
                       Yes ◄─────┴─────► No
                        │                 │
                        │          ┌──────▼────────────────────────────┐
                        │          │ ERROR: All strategies failed      │
                        │          │ Show comprehensive error message: │
                        │          │ 1. Missing permission             │
                        │          │ 2. Job not accessible             │
                        │          │ 3. Config issue                   │
                        │          │ 4. API incompatibility            │
                        │          └───────────────────────────────────┘
                        │                         │
                        │                         ▼
                        │                      [EXIT]
                        │
        ┌───────────────▼──────────────────────────────────────┐
        │ Create Upload Session for Document                   │
        │ POST /print/printers/{pid}/jobs/{jid}/documents/     │
        │      {document_id}/createUploadSession               │
        │                                                       │
        │ Body: {}                                             │
        └───────────────┬──────────────────────────────────────┘
                        │
               ┌────────▼──────────┐
               │  Status 200/201?  │
               └────────┬──────────┘
                        │
              Yes ◄─────┴─────► No
               │                 │
    ┌──────────▼────────┐    ┌──▼────────────────────┐
    │ Extract           │    │ ERROR: Create upload  │
    │ upload_url        │    │ session failed        │
    │ from response     │    └───────────────────────┘
    └──────────┬────────┘               │
               │                        ▼
               │                     [EXIT]
               │
               ▼
    ┌──────────────────────┐
    │ RETURN SUCCESS       │
    │ • document_id        │
    │ • upload_url         │
    └──────────┬───────────┘
               │
               ▼
            [EXIT]
```

## Strategy Decision Tree

```
Document Upload Needed
│
├─ Try Modern API (Strategy 1)
│  └─ Single Call: createUploadSession on collection
│     ├─ ✅ Success → Use upload_url
│     └─ ❌ 404 → Continue to Strategy 2
│
├─ Try Legacy API (Strategy 2)
│  └─ Two Calls: Create doc, then createUploadSession
│     ├─ ✅ Success → Use upload_url
│     └─ ❌ 404 → Continue to Strategy 3
│
└─ Try Share-Based (Strategy 3) ⭐ NEW
   └─ Three Steps:
      1. Discover share for printer
         ├─ No shares → Skip Strategy 3 → Error
         └─ Share found → Continue
      2. Create document via share endpoint
         ├─ ✅ Success → Continue
         └─ ❌ Failed → Error
      3. Create upload session on document
         ├─ ✅ Success → Use upload_url
         └─ ❌ Failed → Error
```

## Debug Output Mapping

```
[debug] Strategy 1: POST .../createUploadSession
├─ Success: [debug] Strategy 1 succeeded
└─ Failure: [debug] Strategy 1 failed: ...

[debug] Strategy 2: POST .../documents
├─ Success: [document_id obtained] → [debug] POST .../createUploadSession
└─ Failure: [debug] Strategy 2 failed: ...

[debug] Strategy 3: Attempting via printer share endpoint
├─ [debug] discovered printer share: {share-id}
├─ [debug] using share ID: {share-id}
├─ [debug] POST /print/shares/{share-id}/jobs/{job-id}/documents
├─ Success: [debug] Strategy 3 succeeded!
│          [debug] document created: {document-id}
└─ Failure: [debug] Strategy 3 failed: ...
```

## Key Decision Points

### Point A: Should Strategy 1 be attempted?
**Always**: It's the fastest when it works

### Point B: Should Strategy 2 be attempted?
**Only if**: Strategy 1 failed with 404 or other error

### Point C: Should Strategy 3 be attempted?
**Only if**: Strategy 2 failed with 404 or other error

### Point D: Should share discovery be done in advance?
**Only in debug mode**: For verification purposes before attempts
**During Strategy 3**: Always, to get share_id

### Point E: Which share to use if multiple exist?
**First share**: `shares[0]` from the response
**Reason**: Simplicity; most printers have one share

## Error Handling Flow

```
Any Strategy Succeeds
    ↓
✅ Continue to upload session creation
    ↓
✅ Return (document_id, upload_url)


All Strategies Fail
    ↓
❌ Build comprehensive error message
    ↓
❌ Include hints:
    • Missing PrinterShare.ReadWrite.All
    • Job not accessible
    • Config issue
    • API incompatibility
    ↓
❌ Raise RuntimeError
    ↓
❌ User sees error in stderr
```

## Performance Characteristics

| Scenario | Strategies Attempted | API Calls | Time |
|----------|---------------------|-----------|------|
| Strategy 1 works | 1 | 1 POST | ~200ms |
| Strategy 2 works | 1, 2 | 1 POST (fail) + 2 POST (success) | ~600ms |
| Strategy 3 works | 1, 2, 3 | 3 POST (fail) + 1 GET + 1 POST + 1 POST | ~1500ms |
| All fail | 1, 2, 3 | 3 POST + 1 GET + 1 POST (all fail) | ~1500ms |

**Note**: Times are approximate and depend on network latency and Microsoft Graph API response time.

## Success Path Examples

### Example 1: Modern Tenant (Strategy 1 Succeeds)
```
[debug] Strategy 1: POST .../createUploadSession
[debug] Strategy 1 succeeded
Uploading document...
Upload complete.
```
**API Calls**: 1 POST
**Duration**: < 1 second

### Example 2: Legacy Tenant (Strategy 2 Succeeds)
```
[debug] Strategy 1: POST .../createUploadSession
[debug] Strategy 1 failed: 404 code=UnknownError
[debug] Strategy 2: POST .../documents
[debug] document created: abc123
[debug] POST .../createUploadSession
Uploading document...
Upload complete.
```
**API Calls**: 2 POST (failed) + 2 POST (success)
**Duration**: 1-2 seconds

### Example 3: Share-Based Tenant (Strategy 3 Succeeds) ⭐
```
[debug] Strategy 1: POST .../createUploadSession
[debug] Strategy 1 failed: 404 code=UnknownError
[debug] Strategy 2: POST .../documents
[debug] Strategy 2 failed: 404 code=UnknownError
[debug] Strategy 3: Attempting via printer share endpoint
[debug] discovered printer share: xyz-789
[debug] using share ID: xyz-789
[debug] POST /print/shares/xyz-789/jobs/15/documents
[debug] Strategy 3 succeeded!
[debug] document created: doc-456
[debug] POST .../createUploadSession
Uploading document...
Upload complete.
```
**API Calls**: 2 POST (failed) + 1 GET + 1 POST + 1 POST (success)
**Duration**: 2-3 seconds

## Implementation Notes

### Why This Order?

1. **Strategy 1 first**: Fastest, single API call
2. **Strategy 2 second**: Well-established fallback, two calls
3. **Strategy 3 last**: Most API calls, newer workaround

### Why Not Check Shares First?

- Performance: Adds GET call even when not needed
- Most environments work with Strategy 1 or 2
- Share discovery only needed in specific scenarios
- Debug mode does preflight check for diagnostics

### Exception Handling

- Each strategy has try/except for robustness
- Failures don't crash, just move to next strategy
- Only raise error if all strategies exhausted
- Debug mode shows all attempts; production hides internals

## Troubleshooting Guide

### If Strategy 1 Fails
✅ **Normal** for some environments
→ Proceed to Strategy 2

### If Strategy 2 Fails
⚠️ **Concerning** but Strategy 3 may help
→ Proceed to Strategy 3

### If Share Discovery Fails
⚠️ **Check permissions**: Need `PrinterShare.ReadWrite.All`
⚠️ **Check printer setup**: Printer may not be shared

### If No Shares Found
❌ **Action required**: Create share in Azure Portal
📖 **See**: `QUICK_FIX.md` for instructions

### If Strategy 3 Fails
❌ **All options exhausted**
📖 **See**: Error message for next steps
📞 **Contact**: Microsoft Support with request IDs

## Future Enhancements

Possible improvements:
- [ ] Cache discovered share_id to skip discovery on subsequent calls
- [ ] Parallel strategy attempts (with race condition handling)
- [ ] User preference for which strategy to prefer
- [ ] Retry logic with exponential backoff
- [ ] Share selection logic (if multiple shares, choose best one)
- [ ] Beta API endpoint attempts as Strategy 4

## References

- Microsoft Graph API: `/print/printers`
- Microsoft Graph API: `/print/shares`
- Microsoft Graph API: `/printDocument/createUploadSession`
- Universal Print Documentation
- MSAL Python Documentation
