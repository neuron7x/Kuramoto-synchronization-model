# Integration Map

Flow:

raw request -> public API -> router -> registry -> module boundary -> response envelope

Full pipeline:

intent -> reflection -> introspection -> reverse_inference -> extrapolation -> artifact_builder -> safety

Rules:

- noisy input starts with intent
- why questions route to introspection
- strategy questions route to reverse_inference
- consequence questions route to extrapolation
- usable output requests route to artifact_builder
- people-impacting outputs route to safety
