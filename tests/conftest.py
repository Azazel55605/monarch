import json
from pathlib import Path

import pytest


@pytest.fixture
def monitors():
    return json.loads((Path(__file__).parent / "fixtures" / "monitors.json").read_text())
