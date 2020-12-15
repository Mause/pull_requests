import json
import logging
import os
import time
from asyncio import gather, get_event_loop, new_event_loop, set_event_loop
from collections import ChainMap
from datetime import datetime, timedelta, timezone

import jwt
import requests
from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sentry_sdk import set_user

from main import AcceptPrs, add_token, get_by_title

app = Blueprint(__name__, 'app')
logging.basicConfig(level=logging.DEBUG)

UTC = timezone(timedelta(seconds=0))
GMT_8 = timezone(timedelta(hours=8))


def fetch_token():
    return session.get('token')


def compliance_fix(session):
    def _fix_token_response(resp):
        data = resp.json()

        if 'refresh_token_expires_in' in data:
            data['refresh_token_expires_at'] = (
                time.time() + data['refresh_token_expires_in']
            )

        resp.json = lambda: data
        return resp

    session.register_compliance_hook('access_token_response', _fix_token_response)
    session.register_compliance_hook('refresh_token_response', _fix_token_response)


oauth = OAuth()
oauth.register(
    'github',
    scope='repo pr',
    client_kwargs={'scope': 'repo pr'},
    authorize_url='https://github.com/login/oauth/authorize',
    access_token_url='https://github.com/login/oauth/access_token',
    userinfo_endpoint='https://api.github.com/user',
    fetch_token=fetch_token,
    compliance_fix=compliance_fix,
    update_token=lambda token, access_token, refresh_token: session.__setitem__(
        'token', token
    ),
)


def make_token():
    payload = {
        'iss': '86174',
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(minutes=9),
    }

    private_key = open('mass-merge.2020-10-25.private-key.pem').read()
    return jwt.encode(payload, private_key, algorithm='RS256')


def app_info():
    return requests.get(
        'https://api.github.com/app',
        headers={
            "Authorization": "Bearer " + (make_token()).decode(),
            "Accept": "application/vnd.github.v3+json",
        },
    ).json()


@app.route('/callback')
def callback():
    session['token'] = oauth.github.authorize_access_token()

    return redirect(url_for('.index'))


@app.route('/reset')
def reset():
    set_user(None)
    session.clear()

    return redirect(url_for('.index'))


def get():
    try:
        return get_event_loop()
    except RuntimeError:
        set_event_loop(new_event_loop())
        return get()


async def pair(pr, job):
    return (pr, await job)


def post():
    selected = [
        {'pr_name': pr_name, 'repo': pr['repo'], 'id': pr['id']}
        for pr_name, prs in request.form.items()
        for pr in json.loads(prs)
    ]

    gathered = get().run_until_complete(
        gather(
            *[
                pair(
                    pr,
                    AcceptPrs.execute_async(
                        pr['id'],
                        on_before_callback=add_token(
                            oauth.github.token['access_token']
                        ),
                    ),
                )
                for pr in selected
            ]
        )
    )

    did_error = False
    for meta, result in gathered:
        if result.errors:
            print(result)
            did_error = True
            for error in result.errors:
                flash(
                    f'Merging pr "{meta["pr_name"]}" into {meta["repo"]} resulted in "{error["message"]}"'
                )

    if not did_error:
        flash('Completed without error')

    return redirect(url_for('.index'))


@app.route('/', methods=['POST', 'GET'])
def index():
    if not oauth.github.token:
        return oauth.github.authorize_redirect(
            redirect_url=url_for('.callback', _external=True)
        )

    for key in ('expires_at', 'refresh_token_expires_at'):
        timestamp = oauth.github.token.get(key)
        logging.info(
            '%s expires at %s',
            key,
            timestamp
            and datetime.fromtimestamp(timestamp, UTC).astimezone(GMT_8).isoformat(),
        )

    user_info = oauth.github.userinfo()  # also triggers token refresh
    set_user({'email': user_info['email'], 'username': user_info['login']})

    if request.method == 'POST':
        return post()

    by_title = get_by_title(oauth.github.token['access_token'])

    by_title_ids = {
        title: [{'repo': pr.repository.name, 'id': pr.id} for pr in prs]
        for title, prs in by_title.items()
    }

    return render_template('by_title.html', by_title=by_title_ids, user_info=user_info)


def create_app():
    papp = Flask(__name__)
    papp.secret_key = '0000000000000000000000000'
    papp.config = ChainMap(papp.config, os.environ)
    papp.register_blueprint(app)

    oauth.init_app(papp)

    return papp


if __name__ == '__main__':
    create_app().run()  # debug=True)
