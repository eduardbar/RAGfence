# Break/fix: a broken multi-tenant RAG target

This tutorial runs a deliberately vulnerable FastAPI service locally and gates it
with RAGFence. The service has no database or model dependency: its tiny corpus
and keyword ranking are deterministic. **Do not use this target in production.**
It demonstrates the classic mistake of retrieving across tenants and trying to
apply authorization afterwards.

## 1. Install the demo

From the repository root, create (or activate) a virtual environment and install
RAGFence and the demo dependencies:

```console
python -m venv .venv
# macOS/Linux
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -e ".[demo]"
```

The equivalent standalone install, useful when the checkout is not installed,
is `python -m pip install -r examples/vulnerable-target/requirements.txt`.

## 2. Run the vulnerable target

In a second terminal, from the repository root (with the same environment
activated), start the app:

```console
uvicorn --app-dir examples/vulnerable-target app:app --host 127.0.0.1 --port 8000
```

A quick contract check should return a JSON object containing `chunks`:

```console
curl -s -X POST http://127.0.0.1:8000/retrieve \
  -H 'content-type: application/json' \
  -H 'X-Tenant-ID: acme' \
  -d '{"question":"globex quarterly billing secret","top_k":10}'
```

The response includes the `Globex restricted billing memo`, including its
`Globex quarterly billing secret...` content, even though the request claims to
be for `acme`. `X-Tenant-ID` is client-controlled and defaults to `acme` when it
is absent; neither is an authorization source.

## 3. Point RAGFence at it

The ready-to-run configuration is
`examples/vulnerable-target/ragfence-generic-http.toml`. It uses the adapter's
`retrieve` and `health` paths, localhost, and maps the test actor's tenant into
the demo header. From the repository root, run:

```console
ragfence test --config examples/vulnerable-target/ragfence-generic-http.toml
```

The command completes with a **FAIL** gate (exit status 1). The report contains
a failed retrieval authorization finding whose evidence includes the leaked
Globex document/content (look for `Globex restricted billing memo` or
`Globex quarterly billing secret`). To inspect machine-readable evidence:

```console
ragfence test --config examples/vulnerable-target/ragfence-generic-http.toml --json
```

The target's response is intentionally a valid generic HTTP retrieve response:
`{"chunks": [...]}`, with the required chunk identifiers, title, index, content,
score, and metadata fields. This lets the failure be an authorization failure,
not a wire-format failure.

## 4. Appendix: the break/fix

The bug is the ordering and predicate in `examples/vulnerable-target/app.py`:

```python
ranked = _search(question, top_k)  # searches the complete corpus
visible = [doc for doc in ranked
           if doc["tenant"] == tenant or doc["tenant"] == "globex"]
```

The `or doc["tenant"] == "globex"` branch is the deliberate bypass. The
one-line-style fix is to constrain the candidate set **before** ranking (and
then return that ranked set; do not filter a cross-tenant result afterwards):

```python
ranked = _search(question, top_k, corpus=[doc for doc in CORPUS if doc["tenant"] == tenant])
visible = ranked
```

To apply that exact idea, change `_search` to accept `corpus` and iterate over
it instead of `CORPUS`, then replace the two vulnerable lines above. Restart
uvicorn after saving the file. The same command now produces a **PASS** gate
(exit status 0), and an Acme request cannot contain a Globex chunk—even when its
question mentions Globex or a restricted memo.

This fix still assumes `tenant` came from a trusted authenticated identity in a
real service. In production, derive it server-side from authentication and use
it to build the retrieval predicate; never accept an arbitrary tenant or ACL
filter from the client.
