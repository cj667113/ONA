import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


os.environ["ONA_DISABLE_BACKUP_SCHEDULER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flask"))

import app as ona_app  # noqa: E402


class SnatPoolTests(unittest.TestCase):
    def test_disabled_payload_does_not_require_vnic_scan(self):
        with mock.patch.object(
            ona_app,
            "snat_pool_policy",
            return_value={"enabled": True, "source_ips": ["10.0.0.1"], "interface": "eth1"},
        ), mock.patch.object(ona_app, "vnic_scan_state", side_effect=AssertionError):
            pool = ona_app.validate_snat_pool_payload(
                {"enabled": False, "source_ips": ["10.0.0.1"]}
            )

        self.assertFalse(pool["enabled"])
        self.assertEqual(pool["source_ips"], ["10.0.0.1"])
        self.assertEqual(pool["interface"], "eth1")
        self.assertEqual(pool["sources"], [])

    def test_enabled_payload_requires_virtual_router_ip(self):
        scan = {
            "source_ips": [
                {
                    "ip": "10.0.0.10",
                    "interface": "eth1",
                    "configured": True,
                    "virtual_router_ip": "",
                }
            ]
        }

        with mock.patch.object(ona_app, "vnic_scan_state", return_value=scan):
            with self.assertRaisesRegex(ona_app.RuleValidationError, "virtual router IP"):
                ona_app.validate_snat_pool_payload(
                    {"enabled": True, "source_ips": ["10.0.0.10"]}
                )

    def test_enabled_payload_can_validate_against_supplied_scan(self):
        scan = {
            "source_ips": [
                {
                    "ip": "10.0.0.10",
                    "interface": "eth1",
                    "configured": True,
                    "virtual_router_ip": "10.0.0.1",
                    "vnic_id": "vnic-a",
                }
            ]
        }

        with mock.patch.object(ona_app, "vnic_scan_state", side_effect=AssertionError):
            pool = ona_app.validate_snat_pool_payload(
                {"enabled": True, "source_ips": ["10.0.0.10"]},
                scan=scan,
            )

        self.assertTrue(pool["enabled"])
        self.assertEqual(pool["source_ips"], ["10.0.0.10"])
        self.assertEqual(pool["interface"], "eth1")
        self.assertEqual(pool["sources"][0]["virtual_router_ip"], "10.0.0.1")

    def test_temp_chain_cleanup_runs_when_mangle_chain_creation_fails(self):
        calls = []

        def fake_run_iptables(args, check=True):
            calls.append(args)
            if args == ["-t", "mangle", "-N", f"{ona_app.SNAT_MARK_CHAIN}_CHECK"]:
                raise RuntimeError("mangle unavailable")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        pool = {
            "enabled": True,
            "source_ips": ["10.0.0.10"],
            "sources": ona_app.decorate_snat_pool_sources(
                [
                    {
                        "ip": "10.0.0.10",
                        "interface": "eth1",
                        "virtual_router_ip": "10.0.0.1",
                    }
                ]
            ),
        }

        with mock.patch.object(ona_app, "run_iptables", side_effect=fake_run_iptables):
            with self.assertRaisesRegex(RuntimeError, "mangle unavailable"):
                ona_app.validate_snat_pool_runtime_commands(pool)

        self.assertIn(["-t", "nat", "-X", f"{ona_app.SNAT_POOL_CHAIN}_CHECK"], calls)
        self.assertIn(["-t", "mangle", "-X", f"{ona_app.SNAT_MARK_CHAIN}_CHECK"], calls)

    def test_positioned_jump_is_reinserted_at_requested_position(self):
        calls = []

        def fake_run_iptables(args, check=True):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(ona_app, "remove_jump") as remove_jump, mock.patch.object(
            ona_app, "run_iptables", side_effect=fake_run_iptables
        ):
            ona_app.ensure_jump("PREROUTING", ona_app.SNAT_MARK_CHAIN, "mangle", position=1)

        remove_jump.assert_called_once_with("PREROUTING", ona_app.SNAT_MARK_CHAIN, "mangle")
        self.assertEqual(
            calls,
            [["-t", "mangle", "-I", "PREROUTING", "1", "-j", ona_app.SNAT_MARK_CHAIN]],
        )

    def test_snat_rule_builds_forward_accept_rules(self):
        rule = {
            "chain": "POSTROUTING",
            "protocol": "all",
            "target": "MASQUERADE",
            "source_ip": "Null",
            "output_interface": "eth1",
            "probability": None,
        }

        commands = ona_app.build_snat_forward_commands(rule, ona_app.MANAGED_FORWARD_CHAIN)

        self.assertEqual(
            commands,
            [
                ["-t", "filter", "-A", ona_app.MANAGED_FORWARD_CHAIN, "-o", "eth1", "-j", "ACCEPT"],
                [
                    "-t",
                    "filter",
                    "-A",
                    ona_app.MANAGED_FORWARD_CHAIN,
                    "-i",
                    "eth1",
                    "-m",
                    "conntrack",
                    "--ctstate",
                    "RELATED,ESTABLISHED",
                    "-j",
                    "ACCEPT",
                ],
            ],
        )

    def test_masquerade_rule_accepts_source_cidr_match(self):
        rules = ona_app.normalize_nat_payload(
            {
                "0": {
                    "chain": "POSTROUTING",
                    "protocol": "all",
                    "target": "MASQUERADE",
                    "source_ip": "10.40.40.0/24",
                    "output_interface": "eth1",
                }
            }
        )

        command = ona_app.build_iptables_command(rules[0], ona_app.MANAGED_SNAT_CHAIN)

        self.assertEqual(rules[0]["source_ip"], "10.40.40.0/24")
        self.assertEqual(
            command,
            [
                "-t",
                "nat",
                "-A",
                ona_app.MANAGED_SNAT_CHAIN,
                "-p",
                "all",
                "-s",
                "10.40.40.0/24",
                "-o",
                "eth1",
                "-j",
                "MASQUERADE",
            ],
        )

    def test_masquerade_forward_rules_scope_source_cidr(self):
        rule = {
            "chain": "POSTROUTING",
            "protocol": "all",
            "target": "MASQUERADE",
            "source_ip": "10.40.40.0/24",
            "output_interface": "eth1",
            "probability": None,
        }

        commands = ona_app.build_snat_forward_commands(rule, ona_app.MANAGED_FORWARD_CHAIN)

        self.assertIn(
            [
                "-t",
                "filter",
                "-A",
                ona_app.MANAGED_FORWARD_CHAIN,
                "-s",
                "10.40.40.0/24",
                "-o",
                "eth1",
                "-j",
                "ACCEPT",
            ],
            commands,
        )
        self.assertIn(
            [
                "-t",
                "filter",
                "-A",
                ona_app.MANAGED_FORWARD_CHAIN,
                "-d",
                "10.40.40.0/24",
                "-i",
                "eth1",
                "-m",
                "conntrack",
                "--ctstate",
                "RELATED,ESTABLISHED",
                "-j",
                "ACCEPT",
            ],
            commands,
        )

    def test_process_nat_rules_reads_masquerade_source_cidr(self):
        _, snat_rules = ona_app.process_nat_rules(
            [
                "-A ONA_POSTROUTING -p all -s 10.40.40.0/24 -o eth1 -j MASQUERADE",
            ]
        )

        self.assertEqual(snat_rules[0]["source_ip"], "10.40.40.0/24")

    def test_snat_target_rejects_cidr_as_translation_ip(self):
        with self.assertRaisesRegex(ona_app.RuleValidationError, "valid IPv4 address"):
            ona_app.normalize_nat_payload(
                {
                    "0": {
                        "chain": "POSTROUTING",
                        "protocol": "all",
                        "target": "SNAT",
                        "source_ip": "10.40.40.0/24",
                        "output_interface": "eth1",
                    }
                }
            )

    def test_sync_snat_forward_rules_installs_filter_jump(self):
        calls = []
        rule = {
            "chain": "POSTROUTING",
            "protocol": "tcp",
            "target": "MASQUERADE",
            "source_ip": "Null",
            "output_interface": "eth1",
            "probability": None,
        }

        def fake_run_iptables(args, check=True):
            calls.append(args)
            if args == ["-t", "filter", "-C", "FORWARD", "-j", ona_app.MANAGED_FORWARD_CHAIN]:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(ona_app, "run_iptables", side_effect=fake_run_iptables):
            ona_app.sync_snat_forward_rules([rule], {"enabled": False})

        self.assertIn(
            ["-t", "filter", "-I", "FORWARD", "1", "-j", ona_app.MANAGED_FORWARD_CHAIN],
            calls,
        )
        self.assertIn(["-t", "filter", "-F", ona_app.MANAGED_FORWARD_CHAIN], calls)
        self.assertIn(
            [
                "-t",
                "filter",
                "-A",
                ona_app.MANAGED_FORWARD_CHAIN,
                "-p",
                "tcp",
                "-o",
                "eth1",
                "-j",
                "ACCEPT",
            ],
            calls,
        )

    def test_snat_pool_builds_forward_accept_rules(self):
        pool = {
            "enabled": True,
            "source_ips": ["10.0.0.10"],
            "sources": ona_app.decorate_snat_pool_sources(
                [{"ip": "10.0.0.10", "interface": "eth1"}]
            ),
        }

        commands = ona_app.snat_pool_forward_commands(pool, ona_app.MANAGED_FORWARD_CHAIN)

        self.assertIn(
            ["-t", "filter", "-A", ona_app.MANAGED_FORWARD_CHAIN, "-o", "eth1", "-j", "ACCEPT"],
            commands,
        )
        self.assertIn(
            [
                "-t",
                "filter",
                "-A",
                ona_app.MANAGED_FORWARD_CHAIN,
                "-i",
                "eth1",
                "-m",
                "conntrack",
                "--ctstate",
                "RELATED,ESTABLISHED",
                "-j",
                "ACCEPT",
            ],
            commands,
        )

    def test_snat_forwarding_sysctls_tune_conntrack_and_forwarding(self):
        existing_paths = {
            "/proc/sys/net/ipv4/conf/all/rp_filter",
            "/proc/sys/net/ipv4/conf/default/rp_filter",
            "/proc/sys/net/ipv4/conf/eth1/rp_filter",
            "/proc/sys/net/netfilter/nf_conntrack_max",
        }

        with mock.patch.object(
            ona_app.os.path,
            "exists",
            side_effect=lambda path: path in existing_paths,
        ), mock.patch.object(ona_app, "write_proc_value") as write_proc:
            ona_app.configure_snat_forwarding_sysctls(["eth1"])

        write_proc.assert_any_call("/proc/sys/net/ipv4/ip_forward", "1")
        write_proc.assert_any_call("/proc/sys/net/netfilter/nf_conntrack_max", "2097152")
        write_proc.assert_any_call("/proc/sys/net/ipv4/conf/all/rp_filter", "0")
        write_proc.assert_any_call("/proc/sys/net/ipv4/conf/default/rp_filter", "0")
        write_proc.assert_any_call("/proc/sys/net/ipv4/conf/eth1/rp_filter", "0")


