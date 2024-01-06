from __future__ import annotations

import numpy as np
import pytest
import scipy
from numpy import pi
from numpy.testing import assert_allclose
from numpy.typing import ArrayLike

import thztools
from thztools.thztools import (
    NoiseModel,
    _assign_sampling_time,
    _costfun_noisefit,
    _costfuntls,
    fit,
    noisefit,
    scaleshift,
    transfer,
    wave,
)

atol = 1e-8
rtol = 1e-5


def tfun(p, w):
    return p[0] * np.exp(1j * p[1] * w)


def tfun1(w, p):
    return p[0] * np.exp(1j * p[1] * w)


def tfun2(w, p0, p1):
    return p0 * np.exp(1j * p1 * w)


def jac_fun(p, w):
    exp_ipw = np.exp(1j * p[1] * w)
    return np.stack((exp_ipw, 1j * w * p[0] * exp_ipw)).T


class TestGlobalOptions:
    # thztools.global_options.sampling_time = None

    def test_sampling_time(self):
        assert thztools.global_options.sampling_time is None

    @pytest.mark.parametrize("global_sampling_time", [None, 0.1])
    @pytest.mark.parametrize("dt", [None, 0.1, 1.0])
    def test_assignment(self, global_sampling_time, dt, monkeypatch):
        monkeypatch.setattr(
            thztools.global_options, "sampling_time", global_sampling_time
        )
        if global_sampling_time is None and dt is None:
            assert np.isclose(_assign_sampling_time(dt), 1.0)
        elif global_sampling_time is None and dt is not None:
            assert np.isclose(_assign_sampling_time(dt), dt)
        elif global_sampling_time is not None and dt is None:
            assert np.isclose(_assign_sampling_time(dt), global_sampling_time)
        elif global_sampling_time is not None and np.isclose(
            dt, global_sampling_time
        ):
            assert np.isclose(_assign_sampling_time(dt), global_sampling_time)
        else:
            with pytest.warns(UserWarning):
                assert np.isclose(_assign_sampling_time(dt), dt)


class TestNoiseModel:
    n = 16
    dt = 1.0 / n
    t = np.arange(n) * dt
    mu = np.cos(2 * pi * t)
    mu_dot = -2 * pi * np.sin(2 * pi * t)

    @pytest.mark.parametrize(
        "alpha, beta, tau, mu, dt, axis, expected",
        [
            (1, 0, 0, mu, dt, -1, np.ones(n)),
            (1, 0, 0, np.stack((mu, mu)), dt, -1, np.ones((2, n))),
            (1, 0, 0, np.stack((mu, mu)).T, dt, 0, np.ones((n, 2))),
            (0, 1, 0, mu, dt, -1, mu**2),
            (0, 0, 1, mu, dt, -1, mu_dot**2),
            (0, 0, 1 / dt, mu, None, -1, mu_dot**2),
        ],
    )
    def test_var_definition(
        self,
        alpha: float,
        beta: float,
        tau: float,
        mu: ArrayLike,
        dt: float | None,
        axis: int,
        expected: ArrayLike,
    ) -> None:
        if dt is None:
            noise_model = NoiseModel(alpha, beta, tau)
            result = noise_model.variance(mu, axis=axis)
        else:
            noise_model = NoiseModel(alpha, beta, tau, dt=dt)
            result = noise_model.variance(mu, axis=axis)
        assert_allclose(result, expected, atol=atol, rtol=rtol)  # type: ignore

    @pytest.mark.parametrize(
        "alpha, beta, tau, mu, dt, axis, expected",
        [
            (1, 0, 0, mu, dt, -1, np.ones(n)),
            (1, 0, 0, np.stack((mu, mu)), dt, -1, np.ones((2, n))),
            (1, 0, 0, np.stack((mu, mu)).T, dt, 0, np.ones((n, 2))),
            (0, 1, 0, mu, dt, -1, np.abs(mu)),
            (0, 0, 1, mu, dt, -1, np.abs(mu_dot)),
            (0, 0, 1 / dt, mu, None, -1, np.abs(mu_dot)),
        ],
    )
    def test_amp_definition(
        self,
        alpha: float,
        beta: float,
        tau: float,
        mu: ArrayLike,
        dt: float,
        axis: int,
        expected: ArrayLike,
    ) -> None:
        if dt is None:
            noise_model = NoiseModel(alpha, beta, tau)
            result = noise_model.amplitude(mu, axis=axis)
        else:
            noise_model = NoiseModel(alpha, beta, tau, dt=dt)
            result = noise_model.amplitude(mu, axis=axis)
        assert_allclose(result, expected, atol=atol, rtol=rtol)  # type: ignore

    @pytest.mark.parametrize(
        "alpha, beta, tau, mu, dt, axis, expected",
        [
            (1, 0, 0, mu, dt, -1, (n,)),
            (1, 0, 0, mu, None, -1, (n,)),
            (1, 0, 0, np.stack((mu, mu)), dt, -1, (2, n)),
            (1, 0, 0, np.stack((mu, mu)).T, dt, 0, (n, 2)),
        ],
    )
    def test_noise_definition(
        self,
        alpha: float,
        beta: float,
        tau: float,
        mu: ArrayLike,
        dt: float,
        axis: int,
        expected: ArrayLike,
    ) -> None:
        if dt is None:
            noise_model = NoiseModel(alpha, beta, tau)
            result = noise_model.noise(mu, axis=axis)
        else:
            noise_model = NoiseModel(alpha, beta, tau, dt=dt)
            result = noise_model.noise(mu, axis=axis)
        assert result.shape == expected


