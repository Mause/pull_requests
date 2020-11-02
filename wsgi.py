import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from app import create_app

if 'SENTRY_DSN' in os.environ:
    sentry_sdk.init(
        os.environ['SENTRY_DSN'],
        integrations=[FlaskIntegration()],
        release=os.environ['HEROKU_SLUG_COMMIT'],
        traces_sample_rate=0.75,
    )

app = create_app()
