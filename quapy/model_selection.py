import itertools
import signal
from copy import deepcopy
from typing import Union, Callable
import evaluation
import quapy as qp
from protocol import AbstractProtocol, OnLabelledCollectionProtocol
from quapy.data.base import LabelledCollection
from quapy.method.aggregative import BaseQuantifier
from time import time


class GridSearchQ(BaseQuantifier):
    """Grid Search optimization targeting a quantification-oriented metric.

    Optimizes the hyperparameters of a quantification method, based on an evaluation method and on an evaluation
    protocol for quantification.

    :param model: the quantifier to optimize
    :type model: BaseQuantifier
    :param param_grid: a dictionary with keys the parameter names and values the list of values to explore
    :param protocol:
    :param error: an error function (callable) or a string indicating the name of an error function (valid ones
        are those in qp.error.QUANTIFICATION_ERROR
    :param refit: whether or not to refit the model on the whole labelled collection (training+validation) with
        the best chosen hyperparameter combination. Ignored if protocol='gen'
    :param timeout: establishes a timer (in seconds) for each of the hyperparameters configurations being tested.
        Whenever a run takes longer than this timer, that configuration will be ignored. If all configurations end up
        being ignored, a TimeoutError exception is raised. If -1 (default) then no time bound is set.
    :param verbose: set to True to get information through the stdout
    """

    def __init__(self,
                 model: BaseQuantifier,
                 param_grid: dict,
                 protocol: AbstractProtocol,
                 error: Union[Callable, str] = qp.error.mae,
                 refit=True,
                 timeout=-1,
                 n_jobs=1,
                 verbose=False):

        self.model = model
        self.param_grid = param_grid
        self.protocol = protocol
        self.refit = refit
        self.timeout = timeout
        self.n_jobs = n_jobs
        self.verbose = verbose
        self.__check_error(error)
        assert isinstance(protocol, AbstractProtocol), 'unknown protocol'

    def _sout(self, msg):
        if self.verbose:
            print(f'[{self.__class__.__name__}]: {msg}')

    def __check_error(self, error):
        if error in qp.error.QUANTIFICATION_ERROR:
            self.error = error
        elif isinstance(error, str):
            self.error = qp.error.from_name(error)
        elif hasattr(error, '__call__'):
            self.error = error
        else:
            raise ValueError(f'unexpected error type; must either be a callable function or a str representing\n'
                             f'the name of an error function in {qp.error.QUANTIFICATION_ERROR_NAMES}')

    def fit(self, training: LabelledCollection):
        """ Learning routine. Fits methods with all combinations of hyperparameters and selects the one minimizing
            the error metric.

        :param training: the training set on which to optimize the hyperparameters
        :return: self
        """
        params_keys = list(self.param_grid.keys())
        params_values = list(self.param_grid.values())

        protocol = self.protocol
        n_jobs = self.n_jobs

        self.param_scores_ = {}
        self.best_score_ = None

        tinit = time()

        hyper = [dict({k: values[i] for i, k in enumerate(params_keys)}) for values in itertools.product(*params_values)]
        scores = qp.util.parallel(self._delayed_eval, ((params, training) for params in hyper), n_jobs=n_jobs)

        for params, score, model in scores:
            if score is not None:
                if self.best_score_ is None or score < self.best_score_:
                    self.best_score_ = score
                    self.best_params_ = params
                    self.best_model_ = model
                self.param_scores_[str(params)] = score
            else:
                self.param_scores_[str(params)] = 'timeout'

        tend = time()-tinit

        if self.best_score_ is None:
            raise TimeoutError('all jobs took more than the timeout time to end')

        self._sout(f'optimization finished: best params {self.best_params_} (score={self.best_score_:.5f}) '
                   f'[took {tend:.4f}s]')

        if self.refit:
            if isinstance(protocol, OnLabelledCollectionProtocol):
                self._sout(f'refitting on the whole development set')
                self.best_model_.fit(training + protocol.get_labelled_collection())
            else:
                raise RuntimeWarning(f'"refit" was requested, but the protocol does not '
                                     f'implement the {OnLabelledCollectionProtocol.__name__} interface')

        return self

    def _delayed_eval(self, args):
        params, training = args

        protocol = self.protocol
        error = self.error

        if self.timeout > 0:
            def handler(signum, frame):
                raise TimeoutError()

            signal.signal(signal.SIGALRM, handler)

        tinit = time()

        if self.timeout > 0:
            signal.alarm(self.timeout)

        try:
            model = deepcopy(self.model)
            # overrides default parameters with the parameters being explored at this iteration
            model.set_params(**params)
            model.fit(training)
            score = evaluation.evaluate(model, protocol=protocol, error_metric=error)

            ttime = time()-tinit
            self._sout(f'hyperparams={params}\t got {error.__name__} score {score:.5f} [took {ttime:.4f}s]')

            if self.timeout > 0:
                signal.alarm(0)
        except TimeoutError:
            self._sout(f'timeout ({self.timeout}s) reached for config {params}')
            score = None

        return params, score, model


    def quantify(self, instances):
        """Estimate class prevalence values using the best model found after calling the :meth:`fit` method.

        :param instances: sample contanining the instances
        :return: a ndarray of shape `(n_classes)` with class prevalence estimates as according to the best model found
            by the model selection process.
        """
        assert hasattr(self, 'best_model_'), 'quantify called before fit'
        return self.best_model().quantify(instances)

    def set_params(self, **parameters):
        """Sets the hyper-parameters to explore.

        :param parameters: a dictionary with keys the parameter names and values the list of values to explore
        """
        self.param_grid = parameters

    def get_params(self, deep=True):
        """Returns the dictionary of hyper-parameters to explore (`param_grid`)

        :param deep: Unused
        :return: the dictionary `param_grid`
        """
        return self.param_grid

    def best_model(self):
        """
        Returns the best model found after calling the :meth:`fit` method, i.e., the one trained on the combination
        of hyper-parameters that minimized the error function.

        :return: a trained quantifier
        """
        if hasattr(self, 'best_model_'):
            return self.best_model_
        raise ValueError('best_model called before fit')


