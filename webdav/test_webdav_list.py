#!/usr/bin/env python3
"""List files via WebDAV."""

from webdav3.client import Client

WEBDAV_URL = "https://pan.airgzn.top/dav"
USERNAME = "admin"
PASSWORD = "@67chr8981CHR123"

options = {
    "webdav_hostname": WEBDAV_URL,
    "webdav_login": USERNAME,
    "webdav_password": PASSWORD,
}
client = Client(options)

print("Listing /video ...")
for f in client.list("/video"):
    print(f"  {f}")
