# Platform Context: Vertical-Focused Pass & Loyalty SaaS

**Last updated:** 2026-06-20
**Status:** Architecture decided. Phase 1 (core refactor + ticketing vertical) is next.

---

## 1. What This Platform Is

This is a **vertical-focused growth and loyalty platform** built on a single Django codebase. It serves three separate, independently branded products designed to maximize customer conversion, lifetime value, and retention for their respective industries. 

The platform leverages Apple and Google Wallet passes as the primary frictionless touchpoints to deliver loyalty campaigns, membership validation, and ticket access. An invisible shared core (loyalty engine, pass issuance, billing, and campaign intelligence) powers all three products under the hood.

> [!IMPORTANT]
> **No Generic Vertical or Dashboard:** The platform strictly serves three distinct verticals (`TICKETING`, `GYM`, and `CAFE`). There is no public generic landing page, generic registration, or generic merchant dashboard. The shared codebase behaves as a common backend backbone only, and every request is routed to its respective vertical.

The three products are:

| Product | Target customer | Core value proposition |
|---|---|---|
| **Ticketing app** | Event organizers, small-to-medium venues | Sell tickets, issue Apple/Google Wallet passes + branded PDF tickets, scan at the door |
| **Gym management app** | Gyms, fitness studios, multi-location chains | Member management, wallet-based membership cards, check-in scanner, renewal reminders |
| **Cafe/Restaurant POS** | Cafes, restaurant chains | Touch-optimized POS terminal, loyalty card issuance via wallet pass, points & campaign management |

Each product runs on its own independent domain (e.g. `www.tickets.com`, `www.gym.com`,
`www.cafe.com`). These are **not** subdomains of a shared apex — they are three entirely separate
domains all served by one Cloud Run deployment.

---

## 2. Technical Architecture

### 2.1 Repository & Django Project Structure

```
gravity/wallet/                    ← single Django project, single repo
│
├── wallet_platform/               ← Django settings, root urls.py, wsgi/asgi
│
├── passes/                        ← SHARED CORE (may be renamed to core/ — optional)
│   ├── models.py                  ← Company, Employee, Location, PassTemplate,
│   │                                 PassInstance, PassAnalytics, StripeTransaction
│   ├── loyalty_engine.py          ← Points math, tier logic, campaign rules
│   ├── pass_issuance.py           ← Apple Wallet (.pkpass) + Google Wallet JWT
│   ├── billing.py                 ← Single Stripe integration, vertical-aware fee logic
│   └── utils/                     ← Existing Apple/Google pass generator utilities
│
├── ticketing/                     ← Product 1 (first to build)
│   ├── models.py                  ← Event, Venue, TicketOrder
│   ├── views.py                   ← Public event pages, ticket purchase, dashboard, door scanner
│   ├── pdf.py                     ← Branded PDF ticket generation (WeasyPrint)
│   ├── urls.py
│   └── templates/ticketing/       ← Completely independent UI from other products
│
├── gym/                           ← Product 2
│   ├── models.py                  ← MembershipPlan, GymMember, CheckIn
│   ├── views.py                   ← Member management, check-in scanner, renewals
│   ├── urls.py
│   └── templates/gym/
│
└── cafe/                          ← Product 3
    ├── models.py                  ← MenuItem, Order, OrderItem, LoyaltyTransaction
    ├── views.py                   ← POS terminal, order flow, loyalty card issuance
    ├── urls.py
    └── templates/cafe/
```

### 2.2 How Multi-Domain Routing Works

All three domains point (via DNS A records) to the same single Cloud Run service.
Django's `ALLOWED_HOSTS` lists all three domains. A thin site-detection middleware
reads `request.get_host()` and sets `request.vertical` (e.g. `'TICKETING'`), which
views and templates use to apply vertical-specific logic and branding.

### 2.3 Infrastructure (unchanged from original)

