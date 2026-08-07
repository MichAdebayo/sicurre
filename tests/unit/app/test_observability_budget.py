"""Observability free-tier budget contract tests."""

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALLOY_CONFIG = REPOSITORY_ROOT / "deploy/alloy/config.alloy"
INFRASTRUCTURE_DASHBOARD = (
    REPOSITORY_ROOT / "deploy/grafana/dashboards/sicurre-infrastructure.json"
)
RUNTIME_DASHBOARD = REPOSITORY_ROOT / "deploy/grafana/dashboards/sicurre-runtime-overview.json"


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
