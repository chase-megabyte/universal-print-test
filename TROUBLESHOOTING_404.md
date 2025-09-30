# Troubleshooting 404 Errors When Creating Documents

## Problem Description

You're encountering 404 errors with error code `UnknownError` when trying to:
1. Create an upload session at `/print/printers/{printerId}/jobs/{jobId}/documents/createUploadSession`
2. Create a document at `/print/printers/{printerId}/jobs/{jobId}/documents`

The job is created successfully (job ID 14 in your case), but adding documents fails.

## Root Causes

Based on Microsoft documentation and community reports, this issue typically occurs due to:

### 1. Missing `PrinterShare.ReadWrite.All` Permission (Most Common)

Even though you have `PrintJob.ReadWrite.All` and can create jobs successfully, many Universal Print environments require the `PrinterShare.ReadWrite.All` permission to add documents to print jobs. This is the most commonly cited solution in Microsoft support forums.

**Solution**: Add the `PrinterShare.ReadWrite.All` application permission to your Azure AD app registration and grant admin consent.

### 2. Unsupported Document Format

Your printer may not support the `application/pdf` content type. Some Universal Print printers only support specific formats like `application/oxps`.

**Solution**: 
- Run with `--debug` to see the printer's supported content types
- Convert your document to a supported format
- Override the content type with `--content-type application/oxps` if appropriate

### 3. API Endpoint Limitations

The `/print/printers/{printerId}/jobs/{jobId}/documents` endpoint may have restrictions or behavioral differences compared to other endpoints in the Graph API.

**Solution**: The updated script now tries alternative endpoints automatically when running in debug mode.

## Changes Made to Fix the Issue

### 1. Enhanced Debugging (`up_print.py`)

- Added `_get_printer_capabilities()` function to check supported content types
- Enhanced error messages to include full response bodies
- Added verification of jobs via both `/print/printers/{printerId}/jobs/{jobId}` and `/print/jobs/{jobId}` endpoints
- Added automatic retry using alternative endpoint `/print/jobs/{jobId}/documents` when the primary endpoint fails

### 2. Updated Documentation (`README.md`)

- Added `PrinterShare.ReadWrite.All` to the list of required permissions with clear indication it's needed for document operations
- Expanded the "Debugging 404" section with detailed explanation of common causes
- Listed all diagnostic features available with `--debug` flag

### 3. Created This Troubleshooting Guide

To help diagnose and resolve similar issues in the future.

## How to Use the Improvements

### Step 1: Add the Missing Permission

1. Go to Azure Portal → Azure Active Directory → App registrations
2. Select your application
3. Go to "API permissions"
4. Click "Add a permission" → Microsoft Graph → Application permissions
5. Search for and add `PrinterShare.ReadWrite.All`
6. Click "Grant admin consent" for your tenant
7. Wait 2-5 minutes for the permission to propagate

### Step 2: Run with Debug Mode

```bash
python up_print.py --printer-id "<your-printer-id>" --file "low.pdf" --debug
```

This will now show you:
- Token claims and scopes
- Printer capabilities and supported content types
- Job status after creation
- Alternative endpoint attempts
- Full error response bodies
- Request IDs for all API calls

### Step 3: Check the Output

Look for these diagnostic messages:

```
[debug] printer supported content types: ["application/oxps","image/jpeg",...]
[debug] WARNING: Content type 'application/pdf' may not be supported by printer
[debug] attempting alternative endpoint via /print/jobs/{jobId}/documents
[debug] alternative endpoint succeeded!
```

## Expected Result

After adding `PrinterShare.ReadWrite.All` permission:
- The document creation should succeed
- The upload session should be created successfully
- The file should upload and the job should start

## If the Problem Persists

1. Verify the permission was granted and admin consent was provided
2. Check if your printer supports the document format you're using
3. Try converting the PDF to OXPS format: many Universal Print environments prefer OXPS
4. Use the request-id and client-request-id from the error messages to open a support ticket with Microsoft
5. Check if your tenant has any restrictions on Universal Print access

## Additional Notes

The token claims in your error show delegated permissions (scopes) rather than application permissions (roles). If you're using device code authentication (`--auth device`), make sure your user account has access to the printer. For production scenarios, application permissions with client credentials flow (`--auth app`) are recommended.

Your current scopes:
```
openid PrintConnector.Read.All Printer.FullControl.All Printer.Read.All 
PrinterShare.Read.All PrinterShare.ReadWrite.All PrintJob.Create 
PrintJob.ReadWrite PrintJob.ReadWrite.All profile email
```

Note that you have `PrinterShare.ReadWrite.All` as a delegated scope, but you may need it as an application permission if using app-only authentication.
