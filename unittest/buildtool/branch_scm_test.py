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

# pylint: disable=missing-docstring
# pylint: disable=invalid-name

import argparse
import os
import unittest

from buildtool import (
    DEFAULT_BUILD_NUMBER,
    GitRunner,
    SemanticVersion,
    BranchSourceCodeManager,
    ConfigError)

from test_util import (
    ALL_STANDARD_TEST_REPO_NAMES,
    BASE_VERSION_TAG,
    OUTLIER_GIT_HOST,
    OUTLIER_GIT_OWNER,
    UNTAGGED_BRANCH,
    BaseGitRepoTestFixture,
    init_runtime)


class TestSourceCodeManager(BaseGitRepoTestFixture):
  def make_test_options(self):
    """Helper function for creating default options for runner."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--output_dir',
        default=os.path.join('/tmp', 'scmtest.%d' % os.getpid()))
    GitRunner.add_parser_args(parser, {'github_owner': 'default'})
    options = parser.parse_args([])
    options.command = 'test-command'
    options.git_branch = 'testing'
    options.scm_repository_spec_path = os.path.join(
        os.path.dirname(__file__), 'standard_test_repositories.yml')
    return options

  def do_test_source_repositories(self, owner):
    test_root = os.path.join(self.base_temp_dir, 'test_source_repositories')
    self.options.github_owner = owner
    scm = BranchSourceCodeManager(self.options, test_root)
    source_repositories = scm.filter_source_repositories(scm.all_filter)
    self.assertEquals(sorted([repo.name for repo in source_repositories]),
                      sorted(ALL_STANDARD_TEST_REPO_NAMES))

    for repo in source_repositories:
      self.assertEquals(repo.git_dir, os.path.join(test_root, repo.name))
      self.assertFalse(os.path.exists(repo.git_dir))
      self.assertEquals(repo.upstream, self.to_origin(repo.name))
      self.assertEquals(repo, scm.make_repository_spec(repo.name))
      self.assertFalse(os.path.exists(repo.git_dir))

      if owner == 'default':
        self.assertEquals(repo.origin,
                          self.repo_commit_map[repo.name]['ORIGIN'])
        self.assertEquals(repo.origin, self.to_origin(repo.name))
      else:
        # The origin will be the normal upstream git server, but
        # with a forked repo owned by the owner.
        default_origin = self.to_origin(repo.name)
        owner_parent = os.path.dirname(os.path.dirname(default_origin))
        user_origin = os.path.join(owner_parent, owner, repo.name)
        self.assertEquals(repo.origin, user_origin)

  def test_source_repositories_from_default(self):
    self.do_test_source_repositories('default')

  def test_source_repositories_from_user(self):
    self.do_test_source_repositories('random-user')

  def test_maybe_pull_repository_branch(self):
    test_root = os.path.join(self.base_temp_dir, 'pulled_test')
    self.options.git_branch = UNTAGGED_BRANCH
    self.options.build_number = 'maybe_pull_branch_buildnum'
    scm = BranchSourceCodeManager(self.options, test_root)

    for repository in scm.filter_source_repositories(scm.all_filter):
      scm.ensure_local_repository(repository)

      git_dir = repository.git_dir
      spec = scm.git.determine_git_repository_spec(git_dir)
      self.assertEquals(repository.name, spec.name)
      self.assertEquals(repository.git_dir, spec.git_dir)
      self.assertEquals(repository.origin, spec.origin)
      self.assertIsNone(spec.upstream_or_none())

      in_branch = scm.git.query_local_repository_branch(git_dir)
      self.assertEquals(UNTAGGED_BRANCH, in_branch)

      summary = scm.git.collect_repository_summary(git_dir)
      semver = SemanticVersion.make(BASE_VERSION_TAG)
      expect_version = semver.next(
          SemanticVersion.MINOR_INDEX).to_version()

      self.assertEquals(expect_version, summary.version)

  def test_pull_repository_fallback_branch(self):
    test_root = os.path.join(self.base_temp_dir, 'fallback_test')
    unique_branch = 'outlier-test-repo-branch'
    self.options.git_branch = unique_branch
    self.options.git_fallback_branch = 'master'
    self.options.build_number = 'pull_repository_fallback_buildnumber'
    scm = BranchSourceCodeManager(self.options, test_root)

    for repository in scm.filter_source_repositories(scm.all_filter):
      scm.ensure_local_repository(repository)
      git_dir = repository.git_dir
      want_branch = (unique_branch
                     if repository.name == 'outlier-test-repo'
                     else 'master')
      in_branch = scm.git.query_local_repository_branch(git_dir)
      self.assertEquals(want_branch, in_branch)

  def test_foreach_repo(self):
    test_root = os.path.join(self.base_temp_dir, 'foreach_test')
    pos_args = [1, 2, 3]
    kwargs = {'a': 'A', 'b': 'B'}

    scm = BranchSourceCodeManager(self.options, test_root)
    all_repos = scm.filter_source_repositories(scm.all_filter)
    expect = {
        repository.name: (repository, pos_args, kwargs)
        for repository in all_repos
    }

    def _foreach_func(repository, *pos_args, **kwargs):
      self.assertFalse(os.path.exists(repository.git_dir))
      return (repository, list(pos_args), dict(kwargs))
    got = scm.foreach_source_repository(
        all_repos, _foreach_func, *pos_args, **kwargs)
    self.assertEquals(expect, got)


  def test_get_repository_db(self):
    test_root = os.path.join(self.base_temp_dir, 'test_db')
    scm = BranchSourceCodeManager(self.options, test_root)
    entry = scm.repository_name_to_database_entry('outlier-test-repo')
    self.assertEquals(entry.get('service_name'), 'outlier-test-service')

  def test_get_repository_db_failure(self):
    test_root = os.path.join(self.base_temp_dir, 'test_db')
    scm = BranchSourceCodeManager(self.options, test_root)
    with self.assertRaises(ConfigError):
      scm.repository_name_to_database_entry('unknown-repo')

  def test_build_number(self):
    test_root = os.path.join(self.base_temp_dir, 'test_db')
    self.options.build_number = 'TheBuildNumber'
    scm = BranchSourceCodeManager(self.options, test_root)
    repository = scm.make_repository_spec('outlier-test-repo')
    self.assertEquals('TheBuildNumber',
                      scm.determine_build_number(repository))

    self.options.build_number = None
    scm = BranchSourceCodeManager(self.options, test_root)
    self.assertEquals(DEFAULT_BUILD_NUMBER,
                      scm.determine_build_number(repository))

  def test_repository_filter(self):
    test_root = os.path.join(self.base_temp_dir, 'test_db')
    scm = BranchSourceCodeManager(self.options, test_root)
    not_in_bom = lambda name, entry: not entry.get('in_bom', False)
    repositories = scm.filter_source_repositories(not_in_bom)
    self.assertEquals(repositories,
                      [scm.make_repository_spec('extra-test-repo')])

  def test_repository_spec(self):
    test_root = os.path.join(self.base_temp_dir, 'test_db')

    # Use an origin off our local filesystem (for testing)
    self.options.github_owner = 'default'
    self.options.github_filesystem_root = self.base_temp_dir
    scm = BranchSourceCodeManager(self.options, test_root)
    repository = scm.make_repository_spec('outlier-test-repo')
    self.assertEquals(repository.git_dir,
                      os.path.join(test_root, 'outlier-test-repo'))
    self.assertEquals(repository.origin,
                      self.repo_commit_map['outlier-test-repo']['ORIGIN'])
    self.assertEquals(repository.upstream,
                      os.path.join(self.base_temp_dir,
                                   OUTLIER_GIT_HOST,
                                   OUTLIER_GIT_OWNER,
                                   'outlier-test-repo'))

    # Use authoritative repo (the upstream owner)
    self.options.github_owner = 'default'
    self.options.github_filesystem_root = None
    scm = BranchSourceCodeManager(self.options, test_root)
    repository = scm.make_repository_spec('outlier-test-repo')
    self.assertEquals(repository.git_dir,
                      os.path.join(test_root, 'outlier-test-repo'))
    self.assertEquals(repository.origin,
                      'https://{host}/{owner}/outlier-test-repo'.format(
                          host=OUTLIER_GIT_HOST, owner=OUTLIER_GIT_OWNER))
    self.assertEquals(repository.upstream,
                      'https://{host}/{owner}/outlier-test-repo'.format(
                          host=OUTLIER_GIT_HOST, owner=OUTLIER_GIT_OWNER))

    # Use particular user clone rather than default
    self.options.github_owner = 'TestUser'
    scm = BranchSourceCodeManager(self.options, test_root)
    repository = scm.make_repository_spec('outlier-test-repo')
    self.assertEquals(repository.git_dir,
                      os.path.join(test_root, 'outlier-test-repo'))
    self.assertEquals(repository.origin,
                      'https://{host}/TestUser/outlier-test-repo'.format(
                          host=OUTLIER_GIT_HOST))
    self.assertEquals(repository.upstream,
                      'https://{host}/{owner}/outlier-test-repo'.format(
                          host=OUTLIER_GIT_HOST, owner=OUTLIER_GIT_OWNER))

    # Use SSH rather than HTTPS
    self.options.github_owner = 'TestUser'
    self.options.github_pull_ssh = True
    scm = BranchSourceCodeManager(self.options, test_root)
    repository = scm.make_repository_spec('outlier-test-repo')
    self.assertEquals(repository.git_dir,
                      os.path.join(test_root, 'outlier-test-repo'))
    self.assertEquals(repository.origin,
                      'git@{host}:TestUser/outlier-test-repo'.format(
                          host=OUTLIER_GIT_HOST))
    self.assertEquals(repository.upstream,
                      'git@{host}:{owner}/outlier-test-repo'.format(
                          host=OUTLIER_GIT_HOST, owner=OUTLIER_GIT_OWNER))
    # Actual local repository is not yet cloned.
    self.assertFalse(os.path.exists(repository.git_dir))


if __name__ == '__main__':
  init_runtime()
  unittest.main(verbosity=2)
