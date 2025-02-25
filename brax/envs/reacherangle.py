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

"""Trains a reacher to reach a target.

Based on the OpenAI Gym MuJoCo Reacher environment.
"""

from typing import Tuple

import dataclasses
import jax
import jax.numpy as jnp
import brax
from brax.envs import env
from brax.physics import math
from brax.physics.base import take

from google.protobuf import text_format


class ReacherAngle(env.Env):
  """Trains a reacher arm to touch a random target via angle actuators."""

  def __init__(self, **kwargs):
    config = text_format.Parse(_SYSTEM_CONFIG, brax.Config())
    super().__init__(config, **kwargs)
    self.target_idx = self.sys.body_idx['target']
    self.arm_idx = self.sys.body_idx['body1']

    # map the [-1, 1] action space into a valid angle for the actuators
    limits = [[(jj.min, jj.max)
               for jj in j.angle_limit]
              for j in self.sys.config.joints]
    limits = [item for sublist in limits for item in sublist]
    mins = [l[0] for l in limits]
    ranges = [l[1] - l[0] for l in limits]
    self._min_act = jnp.array(mins)
    self._range_act = jnp.array(ranges)

  def reset(self, rng: jnp.ndarray) -> env.State:
    qp = self.sys.default_qp()
    rng, target = self._random_target(rng)
    pos = jax.ops.index_update(qp.pos, jax.ops.index[self.target_idx], target)
    qp = dataclasses.replace(qp, pos=pos)
    info = self.sys.info(qp)
    obs = self._get_obs(qp, info)
    reward, done, steps, zero = jnp.zeros(4)
    metrics = {
        'rewardDist': zero,
        'rewardCtrl': zero,
    }
    return env.State(rng, qp, info, obs, reward, done, steps, metrics)

  def step(self, state: env.State, action: jnp.ndarray) -> env.State:
    rng = state.rng

    action = self._min_act + self._range_act * ((action + 1) / 2.)

    qp, info = self.sys.step(state.qp, action)
    obs = self._get_obs(qp, info)

    # vector from tip to target is last 3 entries of obs vector
    reward_dist = -jnp.linalg.norm(obs[-3:])

    reward = reward_dist

    steps = state.steps + self.action_repeat
    done = jnp.where(steps >= self.episode_length, 1.0, 0.0)
    metrics = {
        'rewardDist': reward_dist,
        'rewardCtrl': 0.,
    }

    return env.State(rng, qp, info, obs, reward, done, steps, metrics)

  def _get_obs(self, qp: brax.QP, info: brax.Info) -> jnp.ndarray:
    """Egocentric observation of target and arm body."""

    # some pre-processing to pull joint angles and velocities
    (joint_angle,), _ = self.sys.joint_revolute.angle_vel(qp)

    # qpos:
    # x,y coord of target
    qpos = [qp.pos[self.target_idx, :2]]

    # dist to target and speed of tip
    arm_qps = take(qp, jnp.array(self.arm_idx))
    tip_pos, tip_vel = math.to_world(arm_qps, jnp.array([0.11, 0., 0.]))
    tip_to_target = [tip_pos - qp.pos[self.target_idx]]
    cos_sin_angle = [jnp.cos(joint_angle), jnp.sin(joint_angle)]

    # qvel:
    # velocity of tip
    qvel = [tip_vel[:2]]

    return jnp.concatenate(cos_sin_angle + qpos + qvel + tip_to_target)

  def _random_target(self, rng: jnp.ndarray) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """Returns a target location in a random circle slightly above xy plane."""
    rng, rng1, rng2 = jax.random.split(rng, 3)
    # we perform a sqrt here so that the final distribution of sampled targets
    # is uniformly random in 2D
    dist = .2 * jnp.sqrt(jax.random.uniform(rng1))
    ang = jnp.pi * 2. * jax.random.uniform(rng2)
    target_x = dist * jnp.cos(ang)
    target_y = dist * jnp.sin(ang)
    target_z = .01
    target = jnp.array([target_x, target_y, target_z]).transpose()
    return rng, target

_SYSTEM_CONFIG = """
bodies {
  name: "ground"
  colliders {
    plane {
    }
  }
  mass: 1.0
  inertia {
    x: 1.0
    y: 1.0
    z: 1.0
  }
  frozen {
    all: true
  }
}
bodies {
  name: "body0"
  colliders {
    position {
      x: 0.05
    }
    rotation {
      y: 90.0
    }
    capsule {
      radius: 0.01
      length: 0.12
    }
  }
  inertia {
    x: 1.0
    y: 1.0
    z: 1.0
  }
  mass: 0.035604715
}
bodies {
  name: "body1"
  colliders {
    position {
      x: 0.05
    }
    rotation {
      y: 90.0
    }
    capsule {
      radius: 0.01
      length: 0.12
    }
  }
  colliders {
    position { x: .11 }
    sphere {
      radius: 0.01
    }
  }
  inertia {
    x: 1.0
    y: 1.0
    z: 1.0
  }
  mass: 0.035604715
}
bodies {
  name: "target"
  colliders {
    position {
    }
    sphere {
      radius: 0.009
    }
  }
  inertia {
    x: 1.0
    y: 1.0
    z: 1.0
  }
  mass: 1.0
  frozen { all: true }
}
joints {
  name: "joint0"
  stiffness: 100.0
  parent: "ground"
  child: "body0"
  parent_offset {
    z: 0.01
  }
  child_offset {
  }
  rotation {
    y: -90.0
  }
  angle_limit {
      min: -180
      max: 180
    }
  limit_strength: 0.0
  spring_damping: 3.0
  angular_damping: 10.0
}
joints {
  name: "joint1"
  stiffness: 100.0
  parent: "body0"
  child: "body1"
  parent_offset {
    x: 0.1
  }
  child_offset {
  }
  rotation {
    y: -90.0
  }
  angle_limit {
    min: -180
    max: 180
  }
  limit_strength: 0.0
  spring_damping: 3.0
  angular_damping: 10.0
}
actuators {
  name: "joint0"
  joint: "joint0"
  strength: 20.0
  angle {
  }
}
actuators {
  name: "joint1"
  joint: "joint1"
  strength: 20.0
  angle {
  }
}
collide_include {
}
friction: 0.6
gravity {
  z: -9.81
}
baumgarte_erp: 0.1
dt: 0.02
substeps: 4
frozen {
  position {
    z: 1.0
  }
  rotation {
    x: 1.0
    y: 1.0
  }
}
"""
