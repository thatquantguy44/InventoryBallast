"""Backend translation and normalized solver results (Section 7.1).

``highs.py`` is the sole owner of ``highspy`` imports (Section 16.4). ``statuses.py``,
``capabilities.py``, and ``optional.py`` from the illustrative target structure (Section 7) are
introduced once a second backend exists to make cross-backend concerns worth factoring out; with
one backend, that content lives directly in ``highs.py``.
"""
