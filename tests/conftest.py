```python
import pytest
import os

# Define a common fixture for clearing temporary files if needed
@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_files():
    """
    Fixture to clean up any temporary files created during tests.
    """
    yield
    # Example cleanup logic (add more if your tests create specific files)
    if os.path.exists("adhan_times.json"):
        os.remove("adhan_times.json")
    if os.path.exists("temp_adhan_times.json"):
        os.remove("temp_adhan_times.json")

# Add other common fixtures here if needed
```
