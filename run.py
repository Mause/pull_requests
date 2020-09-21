import requests
from gql import utils_schema
from gql.cli import run

utils_schema.load_introspection_from_server = lambda url: requests.get(url).json()

run()
