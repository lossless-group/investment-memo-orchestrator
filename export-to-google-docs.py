#!/usr/bin/env python3
"""
Export Markdown to Google Docs with Hypernova Branding

Converts markdown memos to branded Word format, then uploads to Google Docs
for collaborative editing. Returns a shareable link.

Setup:
    1. Enable Google Drive API in Google Cloud Console
    2. Download OAuth credentials as 'credentials.json'
    3. Place credentials.json in project root
    4. Run script - will prompt for authorization on first run

Usage:
    # Export single memo
    python export-to-google-docs.py output/KearnyJackson_Memo.md

    # Export with custom folder
    python export-to-google-docs.py output/Memo.md --folder "Investment Memos"

    # Set as editable by anyone with link
    python export-to-google-docs.py output/Memo.md --share editor

    # Set as view-only
    python export-to-google-docs.py output/Memo.md --share viewer
"""

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError:
    print("Error: Google API libraries not installed.")
    print("Please install with: uv pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# Try to import our md2docx converter
try:
    from pathlib import Path
    import subprocess
except ImportError:
    print("Error: Required libraries not available")
    sys.exit(1)


# Scopes required for Google Drive access
SCOPES = ['https://www.googleapis.com/auth/drive.file']


def get_google_credentials(credentials_path: Path = None, token_path: Path = None) -> Credentials:
    """
    Get Google Drive API credentials using OAuth2.

    Args:
        credentials_path: Path to credentials.json from Google Cloud Console
        token_path: Path to store the access token

    Returns:
        Credentials object for Google Drive API
    """
    if credentials_path is None:
        credentials_path = Path('credentials.json')

    if token_path is None:
        token_path = Path('token.json')

    creds = None

    # Check if we have a saved token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing access token...")
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                print(f"Error: Credentials file not found: {credentials_path}")
                print("\nPlease follow setup instructions:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a new project or select existing")
                print("3. Enable Google Drive API")
                print("4. Create OAuth 2.0 credentials (Desktop app)")
                print("5. Download as 'credentials.json' and place in project root")
                sys.exit(1)

            print("No valid credentials found. Starting authorization flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for future runs
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        print(f"✓ Credentials saved to {token_path}")

    return creds


def convert_to_branded_docx(markdown_path: Path, output_dir: Path = None) -> Path:
    """
    Convert markdown to branded Word document using our reference template.

    Args:
        markdown_path: Path to input markdown file
        output_dir: Directory for output (uses temp dir if None)

    Returns:
        Path to created .docx file
    """
    if output_dir is None:
        output_dir = Path(tempfile.gettempdir())

    docx_path = output_dir / markdown_path.with_suffix('.docx').name

    # Get reference document path
    reference_doc = Path(__file__).parent / 'templates' / 'hypernova-reference.docx'

    if not reference_doc.exists():
        print(f"Warning: Reference document not found: {reference_doc}")
        print("Creating reference document...")
        import subprocess
        subprocess.run(['python', 'create-word-reference.py'], check=True)

    # Convert using md2docx.py
    cmd = [
        sys.executable,
        str(Path(__file__).parent / 'md2docx.py'),
        str(markdown_path),
        '--reference-doc', str(reference_doc),
        '-o', str(docx_path)
    ]

    print(f"Converting {markdown_path.name} to branded Word document...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error converting to Word: {result.stderr}")
        sys.exit(1)

    if not docx_path.exists():
        print(f"Error: Conversion failed, output file not created")
        sys.exit(1)

    print(f"✓ Created branded .docx: {docx_path}")
    return docx_path


def upload_to_google_docs(
    docx_path: Path,
    creds: Credentials,
    folder_id: Optional[str] = None,
    share_permission: Optional[str] = None
) -> dict:
    """
    Upload Word document to Google Drive and convert to Google Docs format.

    Args:
        docx_path: Path to .docx file to upload
        creds: Google API credentials
        folder_id: Optional Google Drive folder ID
        share_permission: 'viewer', 'commenter', or 'editor' for link sharing

    Returns:
        Dict with 'id', 'name', and 'webViewLink' of created document
    """
    try:
        service = build('drive', 'v3', credentials=creds)

        # Metadata for the file
        file_metadata = {
            'name': docx_path.stem,  # Remove .docx extension
            'mimeType': 'application/vnd.google-apps.document'  # Convert to Google Docs
        }

        if folder_id:
            file_metadata['parents'] = [folder_id]

        # Upload file
        media = MediaFileUpload(
            str(docx_path),
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            resumable=True
        )

        print(f"Uploading to Google Docs...")
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()

        print(f"✓ Uploaded: {file.get('name')}")

        # Set sharing permissions if requested
        if share_permission:
            permission = {
                'type': 'anyone',
                'role': share_permission
            }
            service.permissions().create(
                fileId=file.get('id'),
                body=permission
            ).execute()
            print(f"✓ Shared as '{share_permission}' with anyone who has the link")

        return file

    except HttpError as error:
        print(f"Error uploading to Google Docs: {error}")
        sys.exit(1)


def find_or_create_folder(service, folder_name: str, parent_id: Optional[str] = None) -> str:
    """
    Find or create a Google Drive folder.

    Args:
        service: Google Drive API service instance
        folder_name: Name of folder to find/create
        parent_id: Optional parent folder ID

    Returns:
        Folder ID
    """
    # Search for existing folder
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)'
    ).execute()

    items = results.get('files', [])

    if items:
        print(f"✓ Found existing folder: {folder_name}")
        return items[0]['id']

    # Create folder if not found
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }

    if parent_id:
        file_metadata['parents'] = [parent_id]

    folder = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()

    print(f"✓ Created folder: {folder_name}")
    return folder.get('id')