class BackupObjectTests(unittest.TestCase):
    def test_backup_object_allowed_can_require_prefix(self):
        policy = {"prefix": "ona-backups/"}

        self.assertTrue(ona_app.backup_object_allowed("other/backup.zip", policy))
        self.assertFalse(
            ona_app.backup_object_allowed("other/backup.zip", policy, require_prefix=True)
        )
        self.assertTrue(
            ona_app.backup_object_allowed(
                "ona-backups/backup.zip", policy, require_prefix=True
            )
        )
        self.assertFalse(ona_app.backup_object_allowed("ona-backups/backup.txt", policy))
        self.assertFalse(ona_app.backup_object_allowed("bad.zip\x00", policy))

    def test_delete_backup_requires_configured_prefix(self):
        with mock.patch.object(
            ona_app,
            "backup_policy",
            return_value={"bucket": "bucket-a", "prefix": "ona-backups/"},
        ), self.assertRaisesRegex(ona_app.RuleValidationError, "configured backup prefix"):
            ona_app.delete_backup_object("other/backup.zip")

    def test_backup_sort_uses_timestamp_before_name(self):
        backups = [
            {"name": "z.zip", "time_created": "2026-01-01T00:00:00+00:00"},
            {"name": "a.zip", "time_created": "2026-02-01T00:00:00+00:00"},
        ]

        backups.sort(key=ona_app.backup_sort_key, reverse=True)

        self.assertEqual([backup["name"] for backup in backups], ["a.zip", "z.zip"])


