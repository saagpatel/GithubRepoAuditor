from __future__ import annotations

import importlib
import inspect
import pkgutil

from src.analyzers import ALL_ANALYZERS
from src.analyzers.base import BaseAnalyzer
from src.scorer import WEIGHTS


def test_scoring_weights_sum_to_one() -> None:
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_scoring_weights_cover_exactly_the_composed_dimensions() -> None:
    expected_scored_dimensions = {
        "readme",
        "structure",
        "code_quality",
        "testing",
        "cicd",
        "dependencies",
        "activity",
        "documentation",
        "build_readiness",
        "community_profile",
    }

    assert set(WEIGHTS) == expected_scored_dimensions
    assert {analyzer.name for analyzer in ALL_ANALYZERS if analyzer.name in WEIGHTS} == set(WEIGHTS)


def test_analyzer_classes_do_not_declare_dead_weight_attributes() -> None:
    import src.analyzers as analyzers_package

    analyzer_classes = [BaseAnalyzer]
    for module_info in pkgutil.iter_modules(analyzers_package.__path__):
        module = importlib.import_module(f"{analyzers_package.__name__}.{module_info.name}")
        analyzer_classes.extend(
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls.__module__ == module.__name__
            and issubclass(cls, BaseAnalyzer)
            and cls is not BaseAnalyzer
        )

    assert all("weight" not in cls.__dict__ for cls in analyzer_classes)
