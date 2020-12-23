from asyncio import get_event_loop
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from aiohttp import ClientSession
from asyncache import cached
from cachetools import TTLCache
from pydantic import BaseModel
from sgqlc.endpoint.base import BaseEndpoint
from sgqlc.operation import Operation
from sgqlc_schemas.github.schema import (
    AddLabelsToLabelableInput,
    AddLabelsToLabelablePayload,
    MergePullRequestInput,
    Mutation,
    Query,
    Repository,
)


class Shared(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class Location(Shared):
    column: int
    line: int


class Error(Shared):
    locations: List[Location]
    message: str
    path: Optional[List[str]] = None


class DataWithErrors(Shared):
    data: Union[Query, Mutation]
    errors: List[Error]


@dataclass
class AsyncHttpEndpoint(BaseEndpoint):
    url: str
    headers: Dict[str, str] = field(default_factory=dict)

    async def __call__(self, query) -> DataWithErrors:
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
            if not (data['errors'] or data.get('data')):
                data['errors'] = [{'message': data['message'], 'locations': []}]

            return DataWithErrors(data=query + data, errors=data['errors'])


@cached(TTLCache(1024, 360), lambda endpoint, repository_id: repository_id)
async def get_labels_for_repo(
    endpoint: AsyncHttpEndpoint, repository_id: str
) -> Dict[str, str]:
    query = Operation(Query)
    query.node(id=repository_id).__as__(Repository).labels(first=50).nodes().__fields__(
        'name', 'id'
    )
    return {
        repo_label.name: repo_label.id
        for repo_label in (await endpoint(query)).node.labels.nodes
    }


async def add_labels_to_labelable(
    endpoint: AsyncHttpEndpoint, repository_id: str, labelable_id: str, label: str
) -> AddLabelsToLabelablePayload:
    labels = await get_labels_for_repo(endpoint, repository_id)
    mutation = Operation(Mutation)
    mutation.add_labels_to_labelable(
        input=AddLabelsToLabelableInput(
            labelable_id=labelable_id, label_ids=[labels[label]]
        )
    )
    return (await endpoint(mutation)).add_labels_to_labelable


async def build_endpoint(token: str) -> AsyncHttpEndpoint:
    return AsyncHttpEndpoint(
        'https://api.github.com/graphql',
        {'Authorization': 'Bearer ' + token},
    )


async def main():
    endpoint = await build_endpoint(open('token.txt').read())

    qu = Operation(Query)
    repo = qu.repository(owner='Mause', name='media')
    repo.id()
    repo.pull_requests(first=1).nodes().__fields__('title', 'id')
    res = (await endpoint(qu)).repository
    await add_labels_to_labelable(
        endpoint, res.id, res.pull_requests.nodes[0].id, 'automerge'
    )

    op = Operation(Mutation)
    op = build_merge([res.pull_requests.nodes[0].id])
    res = await endpoint(op)
    print(res)


def build_merge(ids: List[str]):
    op = Operation(Mutation)

    for i, ident in enumerate(ids):
        op.merge_pull_request(
            input=MergePullRequestInput(pull_request_id=ident), __alias__=f'merge_{i}'
        ).pull_request.title()

    return op


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
