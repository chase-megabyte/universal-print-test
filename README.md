## Universal Print: Simple Print Job via Microsoft Graph (Python)

This small CLI creates a Universal Print job for a given printer, uploads a document through an upload session, starts the job, and optionally polls until completion.

### Prerequisites

- Azure AD tenant and a Universal Print-enabled subscription
- A registered application in Microsoft Entra ID (Azure AD) with a client secret
- Application permissions granted (admin consent):
  - **Printer.Read.All** (required)
  - **PrintJob.ReadWrite.All** (required)
  - **PrintJob.Manage.All** (required)
  - **PrinterShare.ReadWrite.All** (strongly recommended - often needed to add documents to print jobs)
  - Files.ReadWrite.All is NOT needed for Universal Print upload sessions
- A target Universal Print `printerId` and a printable file (PDF/XPS are recommended)

### Setup

1) Clone or open this project and create your environment file:

```bash
cp .env.example .env
```

Fill `.env` with your `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, and optionally default `PRINTER_ID` and `FILE_PATH`.

2) Install dependencies (Python 3.9+ recommended):

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Run

You can pass args or rely on `.env` values.

```bash
python up_print.py \
  --printer-id "<printer-guid>" \
  --file "/absolute/path/to/document.pdf" \
  --job-name "My Graph UP Job" \
  --debug \
  --poll
```

If you populated `.env`, this is sufficient:

```bash
python up_print.py --poll
```

#### Debugging 403 errors

- Use `--debug` to print token claims (audience, tenant, roles) and validate the printer with a preflight GET.
- Required Graph Application permissions (admin consent): `Printer.Read.All`, `PrintJob.ReadWrite.All`, `PrintJob.Manage.All`.
- After granting consent, wait a couple minutes and retry.
  

#### Debugging 404 on createUploadSession / create document

A common issue is receiving 404 errors when trying to create documents or upload sessions after successfully creating a print job. The script has been **significantly improved** to handle this automatically.

**What's been improved:**

1. **Share-first approach**: The script now discovers printer shares **before** creating the job and uses the share endpoint by default when available. This is the most reliable method.

2. **Enhanced share discovery**: Improved share discovery with retry logic and `$expand=printer` for better reliability.

3. **Multiple fallback strategies**: If one approach fails, the script automatically tries alternatives:
   - **Strategy 1**: Create upload session directly (modern single-call API) via share or printer endpoint
   - **Strategy 2**: Create document first, then upload session (legacy two-step) via share or printer endpoint
   - **Strategy 3**: Discover shares as fallback and retry via share endpoint if not already used

4. **Consistent endpoint usage**: Once a share is used to create the job, it's used consistently for all operations (create document, upload session, start job).

**Common causes of 404 errors:**

1. **Missing `PrinterShare.ReadWrite.All` permission**: Even though jobs can be created with `PrintJob.ReadWrite.All`, many environments require `PrinterShare.ReadWrite.All` to attach documents. **Solution**: Add this permission in your app registration and grant admin consent.

2. **Printer not shared**: The printer must have at least one active share in the Universal Print portal. **Solution**: Create a share in Azure Portal → Universal Print → Printers → [Your Printer] → Sharing.

3. **Universal Print connector offline**: The connector on the Windows machine must be online. **Solution**: Verify connector status in the portal and check Windows Event Logs.

4. **Timing issues**: Some configurations have a delay before jobs accept documents. **Solution**: The script now includes retry logic; if issues persist, wait 30-60 seconds between job creation attempts.

**Recommended setup:**
```
Required permissions:
- Printer.Read.All (required)
- PrintJob.ReadWrite.All (required)
- PrintJob.Manage.All (required)
- PrinterShare.ReadWrite.All (strongly recommended - enables share-based access)
```

**Debugging with `--debug` flag:**

With `--debug`, the script provides comprehensive diagnostics:
- Share discovery results (total shares found, matching shares with IDs)
- Which endpoint is being used (share vs printer) for each operation
- Strategy-by-strategy attempts with full URLs
- Complete error response bodies with request IDs
- Printer capabilities and supported content types
- Success/failure indication for each strategy

**Example debug output:**
```
[debug] total shares found: 3
[debug] found matching share: abc-123 (My Printer Share)
[debug] will use share endpoint for job creation: abc-123
[debug] creating job via share: abc-123
Created job 22
[debug] Strategy 1 (via share): POST .../shares/abc-123/jobs/22/documents/createUploadSession
[debug] Strategy 1 succeeded
```

### What the script does

1. Obtains an app-only or delegated token using MSAL.
2. Creates a print job under `/print/printers/{printerId}/jobs`.
3. Fetches the printer's defaults and includes a job `configuration` to avoid 400 "Missing configuration" from some connectors.
4. Creates an upload session on the documents collection via `/print/printers/{printerId}/jobs/{jobId}/documents/createUploadSession` (preferred), then uploads the file in chunks with `Content-Range` headers. If unsupported, falls back to creating a document first and then creating an upload session for that document.
5. Starts the job and optionally polls `/print/printers/{printerId}/jobs/{jobId}` reading `printJob.status.state` until a terminal state.

### Notes

- Use files that your printer supports (PDF/XPS preferred). Office formats may require conversion.
- Ensure the service principal of your app has access to the tenant and Universal Print. Some tenants restrict Universal Print to specific groups.
- The script prints basic status lines; you can extend error handling and logging as needed.

#### Content type detection

- The script now auto-detects the document `contentType` using extension and magic-byte sniffing for common formats (PDF, JPEG, PNG, GIF, TIFF, PS, XPS/OXPS).
- You can still override detection with `--content-type` (e.g., `--content-type application/pdf`).
- Use `--debug` to see the resolved `contentType` and its detection source.

#### About 400 "Missing configuration"

Some Universal Print connectors require specific job configuration to be present when creating a job. The script now fetches `print/printers/{printerId}?$select=defaults` and maps known defaults (e.g., `copies`, `colorMode`, `duplexMode`, `mediaSize`) into the job creation payload. This eliminates the 400 error in most cases. You can inspect what is sent using `--debug`.
