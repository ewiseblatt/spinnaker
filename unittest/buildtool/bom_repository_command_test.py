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

import os
import shutil
import tempfile
import unittest
import yaml

from buildtool import (
    BomSourceCodeManager,
    RepositoryCommandProcessor,
    RepositoryCommandFactory)

from test_util import (
    make_all_standard_git_repos,
    init_runtime)


class TestBomRepositoryCommand(RepositoryCommandProcessor):
  def __init__(self, *pos_args, **kwargs):
    super(TestBomRepositoryCommand, self).__init__(*pos_args, **kwargs)
    self.summary_info = {}

  def _do_repository(self, repository):
    name = repository.name
    assert(name not in self.summary_info)
    self.summary_info[name] = self.scm.git.collect_repository_summary(
        repository.git_dir)


class TestBomRepositoryCommandProcessor(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.base_temp_dir = tempfile.mkdtemp(prefix='bomcmd_test')
    cls.repo_commit_map = make_all_standard_git_repos(cls.base_temp_dir)

    source_path = os.path.join(os.path.dirname(__file__),
                               'standard_test_bom.yml')

    # Adjust the golden bom so it references the details of
    # the test instance specific origin repo we just created in test_util.
    with open(source_path, 'r') as stream:
      cls.golden_bom = yaml.load(stream.read())

      #  Change the bom's default gitPrefix to our origin root
      cls.golden_bom['artifactSources']['gitPrefix'] = (
          os.path.dirname(cls.repo_commit_map['normal-test-service']['ORIGIN']))

      #  Change the outlier git repo to its origin root
      cls.golden_bom['services']['outlier-test-service']['gitPrefix'] = (
          os.path.dirname(cls.repo_commit_map['outlier-test-repo']['ORIGIN']))

      # Update the service commit id's in the BOM to the actual id's
      # so we can check them out later.
      services = cls.golden_bom['services']
      for name, entry in services.items():
        if name == 'outlier-test-service':
          name = 'outlier-test-repo'
        entry['commit'] = cls.repo_commit_map[name][name + '-branch']

    cls.__bom_path = os.path.join(cls.base_temp_dir, 'test-bom.yml')
    with open(cls.__bom_path, 'w') as stream:
      stream.write(yaml.dump(cls.golden_bom))

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.base_temp_dir)

  def make_minimal_options(self):
    class Options(object):
      pass
    options = Options()
    options.github_filesystem_root = self.base_temp_dir
    options.input_dir = os.path.join(self.base_temp_dir, 'input_dir')
    options.output_dir = os.path.join(self.base_temp_dir, 'output_dir')
    options.only_repositories = None
    options.github_disable_upstream_push = True
    options.one_at_a_time = False
    options.scm_repository_spec_path = os.path.join(
        os.path.dirname(__file__), 'standard_test_repositories.yml')
    return options

  def test_repository_command(self):
    options = self.make_minimal_options()
    options.command = 'test_command'
    options.bom_path = self.__bom_path

    # Create a command referencing our test bom
    # That will learn about our test service through that bom
    factory = RepositoryCommandFactory(
        'TestBomRepositoryCommand', TestBomRepositoryCommand,
        'A test command.', BomSourceCodeManager)
    command = factory.make_command(options)

    for repository in command.source_repositories:
      self.assertEquals(
          repository.origin, self.repo_commit_map[repository.name]['ORIGIN'])
      self.assertEquals(
          repository.git_dir,
          os.path.join(os.path.join(self.base_temp_dir, 'input_dir',
                                    'test_command', repository.name)))
      self.assertFalse(os.path.exists(repository.git_dir))

    self.assertEquals(set(['normal-test-service', 'outlier-test-repo']),
                      set([repo.name for repo in command.source_repositories]))
    self.assertEquals(
        command.scm.repository_name_to_service_name('normal-test-service'),
        'normal-test-service')
    self.assertEquals(
        command.scm.repository_name_to_service_name('outlier-test-repo'),
        'outlier-test-service')

    # Now run the command and verify it instantiated the working dir
    # a the expected commit.
    command()

    for repository in command.source_repositories:
      self.assertTrue(os.path.exists(repository.git_dir))
      self.assertEquals(
          command.summary_info[repository.name].commit_id,
          self.repo_commit_map[repository.name][repository.name + '-branch'])


if __name__ == '__main__':
  init_runtime()
  unittest.main(verbosity=2)
