"""Cart aggregate. Behaviour is defined by specs/cart/cart.md (CART-xxx clauses)."""

from __future__ import annotations

from dataclasses import dataclass

MAX_DISTINCT_LINES = 10


class CartError(Exception):
    """Base class for cart domain errors."""


class InvalidQuantity(CartError):
    pass


class InvalidPrice(CartError):
    pass


class CartFull(CartError):
    pass


class UnknownSku(CartError):
    pass


@dataclass(frozen=True)
class Line:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def subtotal_cents(self) -> int:
        return self.quantity * self.unit_price_cents


class Cart:
    def __init__(self) -> None:
        self._lines: dict[str, Line] = {}

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(self._lines.values())

    @property
    def total_cents(self) -> int:
        return sum(line.subtotal_cents for line in self._lines.values())

    def add(self, sku: str, quantity: int, unit_price_cents: int) -> None:
        if quantity < 1:
            raise InvalidQuantity
        if unit_price_cents < 0:
            raise InvalidPrice
        existing = self._lines.get(sku)
        if existing is not None:
            self._lines[sku] = Line(sku, existing.quantity + quantity, existing.unit_price_cents)
            return
        if len(self._lines) >= MAX_DISTINCT_LINES:
            raise CartFull
        self._lines[sku] = Line(sku, quantity, unit_price_cents)

    def remove(self, sku: str) -> None:
        if sku not in self._lines:
            raise UnknownSku(sku)  # pragma: no mutate (the spec does not define error payloads)
        del self._lines[sku]
