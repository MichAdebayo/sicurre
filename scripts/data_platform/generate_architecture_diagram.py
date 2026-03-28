from diagrams import Diagram, Cluster, Edge
from diagrams.gcp.compute import Run
from diagrams.gcp.analytics import PubSub
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.client import User
from diagrams.programming.framework import Fastapi, React
from diagrams.generic.blank import Blank
from diagrams.onprem.monitoring import Prometheus, Grafana
from diagrams.saas.chat import Slack

with Diagram(
    "Sicurre Component Architecture (V1)",
    show=False,
    filename="docs/architecture/diagrams/component_architecture",
    direction="TB",
):
    user = User("End User\n(TPE)")
    ops = User("Ops / SRE\n(Incident Response)")

    dashboard = React("Dashboard UI")
    gmail_api = Blank("Gmail API")
    auth = Blank("Better Auth\n(Node.js)")
    db = PostgreSQL("Neon PostgreSQL")
    pubsub = PubSub("Google Pub/Sub\n(Push Topic)")

    with Cluster("Google Cloud Platform (Cloud Run)"):
        api = Fastapi("sicurre-api\n(Core API / Auth Gateway)")
        listener = Run("gmail-listener\n(Pub/Sub Webhook)")
        phishing = Run("phishing-api\n(Model Inference)")

    with Cluster("Monitoring & Incident Response"):
        prom = Prometheus("Prometheus\n(Metrics/Alerts)")
        grafana = Grafana("Grafana\n(Dashboards)")
        alerts = Slack("Slack\n(Alerts Channel)")

    # User flows
    user >> Edge(label="Manages App") >> dashboard
    dashboard >> Edge(label="REST API") >> api

    # Core API flows
    api >> Edge(label="Reads/Writes") >> db
    api >> Edge(label="Validates Session") >> auth

    # Email ingestion flow
    user >> Edge(label="Receives Email") >> gmail_api
    gmail_api >> Edge(label="History ID Change") >> pubsub
    pubsub >> Edge(label="Webhook Push") >> listener

    # Listener flow
    listener >> Edge(label="Fetches Message") >> gmail_api
    listener >> Edge(label="Classification Request") >> phishing
    listener >> Edge(color="darkred", style="bold", label="Moves to Trash") >> gmail_api
    listener >> Edge(label="Logs Threat Record") >> api

    # Monitoring & Telemetry Flow
    metrics_edge = Edge(style="dotted", color="gray", label="Exports Metrics")
    api >> metrics_edge >> prom
    listener >> metrics_edge >> prom
    phishing >> metrics_edge >> prom

    prom >> Edge(label="Visualizes") >> grafana
    prom >> Edge(color="orange", style="dashed", label="Triggers Alerts") >> alerts
    alerts >> Edge(color="red", style="bold", label="Dispatches Incident") >> ops
