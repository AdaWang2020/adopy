r"""
**Psychometric function** is to figure out whether a subject can perceive a
signal with varying levels of magnitude. The function has one design variable
for the *intensity* of a stimulus, :math:`x`; the model has four model
parameters: *guess rate* :math:`\gamma`, *lapse rate* :math:`\delta`,
*threshold* :math:`\alpha`, and *slope* :math:`\beta`.

.. figure:: ../../_static/images/Psychometricfn.svg
    :width: 70%
    :align: center

    A simple diagram for the Psychometric function.
"""
import numpy as np
from scipy.stats import norm, gumbel_l

from adopy.base import Engine, Task, Model
from adopy.functions import (inv_logit, get_random_design_index,
                             get_nearest_grid_index, const_positive, const_01)
from adopy.types import integer_like

__all__ = [
    'TaskPsi', 'ModelLogistic', 'ModelWeibull', 'ModelNormal', 'EnginePsi'
]


class TaskPsi(Task):
    """Task class for a simple 2-alternative forced choice task"""

    def __init__(self):
        super(TaskPsi, self).__init__(
            name='Psi',
            designs=['stimulus'],
            responses=[0, 1]  # binary responses
        )


class _ModelPsi(Model):
    def __init__(self, name):
        args = dict(
            name=name,
            task=TaskPsi(),
            params=['threshold', 'slope', 'guess_rate', 'lapse_rate'],
            constraint={
                'threshold': const_positive,
                'slope': const_positive,
                'guess_rate': const_01,
                'lapse_rate': const_01,
            })
        super(_ModelPsi, self).__init__(**args)

    def _compute(self, func, st, th, sl, gr, lr):
        return gr + (1 - gr - lr) * func(sl * (st - th))


class ModelLogistic(_ModelPsi):
    def __init__(self):
        super(ModelLogistic, self).__init__(name='Logistic')

    def compute(self, stimulus, guess_rate, lapse_rate, threshold, slope):
        r"""
        Calculate the psychometric function using logistic function.

        .. math::

            F(x; \mu, \beta) = \left[
                1 + \exp\left(-\beta (x - \mu) \right)
            \right]^{-1}

        Parameters
        ----------
        stimulus : numpy.ndarray or array_like
        guess_rate : numpy.ndarray or array_like
        lapse_rate : numpy.ndarray or array_like
        threshold : numpy.ndarry or array_like
        slope : numpy.ndarray or array_like

        Returns
        -------
        numpy.ndarray
        """
        return self._compute(inv_logit, stimulus,
                             threshold, slope, guess_rate, lapse_rate)


class ModelWeibull(_ModelPsi):
    def __init__(self):
        super(ModelWeibull, self).__init__(name='Weibull')

    def compute(self, stimulus, guess_rate, lapse_rate, threshold, slope):
        r"""
        Calculate the psychometric function using log Weibull (Gumbel)
        cumulative distribution function.

        .. math::

            F(x; \mu, \beta) = CDF_\text{Gumbel_l}
                \left( \beta (x - \mu) \right) \\

        Parameters
        ----------
        stimulus : numpy.ndarray or array_like
        guess_rate : numpy.ndarray or array_like
        lapse_rate : numpy.ndarray or array_like
        threshold : numpy.ndarry or array_like
        slope : numpy.ndarray or array_like

        Returns
        -------
        numpy.ndarray
        """
        return self._compute(gumbel_l.cdf, stimulus,
                             threshold, slope, guess_rate, lapse_rate)


class ModelNormal(_ModelPsi):
    def __init__(self):
        super(ModelNormal, self).__init__(name='Normal')

    def compute(self, stimulus, guess_rate, lapse_rate, threshold, slope):
        r"""
        Calculate the psychometric function with the Normal cumulative
        distribution function.

        .. math::

            F(x; \mu, \beta) = CDF_\text{Normal}\left( \beta (x - \mu) \right)

        Parameters
        ----------
        stimulus : numpy.ndarray or array_like
        guess_rate : numpy.ndarray or array_like
        lapse_rate : numpy.ndarray or array_like
        threshold : numpy.ndarry or array_like
        slope : numpy.ndarray or array_like

        Returns
        -------
        numpy.ndarray
        """
        return self._compute(norm.cdf, stimulus,
                             guess_rate, lapse_rate, threshold, slope)


class EnginePsi(Engine):
    def __init__(self, model, designs, params, d_step: int = 1):
        assert type(model) in [
            type(ModelLogistic()),
            type(ModelWeibull()),
            type(ModelNormal()),
        ]

        super(EnginePsi, self).__init__(
            task=TaskPsi(),
            model=model,
            designs=designs,
            params=params
        )

        self.idx_opt = get_random_design_index(self.grid_design)
        self.y_obs_prev = 1
        self.d_step = d_step

    @property
    def d_step(self) -> int:
        r"""
        Step size on index to compute :math:`\Delta` for the staircase method.
        """
        return self._d_step

    @d_step.setter
    def d_step(self, value: integer_like):
        if not isinstance(value, (int, np.int)) or value <= 0:
            raise ValueError('d_step should be an positive integer.')
        self._d_step = int(value)

    def get_design(self, kind='optimal'):
        r"""Choose a design with a given type.

        1. :code:`optimal`: an optimal design :math:`d^*` that maximizes
        the mutual information.

            .. math::
                \begin{align*}
                    p(y | d) &= \sum_\theta p(y | \theta, d) p_t(\theta) \\
                    I(Y(d); \Theta) &= H(Y(d)) - H(Y(d) | \Theta) \\
                    d^* &= \operatorname*{argmax}_d I(Y(d); |Theta) \\
                \end{align*}

        2. :code:`staircase`: Choose the stimulus :math:`s` as below:

            .. math::
                s_t = \begin{cases}
                    s_{t-1} - 1 & \text{if } y_{t-1} = 1 \\
                    s_{t-1} + 2 & \text{if } y_{t-1} = 0
                \end{cases}

        3. :code:`random`: a design randomly chosen.

        Parameters
        ----------
        kind : {'optimal', 'staircase', 'random'}, optional
            Type of a design to choose

        Returns
        -------
        design : array_like
            A chosen design vector
        """
        assert kind in {'optimal', 'staircase', 'random'}

        self._update_mutual_info()

        if kind == 'optimal':
            ret = self.grid_design.iloc[np.argmax(self.mutual_info)]

        elif kind == 'staircase':
            if self.y_obs_prev == 1:
                idx = max(0, self.idx_opt - self.d_step)
            else:
                idx = min(len(self.grid_design) - 1,
                          self.idx_opt + (self.d_step * 2))

            ret = self.grid_design.iloc[np.int(idx)]

        elif kind == 'random':
            ret = self.grid_design.iloc[get_random_design_index(
                self.grid_design)]

        else:
            raise RuntimeError('An invalid kind of design: "{}".'.format(type))

        self.idx_opt = get_nearest_grid_index(ret, self.grid_design)

        return ret

    def update(self, design, response):
        r"""
        Update the posterior distribution for model parameters.

        .. math::

            p(\theta | y_\text{obs}(t), d^*) =
                \frac{ p( y_\text{obs}(t) | \theta, d^*) p_t(\theta) }
                    { p( y_\text{obs}(t) | d^* ) }

        Parameters
        ----------
        design
            Design vector for given response
        response
            Any kinds of observed response
        """
        super(EnginePsi, self).update(design, response)

        # Store the previous response for staircase
        self.y_obs_prev = response