class TestTransferOut:
    n = 16
    dt = 1.0 / n
    t = np.arange(n) * dt
    mu = np.cos(2 * pi * t)

    @pytest.mark.parametrize("fft_sign", [True, False])
    @pytest.mark.parametrize(
        "t_fun, x, p, expected",
        [
            [tfun1, mu, [1.0, 0.0], mu],
            [tfun2, mu, (1.0, 0.0), mu],
        ],
    )
    def test_inputs(self, t_fun, x, fft_sign, p, expected):
        ts = self.dt
        thztools.global_options.sampling_time = None
        assert_allclose(
            transfer(t_fun, x, dt=ts, fft_sign=fft_sign, args=p),
            expected,
        )

    @pytest.mark.parametrize("x", [np.ones((n, n))])
    def test_error(self, x):
        dt = self.dt
        with pytest.raises(ValueError):
            _ = transfer(x, tfun1, dt=dt, args=[1.0, 0.0])


class TestTimebase:
    @pytest.mark.parametrize(
        "dt",
        [
            None,
            1.0,
            2.0,
        ],
    )
    @pytest.mark.parametrize(
        "t_init",
        [
            None,
            1.0,
            2.0,
        ],
    )
    def test_timebase(self, dt, t_init):
        n = 8
        if t_init is None:
            t = thztools.timebase(n, dt=dt)
            t_init = 0.0
        else:
            t = thztools.timebase(n, dt=dt, t_init=t_init)
        dt = _assign_sampling_time(dt)
        t_expected = t_init + np.arange(n) * dt
        assert_allclose(t, t_expected, rtol=rtol, atol=atol)


class TestWave:
    # thztools.global_options.sampling_time = None

    @pytest.mark.parametrize(
        "t0",
        [2.4, None],
    )
    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"a": 1.0},
            {"taur": 6.0},
            {"tauc": 2.0},
            {"fwhm": 1.0},
        ],
    )
    def test_inputs(self, t0: float | None, kwargs: dict) -> None:
        n = 8
        dt = 1.0
        y_expected = np.array(
            [
                0.07767792,
                -0.63041598,
                -1.03807638,
                -0.81199085,
                -0.03955531,
                0.72418661,
                1.0,
                0.71817398,
            ]
        )
        assert_allclose(
            wave(n, dt=dt, t0=t0, **kwargs),  # type: ignore
            y_expected,  # type: ignore
            atol=atol,
            rtol=rtol,
        )


