import os
import runpy
import shutil
import sys
from os.path import isdir, join
from urllib.request import urlopen

FILENAME = 'sgqlc-codegen'
SCHEMA_JSON = 'schema.json'

path = next(
    path
    for root in sys.path
    for path in (root, (root + '\\scripts'))
    if isdir(path) and FILENAME in os.listdir(path)
)

with open(SCHEMA_JSON, 'wb') as fh:
    shutil.copyfileobj(
        urlopen('https://github.com/octokit/graphql-schema/raw/master/schema.json'), fh
    )

sys.argv = [FILENAME, SCHEMA_JSON, 'github.py']
runpy.run_path(join(path, FILENAME))
os.remove(SCHEMA_JSON)
