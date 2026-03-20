#!/usr/bin/env python3
"""
db/download_from_drive.py

Downloads the most recent file from a Google Drive folder using a service account.
Decompresses .gz files automatically. Writes the final SQL to dump.sql in the
current working directory.

Required env vars:
    GDRIVE_SERVICE_ACCOUNT_JSON  — full contents of the service account JSON key
    GDRIVE_FOLDER_ID             — Google Drive folder ID
"""
import gzip
import io
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main():
    folder_id = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
    sa_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")

    if not folder_id or not sa_json:
        print("ERROR: GDRIVE_FOLDER_ID and GDRIVE_SERVICE_ACCOUNT_JSON must be set")
        sys.exit(1)

    sa_info = json.loads(sa_json)
    print(f"Service account: {sa_info.get('client_email')}")
    print(f"Folder ID: {folder_id!r} (len={len(folder_id)})")

    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # Verify folder exists and is accessible
    try:
        folder_meta = service.files().get(
            fileId=folder_id, fields="id, name, mimeType"
        ).execute()
        print(f"Folder name: {folder_meta.get('name')} (type: {folder_meta.get('mimeType')})")
    except Exception as e:
        print(f"ERROR: Cannot access folder: {e}")
        print("Trying list query as fallback...")
        # Try listing with supportsAllDrives in case it's a shared drive
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=5,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields="files(id, name, size, mimeType, modifiedTime)",
            ).execute()
            fallback_files = results.get("files", [])
            print(f"Fallback list found {len(fallback_files)} files")
            for ff in fallback_files:
                print(f"  - {ff['name']}")
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
        print()
        print("Make sure the folder is shared with the service account email.")
        sys.exit(1)

    # List files in the specified folder
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false"
            " and mimeType != 'application/vnd.google-apps.folder'",
        orderBy="modifiedTime desc",
        pageSize=5,
        fields="files(id, name, size, mimeType, modifiedTime)",
    ).execute()
    files = results.get("files", [])

    # If no files, check subfolders
    if not files:
        sub_results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false"
                " and mimeType = 'application/vnd.google-apps.folder'",
            pageSize=10,
            fields="files(id, name)",
        ).execute()
        for sub in sub_results.get("files", []):
            print(f"  Searching subfolder: {sub['name']}")
            sub_files = service.files().list(
                q=f"'{sub['id']}' in parents and trashed=false"
                    " and mimeType != 'application/vnd.google-apps.folder'",
                orderBy="modifiedTime desc",
                pageSize=5,
                fields="files(id, name, size, mimeType, modifiedTime)",
            ).execute()
            files = sub_files.get("files", [])
            if files:
                break

    if not files:
        print("ERROR: No files found in Drive folder")
        sys.exit(1)

    f = files[0]
    print(f"Found: {f['name']} ({int(f.get('size', 0)) // 1024:,} KB)")

    # Download into memory
    request = service.files().get_media(fileId=f["id"])
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        print(f"  {int(status.progress() * 100)}%", end="\r", flush=True)
    print()

    data = buf.getvalue()

    # Decompress if gzipped
    if f["name"].endswith(".gz"):
        print("Decompressing .gz ...")
        data = gzip.decompress(data)

    with open("dump.sql", "wb") as out:
        out.write(data)

    print(f"Written to dump.sql ({len(data) // 1024:,} KB)")


if __name__ == "__main__":
    main()
