# Short Links: `shortlinks`

A [ChaCC API](https://pypi.org/project/chacc-api/) module that turns long URLs into short links, like bit.ly.

```text
https://example.com/products/summer-sale?campaign=newsletter&utm_source=email
                                  ↓
            http://your-server/api/shortlinks/summer-sale
```

Anyone who opens the short link is redirected (`307`) to the long URL. Each visit is counted, and other modules can be notified about it.

- **Works on its own.** No other modules or Python packages are needed.
- **Can be extended.** [`linkstats`](https://github.com/<owner>/linkstats) builds on it to add click analytics.

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [API reference](#api-reference)
- [Database](#database)
- [Services for other modules](#services-for-other-modules)
- [Module lifecycle](#module-lifecycle)
- [Development](#development)
- [Notes and limitations](#notes-and-limitations)

---

## Requirements

| | |
|---|---|
| ChaCC API | `>= 1.0.0` (tested with `1.0.0b6`) |
| Database | SQLite (default) or PostgreSQL, using the server's configured connection |
| Python packages | none beyond ChaCC itself |
| Other modules | none |

---

## Installation

A new module is loaded when the server starts, so **every install ends with a server restart**.

### Option A: from GitHub with the CLI (recommended)

Run this from your ChaCC project folder:

```bash
chacc install <owner>/shortlinks@v0.1.0
```

This clones the repo at that tag, packages it as `shortlinks.chacc`, and places it in `.modules_installed/`. Restart the server afterwards.

For a private repo, export a token first: `export GITHUB_TOKEN=...` (or `CHACC_GIT_TOKEN`). Use `--token-env MY_VAR` to read it from a different variable.

### Option B: through the API, on a running server

Build the package from a **fresh clone**. `chacc build` packs everything in the folder, so a working copy would also include `.git` and caches.

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/<owner>/shortlinks.git
chacc build shortlinks                      # → shortlinks.chacc
```

Then upload it and restart:

```bash
BASE=http://localhost:8085/api

curl -F file=@shortlinks.chacc $BASE/modules/
# {"message":"Module 'shortlinks' installed/updated successfully. Restart the server ..."}

curl -X POST $BASE/system/restart
# {"message":"Restart scheduled. The server will be back shortly.", ...}
```

`chacc deploy shortlinks.chacc --restart` does the upload and restart in one step and handles login when the server needs it.

### Option C: for development

```bash
chacc install <owner>/shortlinks --dev
```

This copies the repo into `plugins/shortlinks`, keeping `.git` so you can edit and push from there. Then start the dev server with `chacc run server --dev`.

### Check that it's loaded

```bash
curl $BASE/modules/shortlinks       # "is_enabled": true, "load_failure": null
```

---

## Quick start

```bash
BASE=http://localhost:8085/api

# 1. Shorten a URL with a code you choose
curl -X POST $BASE/shortlinks \
     -H 'content-type: application/json' \
     -d '{"url": "https://github.com", "code": "github"}'
```
```json
{
  "code": "github",
  "short_url": "http://localhost:8085/api/shortlinks/github",
  "target_url": "https://github.com/",
  "hits": 0,
  "created_at": "2026-11-20T07:07:56.260394"
}
```

```bash
# 2. Follow it
curl -i $BASE/shortlinks/github
# HTTP/1.1 307 Temporary Redirect
# location: https://github.com/

# 3. Or let it pick a random code
curl -X POST $BASE/shortlinks -H 'content-type: application/json' \
     -d '{"url": "https://example.com/a/very/long/path?with=params"}'
# → "code": "POHEtX"
```

Open the `short_url` in a browser and you land on the target page.

---

## API reference

All routes are mounted under **`/api/shortlinks`**. They are also listed in the server's interactive docs at `/docs`.

### `POST /api/shortlinks`: create a short link

| Body field | Type | Required | Rules |
|---|---|---|---|
| `url` | string | yes | an absolute `http` or `https` URL |
| `code` | string | no | 3–32 characters: `A–Z a–z 0–9 - _`. If left out, a random 6-character code is generated. |

| Status | When |
|---|---|
| `201` | Created. Returns the link (see the [response shape](#link-response)). |
| `409` | The `code` is already taken, including by a deleted link. |
| `422` | The URL or code is invalid. |
| `429` | More than 30 creates per minute from the same client. |

### `GET /api/shortlinks`: list links

Returns every active link, newest first, as an array of [link responses](#link-response).

### `GET /api/shortlinks/{code}`: follow a link

| Status | When |
|---|---|
| `307` | Redirect. The `Location` header holds the target URL. The visit is counted and listeners are notified. |
| `404` | The code doesn't exist or was deleted. |

### `GET /api/shortlinks/{code}/info`: link details

Returns the [link response](#link-response) without redirecting or counting a visit. `404` if the code is unknown.

### `DELETE /api/shortlinks/{code}`: retire a link

Returns `204` and stops the link from redirecting. This is a soft delete: the row and its stats are kept, and **the code stays reserved**, so an old printed or shared link never starts pointing somewhere new.

### `GET /api/shortlinks/_listeners`: who is listening (hidden from `/docs`)

```json
{"listeners": ["linkstats"]}
```

This is handy for showing that another module has plugged in.

### Link response

| Field | Type | Description |
|---|---|---|
| `code` | string | the short code |
| `short_url` | string | the full short URL to share |
| `target_url` | string | where it redirects (normalized, e.g. a trailing `/` is added) |
| `hits` | integer | number of redirects so far |
| `created_at` | datetime | creation time, in UTC |

---

## Database

One table, created automatically at startup by ChaCC's migrations (`MIGRATION_MODE=auto`).

**`shortlinks_links`**

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `code` | varchar(32) | unique, indexed |
| `target_url` | varchar(2048) | |
| `hits` | integer | default `0`, incremented on every redirect |
| `uuid`, `created_at`, `updated_at`, `deleted_at` | | inherited from `ChaCCBaseModel`. `deleted_at` is set by `DELETE`. |

Uninstalling the module **does not drop the table**. Reinstall it and every link is back.

---

## Services for other modules

`shortlinks` registers these services on the ChaCC backbone, so other modules can build on it **without importing its code**:

| Service name | Signature | Description |
|---|---|---|
| `shortlinks.get_by_code` | `async (code: str) -> LinkInfo \| None` | Look up an active link. `LinkInfo` has `id`, `code`, `target_url`, `hits`, `created_at`. |
| `shortlinks.add_visit_listener` | `(name: str, fn) -> None` | `fn(event)` is called after every redirect. It can be sync or async. Registering the same `name` again replaces the old listener, so reloads never double-count. |
| `shortlinks.remove_visit_listener` | `(name: str) -> None` | Stop listening. |

The **visit event** passed to listeners has these fields:

| Field | Type |
|---|---|
| `link_id` | int |
| `code` | str |
| `target_url` | str |
| `user_agent` | str \| None |
| `referer` | str \| None |
| `client_ip` | str \| None |
| `visited_at` | datetime (UTC) |

Listeners run **after the redirect response has been sent**, so they never slow it down. A listener that raises an error is logged and skipped, and the redirect and the other listeners are not affected.

### Using it from your own module

```json
// module_meta.json
"module_dependencies": { "required": ["shortlinks"], "optional": [] }
```

```python
# main.py
def setup_plugin(context):
    add_listener = context.get_service("shortlinks.add_visit_listener")

    async def on_visit(event):
        context.logger.info(f"{event.code} was visited from {event.referer or 'direct'}")

    add_listener("my_module", on_visit)
    return router
```

ChaCC starts modules in dependency order, so `shortlinks` has registered its services before your `setup_plugin` runs.

---

## Module lifecycle

These were checked against a ChaCC `1.0.0b6` server in production mode:

| Action | Result |
|---|---|
| Install | `200`. Routes become available after a restart. |
| Disable or uninstall while `linkstats` is installed | Allowed, with the warning *"Module(s) linkstats require 'shortlinks' and will not be loaded after the restart…"* |
| Uninstall, then install again | All links (and `linkstats` clicks) are still there. |

Manage the module with these endpoints:

```bash
curl -X POST   $BASE/modules/shortlinks/disable
curl -X POST   $BASE/modules/shortlinks/enable
curl -X DELETE $BASE/modules/shortlinks/uninstall
curl -X POST   $BASE/system/restart        # needed after each of the above
```

---

## Development

```text
shortlinks/
├── module_meta.json          # name, version, entry point, dependencies
├── requirements.txt          # no extra packages
└── shortlinks_src/
    ├── main.py               # setup_plugin(): registers services, returns the router
    ├── models.py             # Link table and request/response schemas
    ├── routes.py             # the HTTP endpoints
    ├── service.py            # code generation, lookups, visit listeners
    └── tests/test_module.py
```

Run the tests from the module folder, using the ChaCC project's virtualenv:

```bash
pytest shortlinks_src/tests -v
```

The tests cover code generation, input validation, and listener isolation and replacement.

---

## Notes and limitations

- **Timestamps are UTC.** They are stored without a time zone marker.
- **Hit counting is simple.** Every redirect counts, including bots and repeat visitors. Install `linkstats` for unique visitors and a breakdown.
- **The short URL uses the address the request came in on.** It is built from the incoming request's host, so behind a reverse proxy, make sure the proxy forwards the original `Host` header.
- **Codes are case-sensitive.** `GitHub` and `github` are different links.

## License

MIT
