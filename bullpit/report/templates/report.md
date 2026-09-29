{# Markdown report, sections in architecture sec7's order. A section that does not apply is None on the Report and skipped here. `for_prompt` leaves out prose, request ID and timestamp. #}
{% set labels = {"buy": "Buy", "no_trade": "No trade", "rejected": "Rejected"} %}
# {{ r.ticker }}{% if r.company_name %}, {{ r.company_name }}{% endif %}: {{ labels[r.outcome] }}

Price data through {{ r.as_of }} ({{ r.mode }} mode)
{% if not for_prompt %}
Report time {{ r.generated_at.strftime("%Y-%m-%d %H:%M UTC") }}, request `{{ r.request_id }}`
{% endif %}

## Recommendation

**{{ labels[r.outcome] }}**{% if r.confidence is not none %}, confidence {{ r.confidence|num }}{% endif %}


{% if r.summary and not for_prompt %}
{{ r.summary }}

{% endif %}
{% if r.reason and r.outcome != "rejected" %}
Reason: {{ r.reason }}{% if r.reason_detail %} "{{ r.reason_detail }}"{% endif %}


{% endif %}
{% if r.order %}
## Suggested order

| | |
|---|---|
| Order | {{ r.order.shares }} shares, about {{ r.order.cost|money }} ({{ r.order_pct_of_equity|pct }} of equity) |
| Reference price | {{ r.order.reference_price|money }} |
| Stop-loss | {{ r.order.stop_loss|money }}, maximum loss about {{ r.order.max_loss|money }} |
| Take-profit | {{ r.order.take_profit|money }}, possible gain about {{ r.order.max_gain|money }} |
| Exit style | {{ r.order.exit_style }} |

{% endif %}
{% if r.signals %}
## What the analysts found

| Analyst | Direction | Confidence | Note |
|---|---|---|---|
{% for s in r.signals %}
| {{ s.analyst }} | {{ s.direction }} | {{ s.confidence|num }} | {{ ("flagged: " if s.flagged else "") ~ (s.note or "") }} |
{% endfor %}

{% for s in r.signals if s.evidence %}
Evidence, {{ s.analyst }}:
{% for e in s.evidence %}
- {{ e.id }}: {{ e.fact }}
{% endfor %}

{% endfor %}
{% endif %}
{% if r.debate %}
## The debate

{% if not for_prompt %}
{% if r.debate.strongest_bull %}
- Strongest bull point: {{ r.debate.strongest_bull }}
{% endif %}
{% if r.debate.strongest_bear %}
- Strongest bear point: {{ r.debate.strongest_bear }}
{% endif %}
{% if r.debate.bull_conceded %}
- What the bull conceded: {{ r.debate.bull_conceded }}
{% endif %}
{% if r.debate.unresolved %}
- Unresolved: {{ r.debate.unresolved }}
{% endif %}

{% endif %}
Final convictions: bull {{ r.debate.bull_conviction|num }}, bear {{ r.debate.bear_conviction|num }}. Unsupported points: {{ r.debate.unsupported_points }}.

{% endif %}
{% if r.attempts %}
## Risk manager

{% if r.order %}
Stage A size set by the {{ r.order.limit }} limit{% if r.order.shares < r.order.limit_shares[r.order.limit] %}; the risk review shrank it to {{ r.order.shares }} shares{% endif %}. Shares allowed by each limit: target {{ r.order.limit_shares["target"] }}, risk {{ r.order.limit_shares["risk"] }}, cap {{ r.order.limit_shares["cap"] }}, cash {{ r.order.limit_shares["cash"] }}.

{% endif %}
Trader attempts, in order:

{% for a in r.attempts %}
- {{ a.action|replace("_", " ")|capitalize }}{% if a.action == "buy" %}, {{ (a.target_weight * 100)|pct }} target, {{ a.exit_style }} exits{% endif %}, confidence {{ a.confidence|num }}.{% if a.blocked_reason %} Stage A blocked it: {{ a.blocked_reason }}{% elif a.shares is not none %} Stage A sized it at {{ a.shares }} shares.{% endif %}{% if a.review_decision %} Review: {{ a.review_decision }}{% if a.review_clamped %} (clamped){% endif %}{% if a.review_reason %} "{{ a.review_reason }}"{% endif %}.{% endif %}

{% endfor %}

Loss warning: {{ "not available" if r.loss_warning is none else ("equity fell more than the limit" if r.loss_warning else "none") }}

{% endif %}
{% if r.would_change_view is not none and not for_prompt %}
## What would change the view

{{ r.would_change_view }}

{% endif %}
{% if r.market %}
## Market context

- SPY: {% if r.market.spy_above is none %}200-day average not available{% else %}{{ r.market.spy_close|money }} is {{ "above" if r.market.spy_above else "below" }} its 200-day average of {{ r.market.spy_sma_200|money }}{% endif %}

- VIX: {% if r.market.vix_close is none %}not available{% else %}{{ r.market.vix_close|num }}, {{ r.market.vix_label }}{% endif %}


{{ r.market.explanation }}

{% endif %}
## Data notes

{% if r.outcome != "rejected" %}
- Models used: {{ r.data_notes.models|join(", ") or "none" }}
- News headlines used: {{ "not available" if r.data_notes.news_headlines is none else r.data_notes.news_headlines }}
- Latest filing: {% if r.data_notes.filing_form %}{{ r.data_notes.filing_form }}, filed {{ r.data_notes.filing_date }}{% else %}not available{% endif %}

- Price source: {{ r.data_notes.price_source or "not available" }}
{% endif %}
{% if r.data_notes.warnings %}
- Warnings:
{% for w in r.data_notes.warnings %}
  - {{ w }}
{% endfor %}
{% else %}
- Warnings: none
{% endif %}

{% if r.order %}
## Actions

Approve up to {{ r.order.shares }} shares, or reject.

{% endif %}
*Research, not financial advice. Paper trading only.*
