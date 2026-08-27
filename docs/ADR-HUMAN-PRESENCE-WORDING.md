# ADR — Human-presence wording and safety semantics

Allowed detector states are `HUMAN_EVIDENCE`, `NO_HUMAN_EVIDENCE`, and `INDETERMINATE`.

`NO_HUMAN_EVIDENCE` means only that the measured RF window is compatible with calibrated background in the validated regime; it is never proof that nobody is present. A location is never emitted without uncertainty. Unresolved multiple targets become `POSSIBLE_CLUSTER`. No RF result implies death, survivability, or rescue qualification.
