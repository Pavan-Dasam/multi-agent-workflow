"""
workflow.py - Multi-Agent Workflow using LangGraph.
Meets AgenticX Brief 2 Criteria:
1. Three or more nodes with explicit typed state schema (Planner, Worker, Reviewer, Finalizer, Escalator).
2. At least one conditional feedback edge (Reviewer loops back to Worker).
3. Explicit handling when the reviewer rejects twice (Rejection budget exhaustion & failure analysis).
"""

import os
import re
import json
import time
from typing import TypedDict, List, Dict, Any, Literal
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END

# Explicit State Schema for the Multi-Agent Workflow
class WorkflowState(TypedDict):
    task: str
    plan: str
    draft: str
    review_feedback: str
    review_status: Literal["PENDING", "APPROVED", "REJECTED", "ESCALATED"]
    review_score: int
    rejection_count: int
    max_rejections: int
    revision_history: List[Dict[str, Any]]
    final_output: str
    failure_analysis: str


# Candidate models for fallback resilience
CANDIDATE_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-latest"
]


def invoke_llm_resilient(system_prompt: str, user_prompt: str) -> str:
    """Invokes Gemini with multi-model fallback to handle rate limits/spikes."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    last_err = None
    for model_name in CANDIDATE_MODELS:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                streaming=False,
                max_retries=2
            )
            resp = llm.invoke(messages)
            content = resp.content
            if isinstance(content, list):
                parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        parts.append(p.get("text", ""))
                    elif isinstance(p, str):
                        parts.append(p)
                return "".join(parts)
            return str(content)
        except Exception as e:
            last_err = e
            time.sleep(2)
            continue

    raise last_err or RuntimeError("All model candidates failed.")


# Node 1: Planner Agent
PLANNER_PROMPT = """You are the Lead Architect and Planner Agent.
Your job is to deconstruct the user's technical request into a clear, robust engineering specification.

Analyze the task and provide:
1. Target Architecture & Key Requirements
2. Required Components / Functions / Data Models
3. Concrete Acceptance Criteria & Edge Cases to address

Be precise, structured, and comprehensive. Do not write the full implementation code yet."""

def planner_node(state: WorkflowState) -> Dict[str, Any]:
    task = state["task"]
    plan = invoke_llm_resilient(PLANNER_PROMPT, f"User Task:\n{task}")
    return {
        "plan": plan,
        "review_status": "PENDING"
    }


# Node 2: Worker / Developer Agent
WORKER_PROMPT = """You are the Senior Software Developer / Worker Agent.
Your job is to produce a complete, production-ready technical solution according to the Architect's plan.

If this is a revision (review feedback is present), CAREFULLY address every critique point raised by the Reviewer.

Deliverables:
- Complete, functional Python code (with full error handling, type hints, and docstrings).
- Clear explanation of how the code meets the plan requirements.
- Never use lazy placeholders like `# TODO` or `pass` in core logic."""

def worker_node(state: WorkflowState) -> Dict[str, Any]:
    task = state["task"]
    plan = state["plan"]
    feedback = state.get("review_feedback", "")
    rejection_count = state.get("rejection_count", 0)

    prompt = f"Objective:\n{task}\n\nArchitectural Plan:\n{plan}"
    if feedback and rejection_count > 0:
        prompt += f"\n\nCRITICAL REVIEW FEEDBACK (Revision #{rejection_count}):\n{feedback}\nPlease fix the issues above in your new draft."

    draft = invoke_llm_resilient(WORKER_PROMPT, prompt)
    return {
        "draft": draft
    }


# Node 3: Reviewer / Critic Agent
REVIEWER_PROMPT = """You are the Staff QA & Code Reviewer Agent.
Your job is to rigorously review the Worker's draft against the Architectural Plan and production engineering standards.

EVALUATION CRITERIA:
1. Functional Completeness: Does it solve the entire user request without cutting corners?
2. Code Quality & Typing: Are types, error handling, and modular structure properly implemented?
3. Robustness: Are edge cases handled (e.g., null values, network/IO failures, boundary conditions)?

