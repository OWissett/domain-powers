# Python Layout and Boundary Contracts

## Package tree

```
pyproject.toml
src/shop/
  __init__.py
  bootstrap.py                 # composition root: builds adapters, injects into handlers
  shared_kernel/
    __init__.py
    money.py                   # Money, Currency: frozen value objects only
  ordering/
    __init__.py                # empty: don't re-export internals here
    api.py                     # public surface for other contexts
    domain/
      __init__.py
      order.py                 # Order aggregate, OrderLine entity
      values.py                # OrderId, Quantity, Sku ...
      events.py                # OrderPlaced, OrderCancelled (domain events)
      ports.py                 # OrderRepository Protocol
      errors.py                # domain exceptions / error types
    application/
      __init__.py
      place_order.py           # PlaceOrder command + handler
      unit_of_work.py          # UnitOfWork Protocol
    infrastructure/
      __init__.py
      sqlalchemy_repository.py
      acl/
        __init__.py
        legacy_erp.py
  billing/ ... same shape ...
  web/                         # framework entrypoints (FastAPI routers) — call <context>.api only
tests/
  ordering/
    unit/                      # domain + application with fakes: no I/O
    integration/               # adapters against real DB/containers
    contract/                  # api.py contract tests consumed by other contexts
  architecture/                # optional pytest-archon / import tests
```

## import-linter contracts

Put in `pyproject.toml`. Requires `import-linter >= 2.0` (module wildcards). Run with `lint-imports`.

```toml
[tool.importlinter]
root_package = "shop"
include_external_packages = true

# 1. Layers inside every context. Higher layers may import lower ones, never the reverse.
[[tool.importlinter.contracts]]
name = "context layers"
type = "layers"
containers = ["shop.ordering", "shop.billing", "shop.fulfilment"]
layers = [
    "(infrastructure)",   # parentheses = optional: a young context may lack it
    "(api)",
    "(application)",
    "domain",
]

# 2. Domain purity: no frameworks, ORMs, I/O libraries in any domain layer.
[[tool.importlinter.contracts]]
name = "domain is pure"
type = "forbidden"
source_modules = ["shop.*.domain"]
forbidden_modules = [
    "sqlalchemy", "django", "fastapi", "flask", "starlette",
    "pydantic", "requests", "httpx", "aiohttp", "boto3", "redis", "celery",
]

# 3. Contexts are independent except via each other's api module.
#    One forbidden contract per context keeps error messages readable.
[[tool.importlinter.contracts]]
name = "ordering does not reach into other contexts"
type = "forbidden"
source_modules = ["shop.ordering"]
forbidden_modules = [
    "shop.billing.domain", "shop.billing.application", "shop.billing.infrastructure",
    "shop.fulfilment.domain", "shop.fulfilment.application", "shop.fulfilment.infrastructure",
]

# 4. Framework entrypoints talk to contexts only through api.
[[tool.importlinter.contracts]]
name = "web uses public api only"
type = "forbidden"
source_modules = ["shop.web"]
forbidden_modules = ["shop.*.domain", "shop.*.application", "shop.*.infrastructure"]
```

Note on the layers contract: `infrastructure` is outermost (adapters may call the context's own `api`); `api` sits above `application` so it can call handlers and use `domain` types *internally*, but never adapters. Its **public signatures** must use DTOs. The reviewer checks that. import-linter cannot.

## Edit-guard config

The domain-powers edit hook reads this to know where contexts are:

```toml
[tool.domain-powers]
root_package = "shop"          # top-level import name
source_root = "src"            # directory containing the root package
contexts = ["ordering", "billing", "fulfilment"]
shared = ["shared_kernel"]     # importable from anywhere
public_module = "api"          # the only module other contexts may import
# Extra third-party modules banned from domain layers (merged with built-in list)
domain_forbidden = ["mylegacy_sdk"]
```

Without this table the guard still checks type escapes and any `*/domain/*.py` file for framework imports.
