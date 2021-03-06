# Copyright 2018 The TensorFlow Probability Authors.
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
# ============================================================================
"""Tests for GLM families."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# Dependency imports
import numpy as np

import tensorflow as tf
import tensorflow_probability as tfp

from tensorflow.python.framework import test_util


tfd = tf.contrib.distributions
tfb = tf.contrib.distributions.bijectors


class LogNormal(tfd.TransformedDistribution):
  """LogNormal distribution."""

  def __init__(self, loc, scale):
    with tf.name_scope('LogNormal', values=[loc]) as name:
      loc = tf.convert_to_tensor(loc, name='loc')
      scale = tf.convert_to_tensor(scale, name='scale')
      super(LogNormal, self).__init__(
          distribution=tfd.Normal(loc=loc, scale=scale),
          bijector=tfb.Exp(),
          name=name)

  def _mean(self):
    return tf.exp(self.distribution.loc + 0.5 * self.distribution.scale**2.)

  def _variance(self):
    return tf.expm1(self.distribution.scale**2.) * tf.exp(
        2. * self.distribution.loc + self.distribution.scale**2.)


def make_lognormal(mean):
  """Helper which creates a LogNormal with a specific mean."""
  mean = tf.convert_to_tensor(mean, name='mean')
  s2 = np.log(2.).astype(mean.dtype.as_numpy_dtype())
  return LogNormal(tf.log(mean) - 0.5 * s2, np.sqrt(s2))


class _GLMTestHarness(object):

  def testCorrectIsCanonicalSpecification(self):
    predicted_linear_response = np.stack([
        np.linspace(-5., -1e-3, 11),
        np.linspace(1e-3, 5, 11)]).reshape(2, 11, 1).astype(self.dtype)
    _, expected_variance, expected_grad_mean = self.expected(
        predicted_linear_response)
    with self.test_session() as sess:
      expected_variance_, expected_grad_mean_ = sess.run([
          expected_variance, expected_grad_mean])
    self.assertEqual(self.model.is_canonical,
                     np.all(expected_variance_ == expected_grad_mean_))

  @test_util.run_in_graph_and_eager_modes()
  def testCallWorksCorrectly(self):
    predicted_linear_response = np.stack([
        np.linspace(-5., -1e-3, 11),
        np.linspace(1e-3, 5, 11)]).reshape(2, 11, 1).astype(self.dtype)
    expected_mean, expected_variance, expected_grad_mean = self.expected(
        predicted_linear_response)
    actual_mean, actual_variance, actual_grad_mean = self.model(
        predicted_linear_response)
    [
        expected_mean_,
        expected_variance_,
        expected_grad_mean_,
        actual_mean_,
        actual_variance_,
        actual_grad_mean_,
    ] = self.evaluate([
        expected_mean,
        expected_variance,
        expected_grad_mean,
        actual_mean,
        actual_variance,
        actual_grad_mean,
    ])
    self.assertAllClose(expected_mean_, actual_mean_,
                        atol=1e-6, rtol=1e-4)
    self.assertAllClose(expected_variance_, actual_variance_,
                        atol=1e-6, rtol=1e-3)
    self.assertAllClose(expected_grad_mean_, actual_grad_mean_,
                        atol=1e-6, rtol=1e-4)

  @test_util.run_in_graph_and_eager_modes()
  def testLogProbWorksCorrectly(self):
    predicted_linear_response = np.stack([
        np.linspace(-5., -1e-3, 11),
        np.linspace(1e-3, 5, 11)]).reshape(2, 11, 1).astype(self.dtype)
    actual_mean = self.expected.linear_model_to_mean_fn(
        predicted_linear_response)
    distribution = self.expected.distribution_fn(actual_mean)
    response = tf.cast(distribution.sample(seed=42), self.dtype)
    response = tf.identity(response, name='response')  # Disable bijector cache.
    expected_log_prob = distribution.log_prob(
        response, name='expected_log_prob')
    actual_log_prob = self.model.log_prob(
        response, predicted_linear_response)
    [
        expected_log_prob_,
        actual_log_prob_,
    ] = self.evaluate([
        expected_log_prob,
        actual_log_prob,
    ])
    self.assertAllClose(expected_log_prob_, actual_log_prob_,
                        atol=1e-6, rtol=1e-4)


class BernoulliTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.Bernoulli()
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Bernoulli(probs=mu), tf.nn.sigmoid)


class BernoulliNormalCDFTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.BernoulliNormalCDF()
    def normal_cdf(r):
      r = tf.convert_to_tensor(r, name='r')
      n = tfd.Normal(loc=tf.zeros([], r.dtype.base_dtype),
                     scale=tf.ones([], r.dtype.base_dtype))
      return n.cdf(r)
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Bernoulli(probs=mu), normal_cdf)


class GammaExpTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.GammaExp()
    one = np.array(1, self.dtype)
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Gamma(concentration=one, rate=1./mu),
        tf.exp)


class GammaSoftplusTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.GammaSoftplus()
    one = np.array(1, self.dtype)
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Gamma(concentration=one, rate=1./mu),
        tf.nn.softplus)


class LogNormalTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.LogNormal()
    self.expected = tfp.glm.CustomExponentialFamily(
        make_lognormal, tf.exp)


class LogNormalSoftplusTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.LogNormalSoftplus()
    self.expected = tfp.glm.CustomExponentialFamily(
        make_lognormal, tf.nn.softplus)


class NormalTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.Normal()
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Normal(mu, self.dtype(1)), tf.identity)


class NormalReciprocalTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.NormalReciprocal()
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Normal(mu, self.dtype(1)), tf.reciprocal)


class PoissonTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.Poisson()
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Poisson(rate=mu), tf.exp)


class PoissonSoftplusTest(tf.test.TestCase, _GLMTestHarness):

  def setUp(self):
    self.dtype = np.float32
    self.model = tfp.glm.PoissonSoftplus()
    self.expected = tfp.glm.CustomExponentialFamily(
        lambda mu: tfd.Poisson(rate=mu), tf.nn.softplus)


if __name__ == '__main__':
  tf.test.main()
