from aura.agents.base import CouncilAgent
from aura.agents.orchestrator import Orchestrator
from aura.agents.personas import (
    CFOAgent,
    CTOAgent,
    CustomerAgent,
    HistorianAgent,
    RedTeamAgent,
)
from aura.agents.referee import Referee

__all__ = [
    "CFOAgent",
    "CTOAgent",
    "CouncilAgent",
    "CustomerAgent",
    "HistorianAgent",
    "Orchestrator",
    "RedTeamAgent",
    "Referee",
]


def default_council(*, llm, knowledge):
    """Convenience factory: assemble the five canonical personas."""
    return [
        CFOAgent(llm=llm, knowledge=knowledge),
        CTOAgent(llm=llm, knowledge=knowledge),
        CustomerAgent(llm=llm, knowledge=knowledge),
        RedTeamAgent(llm=llm, knowledge=knowledge),
        HistorianAgent(llm=llm, knowledge=knowledge),
    ]
