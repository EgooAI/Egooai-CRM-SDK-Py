import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import AccountManager, AccountMappingManager, AgentPresetManager, CustomerManager, MetaManager, PlatformManager
from models import Account, AccountMapping, AgentPreset, Customer, Platform
from utils import ThreadPoolScheduler


class ThreadPoolSchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "scheduler.sqlite"
        self.other_db_path = self.temp_path / "scheduler-other.sqlite"
        self.customer_manager = CustomerManager(database_path=self.db_path)
        self.account_manager = AccountManager(database_path=self.db_path)
        self.platform_manager = PlatformManager(database_path=self.db_path)
        self.account_mapping_manager = AccountMappingManager(database_path=self.db_path)
        self.agent_preset_manager = AgentPresetManager(database_path=self.db_path)
        self.meta_manager = MetaManager(database_path=self.db_path)
        self.scheduler = ThreadPoolScheduler(max_workers=4)

    def tearDown(self) -> None:
        self.scheduler.shutdown(wait=True)
        self.customer_manager.engine.dispose()
        self.account_manager.engine.dispose()
        self.platform_manager.engine.dispose()
        self.account_mapping_manager.engine.dispose()
        self.agent_preset_manager.engine.dispose()
        self.meta_manager.engine.dispose()
        self.temp_dir.cleanup()

    def test_same_database_tasks_finish_in_submission_order(self) -> None:
        order: list[int] = []
        started = threading.Event()
        release = threading.Event()

        def _task(index: int) -> int:
            if index == 0:
                started.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("first task was not released")
            order.append(index)
            return index

        first = self.scheduler.submit(self.db_path, _task, 0)
        try:
            self.assertTrue(started.wait(timeout=5))
            futures = [first] + [self.scheduler.submit(self.db_path, _task, index) for index in (1, 2)]
            self.assertFalse(any(future.done() for future in futures))
        finally:
            release.set()
        results = [future.result(timeout=5) for future in futures]

        self.assertEqual(results, [0, 1, 2])
        self.assertEqual(order, [0, 1, 2])

    def test_different_databases_can_run_in_parallel(self) -> None:
        started = [threading.Event(), threading.Event()]
        release = threading.Event()

        def _task(index: int) -> str:
            started[index].set()
            if not release.wait(timeout=5):
                raise TimeoutError("parallel tasks were not released")
            return "done"

        first = self.scheduler.submit(self.db_path, _task, 0)
        second = self.scheduler.submit(self.other_db_path, _task, 1)
        try:
            for event in started:
                self.assertTrue(event.wait(timeout=5))
            self.assertFalse(first.done())
            self.assertFalse(second.done())
        finally:
            release.set()
        self.assertEqual(first.result(timeout=5), "done")
        self.assertEqual(second.result(timeout=5), "done")

    def test_submit_manager_call_backfills_primary_key_after_result(self) -> None:
        customer = Customer(name="Queued Alice")

        future = self.scheduler.submit_manager_call(self.customer_manager, self.customer_manager.add_customer, customer)
        future.result(timeout=5)

        self.assertIsNotNone(customer.cid)
        self.assertEqual(self.customer_manager.get_customer(customer.cid).name, "Queued Alice")

    def test_scheduler_propagates_task_exceptions(self) -> None:
        def _raise_error() -> None:
            raise ValueError("boom")

        future = self.scheduler.submit(self.db_path, _raise_error)

        with self.assertRaises(ValueError):
            future.result(timeout=5)

    def test_shutdown_prevents_new_submission(self) -> None:
        self.scheduler.shutdown(wait=True)

        with self.assertRaises(RuntimeError):
            self.scheduler.submit(self.db_path, lambda: None)

    def test_same_database_upsert_customer_skips_duplicate_payload(self) -> None:
        futures = [
            self.scheduler.submit_manager_call(self.customer_manager, self.customer_manager.upsert_customer, Customer(name="Alice", sex="F", region="Shanghai", extra={"level": 1}, image={"avatar": "alice.png"}))
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=5)

        self.assertEqual(len(self.customer_manager.list_customer()), 1)

    def test_same_database_upsert_account_mapping_skips_duplicate_payload(self) -> None:
        customer = Customer(name="Alice")
        self.customer_manager.add_customer(customer)
        self.platform_manager.add_platform(Platform(pid="wechat", name="WeChat", extra=None))
        account_model = Account(
            cid=customer.cid,
            pid="wechat",
            account="alice@example.com",
            nickname="Alice",
            avatar="alice.png",
            sids=[1],
            extra={"level": 1},
        )
        self.account_manager.add_account(account_model)

        futures = [
            self.scheduler.submit_manager_call(
                self.account_mapping_manager,
                self.account_mapping_manager.upsert_account_mapping,
                AccountMapping(aid=account_model.aid, type="openid", key="wx-open-id"),
            )
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=5)

        self.assertEqual(len(self.account_mapping_manager.list_account_mapping()), 1)

    def test_same_database_upsert_agent_preset_skips_duplicate_payload(self) -> None:
        futures = [
            self.scheduler.submit_manager_call(
                self.agent_preset_manager,
                self.agent_preset_manager.upsert_agent_preset,
AgentPreset(
                    apid="default-assistant",
                    name="default assistant",
                    description="General customer service preset",
                    prompt="Help the customer politely",
                    llm_level=2,
                    tools=[],
                ),
            )
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=5)

        self.assertEqual(len(self.agent_preset_manager.list_agent_preset()), 1)

    def test_same_database_get_version_creates_singleton_row_once(self) -> None:
        futures = [
            self.scheduler.submit_manager_call(self.meta_manager, self.meta_manager.get_version)
            for _ in range(2)
        ]
        results = [future.result(timeout=5) for future in futures]

        self.assertEqual(results, ["1.0.0", "1.0.0"])
        self.assertEqual(self.meta_manager.get_version(), "1.0.0")


if __name__ == "__main__":
    unittest.main()
