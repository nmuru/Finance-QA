import unittest
from unittest.mock import patch

from app import memory_guard


class MemoryGuardTests(unittest.TestCase):
    def test_cgroup_v2_reclaims_filesystem_cache(self):
        gib = 1024 * 1024 * 1024
        limit = gib
        current = 900 * 1024 * 1024
        stat = "\n".join(
            [
                f"anon {500 * 1024 * 1024}",
                f"file {350 * 1024 * 1024}",
                f"shmem {50 * 1024 * 1024}",
                f"slab_reclaimable {20 * 1024 * 1024}",
            ]
        )

        values = {
            "/sys/fs/cgroup/memory.max": str(limit),
            "/sys/fs/cgroup/memory.current": str(current),
            "/sys/fs/cgroup/memory.stat": stat,
        }

        def read_text(path, encoding="utf-8"):
            return values[str(path)]

        with patch.object(memory_guard.Path, "read_text", new=read_text):
            available, used, detected_limit = memory_guard.memory_snapshot()

        self.assertEqual(detected_limit, limit)
        self.assertEqual(used, 580 * 1024 * 1024)
        self.assertEqual(available, 444 * 1024 * 1024)

    def test_cgroup_v2_keeps_shmem_as_used(self):
        limit = 1024 * 1024 * 1024
        current = 900 * 1024 * 1024
        stat = "\n".join(
            [
                f"anon {600 * 1024 * 1024}",
                f"file {200 * 1024 * 1024}",
                f"shmem {150 * 1024 * 1024}",
            ]
        )

        values = {
            "/sys/fs/cgroup/memory.max": str(limit),
            "/sys/fs/cgroup/memory.current": str(current),
            "/sys/fs/cgroup/memory.stat": stat,
        }

        def read_text(path, encoding="utf-8"):
            return values[str(path)]

        with patch.object(memory_guard.Path, "read_text", new=read_text):
            available, used, detected_limit = memory_guard.memory_snapshot()

        self.assertEqual(detected_limit, limit)
        self.assertEqual(used, 850 * 1024 * 1024)
        self.assertEqual(available, 174 * 1024 * 1024)

    def test_real_pressure_is_still_detected(self):
        limit = 1024 * 1024 * 1024
        current = 950 * 1024 * 1024

        with patch.object(
            memory_guard,
            "_cgroup_memory",
            return_value=(limit, current, 10 * 1024 * 1024),
        ):
            self.assertTrue(memory_guard.memory_pressure())

    def test_no_cgroup_falls_back_to_psutil(self):
        virtual = type("VirtualMemory", (), {"available": 700 * 1024 * 1024, "total": 1024 * 1024 * 1024})()

        with patch.object(memory_guard.psutil, "virtual_memory", return_value=virtual):
            with patch.object(memory_guard.Path, "read_text", side_effect=FileNotFoundError):
                available, used, limit = memory_guard.memory_snapshot()

        self.assertEqual(available, 700 * 1024 * 1024)
        self.assertEqual(used, 324 * 1024 * 1024)
        self.assertIsNone(limit)

    def test_cgroup_v1_uses_page_cache_as_reclaimable(self):
        limit = 1024 * 1024 * 1024
        current = 900 * 1024 * 1024
        stat = f"cache {300 * 1024 * 1024}\n"

        values = {
            "/sys/fs/cgroup/memory/max": "max",
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(limit),
            "/sys/fs/cgroup/memory/memory.usage_in_bytes": str(current),
            "/sys/fs/cgroup/memory/memory.stat": stat,
        }

        def read_text(path, encoding="utf-8"):
            return values[str(path)]

        with patch.object(memory_guard.Path, "read_text", new=read_text):
            available, used, detected_limit = memory_guard.memory_snapshot()

        self.assertEqual(detected_limit, limit)
        self.assertEqual(used, 600 * 1024 * 1024)
        self.assertEqual(available, 424 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
