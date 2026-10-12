"""Consistent backups and safe restore of the private data folder (PLAN.md §22).

A backup is one zip in `backups/`: the database copied with SQLite's own backup API,
every file in the studio's asset folders, and a manifest with each file's SHA-256.
While all writes are briefly paused, the database is copied and every asset file is
hard-linked (or, where links are not possible, copied) into a snapshot folder. The zip
is then written from that snapshot, so files deleted afterwards are still in it and
the backup matches its database exactly. Nothing else has to wait for the zip.

A backup can also be protected with a password (Phase 6D, `backend.backup_crypto`): the
same zip is then encrypted into a `.csbackup` file and the plain zip is removed. The
password is never stored; checking or restoring such a backup asks for it again.

Restore runs only while the studio is stopped (`Restore-Studio.cmd`). It verifies the
whole backup into a new folder first, then renames the current data folder to
`<name>.before-restore-<time>` and puts the restored folder in its place. Nothing is
deleted or overwritten.

Usage: python -m backend.backup list | verify <zip> | restore [<zip>]
"""

import getpass
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select

from backend.backup_crypto import (
    NotEncrypted,
    WrongPassword,
    decrypt_file,
    encrypt_file,
    is_encrypted,
)
from backend.configuration import ASSET_DIRECTORIES, Settings, asset_path
from backend.keystore import KEY_DIRECTORY
from backend.models import Character, GenerationResult, ReferencePhoto, Scene
from backend.persistence import writing_session

FORMAT = 1
NAME = re.compile(r"^character-studio-backup-\d{8}-\d{6}(-\d+)?\.(zip|csbackup)$")
STAMP = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")
BACKED_UP = tuple(d for d in ASSET_DIRECTORIES if d != "backups")
# Already compressed; storing them avoids wasted work.
STORED = {".jpg", ".jpeg", ".png", ".webp", ".zip"}


