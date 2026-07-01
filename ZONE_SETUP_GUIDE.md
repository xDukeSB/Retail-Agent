# RetailAI Agent — Advanced Zone Setup & Payment Detection Guide

This guide explains how to configure camera zones in the RetailAI dashboard to achieve highly accurate, real-time transaction intelligence across all 5 core payment signals.

---

## 🏗️ The 5 Core Transaction Signals

The RetailAI Transaction Engine tracks visitor progression through the purchase journey using 5 distinct signals:

1. **`checkout_zone_entered`** — Visitor enters the checkout area.
2. **`queue_completed`** — Visitor waits in a queue line for ≥20 seconds and progresses to checkout.
3. **`cash_exchange_detected`** — Visitor completes a cash transaction.
4. **`card_machine_interaction`** — Visitor interacts with a POS Card Terminal.
5. **`upi_payment_interaction`** — Visitor completes a UPI / QR Code scan payment.

---

## 🎯 Option A: Dedicated Zone Configuration (Highest Precision)

For maximum precision, draw specific polygon zones in the **Live Cameras → Zone Editor** corresponding to the physical layout of your cashier desk.

### 1. Card Machine Zone
* **Where to draw:** Draw a small polygon directly over the physical POS / card swipe terminal area on the checkout counter.
* **Naming convention:** Name the zone `Card Machine`, `POS Terminal`, `Card Payment`, or `Card`. (The engine matches keywords: `card`, `payment`, `terminal`, `pos`, `machine`).
* **Trigger behavior:** When a visitor stands in this zone for **≥10 seconds**, the engine registers a `card_machine_interaction` (+25 pts) and transitions the visitor to `PAYMENT_INTERACTION`.

### 2. UPI / QR Payment Zone
* **Where to draw:** Draw a polygon over the physical QR code display stand or UPI payment counter plaque.
* **Naming convention:** Name the zone `UPI Payment`, `QR Stand`, `PhonePe`, `GPay`, or `Paytm`. (The engine matches keywords: `upi`, `qr`, `phonepe`, `gpay`, `paytm`, `bhim`).
* **Trigger behavior:** When a visitor stands in this zone for **≥5 seconds**, the engine registers a `upi_payment_interaction` (+20 pts).

### 3. Queue Zone
* **Where to draw:** Draw a polygon covering the waiting line leading up to the cashier desk.
* **Naming convention:** Name the zone `Queue`, `Waiting Line`, or `Checkout Queue` (or set `zone_type = "queue"`).
* **Trigger behavior:** Requires a dwell time of **≥20 seconds** followed by exiting into the checkout zone to fire `queue_completed`.

---

## 🧠 Option B: Smart Heuristic Inference (Zero-Config Fallback)

If your store layout does not allow drawing separate Card/UPI zones, or you prefer a simpler setup, you only need to draw a single general checkout zone:

* **Naming convention:** Name the zone `Checkout`, `Cashier`, `Till`, or `Register`.

The Transaction Engine's **Smart Heuristic AI** will automatically observe the visitor's dwell time inside this checkout zone to infer the correct payment method upon exit:

| Dwell Time at Checkout | Inferred Payment Method | Engine Signal Fired | Rationale |
| :--- | :--- | :--- | :--- |
| **10s to 30s** | **UPI / QR Code** | `upi_payment_interaction` | Fast tap-and-go or quick mobile QR scan. |
| **30s to 90s** | **Card Machine / POS** | `card_machine_interaction` | Standard card insertion, PIN entry, and receipt printing. |
| **> 90s** | **Cash Exchange** | `cash_exchange_detected` | Slower transaction involving counting bills and returning change. |
| **< 10s** | *None (Browsing)* | *No payment signal* | Too brief; visitor walked past or asked a quick question. |

---

## 🚀 Best Practices for Camera Placement

1. **Top-Down / High-Angle View:** Mount cameras at 2.5m – 3.5m height pointing down at the checkout desk at a 45° to 60° angle to minimize occlusion between waiting customers.
2. **Zone Overlap:** Ensure the `Queue` zone directly abuts or slightly overlaps the `Checkout` zone so the state machine can seamlessly track transitions without losing the visitor's `track_id`.
