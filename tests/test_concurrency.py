# Copyright 2018 D-Wave Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import unittest

import dimod
import hybrid
from hybrid.core import State
from hybrid.concurrency import Present, Future, ImmediateExecutor, immediate_executor
from hybrid.testing import RunTimeAssertionMixin
from hybrid.utils import cpu_count


class TestPresent(unittest.TestCase):

    def test_res(self):
        for val in 1, 'x', True, False, State(problem=1), lambda: None:
            f = Present(result=val)
            self.assertIsInstance(f, Future)
            self.assertTrue(f.done())
            self.assertEqual(f.result(), val)

    def test_exc(self):
        for exc in ValueError, KeyError, ZeroDivisionError:
            f = Present(exception=exc())
            self.assertIsInstance(f, Future)
            self.assertTrue(f.done())
            self.assertRaises(exc, f.result)

    def test_invalid_init(self):
        self.assertRaises(ValueError, Present)


class TestImmediateExecutor(unittest.TestCase):

    def test_submit_res(self):
        ie = ImmediateExecutor()
        f = ie.submit(lambda x: not x, True)
        self.assertIsInstance(f, Present)
        self.assertIsInstance(f, Future)
        self.assertEqual(f.result(), False)

    def test_submit_exc(self):
        ie = ImmediateExecutor()
        f = ie.submit(lambda: 1/0)
        self.assertIsInstance(f, Present)
        self.assertIsInstance(f, Future)
        self.assertRaises(ZeroDivisionError, f.result)


class TestMultithreading(unittest.TestCase, RunTimeAssertionMixin):

    def test_concurrent_tabu_samples(self):
        t1 = hybrid.TabuProblemSampler(timeout=1000)
        t2 = hybrid.TabuProblemSampler(timeout=2000)
        workflow = hybrid.Parallel(t1, t2)

        bqm = dimod.BinaryQuadraticModel({'a': 1}, {}, 0, 'BINARY')
        state = hybrid.State.from_problem(bqm)

        with self.assertRuntimeWithin(1900, 2500):
            workflow.run(state).result()

    @unittest.skipUnless(cpu_count() >= 2, "at least two threads required")
    def test_concurrent_sa_samples(self):
        params = dict(num_reads=1, num_sweeps=1000000)

        # serial and parallel SA runs
        s = (
            hybrid.SimulatedAnnealingProblemSampler(**params)
            | hybrid.SimulatedAnnealingProblemSampler(**params)
        )
        p = hybrid.Parallel(
            hybrid.SimulatedAnnealingProblemSampler(**params),
            hybrid.SimulatedAnnealingProblemSampler(**params)
        )

        bqm = dimod.generators.uniform(graph=1, vartype=dimod.SPIN)
        state = hybrid.State.from_problem(bqm)

        # wall clock workflow runtime for `repeat` runs
        def time_workflow(workflow, state, repeat=10):
            with hybrid.tictoc() as timer:
                for _ in range(repeat):
                    workflow.run(state).result()
            return timer.dt

        # do two warm-up runs before the actual measurement
        for _ in range(3):
            t_s = time_workflow(s, state)
            t_p = time_workflow(p, state)

        speedup = t_s / t_p

        # NOTE: temporary for debugging on CI only
        print(speedup)

        # NOTE: the extremely weak lower bound on speedup was chosen so we don't
        # fail on the unreliable/inconsistent CI VMs, and but to show some
        # concurrency does exist
        self.assertGreater(speedup, 1.25)
