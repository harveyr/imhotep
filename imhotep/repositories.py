import json
import logging
import re
from urlparse import urljoin


log = logging.getLogger(__name__)


class ToolsNotFound(Exception):
    pass


class Repository(object):
    """
    Represents a github repository (both in the abstract and on disk).
    """

    def __init__(self, name, loc, tools, executor, shallow=False):
        if len(tools) == 0:
            raise ToolsNotFound()

        self.name = name
        self.dirname = loc
        self.tools = tools
        self.executor = executor
        self.shallow = shallow

    @property
    def download_location(self):
        return "git://github.com/%s.git" % self.name

    def apply_commit(self, commit):
        """
        Updates the repository to a given commit.
        """
        self.executor("cd %s && git checkout %s" % (self.dirname, commit))

    def diff_commit(self, commit, compare_point=None):
        """
        Returns a diff as a string from the current HEAD to the given commit.
        """
        # @@@ This is a security hazard as compare-point is user-passed in
        # data. Doesn't matter until we wrap this in a service.
        if compare_point is not None:
            self.apply_commit(compare_point)
        return self.executor("cd %s && git diff %s" % (self.dirname, commit))

    def github_compare(self, req, head, base='master'):
        if head == base:
            raise ValueError(
                (
                    'Comparing the "{}" branch against itself. '
                    'Catch this earlier in the process.'
                ).format(head)
            )

        path = '/repos/{repo}/compare/{base}...{head}'.format(
            repo=self.name,
            base=base,
            head=head

        )
        resp = req.get(urljoin('https://api.github.com', path))

        if resp.status_code != 200:
            return None

        return GithubComparison(resp.json())

    def __unicode__(self):
        return self.name


class AuthenticatedRepository(Repository):
    @property
    def download_location(self):
        return "git@github.com:%s.git" % self.name


class LocalRepository(Repository):
    def apply_commit(self, commit):
        raise NotImplementedError


class GithubComparison(object):
    def __init__(self, data):
        self.data = data

        self.files = [FileCompare(d) for d in self.data['files']]

        self.filepaths = set()
        self.files_by_path = {}
        for f in self.files:
            self.filepaths.add(f.filename)
            self.files_by_path[f.filename] = f


class FileCompare(object):
    def __init__(self, data):
        try:
            self.sha = data['sha']
            self.filename = data['filename']
            self.status = data['status']  # e.g., "added"
            self.additions = data['additions']
            self.deletions = data['deletions']
            self.changes = data['changes']
            self.contents_url = data['contents_url']
            self.patch = data.get('patch')
        except KeyError:
            log.error(
                'Expected key not found in data: %s',
                json.dumps(data, indent=2)
            )
            raise

        self.modified_positions = {}
        self.modified_lines = {}
        self.positions_by_line = {}
        self._parse_patch()

    def __unicode__(self):
        return '{}'.format(self.filename)

    def __str__(self):
        return unicode(self).encode('utf-8')

    @classmethod
    def parse_unified_diff(cls, diffline):
        """Returns (start, count) tuple from the diffline.

        Only looks at new state, not old state.
        """
        if not diffline.startswith('@@ '):
            raise ValueError('Bad unified diff line: {}'.format(diffline))

        parts = diffline.split()
        split = parts[2].split(',')

        if len(split) == 2:
            start, count = split
        elif len(split) == 1:
            start = split[0]
            count = None
        else:
            raise ValueError('Unexpected diff line: {}'.format(diffline))

        start = int(start)
        count = int(count) if count is not None else count

        return start, count

    def _parse_patch(self):
        self.modified_positions = {}
        self.modified_lines = {}
        self.positions_by_line = {}

        if not self.patch:
            return

        lines = self.patch.splitlines()

        # this doubles as an assertion that the first line is in the unified
        # diff format
        start_line, count = self.parse_unified_diff(lines[0])

        # we're trying to record both the "position" in the diff as well as
        # the line numbers for each change.
        # https://developer.github.com/v3/pulls/comments/#create-a-comment
        position_offset = 0
        line_offset = 0

        for line in lines[1:]:
            # logger.debug(line)
            if line.startswith('@@ '):
                start_line, count = self.parse_unified_diff(line)
                line_offset = 0
                # note that subsequent unified diff lines in the github diffs
                # ARE significant in determining the line position. so make
                # we increment position_offset below once we're here.
            else:
                if line[0] == '+':
                    try:
                        source_line = SourceCodeLine.from_line(
                            filename=self.filename,
                            text=line[1:]
                        )
                    except UnknownSourceType:
                        log.debug(
                            'Skipping unknown source type: %s',
                            self.filename
                        )
                        continue
                    line_num = start_line + line_offset
                    position_num = position_offset + 1
                    self.modified_positions[position_num] = source_line
                    self.modified_lines[line_num] = source_line
                    self.positions_by_line[line_num] = position_num

                if line[0] != '-':
                    line_offset += 1

            position_offset += 1

    def get_position_for_line(self, line_num):
        return self.positions_by_line[int(line_num)]

    def iter_modified_lines(self):
        """Returns generator of (line_num, SourceCodeLine) tuples.

        Helper method in case the underlying data structure changes."""
        return self.modified_lines.iteritems()


class UnknownSourceType(Exception):
    pass


class SourceCodeLine(object):
    FUNC_DEF_REX = None
    TEST_DEF_REX = None

    def __init__(self, text):
        self.text = text

    def __unicode__(self):
        return self.text

    def __str__(self):
        return unicode(self).encode('utf-8')

    @classmethod
    def from_line(cls, filename, text):
        if filename.endswith('.py'):
            return PyLine(text)

        if filename.endswith('.js'):
            return JsLine(text)

        raise UnknownSourceType("I can't handle {} yet.".format(filename))

    def is_empty(self, ignore_whitespace=True):
        if ignore_whitespace:
            test_text = self.text.strip()
        else:
            test_text = self.text

        return not bool(test_text)

    def is_function_definition(self):
        if not self.FUNC_DEF_REX:
            raise NotImplementedError

        return bool(self.FUNC_DEF_REX.match(self.text))

    def is_test_definition(self):
        if not self.TEST_DEF_REX:
            raise NotImplementedError

        return bool(self.TEST_DEF_REX.match(self.text))

    def is_named_function(self, name):
        raise NotImplementedError


class PyLine(SourceCodeLine):
    FUNC_DEF_REX = re.compile(r'^\s*?def [a-z_\d]+\(.*\):')
    TEST_DEF_REX = re.compile(r'^\s*?def test_[a-z_\d]+\(.*\):')

    def is_named_function(self, name):
        return self.text.strip().startswith('def {}('.format(name))


class JsLine(SourceCodeLine):
    # TODO: Needs work
    FUNC_DEF_REX = re.compile(r'^\s*?function [\w+]\(')
    TEST_DEF_REX = re.compile(r'^test\(')

    def is_named_function(self, name):
        # TODO: Moar function syntax
        return self.text.strip().startswith('function {}('.format(name))
