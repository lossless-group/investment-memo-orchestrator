# Google Docs Export Setup Guide

This guide walks you through setting up automated export from markdown to Google Docs with Hypernova branding.

---

## Quick Start (5 minutes)

### Step 1: Enable Google Drive API

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Create a new project (or select existing):
   - Click project dropdown at top
   - Click **"New Project"**
   - Name: "Investment Memo Exporter" (or your choice)
   - Click **Create**

3. Enable Google Drive API:
   - In the search bar, type "Google Drive API"
   - Click **"Google Drive API"**
   - Click **"Enable"**

### Step 2: Create OAuth 2.0 Credentials

1. In Google Cloud Console, go to **APIs & Services** → **Credentials**
2. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**

3. Configure OAuth consent screen (if first time):
   - Click **"Configure Consent Screen"**
   - Choose **"External"** (unless you have Google Workspace)
   - Click **Create**
   - Fill in:
     - **App name**: Investment Memo Exporter
     - **User support email**: your-email@example.com
     - **Developer contact**: your-email@example.com
   - Click **"Save and Continue"**
   - Skip "Scopes" (click **"Save and Continue"**)
   - Skip "Test users" (click **"Save and Continue"**)
   - Click **"Back to Dashboard"**

4. Create OAuth client ID:
   - Back in **Credentials** tab
   - Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
   - Application type: **"Desktop app"**
   - Name: "Investment Memo CLI" (or your choice)
   - Click **Create**

5. Download credentials:
   - Click the **Download** button (⬇️ icon) next to your new OAuth client
   - This downloads a JSON file like `client_secret_123456.json`

### Step 3: Place Credentials in Project

1. Rename the downloaded file to **`credentials.json`**
2. Move it to your project root:
   ```bash
   mv ~/Downloads/client_secret_*.json \
     /Users/mpstaton/code/lossless-monorepo/ai-labs/investment-memo-orchestrator/credentials.json
   ```

**Project structure should look like:**
```
investment-memo-orchestrator/
├── credentials.json          ← Your OAuth credentials (DO NOT COMMIT!)
├── export-to-google-docs.py
├── md2docx.py
└── ...
```

### Step 4: Add to .gitignore

**IMPORTANT**: Never commit credentials!

Add to `.gitignore`:
```bash
echo "credentials.json" >> .gitignore
echo "token.json" >> .gitignore
```

---

## Usage

### First Run (Authorization)

The first time you run the script, it will open a browser window for authorization:

```bash
python export-to-google-docs.py output/KearnyJackson_Memo.md
```

**What happens:**
1. Browser opens to Google OAuth consent screen
2. Click **"Continue"** (may show "app not verified" warning - click "Advanced" → "Go to app")
3. Click **"Allow"** to grant Drive access
4. Browser shows "Authentication complete" - close window
5. Script continues and uploads document

**After first run:**
- Authorization token saved to `token.json`
- Future runs won't require browser authorization
- Token auto-refreshes when expired

---

## Command Examples

### Basic Export
```bash
# Upload to root of Google Drive
python export-to-google-docs.py output/KearnyJackson_Memo.md
```

### Export to Folder
```bash
# Upload to "Investment Memos" folder (creates if doesn't exist)
python export-to-google-docs.py output/KearnyJackson_Memo.md \
  --folder "Investment Memos"
```

### Share with Link
```bash
# Anyone with link can EDIT
python export-to-google-docs.py output/Memo.md --share editor

# Anyone with link can VIEW (read-only)
python export-to-google-docs.py output/Memo.md --share viewer

# Anyone with link can COMMENT
python export-to-google-docs.py output/Memo.md --share commenter
```

### Combined Example
```bash
# Upload to folder and share as editable
python export-to-google-docs.py output/KearnyJackson_Memo.md \
  --folder "Investment Memos" \
  --share editor
```

---

## What Gets Exported?

### Branding Applied
✅ **Hypernova colors** (navy headings, cyan accents)
✅ **Heading hierarchy** (H1, H2, H3, H4)
✅ **Tables** (with navy headers)
✅ **Links** (preserved and clickable)
✅ **Lists** (bullets and numbered)
✅ **Text formatting** (bold, italic)
✅ **Citations** (footnotes preserved)

### Limitations
⚠️ **Custom fonts**: Google Docs may substitute (Calibri → Arial/Roboto)
⚠️ **Header/Footer**: Google Docs handles differently than Word
⚠️ **Exact spacing**: May vary slightly from Word
⚠️ **Images**: SVG logos may not display (convert to PNG first)

