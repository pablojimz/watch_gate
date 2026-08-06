from app.billing import compute_total


def test_compute_total():
    assert compute_total([]) == 0
