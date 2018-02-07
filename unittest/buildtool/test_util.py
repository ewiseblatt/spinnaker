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
import yaml
from mock import patch


from buildtool import (
    check_subprocess_sequence,
    check_subprocess,
    MetricsManager)


def init_runtime(options=None):
  logging.basicConfig(
      format='%(levelname).1s %(asctime)s.%(msecs)03d %(message)s',
      datefmt='%H:%M:%S',
      level=logging.DEBUG)

  if not options:
    class Options(object):
      pass
    options = Options()
    options.metric_name_scope = 'unittest'
    options.monitoring_flush_frequency = -1
    options.monitoring_system = 'file'
    options.monitoring_enabled = False

  MetricsManager.startup_metrics(options)


#  These names should align with the standard_test_repositories.yml
STANDARD_GIT_HOST = 'test-gitserver'
OUTLIER_GIT_HOST = 'outlier-gitserver'
STANDARD_GIT_OWNER = 'test-owner'
OUTLIER_GIT_OWNER = 'outlier-owner'

BASE_VERSION_TAG = 'version-7.8.9'
PATCH_VERSION_TAG = 'version-7.8.10'
PATCH_VERSION_NUMBER = '7.8.10'
PATCH_BRANCH = 'patch'
UNTAGGED_BRANCH = 'untagged-branch'


def make_standard_git_repo(git_dir):
  """Initialize local git repos corresponding to standard_test_repositories.yml

  These are used by tests that interact with a git repository.
  """
  branch_commits = {'ORIGIN': git_dir}
  repo_name = os.path.basename(git_dir)

  run_git = lambda cmd: 'git %s' % cmd
  os.makedirs(git_dir)
  logging.debug('Initializing git repository in "%s"', git_dir)

  check_subprocess_sequence(
      [
          'touch  %s-basefile.txt' % repo_name,
          run_git('init'),
          run_git('add %s-basefile.txt' % repo_name),
          run_git('commit -a -m "feat(first): first commit"'),
          run_git('tag %s HEAD' % BASE_VERSION_TAG),
      ],
      cwd=git_dir)
  branch_commits['master'] = check_subprocess('git rev-parse HEAD', cwd=git_dir)

  check_subprocess_sequence(
      [
          run_git('checkout -b ' + PATCH_BRANCH),
          'touch %s-patchfile.txt' % repo_name,
          run_git('add %s-patchfile.txt' % repo_name),
          run_git('commit -a -m "fix(patch): added patch change"')
      ],
      cwd=git_dir)
  branch_commits[PATCH_BRANCH] = check_subprocess(
      'git rev-parse HEAD', cwd=git_dir)

  check_subprocess_sequence(
      [
          run_git('checkout master'),
          run_git('checkout -b %s-branch' % repo_name),
          'touch %s-unique.txt' % repo_name,
          run_git('add %s-unique.txt' % repo_name),
          run_git('commit -a -m "chore(uniq): unique commit"')
      ],
      cwd=git_dir)
  branch_commits['%s-branch' % repo_name] = check_subprocess(
      'git rev-parse HEAD', cwd=git_dir)

  check_subprocess_sequence(
      [
          run_git('checkout master'),
          run_git('checkout -b %s' % UNTAGGED_BRANCH),
          'touch %s-untagged.txt' % repo_name,
          run_git('add %s-untagged.txt' % repo_name),
          run_git('commit -a -m "chore(uniq): untagged commit"'),
      ],
      cwd=git_dir)
  branch_commits[UNTAGGED_BRANCH] = check_subprocess(
      'git rev-parse HEAD', cwd=git_dir)

  return branch_commits

ALL_STANDARD_TEST_REPO_NAMES = ['normal-test-service', 'outlier-test-repo',
                                'extra-test-repo']

def make_all_standard_git_repos(base_dir):
  """Creates git repositories for each in test_scm_repositories.yml"""

  result = {}

  path = os.path.join(base_dir, STANDARD_GIT_HOST, STANDARD_GIT_OWNER,
                      'normal-test-service')
  result['normal-test-service'] = make_standard_git_repo(path)

  path = os.path.join(base_dir, STANDARD_GIT_HOST, STANDARD_GIT_OWNER,
                      'extra-test-repo')
  result['extra-test-repo'] = make_standard_git_repo(path)

  path = os.path.join(base_dir, OUTLIER_GIT_HOST, OUTLIER_GIT_OWNER,
                      'outlier-test-repo')
  result['outlier-test-repo'] = make_standard_git_repo(path)

  return result


class BaseGitRepoTestFixture(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.base_temp_dir = tempfile.mkdtemp(prefix='bom_scm_test')
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
        entry['commit'] = cls.repo_commit_map[name][PATCH_BRANCH]

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.base_temp_dir)

  @classmethod
  def to_origin(cls, repo_name):
    return cls.repo_commit_map[repo_name]['ORIGIN']

  def patch_function(self, name):
    patcher = patch(name)
    hook = patcher.start()
    self.addCleanup(patcher.stop)
    return hook

  def patch_method(self, klas, method):
    patcher = patch.object(klas, method)
    hook = patcher.start()
    self.addCleanup(patcher.stop)
    return hook

  def make_test_options(self):
    class Options(object):
      pass
    options = Options()
    return options

  def setUp(self):
    self.options = self.make_test_options()
    self.options.github_filesystem_root = self.base_temp_dir
    self.options.command = self._testMethodName
