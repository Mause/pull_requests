from asyncio import get_event_loop
from dataclasses import dataclass, field
from typing import Dict, Union

from aiohttp import ClientSession
from sgqlc.endpoint.base import BaseEndpoint
from sgqlc.operation import Operation
from sgqlc_schemas.github import (
    AddLabelsToLabelableInput,
    AddLabelsToLabelablePayload,
    Repository,
    github,
)


@dataclass
class AsyncHttpEndpoint(BaseEndpoint):
    url: str
    headers: Dict[str, str] = field(default_factory=dict)

    async def __call__(self, query) -> Union[github.Query, github.Mutation]:
        async with ClientSession() as session:
            res = await session.post(
                self.url,
                headers={**self.headers, 'Content-Type': 'application/json'},
                json={'query': bytes(query).decode()},
            )
            try:
                data = await res.json()
            except Exception as e:
                self._log_json_error(await res.text(), e)
            data.setdefault('errors', [])
            if data['errors']:
                self._log_graphql_error(query, data)
            return query + data


async def add_labels_to_labelable(
    endpoint: BaseEndpoint, repository_id: str, labelable_id: str, label: str
) -> AddLabelsToLabelablePayload:
    query = Operation(github.Query)
    query.node(id=repository_id).__as__(Repository).labels(first=50).nodes().__fields__(
        'name', 'id'
    )
    labels = {
        repo_label.name: repo_label.id
        for repo_label in (await endpoint(query)).node.labels.nodes
    }

    mutation = Operation(github.Mutation)
    mutation.add_labels_to_labelable(
        input=AddLabelsToLabelableInput(
            labelable_id=labelable_id, label_ids=[labels[label]]
        )
    )
    return (await endpoint(mutation)).add_labels_to_labelable


async def main():
    endpoint = AsyncHttpEndpoint(
        'https://api.github.com/graphql',
        {'Authorization': 'Bearer ' + open('token.txt').read()},
    )

    qu = Operation(github.Query)
    repo = qu.repository(owner='Mause', name='media')
    repo.id()
    repo.pull_requests(first=1).nodes().__fields__('title', 'id')
    res = (await endpoint(qu)).repository
    await add_labels_to_labelable(
        endpoint, res.id, res.pull_requests.nodes[0].id, 'automerge'
    )


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
