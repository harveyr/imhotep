from collections import namedtuple
import logging
import sys

log = logging.getLogger(__name__)

Remote = namedtuple('Remote', ('name', 'url'))
CommitInfo = namedtuple("CommitInfo",
                        ('commit', 'origin', 'remote_repo', 'ref'))


class PRInfo(object):
    def __init__(self, json):
        self.json = json

    @property
    def base_sha(self):
        return self.json['base']['sha']

    @property
    def head_sha(self):
        return self.json['head']['sha']

    @property
    def base_ref(self):
        return self.json['base']['ref']

    @property
    def head_ref(self):
        return self.json['head']['ref']

    @property
    def has_remote_repo(self):
        return self.json['base']['repo']['owner']['login'] != self.json['head']['repo']['owner']['login']

    @property
    def remote_repo(self):
        remote = None
        if self.has_remote_repo:
            remote = Remote(name=self.json['head']['repo']['owner']['login'],
                            url=self.json['head']['repo']['clone_url'])
        return remote

    def to_commit_info(self):
        return CommitInfo(self.base_sha, self.head_sha, self.remote_repo,
                          self.head_ref)


def get_pr_info(requester, reponame, number=None, branch=None):
    "Returns the PullRequest as a PRInfo object"
    if number:
        resp = requester.get(
            'https://api.github.com/repos/{}/pulls/{}'.format(
                reponame, number
            )
        )
        return PRInfo(resp.json())

    if branch:
        log.info('Searching for PR for branch %s', branch)
        resp = requester.get(
            'https://api.github.com/repos/{}/pulls'.format(reponame)
        )
        prs = resp.json()
        try:
            pr = next(p for p in prs if p['head']['ref'] == branch)
        except StopIteration:
            sys.exit('No PR found for branch {}'.format(branch))

        return PRInfo(pr)

    raise ValueError('Must provide `number` or `branch`')

