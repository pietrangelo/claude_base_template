# Shopping cart

Bounded context: `cart`
Clause prefix: `CART`

This is the worked example that ships with the template. Replace it with your
own contexts once you have read it.

## Ubiquitous language

- **Cart**: the aggregate root. Holds the lines a customer intends to buy.
- **Line**: one SKU in the cart, with a quantity and a unit price.
- **SKU**: stock keeping unit, a non-empty string identifying a product.
- **Money**: an amount in integer cents. Never a float.

## Invariants

### CART-001 Empty cart total
A new cart has no lines and a total of 0 cents.

### CART-002 Quantity must be positive
Adding a line with a quantity lower than 1 raises `InvalidQuantity` and leaves
the cart unchanged.

### CART-003 Unit price must not be negative
Adding a line with a unit price lower than 0 cents raises `InvalidPrice` and
leaves the cart unchanged. A price of exactly 0 cents is allowed.

### CART-004 Maximum distinct lines
A cart holds at most 10 distinct SKUs. Adding an 11th distinct SKU raises
`CartFull` and leaves the cart unchanged. Adding more of a SKU already in a full
cart is allowed.

## Behaviours

### CART-005 Total is the sum of lines
The total is the sum over all lines of quantity times unit price, in cents.

### CART-006 Same SKU merges
Adding a SKU that is already in the cart increases that line's quantity instead of
creating a second line. The unit price of the existing line is kept.

### CART-007 Removing a line
Removing a SKU deletes its line entirely. Removing a SKU that is not in the cart
raises `UnknownSku` and leaves the cart unchanged.
