# Copyright 2018 Google Inc. All Rights Reserved.
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

import argparse
import datetime
import os
import tempfile
import textwrap
import unittest

import yaml

import buildtool.__main__ as bomtool_main
import buildtool.spinnaker_commands
from buildtool import (
    GitRunner)
    
from test_util import (
    init_runtime,
    BaseGitRepoTestFixture
    )


class TestSpinnakerCommandFixture(BaseGitRepoTestFixture):
  def setUp(self):
    super(TestSpinnakerCommandFixture, self).setUp()
    self.parser = argparse.ArgumentParser()
    self.subparsers = self.parser.add_subparsers(title='command', dest='command')

  def make_test_options(self):
    class Options(object):
      pass
    return Options()

  def test_new_release_branch_command(self):
    test_root = os.path.join(self.base_temp_dir, 'test_new_release_branch')
    defaults = {
      'input_dir': os.path.join(test_root, 'input_dir'),
      'output_dir': os.path.join(test_root, 'output_dir'),

      'only_repositories': 'extra-test-repo',
      'github_owner': 'default',
      'git_branch': 'extra-test-repo-branch',

      'spinnaker_version': 'NewSpinnakerVersion',

      'github_filesystem_root': self.base_temp_dir,
      'scm_repository_spec_path': os.path.join(
            os.path.dirname(__file__), 'standard_test_repositories.yml')
    }

    registry = {}
    bomtool_main.add_standard_parser_args(self.parser, defaults)
    buildtool.spinnaker_commands.register_commands(
        registry, self.subparsers, defaults)

    factory = registry['new_release_branch']
    factory.init_argparser(self.parser, defaults)

    options = self.parser.parse_args(['new_release_branch'])

    mock_push_tag = self.patch_method(GitRunner, 'push_tag_to_origin')
    mock_push_branch = self.patch_method(GitRunner, 'push_branch_to_origin')

    command = factory.make_command(options)
    command()

    base_git_dir = os.path.join(options.input_dir, 'new_release_branch')
    self.assertEquals(os.listdir(base_git_dir), ['extra-test-repo'])
    git_dir = os.path.join(base_git_dir, 'extra-test-repo')
    self.assertEquals(
        GitRunner(options).query_local_repository_commit_id(git_dir),
        self.repo_commit_map['extra-test-repo']['extra-test-repo-branch'])

    mock_push_branch.assert_called_once_with(git_dir, 'NewSpinnakerVersion')
    self.assertEquals(0, mock_push_tag.call_count)


if __name__ == '__main__':
  init_runtime()
  unittest.main(verbosity=2)
