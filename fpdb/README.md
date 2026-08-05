# `fpdb` modern infrastructure package

This package is intentionally retained alongside `fpdb_3_legacy`.

Its current supported responsibility is the cross-platform table-window abstraction in
`fpdb.infrastructure.platform`. The live HUD entry points (`XTables`, `OSXTables`,
`WinTables`, and `HUD_main.pyw`) consume this API. Platform-specific operating-system
dependencies remain lazy-loaded so importing the shared protocol and factory is safe on
Linux, macOS, and Windows.

New code belongs here only when it has a tested, active consumer and does not depend on
legacy module globals. Poker parsing, database models, and adapters still live in
`fpdb_3_legacy`; stale scripts that refer to unimplemented `fpdb.infrastructure.parsers`
or `fpdb.infrastructure.database` namespaces are not evidence that those namespaces
exist.
