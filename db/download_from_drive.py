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
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")
    sa_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")

    if not folder_id or not sa_json:
        print("ERROR: GDRIVE_FOLDER_ID and GDRIVE_SERVICE_ACCOUNT_JSON must be set")
        sys.exit(1)

    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json), scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # Find the most recently modified file in the folder
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        orderBy="modifiedTime desc",
        pageSize=1,
        fields="files(id, name, size)",
    ).execute()

    files = results.get("files", [])
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