class TestScaleShift:
    thztools.global_options.sampling_time = None
    n = 16
    dt = 1.0 / n
    t = np.arange(n) * dt
    x = np.cos(2 * pi * t)
    x_2 = np.stack((x, x))

    @pytest.mark.parametrize(
        "x, kwargs, expected",
        [
            [[], {}, np.empty((0,))],
            [x, {}, x],
            [x, {"a": 2}, 2 * x],
            [x, {"eta": 1}, np.cos(2 * pi * (t - dt))],
            [x, {"a": 2, "eta": 1}, 2 * np.cos(2 * pi * (t - dt))],
            [x, {"a": 2, "eta": dt, "dt": dt}, 2 * np.cos(2 * pi * (t - dt))],
            [x_2, {"a": [2, 0.5]}, np.stack((2 * x, 0.5 * x))],
            [
                x_2,
                {"eta": [1, -1]},
                np.stack(
                    (np.cos(2 * pi * (t - dt)), np.cos(2 * pi * (t + dt)))
                ),
            ],
            [
                x_2,
                {"eta": [dt, -dt], "dt": dt},
                np.stack(
                    (np.cos(2 * pi * (t - dt)), np.cos(2 * pi * (t + dt)))
                ),
            ],
            [
                x_2,
                {"a": [2, 0.5], "eta": [1, -1]},
                np.stack(
                    (
                        2 * np.cos(2 * pi * (t - dt)),
                        0.5 * np.cos(2 * pi * (t + dt)),
                    )
                ),
            ],
            [
                x_2,
                {"a": [2, 0.5], "eta": [dt, -dt], "dt": dt},
                np.stack(
                    (
                        2 * np.cos(2 * pi * (t - dt)),
                        0.5 * np.cos(2 * pi * (t + dt)),
                    )
                ),
            ],
            [x_2.T, {"a": [2, 0.5], "axis": 0}, np.stack((2 * x, 0.5 * x)).T],
        ],
    )
    def test_inputs(
        self, x: ArrayLike, kwargs: dict, expected: ArrayLike
    ) -> None:
        assert_allclose(
            scaleshift(x, **kwargs),  # type: ignore
            expected,  # type: ignore
            atol=atol,
            rtol=rtol,
        )

    @pytest.mark.parametrize(
        "x, kwargs", [[x, {"a": [2, 0.5]}], [x, {"eta": [1, -1]}]]
    )
    def test_errors(self, x: ArrayLike, kwargs: dict) -> None:
        with pytest.raises(ValueError, match="correction with shape"):
            scaleshift(x, **kwargs)


class TestCostFunTLS:
    thztools.global_options.sampling_time = None
    theta = (1, 0)
    mu = np.arange(8)
    xx = mu
    yy = xx
    sigmax = np.ones_like(xx)
    sigmay = sigmax
    dt = 1.0

    assert_allclose(
        _costfuntls(tfun, theta, mu, xx, yy, sigmax, sigmay, dt),
        np.concatenate((np.zeros_like(xx), np.zeros_like(xx))),
    )