OUTPUT FORMAT REQUIREMENTS:
You MUST format your output with a JSON block at the very end of your response:
```json
{
  "score": <integer from 0 to 100>,
  "status": "<APPROVED or REJECTED>",
  "critique": "<Specific bullet points on what needs to be fixed, or summary of why it passed>"
}
```
Rule: If score >= 85, set status to APPROVED. If score < 85, set status to REJECTED."""

def reviewer_node(state: WorkflowState) -> Dict[str, Any]:
    plan = state["plan"]
    draft = state["draft"]
    rejection_count = state.get("rejection_count", 0)
    history = list(state.get("revision_history", []))

    review_input = f"Architectural Plan:\n{plan}\n\nWorker's Implementation Draft:\n{draft}"
    review_response = invoke_llm_resilient(REVIEWER_PROMPT, review_input)

    # Parse JSON block
    score = 75
    status = "REJECTED"
    critique = review_response

    json_match = re.search(r"```json\s*(\{.*?\})\s*```", review_response, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            score = int(parsed.get("score", 75))
            status = str(parsed.get("status", "REJECTED")).upper()
            critique = str(parsed.get("critique", review_response))
        except Exception:
            pass
    else:
        # Fallback keyword parsing
        if "APPROVED" in review_response.upper() and "REJECTED" not in review_response.upper():
            status = "APPROVED"
            score = 90

    new_rejections = rejection_count + (1 if status == "REJECTED" else 0)

    history.append({
        "iteration": len(history) + 1,
        "score": score,
        "status": status,
        "critique": critique[:400]
    })

    return {
        "review_score": score,
        "review_status": status,
        "review_feedback": critique,
        "rejection_count": new_rejections,
        "revision_history": history
    }


# Node 4: Finalizer Node (Happy Path)
FINALIZER_PROMPT = """You are the Release Finalizer Agent.
Format the approved technical solution into a polished, executive-ready deliverable with summary, usage guide, and clean code blocks."""

def finalizer_node(state: WorkflowState) -> Dict[str, Any]:
    task = state["task"]
    draft = state["draft"]
    score = state.get("review_score", 90)
    history = state.get("revision_history", [])

    final_input = f"Original Task:\n{task}\n\nApproved Solution (Quality Score {score}/100, passed after {len(history)} review cycles):\n{draft}"
    output = invoke_llm_resilient(FINALIZER_PROMPT, final_input)

    return {
        "final_output": output,
        "failure_analysis": "N/A - Solution successfully approved by reviewer.",
        "review_status": "APPROVED"
    }


# Node 5: Escalator Node (Double-Rejection Fallback)
ESCALATOR_PROMPT = """You are the Engineering Escalation & Post-Mortem Agent.
The automated multi-agent workflow failed to converge because the Reviewer rejected the Worker's draft twice.

Your job is to produce an Engineering Escalation Report:
1. Executive Summary: What was the goal and why did review fail to pass?
2. Root Cause Analysis: Top discrepancies between worker output and reviewer expectations.
3. Best-Effort Artifact: Provide the highest-scoring draft with clear disclaimers on what remains unverified.
4. Actionable Next Steps: What a human developer or architect must do to unblock and ship this."""

def escalator_node(state: WorkflowState) -> Dict[str, Any]:
    task = state["task"]
    plan = state["plan"]
    draft = state["draft"]
    feedback = state.get("review_feedback", "")
    history = state.get("revision_history", [])

    escalation_input = f"Task:\n{task}\n\nArchitect Plan:\n{plan}\n\nLatest Worker Draft:\n{draft}\n\nFinal Rejection Feedback:\n{feedback}\n\nReview History:\n{json.dumps(history, indent=2)}"
    analysis = invoke_llm_resilient(ESCALATOR_PROMPT, escalation_input)

    return {
        "final_output": analysis,
        "failure_analysis": f"Workflow halted after {len(history)} rejections. Rejection budget exhausted. Dispatched to human escalation.",
        "review_status": "ESCALATED"
    }


# Conditional Edge: Route after Reviewer evaluation
def route_after_review(state: WorkflowState) -> Literal["finalizer", "worker", "escalator"]:
    status = state.get("review_status", "REJECTED")
    rejection_count = state.get("rejection_count", 0)
    max_rejections = state.get("max_rejections", 2)

    # 1. If approved, proceed to finalizer
    if status == "APPROVED":
        return "finalizer"

    # 2. If rejected twice or more, halt and escalate
    if rejection_count >= max_rejections:
        return "escalator"

    # 3. Otherwise loop back to worker with critique
    return "worker"


def build_workflow_graph():
    """Builds and compiles the multi-agent LangGraph workflow."""
    workflow = StateGraph(WorkflowState)

    # Add all 5 nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("worker", worker_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("finalizer", finalizer_node)
    workflow.add_node("escalator", escalator_node)

    # Define edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "worker")
    workflow.add_edge("worker", "reviewer")

    # Conditional feedback edge from reviewer
    workflow.add_conditional_edges(
        "reviewer",
        route_after_review,
        {
            "finalizer": "finalizer",
            "worker": "worker",
            "escalator": "escalator"
        }
    )

    # Terminal edges
    workflow.add_edge("finalizer", END)
    workflow.add_edge("escalator", END)

    return workflow.compile()


