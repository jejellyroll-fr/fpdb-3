# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "fpdb-3"
copyright = "2025, fpdb-project"
author = "fpdb-project"
release = "3.0.0-alpha2"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["**/*-bak.py", "**/*-current.py", "**/*-old-bak.py", "**/*-legacy.py"]

language = "en"

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

autodoc_mock_imports = ["MergeStructures", "ctypes.windll", "xcffib"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]