---

## Workflow with Your Colleague

### Recommended Process:

1. **You**: Generate memo from markdown
   ```bash
   python -m src.main "Company Name" --type direct
   ```

2. **You**: Export to Google Docs (shared as editor)
   ```bash
   python export-to-google-docs.py output/Company-v0.0.1/4-final-draft.md \
     --folder "Investment Memos - Drafts" \
     --share editor
   ```

3. **You**: Send link to colleague
   - Copy the "View Link" from output
   - Email or Slack to colleague

4. **Colleague**: Edits directly in Google Docs
   - Opens link in browser
   - Makes edits/comments
   - No software installation needed

5. **You** (optional): Download updated version
   - Open Google Doc
   - **File** → **Download** → **Microsoft Word (.docx)**
   - Use for final archival or further processing

---

## Troubleshooting

### "credentials.json not found"

**Problem**: Script can't find OAuth credentials

**Solution**:
1. Check file is named exactly `credentials.json` (not `client_secret_*.json`)
2. Check file is in project root (same directory as script)
3. Run: `ls credentials.json` to verify

### "Browser didn't open for authorization"

**Problem**: OAuth flow didn't start

**Solution**:
1. Look for URL in terminal output
2. Copy URL and paste in browser manually
3. Complete authorization
4. Terminal should show "✓ Credentials saved"

### "App not verified" warning

**Problem**: Google shows scary warning during authorization

**Solution**:
1. This is normal for personal projects
2. Click **"Advanced"** at bottom of warning
3. Click **"Go to [App Name] (unsafe)"**
4. Click **"Allow"** on next screen

**Why it happens**: You haven't verified your app with Google (not needed for personal use)

### "Access denied" or "Insufficient permissions"

**Problem**: Token doesn't have right permissions

**Solution**:
1. Delete `token.json`: `rm token.json`
2. Run script again - will re-authorize
3. Make sure to click "Allow" for Drive access

### Document uploaded but styling is plain

**Problem**: Branding not applied

**Solution**:
1. Check `templates/hypernova-reference.docx` exists
2. If not, run: `python create-word-reference.py`
3. Try export again

### Images don't show in Google Docs

**Problem**: SVG images (logos) don't convert

**Solution**:
1. Convert SVG to PNG before running script
2. Or replace logo links in markdown with PNG versions
3. Google Docs doesn't support SVG natively

---

## Security & Privacy

### What Access Does This Grant?

The script requests **minimal permissions**:
- ✅ Create files in Google Drive
- ✅ Manage files it creates
- ❌ Cannot access your existing files
- ❌ Cannot delete files you didn't create with it
- ❌ Cannot access Gmail, Calendar, etc.

### Credentials Storage

- `credentials.json`: OAuth client secret (identifies your app)
- `token.json`: Access token (identifies your authorization)
- Both stored **locally only** (never uploaded)
- Add both to `.gitignore` (never commit to git)

### Revoking Access

To revoke access to your Google account:
1. Go to **[Google Account Permissions](https://myaccount.google.com/permissions)**
2. Find "Investment Memo Exporter" (or your app name)
3. Click **Remove Access**
4. Delete `token.json` locally

---

## Advanced Usage

### Batch Export Multiple Memos

```bash
# Export all memos in output/ directory
for memo in output/*/4-final-draft.md; do
  python export-to-google-docs.py "$memo" \
    --folder "Investment Memos - Archive" \
    --share viewer
done
```

### Custom Credentials Path

```bash
# Use credentials from different location
python export-to-google-docs.py memo.md \
  --credentials /path/to/custom-credentials.json \
  --token /path/to/custom-token.json
```

### Keep Intermediate .docx File

```bash
# Keep the branded .docx file for reference
python export-to-google-docs.py memo.md --keep-docx
```

---

## Next Steps

Once this is working, we can:
1. Add to `README.md` as export option
2. Create batch export script for all memos
3. Integrate with brand-config.yaml (future)
4. Add to memo generation pipeline (auto-upload after creation)

---

## Resources

- [Google Drive API Documentation](https://developers.google.com/drive/api/v3/about-sdk)
- [OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Google Cloud Console](https://console.cloud.google.com/)

---

**Need Help?**

If you run into issues not covered here, check:
1. Google Cloud Console → APIs & Services → Enabled APIs (Drive API should be listed)
2. Terminal output for specific error messages
3. `token.json` file permissions (should be readable/writable)
