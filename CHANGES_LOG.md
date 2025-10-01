# Code Changes Log

## Overview
Fixed Microsoft Graph Universal Print 404 error caused by invalid OData filter in share discovery query.

## Files Modified

### `/workspace/up_print.py`

#### Change 1: Added Helper Function (Lines 248-272)
**Purpose**: Centralize share discovery logic and avoid code duplication

**Code Added**:
```python
def _discover_printer_shares(token: str, printer_id: str, debug: bool = False) -> List[Dict[str, Any]]:
    """Discover all shares for a given printer.
    
    Returns a list of share objects that reference this printer.
    Returns empty list if no shares found or on error.
    """
    try:
        shares_url = f"{GRAPH_BASE_URL}/print/shares"
        shares_resp = requests.get(shares_url, headers=graph_headers(token), timeout=30)
        
        if shares_resp.status_code != 200:
            if debug:
                print(f"[debug] shares discovery failed: {_build_graph_error_message('List shares', shares_resp)}", file=sys.stderr)
            return []
        
        shares_data = shares_resp.json() or {}
        shares = shares_data.get("value") or []
        
        # Filter shares manually to find ones matching this printer
        matching_shares = [s for s in shares if (s.get("printer") or {}).get("id") == printer_id]
        return matching_shares
    except Exception as e:  # noqa: BLE001
        if debug:
            print(f"[debug] exception discovering shares: {e}", file=sys.stderr)
        return []
```

#### Change 2: Updated `create_print_job()` Signature (Line 275)
**Purpose**: Pass debug flag through for better diagnostics

**Before**:
```python
def create_print_job(token: str, printer_id: str, job_name: str, job_configuration: Optional[Dict[str, Any]] = None) -> Dict:
```

**After**:
```python
def create_print_job(token: str, printer_id: str, job_name: str, job_configuration: Optional[Dict[str, Any]] = None, debug: bool = False) -> Dict:
```

#### Change 3: Fixed Share Discovery in Debug Section (Lines 318-334)
**Purpose**: Use new helper function instead of inline OData filter

**Before**:
```python
# Also try to access via the shares endpoint as alternative
try:
    # Try to discover shares for this printer
    shares_url = f"{GRAPH_BASE_URL}/print/shares?$filter=printer/id eq '{printer_id}'"
    shares_resp = requests.get(shares_url, headers=graph_headers(token), timeout=30)
    if shares_resp.status_code == 200:
        shares_data = shares_resp.json() or {}
        shares = shares_data.get("value") or []
        if shares:
            share_id = shares[0].get("id")
            print(f"[debug] discovered printer share: {share_id}", file=sys.stderr)
            # ... rest of code
```

**After**:
```python
# Also try to access via the shares endpoint as alternative
try:
    matching_shares = _discover_printer_shares(token, printer_id, debug=debug)
    if matching_shares:
        share_id = matching_shares[0].get("id")
        print(f"[debug] discovered printer share: {share_id}", file=sys.stderr)
        # ... rest of code (unchanged)
```

#### Change 4: Fixed Share Discovery in Strategy 3 (Lines 400-432)
**Purpose**: Use new helper function in the main upload strategy

**Before**:
```python
# Strategy 3: Try to use printer share endpoint
try:
    if debug:
        print(f"[debug] Strategy 3: Attempting via printer share endpoint", file=sys.stderr)
    
    # First, discover the share ID for this printer
    shares_url = f"{GRAPH_BASE_URL}/print/shares?$filter=printer/id eq '{printer_id}'"
    shares_resp = requests.get(shares_url, headers=graph_headers(token), timeout=30)
    
    if shares_resp.status_code == 200:
        shares_data = shares_resp.json() or {}
        shares = shares_data.get("value") or []
        
        if shares:
            share_id = shares[0].get("id")
            # ... rest of code
```

**After**:
```python
# Strategy 3: Try to use printer share endpoint
try:
    if debug:
        print(f"[debug] Strategy 3: Attempting via printer share endpoint", file=sys.stderr)
    
    # Discover the share ID for this printer
    matching_shares = _discover_printer_shares(token, printer_id, debug=debug)
    
    if matching_shares:
        share_id = matching_shares[0].get("id")
        # ... rest of code (unchanged)
```