def main():
    parser = argparse.ArgumentParser(
        description='Export markdown memos to Google Docs with Hypernova branding',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s output/Memo.md
  %(prog)s output/Memo.md --folder "Investment Memos"
  %(prog)s output/Memo.md --share editor
  %(prog)s output/Memo.md --folder "Memos" --share viewer
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        help='Input markdown file to export'
    )

    parser.add_argument(
        '--folder',
        type=str,
        help='Google Drive folder name (will be created if it doesn\'t exist)'
    )

    parser.add_argument(
        '--share',
        choices=['viewer', 'commenter', 'editor'],
        help='Share with anyone who has the link (viewer/commenter/editor)'
    )

    parser.add_argument(
        '--credentials',
        type=Path,
        default=Path('credentials.json'),
        help='Path to Google OAuth credentials file (default: credentials.json)'
    )

    parser.add_argument(
        '--token',
        type=Path,
        default=Path('token.json'),
        help='Path to store access token (default: token.json)'
    )

    parser.add_argument(
        '--keep-docx',
        action='store_true',
        help='Keep the intermediate .docx file'
    )

    args = parser.parse_args()

    # Validate input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    if not args.input.suffix.lower() in ['.md', '.markdown']:
        print(f"Error: Input must be a markdown file: {args.input}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Exporting to Google Docs: {args.input.name}")
    print(f"{'='*60}\n")

    # Step 1: Get Google credentials
    print("Step 1: Authenticating with Google...")
    creds = get_google_credentials(args.credentials, args.token)

    # Step 2: Convert markdown to branded .docx
    print("\nStep 2: Converting to branded Word document...")
    temp_dir = Path(tempfile.gettempdir())
    docx_path = convert_to_branded_docx(args.input, temp_dir)

    # Step 3: Find/create folder if specified
    folder_id = None
    if args.folder:
        print(f"\nStep 3: Preparing Google Drive folder '{args.folder}'...")
        service = build('drive', 'v3', credentials=creds)
        folder_id = find_or_create_folder(service, args.folder)
    else:
        print("\nStep 3: Skipping folder creation (uploading to root)")

    # Step 4: Upload to Google Docs
    print("\nStep 4: Uploading to Google Docs...")
    doc = upload_to_google_docs(docx_path, creds, folder_id, args.share)

    # Step 5: Clean up temp file (unless --keep-docx)
    if not args.keep_docx:
        docx_path.unlink()
        print(f"✓ Cleaned up temporary file")
    else:
        print(f"✓ Kept .docx file: {docx_path}")

    # Print results
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"\nDocument Name: {doc.get('name')}")
    print(f"Document ID:   {doc.get('id')}")
    print(f"View Link:     {doc.get('webViewLink')}")

    if args.share:
        print(f"\n🔗 Anyone with the link can {args.share} this document")
    else:
        print(f"\n🔒 Document is private (only you can access)")
        print(f"   To share: Right-click in Google Drive → Share")

    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