| Component | Service |
|---|---|
| Compute | Google Cloud Run (`europe-north1`) |
| Database | Google Cloud SQL — PostgreSQL (`wallet-db`, `wallet_db`) |
| Async tasks | Google Cloud Tasks |
| Storage | Google Cloud Storage (`gs://wallet-assets-devcertifit`) |
| Secrets | Google Secret Manager (Apple certs, private keys, API tokens) |
| CI/CD | GitHub Actions → Artifact Registry → Cloud Run |

### 2.4 Technology Stack

| Layer | Technology |
|---|---|
| Backend | Django + Django REST Framework |
| Frontend | Django Templates + Tailwind CSS + Vanilla JS |
| Payments | Stripe (all three verticals) |
| PDF generation | WeasyPrint (HTML → fully branded PDF) |
| Pass generation | Apple Wallet (.pkpass signing) + Google Wallet (JWT) |
| Email | SendGrid or Mailgun via Django email backend |
| Async/Scheduled | Google Cloud Tasks |
| Real-time (future) | Django Channels (WebSocket) — not needed at Phase 1 |

---

## 3. Shared Core Models (`passes/models.py`)

### Existing models (keep, extend minimally)

**`Company`** — One per business client (organizer, gym, cafe).
- Add: `vertical = CharField(choices=['TICKETING', 'GYM', 'CAFE'])`
- Add: `custom_domain = CharField(blank=True, null=True, unique=True)` — for future
  white-label support. Unused at launch but avoids a migration later.

**`Employee`** — Staff of a Company. Roles: OWNER, ADMIN, STAFF, VIEWER.
- No changes needed.

**`PassTemplate`** — The design/configuration of a pass type (colors, logo, pass type).
- Existing `PassTypes`: LOYALTY, GIFT_CARD, MEMBERSHIP, COUPON, EVENT_TICKET, BOARDING_PASS, GENERIC.
- No changes needed to the model itself.

**`PassInstance`** — A single issued pass for a specific customer.
- Add: `vertical = CharField(choices=['TICKETING', 'GYM', 'CAFE'])`
- Add: `phone = CharField(blank=True)` — needed for gym/cafe customer profiles
- Add: `location = ForeignKey('Location', null=True, blank=True)` — which branch issued this pass

**`PassAnalytics`** — Event log per pass action.
- Extend `EventTypes` to include: `CHECK_IN`, `PURCHASE`, `CLASS_BOOKED`, `TICKET_SCANNED`, `STRIPE_CHARGE`

### New shared models (add to `passes/`)

**`Location`** — A physical branch of a Company. Used by gym and cafe verticals.
```python
class Location(models.Model):
    company    = ForeignKey(Company, related_name='locations')
    name       = CharField(max_length=255)   # e.g. "Downtown Branch"
    address    = TextField()
    is_active  = BooleanField(default=True)
```
> IMPORTANT: Add this from the start. Multi-location support is confirmed for gym and cafe
> verticals. It is hard to retrofit later.

**`StripeTransaction`** — Shared billing record across all verticals.
```python
class StripeTransaction(models.Model):
    company                  = ForeignKey(Company)
    vertical                 = CharField(choices=['TICKETING', 'GYM', 'CAFE'])
    stripe_payment_intent_id = CharField(unique=True)
    amount                   = DecimalField()        # gross amount charged to customer
    platform_fee             = DecimalField()        # your cut
    status                   = CharField()           # succeeded / failed / refunded
    created_at               = DateTimeField(auto_now_add=True)
    # Nullable FKs — one per vertical (only the relevant one is set)
    ticket_order             = ForeignKey('ticketing.TicketOrder', null=True, blank=True)
    gym_member               = ForeignKey('gym.GymMember', null=True, blank=True)
```

---

## 4. Vertical-Specific Models

### 4.1 Ticketing (`ticketing/models.py`)