#### Change 5: Enhanced Error Messages (Lines 434-462)
**Purpose**: Provide more specific guidance for 404 UnknownError cases

**Before**:
```python
# Check if any strategy for document creation worked
if doc_resp.status_code not in (200, 201):
    err_msg = _build_graph_error_message("Create document", doc_resp)
    raise RuntimeError(f"{err_msg}\n\nAll strategies failed. This may indicate:\n"
                     "1. Missing PrinterShare.ReadWrite.All permission\n"
                     "2. Job was created but is not accessible for document upload\n"
                     "3. Printer or connector configuration issue\n"
                     "4. API version incompatibility\n\n"
                     "Try running with --debug for detailed diagnostics.")
```

**After**:
```python
# Check if any strategy for document creation worked
if doc_resp.status_code not in (200, 201):
    err_msg = _build_graph_error_message("Create document", doc_resp)
    
    # Extract error details for better diagnostics
    err_details = _extract_graph_error(doc_resp)
    error_code = err_details.get("error_code")
    
    # Provide more specific guidance based on the error
    if error_code == "UnknownError" and doc_resp.status_code == 404:
        guidance = (
            "\n\nThe job was created but documents cannot be attached (404 UnknownError).\n"
            "This typically indicates one of the following:\n\n"
            "1. The printer is not properly shared or the share is not accessible\n"
            "   → Check that PrinterShare.ReadWrite.All permission is granted and consented\n"
            "   → Verify the printer has at least one active share in the Universal Print portal\n\n"
            "2. The job endpoint may require access via the share API instead\n"
            "   → Try creating the job via /print/shares/{shareId}/jobs instead\n\n"
            "3. The Universal Print connector may be offline or misconfigured\n"
            "   → Verify the connector is online in the Universal Print portal\n\n"
            "4. There may be a timing issue where the job is not immediately available\n"
            "   → This is a known issue with some printer configurations\n\n"
            "Try running with --debug for detailed diagnostics."
        )
    else:
        guidance = (
            "\n\nAll strategies failed. This may indicate:\n"
            "1. Missing PrinterShare.ReadWrite.All permission\n"
            "2. Job was created but is not accessible for document upload\n"
            "3. Printer or connector configuration issue\n"
            "4. API version incompatibility\n\n"
            "Try running with --debug for detailed diagnostics."
        )
    
    raise RuntimeError(f"{err_msg}{guidance}")
```

#### Change 6: Updated Function Call in main() (Line 710)
**Purpose**: Pass debug flag to create_print_job function

**Before**:
```python
job = create_print_job(token, args.printer_id, args.job_name, job_configuration=job_configuration or None)
```

**After**:
```python
job = create_print_job(token, args.printer_id, args.job_name, job_configuration=job_configuration or None, debug=args.debug)
```

## Files Created

### `/workspace/FIX_APPLIED.md`
Detailed technical explanation of the issue and fix.

### `/workspace/SUMMARY.md`
User-friendly summary of the issue and resolution.

### `/workspace/TESTING_CHECKLIST.md`
Comprehensive testing guide with expected results.

### `/workspace/CHANGES_LOG.md`
This file - detailed code changes documentation.

## Impact Analysis

### Backward Compatibility: ✅ Maintained
- No breaking changes to function signatures (only added optional parameter)
- All existing functionality preserved
- Graceful fallbacks for all error cases

### Performance Impact: ✅ Minimal
- Share discovery now fetches all shares then filters locally
- For most tenants (< 100 shares), impact is negligible
- Only runs once per print job

### Risk Assessment: ✅ Low
- Changes are isolated to share discovery logic
- Does not modify core printing functionality
- Maintains all three upload strategies
- Enhanced error handling reduces debugging time

## Testing Status

- [x] Code compiles without syntax errors
- [x] No linter errors
- [x] Backward compatible with existing usage
- [ ] Requires manual testing with actual Universal Print environment

## Rollback Plan

If issues arise, revert by:
1. Remove `_discover_printer_shares()` function
2. Restore original inline share discovery code with OData filter
3. Revert error message enhancements

However, this would restore the original 500 error, so forward-fixing is recommended instead.
