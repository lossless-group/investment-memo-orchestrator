"""Materials (plan 4): how a partner's deck, dataroom, notes, and links reach a deal.

- :mod:`.fetch`: download a link (share links rewritten, size and time capped,
  private addresses refused).
- :mod:`.extract`: bytes to text through the orchestrator's document text layer.
- :mod:`.uploads`: the one-time upload tokens.
- :mod:`.upload_page`: ``GET`` and ``POST /upload/{token}``.
- :mod:`.pipeline`: the ``materials.extract`` server step, run in the background.

The tool itself is ``src/connector/tools/add_materials.py``. No model is called.
"""