```python
class Venue(models.Model):
    company, name, address, total_capacity

class Event(models.Model):
    company      = ForeignKey(Company)
    venue        = ForeignKey(Venue)
    slug         = SlugField(max_length=255)
    name, date, description
    ticket_types = JSONField()  # [{name: 'VIP', price: 50.00, qty: 100}, ...]
    is_published = BooleanField()
    class Meta:
        unique_together = [('company', 'slug')]  # slug unique per organizer, not globally

class TicketOrder(models.Model):
    event              = ForeignKey(Event)
    pass_instance      = OneToOneField(PassInstance)
    stripe_transaction = OneToOneField(StripeTransaction)
    order_ref          = CharField(unique=True)    # human-readable e.g. TKT-00123
    ticket_type        = CharField()               # VIP / GENERAL / BACKSTAGE
    buyer_name, buyer_email
    pdf_url            = CharField()               # GCS path to branded PDF
    is_scanned         = BooleanField(default=False)
    scanned_at         = DateTimeField(null=True)
```

### 4.2 Gym (`gym/models.py`)

```python
class MembershipPlan(models.Model):
    company, name
    price_per_member = DecimalField()    # your per-member fee is charged on top
    duration_days    = IntegerField()
    class_access     = BooleanField()    # whether plan includes classes

class GymMember(models.Model):
    pass_instance      = OneToOneField(PassInstance)
    plan               = ForeignKey(MembershipPlan)
    location           = ForeignKey(Location)       # home branch
    join_date, expiry_date
    stripe_transaction = ForeignKey(StripeTransaction)

class CheckIn(models.Model):
    member    = ForeignKey(GymMember)
    location  = ForeignKey(Location)    # which branch they checked into
    timestamp = DateTimeField(auto_now_add=True)
```

### 4.3 Cafe/POS (`cafe/models.py`)

```python
class MenuItem(models.Model):
    company, location (nullable — None means chain-wide)
    name, price, category, is_available

class Order(models.Model):
    company, location
    pass_instance      = ForeignKey(PassInstance, null=True)  # customer may not have card
    items              = JSONField()    # snapshot: [{name, price, qty}, ...]
    total              = DecimalField()
    stripe_transaction = ForeignKey(StripeTransaction, null=True)
    loyalty_points_earned = IntegerField(default=0)
    created_at         = DateTimeField(auto_now_add=True)

class LoyaltyTransaction(models.Model):
    order, points_earned, points_redeemed
```

---

## 5. URL Structures

### 5.1 Ticketing App (`www.tickets.com`)

```
# Public-facing (ticket buyers)
/                                          → Platform landing + featured events
/{organizer-slug}/                         → Organizer public profile + their events
/{organizer-slug}/{event-slug}/            → Event detail + ticket purchase flow
/{organizer-slug}/{event-slug}/confirm/    → Order confirmation + pass/PDF download

# Backoffice (organizer dashboard)
/dashboard/                                → Dashboard home (sales overview)
/dashboard/events/                         → Event list
/dashboard/events/new/                     → Create event
/dashboard/events/{event-slug}/            → Manage event (edit, attendee list)
/dashboard/events/{event-slug}/scanner/    → Door scanner (QR scan + mark as scanned)
/dashboard/analytics/                      → Sales analytics
/dashboard/team/                           → Staff management
```

The `organizer-slug` maps directly to `Company.slug` (already in the model).
Event slugs are unique per organizer (`unique_together = [('company', 'slug')]`),
not globally — two organizers can both have a `summer-festival` event.

### 5.2 Gym App (`www.gym.com`)
```
/dashboard/                                → Member list + today's check-ins
/dashboard/members/                        → Full member list
/dashboard/members/new/                    → Add member + issue membership pass
/dashboard/members/{id}/                   → Member detail + check-in history
/dashboard/scanner/                        → Check-in QR scanner
/dashboard/plans/                          → Membership plan management
/dashboard/analytics/                      → Churn, attendance, revenue reports
/dashboard/locations/                      → Branch management (multi-location)
/dashboard/team/                           → Staff management
```

