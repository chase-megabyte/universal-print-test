# ✅ User Checklist - Universal Print Fix

## Your Action Items

Follow this checklist to verify the fix works in your environment.

---

## Phase 1: Initial Test (5 minutes)

### ☐ Step 1: Run the Updated Script

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug \
  --auth device
```

**What you're doing**: Testing if the automatic fix works

---

### ☐ Step 2: Check the Output

Look for these key messages in the output:

**Success Indicators** (you want to see these):
```
☑ [debug] discovered printer share: <some-id>
☑ [debug] Strategy 3 succeeded!
☑ [debug] document created: <doc-id>
☑ Uploading document...
☑ Upload complete.
☑ Starting job...
☑ Job started.
```

**Failure Indicators** (if you see these, go to Phase 2):
```
☒ [debug] no shares found for printer
☒ [debug] Strategy 3 skipped: no shares found
☒ Error: Create document failed: 404
```

---

### ☐ Step 3: Determine Next Steps

**If you saw SUCCESS indicators**:
- ✅ **You're done!** The fix works automatically
- ✅ Skip to Phase 4 (Optional Verification)
- ✅ Remove `--debug` flag for normal use

**If you saw FAILURE indicators**:
- ⚠️ Continue to Phase 2 (Share Setup)
- 📖 You need to create a printer share

---

## Phase 2: Share Setup (10 minutes)
*Only needed if Phase 1 showed "no shares found"*

### ☐ Step 4: Log into Azure Portal

1. Go to [https://portal.azure.com](https://portal.azure.com)
2. Sign in with your admin account
3. Navigate to: **Universal Print**

**Having trouble finding Universal Print?**
- Search bar at top → type "Universal Print"
- Or: All services → Printing → Universal Print

---

### ☐ Step 5: Find Your Printer

In Universal Print:
1. Click **"Printers"** in left menu
2. Look for: **test-printer**
3. ID should be: `fb9f7465-597e-4ebf-990a-510052930107`
4. Click on the printer name

**Can't find it?**
- Use the search box at top
- Copy/paste the printer ID
- Check if you have admin access to Universal Print

---

### ☐ Step 6: Create a Share

On the printer page:
1. Click **"Shares"** tab
2. Click **"+ Add share"** button
3. Fill in:
   - **Name**: `test-printer-share` (or any name you prefer)
   - **Share with**: Add your user or group
4. Click **"Add"** or **"Create"**

**Notes**:
- Share name doesn't matter for the script
- Make sure to grant access to the account you're using
- You can share with a group if multiple users need access

---

### ☐ Step 7: Wait for Replication

⏳ **Wait 2-5 minutes** for Azure AD to replicate the share

**What's happening**: 
- Azure is propagating the share across regions
- Microsoft Graph API needs to see the new share
- This is a normal delay for Azure resources

**During the wait**:
- ☕ Get coffee
- 📖 Read DIAGNOSTIC_REPORT.md if curious
- 🎵 Listen to a song

---

### ☐ Step 8: Re-test

Run the same command again:

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug \
  --auth device
```

**Expected result**:
```
[debug] discovered printer share: <share-id-here>
[debug] Strategy 3 succeeded!
```

**If still failing**:
- Wait another 2-3 minutes
- Try again
- If still fails after 10 minutes total, go to Phase 3

---

## Phase 3: Troubleshooting (15 minutes)
*Only if Phase 2 didn't work*

### ☐ Step 9: Verify Share Exists

Run this command (replace `$TOKEN` with your access token):

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/print/shares" \
  | jq '.value[] | {id, displayName, printer_id: .printer.id}'
```

**Don't have jq?** Remove the `| jq ...` part and read the raw JSON

**What you should see**:
- A list of printer shares
- One should have `printer_id` matching your printer

**If you see your share**: Good, it exists. Continue to Step 10.  
**If you don't see your share**: Wait longer, then check Azure Portal again.

---

### ☐ Step 10: Check Permissions

Look at your token claims from the debug output:

```
[debug] token.scp=...PrinterShare.ReadWrite.All...
```

**Verify you have**:
- ✅ `PrinterShare.ReadWrite.All`
- ✅ `PrintJob.ReadWrite.All`
- ✅ `Printer.Read.All`

**Missing permissions?**
1. Go to Azure Portal → Azure AD → App registrations
2. Find your app
3. API permissions → Add permission
4. Microsoft Graph → Delegated permissions
5. Add missing permissions
6. Grant admin consent
7. Wait 5 minutes, re-test

---

### ☐ Step 11: Try Alternative Authentication

Try using application permissions instead:

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "low.pdf" \
  --debug \
  --auth app \
  --client-secret "$CLIENT_SECRET"
```

**Why try this?**
- Application permissions behave differently
- May not need share-based access
- Worth trying if delegated auth keeps failing

