# ADR — dev-19 acquisition baseline is immutable

Status: Accepted for dev-20+

Every later milestone must pass the retained dev-19 acquisition evidence gate. Human sensing runs downstream of acquisition health and cannot convert peer-expiry, timing, or environment failure into a sensing PASS. The accepted baseline is the union of tag commit `7d70bd3...` and evidence commit `46995694...`, unified by merge commit `95a29808...`.

Screenshots are never required. Replay/synthetic fixtures are never physical proof.
