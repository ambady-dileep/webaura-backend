# WebAura — Entity-Relationship Diagram

Rendered with [Mermaid](https://mermaid.js.org/) — GitHub, GitLab, and most
modern Markdown viewers render this block natively with no extra tooling.
If your viewer doesn't, paste the block between the fences into
https://mermaid.live to see it rendered.

```mermaid
erDiagram
    USER ||--o{ RESTAURANT : owns
    USER ||--o| CART : has
    USER ||--o{ ADDRESS : has
    USER ||--o{ ORDER : places
    USER ||--o{ NOTIFICATION : receives
    USER ||--o{ DELIVERY : "delivers (as delivery_partner)"

    RESTAURANT ||--o{ CATEGORY : has
    RESTAURANT ||--o{ FOODITEM : has
    RESTAURANT ||--o{ ORDER : fulfills

    CATEGORY ||--o{ FOODITEM : groups

    CART ||--o{ CARTITEM : contains
    CART }o--o| RESTAURANT : "locked to (nullable)"
    FOODITEM ||--o{ CARTITEM : "referenced by"

    ADDRESS ||--o{ ORDER : "delivery address for"

    ORDER ||--o{ ORDERITEM : contains
    ORDER |o--o| PAYMENT : "has (1:1)"
    ORDER |o--o| DELIVERY : "has (1:1)"
    ORDER }o--o| COUPON : "may use"
    ORDER ||--o{ NOTIFICATION : "generates"
    FOODITEM ||--o{ ORDERITEM : "snapshotted into"

    USER {
        string username
        string role "customer / restaurant_owner / delivery_partner / admin"
        string phone_number
    }
    RESTAURANT {
        int id PK
        int owner_id FK
        string name "indexed"
        bool is_active
    }
    CATEGORY {
        int id PK
        int restaurant_id FK
        string name
    }
    FOODITEM {
        int id PK
        int restaurant_id FK
        int category_id FK
        string name "indexed"
        decimal price
        bool is_available
    }
    CART {
        int id PK
        int customer_id FK "OneToOne"
        int restaurant_id FK "nullable"
    }
    CARTITEM {
        int id PK
        int cart_id FK
        int food_item_id FK
        int quantity
    }
    ADDRESS {
        int id PK
        int customer_id FK
        string city
        string pincode
    }
    ORDER {
        int id PK
        string order_number "unique, human-readable"
        int customer_id FK
        int restaurant_id FK
        string status "state machine"
        int delivery_address_id FK
        int coupon_id FK "nullable, SET_NULL"
        decimal subtotal
        decimal discount_amount
        decimal total_amount
        string idempotency_key "unique per customer"
    }
    ORDERITEM {
        int id PK
        int order_id FK
        int food_item_id FK "nullable, SET_NULL"
        string food_item_name "snapshot"
        decimal price_at_purchase "snapshot"
        int quantity
    }
    COUPON {
        int id PK
        string code "unique"
        string discount_type "FLAT / PERCENTAGE"
        decimal value
        decimal min_order_amount
        int usage_limit
        int times_used
    }
    PAYMENT {
        int id PK
        int order_id FK "OneToOne"
        string status "PENDING / SUCCESS / FAILED"
        decimal amount
    }
    DELIVERY {
        int id PK
        int order_id FK "OneToOne"
        int delivery_partner_id FK "nullable"
        string status "state machine"
    }
    NOTIFICATION {
        int id PK
        int user_id FK
        int order_id FK "nullable, SET_NULL"
        string message
    }
```

## Notes on relationships that aren't obvious from the diagram shape

- **`Order.coupon`** is `SET_NULL`: deleting a `Coupon` never deletes or
  corrupts past orders — `Order.discount_amount` is a snapshot taken at
  apply-time, not a live computation off the coupon, so historical order
  totals are unaffected either way.
- **`OrderItem.food_item`** is also `SET_NULL`: an `OrderItem` keeps its own
  `food_item_name`/`price_at_purchase` snapshot, so a deleted or
  price-changed `FoodItem` never alters what a past order shows.
- **`Cart.restaurant`** is nullable and reset to `None` whenever the cart is
  emptied — this is what enforces the "single-restaurant cart" rule at the
  application level (see `restaurants/views.py::CartItemCreateView`).
- **`Payment`** and **`Delivery`** are both strict `OneToOneField`s on
  `Order` — at most one payment record and one delivery record can ever
  exist per order.