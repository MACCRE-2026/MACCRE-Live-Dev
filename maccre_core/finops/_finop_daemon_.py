import logging

from datetime import datetime, timezone
import threading
import time

from maccre_core.finops.sqlite_ledger import SQLiteFinOpsLedger
from maccre_core.utils.path_resolver import get_datacenter_path

logger = logging.getLogger("maccre_core.finops")

class FinOpDaemon:
    """
    Watchdog service for intercepting token consumption and cloud-API calls.
    Provides budgetary projections and performs background health metric polling (AUA Interrupt).
    """

    def __init__(self):
        self.ledger = SQLiteFinOpsLedger()
        self._bg_thread = None
        self._bg_stop_event = threading.Event()

    def record_transaction(
        self,
        project_name: str,
        session_id: str,
        node_type: str,
        agent_name: str,
        tool_name: str,
        model_name: str,
        media_type: str,
        cost_usd: float,
        canonization_status: str = "uncanonized"
    ) -> None:
        """
        Record a granular transaction in the ledger.
        """
        self.ledger.record_cost(
            project_name=project_name,
            session_id=session_id,
            node_type=node_type,
            agent_name=agent_name,
            tool_name=tool_name,
            model_name=model_name,
            media_type=media_type,
            cost_usd=cost_usd,
            canonization_status=canonization_status
        )

    def calculate_topology_projection(self, remaining_nodes: int, node_history_average: float) -> float:
        """
        Estimate the cost of the remaining topology.
        """
        return remaining_nodes * node_history_average

    def log_budget_approval(self, project_name: str, session_id: str, projected_cost: float) -> None:
        """
        Log that a CTRL_REVIEW projection was approved.
        """
        now = datetime.now(timezone.utc).isoformat()
        self.ledger.record_budget_projection(project_name, session_id, projected_cost, now)
        logger.info(f"Budget of ${projected_cost:.4f} approved for {project_name}/{session_id}")

    def refresh_project_health_metrics(self, project_name: str) -> None:
        """
        AUA Interrupt: Scans project stats and updates health metrics.
        This calculates canonization ratios, fail rates, and 04 vs 05 storage sizes.
        """
        try:
            # 1. Fetch failure rates & canonization from DB
            entries = self.ledger.get_ledger_entries({"project_name": project_name})
            
            # Simple dummy calculations for now, would aggregate actual session states
            total_sessions = len(set(e["session_id"] for e in entries))
            failed_sessions = 0 # Need failure tracking logic
            canonized_sessions = len(set(e["session_id"] for e in entries if e.get("canonization_status") == "canonized"))
            
            fail_rate = (failed_sessions / total_sessions) if total_sessions > 0 else 0.0
            canonization_ratio = (canonized_sessions / total_sessions) if total_sessions > 0 else 0.0
            
            # 2. Filesystem walk for sizes
            dc_path = get_datacenter_path(project_name)
            dir_04 = dc_path / "04_Code_Artifacts"
            dir_05 = dc_path / "05_Rendered_Media"
            
            size_04 = sum(f.stat().st_size for f in dir_04.glob('**/*') if f.is_file()) if dir_04.exists() else 0
            size_05 = sum(f.stat().st_size for f in dir_05.glob('**/*') if f.is_file()) if dir_05.exists() else 0
            
            size_ratio = (size_04 / size_05) if size_05 > 0 else float(size_04)
            
            # 3. Update DB
            self.ledger.update_health_metrics(project_name, fail_rate, canonization_ratio, size_ratio)
            
        except Exception as e:
            logger.error(f"Failed to refresh health metrics for {project_name}: {e}")

    def start_background_polling(self, project_name: str, interval_seconds: int = 300) -> None:
        """
        Starts the daemon background thread to poll metrics.
        """
        if self._bg_thread and self._bg_thread.is_alive():
            return
            
        self._bg_stop_event.clear()
        
        def poll_loop():
            while not self._bg_stop_event.is_set():
                self.refresh_project_health_metrics(project_name)
                # Sleep in short increments to allow quick exit
                for _ in range(interval_seconds):
                    if self._bg_stop_event.is_set():
                        break
                    time.sleep(1)
                    
        self._bg_thread = threading.Thread(target=poll_loop, daemon=True)
        self._bg_thread.start()

    def stop_background_polling(self) -> None:
        """
        Stops the daemon background thread.
        """
        self._bg_stop_event.set()
        if self._bg_thread:
            self._bg_thread.join(timeout=2.0)

# Global singleton instance
_daemon_instance = None

def get_finop_daemon() -> FinOpDaemon:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = FinOpDaemon()
    return _daemon_instance
