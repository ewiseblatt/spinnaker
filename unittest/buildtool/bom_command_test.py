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

import argparse
import datetime
import os
import tempfile
import textwrap
import unittest
from mock import patch

import yaml

from test_util import init_runtime

from buildtool import (
    DEFAULT_BUILD_NUMBER,
    BranchSourceCodeManager,
    GitRepositorySpec,
    RepositorySummary,
    SourceInfo)
import buildtool

import buildtool.__main__ as bomtool_main
import buildtool.bom_commands
from buildtool.bom_commands import (
    BomBuilder, BuildBomCommand)


class MinOptions(object):
  def __init__(self):
    self.git_branch = 'OptionBranch'
    self.bom_dependencies_path = None
    self.build_number = 'OptionBuildNumber'
    self.bintray_org = 'TestBintrayOrg'
    self.bintray_debian_repository = 'TestDebianRepo'
    self.docker_registry = 'TestDockerRegistry'
    self.publish_gce_image_project = 'TestGceProject'


def load_default_bom_dependencies():
  path = os.path.join(os.path.dirname(__file__),
                      '../../dev/buildtool/bom_dependencies.yml')
  with open(path, 'r') as stream:
    return yaml.load(stream.read())

class TestBuildBomCommand(unittest.TestCase):
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

  def setUp(self):
    self.parser = argparse.ArgumentParser()
    self.subparsers = self.parser.add_subparsers()

  def test_default_bom_options(self):
    registry = {}
    buildtool.bom_commands.register_commands(registry, self.subparsers, {})
    self.assertTrue('build_bom' in registry)
    self.assertTrue('publish_bom' in registry)

    options = self.parser.parse_args(['build_bom'])
    option_dict = vars(options)

    # Of our min options, only build number should be set
    min_options = MinOptions()
    min_option_dict = vars(min_options)
    self.assertEquals(DEFAULT_BUILD_NUMBER, options.build_number)
    del(min_option_dict['build_number'])

    for key in ['bom_path', 'github_owner']:
      self.assertIsNone(option_dict[key])

    for key in min_option_dict.keys():
      self.assertIsNone(option_dict[key])

  def test_bom_option_default_overrides(self):
    defaults = {'not_used': False}
    min_option_dict = vars(MinOptions())
    defaults.update(min_option_dict)

    registry = {}
    buildtool.bom_commands.register_commands(
        registry, self.subparsers, defaults)
    options = self.parser.parse_args(['build_bom'])
    option_dict = vars(options)

    self.assertTrue('not_used' not in option_dict)
    for key, value in min_option_dict.items():
      self.assertEquals(value, option_dict[key])

  def test_bom_command(self):
    """Make sure when we run "build_bom" we actually get what we meant."""
    defaults = {'bom_path': 'MY PATH',
                'github_owner': 'TestOwner',
                'input_dir': 'TestInputRoot'}
    defaults.update(vars(MinOptions()))

    parser = argparse.ArgumentParser()
    registry = bomtool_main.make_registry([buildtool.bom_commands],
                                          parser, defaults)
    bomtool_main.add_standard_parser_args(parser, defaults)
    options = parser.parse_args(['build_bom'])

    prefix = 'http://test-domain.com/test-owner'

    make_fake = self.patch_method

    # When asked to filter the normal bom repos to determine source_repositories
    # we'll return our own fake repository as if we configured the original
    # command for it. This will also make it easier to test just the one
    # repo rather than all, and that there are no assumptions.
    mock_filter = make_fake(BuildBomCommand, 'filter_repositories')
    test_repository = GitRepositorySpec('TestRepoA', commit_id='CommitA',
                                        origin=prefix + '/TestRepoA')
    mock_filter.return_value = [test_repository]

    # When the base command ensures the local repository exists, we'll
    # intercept that call and do nothing rather than the git checkouts, etc.
    make_fake(BranchSourceCodeManager, 'ensure_local_repository')

    # When the base command asks for the repository metadata, we'll return
    # this hardcoded info, then look for it later in the generated om.
    mock_lookup = make_fake(BranchSourceCodeManager, 'lookup_source_info')
    summary = RepositorySummary('CommitA', 'TagA', '9.8.7', '44.55.66', [])
    source_info = SourceInfo('MyBuildNumber', summary)
    mock_lookup.return_value = source_info

    # When asked to write the bom out, do nothing.
    # We'll verify the bom later when looking at the mock call sequencing.
    mock_write = self.patch_function('buildtool.bom_commands.write_to_path')

    mock_now = self.patch_function('buildtool.bom_commands.now')
    mock_now.return_value = datetime.datetime(2018, 1, 2, 3, 4, 5)

    factory = registry['build_bom']
    command = factory.make_command(options)
    command()

    # Verify source repositories were filtered
    self.assertEquals([test_repository], command.source_repositories)

    # Verify that the filter was called with the original bom repos,
    # and these repos were coming from the configured github_owner's repo.
    bom_repo_list = [
        GitRepositorySpec(
            name,
            git_dir=os.path.join('TestInputRoot', 'build_bom', name),
            origin='https://github.com/TestOwner/' + name,
            upstream='https://github.com/spinnaker/' + name)
        for name in sorted(['clouddriver', 'deck', 'echo', 'fiat', 'front50',
                            'gate', 'igor', 'orca', 'rosco', 'spinnaker',
                            'spinnaker-monitoring'])
    ]
    mock_filter.assert_called_once_with(bom_repo_list)
    mock_lookup.assert_called_once_with(test_repository)
    bom_text, bom_path = mock_write.call_args_list[0][0]

    self.assertEquals(bom_path, 'MY PATH')
    bom = yaml.load(bom_text)

    golden_text = textwrap.dedent("""\
        artifactSources:
          debianRepository: https://dl.bintray.com/TestBintrayOrg/TestDebianRepo
          dockerRegistry: TestDockerRegistry
          gitPrefix: http://test-domain.com/test-owner
          googleImageProject: TestGceProject
        dependencies:
        services:
          TestRepoA:
            commit: CommitA
            version: 9.8.7-MyBuildNumber
        timestamp: '2018-01-02 03:04:05'
        version: OptionBranch-OptionBuildNumber
    """)
    golden_bom = yaml.load(golden_text)
    golden_bom['dependencies'] = load_default_bom_dependencies()

    for key, value in golden_bom.items():
      self.assertEquals(value, bom[key])


