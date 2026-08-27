# ADR — Rescue qualification is separate from v1 engineering acceptance

`rescue_use_validated` remains `false` for dev-20 and ordinary lab campaigns. Enabling it requires a separately approved qualification protocol covering representative environments, hazards, ethical/consent controls where applicable, independent ground truth, false-negative risk, operational procedures, trained operators, and explicit acceptance authority. A normal `final_go=true` never flips this flag.
