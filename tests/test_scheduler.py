import threading
import time
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

        def _task(index: int) -> int:
            order.append(index)
            return index

        futures = [self.scheduler.submit(self.db_path, _task, index) for index in range(3)]
        results = [future.result() for future in futures]

        self.assertEqual(results, [0, 1, 2])
        self.assertEqual(order, [0, 1, 2])

    def test_different_databases_can_run_in_parallel(self) -> None:
        started = threading.Event()

        def _sleep_task() -> str:
            started.set()
            time.sleep(0.2)
            return "done"

        first_future = self.scheduler.submit(self.db_path, _sleep_task)
        started.wait(timeout=1)
        begin = time.perf_counter()
        second_future = self.scheduler.submit(self.other_db_path, _sleep_task)
        self.assertEqual(first_future.result(), "done")
        self.assertEqual(second_future.result(), "done")
        elapsed = time.perf_counter() - begin

        self.assertLess(elapsed, 0.35)

    def test_submit_manager_call_backfills_primary_key_after_result(self) -> None:
        customer = Customer(name="Queued Alice")

        future = self.scheduler.submit_manager_call(self.customer_manager, self.customer_manager.add_customer, customer)
        self.assertIsNone(customer.cid)
        future.result()

        self.assertIsNotNone(customer.cid)

    def test_scheduler_propagates_task_exceptions(self) -> None:
        def _raise_error() -> None:
            raise ValueError("boom")

        future = self.scheduler.submit(self.db_path, _raise_error)

        with self.assertRaises(ValueError):
            future.result()

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
            future.result()

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
            future.result()

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
            future.result()

        self.assertEqual(len(self.agent_preset_manager.list_agent_preset()), 1)

    def test_same_database_get_version_creates_singleton_row_once(self) -> None:
        futures = [
            self.scheduler.submit_manager_call(self.meta_manager, self.meta_manager.get_version)
            for _ in range(2)
        ]
        results = [future.result() for future in futures]

        self.assertEqual(results, ["1.0.0", "1.0.0"])
        self.assertEqual(self.meta_manager.get_version(), "1.0.0")


if __name__ == "__main__":
    unittest.main()
