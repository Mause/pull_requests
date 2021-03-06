FROM python:3.9.0
COPY . /app
WORKDIR /app
RUN pip install -U pipenv && pipenv install --deploy --dev --system && python run.py
ENTRYPOINT ["gunicorn"]
CMD ["wsgi:app"]
