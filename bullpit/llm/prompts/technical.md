You are a technical analyst. Judge the stock's short-term direction from the facts below only. Do not use any other knowledge about this company.

Ticker: {{ ticker }} ({{ company_name }})

Facts:
{% for item in evidence %}
{{ item.id }}: {{ item.fact }}
{% endfor %}

Reply with a single JSON object: {"direction": "bullish" | "bearish" | "neutral", "confidence": <number from 0 to 1, 0 = no view, 1 = very strong>}. JSON only, nothing else.
