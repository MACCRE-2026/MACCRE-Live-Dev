import abc
from typing import Optional, Dict, Any, List

class AbstractFinOpsLedger(abc.ABC):
    """
    Abstract interface for FinOps ledger storage (Strangler Fig pattern).
    Enables recording of granular AI API costs and retrieving cost telemetry.
    """

    @abc.abstractmethod
    def record_cost(
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
        Record a cost event to the ledger.
        """
        pass

    @abc.abstractmethod
    def get_aggregated_costs(
        self,
        project_name: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> float:
        """
        Retrieve the total aggregated cost, optionally filtered by project or session.
        """
        pass

    @abc.abstractmethod
    def get_ledger_entries(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Retrieve granular ledger entries based on filter criteria.
        """
        pass

    @abc.abstractmethod
    def record_budget_projection(
        self,
        project_name: str,
        session_id: str,
        projected_cost_usd: float,
        timestamp_iso: str
    ) -> None:
        """
        Record an approved CTRL_REVIEW budget projection for future reconciliation auditing.
        """
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """
        Close the underlying connection gracefully.
        """
        pass