class TestTDNLLScaled:
    thztools.global_options.sampling_time = None
    m = 2
    n = 16
    dt = 1.0 / n
    t = np.arange(n) * dt
    mu = np.cos(2 * pi * t)
    x = np.tile(mu, [m, 1])
    logv_alpha = 0
    logv_beta = -np.inf
    logv_tau = -np.inf
    delta = np.zeros(n)
    epsilon = np.zeros(m - 1)
    eta = np.zeros(m - 1)
    desired_nll = x.size * np.log(2 * pi) / 2

    @pytest.mark.parametrize(
        "fix_logv_alpha, desired_gradnll_logv_alpha",
        [
            [
                True,
                [],
            ],
            [
                False,
                [1.0],
            ],
        ],
    )
    @pytest.mark.parametrize(
        "fix_logv_beta, desired_gradnll_logv_beta",
        [
            [
                True,
                [],
            ],
            [
                False,
                [0.0],
            ],
        ],
    )
    @pytest.mark.parametrize(
        "fix_logv_tau, desired_gradnll_logv_tau",
        [
            [
                True,
                [],
            ],
            [
                False,
                [0.0],
            ],
        ],
    )
    @pytest.mark.parametrize(
        "fix_delta, desired_gradnll_delta",
        [
            [
                True,
                [],
            ],
            [
                False,
                np.zeros(n),
            ],
        ],
    )
    @pytest.mark.parametrize(
        "fix_epsilon, desired_gradnll_epsilon",
        [
            [
                True,
                [],
            ],
            [
                False,
                np.zeros(m - 1),
            ],
        ],
    )
    @pytest.mark.parametrize(
        "fix_eta, desired_gradnll_eta",
        [
            [
                True,
                [],
            ],
            [
                False,
                np.zeros(m - 1),
            ],
        ],
    )
    def test_gradnll_calc(
        self,
        fix_logv_alpha,
        fix_logv_beta,
        fix_logv_tau,
        fix_delta,
        fix_epsilon,
        fix_eta,
        desired_gradnll_logv_alpha,
        desired_gradnll_logv_beta,
        desired_gradnll_logv_tau,
        desired_gradnll_delta,
        desired_gradnll_epsilon,
        desired_gradnll_eta,
    ):
        n = self.n
        m = self.m
        x = self.x
        logv_alpha = self.logv_alpha
        logv_beta = self.logv_beta
        logv_tau = self.logv_tau
        delta = self.delta
        epsilon = self.epsilon
        eta_on_dt = self.eta / self.dt
        desired_gradnll = np.concatenate(
            (
                desired_gradnll_logv_alpha,
                desired_gradnll_logv_beta,
                desired_gradnll_logv_tau,
                desired_gradnll_delta,
                desired_gradnll_epsilon,
                desired_gradnll_eta,
            )
        )
        _, gradnll = _costfun_noisefit(
            x,
            logv_alpha,
            logv_beta,
            logv_tau,
            delta,
            epsilon,
            eta_on_dt,
            fix_logv_alpha=fix_logv_alpha,
            fix_logv_beta=fix_logv_beta,
            fix_logv_tau=fix_logv_tau,
            fix_delta=fix_delta,
            fix_epsilon=fix_epsilon,
            fix_eta=fix_eta,
            scale_logv=np.ones(3),
            scale_delta=np.ones(n),
            scale_epsilon=np.ones(m - 1),
            scale_eta=np.ones(m - 1),
        )
        assert_allclose(
            gradnll, desired_gradnll, atol=10 * np.finfo(float).eps
        )


