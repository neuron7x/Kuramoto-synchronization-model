from core.utils.network import is_public_bind


def test_public_bind_detection() -> None:
    assert is_public_bind("0.0.0.0") is True
    assert is_public_bind("8.8.8.8") is True
    assert is_public_bind("127.0.0.1") is False
    assert is_public_bind("::1") is False
    assert is_public_bind("192.168.1.10") is False
    assert is_public_bind("localhost") is False
