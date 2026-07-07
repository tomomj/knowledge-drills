"""Eval entry module exposing the standalone drill generator agent as root_agent.

`adk eval` / AgentEvaluator discover agents through the root_agent convention.
Uses the parent-less factory to avoid AutoFlow transfer pollution.
"""

from knowledge_drill_agent.agent import create_drill_generator_agent

root_agent = create_drill_generator_agent()
