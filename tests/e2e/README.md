# End-to-end tests

This directory is reserved for user-journey tests that drive the documented API
and application shells against local, synthetic infrastructure. No end-to-end
test is added before authentication, project APIs, and a test environment exist.

Future tests must use the fixture principals and resources in
`tests/fixtures/synthetic/manifest.json`. They must authenticate through the
test-only identity override described in `docs/SECURITY.md`, never through a
production route or an untrusted request header. Every test must assert its own
authorization result; it cannot treat a UI omission as proof of isolation.