class ConfigTests(unittest.TestCase):
    def test_write_file_config_supports_relative_file_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.dict(os.environ, {}, clear=False):
            previous_cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                with mock.patch.object(ona_app, "config_file_path", return_value="config.json"):
                    ona_app.write_file_config({"ADDRESS": "http://example.test"})
                with open("config.json", "r", encoding="utf-8") as config_file:
                    data = json.load(config_file)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(data["ADDRESS"], "http://example.test")
        self.assertTrue(data["ONA_SECRET_KEY"])

    def test_empty_backup_override_clears_saved_value(self):
        with mock.patch.object(
            ona_app,
            "get_config",
            return_value={"OCI_NAMESPACE": "saved-namespace"},
        ):
            policy = ona_app.backup_policy({"OCI_NAMESPACE": ""})

        self.assertEqual(policy["namespace"], "")

    def test_load_file_config_ignores_non_object_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text("[]", encoding="utf-8")
            with mock.patch.object(
                ona_app, "config_file_path", return_value=str(config_path)
            ), mock.patch.object(ona_app.app.logger, "warning") as warning:
                data = ona_app.load_file_config()

        self.assertEqual(data, {})
        warning.assert_called_once()


class NatPortCapacityTests(unittest.TestCase):
    def test_read_port_capacity_does_not_double_tcp_and_udp(self):
        with mock.patch("builtins.open", mock.mock_open(read_data="10000 65000\n")):
            capacity = ona_app.read_port_capacity()

        self.assertEqual(capacity["per_ip_total"], 55001)
        self.assertEqual(capacity["per_protocol"], 55001)
        self.assertEqual(capacity["max_per_ip"], 65535)

    def test_estimated_snat_capacity_counts_one_port_space_per_source_ip(self):
        with mock.patch.object(
            ona_app,
            "snat_pool_policy",
            return_value={"enabled": True, "source_ips": ["10.0.0.10", "10.0.0.11"]},
        ), mock.patch.object(
            ona_app,
            "read_port_capacity",
            return_value={"per_ip_total": 55001},
        ):
            capacity = ona_app.estimated_snat_capacity()

        self.assertEqual(capacity["source_ip_count"], 2)
        self.assertEqual(capacity["per_ip_ports"], 55001)
        self.assertEqual(capacity["total_available_ports"], 110002)

    def test_conntrack_metrics_counts_unique_ports_once_across_protocols(self):
        previous_sample = ona_app._last_conntrack_sample
        ona_app._last_conntrack_sample = None
        try:
            with mock.patch.object(ona_app, "read_first_int", return_value=1000), mock.patch.object(
                ona_app,
                "parse_conntrack_lines",
                return_value=[
                    "ipv4 2 tcp 6 300 ESTABLISHED src=10.0.0.2 dst=198.51.100.10 sport=12345 dport=443\n",
                    "ipv4 2 udp 17 30 src=10.0.0.2 dst=198.51.100.10 sport=12345 dport=53\n",
                ],
            ), mock.patch.object(
                ona_app,
                "read_port_capacity",
                return_value={
                    "range_start": 1,
                    "range_end": 65535,
                    "usable_range_start": 1,
                    "usable_range_end": 65535,
                    "per_protocol": 65535,
                    "per_ip_total": 65535,
                    "max_per_ip": 65535,
                },
            ), mock.patch.object(
                ona_app,
                "snat_pool_policy",
                return_value={"enabled": False, "source_ips": []},
            ):
                metrics = ona_app.conntrack_metrics()
        finally:
            ona_app._last_conntrack_sample = previous_sample

        self.assertEqual(metrics["ports_in_use_by_protocol"], {"tcp": 1, "udp": 1})
        self.assertEqual(metrics["ports_in_use"], 1)
        self.assertEqual(metrics["total_available_ports"], 65535)
        self.assertEqual(metrics["available_ports"], 65534)


