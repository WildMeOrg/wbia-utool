#!/bin/bash
# python -m utool.util_setup --exec-autogen_sphinx_apidoc  --nomake

pip install -e .
cp utool/_version.py _docs/_version.py

make -C _docs html
rm -rf docs/
mkdir -p docs/
cp -r _docs/_build/html/* docs/
touch docs/.nojekyll