class TestNoiseFit:
    rng = np.random.default_rng(0)
    n = 256
    m = 64
    dt = 0.05
    t = np.arange(n) * dt
    mu = wave(n, dt=dt, t0=n * dt / 3)
    alpha, beta, tau = 1e-5, 1e-3, 1e-3
    sigma = np.array([alpha, beta, tau])
    noise_model = NoiseModel(alpha, beta, tau, dt=dt)
    noise = noise_model.noise(np.ones((m, 1)) * mu, seed=0)
    x = np.array(mu + noise)
    a = np.ones(m)
    eta = np.zeros(m)

    @pytest.mark.parametrize("x", [x, x[:, 0]])
    @pytest.mark.parametrize(
        "sigma_alpha0",
        [
            None,
            alpha,
        ],
    )
    @pytest.mark.parametrize(
        "sigma_beta0",
        [
            None,
            beta,
        ],
    )
    @pytest.mark.parametrize(
        "sigma_tau0",
        [
            None,
            tau,
        ],
    )
    @pytest.mark.parametrize("mu0", [None, mu, []])
    @pytest.mark.parametrize("a0", [None, a, []])
    @pytest.mark.parametrize("eta0", [None, eta, []])
    @pytest.mark.parametrize("fix_sigma_alpha", [True, False])
    @pytest.mark.parametrize("fix_sigma_beta", [True, False])
    @pytest.mark.parametrize("fix_sigma_tau", [True, False])
    @pytest.mark.parametrize("fix_mu", [True, False])
    @pytest.mark.parametrize("fix_a", [True, False])
    @pytest.mark.parametrize("fix_eta", [True, False])
    def test_inputs(
        self,
        x,
        sigma_alpha0,
        sigma_beta0,
        sigma_tau0,
        mu0,
        a0,
        eta0,
        fix_sigma_alpha,
        fix_sigma_beta,
        fix_sigma_tau,
        fix_mu,
        fix_a,
        fix_eta,
    ):
        print(f"{scipy.__version__=}")
        n = self.n
        m = self.m
        dt = self.dt
        if (
            x.ndim < 2
            or (mu0 is not None and len(mu0) != n)
            or (a0 is not None and len(a0) != m)
            or (eta0 is not None and len(eta0) != m)
            or (
                fix_sigma_alpha
                and fix_sigma_beta
                and fix_sigma_tau
                and fix_mu
                and fix_a
                and fix_eta
            )
        ):
            with pytest.raises(ValueError):
                _ = noisefit(
                    x.T,
                    dt=dt,
                    sigma_alpha0=sigma_alpha0,
                    sigma_beta0=sigma_beta0,
                    sigma_tau0=sigma_tau0,
                    mu0=mu0,
                    a0=a0,
                    eta0=eta0,
                    fix_sigma_alpha=fix_sigma_alpha,
                    fix_sigma_beta=fix_sigma_beta,
                    fix_sigma_tau=fix_sigma_tau,
                    fix_mu=fix_mu,
                    fix_a=fix_a,
                    fix_eta=fix_eta,
                )
        else:
            res = noisefit(
                x.T,
                dt=dt,
                sigma_alpha0=sigma_alpha0,
                sigma_beta0=sigma_beta0,
                sigma_tau0=sigma_tau0,
                mu0=mu0,
                a0=a0,
                eta0=eta0,
                fix_sigma_alpha=fix_sigma_alpha,
                fix_sigma_beta=fix_sigma_beta,
                fix_sigma_tau=fix_sigma_tau,
                fix_mu=fix_mu,
                fix_a=fix_a,
                fix_eta=fix_eta,
            )
            assert res.diagnostic["status"] == 0


class TestFit:
    thztools.global_options.sampling_time = None
    rng = np.random.default_rng(0)
    n = 16
    dt = 1.0 / n
    t = np.arange(n) * dt
    mu = np.cos(2 * pi * t)
    p0 = (1, 0)
    psi = mu
    alpha, beta, tau = 1e-5, 0, 0
    sigma = np.array([alpha, beta, tau])
    noise_model = NoiseModel(alpha, beta, tau, dt=dt)
    noise_amp = noise_model.amplitude(mu)
    x = mu + noise_amp * rng.standard_normal(n)
    y = psi + noise_amp * rng.standard_normal(n)

    @pytest.mark.parametrize("noise_parms", [(1, 0, 0), sigma**2])
    @pytest.mark.parametrize("p_bounds", [None, ((0, -1), (2, 1))])
    @pytest.mark.parametrize("jac", [None, jac_fun])
    @pytest.mark.parametrize("kwargs", [None, {}])
    def test_inputs(self, noise_parms, p_bounds, jac, kwargs):
        p0 = self.p0
        x = self.x
        y = self.y
        dt = self.dt
        p = fit(
            tfun,
            p0,
            x,
            y,
            dt=dt,
            sigma_parms=noise_parms,
            p_bounds=p_bounds,
            jac=jac,
            kwargs=kwargs,
        )
        assert_allclose(p["p_opt"], p0, atol=1e-6)

    def test_errors(self):
        p0 = self.p0
        x = self.x
        y = self.y
        dt = self.dt
        with pytest.raises(ValueError):
            _ = fit(tfun, p0, x, y, dt=dt, p_bounds=())
