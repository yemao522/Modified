#!/usr/bin/env python3
"""Upload file via WebDAV to OpenList."""

from webdav3.client import Client

# WebDAV configuration
WEBDAV_URL = "https://pan.airgzn.top/dav"
USERNAME = "admin"
PASSWORD = "@67chr8981CHR123"

def upload_file():
    """Upload file to OpenList via WebDAV."""
    try:
        options = {
            "webdav_hostname": WEBDAV_URL,
            "webdav_login": USERNAME,
            "webdav_password": PASSWORD,
        }
        client = Client(options)

        local_file = "7b20cc1c-38c2-43c9-9437-8d15e55a0fe9.jpeg"
        remote_path = "/video/7b20cc1c-38c2-43c9-9437-8d15e55a0fe9.jpeg"

        print(f"Uploading {local_file} to {remote_path}...")
        client.upload_sync(remote_path=remote_path, local_path=local_file)
        
        print("✓ Upload successful!")
        
        # Verify
        print("Verifying...")
        files = client.list("/video")
        if "7b20cc1c-38c2-43c9-9437-8d15e55a0fe9.jpeg" in str(files):
            print("✓ File verified on server!")
        
        return True

    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    upload_file()
