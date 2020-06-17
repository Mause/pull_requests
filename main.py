import re
from itertools import groupby as _groupby
from typing import Iterable, TypeVar, Callable, Dict, List, Mapping
from itertools import chain
from dataclasses import dataclass

from tqdm import tqdm
from query import GetPullRequests
from accept import AcceptPrs
from PyInquirer import prompt

token = open('token.txt').read().strip()
TITLE_RE = re.compile(
    r'Bump (?P<name>[^ ]+) from (?P<from>[^ ]+) to (?P<to>[^ ]+)'
)


K = TypeVar("K")
V = TypeVar("V")


def groupby(iterable: Iterable[V], key: Callable[[V], K]) -> Dict[K, List[V]]:
    return {k: list(v) for k, v in _groupby(sorted(iterable, key=key), key)}


def callback(params: Mapping[str, str], headers: Mapping[str, str]) -> None:
    headers["Authorization"] = f"Bearer {token}"


def paginate() -> Iterable:
    cursor = None
    while True:
        pull_requests: GetPullRequests = GetPullRequests.execute(
            cursor=cursor, on_before_callback=callback
        )

        assert pull_requests and pull_requests.data
        repos = pull_requests.data.viewer.repositories
        assert repos and repos.edges
        for repo in repos.edges:
            assert repo and repo.node
            yield from (pr.node for pr in repo.node.pullRequests.edges)

        cursor = repos.pageInfo.endCursor
        if cursor is None:
            break


def get_message(selected):
    names = {name.repository.name for name in selected}
    return "Merge?\n" + "".join(f" ● {name}\n" for name in names)


@dataclass
class AsStr:
    answers: Dict
    func: Callable[[Dict], str]

    def __str__(self):
        return self.func(self.answers)


def get_selected(by_title, answers):
    return chain.from_iterable(by_title[chosen] for chosen in answers["update"])


def normalise_title(title: str) -> str:
    m = TITLE_RE.search(title)
    return m.group(0) if m else title


def main():
    prs = tqdm(paginate())
    prs = list(
        pr
        for pr in prs
        if pr.author.login in {"dependabot", "dependabot-preview"}
    )
    if not prs:
        print('Nothing to do')
        return

    by_title = groupby(prs, lambda pr: normalise_title(pr.title))

    answers = {None: None}
    answers = prompt(
        [
            {
                "type": "checkbox",
                "name": "update",
                "message": "Which updates to do you want to merge?",
                "choices": [{'name': name} for name in sorted(by_title)],
            },
            {
                "type": "confirm",
                "message": AsStr(
                    answers,
                    lambda answers: get_message(
                        get_selected(by_title, answers)
                    ),
                ),
                "name": "merge",
                "default": False,
            },
        ],
        answers,
    )
    title = answers.get("update")
    if not title:
        return
    selected = get_selected(by_title, answers)
    if answers.get("merge"):
        for pr in tqdm(selected):
            errors = AcceptPrs.execute(
                pr.id, on_before_callback=callback
            ).errors
            if errors:
                print(pr, errors)

    if not prompt(
        {"type": "confirm", "message": 'Done?', "name": "done", "default": True}
    )['done']:
        main()


if __name__ == "__main__":
    main()
