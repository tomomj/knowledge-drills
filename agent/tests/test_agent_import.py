import importlib


def test_agent_package_imports_root_agent() -> None:
    module = importlib.import_module("knowledge_drill_agent.agent")

    assert module.root_agent is not None
