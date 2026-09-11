import os
import tempfile

# Tests never write records/audio into the application's normal local runtime directory.
os.environ.setdefault("SAUDI_STA_DATA_DIR", tempfile.mkdtemp(prefix="saudi-sta-tests-"))
