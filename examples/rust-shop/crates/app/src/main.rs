//! Composition root: wires the contexts through their public apis.

use billing::api::capture_payment;
use ordering::api::{LineRequest, OrderingService, PlaceOrderRequest};

fn main() {
    let ordering = OrderingService::default();
    let request = PlaceOrderRequest {
        customer_id: 42,
        lines: vec![LineRequest {
            sku: "TEA-0001".to_owned(),
            quantity: 2,
            unit_price_minor: 450,
        }],
    };
    match ordering.place_order(&request) {
        Ok(placed) => {
            println!(
                "placed order {} for {} {}",
                placed.order_id, placed.total_minor, placed.currency
            );
            match placed_amount(&placed).and_then(|amount| {
                capture_payment(1, placed.order_id, amount).map_err(|e| format!("{e:?}"))
            }) {
                Ok(captured) => match ordering.on_payment_captured(&captured) {
                    Ok(()) => println!(
                        "payment {} confirmed; order is {:?}",
                        captured.payment_id,
                        ordering.order_status(placed.order_id)
                    ),
                    Err(e) => eprintln!("could not confirm payment: {e:?}"),
                },
                Err(e) => eprintln!("could not capture payment: {e}"),
            }
        }
        Err(e) => eprintln!("could not place order: {e:?}"),
    }
}

fn placed_amount(placed: &ordering::api::OrderPlacedV1) -> Result<shared_kernel::Money, String> {
    shared_kernel::Money::new(placed.total_minor, shared_kernel::Currency::Gbp)
        .map_err(|e| format!("{e:?}"))
}
