"""Core integration test package.

This file ensures that pytest treats the ``tests.core`` hierarchy as a
regular Python package so that modules nested under it receive fully
qualified import names during collection.  Without the package marker the
default pytest import mode can load multiple ``test_*.py`` modules using the
same top-level name, which leads to import collisions when different suites
contain files with identical basenames.  Adding the package initializer
prevents those collisions and keeps module discovery stable.
"""
