"""Suite-wide isolation, loaded for every test directory under the repository root."""

import os

# The suite imports hands into throwaway databases, and the importer pushes each
# new id to whatever HUD listens on 127.0.0.1:5555. A HUD left running on this
# machine reads those ids in its own database, where they name unrelated hands,
# and freezes looking for their tables' windows. Set at collection, before any
# test can build a sender, and inherited by the subprocesses some tests start.
os.environ.setdefault("FPDB_HUD_NOTIFY", "0")
