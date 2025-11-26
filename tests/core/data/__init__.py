"""Package marker for core data tests.

Pytest relies on package-qualified module names to avoid collisions during
collection.  Declaring this directory as a package ensures that imports use
the ``tests.core.data`` prefix instead of falling back to the generic
``test_*`` module namespace.
"""