### 5.3 Cafe App (`www.cafe.com`)
```
/dashboard/pos/                            → POS terminal (touch-optimized PWA)
/dashboard/orders/                         → Order history
/dashboard/menu/                           → Menu item management
/dashboard/loyalty/                        → Loyalty card holders + campaign management
/dashboard/analytics/                      → Basket size, visit frequency, campaign ROI
/dashboard/locations/                      → Branch management
/dashboard/team/                           → Staff management
```

---

## 6. Shared Services (`passes/`)

### `PassIssuanceService`
Single service called by all three verticals. Written once.
```python
class PassIssuanceService:
    def issue_event_ticket(self, ticket_order, seat) -> PassInstance: ...
    def issue_membership_card(self, gym_member, plan) -> PassInstance: ...
    def issue_loyalty_card(self, company, customer, template) -> PassInstance: ...
    def push_update(self, pass_instance, updated_fields) -> None: ...  # Apple/Google push
```

### `LoyaltyEngine`
Vertical-aware points logic, shared engine.
```python
class LoyaltyEngine:
    # Cafe:    1pt per €1 spent
    # Gym:     1pt per visit or class attended
    # Tickets: optional — reward repeat buyers
    def earn_points(self, pass_instance, amount, vertical, context={}) -> int: ...
    def redeem_points(self, pass_instance, amount) -> None: ...
    def get_tier(self, pass_instance) -> str: ...  # Bronze / Silver / Gold
    def evaluate_campaign(self, company, customer) -> list: ...
```

### `BillingService`
One Stripe integration, vertical-specific fee logic.
```python
class BillingService:
    def charge_ticket_purchase(self, ticket_order, gross_amount) -> StripeTransaction:
        # platform_fee = settings.TICKETING_FEE_FIXED (e.g. €0.50 per ticket)

    def charge_gym_member(self, gym_member, plan) -> StripeTransaction:
        # platform_fee = settings.GYM_FEE_PER_MEMBER (e.g. €1.00 per active member)

    def charge_cafe_order(self, order) -> StripeTransaction:
        # No platform fee at launch — revenue from future value-added services
```
Fee constants live in Django settings (or a `PlatformConfig` DB model if runtime-editable
is needed). New verticals or new fee types = new methods. Existing code is never touched.

---

## 7. Business Model & Pricing

| Vertical | Pricing model | Notes |
|---|---|---|
| Ticketing | Per-ticket fixed fee (Stripe) | No monthly subscription. Organizers pay per ticket sold. Similar to Eventbrite model. |
| Gym | Per-active-member fixed fee (Stripe) | No monthly subscription. Platform charges per member managed. |
| Cafe | At POS via Stripe | Revenue model TBD — future value-added services. No platform fee at launch. |

All three verticals may have a **freemium tier** in future. Architecture supports this via
a `plan` field on `Company` (add when needed — not required at launch).

---

## 8. PDF Tickets (Ticketing vertical)

- Format: **Fully branded** — event artwork, organizer logo, QR code, seat/ticket type, terms.
- Library: **WeasyPrint** (HTML → PDF, CSS-styled, no layout limitations).
- Storage: Generated PDF saved to GCS, URL stored on `TicketOrder.pdf_url`.
- Delivery: Emailed to buyer + available for download on confirmation page.
- Both PDF and wallet pass are issued for every ticket purchase.

---

## 9. White-Labeling

**Decision: Launch without white-labeling.**

All products run on the platform's own domains. Client backoffice dashboards are at
`www.[product-domain].com/dashboard/`. Customer-facing pages use slug-based paths.

**Future:** If gym clients request it, member self-service portals can be white-labeled
(e.g. `members.mygym.com` via CNAME). The `Company.custom_domain` field is already in
the model (add it from the start). One Django middleware reads the host and maps to a
Company — fully backwards-compatible, ~50 lines of code.

Backoffice dashboards will never be white-labeled. This is standard SaaS practice.

---

## 10. Multi-Location Support

