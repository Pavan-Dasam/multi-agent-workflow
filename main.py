import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

"""
main.py - Interactive CLI for LangGraph Multi-Agent Workflow.
Demonstrates:
- 3 specialized nodes: Planner -> Worker -> Reviewer
- Cyclic conditional edge (Reviewer sending work back to Worker)
- Double-rejection handling and escalation
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from workflow import build_workflow_graph


def run_multi_agent_workflow(task_prompt: str, max_rejections: int = 2):
    print("\n" + "="*75)
    print("🚀 INITIATING MULTI-AGENT WORKFLOW (LangGraph)")
    print(f"🎯 Objective: {task_prompt}")
    print(f"🛡️  Rejection Budget: {max_rejections} max rejections before escalation")
    print("="*75 + "\n")

    app = build_workflow_graph()

    initial_state = {
        "task": task_prompt,
        "plan": "",
        "draft": "",
        "review_feedback": "",
        "review_status": "PENDING",
        "review_score": 0,
        "rejection_count": 0,
        "max_rejections": max_rejections,
        "revision_history": [],
        "final_output": "",
        "failure_analysis": ""
    }

    final_state = None
    step_count = 0

    try:
        for output in app.stream(initial_state, stream_mode="updates"):
            for node_name, node_state in output.items():
                step_count += 1
                if node_name == "planner":
                    print(f"📋 [Step {step_count}] PLANNER AGENT: Deconstructed task into specification.")
                    plan_snippet = node_state.get("plan", "")[:180].replace("\n", " ")
                    print(f"   Architecture Outline: {plan_snippet}...\n")

                elif node_name == "worker":
                    print(f"💻 [Step {step_count}] WORKER AGENT: Generated technical implementation draft.")
                    draft_len = len(node_state.get("draft", ""))
                    print(f"   Draft artifact length: {draft_len} characters. Handing over to Reviewer...\n")

                elif node_name == "reviewer":
                    score = node_state.get("review_score", 0)
                    status = node_state.get("review_status", "REJECTED")
                    rejections = node_state.get("rejection_count", 0)
                    print(f"🔍 [Step {step_count}] REVIEWER AGENT: Quality Score = {score}/100 | Status = {status}")
                    print(f"   Rejection Count: {rejections}/{max_rejections}")
                    critique_snippet = node_state.get("review_feedback", "")[:200].replace("\n", " ")
                    print(f"   Reviewer Feedback: {critique_snippet}...")
                    
                    if status == "APPROVED":
                        print("   ✅ APPROVED! Routing to Finalizer node.\n")
                    elif rejections < max_rejections:
                        print("   🔄 REJECTED! Looping back to Worker Agent with critique...\n")
                    else:
                        print("   ⚠️ REJECTED TWICE! Budget exhausted. Escalating to Fallback Node...\n")

                elif node_name == "finalizer":
                    print(f"📦 [Step {step_count}] FINALIZER AGENT: Packaging approved production deliverable.")
                    final_state = node_state

                elif node_name == "escalator":
                    print(f"🚨 [Step {step_count}] ESCALATOR AGENT: Generated failure post-mortem & unblock report.")
                    final_state = node_state

    except KeyboardInterrupt:
        print("\n⚠️ Workflow cancelled by user.")
        return None

    if not final_state or not final_state.get("final_output"):
        final_state = app.invoke(initial_state)

    output_text = final_state.get("final_output", "No output.")
    status = final_state.get("review_status", "UNKNOWN")

    print("\n" + "#"*75)
    print(f"📊 WORKFLOW OUTCOME: [{status}]")
    print("#"*75 + "\n")
    print(output_text)
    print("\n" + "="*75)
    print(f"Workflow completed in {step_count} node transitions.")
    print("="*75)

    # Save deliverable
    os.makedirs("outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() else "_" for c in task_prompt[:25])
    filename = f"outputs/output_{safe_name}_{status}_{timestamp}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Workflow Outcome: {task_prompt}\n\n")
        f.write(f"**Final Status**: `{status}`\n")
        f.write(f"**Timestamp**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(output_text)
    print(f"\n💾 Output saved to: {filename}")

    return final_state


def main():
    print("="*75)
    print("   AGENTICX MULTI-AGENT WORKFLOW - BRIEF 2")
    print("   Planner -> Worker -> Reviewer Loop with Double-Rejection Escalation")
    print("="*75)

    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = input("\nEnter your engineering task (or press Enter for default): ").strip()
        if not task:
            task = "Build a resilient Python rate limiter using the Token Bucket algorithm with thread-safety and sliding window support."

    run_multi_agent_workflow(task)


if __name__ == "__main__":
    main()
