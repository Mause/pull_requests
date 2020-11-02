FROM heroku/heroku:latest
COPY . /app
WORKDIR /app
RUN pip install -U pipenv && pipenv sync --dev && pipenv run puthon run.py
ENTRYPOINT ["gunicorn"]
CMD ["wsgi:app"]
