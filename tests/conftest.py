import os
import pytest


@pytest.fixture
def temp_dir(tmp_path):
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)
