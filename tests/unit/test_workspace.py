"""验证统一安装包可加载各功能包。"""

from importlib import import_module, metadata

import pytest


@pytest.mark.parametrize("name", ["aurora_core", "aurora_model_adapter", "aurora_bot", "aurora_cli", "aurora_api"])
def test_workspace_packages_import(name):
    assert import_module(name).__name__ == name


def test_unified_distribution_dependencies():
    requirements = metadata.requires("aurorabot-ai")
    assert requirements is not None
    for package in ("aurora-bot", "aurora-cli", "aurora-api"):
        assert any(requirement.startswith(f"{package}>=") for requirement in requirements)
