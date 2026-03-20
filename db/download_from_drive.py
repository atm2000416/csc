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

    # Debug: check what the service account can see
    print(f"Folder ID: {folder_id}")

    # 1. Try listing files in the specified folder
    print("Listing contents of folder...")
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        pageSize=20,
        fields="files(id, name, size, mimeType, modifiedTime)",
    ).execute()
    items = results.get("files", [])
    print(f"  Found {len(items)} items in folder:")
    for item in items:
        print(f"    {item['name']}  ({item['mimeType']})  modified={item.get('modifiedTime','?')}")

    # 2. If empty, try listing ALL files visible to the service account
    if not items:
        print("\nFolder appears empty. Listing ALL files visible to service account...")
        all_results = service.files().list(
            pageSize=20,
            fields="files(id, name, mimeType, parents, modifiedTime)",
            orderBy="modifiedTime desc",
        ).execute()
        all_files = all_results.get("files", [])
        print(f"  Service account can see {len(all_files)} files total:")
        for af in all_files:
            print(f"    {af['name']}  parents={af.get('parents',[])}  ({af['mimeType']})")

        if not all_files:
            print("\n  Service account cannot see ANY files — likely a sharing/permission issue.")
        print()
        print("ERROR: No files found in Drive folder")
        sys.exit(1)

    # Pick the most recent non-folder file
    files = [f for f in items if f["mimeType"] != "application/vnd.google-apps.folder"]
    if not files:
        # Only subfolders — recurse
        for item in items:
            if item["mimeType"] == "application/vnd.google-apps.folder":
                print(f"\n  Searching subfolder: {item['name']} ({item['id']})")
                sub = service.files().list(
                    q=f"'{item['id']}' in parents and trashed=false",
                    orderBy="modifiedTime desc",
                    pageSize=5,
                    fields="files(id, name, size, mimeType)",
                ).execute()
                files = [f for f in sub.get("files", []) if f["mimeType"] != "application/vnd.google-apps.folder"]
                if files:
                    break
    if not files:
        print("ERROR: No downloadable files found")
        sys.exit(1)

    files.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)

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
