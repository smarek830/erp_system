The repository is a small Django monolith focused on production orders and an operator interface.

- Architecture: Django project `config/` (settings, wsgi, urls) + single app `core/` (models, views, templates).
- DB: SQLite at `db.sqlite3`; media files saved to `media/` via `MEDIA_ROOT` in `config/settings.py`.

- Key places to edit:
  - Backend views / URL patterns: `core/views.py` and `core/urls.py` (operator AJAX endpoints live here).
  - Templates: `core/templates/core/` (operator UI in `operator/zakazka_detail.html` shows client-side patterns).
  - Models & migrations: `core/models.py` and `core/migrations/` (data model is centralized here).
  - Domain layer: `core/domain.py` (business logic aliases like `Job`, `StockMovement` for cleaner code).

- Important runtime commands (project-specific):
  - Run dev server: `python manage.py runserver`
  - Apply DB migrations: `python manage.py migrate`
  - Create superuser: `python manage.py createsuperuser`
  - Run tests: `python manage.py test`

- HTTP & AJAX patterns to follow (examples from `core/urls.py`):
  - `POST /api/operator/start/<obj_pk>/<oper_pk>/` — start operation
  - `POST /api/operator/pause/<obj_pk>/<oper_pk>/` — pause operation
  - `POST /api/operator/end-operation/<obj_pk>/<oper_pk>/` — end single operation
  - `POST /api/operator/end/<pk>/` — finish work + file upload (multipart/form-data)
  - `POST /api/operator/report/<pk>/` — report problem

- CSRF and client JS conventions:
  - Templates use a JS `getCookie('csrftoken')` helper and send `X-CSRFToken` header on `fetch()` calls.
  - File uploads use `FormData()` (see `end` endpoint in `operator/zakazka_detail.html`). Keep `Content-Type` omitted so browser sets multipart boundary.

- Project conventions and gotchas to preserve:
  - The app mixes Slovak UI text and emoji in templates — preserve existing language/UX tone when editing UI.
  - Templates rely on Bootstrap modals and client-side `fetch()` handlers (modify both template HTML and corresponding view behavior together).
  - `MEDIA_ROOT` is used for uploaded photos and product drawings; avoid hardcoding paths.
  - Settings show `DEBUG = True` and `ALLOWED_HOSTS = ['*']` — be cautious when preparing production changes.

- Integration points & external resources:
  - No `requirements.txt` detected in repo root; Django version is noted in `settings.py` header (Django 5.2.10). Confirm virtualenv and dependencies with the developer.
  - Large reference files live under `Database/` and `media/` — these are content, not Django models.

- Editing guidance for an AI agent:
  - For UI changes, update both `core/templates/core/operator/zakazka_detail.html` and ensure view-side API responses remain JSON `{status,message,...}` as the JS expects.
  - Maintain URL names from `core/urls.py` when refactoring; other templates use `url 'operator_dashboard'` etc.
  - When adding new POST endpoints consumed by `fetch()`, return `JsonResponse({'status':'ok', 'message': '...'})` or `{'status':'error','message': '...'}`.
  - Use `MEDIA_ROOT` and `request.FILES` handling for uploaded images; follow patterns in existing views where present.

- Quick file references (examples):
  - Routing & AJAX endpoints: `core/urls.py`
  - Operator template example: core/templates/core/operator/zakazka_detail.html
  - Settings & media config: config/settings.py
  - App entrypoint + models: core/models.py, core/views.py

If anything above is unclear or you want the agent to follow stricter guardrails (test-run changes, create requirements file, or set up a venv), tell me which task to perform next.
