#! /bin/bash

echo "Generating requirements files"
pipenv lock --requirements > requirements.txt
pipenv lock --requirements --dev > requirements-dev.txt

pip install "tox==3.0.0"
tox -r
