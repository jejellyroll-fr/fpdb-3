import pytest
from Card import twoStartCards


def test_twoStartCards():
    # Test pair
    result = twoStartCards(4, 'd', 4, 'c')
    assert result == 29
    
    # Test suited
    result = twoStartCards(10, 'h', 12, 'h')
    assert result == 139
    
    # Test unsuited
    result = twoStartCards(6, 's', 9, 'c')
    assert result == 60
    
    # Test invalid cards
    result = twoStartCards(1, 'd', 15, 'h')
    assert result == 170

    # Test invalid value
    result = twoStartCards(5, 'd', 18, 's')
    assert result == 170