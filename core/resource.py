"""Stores immutable files and transactional references without host dependencies."""

from contextlib import closing, contextmanager
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import math
import os
import re
import sqlite3
import time

from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from models.resource import Resource
from models.resource_reference import ResourceReference
from utils.common import resolve_database_path


class ResourceUnavailable(FileNotFoundError):
    """Reports missing, collected, expired or corrupt resource data."""


def sqlite_connection(transaction):
    """Adapts a caller-owned SQLite connection or SQLAlchemy transaction."""
    if isinstance(transaction, sqlite3.Connection):
        return transaction
    # Session.connection() and Connection.connection have different shapes.
    connection = transaction.connection
    connection = connection() if callable(connection) else transaction
    raw = connection.connection.driver_connection
    if not isinstance(raw, sqlite3.Connection):
        raise ValueError("Resources require a SQLite transaction")
    return raw


def _one(cursor):
    row = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), row)) if row is not None else None


class ResourceManager:
    """Provides local binary storage with explicit initialization and reference GC."""

    def __init__(self, database_path=None, *, root=None):
        self.database_path = (Path(database_path).expanduser().resolve() if database_path is not None
                              else resolve_database_path())
        self.root = Path(root).resolve() if root is not None else self.database_path.with_name(self.database_path.name + ".resources")

    @staticmethod
    def validate_id(resource_id):
        if not isinstance(resource_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", resource_id):
            raise ValueError("Invalid resource ID")

    def path(self, resource_id):
        self.validate_id(resource_id)
        digest = resource_id.split(":", 1)[1]
        return self.root / "objects" / "sha256" / digest[:2] / digest[2:4] / digest

    @contextmanager
    def transaction(self, transaction=None, *, write=False, create=False):
        """Joins a same-database transaction without committing caller-owned work."""
        if transaction is not None:
            conn = sqlite_connection(transaction)
            filename = next((row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main"), "")
            if not filename or Path(filename).resolve() != self.database_path:
                raise ValueError("Resource transaction belongs to another database")
            if write:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                else:
                    # Acquires the SQLite writer lock even for a deferred transaction.
                    conn.execute("UPDATE resource SET retain_until=retain_until WHERE 0")
            yield conn
            return
        mode = "rwc" if create else "rw" if write else "ro"
        with closing(sqlite3.connect(self.database_path.as_uri() + "?mode=" + mode, uri=True,
                                     timeout=30, isolation_level=None)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                if write:
                    conn.commit()
            except BaseException:
                if write:
                    conn.rollback()
                raise

    def initialize(self):
        """Creates only the resource tables; reads never create schema or files."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction(write=True, create=True) as conn:
            for model in (Resource, ResourceReference):
                conn.execute(str(CreateTable(model.__table__, if_not_exists=True).compile(dialect=dialect())))
                for index in model.__table__.indexes:
                    conn.execute(str(CreateIndex(index, if_not_exists=True).compile(dialect=dialect())))

    def get(self, resource_id, *, transaction=None):
        self.validate_id(resource_id)
        if not self.database_path.is_file():
            return None
        with self.transaction(transaction) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='resource'").fetchone():
                return None
            row = _one(conn.execute("SELECT * FROM resource WHERE resource_id=?", (resource_id,)))
        if row is None:
            return None
        row["attributes"] = json.loads(row["attributes"])
        return Resource(**row)

    @staticmethod
    def _verify(stream, resource_id, size):
        digest = hashlib.sha256()
        count = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            count += len(chunk)
        if count != size or "sha256:" + digest.hexdigest() != resource_id:
            raise ResourceUnavailable("corrupt")
        stream.seek(0)

    def _open(self, resource_id, *, transaction=None):
        """Returns the verified record together with its stream."""
        record = self.get(resource_id, transaction=transaction)
        if record is None or record.state != "ready":
            raise ResourceUnavailable("missing")
        try:
            stream = self.path(resource_id).open("rb")
        except FileNotFoundError:
            raise ResourceUnavailable("missing") from None
        try:
            self._verify(stream, resource_id, record.size)
            return record, stream
        except BaseException:
            stream.close()
            raise

    def open(self, resource_id, *, transaction=None):
        """Returns a verified binary file handle owned by the caller."""
        _, stream = self._open(resource_id, transaction=transaction)
        return stream

    def put(self, source, *, media_type="application/octet-stream", attributes=None,
            retain_until=0.0, max_bytes=None, transaction=None):
        """Hashes and publishes bytes before registering their durable identity."""
        if not math.isfinite(retain_until):
            raise ValueError("Invalid retention time")
        encoded = json.dumps(attributes or {}, allow_nan=False, sort_keys=True)
        stream = BytesIO(source) if isinstance(source, bytes) else source
        staging = self.root / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        temporary = staging / uuid4().hex
        sha256, md5, size = hashlib.sha256(), hashlib.md5(), 0
        try:
            with temporary.open("xb") as output:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise ValueError("Resource exceeds byte budget")
                    sha256.update(chunk)
                    md5.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            identifier = "sha256:" + sha256.hexdigest()
            target = self.path(identifier)
            with self.transaction(transaction, write=True) as conn:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    try:
                        with target.open("rb") as existing:
                            self._verify(existing, identifier, size)
                    except ResourceUnavailable:
                        # Only verified bytes of this exact identity can repair a corrupt copy.
                        os.replace(temporary, target)
                else:
                    temporary.rename(target)
                conn.execute("""INSERT INTO resource
                    (resource_id,file_md5,size,media_type,attributes,state,created_at,retain_until)
                    VALUES (?,?,?,?,?,'ready',?,?) ON CONFLICT(resource_id) DO UPDATE SET
                    state='ready', retain_until=max(resource.retain_until,excluded.retain_until)
                """, (identifier, "md5:" + md5.hexdigest(), size, media_type, encoded, time.time(), retain_until))
                return self.get(identifier, transaction=conn)
        finally:
            temporary.unlink(missing_ok=True)

    def get_reference(self, reference_id, *, transaction=None):
        if not self.database_path.is_file():
            return None
        with self.transaction(transaction) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='resource_reference'").fetchone():
                return None
            row = _one(conn.execute("SELECT * FROM resource_reference WHERE reference_id=?", (reference_id,)))
        return ResourceReference(**row) if row else None

    def list_references(self, *, namespace, resource_id=None, transaction=None):
        with self.transaction(transaction) as conn:
            cursor = conn.execute("SELECT * FROM resource_reference WHERE namespace=?" +
                                  (" AND resource_id=?" if resource_id else ""),
                                  (namespace, resource_id) if resource_id else (namespace,))
            names = [column[0] for column in cursor.description]
            return [ResourceReference(**dict(zip(names, row))) for row in cursor]

    def find_reference(self, *, namespace, owner_type, owner_id, slot="content", transaction=None):
        """Resolves one caller-owned identity without enumerating other references."""
        if not self.database_path.is_file():
            return None
        with self.transaction(transaction) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='resource_reference'").fetchone():
                return None
            row = _one(conn.execute("SELECT * FROM resource_reference WHERE namespace=? AND owner_type=? AND owner_id=? AND slot=?",
                                    (namespace, owner_type, owner_id, slot)))
        return ResourceReference(**row) if row else None

    def link(self, resource_id, *, namespace, owner_type, owner_id, slot="content",
             expires_at=None, expected_resource_id=None, retain_previous_until=0.0, transaction=None):
        """Binds an opaque owner, rejecting an implicit content replacement."""
        key = (namespace, owner_type, owner_id, slot)
        if any(not isinstance(part, str) or not part for part in key):
            raise ValueError("Reference identity must be nonempty")
        if expires_at is not None and not math.isfinite(expires_at):
            raise ValueError("Invalid reference expiry")
        if not math.isfinite(retain_previous_until):
            raise ValueError("Invalid retention time")
        with self.transaction(transaction, write=True) as conn:
            with self.open(resource_id, transaction=conn):
                pass
            old = _one(conn.execute("SELECT * FROM resource_reference WHERE namespace=? AND owner_type=? AND owner_id=? AND slot=?", key))
            if old and old["resource_id"] != resource_id and old["resource_id"] != expected_resource_id:
                raise ValueError("Reference already belongs to different content")
            if old and old["resource_id"] != resource_id:
                conn.execute("UPDATE resource SET retain_until=max(retain_until,?) WHERE resource_id=?",
                             (retain_previous_until, old["resource_id"]))
            identifier = old["reference_id"] if old else uuid4().hex
            conn.execute("""INSERT INTO resource_reference
                (reference_id,namespace,owner_type,owner_id,slot,resource_id,expires_at) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(reference_id) DO UPDATE SET resource_id=excluded.resource_id, expires_at=excluded.expires_at
            """, (identifier, *key, resource_id, expires_at))
            return self.get_reference(identifier, transaction=conn)

    def read_reference(self, reference_id, *, namespace, transaction=None, now=None):
        ref = self.get_reference(reference_id, transaction=transaction)
        now = time.time() if now is None else now
        if ref is None or ref.namespace != namespace or (ref.expires_at is not None and ref.expires_at <= now):
            raise ResourceUnavailable("expired")
        record, stream = self._open(ref.resource_id, transaction=transaction)
        try:
            return record, stream.read()
        finally:
            stream.close()

    def unlink(self, reference_id, *, namespace, retain_until, transaction=None):
        if not math.isfinite(retain_until):
            raise ValueError("Invalid retention time")
        with self.transaction(transaction, write=True) as conn:
            ref = self.get_reference(reference_id, transaction=conn)
            if ref is None or ref.namespace != namespace:
                return False
            conn.execute("UPDATE resource SET retain_until=max(retain_until,?) WHERE resource_id=?", (retain_until, ref.resource_id))
            conn.execute("DELETE FROM resource_reference WHERE reference_id=?", (reference_id,))
            return True

    def collect_unreferenced(self, *, now, orphan_grace, limit=100):
        """Collects expired bytes under the same writer lock used to establish references."""
        if not math.isfinite(now) or orphan_grace < 0 or limit < 1:
            raise ValueError("Invalid collection policy")
        removed = 0
        with self.transaction(write=True) as conn:
            rows = conn.execute("""SELECT resource_id FROM resource r WHERE state='ready' AND retain_until<=?
                AND NOT EXISTS (SELECT 1 FROM resource_reference f WHERE f.resource_id=r.resource_id
                                AND (f.expires_at IS NULL OR f.expires_at>?)) LIMIT ?""", (now, now, limit)).fetchall()
            for (identifier,) in rows:
                try:
                    self.path(identifier).unlink(missing_ok=True)
                except OSError:
                    continue
                conn.execute("UPDATE resource SET state='collected' WHERE resource_id=?", (identifier,))
                removed += 1
            for directory in (self.root / "staging", self.root / "objects"):
                for path in directory.rglob("*"):
                    if removed >= limit:
                        return removed
                    if not path.is_file() or path.stat().st_mtime > now - orphan_grace:
                        continue
                    if directory.name == "staging":
                        if path.parent != directory or not re.fullmatch(r"[0-9a-f]{32}", path.name):
                            continue
                    elif not re.fullmatch(r"[0-9a-f]{64}", path.name) or path != self.path("sha256:" + path.name):
                        continue
                    if directory.name == "objects" and conn.execute("SELECT 1 FROM resource WHERE resource_id=?", ("sha256:" + path.name,)).fetchone():
                        continue
                    try:
                        path.unlink()
                    except OSError:
                        continue
                    removed += 1
        return removed


__all__ = ["ResourceManager", "ResourceUnavailable", "sqlite_connection"]
