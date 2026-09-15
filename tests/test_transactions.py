import pytest

from omni_retail import services
from omni_retail.transactions import (
    Cart,
    CartItem,
    CustomerNotFoundError,
    EmptyCartError,
    InsufficientStockError,
    InvalidDiscountError,
    InvalidPaymentMethodError,
    InvalidQuantityError,
    ProductNotFoundError,
    complete_sale,
)


def _healthy_product(session, exclude_id=None):
    for p in services.list_products(session):
        if p.status == "healthy" and p.product_id != exclude_id:
            return p
    raise AssertionError("seeded data has no healthy-stock product to test with")


def _order_count(session):
    from omni_retail.models import Order

    return session.query(Order).count()


def test_successful_sale_creates_order_and_decrements_inventory(fresh_session):
    product = _healthy_product(fresh_session)
    stock_before = product.current_stock

    receipt = complete_sale(
        fresh_session,
        Cart(items=[CartItem(product_id=product.product_id, quantity=3)], payment_method="cash"),
    )

    assert receipt.order_id is not None
    assert receipt.total == round(product.selling_price * 3, 2)

    after = next(p for p in services.list_products(fresh_session) if p.product_id == product.product_id)
    assert after.current_stock == stock_before - 3


def test_guest_sale_has_no_customer(fresh_session):
    product = _healthy_product(fresh_session)
    receipt = complete_sale(
        fresh_session,
        Cart(items=[CartItem(product_id=product.product_id, quantity=1)], payment_method="cash"),
    )
    assert receipt.customer_id is None
    assert receipt.customer_name == "Guest"

    order = services.get_order(fresh_session, receipt.order_id)
    assert order.customer_id is None
    assert order.customer_name == "Guest"


def test_sale_with_existing_customer_is_attributed(fresh_session):
    product = _healthy_product(fresh_session)
    customer = services.search_customers(fresh_session, "", limit=1)[0]

    receipt = complete_sale(
        fresh_session,
        Cart(
            items=[CartItem(product_id=product.product_id, quantity=1)],
            payment_method="credit_card",
            customer_id=customer.customer_id,
        ),
    )
    assert receipt.customer_id == customer.customer_id
    assert receipt.customer_name == customer.name


def test_percent_discount_is_applied_and_prorated_across_lines(fresh_session):
    p1 = _healthy_product(fresh_session)
    p2 = _healthy_product(fresh_session, exclude_id=p1.product_id)

    receipt = complete_sale(
        fresh_session,
        Cart(
            items=[
                CartItem(product_id=p1.product_id, quantity=2),
                CartItem(product_id=p2.product_id, quantity=1),
            ],
            payment_method="cash",
            discount_type="percent",
            discount_value=10,
        ),
    )

    expected_subtotal = round(p1.selling_price * 2 + p2.selling_price * 1, 2)
    assert receipt.subtotal == expected_subtotal
    assert receipt.discount_total == round(expected_subtotal * 0.10, 2)
    assert receipt.total == round(expected_subtotal - receipt.discount_total, 2)
    # sum of line totals must reconcile exactly with the receipt total
    assert round(sum(line.line_total for line in receipt.lines), 2) == receipt.total


def test_fixed_amount_discount_is_applied(fresh_session):
    product = _healthy_product(fresh_session)
    receipt = complete_sale(
        fresh_session,
        Cart(
            items=[CartItem(product_id=product.product_id, quantity=1)],
            payment_method="cash",
            discount_type="amount",
            discount_value=1.5,
        ),
    )
    assert receipt.discount_total == 1.5
    assert receipt.total == round(product.selling_price - 1.5, 2)


def test_sale_is_immediately_visible_to_analytics(fresh_session):
    product = _healthy_product(fresh_session)
    revenue_before = services.revenue(fresh_session)

    receipt = complete_sale(
        fresh_session,
        Cart(items=[CartItem(product_id=product.product_id, quantity=1)], payment_method="cash"),
    )

    assert services.revenue(fresh_session) == round(revenue_before + receipt.total, 2)
    order_ids = [o.order_id for o in services.list_orders(fresh_session, limit=5)]
    assert receipt.order_id in order_ids


@pytest.mark.parametrize(
    "build_cart,error_cls",
    [
        (lambda p, c: Cart(items=[], payment_method="cash"), EmptyCartError),
        (lambda p, c: Cart(items=[CartItem(product_id=p.product_id, quantity=0)], payment_method="cash"), InvalidQuantityError),
        (lambda p, c: Cart(items=[CartItem(product_id=p.product_id, quantity=-1)], payment_method="cash"), InvalidQuantityError),
        (lambda p, c: Cart(items=[CartItem(product_id=999999, quantity=1)], payment_method="cash"), ProductNotFoundError),
        (lambda p, c: Cart(items=[CartItem(product_id=p.product_id, quantity=1)], payment_method="bitcoin"), InvalidPaymentMethodError),
        (lambda p, c: Cart(items=[CartItem(product_id=p.product_id, quantity=1)], payment_method="cash", customer_id=999999), CustomerNotFoundError),
        (
            lambda p, c: Cart(
                items=[CartItem(product_id=p.product_id, quantity=1)],
                payment_method="cash",
                discount_type="percent",
                discount_value=150,
            ),
            InvalidDiscountError,
        ),
        (
            lambda p, c: Cart(
                items=[CartItem(product_id=p.product_id, quantity=1)],
                payment_method="cash",
                discount_type="amount",
                discount_value=999999,
            ),
            InvalidDiscountError,
        ),
    ],
)
def test_validation_error_leaves_database_untouched(fresh_session, build_cart, error_cls):
    product = _healthy_product(fresh_session)
    customer = services.search_customers(fresh_session, "", limit=1)[0]
    stock_before = product.current_stock
    orders_before = _order_count(fresh_session)

    with pytest.raises(error_cls):
        complete_sale(fresh_session, build_cart(product, customer))

    after = next(p for p in services.list_products(fresh_session) if p.product_id == product.product_id)
    assert after.current_stock == stock_before
    assert _order_count(fresh_session) == orders_before


def test_insufficient_stock_names_the_product_and_available_quantity(fresh_session):
    product = _healthy_product(fresh_session)
    with pytest.raises(InsufficientStockError) as exc_info:
        complete_sale(
            fresh_session,
            Cart(items=[CartItem(product_id=product.product_id, quantity=product.current_stock + 1)], payment_method="cash"),
        )
    assert exc_info.value.product_name == product.name
    assert exc_info.value.available == product.current_stock
    assert exc_info.value.requested == product.current_stock + 1


def test_duplicate_line_items_for_same_product_are_aggregated(fresh_session):
    product = _healthy_product(fresh_session)
    receipt = complete_sale(
        fresh_session,
        Cart(
            items=[
                CartItem(product_id=product.product_id, quantity=1),
                CartItem(product_id=product.product_id, quantity=2),
            ],
            payment_method="cash",
        ),
    )
    assert len(receipt.lines) == 1
    assert receipt.lines[0].quantity == 3

    after = next(p for p in services.list_products(fresh_session) if p.product_id == product.product_id)
    assert after.current_stock == product.current_stock - 3