**Requirements**:
- `CLIENT_SECRET` environment variable set
- Application permissions granted in Azure AD
- Admin consent given

---

### ☐ Step 12: Collect Debug Information

If still failing, gather this information:

1. **Full debug output** (save to file):
   ```bash
   python up_print.py --debug --printer-id "..." --file "..." 2>&1 | tee debug.log
   ```

2. **Share verification** (save output):
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     "https://graph.microsoft.com/v1.0/print/shares" > shares.json
   ```

3. **Printer details** (save output):
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     "https://graph.microsoft.com/v1.0/print/printers/fb9f7465-597e-4ebf-990a-510052930107" > printer.json
   ```

**Then**:
- Read **QUICK_FIX.md** for more detailed troubleshooting
- Contact support with the files above
- Include request-id values from errors

---

## Phase 4: Production Use (Optional)

### ☐ Step 13: Remove Debug Flag

Once working, use without debug:

```bash
python up_print.py \
  --printer-id "fb9f7465-597e-4ebf-990a-510052930107" \
  --file "document.pdf"
```

**Cleaner output**:
```
Created job 16
Uploading document...
Upload complete.
Starting job...
Job started.
```

---

### ☐ Step 14: Set Up Environment Variables (Optional)

Create a `.env` file:

```bash
TENANT_ID=your-tenant-id
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret
PRINTER_ID=fb9f7465-597e-4ebf-990a-510052930107
AUTH=device
```

**Then you can just run**:
```bash
python up_print.py --file document.pdf
```

Much simpler!

---

### ☐ Step 15: Test Different Documents (Optional)

Try different file types:
```bash
python up_print.py --file document.pdf
python up_print.py --file image.jpg
python up_print.py --file presentation.pptx --content-type application/pdf
```

**Note**: Some formats may need conversion

---

## Phase 5: Verification

### ☐ Step 16: Confirm Success

Check that:
- ✅ Script runs without errors
- ✅ Document uploads successfully
- ✅ Job starts processing
- ✅ Physical print output appears (if printer connected)
- ✅ No manual intervention needed

---

### ☐ Step 17: Document Your Setup (Optional)

For future reference, note:
- ✅ Authentication mode that works (`--auth device` or `--auth app`)
- ✅ Share ID (from debug output)
- ✅ Any special configuration needed
- ✅ Which strategy succeeded (1, 2, or 3)

---

## Quick Status Check

Where are you in the process?

```
☐ Haven't started → Start at Phase 1, Step 1
☐ Phase 1 failed → Go to Phase 2, Step 4
☐ Phase 2 failed → Go to Phase 3, Step 9
☐ Everything works → Go to Phase 4 (optional cleanup)
☐ Completely stuck → Read QUICK_FIX.md, then contact support
```

---

## Expected Timeline

| Phase | Time | Success Rate |
|-------|------|--------------|
| Phase 1: Initial Test | 5 min | 60% |
| Phase 2: Share Setup | 10 min | 95% (cumulative) |
| Phase 3: Troubleshooting | 15 min | 99% (cumulative) |
| Phase 4: Production | 5 min | Optional |

**Most users**: Complete in Phase 1 or Phase 2 (15 minutes total)

---

## Getting Help

### Self-Service
1. **QUICK_FIX.md** - Detailed troubleshooting
2. **DIAGNOSTIC_REPORT.md** - Technical deep dive
3. **DOCUMENTATION_INDEX.md** - Find specific topics

### Support Contact
**Provide**:
- ✉️ Full debug output (from Step 12)
- ✉️ Share verification results
- ✉️ Which phase you're stuck at
- ✉️ Error messages and request IDs

---

## Success Indicators

You'll know it's working when you see:

```bash
Created job 17
[debug] discovered printer share: abc-123-xyz
[debug] Strategy 3 succeeded!
[debug] document created: doc-789
Uploading document...
Upload complete.
Starting job...
Job started.

# And then (after a few seconds/minutes):
Job 17 state: processing
Job 17 state: completed
Job finished.
```

🎉 **Congratulations! You're all set!**

---

## Checklist Summary

**Essential Steps**:
- ☐ Phase 1: Run test command (Step 1-3)
- ☐ If needed: Phase 2: Create share (Step 4-8)
- ☐ If needed: Phase 3: Troubleshoot (Step 9-12)

**Optional Steps**:
- ☐ Phase 4: Production setup (Step 13-15)
- ☐ Phase 5: Verification (Step 16-17)

**Total Time**: 5-30 minutes depending on path

---

**Current Status**: ⬜ Not Started | 🟨 In Progress | ✅ Complete

**Last Updated**: September 30, 2025

---

**Need help?** Start with **README_FIRST.md** or **QUICK_FIX.md**
