You are the risk manager. Review this sized order for {{ ticker }} ({{ company_name }}) before it goes to the owner for approval. You may approve it, shrink it to fewer shares, or veto it -- never enlarge it.

Signals:
{% for s in signals %}
{{ s.analyst }}: {{ s.direction }} (confidence {{ "%.2f"|format(s.confidence) }}){% if s.flagged %} [flagged]{% endif %}
{% endfor %}

Debate transcript:
{% for line in transcript %}
{{ line }}
{% endfor %}

Trader's recommendation: {{ recommendation.action }}, target weight {{ "%.1f"|format(recommendation.target_weight_pct) }}%, exit style {{ recommendation.exit_style }}, confidence {{ "%.2f"|format(recommendation.confidence) }}. Decisive evidence: {{ recommendation.decisive_evidence|join(", ") }}. Reasoning: {{ recommendation.reasoning }}

Sized order: {{ order.shares }} shares ({{ "%.1f"|format(order.pct_of_equity) }}% of equity, cost {{ order.cost }}), stop-loss {{ order.stop_loss }}, take-profit {{ order.take_profit }}, maximum loss {{ order.max_loss }}, possible gain {{ order.max_gain }}. Size set by the {{ order.limit }} limit.

Look for a serious bear point the trader ignored, or a size that doesn't match the confidence. Reply with a single JSON object: {"decision": "approve" | "shrink" | "veto", "shares": <integer, required only if "shrink">, "reason": <string>}. JSON only, nothing else.
