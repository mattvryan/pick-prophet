"""Tests for fixed-offset logistic estimator."""

from __future__ import annotations

import numpy as np
import pytest

from pick_prophet.models.fixed_offset_logit import (
    ConvergenceError,
    fit_fixed_offset_logit,
    gradient,
    objective,
    predict_raw,
    sigmoid,
)


def test_zero_beta_reproduces_sigmoid_offset() -> None:
    offset = np.array([-1.0, 0.0, 2.0])
    x = np.zeros((3, 2))
    beta = np.zeros(2)
    p = predict_raw(offset, x, beta)
    np.testing.assert_allclose(p, sigmoid(offset))


def test_empty_features_fit() -> None:
    offset = np.array([0.0, 1.0])
    y = np.array([0.0, 1.0])
    x = np.zeros((2, 0))
    fit = fit_fixed_offset_logit(x, y, offset)
    assert fit.beta.shape == (0,)
    np.testing.assert_allclose(predict_raw(offset, x, fit.beta), sigmoid(offset))


def test_objective_gradient_finite_difference() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(20, 3))
    y = rng.integers(0, 2, size=20).astype(float)
    offset = rng.normal(size=20)
    beta = rng.normal(size=3)
    lam = 1.0
    analytic = gradient(beta, x, y, offset, lam)
    eps = 1e-6
    numeric = np.zeros_like(beta)
    for j in range(len(beta)):
        e = np.zeros_like(beta)
        e[j] = eps
        numeric[j] = (
            objective(beta + e, x, y, offset, lam)
            - objective(beta - e, x, y, offset, lam)
        ) / (2 * eps)
    np.testing.assert_allclose(analytic, numeric, rtol=1e-5, atol=1e-6)


def test_fit_improves_on_signal() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(200, 2))
    true_beta = np.array([1.5, -0.5])
    offset = rng.normal(size=200) * 0.1
    logits = offset + x @ true_beta
    y = (rng.random(200) < sigmoid(logits)).astype(float)
    fit = fit_fixed_offset_logit(x, y, offset, lam=1.0)
    assert fit.success
    assert fit.beta[0] > 0
    assert fit.fun < objective(np.zeros(2), x, y, offset, 1.0)


def test_convergence_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from pick_prophet.models import fixed_offset_logit as mod

    class FakeResult:
        success = False
        message = "forced failure"
        nit = 0
        fun = np.inf
        x = np.zeros(1)

    monkeypatch.setattr(mod, "minimize", lambda *a, **k: FakeResult())
    with pytest.raises(ConvergenceError):
        fit_fixed_offset_logit(
            np.ones((5, 1)), np.array([0, 1, 0, 1, 0], float), np.zeros(5)
        )
