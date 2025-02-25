# Copyright 2021 The Brax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for brax.envs."""

import logging
import time

from absl.testing import absltest
from absl.testing import parameterized
import jax
import jax.numpy as np
from brax import envs

_EXPECTED_SPS = {'ant': 1000, 'fetch': 1000}


class EnvTest(parameterized.TestCase):

  @parameterized.parameters(_EXPECTED_SPS.items())
  def testSpeed(self, env_name, expected_sps):
    batch_size = 128
    episode_length = 1000

    env = envs.create(env_name, batch_size=batch_size)
    zero_action = np.zeros((batch_size, env.action_size))

    @jax.jit
    def run_env(state):

      def step(carry, _):
        state, = carry
        state = env.step(state, zero_action)
        return (state,), ()

      (state,), _ = jax.lax.scan(step, (state,), (), length=episode_length)
      return state

    # warmup
    rng = jax.random.split(jax.random.PRNGKey(0), batch_size)
    state = env.reset(rng)
    state = run_env(state)
    state.done.block_until_ready()

    sps = []
    for seed in range(5):
      rng = jax.random.split(jax.random.PRNGKey(seed), batch_size)
      state = env.reset(rng)
      jax.device_put(state)
      t = time.time()
      state = run_env(state)
      state.done.block_until_ready()
      sps.append((batch_size * episode_length) / (time.time() - t))
      self.assertTrue(np.alltrue(state.done))

    mean_sps = np.mean(np.array(sps))
    logging.info('%s SPS %s %s', env_name, mean_sps, sps)
    self.assertGreater(mean_sps, expected_sps * 0.99)


if __name__ == '__main__':
  absltest.main()
