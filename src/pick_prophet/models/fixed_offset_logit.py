"""Fixed-offset logistic with per-row market logit offset (M08)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


@dataclass(frozen=True)
class FitResult:
    beta: np.ndarray
    success: bool
    nit: int
    fun: float
    message: str
    lam: float


class ConvergenceError(RuntimeError):
    """Raised when L-BFGS-B fails to converge."""


def sigmoid(z: np.ndarray | float) -> np.ndarray | float:
    return expit(z)


def objective(
    beta: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    offset: np.ndarray,
    lam: float,
) -> float:
    eta = offset + x @ beta
    nll = np.mean(np.logaddexp(0.0, eta) - y * eta)
    return float(nll + 0.5 * lam * float(beta @ beta))


def gradient(
    beta: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    offset: np.ndarray,
    lam: float,
) -> np.ndarray:
    eta = offset + x @ beta
    residual = sigmoid(eta) - y
    return (x.T @ residual) / len(y) + lam * beta


def fit_fixed_offset_logit(
    x: np.ndarray,
    y: np.ndarray,
    offset: np.ndarray,
    *,
    lam: float = 1.0,
    max_iter: int = 1000,
    ftol: float = 1e-12,
    gtol: float = 1e-8,
) -> FitResult:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    offset = np.asarray(offset, dtype=float)
    if x.ndim != 2:
        raise ValueError("X must be 2-D")
    n, p = x.shape
    if len(y) != n or len(offset) != n:
        raise ValueError("X, y, offset length mismatch")
    if p == 0:
        return FitResult(
            beta=np.zeros(0, dtype=float),
            success=True,
            nit=0,
            fun=float(objective(np.zeros(0), x, y, offset, lam)),
            message="empty feature matrix",
            lam=lam,
        )

    beta0 = np.zeros(p, dtype=float)

    def fun(beta: np.ndarray) -> float:
        return objective(beta, x, y, offset, lam)

    def jac(beta: np.ndarray) -> np.ndarray:
        return gradient(beta, x, y, offset, lam)

    result = minimize(
        fun,
        beta0,
        method="L-BFGS-B",
        jac=jac,
        options={"maxiter": max_iter, "ftol": ftol, "gtol": gtol},
    )
    if not result.success:
        raise ConvergenceError(
            f"L-BFGS-B failed: {result.message} (nit={result.nit}, fun={result.fun})"
        )
    return FitResult(
        beta=np.asarray(result.x, dtype=float),
        success=True,
        nit=int(result.nit),
        fun=float(result.fun),
        message=str(result.message),
        lam=lam,
    )


def predict_raw(offset: np.ndarray, x: np.ndarray, beta: np.ndarray) -> np.ndarray:
    offset = np.asarray(offset, dtype=float)
    x = np.asarray(x, dtype=float)
    beta = np.asarray(beta, dtype=float)
    if x.size == 0 or beta.size == 0:
        return np.asarray(sigmoid(offset), dtype=float)
    return np.asarray(sigmoid(offset + x @ beta), dtype=float)
