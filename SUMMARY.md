# Universal Print 404 Error - Fix Summary

## Issue Diagnosed

Your Microsoft Graph Universal Print script was encountering a **404 "UnknownError"** when trying to upload documents to print jobs. The root cause was an **invalid OData filter query** that was preventing the share discovery mechanism from working.

## Error Chain

1. **Job Creation**: ✅ Succeeded (Job ID: 21)
2. **Strategy 1** (createUploadSession on collection): ❌ 404 UnknownError
3. **Strategy 2** (create document first): ❌ 404 UnknownError  
4. **Strategy 3** (via share endpoint): ❌ Failed because share discovery threw 500 error

The share discovery failed with:
```
Code: InvalidODataUri
Message: Found a Uri function 'cast' with a parent token. 
Uri functions cannot have parent tokens.
```

This was caused by the OData filter: `$filter=printer/id eq '{printer_id}'`

## Fix Applied

### Changed the share discovery approach:

**Before** (Complex OData filter - Not supported):
```python
shares_url = f"{GRAPH_BASE_URL}/print/shares?$filter=printer/id eq '{printer_id}'"
```

**After** (Simple list + manual filter):
```python
shares_url = f"{GRAPH_BASE_URL}/print/shares"
# Then filter in Python:
matching_shares = [s for s in shares if (s.get("printer") or {}).get("id") == printer_id]
```

### Additional Improvements:

1. ✅ Created `_discover_printer_shares()` helper function
2. ✅ Updated both share discovery locations (lines 294 and 386)  
3. ✅ Enhanced error messages with specific guidance for 404 UnknownError
4. ✅ All changes maintain backward compatibility

## What Should Work Now

- Share discovery will no longer fail with 500 error
- Strategy 3 can now properly discover and use printer shares
- Document upload via share endpoint should succeed
- Better diagnostic messages guide troubleshooting

## Next Steps

### Test the fix:

```bash
python up_print.py --printer-id YOUR_PRINTER_ID --file YOUR_FILE.pdf --debug
```

### What to look for in debug output:

1. ✅ `[debug] discovered printer share: ...` - Shares are found
2. ✅ `[debug] Strategy 3 succeeded!` - Document creation works via share
3. ✅ Upload completes successfully

### If still encountering 404:

The issue may be related to:

1. **Missing Permission**: Ensure `PrinterShare.ReadWrite.All` is:
   - Added to your app registration
   - Admin-consented for your tenant
   - Actually present in the token (check token.scp in debug output)

2. **No Shares Configured**: 
   - Go to Universal Print portal
   - Verify your printer has at least one active share
   - The printer must be shared for jobs to be accessible

3. **Connector Offline**:
   - Check Universal Print connector status
   - Verify it's connected and online
   - Jobs created when connector is offline may not accept documents

4. **Timing Issue**:
   - Some printer configurations have a delay before jobs accept documents
   - May need to add a small delay between job creation and document upload

## Files Modified

- `/workspace/up_print.py` - Fixed share discovery and added helper function
- `/workspace/FIX_APPLIED.md` - Detailed technical explanation
- `/workspace/SUMMARY.md` - This file

## Questions?

If the issue persists after applying this fix, it likely indicates a configuration or permission issue specific to your tenant. Review the enhanced error messages for specific guidance on what to check next.