class TestBomBuilder(unittest.TestCase):
  def test_default_build(self):
    builder = BomBuilder(MinOptions())
    bom = builder.build()
    self.assertEquals(
        bom['dependencies'], load_default_bom_dependencies())

  def test_inject_dependencies(self):
    dependencies = {
        'DependencyA': {'version': 'vA'},
        'DependencyB': {'version': 'vB'}
    }
    fd, path = tempfile.mkstemp(prefix='bomdeps')
    os.close(fd)
    with open(path, 'w') as stream:
      yaml.dump(dependencies, stream)

    options = MinOptions()
    options.bom_dependencies_path = path
    try:
      builder = BomBuilder(options)
      bom = builder.build()
    finally:
      os.remove(path)

    self.assertEquals(dependencies, bom['dependencies'])

  def test_build(self):
    prefixes = ['http://github.com/one', '/local/source/path/two']
    branches = ['BranchOne', 'BranchTwo']

    dependencies = {
        'DependencyA': {'version': 'vA'},
        'DependencyB': {'version': 'vB'}
    }
    fd, dependencies_path = tempfile.mkstemp(prefix='bomdeps')
    os.close(fd)
    with open(dependencies_path, 'w') as stream:
      yaml.dump(dependencies, stream)

    options = MinOptions()
    options.bom_dependencies_path = dependencies_path
    builder = BomBuilder(options)

    repository = GitRepositorySpec(
        'RepoOutlier', origin=prefixes[0] + '/RepoOutlier',
        commit_id='RepoOutlierCommit', branch=branches[0])
    summary = RepositorySummary('RepoOutlierCommit', 'RepoOutlierTag',
                                '1.2.3', '1.2.2', [])
    source_info = SourceInfo('BuildOutlier', summary)
    builder.add_repository(repository, source_info)
    for name in ['A', 'B']:
      repository = GitRepositorySpec(
          'Repo' + name, origin=prefixes[1] + '/RepoOutlier',
          commit_id='RepoCommit' + name, branch=branches[1])
      summary = RepositorySummary(
          'RepoCommit' + name, 'RepoTag' + name,
          '2.3.' + str(ord(name) - ord('A')), '2.3.0', [])
      source_info = SourceInfo('Build' + name, summary)
      builder.add_repository(repository, source_info)

    with patch('buildtool.bom_commands.now') as mock_now:
      mock_now.return_value = datetime.datetime(2018, 1, 2, 3, 4, 5)
      bom = builder.build()
    os.remove(dependencies_path)

    golden_text = textwrap.dedent("""
        artifactSources:
          debianRepository: https://dl.bintray.com/TestBintrayOrg/TestDebianRepo
          dockerRegistry: TestDockerRegistry
          gitPrefix: /local/source/path/two
          googleImageProject: TestGceProject
        dependencies:
          DependencyA:
             version: vA
          DependencyB:
             version: vB
        services:
          RepoOutlier:
            commit: RepoOutlierCommit
            version: 1.2.3-BuildOutlier
            gitPrefix: http://github.com/one
          RepoA:
            commit: RepoCommitA
            version: 2.3.0-BuildA
          RepoB:
            commit: RepoCommitB
            version: 2.3.1-BuildB
        timestamp: '2018-01-02 03:04:05'
        version: OptionBranch-OptionBuildNumber
        """)

    golden_bom = yaml.load(golden_text)
    for key, value in bom.items():
      self.assertEquals(value, golden_bom[key])
    self.assertEquals(golden_bom, bom)

  def test_rebuild(self):
    original_text = textwrap.dedent("""
        artifactSources:
          debianRepository: https://dl.bintray.com/TestBintrayOrg/TestDebianRepo
          dockerRegistry: TestDockerRegistry
          gitPrefix: /local/source/path/two
          googleImageProject: TestGceProject
        dependencies:
          DependencyA:
             version: vA
          DependencyB:
             version: vB
        services:
          RepoOutlier:
            commit: RepoOutlierCommit
            version: 1.2.3-BuildOutlier
            gitPrefix: http://github.com/one
          RepoA:
            commit: RepoCommitA
            version: 2.3.0-BuildA
          RepoB:
            commit: RepoCommitB
            version: 2.3.1-BuildB
        timestamp: '2018-05-04 03:02:01'
        version: OptionBranch-OptionBuildNumber
        """)

    options = MinOptions()
    options.build_number = 'UpdatedBuildNumber'
    options.defaults = {}
    options.defaults['bom_dependencies'] = {
        'DependencyA': {'version': 'vA'},
        'DependencyB': {'version': 'vB'}}

    original_bom = yaml.load(original_text)
    builder = BomBuilder.new_from_bom(options, original_bom)

    repository = GitRepositorySpec(
        'RepoOutlier',
        origin='/local/source/path/two/RepoOutlier',
        commit_id='UpdatedCommitId')

    summary = RepositorySummary('UpdatedCommitId', 'UpdatedTag',
                                '1.2.4', '1.2.3', [])
    source_info = SourceInfo('SourceInfoBuildNumber', summary)
    builder.add_repository(repository, source_info)

    with patch('buildtool.bom_commands.now') as mock_now:
      mock_now.return_value = datetime.datetime(2018, 1, 2, 3, 4, 5)
      bom = builder.build()

    self.assertEquals(original_bom, yaml.load(original_text))
    updated_service = bom['services']['RepoOutlier']
    self.assertEquals(updated_service, {
        'commit': 'UpdatedCommitId',
        'version': '1.2.4-SourceInfoBuildNumber',
        })

    # The bom should be the same as before, but with new timestamp/version
    # and our service updated
    original_bom['timestamp'] = '2018-01-02 03:04:05'
    original_bom['version'] = 'OptionBranch-UpdatedBuildNumber'
    original_bom['services']['RepoOutlier'] = updated_service
    for key, value in original_bom.items():
      self.assertEquals(value, bom[key])
    self.assertEquals(original_bom, bom)

  def test_determine_most_common_prefix(self):
    class Options(object):
      pass
    options = Options()
    options.bom_dependencies_path = None
    builder = BomBuilder(options)
    self.assertIsNone(builder.determine_most_common_prefix())

    prefixes = ['http://github.com/one', '/local/source/path/two']
    branches = ['BranchOne', 'BranchTwo']

    # Test two vs one in from different repo prefixes
    # run the test twice changing the ordering the desired prefix is visible.
    for which in [0, 1]:
      repository = GitRepositorySpec(
          'RepoOne', origin=prefixes[0] + '/RepoOne',
          commit_id='RepoOneCommit', branch=branches[0])
      summary = RepositorySummary('RepoOneCommit', 'RepoOneTag',
                                  '1.2.3', '1.2.2', [])
      source_info = SourceInfo('BuildOne', summary)
      builder.add_repository(repository, source_info)
      self.assertEquals(prefixes[0], builder.determine_most_common_prefix())

      repository = GitRepositorySpec(
          'RepoTwo', origin=prefixes[which] + '/RepoTwo',
          commit_id='RepoTwoCommit', branch=branches[which])
      summary = RepositorySummary('RepoTwoCommit', 'RepoTwoTag',
                                  '2.2.3', '2.2.3', [])
      source_info = SourceInfo('BuildTwo', summary)
      builder.add_repository(repository, source_info)

      repository = GitRepositorySpec(
          'RepoThree', origin=prefixes[1] + '/RepoThree',
          commit_id='RepoThreeCommit', branch=branches[1])
      summary = RepositorySummary('RepoThreeCommit', 'RepoThreeTag',
                                  '3.2.0', '2.2.1', [])
      source_info = SourceInfo('BuildThree', summary)
      builder.add_repository(repository, source_info)

      self.assertEquals(prefixes[which], builder.determine_most_common_prefix())


if __name__ == '__main__':
  init_runtime()
  unittest.main(verbosity=2)
