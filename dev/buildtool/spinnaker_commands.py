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

"""Implements spinnaker support commands for buildtool."""

import copy
import logging
import os
import yaml

from buildtool import (
    BomSourceCodeManager,
    CommandProcessor,
    CommandFactory,
    GitRunner,
    HalRunner,

    check_options_set,
    write_to_path)


class PublishSpinnakerFactory(CommandFactory):
  """"Implements the publish_spinnaker command."""
  def __init__(self):
    super(PublishSpinnakerFactory, self).__init__(
        'publish_spinnaker', PublishSpinnakerCommand,
        'Publish a spinnaker release')

  def init_argparser(self, parser, defaults):
    super(PublishSpinnakerFactory, self).init_argparser(parser, defaults)
    HalRunner.add_parser_args(parser, defaults)
    GitRunner.add_parser_args(parser, defaults)
    GitRunner.add_publishing_parser_args(parser, defaults)

    self.add_argument(
        parser, 'spinnaker_version', defaults, None,
        help='The spinnaker version to publish.')
    self.add_argument(
        parser, 'spinnaker_release_alias', defaults, None, required=True,
        help='The spinnaker version alias to publish as.')
    self.add_argument(
        parser, 'halyard_bom_bucket', defaults, 'halconfig',
        help='The bucket manaing halyard BOMs and config profiles.')
    self.add_argument(
        parser, 'bom_version', defaults, None,
        help='The existing bom version usef for this release.')
    self.add_argument(
        parser, 'min_halyard_version', defaults, None,
        help='The minimum halyard version required.')


class PublishSpinnakerCommand(CommandProcessor):
  """"Implements the publish_spinnaker command."""
  # pylint: disable=too-few-public-methods

  def __init__(self, factory, options, **kwargs):
    super(PublishSpinnakerCommand, self).__init__(factory, options, **kwargs)
    check_options_set(options, [
        'spinnaker_version',
        'bom_version',
        'github_owner',
        'min_halyard_version'
    ])

    options_copy = copy.copy(options)
    self.__scm = BomSourceCodeManager(options_copy, self.get_input_dir())
    self.__hal = HalRunner(options)
    self.__git = GitRunner(options)
    self.__hal.check_property(
        'spinnaker.config.input.bucket', options.halyard_bom_bucket)

  def push_branches_and_tags(self, bom):
    """Update the release branches and tags in each of the BOM repositires."""
    major, minor, _ = self.options.spinnaker_version.split('.')
    branch = 'release-{major}.{minor}.x'.format(major=major, minor=minor)
    logging.info('Tagging each of the BOM service repos')

    # Run in two passes so we dont push anything if we hit a problem
    # in the tagging pass. Since we are spread against multiple repositiories,
    # we cannot do this atomically. The two passes gives us more protection
    # from a partial push due to errors in a repo.
    for which in ['tag', 'push']:
      for name, spec in bom['services'].items():
        if name in ['monitoring-third-party', 'defaultArtifact']:
          # Ignore this, it is redundant to monitoring-daemon
          continue
        if spec is None:
          logging.warning('HAVE bom.services.%s = None', name)
          continue
        if name == 'monitoring-daemon':
          name = 'spinnaker-monitoring'
        repository = self.__scm.make_repository_spec(name)
        self.__scm.ensure_local_repository(repository)
        if which == 'tag':
          self.__branch_and_tag_repository(repository, branch)
        else:
          self.__push_branch_and_tag_repository(repository, branch)

  def __branch_and_tag_repository(self, repository, branch):
    """Create a branch and/or verison tag in the repository, if needed."""
    source_info = self.__scm.lookup_source_info(repository)
    tag = 'version-' + source_info.summary.version
    self.__git.check_run(repository.git_dir, 'tag ' + tag)

  def __push_branch_and_tag_repository(self, repository, branch):
    """Push the branch and verison tag to the origin."""
    source_info = self.__scm.lookup_source_info(repository)
    tag = 'version-' + source_info.summary.version
    self.__git.push_branch_to_origin(repository.git_dir, branch)
    self.__git.push_tag_to_origin(repository.git_dir, tag)

  def _do_command(self):
    """Implements CommandProcessor interface."""
    options = self.options
    spinnaker_version = options.spinnaker_version
    bom = self.__hal.retrieve_bom_version(self.options.bom_version)
    bom['version'] = spinnaker_version

    self.push_branches_and_tags(bom)
    bom_path = os.path.join(self.get_output_dir(), spinnaker_version + '.yml')
    changelog_base_url = 'https://www.spinnaker.io/%s' % options.github_owner
    changelog_filename = '%s-changelog' % spinnaker_version.replace('.', '-')
    changelog_uri = '%s/community/releases/versions/%s' % (
        changelog_base_url, changelog_filename)

    write_to_path(yaml.dump(bom, default_flow_style=False), bom_path)
    self.__hal.publish_spinnaker_release(
        spinnaker_version, options.spinnaker_release_alias, changelog_uri,
        options.min_halyard_version)


def register_commands(registry, subparsers, defaults):
  PublishSpinnakerFactory().register(registry, subparsers, defaults)
