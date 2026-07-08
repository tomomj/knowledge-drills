"""Eval entry module exposing the configured failure analysis agent as root_agent.

`adk eval` / AgentEvaluator discover agents through the root_agent convention.
Uses the parent-less configured factory to avoid AutoFlow transfer pollution.
"""

from knowledge_drill_agent.agent import create_configured_failure_analysis_agent

root_agent = create_configured_failure_analysis_agent()
