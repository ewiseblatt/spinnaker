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
import shutil
import tempfile
import unittest

from buildtool import (
    BomSourceCodeManager,
    RepositoryCommandProcessor,
    RepositoryCommandFactory,

    GitRepositorySpec,
    RepositorySummary,

    check_subprocess,
    write_to_path)

from test_util import init_runtime


INPUT_DIR = None
INITIAL_COMMIT = None
TEST_COMMAND_NAME = 'test_command'
TEST_SERVICE_NAME = 'testservice'
TEST_PREFIX = 'testhost/repoowner'
TEST_BRANCH = 'mybranch'
TEST_VERSION = '1.2.3'
TEST_BUILD_VERSION = TEST_VERSION + '-buildnumber'
TEST_TAG = 'version-1.2.3'

class MinimalOptions(object):
  def __init__(self, base_dir):
    self.input_dir = INPUT_DIR
    self.output_dir = os.path.join(base_dir, 'output')


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
    global TEST_PREFIX
    global INPUT_DIR
    global INITIAL_COMMIT
    cls.base_temp_dir = tempfile.mkdtemp(prefix='bomcmd_test')
    TEST_PREFIX = os.path.join(cls.base_temp_dir, 'testhost/repowner')
    INPUT_DIR = os.path.join(cls.base_temp_dir, 'local_sources')

    test_origin = os.path.join(TEST_PREFIX, TEST_SERVICE_NAME)
    write_to_path('initial', os.path.join(test_origin, 'hello.txt'))
    check_subprocess('git init', cwd=test_origin)
    check_subprocess('git add hello.txt', cwd=test_origin)
    check_subprocess('git commit -a -m "initial"', cwd=test_origin)
    INITIAL_COMMIT = check_subprocess('git rev-parse HEAD', cwd=test_origin)
    check_subprocess('git tag ' + TEST_TAG, cwd=test_origin)
    write_to_path('changed', os.path.join(test_origin, 'hello.txt'))
    check_subprocess('git add hello.txt', cwd=test_origin)
    check_subprocess('git commit -m "changed" hello.txt', cwd=test_origin)

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.base_temp_dir)

  def test_repository_command(self):
    bom_path = os.path.join(self.base_temp_dir, 'bom.yml')
    options = MinimalOptions(self.base_temp_dir)
    options.command = TEST_COMMAND_NAME
    options.one_at_a_time = False
    options.bom_path = bom_path
    options.only_repositories = None
    options.github_disable_upstream_push = True

    # Write a bom
    with open(bom_path, 'w') as stream:
      stream.write("""
          artifactSources:
             gitBranch: testBranch
             gitPrefix: {prefix}
          services:
             {service}:
                 commit: {commit}
                 version: {build_version}
      """.format(prefix=TEST_PREFIX, service=TEST_SERVICE_NAME,
                 commit=INITIAL_COMMIT, build_version=TEST_BUILD_VERSION))

    # Create a command referencing that bom we just wrote.
    # That will learn about our test service through that bom
    factory = RepositoryCommandFactory(
        'TestBomRepositoryCommand', TestBomRepositoryCommand,
        'A test command.', BomSourceCodeManager)
    command = factory.make_command(options)

    # Verify that the repository specs this command uses match the bom
    self.assertEquals(
        command.source_repositories,
        [
            GitRepositorySpec(
                TEST_SERVICE_NAME,
                git_dir=os.path.join(
                    INPUT_DIR, TEST_COMMAND_NAME, TEST_SERVICE_NAME),
                origin='%s/%s' % (TEST_PREFIX, TEST_SERVICE_NAME),
                commit_id=INITIAL_COMMIT)
        ])


    # Now run the command and verify it instantiated the working dir
    # as expected.
    command()
    self.assertEquals(
        command.summary_info,
        {
            TEST_SERVICE_NAME: RepositorySummary(
                commit_id=INITIAL_COMMIT,
                tag=TEST_TAG,
                version=TEST_VERSION,
                prev_version=TEST_VERSION,
                commit_messages=[])
        })


if __name__ == '__main__':
  init_runtime()
  unittest.main(verbosity=2)
