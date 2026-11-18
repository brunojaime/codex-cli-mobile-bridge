"""Read-only discovery and bounded downloads for the new Drive layout.

No create, update or sync operation is used by this adapter.
"""
from pathlib import Path
import hashlib

from .drive import Drive, FOLDER
from .drive_auth import credentials

FIELDS = "id,name,mimeType,size,version,sha256Checksum,parents,trashed,capabilities(canDownload)"


class InboxDrive(Drive):
    def refresh(self):
        data, _ = credentials()
        response = self.http.post("https://oauth2.googleapis.com/token", data=data)
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def children(self, parent):
        if parent not in self.allowed:
            raise ValueError("outside_scope")
        result, token = [], None
        while True:
            params = {
                "q": f"'{parent}' in parents and trashed=false",
                "fields": f"nextPageToken,files({FIELDS})", "pageSize": 1000,
            }
            if token:
                params["pageToken"] = token
            data = self.request("GET", "drive/v3/files", params=params).json()
            result.extend(data.get("files", []))
            token = data.get("nextPageToken")
            if not token:
                return result

    def folders(self, parent):
        folders = [f for f in self.children(parent) if f["mimeType"] == FOLDER]
        self.allowed.update(f["id"] for f in folders)
        return folders

    def inventory(self, folder, prefix="", depth=0):
        if depth > 5:
            raise ValueError("attachments_nested_too_deep")
        result, names = {}, set()
        for meta in self.children(folder):
            name = meta["name"]
            if not name or "/" in name or "\\" in name or name in {".", ".."}:
                raise ValueError("unsafe_remote_name")
            key = prefix + name
            if name in names:
                raise ValueError("duplicate_remote_path")
            names.add(name)
            if meta["mimeType"] == FOLDER:
                if not prefix and name != "adjuntos":
                    raise ValueError("unexpected_meeting_folder")
                self.allowed.add(meta["id"])
                nested = self.inventory(meta["id"], key + "/", depth + 1)
                if result.keys() & nested.keys():
                    raise ValueError("duplicate_remote_path")
                result.update(nested)
                # Track folder names separately, including empty folders.
                result[key + "/"] = meta
            else:
                result[key] = meta
        return result

    def metadata(self, ident):
        return self.request("GET", "drive/v3/files/" + ident, params={"fields": FIELDS}).json()

    def fetch(self, meta, target, *, limit, expected_hash=None):
        if int(meta.get("size", limit + 1)) > limit:
            raise ValueError("source_limit")
        if not meta.get("capabilities", {}).get("canDownload", False):
            raise ValueError("source_not_downloadable")
        before = self.metadata(meta["id"])
        if before != meta:
            raise ValueError("source_changed")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.download(meta, target)
        if self.metadata(meta["id"]) != before:
            target.unlink(missing_ok=True)
            raise ValueError("source_changed")
        checksum = hashlib.sha256()
        with target.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                checksum.update(chunk)
        if expected_hash and checksum.hexdigest() != expected_hash:
            target.unlink(missing_ok=True)
            raise ValueError("content_hash_mismatch")
