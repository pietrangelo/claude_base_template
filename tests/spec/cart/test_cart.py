"""Tests derived from specs/cart/cart.md. Regenerate from the spec; never edit to fit the code."""

import pytest

from shop.cart import Cart, CartFull, InvalidPrice, InvalidQuantity, UnknownSku


def full_cart() -> Cart:
    cart = Cart()
    for i in range(10):
        cart.add(f"SKU-{i}", 1, 100)
    return cart


@pytest.mark.spec("CART-001")
def test_cart_001_new_cart_is_empty_with_zero_total():
    cart = Cart()
    assert cart.lines == ()
    assert cart.total_cents == 0


@pytest.mark.spec("CART-002")
@pytest.mark.parametrize("quantity", [0, -1])
def test_cart_002_quantity_below_one_is_rejected_and_cart_unchanged(quantity):
    cart = Cart()
    cart.add("APPLE", 1, 50)
    with pytest.raises(InvalidQuantity):
        cart.add("PEAR", quantity, 50)
    assert [line.sku for line in cart.lines] == ["APPLE"]
    assert cart.total_cents == 50


@pytest.mark.spec("CART-002")
def test_cart_002_quantity_of_one_is_accepted():
    cart = Cart()
    cart.add("APPLE", 1, 50)
    assert cart.total_cents == 50


@pytest.mark.spec("CART-003")
def test_cart_003_negative_price_is_rejected_and_cart_unchanged():
    cart = Cart()
    with pytest.raises(InvalidPrice):
        cart.add("APPLE", 1, -1)
    assert cart.lines == ()


@pytest.mark.spec("CART-003")
def test_cart_003_zero_price_is_allowed():
    cart = Cart()
    cart.add("FREEBIE", 2, 0)
    assert cart.total_cents == 0
    assert len(cart.lines) == 1


@pytest.mark.spec("CART-004")
def test_cart_004_eleventh_distinct_sku_is_rejected_and_cart_unchanged():
    cart = full_cart()
    with pytest.raises(CartFull):
        cart.add("ONE-TOO-MANY", 1, 100)
    assert len(cart.lines) == 10
    assert cart.total_cents == 1000


@pytest.mark.spec("CART-004", "CART-006")
def test_cart_004_more_of_existing_sku_in_full_cart_is_allowed():
    cart = full_cart()
    cart.add("SKU-0", 2, 100)
    assert len(cart.lines) == 10
    assert cart.total_cents == 1200


@pytest.mark.spec("CART-005")
def test_cart_005_total_is_sum_of_quantity_times_unit_price():
    cart = Cart()
    cart.add("APPLE", 3, 50)
    cart.add("PEAR", 2, 75)
    assert cart.total_cents == 3 * 50 + 2 * 75


@pytest.mark.spec("CART-006")
def test_cart_006_same_sku_merges_and_keeps_first_unit_price():
    cart = Cart()
    cart.add("APPLE", 1, 50)
    cart.add("APPLE", 2, 80)
    assert len(cart.lines) == 1
    (line,) = cart.lines
    assert line.quantity == 3
    assert line.unit_price_cents == 50
    assert cart.total_cents == 150


@pytest.mark.spec("CART-007")
def test_cart_007_remove_deletes_whole_line():
    cart = Cart()
    cart.add("APPLE", 3, 50)
    cart.add("PEAR", 1, 75)
    cart.remove("APPLE")
    assert [line.sku for line in cart.lines] == ["PEAR"]
    assert cart.total_cents == 75


@pytest.mark.spec("CART-007")
def test_cart_007_removing_unknown_sku_is_rejected_and_cart_unchanged():
    cart = Cart()
    cart.add("APPLE", 1, 50)
    with pytest.raises(UnknownSku):
        cart.remove("PEAR")
    assert cart.total_cents == 50
