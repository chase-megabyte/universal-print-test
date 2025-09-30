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

A common issue is receiving 404 errors when trying to create documents or upload sessions after successfully creating a print job. This can happen due to:

1. **Missing `PrinterShare.ReadWrite.All` permission**: Even though the job was created successfully with `PrintJob.ReadWrite.All`, some environments require `PrinterShare.ReadWrite.All` to add documents to jobs. Add this permission in your app registration and grant admin consent.

2. **Unsupported document format**: The printer may not support the document format you're uploading (e.g., `application/pdf`). Use `--debug` to see the printer's supported content types. Some printers only support `application/oxps`. Consider converting your document to a supported format.

3. **API endpoint variations**: The script tries multiple approaches:
   - First, it attempts `/print/printers/{printerId}/jobs/{jobId}/documents/createUploadSession` (collection-level upload session)
   - If that fails (404), it falls back to creating a document first, then creating an upload session for that document
   - With `--debug`, it also attempts the alternative `/print/jobs/{jobId}/documents` endpoint

4. **Permission scope mismatch**: If using delegated permissions (device code flow with `--auth device`), ensure your account has access to the printer. Application permissions require: `Printer.Read.All`, `PrintJob.ReadWrite.All`, `PrintJob.Manage.All`, and ideally `PrinterShare.ReadWrite.All`.

**Recommended solution**: Add `PrinterShare.ReadWrite.All` to your app registration's application permissions and grant admin consent. This permission is often required for document operations on print jobs.

With `--debug`, the script now:
- Prints full URLs for all API calls
- Shows the complete error response body including the Graph error details
- Attempts to verify the job via both `/print/printers/{printerId}/jobs/{jobId}` and `/print/jobs/{jobId}` endpoints
- Shows printer capabilities and supported content types
- Attempts alternative endpoints if the primary ones fail
- Includes `request-id`/`client-request-id` for all failures to speed up support cases

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
