# Installation

## Supported local setup

- Python 3.11 or newer; release validation used Python 3.14.6.
- A modern browser with JavaScript enabled.
- Node.js is optional and used only for the JavaScript syntax check.
- The default server binds to `127.0.0.1:5000`.

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python scripts\generate_citycare_demo_data.py
Copy-Item .env.example .env
python app.py
```

## macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python scripts/generate_citycare_demo_data.py
cp .env.example .env
python app.py
```

The generator refuses to overwrite an existing destination unless `--overwrite` is given. Open <http://127.0.0.1:5000> after startup reports `Model ready: True`.

## Development environment

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app.py scripts tests
python -m bandit -q -r app.py scripts
python -m pip check
node --check static\script.js
```

`requirements.lock` pins the complete runtime closure. `requirements-dev.txt` pins the review tools and references the direct runtime requirements.

## Configuration

| Variable | Safe default | Meaning |
| --- | --- | --- |
| `DATASET_PATH` | `data/citycare_demo_dataset.csv` | CSV resolved from the repository root when relative |
| `HOST` | `127.0.0.1` | Flask bind address |
| `PORT` | `5000` | Flask port |
| `DEBUG` | `false` | Debug mode; automatically disabled for non-loopback binds |
| `AI_ENABLED` | `false` | Enables optional external wording only |
| `AI_BASE_URL` | OpenAI-compatible HTTPS URL | Provider API root |
| `AI_ALLOWED_HOSTS` | `api.openai.com` | Exact comma-separated public egress allowlist |
| `AI_MODEL` | `gpt-4o-mini` | Provider model identifier |
| `AI_API_KEY` | empty/local only | Provider bearer credential; never commit it |
| `AI_TIMEOUT_SECONDS` | `30` | Bounded outbound timeout |
| `AI_MAX_TOKENS` | `700` | Bounded output token request |
| `AI_TEMPERATURE` | `0.2` | Bounded provider temperature |

Operating-system environment variables override `.env` values. Do not put patient data, secrets, or unauthorized datasets into this prototype.
