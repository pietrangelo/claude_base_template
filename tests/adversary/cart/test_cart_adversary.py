"""Adversarial tests: boundary values and state corruption attempts against the cart.

Written by the adversary agent without seeing the implementer's reasoning.
"""

import pytest

from shop.cart import Cart, CartFull, InvalidPrice, InvalidQuantity


@pytest.mark.spec("CART-004")
def test_cart_004_exactly_ten_distinct_skus_fit():
    cart = Cart()
    for i in range(10):
        cart.add(f"SKU-{i}", 1, 1)
    assert len(cart.lines) == 10


@pytest.mark.spec("CART-004")
def test_cart_004_removing_a_line_frees_a_slot():
    cart = Cart()
    for i in range(10):
        cart.add(f"SKU-{i}", 1, 1)
    cart.remove("SKU-3")
    cart.add("NEW", 1, 1)
    assert len(cart.lines) == 10


@pytest.mark.spec("CART-002", "CART-006")
def test_cart_002_invalid_quantity_on_existing_sku_does_not_change_its_line():
    cart = Cart()
    cart.add("APPLE", 2, 50)
    with pytest.raises(InvalidQuantity):
        cart.add("APPLE", 0, 50)
    assert cart.lines[0].quantity == 2


@pytest.mark.spec("CART-003", "CART-006")
def test_cart_003_invalid_price_on_existing_sku_does_not_change_its_line():
    cart = Cart()
    cart.add("APPLE", 2, 50)
    with pytest.raises(InvalidPrice):
        cart.add("APPLE", 1, -5)
    assert cart.lines[0].quantity == 2


@pytest.mark.spec("CART-004", "CART-002")
def test_cart_004_full_cart_rejects_invalid_quantity_before_capacity():
    cart = Cart()
    for i in range(10):
        cart.add(f"SKU-{i}", 1, 1)
    with pytest.raises((InvalidQuantity, CartFull)):
        cart.add("NEW", 0, 1)
    assert len(cart.lines) == 10


@pytest.mark.spec("CART-005")
def test_cart_005_large_amounts_stay_exact_integers():
    cart = Cart()
    cart.add("GOLD", 3, 10**12 + 1)
    assert cart.total_cents == 3 * (10**12 + 1)
    assert isinstance(cart.total_cents, int)


@pytest.mark.spec("CART-007")
def test_cart_007_removed_sku_can_be_added_again_with_new_price():
    cart = Cart()
    cart.add("APPLE", 1, 50)
    cart.remove("APPLE")
    cart.add("APPLE", 1, 70)
    assert cart.total_cents == 70


@pytest.mark.spec("CART-006")
def test_cart_006_merged_line_keeps_its_sku():
    cart = Cart()
    cart.add("APPLE", 1, 50)
    cart.add("APPLE", 1, 50)
    assert [line.sku for line in cart.lines] == ["APPLE"]
