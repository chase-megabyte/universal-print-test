## Universal Print: Simple Print Job via Microsoft Graph (Python)

This small CLI creates a Universal Print job for a given printer, uploads a document through an upload session, starts the job, and optionally polls until completion.

### Prerequisites

- Azure AD tenant and a Universal Print-enabled subscription
- A registered application in Microsoft Entra ID (Azure AD) with a client secret
- Application permissions granted (admin consent):
  - Printer.Read.All
  - PrintJob.ReadWrite.All
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
  --poll
```

If you populated `.env`, this is sufficient:

```bash
python up_print.py --poll
```

### What the script does

1. Obtains an app-only token using MSAL (`client_credentials`) for the `https://graph.microsoft.com/.default` scope.
2. Creates a print job under `/print/printers/{printerId}/jobs`.
3. Creates a document and an upload session, then uploads the file in chunks with `Content-Range` headers.
4. Starts the job and optionally polls `/print/printers/{printerId}/jobs/{jobId}` until a terminal state.

### Notes

- Use files that your printer supports (PDF/XPS preferred). Office formats may require conversion.
- Ensure the service principal of your app has access to the tenant and Universal Print. Some tenants restrict Universal Print to specific groups.
- The script prints basic status lines; you can extend error handling and logging as needed.
