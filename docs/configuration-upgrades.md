# Configuration upgrades

Configuration schema 84 restores the startup warning for version-83 files.
At startup, **Back up and upgrade** merges missing named definitions from the
shipped example and repairs dangling `Classic_HUD` and `bodova_default` aliases.
Existing profiles, game bindings, layouts, sites, folders, screen names,
favourite seats and database settings remain intact. Custom definitions are
not overwritten. Every unresolved aux, stat-set and layout binding is reported,
even when the version matches.

The upgrade is prepared on a copy and validated before writing. Unknown versions
and remaining unresolved references require manual correction; their version is
not advanced. A unique `HUD_config.xml.pre-upgrade-*.xml` backup is written beside
the configuration before atomic replacement. To restore it, close fpdb and copy
that backup over HUD_config.xml. Ordinary `.backup` rotation cannot overwrite it.

## Maintaining templates

When either shipped XML template changes, increment CONFIG_VERSION and both
`general` versions. CI compares the PR with its base and rejects unversioned
changes or inconsistent markers. Add an ordered `(from, to, callable)` step to
`config_migrations.MIGRATIONS`; use explicit, conservative transformations.
The existing idempotent Entain/AoF repair helpers still run independently for
compatibility with current files. They are not evidence of a schema upgrade.

## Database versions

This fix does not invent migrations for historical database schemas. An
incompatible database remains flagged. Recreating tables deletes imported hands
and statistics and requires original histories for reimport. The startup warning
now explains this and offers the existing diagnostic text export, with errors
reported if the old schema cannot be exported. That text format is not a
restorable backup: preserve a native database backup and original hand histories
before recreating tables. A database schema migration needs separately verified
steps for each supported historical version and backend.
