import os

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

if 'SENTRY_DSN' in os.environ:
    sentry_sdk.init(
        os.environ['SENTRY_DSN'],
        integrations=[FlaskIntegration()],
        release=os.environ.get('HEROKU_SLUG_COMMIT'),
        traces_sample_rate=1.0,
    )

app = create_app()
app = ProxyFix(app, x_for=1, x_host=1)
