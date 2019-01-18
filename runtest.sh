#!/bin/bash
pytest -v ./test/test_dump.py ./test/test_filehitcount.py ./test/test_leven.py ./test/test_search.py ./test/test_stack.py ./test/test_status.py ./test/test_tcorr.py ./test/test_tstack.py ./test/test_tstomp.py
pytest -v ./test/test_ingestPlugins.py
pytest -v ./test/test_load.py
pytest -v ./test/test_mpengine.py
pytest -v ./test/test_fevil.py
#pytest -v ./test/test_reconscan.py
