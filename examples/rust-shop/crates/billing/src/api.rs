//! Billing's public surface: commands and integration events, never domain types.

use crate::domain::payment::{CaptureError, Payment, PaymentId};
use shared_kernel::Money;

/// Published when a payment for an order has been captured.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PaymentCapturedV1 {
    pub payment_id: u128,
    pub order_id: u128,
    pub amount_minor: i64,
    pub currency: &'static str,
}

#[derive(Debug, PartialEq, Eq)]
pub enum CaptureFailure {
    ZeroAmount,
}

/// Capture a payment for an order.
///
/// # Errors
/// `ZeroAmount` if there is nothing to capture.
pub fn capture_payment(
    payment_id: u128,
    order_id: u128,
    amount: Money,
) -> Result<PaymentCapturedV1, CaptureFailure> {
    let payment =
        Payment::capture(PaymentId::new(payment_id), order_id, amount).map_err(|e| match e {
            CaptureError::ZeroAmount => CaptureFailure::ZeroAmount,
        })?;
    Ok(PaymentCapturedV1 {
        payment_id: payment.id().value(),
        order_id: payment.order_ref(),
        amount_minor: payment.amount().minor(),
        currency: payment.amount().currency().code(),
    })
}
