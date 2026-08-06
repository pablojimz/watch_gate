from app.billing import calculate_total


def test_calculate_total():
    assert calculate_total([]) == 0
