# Issue Fixed: Job Stuck in Paused State

## Problem Identified

Your print jobs were staying in **"paused"** state with the message **"The job is not a candidate for processing yet"** because:

1. **Missing `--file` parameter**: The script was only creating an empty print job without uploading any document
2. **Missing upload logic**: The `main()` function was not calling the document upload functions
3. **Missing start logic**: The job was never being started after creation

Looking at your debug output:
```
Created job 24
Job 24 state: paused - The job is not a candidate for processing yet.
```

This shows the job was created but nothing happened after that - no document upload, no job start.

## What Was Fixed

### 1. Added `--file` Parameter
```python
parser.add_argument("--file", default=os.getenv("FILE_PATH"), help="Path to the file to print")
parser.add_argument("--content-type", default=os.getenv("CONTENT_TYPE"), help="MIME type of the document")
```

### 2. Added File Validation
```python
required_base = [
    ("--tenant-id", args.tenant_id),
    ("--client-id", args.client_id),
    ("--printer-id", args.printer_id),
    ("--file", args.file),  # Now required!
]

# Validate file exists
if not os.path.exists(args.file):
    print(f"Error: File not found: {args.file}", file=sys.stderr)
    return 2
```

### 3. Added Document Upload Logic
After creating the job, the script now:
```python
# Upload document to the job
print("Uploading document...")
document_id, upload_url = create_document_and_upload_session(
    token,
    args.printer_id,
    job_id,
    args.file,
    args.content_type,
    debug=args.debug,
    share_id=job_share_id
)

upload_file_to_upload_session(upload_url, args.file)
print("Upload complete.")
```

### 4. Added Job Start Logic
After uploading, the script now starts the job:
```python
# Start the job
print("Starting job...")
start_print_job(token, args.printer_id, job_id, share_id=job_share_id, debug=args.debug)
print("Job started.")
```

## How to Use the Fixed Script

### Basic Usage
```bash
python3 up_print.py \
  --printer-id "b7f12096-05fe-493f-b3f3-91ecc010e486" \
  --file "/path/to/your/document.pdf"
```

### With Debug Output
```bash
python3 up_print.py \
  --printer-id "b7f12096-05fe-493f-b3f3-91ecc010e486" \
  --file "/path/to/your/document.pdf" \
  --debug
```

### With Polling (Wait Until Complete)
```bash
python3 up_print.py \
  --printer-id "b7f12096-05fe-493f-b3f3-91ecc010e486" \
  --file "/path/to/your/document.pdf" \
  --poll
```

### Using Environment Variables
Create a `.env` file:
```bash
TENANT_ID=c21aecc4-c6f2-4e82-9a7a-71a91b03eb0b
CLIENT_ID=0c9a3887-2fc4-464f-891f-8515bd197bbb
CLIENT_SECRET=your_secret_here
PRINTER_ID=b7f12096-05fe-493f-b3f3-91ecc010e486
FILE_PATH=/path/to/document.pdf
```

Then run:
```bash
python3 up_print.py --poll
```

## Expected Output (After Fix)

### Before (Your Issue):
```
[debug] creating job via printer: b7f12096-05fe-493f-b3f3-91ecc010e486
Created job 24
Job 24 state: paused - The job is not a candidate for processing yet.
Job 24 state: paused - The job is not a candidate for processing yet.
```
❌ Job stuck forever in paused state

### After (Fixed):
```
[debug] creating job via printer: b7f12096-05fe-493f-b3f3-91ecc010e486
Created job 25
Uploading document...
[debug] Strategy 1 (via printer): POST https://graph.microsoft.com/v1.0/print/printers/.../jobs/25/documents/createUploadSession
[debug] Strategy 1 succeeded
Upload complete.
Starting job...
[debug] starting job via printer: b7f12096-05fe-493f-b3f3-91ecc010e486
Job started.
Job 25 state: processing - The job is being processed by the printer.
Job 25 state: completed - The job completed successfully.
```
✅ Job progresses through: paused → processing → completed

## Why Jobs Were Paused

Universal Print jobs follow this lifecycle:

1. **Job Created** → State: `paused` (waiting for document)
2. **Document Uploaded** → State: still `paused` (waiting for start command)
3. **Job Started** → State: `processing` (printer working)
4. **Print Complete** → State: `completed`

Your script was only doing step 1, so jobs stayed in `paused` forever!

## About Printer Shares

Based on your debug output showing **"total shares found: 0"**, you don't have printer shares configured. This is fine - the script will work using the printer endpoint directly. However, for better reliability, consider:

1. **Creating a printer share** in Azure Portal:
   - Go to Universal Print → Printers → [Your Printer] → Sharing
   - Click "Share printer"
   - Wait 2-3 minutes for activation

2. **Adding PrinterShare.ReadWrite.All permission**:
   - Go to App registrations → [Your App] → API permissions
   - Add "PrinterShare.ReadWrite.All" (Application permission)
   - Grant admin consent

The script will automatically use shares if available, or fall back to printer endpoint if not.

## Testing the Fix

1. **Find or create a test PDF**:
   ```bash
   echo "Test print" | gs -sDEVICE=pdfwrite -o test.pdf -
   # Or just use any existing PDF file
   ```

2. **Run the script**:
   ```bash
   python3 up_print.py \
     --printer-id "b7f12096-05fe-493f-b3f3-91ecc010e486" \
     --file "test.pdf" \
     --debug \
     --poll
   ```

3. **Expected behavior**:
   - Job created ✓
   - Document uploaded ✓
   - Job started ✓
   - Job transitions to "processing" ✓
   - Job completes ✓

## Summary

The issue was **not** about printer shares or permissions - it was simply that the script was incomplete and only created empty jobs without uploading documents or starting them. The fix adds:

- ✅ `--file` parameter (required)
- ✅ Document upload logic
- ✅ Job start logic
- ✅ File existence validation

Your print jobs will now complete successfully!
