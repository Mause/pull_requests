import json

from aioresponses import aioresponses as _aioresponses
from flask.sessions import SessionInterface, SessionMixin
from pytest import fixture
from responses import RequestsMock

from app import create_app, oauth


@fixture
def aioresponses():
    with _aioresponses() as m:
        yield m


@fixture
def responses():
    with RequestsMock() as mock:
        yield mock


@fixture
def app():
    return create_app()


@fixture
def test_client(app):
    return app.test_client()


class Session(dict, SessionMixin):
    pass


class MySessionInterface(SessionInterface):
    session = Session()

    def open_session(self, app, request):
        return self.session

    def save_session(self, app, session, response):
        pass


def test_app(app, test_client, responses, aioresponses):
    responses.add(
        'GET',
        'https://api.github.com/user',
        json.dumps({'email': 'me@mause.me', 'login': 'Mause'}),
    )
    aioresponses.post(
        'https://api.github.com/graphql',
        payload={
            'errors': [
                {'message': 'Error in the tubes', 'locations': [], 'path': ['merge_0']}
            ]
        },
    )

    app.session_interface = MySessionInterface()

    with app.app_context():
        oauth.github.token = {'access_token': 'access_token'}
        r = test_client.post(
            '/', data={'hello': json.dumps([{'repo': 'media', 'id': '0000000'}])}
        )

        assert r.status_code == 302, r.get_data()

        assert MySessionInterface.session.get('_flashes') == [
            (
                'message',
                'Merging pr "hello" into media resulted in "Error in the tubes"',
            ),
        ]
