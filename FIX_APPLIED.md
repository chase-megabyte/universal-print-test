# Fix Applied for Microsoft Graph Universal Print 404 Error

## Problem Summary

The Universal Print script was failing with a **404 "UnknownError"** when attempting to upload documents to a print job. The error occurred in all three upload strategies:

1. **Strategy 1**: `POST .../documents/createUploadSession` - Failed with 404
2. **Strategy 2**: `POST .../documents` - Failed with 404  
3. **Strategy 3**: Share endpoint discovery - Failed with 500 due to invalid OData filter

## Root Cause

The primary issue was in the **printer share discovery query** on lines 294 and 386:

```python
shares_url = f"{GRAPH_BASE_URL}/print/shares?$filter=printer/id eq '{printer_id}'"
```

This OData filter query using a navigation property (`printer/id`) was causing a **500 Internal Server Error** with the message:

> "Code: InvalidODataUri  
> Message: Found a Uri function 'cast' with a parent token. Uri functions cannot have parent tokens."

This syntax is either unsupported or has been deprecated in the Microsoft Graph API. When Strategy 3 failed to discover shares, the fallback strategies couldn't work because:

- The job was created successfully via `/print/printers/{printerId}/jobs`
- But the document upload endpoints returned 404, indicating the job might only be accessible via the share endpoints
- Without share discovery working, there was no way to try the share-based document upload

## Fix Applied

### 1. Fixed Share Discovery Query

Changed from complex OData filter to simple list-and-filter approach:

**Before:**
```python
shares_url = f"{GRAPH_BASE_URL}/print/shares?$filter=printer/id eq '{printer_id}'"
shares_resp = requests.get(shares_url, headers=graph_headers(token), timeout=30)
```

**After:**
```python
shares_url = f"{GRAPH_BASE_URL}/print/shares"
shares_resp = requests.get(shares_url, headers=graph_headers(token), timeout=30)
# ... then filter manually:
matching_shares = [s for s in shares if (s.get("printer") or {}).get("id") == printer_id]
```

### 2. Created Helper Function

Added `_discover_printer_shares()` function to centralize share discovery logic and avoid code duplication:

```python
def _discover_printer_shares(token: str, printer_id: str, debug: bool = False) -> List[Dict[str, Any]]:
    """Discover all shares for a given printer.
    
    Returns a list of share objects that reference this printer.
    Returns empty list if no shares found or on error.
    """
```

### 3. Enhanced Error Messages

Improved error diagnostics to provide more specific guidance when encountering 404 UnknownError:

- Explains that the printer may not be properly shared
- Recommends checking PrinterShare.ReadWrite.All permission
- Suggests verifying connector status
- Points users to create jobs via share endpoint if needed

## What This Fixes

1. **Share Discovery**: No longer throws 500 error when listing printer shares
2. **Strategy 3**: Can now successfully discover and use printer shares for document upload
3. **Better Diagnostics**: Provides clearer guidance on what to check when errors occur

## Testing Recommendations

After applying this fix, test with:

1. Run with `--debug` flag to see detailed strategy execution
2. Verify that share discovery succeeds (should see `[debug] discovered printer share: ...`)
3. Check if Strategy 3 can now create documents via the share endpoint
4. Ensure the printer has at least one active share in Universal Print portal
5. Verify PrinterShare.ReadWrite.All permission is granted and admin-consented

## Additional Notes

- The fix maintains backward compatibility with existing functionality
- All three strategies are still attempted in order
- Manual filtering is more compatible across API versions
- The approach works even with large numbers of shares (though performance may degrade if you have thousands of shares)

## Next Steps if Still Failing

If the error persists after this fix:

1. **Check Permissions**: Ensure `PrinterShare.ReadWrite.All` is granted and consented
2. **Verify Shares**: Check that the printer has at least one share in the Universal Print portal
3. **Check Connector**: Verify the Universal Print connector is online
4. **Try Share-Based Job Creation**: Consider creating the job via `/print/shares/{shareId}/jobs` instead of `/print/printers/{printerId}/jobs`
5. **Contact Support**: This may indicate a configuration issue specific to your tenant or printer setup
