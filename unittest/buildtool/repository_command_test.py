# Copyright 2017 Google Inc. All Rights Reserved.
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

import logging
import os
import threading
import time
import unittest


from buildtool import (
    RepositoryCommandProcessor,
    RepositoryCommandFactory,
    BranchSourceCodeManager,
    MetricsManager)

import custom_test_command


TEST_INPUT_DIR = '/test/root/path/for/local/repos'
TEST_REPOSITORY_NAMES = ['repo-one', 'repo-two']

COMMAND = custom_test_command.COMMAND
FAILURE_COMMAND_NAME = 'test_command_failure'

class SimpleNamespace(object):
  def __init__(self):
    self.command = 'test_command'
    self.git_branch = 'test_branch'
    self.github_owner = 'test_github_owner'
    self.github_pull_ssh = False
    self.output_dir = '/tmp'
<<<<<<< HEAD
=======
    self.scm_repository_spec_path = os.path.join(
        os.path.dirname(__file__), 'test_scm_repositories.yml')
>>>>>>> feat(buildtool): added publish_halyard and publish_spinnaker


class TestRepositoryCommand(RepositoryCommandProcessor):
  def __init__(self, factory, options, pos_arg, **kwargs):
    super(TestRepositoryCommand, self).__init__(
        factory, options, source_repository_names=TEST_REPOSITORY_NAMES)
    self.test_init_args = (factory, options, pos_arg, kwargs)
    self.preprocessed = False
    self.postprocess_dict = None
    self.ensured = set([])
    self.repositories = set([])
    self.test_repo_threadid = []

  def ensure_local_repository(self, repository):
    assert(self.preprocessed)
    assert(not self.postprocess_dict)
    assert(repository not in self.ensured)
    assert(repository not in self.repositories)
    self.ensured.add(repository)

  def _do_preprocess(self):
    assert(not self.preprocessed)
    self.preprocessed = True

  def _do_postprocess(self, result_dict):
    assert(self.preprocessed)
    assert(not self.postprocess_dict)
    self.postprocess_dict = result_dict
    return {'foo': 'bar'}

  def _do_repository(self, repository):
    assert(self.preprocessed)
    assert(not self.postprocess_dict)
    assert(repository in self.ensured)
    assert(repository not in self.repositories)
    self.repositories.add(repository)
    time.sleep(0.1)  # Encourage threads to be different
    self.test_repo_threadid.append(threading.current_thread().ident)
    if self.name == FAILURE_COMMAND_NAME:
      logging.info('Raising injected error')
      raise ValueError('Injected Failure')
    return 'TEST {0}'.format(repository.name)


