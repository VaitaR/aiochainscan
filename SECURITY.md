# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |
| < 1.0 | No |

Fixes ship in the next patch release of the 1.x line.

## Reporting a vulnerability

Report privately through GitHub's
[private vulnerability reporting](https://github.com/VaitaR/aiochainscan/security/advisories/new),
or by email to andrey.shivalin@gmail.com. Please do not open a public issue for
a vulnerability.

Include the version, the affected code path, and a reproduction — a script or
the request/response pair is enough. Expect an acknowledgement within a week.

## Scope

This is an HTTP client for third-party blockchain explorers. What is in scope:

- Credential handling: API keys read from the environment or `.env` files must
  never appear in logs, exception messages, or repr output. Redaction lives in
  `aiochainscan/_redaction.py`; a leak there is a vulnerability.
- Input handling of untrusted API responses: ABI decoding (`decode.py`,
  `abi_pure.py`, the Rust `fastabi` extension), envelope parsing (`network.py`),
  and base-URL validation (`base_url.py`). A crash, an unbounded allocation, or
  a hang on hostile response data is in scope.
- Custom base URLs: `base_url.py` rejects credentials in URLs, query strings,
  `..` segments, and plain HTTP unless `allow_http=True` is passed explicitly. A
  way around those checks is in scope.

What is not in scope: the availability, correctness, or access control of the
explorers themselves; rate limits and bot protection on public instances; and
the security of API keys you paste into your own shell history.
