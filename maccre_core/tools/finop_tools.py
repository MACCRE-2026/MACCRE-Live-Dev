from typing import Dict, Any, List
import json

from maccre_core.finops._finop_daemon_ import get_finop_daemon

def get_project_health_metrics(project_name: str) -> str:
    """
    Returns the health metrics for a given project.
    Includes failure rate, canonization ratio, and the 04 vs 05 directory storage size ratio.
    """
    daemon = get_finop_daemon()
    metrics = daemon.ledger.get_health_metrics(project_name)
    if not metrics:
        return f"No health metrics found for project {project_name}. Ensure AUA Interrupts have run."
        
    return json.dumps(metrics, indent=2)

def query_finops_ledger(filters: Dict[str, Any]) -> str:
    """
    Queries the granular FinOps ledger with arbitrary filters.
    Available filter keys: project_name, session_id, node_type, agent_name, tool_name, model_name, media_type, canonization_status.
    """
    daemon = get_finop_daemon()
    entries = daemon.ledger.get_ledger_entries(filters)
    if not entries:
        return "No entries matched the provided filters."
        
    return json.dumps(entries, indent=2)

def get_aggregated_cost(project_name: str, session_id: str = None) -> str:
    """
    Retrieves the total aggregated USD cost for a specific project (and optionally a specific session).
    """
    daemon = get_finop_daemon()
    total = daemon.ledger.get_aggregated_costs(project_name, session_id)
    scope = f"Project '{project_name}'"
    if session_id:
        scope += f", Session '{session_id}'"
        
    return f"Total Aggregated Cost for {scope}: ${total:.4f}"
