import pytest
from django.test import TestCase


@pytest.fixture(autouse=True)
def use_db(db):
    """Auto-use DB fixture for all tests."""
    pass
