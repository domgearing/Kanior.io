# Fictional contract cases

`cases.json` contains positive and adversarial examples for foundation requests, transcript imports, evidence selection and the two defined event types. All IDs and content are fictional.

Each case declares `schema_valid` and `model_valid` separately. A cross-field/context-free semantic failure can pass JSON Schema but must fail the Python validator (reversed times/spans, event aggregate mismatch, non-UTC event time). Contextual failures such as unauthorized IDs still require real service/RLS tests in the implementation phase; these fixtures make no claim about access control being implemented.

Extend examples when contracts change. Never change a negative expectation simply to make a failing check pass; reconcile it with the architecture/spec and document any contract decision.
