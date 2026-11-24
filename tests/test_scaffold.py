import doublecheck


def test_package_is_importable():
    assert doublecheck.__doc__ is not None