Confirmed required for gym and cafe verticals.

**Key model:** `Location` (in `passes/models.py`, shared across verticals).
- `Location` belongs to a `Company`.
- `GymMember`, `CheckIn`, `Order`, `MenuItem` all have a `ForeignKey` to `Location`.
- `Employee` can optionally be scoped to a specific `Location` (for branch staff).

This must be added in Phase 1 (core refactor). It is difficult to retrofit later.

---

## 11. Development Phases

### Phase 1 — Core Refactor (current codebase → new architecture)
- [ ] Add `Location`, `StripeTransaction` models to `passes/`
- [ ] Add `vertical`, `phone`, `location` fields to `PassInstance`
- [ ] Add `vertical`, `custom_domain` fields to `Company`
- [ ] Extract `PassIssuanceService`, `LoyaltyEngine`, `BillingService` classes
- [ ] Extend `PassAnalytics.EventTypes` with new event types
- [ ] Add site-detection middleware for multi-domain routing
- [ ] Update `ALLOWED_HOSTS` for all three domains

### Phase 2 — Ticketing Vertical (start here)
- [ ] `ticketing/` Django app: `Event`, `Venue`, `TicketOrder` models
- [ ] Organizer registration + dashboard
- [ ] Event creation (name, venue, date, ticket types with capacity + price)
- [ ] Public event page (`/{organizer-slug}/{event-slug}/`)
- [ ] Ticket purchase flow with Stripe Checkout
- [ ] Apple Wallet pass + branded PDF ticket generation
- [ ] Order confirmation page (download pass + PDF)
- [ ] Door scanner (`/dashboard/events/{slug}/scanner/`)
- [ ] Basic sales analytics dashboard

### Phase 3 — Gym Vertical
- [ ] `gym/` Django app: `MembershipPlan`, `GymMember`, `CheckIn` models
- [ ] Member management dashboard
- [ ] Membership card issuance (wallet pass)
- [ ] Stripe per-member billing
- [ ] Check-in QR scanner + check-in log
- [ ] Membership expiry tracking + renewal reminders
- [ ] Multi-location support (branches, branch-scoped staff)
- [ ] Analytics: churn, attendance, plan conversion

### Phase 4 — Cafe/POS Vertical
- [ ] `cafe/` Django app: `MenuItem`, `Order`, `LoyaltyTransaction` models
- [ ] Menu management (chain-wide + branch-specific items)
- [ ] POS terminal (touch-optimized PWA, offline-capable)
- [ ] Loyalty card issuance at checkout
- [ ] Points earn/redeem flow
- [ ] Stripe payment at POS
- [ ] Analytics: basket size, visit frequency, campaign ROI

### Phase 5 — Campaign Engine & Advanced Analytics (ongoing)
- [ ] Automated campaign triggers per vertical (e.g. "no visit in 14 days → coupon")
- [ ] Customer segmentation
- [ ] Push notifications via Apple/Google wallet update API
- [ ] Freemium tier gating per vertical

---

## 12. What Exists Today (in `passes/` app)

The following is already built and should be refactored, not rewritten:

| Component | State |
|---|---|
| `Company`, `Employee`, role-based access | ✅ Complete |
| `PassTemplate`, `PassInstance` | ✅ Complete — needs minor field additions |
| `PassAnalytics` | ✅ Complete — needs new EventTypes |
| Apple Wallet `.pkpass` generation | ✅ Working (`passes/utils/pass_generator.py`) |
| Google Wallet JWT generation | ✅ Working |
| Merchant dashboard (login, register, templates, instances, employees) | ✅ Working |
| Points add/redeem API endpoints | ✅ Working |
| Analytics dashboard with 30-day install trend chart | ✅ Working |
| REST API (DRF ViewSets) | ✅ Working |
| Django i18n setup (English, future-proofed) | ✅ Complete |
| GCP Cloud Run + Cloud SQL deployment + GitHub Actions CI/CD | ✅ Working |
