import logging

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
        path = '/repos/{repo}/compare/{base}...{head}'.format(
            repo=self.name,

        )
        resp = req.get(
            'https://api.github.com/repos/{repo}/compare/{base}...{head}'.format(

            )
        )

        path = '/repos/urbanairship/{repo}/compare/{base}...{head}'.format(
            repo=repo,
            base=base,
            head=head
        )

        request = api_get(path, assert_status=None)
        result = None

        if request.status_code == 200:
            result = GithubComparison(request.json())


    def __unicode__(self):
        return self.name


class AuthenticatedRepository(Repository):
    @property
    def download_location(self):
        return "git@github.com:%s.git" % self.name
