import re
from asyncio import get_event_loop
from dataclasses import dataclass
from itertools import chain
from itertools import groupby as _groupby
from typing import Callable, Dict, Iterable, List, Mapping, Optional, TypeVar

from PyInquirer import prompt
from tqdm import tqdm

from add_label import build_endpoint, build_merge

# these two files are generated using gql-next: gql run
from query import GetPullRequests

TITLE_RE = re.compile(r'Bump (?P<name>[^ ]+) from (?P<from>[^ ]+) to (?P<to>[^ ]+)')


K = TypeVar('K')
V = TypeVar('V')


def groupby(iterable: Iterable[V], key: Callable[[V], K]) -> Dict[K, List[V]]:
    return {k: list(v) for k, v in _groupby(sorted(iterable, key=key), key)}  # type: ignore


def add_token(token):
    def callback(params: Mapping[str, str], headers: Mapping[str, str]) -> None:
        headers['Authorization'] = f'Bearer {token}'  # type: ignore

    return callback


PullRequest = (
    GetPullRequests.GetPullRequestsData.User.RepositoryConnection.RepositoryEdge.Repository.PullRequestConnection.PullRequestEdge.PullRequest
)


def paginate(token: str) -> Iterable[PullRequest]:
    cursor = None
    while True:
        pull_requests: GetPullRequests = GetPullRequests.execute(
            cursor=cursor, on_before_callback=add_token(token)
        )

        repos = pull_requests.data.viewer.repositories
        for repo in repos.edges:
            if repo.node:
                for pr in repo.node.pullRequests.edges:
                    yield pr.node

        cursor = repos.pageInfo.endCursor
        if cursor is None:
            break


def get_message(selected):
    names = {name.repository.name for name in selected}
    return 'Merge?\n' + ''.join(f' ● {name}\n' for name in names)


@dataclass
class AsStr:
    answers: Dict
    func: Callable[[Dict], str]

    def __str__(self):
        return self.func(self.answers)


def get_selected(by_title, answers):
    return chain.from_iterable(by_title[chosen] for chosen in answers['update'])


def normalise_title(title: str) -> str:
    m = TITLE_RE.search(title)
    return m.group(0) if m else title


def labs(labels):
    return ", ".join(
        label.name for label in labels.nodes if label.name != "dependencies"
    )


def get_by_title(token: str) -> Dict[str, List[PullRequest]]:
    prs = paginate(token)
    prs = (pr for pr in prs if pr.author.login in {'dependabot', 'dependabot-preview'})
    return groupby(prs, lambda pr: normalise_title(pr.title))


async def main():
    token = open('token.txt').read().strip()
    by_title = get_by_title(token)
    if not by_title:
        print('Nothing to do')
        return

    answers: Dict[Optional[str], Optional[str]] = {None: None}
    answers = prompt(
        [
            {
                'type': 'checkbox',
                'name': 'update',
                'message': 'Which updates to do you want to merge?',
                'choices': [{'name': name} for name in sorted(by_title)],
            },
            {
                'type': 'confirm',
                'message': AsStr(
                    answers,
                    lambda answers: get_message(get_selected(by_title, answers)),
                ),
                'name': 'merge',
                'default': False,
            },
        ],
        answers,
    )
    title = answers.get('update')
    if not title:
        return
    selected = get_selected(by_title, answers)

    endpoint = await build_endpoint(token)

    if answers.get('merge'):
        for pr in tqdm(selected):
            errors = (await endpoint(build_merge([]))).errors
            if errors:
                print(pr.title, [error['message'] for error in errors])

    if not prompt(
        {'type': 'confirm', 'message': 'Done?', 'name': 'done', 'default': True}
    )['done']:
        main()


if __name__ == '__main__':
    get_event_loop().run_until_complete(main())
