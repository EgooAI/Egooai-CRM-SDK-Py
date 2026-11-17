from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import hashlib
import os
import sqlite3
import unittest

from sqlmodel import Session

from core import ResourceManager, ResourceUnavailable
from utils.common import bootstrap_engine


class ResourceManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "resources.sqlite"
        self.manager = ResourceManager(self.path)
        self.manager.initialize()

    def test_binary_identity_deduplication_and_restart(self):
        for data, media in ((b"%PDF-1.7\nfile", "application/pdf"), (b"\x89PNG\0\1\2", "image/png")):
            first = self.manager.put(data, media_type=media)
            second = self.manager.put(BytesIO(data), media_type=media)
            self.assertEqual(first.resource_id, "sha256:" + hashlib.sha256(data).hexdigest())
            self.assertEqual(first.file_md5, "md5:" + hashlib.md5(data).hexdigest())
            self.assertEqual(first.resource_id, second.resource_id)
            self.manager.link(first.resource_id, namespace="tenant-a", owner_type="message", owner_id=media)
            other = self.manager.link(first.resource_id, namespace="tenant-b", owner_type="document", owner_id=media)
            restarted = ResourceManager(self.path)
            self.assertEqual(restarted.read_reference(other.reference_id, namespace="tenant-b")[1], data)
            with self.assertRaises(ResourceUnavailable):
                restarted.read_reference(other.reference_id, namespace="tenant-a")
        self.assertEqual(sum(path.is_file() for path in (self.manager.root / "objects").rglob("*")), 2)

    def test_references_protect_shared_content_and_expiry_releases_only_one_owner(self):
        resource = self.manager.put(b"shared")
        self.manager.link(resource.resource_id, namespace="a", owner_type="draft", owner_id="1", expires_at=10)
        permanent = self.manager.link(resource.resource_id, namespace="b", owner_type="message", owner_id="2")
        self.assertEqual(self.manager.collect_unreferenced(now=20, orphan_grace=100), 0)
        self.assertTrue(self.manager.unlink(permanent.reference_id, namespace="b", retain_until=30))
        self.assertEqual(self.manager.collect_unreferenced(now=29, orphan_grace=100), 0)
        self.assertEqual(self.manager.collect_unreferenced(now=30, orphan_grace=100), 1)
        with self.assertRaises(ResourceUnavailable):
            self.manager.open(resource.resource_id)
        self.manager.put(b"shared")
        with self.manager.open(resource.resource_id) as stream:
            self.assertEqual(stream.read(), b"shared")

    def test_external_transactions_do_not_commit_the_callers_work(self):
        resource = self.manager.put(b"transaction")
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("CREATE TABLE owner(id TEXT)")
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO owner VALUES ('one')")
            ref = self.manager.link(resource.resource_id, namespace="a", owner_type="owner", owner_id="one", transaction=conn)
            conn.rollback()
            self.assertIsNone(self.manager.get_reference(ref.reference_id))
            self.assertEqual(conn.execute("SELECT count(*) FROM owner").fetchone()[0], 0)
        _, engine = bootstrap_engine(self.path)
        self.addCleanup(engine.dispose)
        with Session(engine) as session:
            ref = self.manager.link(resource.resource_id, namespace="a", owner_type="owner", owner_id="two", transaction=session)
            session.rollback()
        self.assertIsNone(self.manager.get_reference(ref.reference_id))
        with engine.begin() as transaction:
            ref = self.manager.link(resource.resource_id, namespace="a", owner_type="owner", owner_id="three", transaction=transaction)
        self.assertIsNotNone(self.manager.get_reference(ref.reference_id))

    def test_concurrent_writers_and_collection_serialize_at_the_database(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(self.manager.put, b"concurrent", retain_until=100) for _ in range(3)]
            resources = [future.result(5) for future in futures]
        self.assertEqual(len({resource.resource_id for resource in resources}), 1)
        entered = Event()
        with closing(sqlite3.connect(self.path)) as conn, ThreadPoolExecutor(max_workers=1) as pool:
            conn.execute("BEGIN IMMEDIATE")
            self.manager.link(resources[0].resource_id, namespace="a", owner_type="owner", owner_id="1", transaction=conn)
            def collect():
                entered.set()
                return ResourceManager(self.path).collect_unreferenced(now=101, orphan_grace=1000)
            future = pool.submit(collect)
            try:
                self.assertTrue(entered.wait(5))
            finally:
                conn.commit()
            self.assertEqual(future.result(5), 0)
        with self.manager.open(resources[0].resource_id) as stream:
            self.assertEqual(stream.read(), b"concurrent")

    def test_corruption_invalid_ids_and_failed_publication_are_not_readable(self):
        resource = self.manager.put(b"correct")
        self.manager.path(resource.resource_id).write_bytes(b"broken!")
        with self.assertRaises(ResourceUnavailable):
            self.manager.open(resource.resource_id)
        with self.assertRaises(ResourceUnavailable):
            self.manager.link(resource.resource_id, namespace="a", owner_type="document", owner_id="x")
        self.manager.put(b"correct")
        with self.manager.open(resource.resource_id) as repaired:
            self.assertEqual(repaired.read(), b"correct")
        for identifier in ("md5:" + "a" * 32, "sha256:../../file", "sha256:" + "A" * 64):
            with self.assertRaises(ValueError):
                self.manager.open(identifier)
        with self.assertRaises(ValueError):
            self.manager.put(b"too large", max_bytes=2)
        self.assertEqual(list((self.manager.root / "staging").iterdir()), [])
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            orphan = self.manager.put(b"rolled back", transaction=conn)
            conn.rollback()
        self.assertIsNone(self.manager.get(orphan.resource_id))
        self.assertTrue(self.manager.path(orphan.resource_id).exists())

    def test_replacement_requires_expected_content_and_preserves_its_grace_period(self):
        first = self.manager.put(b"first")
        second = self.manager.put(b"second")
        owner = dict(namespace="a", owner_type="record", owner_id="one")
        ref = self.manager.link(first.resource_id, **owner)
        with self.assertRaises(ValueError):
            self.manager.link(second.resource_id, **owner)
        replaced = self.manager.link(second.resource_id, **owner, expected_resource_id=first.resource_id, retain_previous_until=100)
        self.assertEqual(ref.reference_id, replaced.reference_id)
        self.assertEqual(self.manager.collect_unreferenced(now=99, orphan_grace=1000), 0)
        self.assertEqual(self.manager.collect_unreferenced(now=100, orphan_grace=1000), 1)
        self.assertEqual(self.manager.read_reference(ref.reference_id, namespace="a")[1], b"second")

    def test_orphan_cleanup_preserves_foreign_files_and_uncommitted_young_objects(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            orphan = self.manager.put(b"orphan", transaction=conn)
            conn.rollback()
        path = self.manager.path(orphan.resource_id)
        os.utime(path, (10, 10))
        foreign = path.parent / "notes.txt"
        foreign.write_text("keep", encoding="utf-8")
        os.utime(foreign, (1, 1))
        self.assertEqual(self.manager.collect_unreferenced(now=50, orphan_grace=60), 0)
        self.assertEqual(self.manager.collect_unreferenced(now=100, orphan_grace=60), 1)
        self.assertFalse(path.exists())
        self.assertEqual(foreign.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
