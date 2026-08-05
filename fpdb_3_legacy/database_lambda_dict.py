"""A dict that builds missing values on demand.

Shared by the Database domains that cache generated ids, and kept apart from
them so a mixin can import it without importing Database itself.
"""

from __future__ import annotations


# Code borrowed from http://push.cx/2008/caching-dictionaries-in-python-vs-ruby
class LambdaDict(dict):
    def __init__(self, value_factory) -> None:
        super().__init__()
        self.value_factory = value_factory

    def __getitem__(self, key):
        if key in self:
            return self.get(key)
        # Use the value_factory to generate a value for the missing key
        self.__setitem__(key, self.value_factory(key))
        return self.get(key)
