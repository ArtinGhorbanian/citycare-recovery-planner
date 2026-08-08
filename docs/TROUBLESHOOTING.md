# Troubleshooting

## Startup reports the service could not initialize

1. Confirm `.env` exists and `DATASET_PATH` points to a readable CSV.
2. Generate the safe demo file with `python scripts/generate_citycare_demo_data.py`.
3. Confirm the CSV has the exact schema produced by the generator.
4. Check the local server console; detailed startup errors are intentionally not sent to the browser.

## The generator refuses to write

It does not overwrite by default. Keep the existing file, choose a different `--output`, or intentionally pass `--overwrite`.

## The browser remains on “Starting”

- Wait for model training to finish; the app trains at process startup.
- Reload after the server reports `Model ready: True`.
- Check `/api/status`; a `503` means the data/model pipeline is unavailable.
- Confirm same-origin static files are not blocked by an extension or proxy.

## Charts are unavailable

Chart.js is served locally from `static/vendor/chart.umd.js`. The accessible tables remain usable when the visual chart cannot load. Confirm that the vendor file exists and that the response Content Security Policy contains `script-src 'self'`.

## Results say “Needs update”

This is intentional. Changing a hospital, scenario field, reserve, or objective weight invalidates results derived from the older state. Rerun the corresponding workflow before downloading or acting on it.

## AI says it is unavailable

Fixed-rule mode is the safe default. If AI is intentionally enabled, verify the base URL uses HTTPS (unless loopback), its exact hostname appears in `AI_ALLOWED_HOSTS`, the key is set outside version control, and numeric settings are within the documented bounds.

Do not expose an AI-enabled instance publicly without authentication, rate limits, cost controls, monitoring, and an appropriate provider/data agreement.

## Port already in use

Choose another local port in `.env`, for example `PORT=5057`, or stop only the process you know owns port 5000. Do not terminate unrelated services.