class RepositoryCommandProcessorTest(unittest.TestCase):
  def do_test_command(self, options, command_name):
    options.input_dir = TEST_INPUT_DIR
    options.only_repositories = None

    init_dict = {'a': 'A', 'b': 'B'}
    factory = RepositoryCommandFactory(
        command_name, TestRepositoryCommand, 'A test command.',
        BranchSourceCodeManager,
        123, **init_dict)

    # Test construction
    command = factory.make_command(options)
    self.assertEquals((factory, options, 123, init_dict),
                      command.test_init_args)
    self.assertFalse(command.preprocessed)
    self.assertEquals(factory, command.factory)
    self.assertEquals(factory.name, command.name)
    self.assertEquals([command.source_code_manager.make_repository_spec(name)
                       for name in TEST_REPOSITORY_NAMES],
                      command.source_repositories)
    self.assertEquals(os.path.join(TEST_INPUT_DIR, command_name),
                      command.source_code_manager.root_source_dir)

    # Test invocation
    if command_name == FAILURE_COMMAND_NAME:
      with self.assertRaises(ValueError):
        command()
      self.assertIsNone(command.postprocess_dict)
    else:
      self.assertEquals({'foo': 'bar'}, command())
      self.assertEquals(command.postprocess_dict,
                        {name: 'TEST ' + name
                         for name in TEST_REPOSITORY_NAMES})

    self.assertTrue(command.preprocessed)
    self.assertEquals(set(command.source_repositories), command.ensured)
    self.assertEquals(set(command.source_repositories), command.repositories)

    return command

  def test_concurrent_command(self):
    test_command_name = 'concurrent_command'
    options = SimpleNamespace()
    options.one_at_a_time = False
    options.command = test_command_name
    command = self.do_test_command(options, test_command_name)
    self.assertNotEquals(command.test_repo_threadid[0],
                         command.test_repo_threadid[1])

    outcome_name = 'RunCommand_Outcome'
    family = command.metrics.lookup_family_or_none(outcome_name)
    self.assertIsNotNone(family)
    self.assertEquals(family.family_type, family.TIMER)
    self.assertEquals(family.name, outcome_name)
    self.assertEquals(1, len(family.instance_list))
    metric = family.instance_list[0]
    self.assertEquals(1, metric.count)
    self.assertEquals(True, metric.labels.get('success'))
    self.assertEquals(test_command_name, metric.labels.get('command'))

    outcome_name = 'RunRepositoryCommand_Outcome'
    family = command.metrics.lookup_family_or_none(outcome_name)
    self.assertIsNotNone(family)
    self.assertEquals(family.family_type, family.TIMER)
    self.assertEquals(family.name, outcome_name)
    repository_names = set(
        [metric.labels.get('repository')
         for metric in family.instance_list
         if metric.labels.get('command') == test_command_name])
    self.assertEquals(2, len(repository_names))
    self.assertEquals(repository_names, set(TEST_REPOSITORY_NAMES))
    for metric in family.instance_list:
      self.assertEquals(family, metric.family)
      self.assertEquals(outcome_name, metric.name)
      self.assertEquals(1, metric.count)
      self.assertEquals(True, metric.labels.get('success'))

  def test_serialized_command(self):
    test_command_name = 'serialized_command'
    options = SimpleNamespace()
    options.one_at_a_time = True
    options.command = test_command_name
    command = self.do_test_command(options, test_command_name)
    self.assertEquals(command.test_repo_threadid[0],
                      command.test_repo_threadid[1])

  def test_failed_command(self):
    test_command_name = FAILURE_COMMAND_NAME
    options = SimpleNamespace()
    options.one_at_a_time = False
    options.command = test_command_name
    command = self.do_test_command(options, test_command_name)
    self.assertNotEquals(command.test_repo_threadid[0],
                         command.test_repo_threadid[1])

    for test_repository_command in [True, False]:
      outcome_name = ('RunRepositoryCommand_Outcome'
                      if test_repository_command
                      else 'RunCommand_Outcome')
      family = command.metrics.lookup_family_or_none(outcome_name)
      self.assertIsNotNone(family)
      self.assertEquals(family.family_type, family.TIMER)
      self.assertEquals(family.name, outcome_name)
      if test_repository_command:
        repository_names = set([
            metric.labels.get('repository')
            for metric in family.instance_list
            if metric.labels.get('command') == test_command_name])
        self.assertEquals(2, len(repository_names))
        self.assertEquals(repository_names, set(TEST_REPOSITORY_NAMES))

      found = False
      for metric in family.instance_list:
        if metric.labels.get('command') != test_command_name:
          continue  # Metric was from a different test
        found = True
        self.assertEquals(family, metric.family)
        self.assertEquals(outcome_name, metric.name)
        self.assertEquals(1, metric.count)
        self.assertEquals(False, metric.labels.get('success'))
      self.assertTrue(found)

def init_runtime():
  logging.basicConfig(
      format='%(levelname).1s %(asctime)s.%(msecs)03d %(message)s',
      datefmt='%H:%M:%S',
      level=logging.DEBUG)

  class Options(object):
    pass
  options = Options()
  options.metric_name_scope = 'unittest'
  options.monitoring_flush_frequency = -1
  options.monitoring_system = 'file'
  options.monitoring_enabled = False
  MetricsManager.startup_metrics(options)


if __name__ == '__main__':
  init_runtime()
  unittest.main(verbosity=2)
