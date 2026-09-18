import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

"""
test_workflow.py - Automated Unit & Integration Tests for Project 2 (Brief 2).
Tests all 4 assessment criteria:
1. Three or more nodes with clearly drawn state schema.
2. Conditional edge logic (Reviewer deciding whether to approve, loop, or escalate).
3. Explicit double-rejection handling and escalation behavior.
4. End-to-end execution integrity.
"""

from workflow import build_workflow_graph, route_after_review, WorkflowState


def test_graph_nodes_and_topology():
    """Verifies that the graph contains all required specialized nodes."""
    app = build_workflow_graph()
    graph_nodes = set(app.nodes.keys())
    required_nodes = {"planner", "worker", "reviewer", "finalizer", "escalator"}
    assert required_nodes.issubset(graph_nodes), f"Missing nodes: {required_nodes - graph_nodes}"
    print("[PASS] Graph contains 5 distinct nodes (Planner, Worker, Reviewer, Finalizer, Escalator)")


def test_conditional_edge_routing():
    """Verifies the conditional edge logic under all review outcomes."""
    # Case A: Approved work routes to finalizer
    state_approved = {
        "review_status": "APPROVED",
        "rejection_count": 0,
        "max_rejections": 2
    }
    assert route_after_review(state_approved) == "finalizer"
    print("[PASS] Conditional edge: Approved status routes to 'finalizer'")

    # Case B: First rejection routes back to worker (Loopback edge)
    state_rejected_once = {
        "review_status": "REJECTED",
        "rejection_count": 1,
        "max_rejections": 2
    }
    assert route_after_review(state_rejected_once) == "worker"
    print("[PASS] Conditional edge: First rejection routes back to 'worker' for revision")

    # Case C: Second rejection routes to escalator (Double-rejection budget exhausted)
    state_rejected_twice = {
        "review_status": "REJECTED",
        "rejection_count": 2,
        "max_rejections": 2
    }
    assert route_after_review(state_rejected_twice) == "escalator"
    print("[PASS] Conditional edge: Second rejection (>=2) routes to 'escalator' to halt cycle")


def test_double_rejection_escalator_node():
    """Verifies that the escalator node properly handles a double-rejected state."""
    from workflow import escalator_node
    mock_state = {
        "task": "Build an unachievable infinite memory buffer",
        "plan": "Allocate infinite RAM",
        "draft": "def memory(): return float('inf')",
        "review_feedback": "Memory cannot be infinite. Lacks hardware boundaries.",
        "revision_history": [
            {"iteration": 1, "score": 50, "status": "REJECTED", "critique": "Lacks bounds."},
            {"iteration": 2, "score": 55, "status": "REJECTED", "critique": "Still unbounded."}
        ],
        "rejection_count": 2,
        "max_rejections": 2
    }
    result = escalator_node(mock_state)
    assert result["review_status"] == "ESCALATED"
    assert "rejection" in result["failure_analysis"].lower()
    assert len(result["final_output"]) > 50
    print("[PASS] Escalator node correctly formats post-mortem and unblock report upon double rejection")


def test_end_to_end_execution():
    """Runs a complete task through the multi-agent graph."""
    app = build_workflow_graph()
    initial_state = {
        "task": "Write a Python singleton decorator with thread safety using threading.Lock.",
        "plan": "",
        "draft": "",
        "review_feedback": "",
        "review_status": "PENDING",
        "review_score": 0,
        "rejection_count": 0,
        "max_rejections": 2,
        "revision_history": [],
        "final_output": "",
        "failure_analysis": ""
    }
    result = app.invoke(initial_state)
    assert result["plan"] != ""
    assert result["draft"] != ""
    assert result["review_status"] in ("APPROVED", "ESCALATED")
    assert len(result["final_output"]) > 100
    print(f"[PASS] End-to-end multi-agent execution completed with status: {result['review_status']}")


if __name__ == "__main__":
    print("Running Multi-Agent Workflow Test Suite (Brief 2)...\n")
    test_graph_nodes_and_topology()
    test_conditional_edge_routing()
    test_double_rejection_escalator_node()
    test_end_to_end_execution()
    print("\nALL WORKFLOW TESTS PASSED SUCCESSFULLY!")
