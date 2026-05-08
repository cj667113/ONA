#!/usr/bin/env python3
import hmac
import ipaddress
import io
import json
import math
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

import jwt
import requests
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
from jwt import InvalidTokenError
from oauthlib.oauth2 import WebApplicationClient

try:
    import oci
except ImportError:
    oci = None


app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("ONA_SECRET_KEY") or secrets.token_urlsafe(48)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=64 * 1024,
)

os.environ["XTABLES_LIBDIR"] = "/usr/lib64/xtables"

CONFIG_KEYS = (
    "ORACLE_CLIENT_ID",
    "ORACLE_IDCS_SECRET",
    "ORACLE_IDCS_URL",
    "ADDRESS",
    "ONA_SECRET_KEY",
    "ORACLE_JWKS_URL",
    "OCI_AUTH_METHOD",
    "OCI_REGION",
    "OCI_COMPARTMENT_ID",
    "OCI_NAMESPACE",
    "ONA_BACKUP_BUCKET",
    "ONA_BACKUP_PREFIX",
    "ONA_BACKUP_ENABLED",
    "ONA_BACKUP_SCHEDULE",
    "ONA_BACKUP_TIME_UTC",
    "ONA_BACKUP_WEEKDAY",
    "ONA_BACKUP_RETENTION",
    "ONA_BACKUP_LAST_SCHEDULE_KEY",
    "ONA_LAST_BACKUP_AT",
    "ONA_LAST_BACKUP_OBJECT",
    "ONA_LAST_BACKUP_ERROR",
    "ONA_VNIC_SCAN_JSON",
    "ONA_VNIC_SCAN_AT",
    "ONA_SNAT_POOL_ENABLED",
    "ONA_SNAT_POOL_IPS",
    "ONA_SNAT_POOL_INTERFACE",
)
REQUIRED_CONFIG_KEYS = (
    "ORACLE_CLIENT_ID",
    "ORACLE_IDCS_SECRET",
    "ORACLE_IDCS_URL",
    "ADDRESS",
)

MANAGED_DNAT_CHAIN = "ONA_PREROUTING"
MANAGED_SNAT_CHAIN = "ONA_POSTROUTING"
SNAT_POOL_CHAIN = "ONA_SNAT_POOL"
SNAT_MARK_CHAIN = "ONA_SNAT_MARK"
TEMP_CHAIN_SUFFIX = "_CHECK"
SNAT_POOL_MARK_BASE = 0x4F4E0000
SNAT_POOL_TABLE_BASE = 30000
SNAT_POOL_RULE_PRIORITY_BASE = 30000
SNAT_POOL_MAX_SOURCES = 256
ALLOWED_DNAT_PROTOCOLS = {"tcp", "udp"}
ALLOWED_SNAT_PROTOCOLS = {"all", "tcp", "udp"}
ALLOWED_SNAT_TARGETS = {"MASQUERADE", "SNAT"}
ALLOWED_JWT_ALGORITHMS = {"RS256", "RS384", "RS512"}
INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:+-]{1,64}$")
OCI_REGION_RE = re.compile(r"^[A-Za-z0-9-]+(?:-[A-Za-z0-9-]+)*-[0-9]+$")
OCI_OCID_RE = re.compile(r"^ocid1\.[A-Za-z0-9_.:-]+$")
BUCKET_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,256}$")
BACKUP_PREFIX_RE = re.compile(r"^[A-Za-z0-9._/+@=-]{0,512}$")
ALLOWED_OCI_AUTH_METHODS = {"instance_principal"}
ALLOWED_BACKUP_SCHEDULES = {"manual", "hourly", "daily", "weekly"}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DEFAULT_BACKUP_PREFIX = "ona-backups/"
DEFAULT_BACKUP_RETENTION = 30
IMDS_VNICS_URL = "http://169.254.169.254/opc/v2/vnics/"

_provider_cache = {}
_jwks_cache = {}
_scheduler_started = False
_scheduler_lock = threading.Lock()
_config_lock = threading.Lock()
_metrics_lock = threading.Lock()
_dashboard_history_lock = threading.Lock()
_last_cpu_sample = None
_last_network_sample = None
_last_conntrack_sample = None
_dashboard_history = []
_dashboard_history_loaded = False
_dashboard_history_retention_seconds = 24 * 60 * 60
_dashboard_history_max_samples = 5000


class RuleValidationError(ValueError):
    pass


class BackupError(RuntimeError):
    pass


class VnicScanError(RuntimeError):
    pass


def config_file_path():
    return os.getenv("ONA_CONFIG_FILE") or os.path.join(app.instance_path, "config.json")


def dashboard_history_file_path():
    return os.getenv("ONA_DASHBOARD_HISTORY_FILE") or os.path.join(
        app.instance_path, "dashboard_history.json"
    )


def load_file_config():
    path = config_file_path()
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        app.logger.warning("Unable to read ONA config file %s: %s", path, exc)
        return {}

    if not isinstance(data, dict):
        app.logger.warning("ONA config file %s did not contain a JSON object.", path)
        return {}

    return {
        key: str(value).strip()
        for key, value in data.items()
        if key in CONFIG_KEYS and value is not None
    }


def write_file_config(config):
    path = config_file_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    data = {
        key: str(value)
        for key, value in config.items()
        if key in CONFIG_KEYS and value is not None
    }
    if not data.get("ONA_SECRET_KEY"):
        data["ONA_SECRET_KEY"] = os.getenv("ONA_SECRET_KEY") or secrets.token_urlsafe(48)

    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as config_file:
        json.dump(data, config_file, indent=2)
        config_file.write("\n")
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)

    for key, value in data.items():
        os.environ[key] = value


def save_file_config(config):
    with _config_lock:
        data = load_file_config()
        data.update({key: value for key, value in config.items() if key in CONFIG_KEYS})
        write_file_config(data)
    apply_app_secret()
    _provider_cache.clear()
    _jwks_cache.clear()


def get_config():
    config = load_file_config()
    for key in CONFIG_KEYS:
        value = os.getenv(key)
        if value:
            config[key] = value.strip()

    for key in ("ORACLE_IDCS_URL", "ADDRESS", "ORACLE_JWKS_URL"):
        if config.get(key):
            config[key] = config[key].rstrip("/")
    return config


def apply_app_secret():
    secret_key = get_config().get("ONA_SECRET_KEY")
    if secret_key:
        app.secret_key = secret_key


def is_configured():
    config = get_config()
    return all(config.get(key) for key in REQUIRED_CONFIG_KEYS)


def refresh_cookie_settings():
    app.config["SESSION_COOKIE_SECURE"] = get_config().get("ADDRESS", "").startswith("https://")


def validate_absolute_url(field_name, value):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuleValidationError(f"{field_name} must be an absolute HTTP or HTTPS URL.")
    return value.rstrip("/")


def validate_setup_form(form):
    config = {
        "ORACLE_CLIENT_ID": form.get("client_id", "").strip(),
        "ORACLE_IDCS_SECRET": form.get("client_secret", "").strip(),
        "ORACLE_IDCS_URL": validate_absolute_url(
            "Oracle IDCS URL", form.get("idcs_url", "").strip()
        ),
        "ADDRESS": validate_absolute_url("Address", form.get("address", "").strip()),
    }
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise RuleValidationError("All setup fields are required.")
    return config


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def require_csrf_token():
    expected = session.get("_csrf_token")
    supplied = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise RuleValidationError("Invalid or missing CSRF token.")


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def configure_request():
    refresh_cookie_settings()


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