class DashboardHistoryTests(unittest.TestCase):
    def setUp(self):
        self.previous_history = ona_app._dashboard_history
        self.previous_loaded = ona_app._dashboard_history_loaded
        self.reset_dashboard_history()

    def tearDown(self):
        with ona_app._dashboard_history_lock:
            ona_app._dashboard_history = self.previous_history
            ona_app._dashboard_history_loaded = self.previous_loaded

    def reset_dashboard_history(self):
        with ona_app._dashboard_history_lock:
            ona_app._dashboard_history = []
            ona_app._dashboard_history_loaded = False

    def test_dashboard_history_persists_for_future_logins(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            history_path = Path(tmp_dir) / "dashboard_history.json"
            sample = {
                "timestamp": "2026-05-08T00:00:00Z",
                "epoch": time.time(),
                "cpu": {"usage_percent": 12.5},
                "memory": {"usage_percent": 24.0},
                "nat": {"total_connections": 4},
                "network": {"rx_bytes_per_second": 64},
                "rules": {"total": 3},
            }

            with mock.patch.object(
                ona_app, "dashboard_history_file_path", return_value=str(history_path)
            ):
                ona_app.record_dashboard_sample(sample)
                with open(history_path, "r", encoding="utf-8") as history_file:
                    persisted = json.load(history_file)

                self.reset_dashboard_history()
                loaded = ona_app.dashboard_history(3600)

        self.assertEqual(len(persisted["samples"]), 1)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["cpu"]["usage_percent"], 12.5)
        self.assertEqual(loaded[0]["rules"]["total"], 3)

    def test_dashboard_history_recovers_from_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            history_path = Path(tmp_dir) / "dashboard_history.json"
            history_path.write_text("{", encoding="utf-8")
            sample = {
                "timestamp": "2026-05-08T00:00:00Z",
                "epoch": time.time(),
                "cpu": {},
                "memory": {},
                "nat": {},
                "network": {},
                "rules": {},
            }

            with mock.patch.object(
                ona_app, "dashboard_history_file_path", return_value=str(history_path)
            ), mock.patch.object(ona_app.app.logger, "warning") as warning:
                self.assertEqual(ona_app.dashboard_history(3600), [])
                ona_app.record_dashboard_sample(sample)

            with open(history_path, "r", encoding="utf-8") as history_file:
                recovered = json.load(history_file)

        warning.assert_called_once()
        self.assertEqual(len(recovered["samples"]), 1)


class ValidationTests(unittest.TestCase):
    def test_string_false_values_are_false(self):
        backup_updates = ona_app.validate_backup_policy_payload(
            {"enabled": "false", "schedule": "daily", "bucket": ""}
        )
        snat_pool = ona_app.validate_snat_pool_payload(
            {"enabled": "false", "source_ips": ["10.0.0.1"]}
        )

        self.assertEqual(backup_updates["ONA_BACKUP_ENABLED"], "false")
        self.assertFalse(snat_pool["enabled"])

    def test_numeric_zero_retention_is_preserved(self):
        self.assertEqual(ona_app.parse_backup_retention(0), "0")


if __name__ == "__main__":
    unittest.main()
