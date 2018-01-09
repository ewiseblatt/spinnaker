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

"""Source code manager that uses git branches."""

import logging
import os

from buildtool import (
    DEFAULT_BUILD_NUMBER,
    GitRunner,
    SpinnakerSourceCodeManager,

    add_parser_argument,
    check_kwargs_empty,
    check_options_set,
    raise_and_log_error,
    ConfigError,
    UnexpectedError)


class BranchSourceCodeManager(SpinnakerSourceCodeManager):
  """Sources are retrieved from github using branches."""

  @staticmethod
  def add_parser_args(parser, defaults):
    """Add standard parser arguments used by SourceCodeManager."""
    if hasattr(parser, 'added_branch_scm'):
      return
    parser.added_branch_scm = True

    SpinnakerSourceCodeManager.add_parser_args(parser, defaults)
    GitRunner.add_parser_args(parser, defaults)
    add_parser_argument(parser, 'git_branch', defaults, None,
                        help='The git branch to operate on.')

  @staticmethod
  def in_bom_filter(_, entry):
    return entry.get('in_bom', False)

  def __init__(self, *pos_args, **kwargs):
    super(BranchSourceCodeManager, self).__init__(*pos_args, **kwargs)
    options = self.options
    check_options_set(options, ['git_branch', 'github_owner'])

    self.__github_owner = (options.github_owner
                           if hasattr(options, 'github_owner')
                           else None)

  def determine_origin(self, name):
    """Determine the origin to use for the given repository."""
    if not self.__github_owner:
      raise_and_log_error(
          UnexpectedError('Not reachable', cause='NotReachable'))
      return None
    return self.determine_origin_for_owner(name, self.__github_owner)

  def determine_origin_for_owner(self, name, github_owner):
    options = self.options
    db = self.source_repository_database
    repositories_dict = db['repositories']
    if not name in repositories_dict:
      raise_and_log_error(
          ConfigError('Repository "{name}" is not in "{path}"\n'.format(
              name=name, path=options.scm_repository_spec_path)))
    entry = repositories_dict.get(name) or {}
    if github_owner in ('upstream', 'default'):
      github_owner = entry.get('owner')
      if not github_owner:
        github_owner = db.get('default_git_owner')
      if not github_owner:
        raise_and_log_error(
            ConfigError(
                '"{path}" does not specify :default_git_owner".'
                ' Cannot determine owner for "{name}"'.format(
                    path=options.scm_repository_spec_path, name=name)))
    origin_hostname = entry.get(
        'origin_hostname', db.get('default_origin_hostname'))
    if not origin_hostname:
      raise_and_log_error(
          ConfigError(
              '"{path}" does not specify "default_origin_hostname".'
              'Cannot determine git hostname for "{name}"'.format(
                  path=options.scm_repository_spec_path, name=name)))

    if self.options.github_filesystem_root:
      return os.path.join(self.options.github_filesystem_root,
                          origin_hostname, github_owner, name)
    elif self.options.github_pull_ssh:
      return self.git.make_ssh_url(origin_hostname, github_owner, name)
    else:
      return self.git.make_https_url(origin_hostname, github_owner, name)

  def ensure_git_path(self, repository, **kwargs):
    branch = kwargs.pop('branch', None)
    check_kwargs_empty(kwargs)
    options = self.options

    git_dir = repository.git_dir
    have_git_dir = os.path.exists(git_dir)
    if not branch:
      if hasattr(options, 'git_branch'):
        branch = options.git_branch
      else:
        branch = 'master'
        logging.debug('No git_branch option available.'
                      ' Assuming "%s" branch is "master"', repository.name)

    fallback_branch = (options.git_fallback_branch
                       if hasattr(options, 'git_fallback_branch')
                       else None)
    if not have_git_dir:
      self.git.clone_repository_to_path(
          repository, branch=branch, default_branch=fallback_branch)

  def determine_build_number(self, repository):
    if hasattr(self.options, 'build_number') and self.options.build_number:
      build_number = self.options.build_number
    else:
      build_number = DEFAULT_BUILD_NUMBER
      logging.debug('Using default build number "%s" for "%s"',
                    build_number, repository.name)
    return build_number

  def determine_upstream_url(self, name):
    return self.determine_origin_for_owner(name, 'default')

  def check_repository_is_current(self, repository):
    branch = self.options.git_branch or 'master'
    have_branch = self.git.query_local_repository_branch(repository.git_dir)
    if have_branch == branch:
      return True
    raise_and_log_error(
        UnexpectedError(
            '"%s" is at the wrong branch "%s"' % (repository.git_dir, branch)))

  def filter_source_repositories(self, entry_filter):
    db = self.source_repository_database
    prototype = {
        'owner': db.get('default_git_owner'),
        'origin_hostname': db.get('default_origin_hostname')
    }

    result = []
    for name, value in db['repositories'].items():
      if value:
        entry = dict(prototype)
        entry.update(value)
      else:
        entry = prototype
      if entry_filter(name, entry):
        result.append(self.make_repository_spec(name))
    return result
