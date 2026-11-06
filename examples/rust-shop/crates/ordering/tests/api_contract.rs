//! Contract tests for Ordering's public api, as a consumer sees it.

use billing::api::capture_payment;
use ordering::api::{
    LineRequest, OrderStatusV1, OrderingFailure, OrderingService, PlaceOrderRequest,
};
use shared_kernel::{Currency, Money};

fn request() -> PlaceOrderRequest {
    PlaceOrderRequest {
        customer_id: 9,
        lines: vec![LineRequest {
            sku: "ABC-0001".to_owned(),
            quantity: 3,
            unit_price_minor: 250,
        }],
    }
}

#[test]
fn placing_an_order_publishes_its_total() {
    let service = OrderingService::default();
    let placed = service.place_order(&request()).unwrap();
    assert_eq!((placed.total_minor, placed.currency), (750, "GBP"));
}

#[test]
fn a_paid_order_cannot_be_cancelled() {
    let service = OrderingService::default();
    let placed = service.place_order(&request()).unwrap();
    let amount = Money::new(placed.total_minor, Currency::Gbp).unwrap();
    let captured = capture_payment(1, placed.order_id, amount).unwrap();
    service.on_payment_captured(&captured).unwrap();
    service.on_payment_captured(&captured).unwrap(); // idempotent
    assert_eq!(
        service.cancel_order(placed.order_id),
        Err(OrderingFailure::AlreadyPaid)
    );
    assert_eq!(
        service.order_status(placed.order_id),
        Ok(OrderStatusV1::Paid)
    );
}

#[test]
fn a_malformed_sku_is_rejected_at_the_edge() {
    let service = OrderingService::default();
    let mut bad = request();
    bad.lines[0].sku = "abc".to_owned();
    assert!(matches!(
        service.place_order(&bad),
        Err(OrderingFailure::InvalidRequest(_))
    ));
}
