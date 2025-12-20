#!/usr/bin/env python3
"""Test WebDAV connection to OpenList."""

from webdav3.client import Client

# WebDAV configuration
WEBDAV_URL = "https://pan.airgzn.top/dav"
USERNAME = "admin"
PASSWORD = "@67chr8981CHR123"

def test_webdav_connection():
    """Test connection to OpenList WebDAV service."""
    try:
        options = {
            "webdav_hostname": WEBDAV_URL,
            "webdav_login": USERNAME,
            "webdav_password": PASSWORD,
        }
        client = Client(options)

        print(f"Endpoint: {WEBDAV_URL}")
        print("-" * 40)

        # List root directory
        print("Listing /video directory...")
        files = client.list("/video")
        
        print(f"✓ Found {len(files)} items:")
        for f in files[:10]:
            print(f"  - {f}")
        
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")

        print("-" * 40)
        print("Connection test PASSED!")
        return True

    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    test_webdav_connection()
