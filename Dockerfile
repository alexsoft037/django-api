FROM cozmocontainerregistry.azurecr.io/cozmo/cozmo-base:3.6.6-4 as builder

COPY Pipfile Pipfile.lock ./

RUN pipenv lock -rd > requirements-dev.txt && \
    pipenv lock -r > requirements.txt && \
    pipenv install && \
    pipenv install --dev && \
    pip install -r requirements.txt --target /cozmo/dist/

ENV PATH=/cozmo/dev/bin:$PATH
ENV PYTHONPATH=/cozmo/dev:$PYTHONPATH

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM cozmocontainerregistry.azurecr.io/cozmo/cozmo-base:3.6.6-4 as prod

USER cozmo

ENV PATH=/cozmo/dist/bin:$PATH
ENV PYTHONPATH=/cozmo/dist:$PYTHONPATH

COPY --chown=cozmo:cozmo --from=builder /cozmo/dist /cozmo/dist

COPY --chown=cozmo:cozmo . ./