def run_iptables(args, check=True):
    try:
        completed = subprocess.run(
            ["iptables", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Unable to run iptables: {exc}") from exc
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"iptables {' '.join(args)} failed: {message}")
    return completed


def ensure_chain(chain, table="nat"):
    result = run_iptables(["-t", table, "-N", chain], check=False)
    if result.returncode != 0 and "Chain already exists" not in result.stderr:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Unable to create {table} iptables chain {chain}: {message}")


def ensure_jump(source_chain, managed_chain, table="nat", position=None):
    if position is not None:
        remove_jump(source_chain, managed_chain, table)
        run_iptables(["-t", table, "-I", source_chain, str(position), "-j", managed_chain])
        return

    result = run_iptables(["-t", table, "-C", source_chain, "-j", managed_chain], check=False)
    if result.returncode != 0:
        run_iptables(["-t", table, "-A", source_chain, "-j", managed_chain])


def remove_jump(source_chain, managed_chain, table="nat"):
    while True:
        result = run_iptables(["-t", table, "-C", source_chain, "-j", managed_chain], check=False)
        if result.returncode != 0:
            return
        run_iptables(["-t", table, "-D", source_chain, "-j", managed_chain], check=False)


def delete_chain_if_exists(chain, table="nat"):
    run_iptables(["-t", table, "-F", chain], check=False)
    run_iptables(["-t", table, "-X", chain], check=False)


def ensure_managed_chains():
    ensure_chain(MANAGED_DNAT_CHAIN, "nat")
    ensure_chain(MANAGED_SNAT_CHAIN, "nat")
    ensure_jump("PREROUTING", MANAGED_DNAT_CHAIN, "nat")
    ensure_jump("POSTROUTING", MANAGED_SNAT_CHAIN, "nat")


def get_nat_rules():
    ensure_managed_chains()
    nat_rules = []
    for chain in (MANAGED_DNAT_CHAIN, MANAGED_SNAT_CHAIN):
        completed = run_iptables(["-t", "nat", "-S", chain])
        for nat_rule in completed.stdout.splitlines():
            if nat_rule.startswith("-A "):
                nat_rules.append(nat_rule)
    return nat_rules


def parse_port(value, field_name):
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise RuleValidationError(f"{field_name} must be a number.")
    if port < 1 or port > 65535:
        raise RuleValidationError(f"{field_name} must be between 1 and 65535.")
    return str(port)


def parse_ip(value, field_name):
    try:
        return str(ipaddress.IPv4Address(str(value).strip()))
    except ValueError:
        raise RuleValidationError(f"{field_name} must be a valid IPv4 address.")


def parse_optional_source_ip(value, target):
    normalized = str(value or "").strip()
    if target == "MASQUERADE":
        return "Null"
    if not normalized or normalized.upper() == "NULL":
        raise RuleValidationError("Source IP is required for SNAT rules.")
    return parse_ip(normalized, "Source IP")


def parse_interface(value):
    normalized = str(value or "").strip()
    if not INTERFACE_RE.fullmatch(normalized):
        raise RuleValidationError("Output interface contains invalid characters.")
    return normalized


def parse_probability(value):
    if value in (None, ""):
        return None
    try:
        probability = float(str(value).strip())
    except (TypeError, ValueError):
        raise RuleValidationError("SNAT pool probability must be numeric.")
    if probability <= 0 or probability > 1:
        raise RuleValidationError("SNAT pool probability must be between 0 and 1.")
    return f"{probability:.8f}"


def normalize_nat_payload(data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise RuleValidationError("Invalid JSON payload.") from exc
    if not isinstance(data, dict):
        raise RuleValidationError("Expected a JSON object of NAT rules.")

    normalized = []

    def rule_sort_key(item):
        key = str(item[0])
        return (0, int(key)) if key.isdigit() else (1, key)

    for _, rule in sorted(data.items(), key=rule_sort_key):
        if not isinstance(rule, dict):
            raise RuleValidationError("Each NAT rule must be an object.")

        chain = str(rule.get("chain", "")).strip().upper()
        if chain == "PREROUTING":
            protocol = str(rule.get("protocol", "")).strip().lower()
            if protocol not in ALLOWED_DNAT_PROTOCOLS:
                raise RuleValidationError("DNAT protocol must be tcp or udp.")
            normalized.append(
                {
                    "chain": "PREROUTING",
                    "protocol": protocol,
                    "destination_port": parse_port(
                        rule.get("destination_port"), "Destination port"
                    ),
                    "target": "DNAT",
                    "forward_ip": parse_ip(rule.get("forward_ip"), "Forward IP"),
                    "forward_port": parse_port(rule.get("forward_port"), "Forward port"),
                }
            )
        elif chain == "POSTROUTING":
            protocol = str(rule.get("protocol", "")).strip().lower()
            target = str(rule.get("target", "")).strip().upper()
            if protocol not in ALLOWED_SNAT_PROTOCOLS:
                raise RuleValidationError("SNAT protocol must be all, tcp, or udp.")
            if target not in ALLOWED_SNAT_TARGETS:
                raise RuleValidationError("SNAT target must be MASQUERADE or SNAT.")
            normalized.append(
                {
                    "chain": "POSTROUTING",
                    "protocol": protocol,
                    "target": target,
                    "source_ip": parse_optional_source_ip(rule.get("source_ip"), target),
                    "output_interface": parse_interface(rule.get("output_interface")),
                    "probability": parse_probability(rule.get("probability")),
                }
            )
        else:
            raise RuleValidationError("NAT rule chain must be PREROUTING or POSTROUTING.")

    return normalized


def build_iptables_command(rule, chain):
    if rule["chain"] == "PREROUTING":
        return [
            "-t",
            "nat",
            "-A",
            chain,
            "-p",
            rule["protocol"],
            "--dport",
            rule["destination_port"],
            "-j",
            "DNAT",
            "--to-destination",
            f"{rule['forward_ip']}:{rule['forward_port']}",
        ]

    command = [
        "-t",
        "nat",
        "-A",
        chain,
        "-p",
        rule["protocol"],
        "-o",
        rule["output_interface"],
    ]
    if rule.get("probability"):
        command.extend(
            [
                "-m",
                "statistic",
                "--mode",
                "random",
                "--probability",
                rule["probability"],
            ]
        )
    command.extend(["-j", rule["target"]])
    if rule["target"] == "SNAT":
        command.extend(["--to-source", rule["source_ip"]])
    return command


def validate_commands_against_temp_chain(rules, managed_chain, rule_chain):
    temp_chain = f"{managed_chain}{TEMP_CHAIN_SUFFIX}"
    delete_chain_if_exists(temp_chain)
    run_iptables(["-t", "nat", "-N", temp_chain])
    try:
        for rule in rules:
            if rule["chain"] == rule_chain:
                run_iptables(build_iptables_command(rule, temp_chain))
    finally:
        delete_chain_if_exists(temp_chain)


def replace_managed_rules(rules):
    ensure_managed_chains()
    validate_commands_against_temp_chain(rules, MANAGED_DNAT_CHAIN, "PREROUTING")
    validate_commands_against_temp_chain(rules, MANAGED_SNAT_CHAIN, "POSTROUTING")

    run_iptables(["-t", "nat", "-F", MANAGED_DNAT_CHAIN])
    run_iptables(["-t", "nat", "-F", MANAGED_SNAT_CHAIN])
    if snat_pool_policy()["enabled"]:
        ensure_snat_pool_jump()
    for rule in rules:
        chain = MANAGED_DNAT_CHAIN if rule["chain"] == "PREROUTING" else MANAGED_SNAT_CHAIN
        run_iptables(build_iptables_command(rule, chain))


def load_post_routing(data):
    rules = normalize_nat_payload(data)
    replace_managed_rules(rules)
    return get_nat_rules()


def process_nat_rules(nat_rules):
    dnat_dictionary_rule = {}
    snat_dictionary_rule = {}
    seen = set()

    for nat_rule in nat_rules:
        if isinstance(nat_rule, bytes):
            nat_rule = nat_rule.decode()
        rule_data = str(nat_rule).split()
        if "-A" not in rule_data:
            continue

        chain_name = rule_data[rule_data.index("-A") + 1]
        try:
            if chain_name == MANAGED_DNAT_CHAIN:
                destination = rule_data[rule_data.index("--to-destination") + 1]
                forward_ip, forward_port = destination.split(":", 1)
                collect = {
                    "chain": "PREROUTING",
                    "protocol": rule_data[rule_data.index("-p") + 1],
                    "destination_port": rule_data[rule_data.index("--dport") + 1],
                    "target": rule_data[rule_data.index("-j") + 1],
                    "forward_ip": forward_ip,
                    "forward_port": forward_port,
                }
                key = tuple(sorted(collect.items()))
                if key not in seen:
                    dnat_dictionary_rule[len(dnat_dictionary_rule)] = collect
                    seen.add(key)
            elif chain_name == MANAGED_SNAT_CHAIN:
                if "-j" in rule_data and rule_data[rule_data.index("-j") + 1] == SNAT_POOL_CHAIN:
                    continue
                collect = {
                    "chain": "POSTROUTING",
                    "protocol": rule_data[rule_data.index("-p") + 1]
                    if "-p" in rule_data
                    else "all",
                    "target": rule_data[rule_data.index("-j") + 1],
                    "output_interface": rule_data[rule_data.index("-o") + 1],
                    "source_ip": "Null",
                    "probability": None,
                }
                if "--to-source" in rule_data:
                    collect["source_ip"] = rule_data[rule_data.index("--to-source") + 1]
                if "--probability" in rule_data:
                    collect["probability"] = rule_data[rule_data.index("--probability") + 1]
                key = tuple(sorted(collect.items()))
                if key not in seen:
                    snat_dictionary_rule[len(snat_dictionary_rule)] = collect
                    seen.add(key)
        except (ValueError, IndexError):
            app.logger.warning("Skipping unrecognized managed NAT rule: %s", nat_rule)

    return dnat_dictionary_rule, snat_dictionary_rule


def current_rules_payload():
    raw_rules = get_nat_rules()
    dnat_rules, snat_rules = process_nat_rules(raw_rules)
    rules = list(dnat_rules.values()) + list(snat_rules.values())
    normalized_rules = normalize_nat_payload({str(index): rule for index, rule in enumerate(rules)})
    return {
        "format": "ona-iptables-backup/v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname(),
        "managed_chains": {
            "dnat": MANAGED_DNAT_CHAIN,
            "snat": MANAGED_SNAT_CHAIN,
        },
        "rule_count": len(normalized_rules),
        "rules": normalized_rules,
        "iptables_rules": raw_rules,
    }


def backup_policy(overrides=None):
    config = get_config()
    if overrides:
        config.update(
            {
                key: str(value).strip()
                for key, value in overrides.items()
                if key in CONFIG_KEYS and value is not None
            }
        )

    return {
        "auth_method": "instance_principal",
        "region": config.get("OCI_REGION", ""),
        "compartment_id": config.get("OCI_COMPARTMENT_ID", ""),
        "namespace": config.get("OCI_NAMESPACE", ""),
        "bucket": config.get("ONA_BACKUP_BUCKET", ""),
        "prefix": config.get("ONA_BACKUP_PREFIX", DEFAULT_BACKUP_PREFIX),
        "enabled": config.get("ONA_BACKUP_ENABLED", "false").lower() == "true",
        "schedule": config.get("ONA_BACKUP_SCHEDULE", "manual"),
        "time_utc": config.get("ONA_BACKUP_TIME_UTC", "00:00"),
        "weekday": config.get("ONA_BACKUP_WEEKDAY", "0"),
        "retention": config.get("ONA_BACKUP_RETENTION", str(DEFAULT_BACKUP_RETENTION)),
        "last_schedule_key": config.get("ONA_BACKUP_LAST_SCHEDULE_KEY", ""),
        "last_backup_at": config.get("ONA_LAST_BACKUP_AT", ""),
        "last_backup_object": config.get("ONA_LAST_BACKUP_OBJECT", ""),
        "last_backup_error": config.get("ONA_LAST_BACKUP_ERROR", ""),
    }


def public_backup_policy(policy=None):
    policy = policy or backup_policy()
    public = dict(policy)
    weekday = int(public["weekday"]) if str(public["weekday"]).isdigit() else 0
    if weekday < 0 or weekday >= len(WEEKDAYS):
        weekday = 0
    public["weekday_name"] = WEEKDAYS[weekday]
    return public


def normalize_backup_prefix(value):
    prefix = str(value or DEFAULT_BACKUP_PREFIX).strip().lstrip("/")
    if prefix and not BACKUP_PREFIX_RE.fullmatch(prefix):
        raise RuleValidationError("Backup prefix contains invalid characters.")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def parse_backup_time(value):
    value = str(value or "00:00").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        raise RuleValidationError("Backup time must use HH:MM format.")
    hour, minute = [int(part) for part in value.split(":", 1)]
    if hour > 23 or minute > 59:
        raise RuleValidationError("Backup time must be a valid UTC time.")
    return f"{hour:02d}:{minute:02d}"


def parse_backup_weekday(value):
    try:
        weekday = int(value)
    except (TypeError, ValueError):
        raise RuleValidationError("Backup weekday must be valid.")
    if weekday < 0 or weekday > 6:
        raise RuleValidationError("Backup weekday must be valid.")
    return str(weekday)


def parse_backup_retention(value):
    try:
        raw_value = DEFAULT_BACKUP_RETENTION if value is None or str(value).strip() == "" else value
        retention = int(str(raw_value).strip())
    except (TypeError, ValueError):
        raise RuleValidationError("Backup retention must be a number.")
    if retention < 0 or retention > 10000:
        raise RuleValidationError("Backup retention must be between 0 and 10000.")
    return str(retention)


def parse_bool(value, field_name):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"", "0", "false", "no", "off"}:
        return False
    raise RuleValidationError(f"{field_name} must be true or false.")


def validate_backup_policy_payload(payload):
    if not isinstance(payload, dict):
        raise RuleValidationError("Expected a JSON object for backup policy.")

    auth_method = str(payload.get("auth_method", "instance_principal")).strip()
    if auth_method not in ALLOWED_OCI_AUTH_METHODS:
        raise RuleValidationError("Backups only support OCI instance principal authentication.")

    region = str(payload.get("region", "")).strip()
    if region and not OCI_REGION_RE.fullmatch(region):
        raise RuleValidationError("OCI region format is invalid.")

    compartment_id = str(payload.get("compartment_id", "")).strip()
    if compartment_id and not OCI_OCID_RE.fullmatch(compartment_id):
        raise RuleValidationError("Compartment OCID format is invalid.")

    namespace = str(payload.get("namespace", "")).strip()
    if namespace and not re.fullmatch(r"^[A-Za-z0-9._-]{1,128}$", namespace):
        raise RuleValidationError("Object Storage namespace format is invalid.")

    bucket = str(payload.get("bucket", "")).strip()
    if bucket and not BUCKET_NAME_RE.fullmatch(bucket):
        raise RuleValidationError("Bucket name format is invalid.")

    schedule = str(payload.get("schedule", "manual")).strip()
    if schedule not in ALLOWED_BACKUP_SCHEDULES:
        raise RuleValidationError("Backup schedule is invalid.")

    enabled = parse_bool(payload.get("enabled", False), "Backup enabled")
    if enabled and (not bucket or schedule == "manual"):
        raise RuleValidationError("Enabled backup policies require a bucket and a schedule.")

    return {
        "OCI_AUTH_METHOD": auth_method,
        "OCI_REGION": region,
        "OCI_COMPARTMENT_ID": compartment_id,
        "OCI_NAMESPACE": namespace,
        "ONA_BACKUP_BUCKET": bucket,
        "ONA_BACKUP_PREFIX": normalize_backup_prefix(payload.get("prefix")),
        "ONA_BACKUP_ENABLED": "true" if enabled else "false",
        "ONA_BACKUP_SCHEDULE": schedule,
        "ONA_BACKUP_TIME_UTC": parse_backup_time(payload.get("time_utc")),
        "ONA_BACKUP_WEEKDAY": parse_backup_weekday(payload.get("weekday", 0)),
        "ONA_BACKUP_RETENTION": parse_backup_retention(payload.get("retention")),
        "ONA_BACKUP_LAST_SCHEDULE_KEY": "",
        "ONA_LAST_BACKUP_ERROR": "",
    }


def ensure_oci_sdk():
    if oci is None:
        raise BackupError("The OCI Python SDK is not installed.")


def oci_client(overrides=None):
    ensure_oci_sdk()
    policy = backup_policy(overrides)
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    client_config = {}
    if policy["region"]:
        client_config["region"] = policy["region"]
    return oci.object_storage.ObjectStorageClient(client_config, signer=signer)


def object_storage_namespace(client, policy):
    if policy["namespace"]:
        return policy["namespace"]
    if policy["compartment_id"]:
        return client.get_namespace(compartment_id=policy["compartment_id"]).data
    return client.get_namespace().data


def list_oci_buckets(overrides=None):
    policy = backup_policy(overrides)
    if not policy["compartment_id"]:
        raise RuleValidationError("Compartment OCID is required to list buckets.")
    client = oci_client(overrides)
    namespace = object_storage_namespace(client, policy)
    buckets = []
    page = None
    while True:
        kwargs = {"limit": 1000}
        if page:
            kwargs["page"] = page
        response = client.list_buckets(namespace, policy["compartment_id"], **kwargs)
        buckets.extend(response.data)
        page = response.headers.get("opc-next-page")
        if not page:
            break
    return {
        "namespace": namespace,
        "buckets": [
            {
                "name": bucket.name,
                "created_at": getattr(bucket, "time_created", None).isoformat()
                if getattr(bucket, "time_created", None)
                else "",
            }
            for bucket in buckets
        ],
    }


def backup_object_is_zip(object_name):
    name = str(object_name or "")
    return bool(name) and name.endswith(".zip") and "\x00" not in name


def backup_object_allowed(object_name, policy, require_prefix=False):
    name = str(object_name or "")
    if not backup_object_is_zip(name):
        return False
    if not require_prefix:
        return True
    prefix = normalize_backup_prefix(policy["prefix"])
    return name.startswith(prefix)


def backup_sort_key(backup):
    return (
        backup.get("time_created") or backup.get("time_modified") or "",
        backup.get("name", ""),
    )


def list_backup_objects(policy=None, require_prefix=False):
    policy = policy or backup_policy()
    if not policy["bucket"]:
        return []

    client = oci_client()
    namespace = object_storage_namespace(client, policy)
    prefix = normalize_backup_prefix(policy["prefix"])
    backups = []
    start = None

    while True:
        kwargs = {"fields": "name,size,timeCreated,timeModified", "limit": 1000}
        if require_prefix:
            kwargs["prefix"] = prefix
        if start:
            kwargs["start"] = start
        response = client.list_objects(namespace, policy["bucket"], **kwargs)
        for obj in response.data.objects:
            if not backup_object_allowed(obj.name, policy, require_prefix=require_prefix):
                continue
            backups.append(
                {
                    "name": obj.name,
                    "in_configured_prefix": str(obj.name).startswith(prefix),
                    "size": getattr(obj, "size", 0),
                    "time_created": getattr(obj, "time_created", None).isoformat()
                    if getattr(obj, "time_created", None)
                    else "",
                    "time_modified": getattr(obj, "time_modified", None).isoformat()
                    if getattr(obj, "time_modified", None)
                    else "",
                }
            )
        start = getattr(response.data, "next_start_with", None)
        if not start:
            break

    backups.sort(key=backup_sort_key, reverse=True)
    return backups


def enforce_backup_retention(policy=None):
    policy = policy or backup_policy()
    retention = int(policy.get("retention", DEFAULT_BACKUP_RETENTION))
    if retention <= 0 or not policy["bucket"]:
        return []

    backups = list_backup_objects(policy, require_prefix=True)
    expired = backups[retention:]
    if not expired:
        return []

    client = oci_client()
    namespace = object_storage_namespace(client, policy)
    deleted = []
    for backup in expired:
        client.delete_object(namespace, policy["bucket"], backup["name"])
        deleted.append(backup["name"])
    return deleted


def build_backup_zip():
    payload = current_rules_payload()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("rules.json", json.dumps(payload, indent=2))
        archive.writestr("iptables-rules.txt", "\n".join(payload["iptables_rules"]) + "\n")
    return buffer.getvalue(), payload


def create_backup_object(reason="manual"):
    policy = backup_policy()
    if not policy["bucket"]:
        raise RuleValidationError("Select a backup bucket before creating backups.")

    client = oci_client()
    namespace = object_storage_namespace(client, policy)
    backup_body, payload = build_backup_zip()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = normalize_backup_prefix(policy["prefix"])
    object_name = f"{prefix}ona-rules-{timestamp}-{secrets.token_hex(4)}.zip"
    client.put_object(
        namespace,
        policy["bucket"],
        object_name,
        io.BytesIO(backup_body),
        content_length=len(backup_body),
    )
    deleted_objects = enforce_backup_retention(policy)

    completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    save_file_config(
        {
            "ONA_LAST_BACKUP_AT": completed_at,
            "ONA_LAST_BACKUP_OBJECT": object_name,
            "ONA_LAST_BACKUP_ERROR": "",
        }
    )
    app.logger.info(
        "Created %s backup %s in bucket %s with %s rules",
        reason,
        object_name,
        policy["bucket"],
        payload["rule_count"],
    )
    return {
        "object_name": object_name,
        "bucket": policy["bucket"],
        "namespace": namespace,
        "created_at": completed_at,
        "rule_count": payload["rule_count"],
        "size": len(backup_body),
        "deleted_by_retention": deleted_objects,
    }


def extract_rules_from_backup(body):
    try:
        with zipfile.ZipFile(io.BytesIO(body), mode="r") as archive:
            with archive.open("rules.json") as rules_file:
                payload = json.load(rules_file)
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise RuleValidationError("Backup object is not a valid ONA rules backup.") from exc

    if payload.get("format") != "ona-iptables-backup/v1":
        raise RuleValidationError("Backup format is not supported.")
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise RuleValidationError("Backup does not contain a rule list.")
    return normalize_nat_payload({str(index): rule for index, rule in enumerate(rules)})


def restore_backup_object(object_name):
    policy = backup_policy()
    if not policy["bucket"]:
        raise RuleValidationError("Select a backup bucket before restoring backups.")
    if not backup_object_allowed(object_name, policy):
        raise RuleValidationError("Backup object must be a .zip file in the selected bucket.")

    client = oci_client()
    namespace = object_storage_namespace(client, policy)
    response = client.get_object(namespace, policy["bucket"], object_name)
    rules = extract_rules_from_backup(response.data.content)
    replace_managed_rules(rules)
    return {
        "object_name": object_name,
        "restored_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rule_count": len(rules),
    }


def delete_backup_object(object_name):
    policy = backup_policy()
    if not policy["bucket"]:
        raise RuleValidationError("Select a backup bucket before deleting backups.")
    if not backup_object_allowed(object_name, policy, require_prefix=True):
        raise RuleValidationError(
            "Backup object must be a .zip file in the configured backup prefix."
        )

    client = oci_client()
    namespace = object_storage_namespace(client, policy)
    client.delete_object(namespace, policy["bucket"], object_name)
    return {
        "object_name": object_name,
        "deleted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def scheduled_backup_key(policy, now):
    if not policy["enabled"] or policy["schedule"] == "manual":
        return None

    hour, minute = [int(part) for part in policy["time_utc"].split(":", 1)]
    if policy["schedule"] == "hourly":
        if now.minute < minute:
            return None
        return f"hourly:{now.strftime('%Y-%m-%dT%H')}"

    if now.hour < hour or (now.hour == hour and now.minute < minute):
        return None

    if policy["schedule"] == "daily":
        return f"daily:{now.strftime('%Y-%m-%d')}"

    if policy["schedule"] == "weekly":
        if now.weekday() != int(policy["weekday"]):
            return None
        return f"weekly:{now.strftime('%G-W%V')}"

    return None


def run_scheduled_backup_if_due():
    policy = backup_policy()
    now = datetime.now(timezone.utc)
    schedule_key = scheduled_backup_key(policy, now)
    if not schedule_key or schedule_key == policy["last_schedule_key"]:
        return None

    try:
        result = create_backup_object(reason="scheduled")
        save_file_config({"ONA_BACKUP_LAST_SCHEDULE_KEY": schedule_key})
        return result
    except Exception as exc:
        app.logger.exception("Scheduled backup failed")
        save_file_config({"ONA_LAST_BACKUP_ERROR": str(exc)})
        return None


def backup_scheduler_loop():
    while True:
        time.sleep(60)
        try:
            run_scheduled_backup_if_due()
        except Exception:
            app.logger.exception("Backup scheduler loop failed")


def start_backup_scheduler_once():
    global _scheduler_started
    if os.getenv("ONA_DISABLE_BACKUP_SCHEDULER") == "1":
        return
    with _scheduler_lock:
        if _scheduler_started:
            return
        thread = threading.Thread(target=backup_scheduler_loop, name="ona-backup-scheduler", daemon=True)
        thread.start()
        _scheduler_started = True


def read_first_int(path):
    try:
        with open(path, "r", encoding="utf-8") as value_file:
            return int(value_file.read().strip())
    except (OSError, ValueError):
        return 0


def json_config_value(key, default):
    raw_value = get_config().get(key, "")
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return default


def local_interfaces():
    interfaces = {}
    try:
        completed = subprocess.run(
            ["ip", "-j", "addr", "show"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            for item in json.loads(completed.stdout):
                name = item.get("ifname", "")
                mac_addr = (item.get("address") or "").lower()
                addresses = []
                for info in item.get("addr_info", []):
                    if info.get("family") == "inet" and info.get("local"):
                        addresses.append(info["local"])
                interfaces[name] = {"name": name, "mac": mac_addr, "addresses": addresses}
            return interfaces
    except (OSError, json.JSONDecodeError):
        pass

    interface_names = os.listdir("/sys/class/net") if os.path.isdir("/sys/class/net") else []
    for interface in interface_names:
        address_path = f"/sys/class/net/{interface}/address"
        try:
            with open(address_path, "r", encoding="utf-8") as address_file:
                mac_addr = address_file.read().strip().lower()
        except OSError:
            mac_addr = ""
        interfaces[interface] = {"name": interface, "mac": mac_addr, "addresses": []}
    return interfaces


def fetch_vnics_from_metadata():
    try:
        response = requests.get(
            IMDS_VNICS_URL,
            headers={"Authorization": "Bearer Oracle"},
            timeout=3,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise VnicScanError(f"Unable to read OCI VNIC metadata: {exc}") from exc
    except ValueError as exc:
        raise VnicScanError("OCI VNIC metadata returned invalid JSON.") from exc

    if not isinstance(data, list):
        raise VnicScanError("OCI VNIC metadata did not return a VNIC list.")
    return data


def normalize_vnic_scan(metadata_vnics, interfaces):
    interfaces_by_mac = {
        data["mac"].lower(): data
        for data in interfaces.values()
        if data.get("mac")
    }
    addresses_to_interface = {}
    for interface in interfaces.values():
        for address in interface.get("addresses", []):
            addresses_to_interface[address] = interface["name"]

    vnics = []
    source_ips = []
    for index, vnic in enumerate(metadata_vnics):
        mac_addr = str(vnic.get("macAddr", "")).lower()
        matched_interface = interfaces_by_mac.get(mac_addr)
        primary_ip = str(vnic.get("privateIp") or "")
        secondary_ips = [
            str(ip)
            for ip in vnic.get("secondaryPrivateIps", [])
            if ip
        ]
        all_ips = [ip for ip in [primary_ip, *secondary_ips] if ip]
        configured_ips = [
            ip
            for ip in all_ips
            if ip in addresses_to_interface
            or (matched_interface and ip in matched_interface.get("addresses", []))
        ]
        interface_name = (
            matched_interface["name"]
            if matched_interface
            else addresses_to_interface.get(primary_ip, "")
        )

        for ip in all_ips:
            source_ips.append(
                {
                    "ip": ip,
                    "vnic_id": vnic.get("vnicId", ""),
                    "interface": interface_name or addresses_to_interface.get(ip, ""),
                    "configured": ip in configured_ips,
                    "primary": ip == primary_ip,
                    "nic_index": vnic.get("nicIndex", index),
                    "virtual_router_ip": vnic.get("virtualRouterIp", ""),
                    "subnet_cidr": vnic.get("subnetCidrBlock", ""),
                }
            )

        vnics.append(
            {
                "vnic_id": vnic.get("vnicId", ""),
                "private_ip": primary_ip,
                "secondary_private_ips": secondary_ips,
                "all_private_ips": all_ips,
                "configured_ips": configured_ips,
                "interface": interface_name,
                "mac": mac_addr,
                "nic_index": vnic.get("nicIndex", index),
                "vlan_tag": vnic.get("vlanTag", ""),
                "virtual_router_ip": vnic.get("virtualRouterIp", ""),
                "subnet_cidr": vnic.get("subnetCidrBlock", ""),
                "subnet_cidrs": vnic.get("subnetCidrBlocks", []),
            }
        )

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vnics": vnics,
        "source_ips": source_ips,
        "interfaces": list(interfaces.values()),
    }


def save_vnic_scan(scan):
    save_file_config(
        {
            "ONA_VNIC_SCAN_JSON": json.dumps(scan),
            "ONA_VNIC_SCAN_AT": scan["scanned_at"],
        }
    )


def scan_vnics():
    scan = normalize_vnic_scan(fetch_vnics_from_metadata(), local_interfaces())
    save_vnic_scan(scan)
    return scan


def vnic_scan_state():
    scan = json_config_value("ONA_VNIC_SCAN_JSON", {})
    if not isinstance(scan, dict):
        scan = {}
    if not scan.get("vnics"):
        scan = {
            "scanned_at": "",
            "vnics": [],
            "source_ips": [],
            "interfaces": list(local_interfaces().values()),
        }
    elif not scan.get("interfaces"):
        scan["interfaces"] = list(local_interfaces().values())
    return scan


def run_ip(args, check=True):
    try:
        completed = subprocess.run(
            ["ip", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Unable to run ip {' '.join(args)}: {exc}") from exc
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"ip {' '.join(args)} failed: {message}")
    return completed


def vnic_ipv4_addresses(vnic):
    primary_ip = str(vnic.get("privateIp") or "")
    secondary_ips = [
        str(ip)
        for ip in vnic.get("secondaryPrivateIps", [])
        if ip
    ]
    addresses = []
    for ip in [primary_ip, *secondary_ips]:
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            continue
        addresses.append(ip)
    return addresses


def vnic_prefix_for_ip(vnic, ip):
    address = ipaddress.IPv4Address(ip)
    cidrs = []
    if vnic.get("subnetCidrBlock"):
        cidrs.append(vnic["subnetCidrBlock"])
    cidrs.extend(vnic.get("subnetCidrBlocks") or [])
    cidrs.extend(vnic.get("secondaryPrivateIpCidrs") or [])

    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(str(cidr), strict=False)
        except ValueError:
            continue
        if network.version == 4 and address in network:
            return network.prefixlen
    return 32


def configure_vnics_with_ip(metadata_vnics, interfaces):
    interfaces_by_mac = {
        data["mac"].lower(): data
        for data in interfaces.values()
        if data.get("mac")
    }
    configured_addresses = {
        address
        for interface in interfaces.values()
        for address in interface.get("addresses", [])
    }
    results = []
    errors = []

    for index, vnic in enumerate(metadata_vnics):
        mac_addr = str(vnic.get("macAddr", "")).lower()
        interface = interfaces_by_mac.get(mac_addr)
        interface_name = interface["name"] if interface else ""
        for ip in vnic_ipv4_addresses(vnic):
            item = {
                "ip": ip,
                "vnic_id": vnic.get("vnicId", ""),
                "interface": interface_name,
                "nic_index": vnic.get("nicIndex", index),
            }
            if ip in configured_addresses:
                item["status"] = "already_configured"
                results.append(item)
                continue
            if not interface_name:
                item["status"] = "error"
                item["message"] = "No matching OS interface was found for this VNIC MAC address."
                errors.append(item)
                results.append(item)
                continue

            prefix = vnic_prefix_for_ip(vnic, ip)
            item["cidr"] = f"{ip}/{prefix}"
            try:
                run_ip(["link", "set", "dev", interface_name, "up"])
                add_result = run_ip(["addr", "add", item["cidr"], "dev", interface_name], check=False)
                if add_result.returncode != 0 and "File exists" not in add_result.stderr:
                    message = add_result.stderr.strip() or add_result.stdout.strip()
                    raise RuntimeError(message or "address add failed")
                item["status"] = "configured"
                configured_addresses.add(ip)
            except RuntimeError as exc:
                item["status"] = "error"
                item["message"] = str(exc)
                errors.append(item)
            results.append(item)

    return {"method": "ip", "results": results, "errors": errors}


def run_oci_network_configure():
    if not shutil.which("oci-network-config"):
        return None

    completed = subprocess.run(
        ["oci-network-config", "configure"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return {
            "method": "oci-network-config",
            "results": [],
            "errors": [
                {
                    "status": "error",
                    "message": completed.stderr.strip() or completed.stdout.strip() or "oci-network-config configure failed",
                }
            ],
        }
    return {
        "method": "oci-network-config",
        "results": [
            {
                "status": "configured",
                "message": completed.stdout.strip() or "Configured",
            }
        ],
        "errors": [],
    }


def configure_vnic_interfaces():
    metadata_vnics = fetch_vnics_from_metadata()
    before_scan = normalize_vnic_scan(metadata_vnics, local_interfaces())
    save_vnic_scan(before_scan)

    configuration = run_oci_network_configure()
    fallback_needed = configuration is None or configuration.get("errors")
    if not fallback_needed:
        after_oci_scan = normalize_vnic_scan(metadata_vnics, local_interfaces())
        fallback_needed = any(
            not item.get("configured")
            for item in after_oci_scan.get("source_ips", [])
        )
    if fallback_needed:
        fallback = configure_vnics_with_ip(metadata_vnics, local_interfaces())
        if configuration and configuration.get("errors"):
            fallback["previous_method"] = configuration["method"]
            fallback["previous_errors"] = configuration["errors"]
        configuration = fallback

    after_scan = normalize_vnic_scan(metadata_vnics, local_interfaces())
    before_unconfigured = {
        item["ip"]
        for item in before_scan.get("source_ips", [])
        if not item.get("configured")
    }
    newly_configured = [
        item["ip"]
        for item in after_scan.get("source_ips", [])
        if item.get("configured") and item["ip"] in before_unconfigured
    ]
    configuration["configured_count"] = len(newly_configured)
    configuration["configured_ips"] = newly_configured
    save_vnic_scan(after_scan)
    return {"scan": after_scan, "configuration": configuration}


def snat_pool_policy():
    config = get_config()
    ips = [
        ip.strip()
        for ip in config.get("ONA_SNAT_POOL_IPS", "").split(",")
        if ip.strip()
    ]
    return {
        "enabled": config.get("ONA_SNAT_POOL_ENABLED", "false").lower() == "true",
        "source_ips": ips,
        "interface": config.get("ONA_SNAT_POOL_INTERFACE", ""),
    }


def snat_pool_mark(index):
    return SNAT_POOL_MARK_BASE + index + 1


def snat_pool_table(index):
    return SNAT_POOL_TABLE_BASE + index + 1


def snat_pool_priority(index):
    return SNAT_POOL_RULE_PRIORITY_BASE + index + 1


def decorate_snat_pool_sources(sources):
    if len(sources) > SNAT_POOL_MAX_SOURCES:
        raise RuleValidationError(
            f"SNAT pools support up to {SNAT_POOL_MAX_SOURCES} source IPs."
        )
    decorated = []
    for index, source in enumerate(sources):
        item = dict(source)
        item["mark"] = snat_pool_mark(index)
        item["mark_hex"] = hex(item["mark"])
        item["table"] = snat_pool_table(index)
        item["priority"] = snat_pool_priority(index)
        decorated.append(item)
    return decorated


def validate_snat_pool_payload(payload):
    if not isinstance(payload, dict):
        raise RuleValidationError("Expected a JSON object for SNAT pool policy.")

    enabled = parse_bool(payload.get("enabled", False), "SNAT pool enabled")
    source_ips = payload.get("source_ips", [])
    if not isinstance(source_ips, list):
        raise RuleValidationError("SNAT pool source IPs must be a list.")
    source_ips = [parse_ip(ip, "SNAT source IP") for ip in source_ips]
    source_ips = list(dict.fromkeys(source_ips))
    if len(source_ips) > SNAT_POOL_MAX_SOURCES:
        raise RuleValidationError(
            f"SNAT pools support up to {SNAT_POOL_MAX_SOURCES} source IPs."
        )

    if not enabled:
        existing_interface = snat_pool_policy().get("interface", "")
        interface = payload.get("interface", existing_interface)
        interface = parse_interface(interface) if interface else ""
        return {
            "enabled": False,
            "source_ips": source_ips,
            "interface": interface,
            "sources": [],
        }

    scan = vnic_scan_state()
    scanned_ips = {entry["ip"]: entry for entry in scan.get("source_ips", [])}
    unknown_ips = [ip for ip in source_ips if ip not in scanned_ips]
    if unknown_ips:
        raise RuleValidationError("SNAT source IPs must come from the latest VNIC scan.")
    unconfigured_ips = [ip for ip in source_ips if not scanned_ips[ip].get("configured")]
    if unconfigured_ips:
        raise RuleValidationError("SNAT source IPs must be configured on the OS before use.")
    if not source_ips:
        raise RuleValidationError("Enable the SNAT pool only after selecting at least one source IP.")

    source_entries = []
    for ip in source_ips:
        scanned_entry = scanned_ips[ip]
        source_entries.append(
            {
                "ip": ip,
                "interface": scanned_entry.get("interface", ""),
                "virtual_router_ip": scanned_entry.get("virtual_router_ip", ""),
                "vnic_id": scanned_entry.get("vnic_id", ""),
            }
        )
    missing_interfaces = [entry["ip"] for entry in source_entries if not entry["interface"]]
    if missing_interfaces:
        raise RuleValidationError("Selected SNAT source IPs must have an OS interface.")
    missing_routers = [entry["ip"] for entry in source_entries if not entry["virtual_router_ip"]]
    if missing_routers:
        raise RuleValidationError("Selected SNAT source IPs must have a VNIC virtual router IP.")
    for entry in source_entries:
        entry["interface"] = parse_interface(entry["interface"])
        if entry["virtual_router_ip"]:
            entry["virtual_router_ip"] = parse_ip(entry["virtual_router_ip"], "VNIC virtual router IP")

    interface = parse_interface(payload.get("interface", "")) if payload.get("interface") else ""
    if not interface and source_entries:
        interface = source_entries[0]["interface"]
    if not interface:
        raise RuleValidationError("An output interface is required for the SNAT pool.")

    return {
        "enabled": enabled,
        "source_ips": source_ips,
        "interface": interface,
        "sources": decorate_snat_pool_sources(source_entries),
    }


def snat_pool_sources(pool):
    sources = pool.get("sources") or [
        {"ip": source_ip, "interface": pool.get("interface", "")}
        for source_ip in pool["source_ips"]
    ]
    if sources and "mark" not in sources[0]:
        sources = decorate_snat_pool_sources(sources)
    return sources


def ensure_snat_pool_jump():
    ensure_chain(SNAT_POOL_CHAIN, "nat")
    ensure_jump(MANAGED_SNAT_CHAIN, SNAT_POOL_CHAIN, "nat", position=1)


def ensure_snat_mark_jump():
    ensure_chain(SNAT_MARK_CHAIN, "mangle")
    ensure_jump("PREROUTING", SNAT_MARK_CHAIN, "mangle", position=1)


def ensure_snat_pool_chains():
    ensure_managed_chains()
    ensure_snat_pool_jump()
    ensure_snat_mark_jump()


def snat_pool_nat_commands(pool, chain):
    commands = []
    for source in snat_pool_sources(pool):
        command = [
            "-t",
            "nat",
            "-A",
            chain,
            "-m",
            "mark",
            "--mark",
            source["mark_hex"],
            "-o",
            source["interface"],
            "-j",
            "SNAT",
            "--to-source",
            source["ip"],
        ]
        commands.append(command)
    return commands


def snat_pool_mark_commands(pool, chain):
    commands = [
        ["-t", "mangle", "-A", chain, "-m", "addrtype", "--dst-type", "LOCAL", "-j", "RETURN"],
        ["-t", "mangle", "-A", chain, "-j", "CONNMARK", "--restore-mark"],
        ["-t", "mangle", "-A", chain, "-m", "mark", "!", "--mark", "0x0", "-j", "RETURN"],
    ]
    sources = snat_pool_sources(pool)
    remaining = len(sources)
    for index, source in enumerate(sources):
        command = ["-t", "mangle", "-A", chain]
        if index < len(sources) - 1:
            probability = 1 / remaining
            command.extend(
                [
                    "-m",
                    "statistic",
                    "--mode",
                    "random",
                    "--probability",
                    f"{probability:.8f}",
                ]
            )
        command.extend(["-j", "MARK", "--set-mark", source["mark_hex"]])
        commands.append(command)
        commands.append(
            [
                "-t",
                "mangle",
                "-A",
                chain,
                "-m",
                "mark",
                "--mark",
                source["mark_hex"],
                "-j",
                "CONNMARK",
                "--save-mark",
            ]
        )
        commands.append(
            [
                "-t",
                "mangle",
                "-A",
                chain,
                "-m",
                "mark",
                "--mark",
                source["mark_hex"],
                "-j",
                "RETURN",
            ]
        )
        remaining -= 1
    return commands


def validate_snat_pool_runtime_commands(pool):
    nat_temp_chain = f"{SNAT_POOL_CHAIN}{TEMP_CHAIN_SUFFIX}"
    mark_temp_chain = f"{SNAT_MARK_CHAIN}{TEMP_CHAIN_SUFFIX}"
    delete_chain_if_exists(nat_temp_chain, "nat")
    delete_chain_if_exists(mark_temp_chain, "mangle")
    try:
        run_iptables(["-t", "nat", "-N", nat_temp_chain])
        run_iptables(["-t", "mangle", "-N", mark_temp_chain])
        for command in snat_pool_nat_commands(pool, nat_temp_chain):
            run_iptables(command)
        for command in snat_pool_mark_commands(pool, mark_temp_chain):
            run_iptables(command)
    finally:
        delete_chain_if_exists(nat_temp_chain, "nat")
        delete_chain_if_exists(mark_temp_chain, "mangle")


def clear_snat_pool_policy_routes():
    for index in range(SNAT_POOL_MAX_SOURCES):
        mark = hex(snat_pool_mark(index))
        table = str(snat_pool_table(index))
        priority = str(snat_pool_priority(index))
        while True:
            result = run_ip(
                ["rule", "del", "fwmark", mark, "table", table, "priority", priority],
                check=False,
            )
            if result.returncode != 0:
                break
        run_ip(["route", "flush", "table", table], check=False)


def configure_snat_pool_policy_routes(pool):
    try:
        for source in snat_pool_sources(pool):
            run_ip(
                [
                    "route",
                    "replace",
                    "default",
                    "via",
                    source["virtual_router_ip"],
                    "dev",
                    source["interface"],
                    "table",
                    str(source["table"]),
                ]
            )
            run_ip(
                [
                    "rule",
                    "add",
                    "fwmark",
                    source["mark_hex"],
                    "table",
                    str(source["table"]),
                    "priority",
                    str(source["priority"]),
                ]
            )
    except RuntimeError:
        clear_snat_pool_policy_routes()
        raise


def write_proc_value(path, value):
    try:
        with open(path, "w", encoding="utf-8") as proc_file:
            proc_file.write(str(value))
    except OSError as exc:
        raise RuntimeError(f"Unable to write {path}: {exc}") from exc


def configure_snat_pool_sysctls(pool):
    write_proc_value("/proc/sys/net/ipv4/ip_forward", "1")
    for name in ("all", "default", *[source["interface"] for source in snat_pool_sources(pool)]):
        path = f"/proc/sys/net/ipv4/conf/{name}/rp_filter"
        if os.path.exists(path):
            write_proc_value(path, "0")


def clear_snat_pool_runtime():
    ensure_managed_chains()
    remove_jump(MANAGED_SNAT_CHAIN, SNAT_POOL_CHAIN, "nat")
    remove_jump("PREROUTING", SNAT_MARK_CHAIN, "mangle")
    delete_chain_if_exists(SNAT_POOL_CHAIN, "nat")
    delete_chain_if_exists(SNAT_MARK_CHAIN, "mangle")
    clear_snat_pool_policy_routes()


def apply_snat_pool(pool):
    if not pool["enabled"]:
        clear_snat_pool_runtime()
        save_file_config(
            {
                "ONA_SNAT_POOL_ENABLED": "false",
                "ONA_SNAT_POOL_IPS": ",".join(pool["source_ips"]),
                "ONA_SNAT_POOL_INTERFACE": pool["interface"],
            }
        )
        return

    pool = dict(pool)
    pool["sources"] = snat_pool_sources(pool)
    validate_snat_pool_runtime_commands(pool)
    runtime_cleared = False
    try:
        clear_snat_pool_runtime()
        runtime_cleared = True
        configure_snat_pool_sysctls(pool)
        configure_snat_pool_policy_routes(pool)
        ensure_snat_pool_chains()
        run_iptables(["-t", "nat", "-F", SNAT_POOL_CHAIN])
        run_iptables(["-t", "mangle", "-F", SNAT_MARK_CHAIN])
        for command in snat_pool_mark_commands(pool, SNAT_MARK_CHAIN):
            run_iptables(command)
        for command in snat_pool_nat_commands(pool, SNAT_POOL_CHAIN):
            run_iptables(command)
    except Exception:
        if runtime_cleared:
            try:
                clear_snat_pool_runtime()
            except Exception:
                app.logger.exception("Unable to clean up partial SNAT pool runtime state")
            save_file_config(
                {
                    "ONA_SNAT_POOL_ENABLED": "false",
                    "ONA_SNAT_POOL_IPS": ",".join(pool["source_ips"]),
                    "ONA_SNAT_POOL_INTERFACE": pool["interface"],
                }
            )
        raise

    save_file_config(
        {
            "ONA_SNAT_POOL_ENABLED": "true",
            "ONA_SNAT_POOL_IPS": ",".join(pool["source_ips"]),
            "ONA_SNAT_POOL_INTERFACE": pool["interface"],
        }
    )


def estimated_snat_capacity():
    pool = snat_pool_policy()
    source_count = len(pool["source_ips"]) if pool["enabled"] else 1
    port_capacity = read_port_capacity()
    return {
        "source_ip_count": max(1, source_count),
        "total_available_ports": port_capacity["tcp_udp_total"] * max(1, source_count),
        "per_ip_ports": port_capacity["tcp_udp_total"],
    }


def read_cpu_sample():
    try:
        with open("/proc/stat", "r", encoding="utf-8") as stat_file:
            fields = stat_file.readline().split()
    except OSError:
        return None

    if not fields or fields[0] != "cpu":
        return None
    values = [int(value) for value in fields[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return {"total": sum(values), "idle": idle, "timestamp": time.time()}


def cpu_metrics():
    global _last_cpu_sample
    current = read_cpu_sample()
    if current is None:
        return {"percent": None, "load_average": []}

    percent = None
    with _metrics_lock:
        previous = _last_cpu_sample
        _last_cpu_sample = current

    if previous:
        total_delta = current["total"] - previous["total"]
        idle_delta = current["idle"] - previous["idle"]
        if total_delta > 0:
            percent = round(max(0, min(100, (1 - idle_delta / total_delta) * 100)), 1)

    try:
        load_average = [round(value, 2) for value in os.getloadavg()]
    except OSError:
        load_average = []

    return {"percent": percent, "load_average": load_average}


def memory_metrics():
    meminfo = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as meminfo_file:
            for line in meminfo_file:
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return {"total_bytes": 0, "available_bytes": 0, "used_bytes": 0, "percent": None}

    total = meminfo.get("MemTotal", 0)
    available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    used = max(0, total - available)
    percent = round((used / total) * 100, 1) if total else None
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "percent": percent,
    }


def network_sample():
    interfaces = []
    totals = {
        "rx_bytes": 0,
        "tx_bytes": 0,
        "rx_packets": 0,
        "tx_packets": 0,
    }

    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as net_file:
            rows = net_file.readlines()[2:]
    except OSError:
        rows = []

    for row in rows:
        if ":" not in row:
            continue
        name, values = row.split(":", 1)
        interface = name.strip()
        if interface == "lo":
            continue
        fields = values.split()
        if len(fields) < 16:
            continue
        stats = {
            "interface": interface,
            "rx_bytes": int(fields[0]),
            "rx_packets": int(fields[1]),
            "tx_bytes": int(fields[8]),
            "tx_packets": int(fields[9]),
        }
        interfaces.append(stats)
        for key in totals:
            totals[key] += stats[key]

    return {"timestamp": time.time(), "interfaces": interfaces, "totals": totals}


def network_metrics():
    global _last_network_sample
    current = network_sample()
    rates = {
        "rx_bytes_per_second": 0,
        "tx_bytes_per_second": 0,
        "total_bytes_per_second": 0,
        "rx_packets_per_second": 0,
        "tx_packets_per_second": 0,
        "total_packets_per_second": 0,
    }

    with _metrics_lock:
        previous = _last_network_sample
        _last_network_sample = current

    if previous:
        elapsed = max(0.001, current["timestamp"] - previous["timestamp"])
        for direction in ("rx", "tx"):
            byte_delta = current["totals"][f"{direction}_bytes"] - previous["totals"][f"{direction}_bytes"]
            packet_delta = current["totals"][f"{direction}_packets"] - previous["totals"][f"{direction}_packets"]
            rates[f"{direction}_bytes_per_second"] = round(max(0, byte_delta) / elapsed, 1)
            rates[f"{direction}_packets_per_second"] = round(max(0, packet_delta) / elapsed, 1)
        rates["total_bytes_per_second"] = round(
            rates["rx_bytes_per_second"] + rates["tx_bytes_per_second"], 1
        )
        rates["total_packets_per_second"] = round(
            rates["rx_packets_per_second"] + rates["tx_packets_per_second"], 1
        )

    return {
        "interfaces": current["interfaces"],
        "totals": current["totals"],
        "rates": rates,
    }


def read_port_capacity():
    try:
        with open("/proc/sys/net/ipv4/ip_local_port_range", "r", encoding="utf-8") as range_file:
            start, end = [int(value) for value in range_file.read().split()[:2]]
    except (OSError, ValueError, IndexError):
        start, end = 32768, 60999

    per_protocol = max(0, end - start + 1)
    return {
        "range_start": start,
        "range_end": end,
        "per_protocol": per_protocol,
        "tcp_udp_total": per_protocol * 2,
    }


def conntrack_paths():
    return ("/proc/net/nf_conntrack", "/proc/net/ip_conntrack")


def parse_conntrack_lines():
    for path in conntrack_paths():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as conntrack_file:
                return conntrack_file.readlines()
        except OSError:
            continue
    return []


def conntrack_metrics():
    global _last_conntrack_sample

    total_connections = read_first_int("/proc/sys/net/netfilter/nf_conntrack_count")
    max_connections = read_first_int("/proc/sys/net/netfilter/nf_conntrack_max")
    protocol_counts = {}
    ports_by_protocol = {"tcp": set(), "udp": set()}
    lines = parse_conntrack_lines()

    if lines:
        total_connections = len(lines)
        for line in lines:
            fields = line.split()
            protocol = fields[2].lower() if len(fields) > 2 else "unknown"
            protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
            if protocol in ports_by_protocol:
                for token in fields:
                    if token.startswith("sport="):
                        port = token.split("=", 1)[1]
                        if port.isdigit():
                            ports_by_protocol[protocol].add(port)

    now = time.time()
    connections_per_second = 0
    with _metrics_lock:
        previous = _last_conntrack_sample
        _last_conntrack_sample = {"timestamp": now, "total": total_connections}

    if previous:
        elapsed = max(0.001, now - previous["timestamp"])
        delta = max(0, total_connections - previous["total"])
        connections_per_second = round(delta / elapsed, 2)

    port_capacity = read_port_capacity()
    pool = snat_pool_policy()
    source_ip_count = len(pool["source_ips"]) if pool["enabled"] else 1
    source_ip_count = max(1, source_ip_count)
    ports_in_use_by_protocol = {
        protocol: len(ports)
        for protocol, ports in ports_by_protocol.items()
    }
    ports_in_use = sum(ports_in_use_by_protocol.values())
    total_available_ports = port_capacity["tcp_udp_total"] * source_ip_count
    utilization = round((ports_in_use / total_available_ports) * 100, 2) if total_available_ports else 0
    connection_utilization = (
        round((total_connections / max_connections) * 100, 2)
        if max_connections
        else 0
    )

    return {
        "total_connections": total_connections,
        "max_connections": max_connections,
        "connection_utilization_percent": connection_utilization,
        "connections_per_second": connections_per_second,
        "protocol_counts": protocol_counts,
        "ports_in_use": ports_in_use,
        "ports_in_use_by_protocol": ports_in_use_by_protocol,
        "snat_source_ip_count": source_ip_count,
        "total_available_ports": total_available_ports,
        "available_ports": max(0, total_available_ports - ports_in_use),
        "port_utilization_percent": utilization,
        "ephemeral_port_range": {
            "start": port_capacity["range_start"],
            "end": port_capacity["range_end"],
            "per_protocol": port_capacity["per_protocol"],
        },
    }


def rule_count_metrics():
    try:
        dnat_rules, snat_rules = process_nat_rules(get_nat_rules())
        return {"dnat": len(dnat_rules), "snat": len(snat_rules), "total": len(dnat_rules) + len(snat_rules)}
    except RuntimeError as exc:
        return {"dnat": 0, "snat": 0, "total": 0, "error": str(exc)}


def normalize_dashboard_sample(sample):
    if not isinstance(sample, dict):
        return None

    try:
        epoch = float(sample.get("epoch"))
    except (TypeError, ValueError):
        return None

    if not math.isfinite(epoch):
        return None

    normalized = dict(sample)
    normalized["epoch"] = epoch
    if not isinstance(normalized.get("timestamp"), str) or not normalized["timestamp"]:
        normalized["timestamp"] = (
            datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")
        )
    return normalized


def trim_dashboard_samples(samples, now=None):
    if now is None:
        now = time.time()
    cutoff = float(now) - _dashboard_history_retention_seconds
    trimmed = []

    for sample in samples:
        normalized = normalize_dashboard_sample(sample)
        if normalized and normalized["epoch"] >= cutoff:
            trimmed.append(normalized)

    trimmed.sort(key=lambda sample: sample["epoch"])
    return trimmed[-_dashboard_history_max_samples:]


def load_dashboard_history_file():
    path = dashboard_history_file_path()
    try:
        with open(path, "r", encoding="utf-8") as history_file:
            data = json.load(history_file)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        app.logger.warning("Unable to read dashboard history file %s: %s", path, exc)
        return []

    if isinstance(data, dict):
        samples = data.get("samples", [])
    elif isinstance(data, list):
        samples = data
    else:
        app.logger.warning("Dashboard history file %s did not contain a sample list.", path)
        return []

    if not isinstance(samples, list):
        app.logger.warning("Dashboard history file %s did not contain a sample list.", path)
        return []

    return trim_dashboard_samples(samples)


def write_dashboard_history_file(samples):
    path = dashboard_history_file_path()
    try:
        serialized = json.dumps({"samples": samples}, indent=2) + "\n"
    except (TypeError, ValueError) as exc:
        app.logger.warning("Unable to serialize dashboard history for %s: %s", path, exc)
        return

    directory = os.path.dirname(path)
    try:
        if directory:
            os.makedirs(directory, exist_ok=True)

        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as history_file:
            history_file.write(serialized)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    except OSError as exc:
        app.logger.warning("Unable to write dashboard history file %s: %s", path, exc)


def ensure_dashboard_history_loaded_locked():
    global _dashboard_history, _dashboard_history_loaded

    if not _dashboard_history_loaded:
        _dashboard_history = load_dashboard_history_file()
        _dashboard_history_loaded = True


def record_dashboard_sample(sample):
    global _dashboard_history

    with _dashboard_history_lock:
        ensure_dashboard_history_loaded_locked()
        normalized = normalize_dashboard_sample(sample)
        if not normalized:
            return

        _dashboard_history.append(normalized)
        _dashboard_history = trim_dashboard_samples(
            _dashboard_history, now=normalized["epoch"]
        )
        write_dashboard_history_file(_dashboard_history)


def dashboard_metrics(record=True):
    now = time.time()
    sample = {
        "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z"),
        "epoch": now,
        "cpu": cpu_metrics(),
        "memory": memory_metrics(),
        "nat": conntrack_metrics(),
        "network": network_metrics(),
        "rules": rule_count_metrics(),
    }
    if record:
        record_dashboard_sample(sample)
    return sample


def dashboard_history(range_seconds):
    now = time.time()
    cutoff = now - range_seconds
    with _dashboard_history_lock:
        ensure_dashboard_history_loaded_locked()
        return [
            sample for sample in _dashboard_history if sample.get("epoch", 0) >= cutoff
        ]


def provider_metadata():
    config = get_config()
    issuer = config["ORACLE_IDCS_URL"]
    cached = _provider_cache.get(issuer)
    if cached and cached["expires_at"] > time.time():
        return cached["metadata"]

    metadata_url = f"{issuer}/.well-known/openid-configuration"
    metadata = {}
    try:
        response = requests.get(metadata_url, timeout=5)
        if response.ok:
            metadata = response.json()
    except (requests.RequestException, ValueError) as exc:
        app.logger.warning("Unable to read OIDC metadata from %s: %s", metadata_url, exc)
    if not isinstance(metadata, dict):
        metadata = {}

    metadata = {
        "issuer": metadata.get("issuer", issuer),
        "authorization_endpoint": metadata.get(
            "authorization_endpoint", f"{issuer}/oauth2/v1/authorize"
        ),
        "token_endpoint": metadata.get("token_endpoint", f"{issuer}/oauth2/v1/token"),
        "jwks_uri": config.get("ORACLE_JWKS_URL")
        or metadata.get("jwks_uri")
        or f"{issuer}/admin/v1/SigningCert/jwk",
    }
    _provider_cache[issuer] = {"metadata": metadata, "expires_at": time.time() + 300}
    return metadata


def fetch_jwks(jwks_uri):
    cached = _jwks_cache.get(jwks_uri)
    if cached and cached["expires_at"] > time.time():
        return cached["jwks"]

    response = requests.get(jwks_uri, timeout=5)
    response.raise_for_status()
    jwks = response.json()
    if not isinstance(jwks, dict) or "keys" not in jwks:
        raise InvalidTokenError("OIDC JWKS response did not contain signing keys.")
    _jwks_cache[jwks_uri] = {"jwks": jwks, "expires_at": time.time() + 300}
    return jwks


def signing_key_for_token(token, jwks_uri):
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")
    key_id = header.get("kid")
    if algorithm not in ALLOWED_JWT_ALGORITHMS:
        raise InvalidTokenError("OIDC token used an unsupported signing algorithm.")
    if not key_id:
        raise InvalidTokenError("OIDC token did not include a key id.")

    for jwk in fetch_jwks(jwks_uri).get("keys", []):
        if jwk.get("kid") == key_id:
            return jwt.PyJWK.from_dict(jwk).key
    raise InvalidTokenError("OIDC signing key was not found.")


def verify_oidc_token(token):
    config = get_config()
    metadata = provider_metadata()
    signing_key = signing_key_for_token(token, metadata["jwks_uri"])
    return jwt.decode(
        token,
        signing_key,
        algorithms=list(ALLOWED_JWT_ALGORITHMS),
        audience=config["ORACLE_CLIENT_ID"],
        issuer=metadata["issuer"],
        leeway=60,
    )


def display_name_from_claims(claims):
    return (
        claims.get("name")
        or claims.get("user_displayname")
        or claims.get("preferred_username")
        or claims.get("sub")
    )


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_configured():
            return redirect(url_for("setup"))

        id_token = session.get("id_token")
        if not id_token:
            return make_response(redirect(url_for("login")))

        try:
            claims = verify_oidc_token(id_token)
        except Exception:
            app.logger.exception("OIDC token verification failed")
            session.clear()
            return make_response(redirect(url_for("login")))

        return f(display_name_from_claims(claims), *args, **kwargs)

    return decorated


def external_url(path):
    base = get_config().get("ADDRESS") or request.url_root.rstrip("/")
    return f"{base.rstrip('/')}{path}"


@app.route("/", methods=["GET", "POST"])
@token_required
def dnoa(current_user):
    if request.method == "GET":
        try:
            nat_rules = process_nat_rules(get_nat_rules())
        except RuntimeError as exc:
            app.logger.exception("Unable to read iptables rules")
            return make_response(str(exc), 500)
        return render_template(
            "bootstrap_table.html",
            title="Oracle NAT Appliance",
            current_user=current_user,
            dnat_rules=nat_rules[0],
            snat_rules=nat_rules[1],
        )

    try:
        require_csrf_token()
        data = request.get_json(silent=True)
        if data is None:
            raise RuleValidationError("Expected JSON request body.")
        nat_rules = process_nat_rules(load_post_routing(data))
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        app.logger.exception("Unable to update iptables rules")
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "message": "Submit successful",
            "dnat_rules": nat_rules[0],
            "snat_rules": nat_rules[1],
        }
    )


def backup_api_exception_response(exc, status_code=502):
    app.logger.exception("Backup API request failed")
    return jsonify({"error": str(exc)}), status_code


def bucket_query_overrides():
    return {
        "OCI_AUTH_METHOD": "instance_principal",
        "OCI_REGION": request.args.get("region", ""),
        "OCI_COMPARTMENT_ID": request.args.get("compartment_id", ""),
        "OCI_NAMESPACE": request.args.get("namespace", ""),
    }


@app.route("/api/oci/buckets")
@token_required
def api_oci_buckets(current_user):
    try:
        return jsonify(list_oci_buckets(bucket_query_overrides()))
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except BackupError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return backup_api_exception_response(exc)


@app.route("/api/backups/status")
@token_required
def api_backups_status(current_user):
    policy = backup_policy()
    backups = []
    error = ""
    if policy["bucket"]:
        try:
            backups = list_backup_objects(policy)
        except Exception as exc:
            app.logger.exception("Unable to list backup objects")
            error = str(exc)

    return jsonify(
        {
            "policy": public_backup_policy(policy),
            "backups": backups,
            "error": error,
            "weekdays": [{"value": str(index), "label": day} for index, day in enumerate(WEEKDAYS)],
        }
    )


@app.route("/api/vnics/status")
@token_required
def api_vnics_status(current_user):
    return jsonify(
        {
            "scan": vnic_scan_state(),
            "snat_pool": snat_pool_policy(),
            "capacity": estimated_snat_capacity(),
        }
    )


@app.route("/api/vnics/rescan", methods=["POST"])
@token_required
def api_vnics_rescan(current_user):
    try:
        require_csrf_token()
        scan = scan_vnics()
        return jsonify(
            {
                "scan": scan,
                "snat_pool": snat_pool_policy(),
                "capacity": estimated_snat_capacity(),
            }
        )
    except VnicScanError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        app.logger.exception("VNIC scan failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/vnics/configure", methods=["POST"])
@token_required
def api_vnics_configure(current_user):
    try:
        require_csrf_token()
        result = configure_vnic_interfaces()
        return jsonify(
            {
                "scan": result["scan"],
                "configuration": result["configuration"],
                "snat_pool": snat_pool_policy(),
                "capacity": estimated_snat_capacity(),
            }
        )
    except VnicScanError as exc:
        return jsonify({"error": str(exc)}), 502
    except RuntimeError as exc:
        app.logger.exception("VNIC configuration failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/vnics/snat-pool", methods=["POST"])
@token_required
def api_vnics_snat_pool(current_user):
    try:
        require_csrf_token()
        data = request.get_json(silent=True)
        if data is None:
            raise RuleValidationError("Expected JSON request body.")
        configuration = {
            "scan": vnic_scan_state(),
            "configuration": {
                "method": "none",
                "results": [],
                "errors": [],
                "configured_count": 0,
                "configured_ips": [],
            },
        }
        if parse_bool(data.get("enabled", False), "SNAT pool enabled"):
            configuration = configure_vnic_interfaces()
        pool = validate_snat_pool_payload(data)
        apply_snat_pool(pool)
        nat_rules = process_nat_rules(get_nat_rules())
        return jsonify(
            {
                "scan": vnic_scan_state(),
                "configuration": configuration["configuration"],
                "snat_pool": snat_pool_policy(),
                "capacity": estimated_snat_capacity(),
                "dnat_rules": nat_rules[0],
                "snat_rules": nat_rules[1],
            }
        )
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except VnicScanError as exc:
        return jsonify({"error": str(exc)}), 502
    except RuntimeError as exc:
        app.logger.exception("SNAT pool update failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/dashboard/stats")
@token_required
def api_dashboard_stats(current_user):
    return jsonify(dashboard_metrics())


@app.route("/api/dashboard/history")
@token_required
def api_dashboard_history(current_user):
    try:
        range_seconds = int(request.args.get("range", "3600"))
    except ValueError:
        range_seconds = 3600
    range_seconds = max(60, min(_dashboard_history_retention_seconds, range_seconds))
    samples = dashboard_history(range_seconds)
    if not samples:
        samples = [dashboard_metrics()]
    return jsonify({"range_seconds": range_seconds, "samples": samples})


@app.route("/api/dashboard/stream")
@token_required
def api_dashboard_stream(current_user):
    @stream_with_context
    def events():
        while True:
            yield f"data: {json.dumps(dashboard_metrics())}\n\n"
            time.sleep(30)

    response = Response(events(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/api/backups/policy", methods=["POST"])
@token_required
def api_save_backup_policy(current_user):
    try:
        require_csrf_token()
        data = request.get_json(silent=True)
        if data is None:
            raise RuleValidationError("Expected JSON request body.")
        updates = validate_backup_policy_payload(data)
        save_file_config(updates)
        return jsonify({"policy": public_backup_policy(backup_policy(updates)), "message": "Backup policy saved."})
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return backup_api_exception_response(exc)


@app.route("/api/backups/run", methods=["POST"])
@token_required
def api_run_backup(current_user):
    try:
        require_csrf_token()
        return jsonify({"backup": create_backup_object(reason="manual")})
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except BackupError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return backup_api_exception_response(exc)


@app.route("/api/backups/restore", methods=["POST"])
@token_required
def api_restore_backup(current_user):
    try:
        require_csrf_token()
        data = request.get_json(silent=True) or {}
        object_name = data.get("object_name", "")
        restored = restore_backup_object(object_name)
        nat_rules = process_nat_rules(get_nat_rules())
        return jsonify(
            {
                "restore": restored,
                "dnat_rules": nat_rules[0],
                "snat_rules": nat_rules[1],
            }
        )
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except BackupError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return backup_api_exception_response(exc)


@app.route("/api/backups/delete", methods=["POST"])
@token_required
def api_delete_backup(current_user):
    try:
        require_csrf_token()
        data = request.get_json(silent=True) or {}
        object_name = data.get("object_name", "")
        return jsonify({"delete": delete_backup_object(object_name)})
    except RuleValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except BackupError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return backup_api_exception_response(exc)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if is_configured():
        return redirect(url_for("dnoa"))

    if request.method == "POST":
        try:
            require_csrf_token()
            save_file_config(validate_setup_form(request.form))
        except RuleValidationError as exc:
            flash(str(exc))
            return render_template("setup_form.html"), 400

        flash("Configuration saved successfully.")
        return redirect(url_for("login"))

    return render_template("setup_form.html")


@app.route("/login")
def login():
    if not is_configured():
        return redirect(url_for("setup"))

    config = get_config()
    metadata = provider_metadata()
    client = WebApplicationClient(config["ORACLE_CLIENT_ID"])
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    request_uri = client.prepare_request_uri(
        metadata["authorization_endpoint"],
        redirect_uri=external_url("/login/callback"),
        state=state,
        scope=["openid", "profile"],
    )
    return redirect(request_uri)


@app.route("/login/callback")
def callback():
    if not is_configured():
        return redirect(url_for("setup"))

    expected_state = session.pop("oauth_state", None)
    supplied_state = request.args.get("state")
    if not expected_state or not supplied_state or not hmac.compare_digest(
        expected_state, supplied_state
    ):
        abort(400, description="Invalid OAuth state.")

    code = request.args.get("code")
    if not code:
        abort(400, description="Missing OAuth authorization code.")

    config = get_config()
    metadata = provider_metadata()
    client = WebApplicationClient(config["ORACLE_CLIENT_ID"])
    token_url, headers, body = client.prepare_token_request(
        metadata["token_endpoint"],
        authorization_response=request.url,
        redirect_url=external_url("/login/callback"),
        code=code,
    )
    try:
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=(config["ORACLE_CLIENT_ID"], config["ORACLE_IDCS_SECRET"]),
            timeout=10,
        )
        token_response.raise_for_status()
        token = client.parse_request_body_response(json.dumps(token_response.json()))
        id_token = token.get("id_token")
        if not id_token:
            abort(502, description="OIDC provider did not return an ID token.")
        verify_oidc_token(id_token)
    except requests.RequestException as exc:
        app.logger.exception("OIDC token request failed")
        abort(502, description=f"OIDC token request failed: {exc}")
    except (ValueError, InvalidTokenError) as exc:
        app.logger.exception("OIDC token validation failed")
        abort(502, description=f"OIDC token validation failed: {exc}")

    session["id_token"] = id_token
    session.pop("_csrf_token", None)
    return make_response(redirect(url_for("dnoa")))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


apply_app_secret()
start_backup_scheduler_once()


if __name__ == "__main__":
    app.run(host="0.0.0.0")
