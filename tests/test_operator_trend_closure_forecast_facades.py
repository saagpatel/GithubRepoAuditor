from __future__ import annotations

from src.operator_trend_closure_forecast_core import (
    class_closure_forecast_events as facade_class_closure_forecast_events,
)
from src.operator_trend_closure_forecast_events import class_closure_forecast_events
from src.operator_trend_closure_forecast_freshness import closure_forecast_freshness_status
from src.operator_trend_closure_forecast_freshness_controls import (
    closure_forecast_freshness_status as facade_closure_forecast_freshness_status,
)
from src.operator_trend_closure_forecast_reacquisition import (
    apply_closure_forecast_reacquisition_control,
)
from src.operator_trend_closure_forecast_reacquisition_controls import (
    apply_closure_forecast_reacquisition_control as facade_apply_reacquisition_control,
)
from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_refresh_reentry_control as facade_apply_reset_refresh_reentry_control,
)
from src.operator_trend_closure_forecast_reset_refresh import (
    apply_reset_refresh_reentry_control,
)


def test_closure_forecast_facades_preserve_old_import_targets() -> None:
    assert facade_class_closure_forecast_events is class_closure_forecast_events
    assert facade_closure_forecast_freshness_status is closure_forecast_freshness_status
    assert facade_apply_reacquisition_control is apply_closure_forecast_reacquisition_control
    assert facade_apply_reset_refresh_reentry_control is apply_reset_refresh_reentry_control
