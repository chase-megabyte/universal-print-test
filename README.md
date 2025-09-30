## Universal Print: Simple Print Job via Microsoft Graph (Python)

This small CLI creates a Universal Print job for a given printer, uploads a document through an upload session, starts the job, and optionally polls until completion.

### Prerequisites

- Azure AD tenant and a Universal Print-enabled subscription
- A registered application in Microsoft Entra ID (Azure AD) with a client secret
- Application permissions granted (admin consent):
  - Printer.Read.All
  - PrintJob.ReadWrite.All
  - PrintJob.Manage.All
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

- The script uses only printer endpoints. With `--debug`, it prints full URLs.
- If the collection upload session endpoint is unsupported or returns an error, the script falls back to creating a document, then creates an upload session for that document, all under `/print/printers/{printerId}/jobs/{jobId}`.
- All Graph failures include `request-id`/`client-request-id` and error codes/messages in the debug output to speed up support cases.

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
