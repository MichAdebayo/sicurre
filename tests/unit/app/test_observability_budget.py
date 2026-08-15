"""Observability free-tier budget contract tests."""

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALLOY_CONFIG = REPOSITORY_ROOT / "deploy/alloy/config.alloy"
PRODUCTION_COMPOSE = REPOSITORY_ROOT / "docker-compose.prod.yml"

# Metric groups the infrastructure dashboards actually consume. Everything else
# cAdvisor can emit is disabled at the source.
RETAINED_CADVISOR_METRIC_GROUPS = {"cpu", "memory", "network", "oom_event"}
DISABLEABLE_CADVISOR_METRIC_GROUPS = {
    "advtcp", "app", "cpu", "cpuLoad", "cpu_topology", "cpuset", "disk", "diskIO",
    "hugetlb", "memory", "memory_numa", "network", "oom_event", "percpu",
    "perf_event", "process", "referenced_memory", "resctrl", "sched", "tcp", "udp",
}
INFRASTRUCTURE_DASHBOARD = (
    REPOSITORY_ROOT / "deploy/grafana/dashboards/sicurre-infrastructure.json"
)
RUNTIME_DASHBOARD = REPOSITORY_ROOT / "deploy/grafana/dashboards/sicurre-runtime-overview.json"
TELEMETRY_DASHBOARD = (
    REPOSITORY_ROOT / "deploy/grafana/dashboards/sicurre-telemetry-pipeline.json"
)
ALERT_RULES = REPOSITORY_ROOT / "deploy/grafana/alerts/sicurre-alerts.json"


def test_cadvisor_metrics_are_scoped_and_allowlisted() -> None:
    """Prevent shared-host and high-cardinality cAdvisor series ingestion."""
    config = ALLOY_CONFIG.read_text(encoding="utf-8")

    assert "prometheus.relabel \"sicurre_containers\"" in config
    assert "container_label_com_docker_compose_project" in config
    assert ";sicurre-prod" in config
    assert "container_network_advance_tcp_stats_total" not in config
    assert 'regex  = "container_label_.*|id|image"' in config


def test_infrastructure_dashboard_uses_retained_container_metrics() -> None:
    """Ensure retained cAdvisor series support explicit operational panels."""
    dashboard = json.loads(INFRASTRUCTURE_DASHBOARD.read_text(encoding="utf-8"))
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }

    assert any("container_cpu_usage_seconds_total" in expr for expr in expressions)
    assert any("container_memory_working_set_bytes" in expr for expr in expressions)
    assert any("container_network_receive_bytes_total" in expr for expr in expressions)


def test_application_error_rate_does_not_retain_a_stale_incident() -> None:
    """Render zero when no current 5xx time series exists."""
    dashboard = json.loads(RUNTIME_DASHBOARD.read_text(encoding="utf-8"))
    panel = next(panel for panel in dashboard["panels"] if panel["title"] == "5xx Error Rate")

    assert panel["targets"][0]["expr"].endswith("or vector(0)")


def test_gateway_error_alert_requires_meaningful_customer_traffic() -> None:
    """Prevent sparse probes and one-off failures from paging operations."""
    alerts = json.loads(ALERT_RULES.read_text(encoding="utf-8"))
    rule = next(rule for rule in alerts["rules"] if rule["uid"] == "sicurre-elevated-5xx")

    assert 'route=~"app|api|auth"' in rule["expression"]
    assert "[15m]" in rule["expression"]
    assert ">= 5" in rule["expression"]
    assert ">= 20" in rule["expression"]
    assert rule["for"] == "10m"


def test_shared_active_series_budget_is_visible_and_alerted() -> None:
    """Keep the shared Grafana free-tier budget observable before exhaustion."""
    dashboard = json.loads(TELEMETRY_DASHBOARD.read_text(encoding="utf-8"))
    alerts = json.loads(ALERT_RULES.read_text(encoding="utf-8"))
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    rules = {rule["uid"]: rule for rule in alerts["rules"]}

    assert "sum(prometheus_remote_write_wal_storage_active_series)" in expressions
    assert "100 * sum(prometheus_remote_write_wal_storage_active_series) / 10000" in expressions
    assert rules["sicurre-series-budget-warning"]["threshold"] == 7000
    assert rules["sicurre-series-budget-critical"]["threshold"] == 8500


def _cadvisor_command() -> list[str]:
    """Return the cAdvisor command arguments from the production Compose file."""
    compose = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
    block = compose.split("\n  cadvisor:\n", maxsplit=1)[1]
    return [
        line.strip().removeprefix("- ")
        for line in block.split("\n    devices:", maxsplit=1)[0].splitlines()
        if line.strip().startswith("- --")
    ]


def test_cadvisor_disables_every_metric_group_the_dashboards_do_not_use() -> None:
    """Bound cardinality at the source, not only in the Alloy relabel filter."""
    disable_flag = next(
        arg for arg in _cadvisor_command() if arg.startswith("--disable_metrics=")
    )
    disabled = set(disable_flag.split("=", maxsplit=1)[1].split(","))

    # Only real cAdvisor metric groups; an invalid value crashloops the container.
    assert disabled <= DISABLEABLE_CADVISOR_METRIC_GROUPS
    assert disabled == DISABLEABLE_CADVISOR_METRIC_GROUPS - RETAINED_CADVISOR_METRIC_GROUPS


def test_cadvisor_reports_docker_containers_only() -> None:
    """Raw system cgroups on the shared host are not Sicurre's to observe."""
    assert "--docker_only=true" in _cadvisor_command()


def test_cadvisor_keeps_the_container_labels_the_alloy_filter_depends_on() -> None:
    """Guard the interlock between the two configuration files.

    The Alloy relabel rule keeps container series by matching the Compose
    project label. Suppressing container labels at the source would make that
    rule match nothing and silently remove every container panel from the
    infrastructure dashboard. It would also save no cardinality, because those
    are labels on existing series and Alloy already drops them before remote
    write. Disabling them is therefore pure downside.
    """
    command = _cadvisor_command()
    assert not any(arg.startswith("--store_container_labels=false") for arg in command)

    alloy = ALLOY_CONFIG.read_text(encoding="utf-8")
    assert "container_label_com_docker_compose_project" in alloy
    assert 'regex  = "container_label_.*|id|image"' in alloy
