import pytest

from capno_core.config import make_config


@pytest.fixture
def cfg():
    return make_config({"t10_90_ms": 300, "delay_ms": 1000, "max_resolvable_rr": 60.0})
