"""Stand-ins for the macOS accessibility API, so its callers can be tested.

``winamax_ax_seats`` reads the Winamax client's window through
ApplicationServices and AppKit. Those need a running client, granted TCC
permissions and a real screen, so the code that drives them was the least
covered part of the Fast-Fold HUD -- exactly the part a Windows or Linux
implementation is most likely to disturb.

The API surface actually used is four functions and one workspace lookup, so
it is small enough to reproduce faithfully. Everything here mimics the real
contract, including its oddities: ``AXUIElementCopyAttributeValue`` returns an
``(error, value)`` pair rather than raising, and geometry arrives boxed behind
``AXValueGetValue``.

Not a test module itself: :mod:`test.test_winamax_ax_seats_macos` and the
cross-platform contract tests import it.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from typing import Any

#: Sentinels standing in for the real CoreFoundation type constants.
K_POINT = "kAXValueCGPointType"
K_SIZE = "kAXValueCGSizeType"

#: The error code the real API returns for an attribute an element lacks.
AX_ERROR_NO_VALUE = -25212


class Boxed:
    """A geometry value as the AX API hands it over: opaque until unboxed."""

    def __init__(self, kind: str, **fields: float) -> None:
        self.kind = kind
        for name, value in fields.items():
            setattr(self, name, value)


class AXElement:
    """One node of an accessibility tree.

    Attributes are held in a mapping because that is how the real API exposes
    them -- by name, absent rather than empty when the element has none.
    """

    def __init__(
        self,
        role: str = "AXGroup",
        *,
        value: Any = None,
        title: str | None = None,
        position: tuple[float, float] | None = None,
        size: tuple[float, float] | None = None,
        children: list[AXElement] | None = None,
        windows: list[AXElement] | None = None,
        missing: tuple[str, ...] = (),
        unboxable: tuple[str, ...] = (),
    ) -> None:
        self.attrs: dict[str, Any] = {"AXRole": role}
        if value is not None:
            self.attrs["AXValue"] = value
        if title is not None:
            self.attrs["AXTitle"] = title
        if position is not None:
            self.attrs["AXPosition"] = Boxed(K_POINT, x=position[0], y=position[1])
        if size is not None:
            self.attrs["AXSize"] = Boxed(K_SIZE, width=size[0], height=size[1])
        if children is not None:
            self.attrs["AXChildren"] = children
        if windows is not None:
            self.attrs["AXWindows"] = windows
        for name in missing:
            self.attrs.pop(name, None)
        #: Attributes whose boxed value refuses to unbox, as a stale handle does.
        self.unboxable = frozenset(unboxable)


def text(value: str, x: float, y: float) -> AXElement:
    """A static-text node at a position, which is what a label is."""
    return AXElement("AXStaticText", value=value, position=(x, y))


def button(value: str, x: float, y: float) -> AXElement:
    """An action control. Labels itself with text and sits above a chip amount."""
    return AXElement("AXButton", value=value, position=(x, y))


class RunningApplication:
    """What NSWorkspace lists: a name and a pid."""

    def __init__(self, name: str | None, pid: int) -> None:
        self._name = name
        self._pid = pid

    def localizedName(self) -> str | None:  # noqa: N802 - mirrors the Cocoa API
        return self._name

    def processIdentifier(self) -> int:  # noqa: N802 - mirrors the Cocoa API
        return self._pid


class FakeAX:
    """The ApplicationServices / AppKit pair, recorded as it is called."""

    def __init__(self, applications: list[RunningApplication] | None = None) -> None:
        self.applications = applications if applications is not None else [RunningApplication("Winamax", 4242)]
        #: pid -> the app element handed back for it.
        self.created: list[int] = []
        #: Every AXUIElementSetAttributeValue call, as (element, name, value).
        self.set_calls: list[tuple[Any, str, Any]] = []
        #: The tree each created application element exposes.
        self.app_element = AXElement("AXApplication", windows=[])

    # -- ApplicationServices ------------------------------------------------

    def AXUIElementCreateApplication(self, pid: int) -> AXElement:  # noqa: N802 - mirrors the API
        self.created.append(pid)
        return self.app_element

    def AXUIElementSetAttributeValue(self, element: Any, name: str, value: Any) -> int:  # noqa: N802
        self.set_calls.append((element, name, value))
        return AX_ERROR_NO_VALUE  # the real call reports an error and still works

    def AXUIElementCopyAttributeValue(self, element: Any, name: str, _none: Any) -> tuple[int, Any]:  # noqa: N802
        attrs = getattr(element, "attrs", None)
        if attrs is None or name not in attrs:
            return (AX_ERROR_NO_VALUE, None)
        return (0, attrs[name])

    def AXValueGetValue(self, boxed: Any, kind: str, _none: Any) -> tuple[bool, Any]:  # noqa: N802
        if boxed is None or getattr(boxed, "kind", None) != kind:
            return (False, None)
        return (True, boxed)

    # -- installation -------------------------------------------------------

    def modules(self) -> dict[str, types.ModuleType]:
        """The two modules the reader imports, populated from this instance."""
        application_services = types.ModuleType("ApplicationServices")
        application_services.AXUIElementCreateApplication = self.AXUIElementCreateApplication
        application_services.AXUIElementSetAttributeValue = self.AXUIElementSetAttributeValue
        application_services.AXUIElementCopyAttributeValue = self.AXUIElementCopyAttributeValue
        application_services.AXValueGetValue = self.AXValueGetValue
        application_services.kAXValueCGPointType = K_POINT
        application_services.kAXValueCGSizeType = K_SIZE

        workspace = types.SimpleNamespace(runningApplications=lambda: self.applications)
        appkit = types.ModuleType("AppKit")
        appkit.NSWorkspace = types.SimpleNamespace(sharedWorkspace=lambda: workspace)
        return {"ApplicationServices": application_services, "AppKit": appkit}


@contextmanager
def installed(fake: FakeAX, *, absent: tuple[str, ...] = ()):
    """Put a :class:`FakeAX` in place of the real bindings for the block.

    ``absent`` names modules to make un-importable instead, which is how a
    machine without the pyobjc bindings behaves.
    """
    saved = {name: sys.modules.get(name) for name in ("ApplicationServices", "AppKit", *absent)}
    try:
        for name, module in fake.modules().items():
            if name not in absent:
                sys.modules[name] = module
        for name in absent:
            sys.modules[name] = None  # type: ignore[assignment]  # makes `import name` raise ImportError
        yield fake
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
