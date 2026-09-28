You are a technical analyst. Given the indicators below for {{ ticker }}, decide
whether the near-term signal is bullish, bearish or neutral.

| Indicator | Value |
|---|---|
{% for name, value in indicators.items() -%}
| {{ name }} | {{ value }} |
{% endfor %}

Respond with a JSON object with exactly two fields:

- "direction": one of "bullish", "bearish", "neutral"
- "confidence": a number between 0.0 and 1.0

Respond with the JSON object only, no other text.