class BackupError(Exception):
    """A backup could not be made, verified or restored; the message is safe to show."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def known_revisions() -> set[str]:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    return {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}


def backups_dir(settings: Settings) -> Path:
    folder = asset_path(settings, "backups")
    folder.mkdir(exist_ok=True)
    return folder


def clean_partial(settings: Settings) -> None:
    """A backup interrupted by a stop leaves only `.partial` items; remove them at startup."""
    for path in backups_dir(settings).glob("*.partial"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _snapshot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _add(archive: zipfile.ZipFile, source: Path, name: str) -> dict:
    """Stream one file into the zip, hashing exactly the bytes written."""
    info = zipfile.ZipInfo.from_file(source, name)
    stored = source.suffix.lower() in STORED
    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    digest, size = hashlib.sha256(), 0
    with source.open("rb") as file, archive.open(info, "w", force_zip64=True) as out:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
            out.write(block)
    return {"sha256": digest.hexdigest(), "size": size}


def _counts(session) -> dict:
    return {
        "characters": session.scalar(select(func.count()).select_from(Character)),
        "photos": session.scalar(select(func.count()).select_from(ReferencePhoto)),
        "scenes": session.scalar(select(func.count()).select_from(Scene)),
        "results": session.scalar(select(func.count()).select_from(GenerationResult)),
    }


def _list_assets(settings: Settings) -> list[str]:
    files = []
    for name in BACKED_UP:
        root = asset_path(settings, name)
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.name.endswith(".partial"):
                    files.append(path.relative_to(settings.data_dir).as_posix())
    return files


def create_backup(engine, settings: Settings, password: str | None = None) -> Path:
    """Write one backup and return its path: a zip, or (with a password) a `.csbackup`."""
    folder = backups_dir(settings)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base, n = f"character-studio-backup-{stamp}", 1
    while any((folder / f"{base}{ext}").exists() for ext in (".zip", ".csbackup")):
        n += 1
        base = f"character-studio-backup-{stamp}-{n}"
    name = f"{base}.zip"
    partial = folder / f"{name}.partial"
    sealed = folder / f"{base}.csbackup.partial"
    snapshot = folder / f"{name}.files.partial"
    try:
        # One moment for the database and its files; writes wait only for this part.
        with writing_session(engine) as session:
            snapshot.mkdir()
            session.connection()  # Holds the write lock, so nothing commits meanwhile.
            # SQLite's backup API reads through its own connection (WAL allows reading
            # while the lock is held); one step copies a single consistent snapshot.
            database = asset_path(settings, "studio.db").as_posix()
            source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            target = sqlite3.connect(snapshot / "studio.db")
            try:
                source.backup(target, pages=-1)
            finally:
                target.close()
                source.close()
            counts = _counts(session)
            revision = session.connection().exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            files = _list_assets(settings)
            for key in files:
                _snapshot(asset_path(settings, key), snapshot.joinpath(*key.split("/")))
        manifest = {
            "format": FORMAT,
            "application": "character-studio",
            "created_at": datetime.now(UTC).isoformat(),
            "schema_revision": revision,
            "counts": counts,
            "files": {},
        }
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            for key in ["studio.db", *files]:
                manifest["files"][key] = _add(archive, snapshot.joinpath(*key.split("/")), key)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        if password is not None:
            # The plain zip exists only as a `.partial` inside the data folder, which holds
            # the same data unencrypted anyway, and is removed as soon as it is sealed.
            encrypt_file(partial, sealed, password)
            partial.unlink()
            name = f"{base}.csbackup"
            sealed.replace(folder / name)
        else:
            partial.replace(folder / name)
    except BaseException:
        partial.unlink(missing_ok=True)
        sealed.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)
    return folder / name


def read_manifest(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise BackupError("This is not a Character Studio backup, or it is damaged.") from error
    if manifest.get("application") != "character-studio" or manifest.get("format") != FORMAT:
        raise BackupError("This is not a Character Studio backup this version can read.")
    return manifest


def _stamp_time(name: str) -> str | None:
    match = STAMP.search(name)
    if not match:
        return None
    y, mo, d, h, mi, s = (int(v) for v in match.groups())
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC).isoformat()


def backup_info(path: Path) -> dict:
    info = {"name": path.name, "size": path.stat().st_size, "created_at": None, "counts": None,
            "encrypted": False}
    if is_encrypted(path):
        # Its contents (and counts) can only be read with the password.
        info.update(encrypted=True, created_at=_stamp_time(path.name))
        return info
    try:
        manifest = read_manifest(path)
    except BackupError as error:
        info["problem"] = str(error)
        return info
    info.update(
        created_at=manifest["created_at"],
        counts=manifest["counts"],
        schema_revision=manifest["schema_revision"],
    )
    return info


def list_backups(settings: Settings) -> list[dict]:
    paths = [p for p in backups_dir(settings).iterdir() if p.is_file() and NAME.match(p.name)]
    return [backup_info(p) for p in sorted(paths, key=lambda p: p.name, reverse=True)]


def _safe_member(name: str) -> bool:
    parts = Path(name).parts
    return (
        bool(parts)
        and not Path(name).is_absolute()
        and ":" not in name
        and "\\" not in name
        and ".." not in parts
        and (name == "studio.db" or parts[0] in BACKED_UP)
    )


def _check_database(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("The database in this backup is damaged.")
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    except sqlite3.DatabaseError as error:
        raise BackupError("The database in this backup is damaged.") from error
    finally:
        connection.close()
    if revision not in known_revisions():
        raise BackupError(
            "This backup comes from a newer version of Character Studio. Update the studio first."
        )
    return revision


def extract_verified(path: Path, target: Path) -> dict:
    """Extract into an empty folder, checking every file against the manifest."""
    manifest = read_manifest(path)
    expected = manifest["files"]
    target.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(path) as archive:
        members = {i.filename: i for i in archive.infolist() if not i.is_dir()}
        unexpected = set(members) - set(expected) - {"manifest.json"}
        missing = set(expected) - set(members)
        if unexpected or missing or not all(_safe_member(n) for n in expected):
            raise BackupError("This backup's contents do not match its manifest.")
        for name, details in expected.items():
            destination = target.joinpath(*Path(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(members[name]) as source, destination.open("wb") as out:
                for block in iter(lambda source=source: source.read(1 << 20), b""):
                    digest.update(block)
                    out.write(block)
            if digest.hexdigest() != details["sha256"]:
                raise BackupError(f"A file in this backup is damaged: {name}.")
    manifest["schema_revision"] = _check_database(target / "studio.db")
    return manifest


def open_backup(path: Path, password: str | None, scratch: Path) -> Path:
    """The plain zip of a backup: the file itself, or a decrypted copy inside `scratch`."""
    if not is_encrypted(path):
        return path
    if not password:
        raise BackupError("This backup is protected with a password. Enter it to continue.")
    plain = scratch / "decrypted.zip"
    try:
        decrypt_file(path, plain, password)
    except (WrongPassword, NotEncrypted) as error:
        raise BackupError(str(error)) from error
    return plain


def verify_backup(path: Path, password: str | None = None) -> dict:
    """Full check without touching the data folder: every hash, plus the database."""
    with tempfile.TemporaryDirectory(prefix="studio-verify-") as scratch:
        plain = open_backup(path, password, Path(scratch))
        manifest = extract_verified(plain, Path(scratch) / "check")
    return {
        "ok": True,
        "files": len(manifest["files"]),
        "counts": manifest["counts"],
        "encrypted": plain != path,
    }


def restore_backup(path: Path, data_dir: Path) -> tuple[Path, Path | None]:
    """Restore into a fresh folder, then swap it in. Returns (data folder, previous folder)."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    staging = data_dir.with_name(f"{data_dir.name}.restoring-{stamp}")
    try:
        extract_verified(path, staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    previous = None
    if data_dir.exists():
        previous = data_dir.with_name(f"{data_dir.name}.before-restore-{stamp}")
        try:
            data_dir.rename(previous)
        except OSError as error:
            shutil.rmtree(staging, ignore_errors=True)
            raise BackupError(
                "The data folder is in use. Stop Character Studio and close any open files, "
                "then try again. Nothing was changed."
            ) from error
    try:
        staging.rename(data_dir)
    except OSError as error:
        if previous is not None:
            previous.rename(data_dir)
        raise BackupError(
            "The restored folder could not be put in place. Nothing was changed."
        ) from error
    if previous is not None and (previous / "backups").is_dir():
        # Keep every backup reachable from the studio after restoring.
        (previous / "backups").rename(data_dir / "backups")
    if previous is not None and (previous / KEY_DIRECTORY).is_dir():
        # API keys are never in backups (Phase 6A); keep the ones saved on this PC.
        (previous / KEY_DIRECTORY).rename(data_dir / KEY_DIRECTORY)
    return data_dir, previous


class BackupRunner:
    """One backup at a time, in the background, so a large one never blocks a request."""

    def __init__(self, engine, settings: Settings):
        self.engine, self.settings = engine, settings
        self._lock = threading.Lock()
        self.running = False
        self.error: str | None = None
        self.last: str | None = None

    def start(self, password: str | None = None) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running, self.error = True, None
        # The password lives only in this thread's arguments and is never stored.
        threading.Thread(target=self._run, args=(password,), name="backup", daemon=True).start()
        return True

    def _run(self, password: str | None) -> None:
        try:
            self.last = create_backup(self.engine, self.settings, password).name
        except BackupError as error:
            self.error = str(error)
        except OSError:
            self.error = "The backup could not be written. Check free disk space, then try again."
        except Exception:
            self.error = "The backup could not be completed because of an unexpected problem."
        finally:
            with self._lock:
                self.running = False


def _choose(settings: Settings) -> Path:
    items = list_backups(settings)
    if not items:
        raise BackupError(f"No backups found in {backups_dir(settings)}.")
    print("Backups in your data folder (newest first):")
    for number, item in enumerate(items, start=1):
        counts = item["counts"] or {}
        what = (
            "password protected"
            if item["encrypted"]
            else f"{counts.get('characters', '?')} characters, {counts.get('scenes', '?')} scenes"
        )
        print(f"  {number}. {item['name']}  ({item['size'] // 1024} KB, {what})")
    answer = input("Number to restore [1]: ").strip() or "1"
    if not answer.isdigit() or not 1 <= int(answer) <= len(items):
        raise BackupError("No backup chosen. Nothing was changed.")
    return backups_dir(settings) / items[int(answer) - 1]["name"]


def main(argv: list[str]) -> int:
    from backend.configuration import load_settings

    settings = load_settings()
    command = argv[0] if argv else "list"
    try:
        if command == "list":
            for item in list_backups(settings):
                print(item["name"], item.get("problem", ""))
            return 0
        if command == "verify":
            print(json.dumps(verify_backup(Path(argv[1])), indent=2))
            return 0
        if command == "restore":
            source = Path(argv[1]).resolve() if len(argv) > 1 else _choose(settings)
            # Copy a backup that lives inside the data folder out of it before renaming.
            with tempfile.TemporaryDirectory(prefix="studio-restore-") as scratch:
                if is_encrypted(source):
                    # Typed here, never shown, stored or logged (Phase 6D).
                    password = getpass.getpass("This backup is protected. Password: ")
                    source = open_backup(source, password, Path(scratch))
                elif source.is_relative_to(settings.data_dir):
                    copy = Path(scratch) / source.name
                    shutil.copy2(source, copy)
                    source = copy
                manifest = read_manifest(source)
                print(f"Backup from {manifest['created_at'][:19].replace('T', ' ')} UTC.")
                print(f"Your current data folder will be kept, renamed: {settings.data_dir}")
                if input("Type RESTORE to continue: ").strip() != "RESTORE":
                    print("Nothing was changed.")
                    return 1
                restored, previous = restore_backup(source, settings.data_dir)
            print(f"Restored into {restored}.")
            if previous:
                print(f"Your previous data is kept in {previous}.")
            print("Start Character Studio to use the restored data.")
            return 0
        print(__doc__)
        return 2
    except BackupError as error:
        print(f"Restore stopped: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
