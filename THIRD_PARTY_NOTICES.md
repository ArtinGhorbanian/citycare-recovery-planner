# Third-party notices

## Bundled component

| Component | Version | Purpose | License | Upstream |
| --- | ---: | --- | --- | --- |
| Chart.js | 4.4.1 | Accessible visual chart enhancement | MIT | <https://www.chartjs.org/> |

The bundled file is `static/vendor/chart.umd.js`. The unmodified upstream license text is stored in `static/vendor/CHARTJS_LICENSE.md` and must remain with redistributed copies.

## Installed dependencies

Flask, NumPy, pandas, scikit-learn, and their dependency closure are not vendored. They are installed from the exact versions in `requirements.lock` and are governed by their respective upstream licenses. Development tools listed in `requirements-dev.txt` are likewise not vendored.

This notice does not grant a license to the CityCare Recovery Planner project itself. See [docs/LICENSE_DECISION.md](docs/LICENSE_DECISION.md).
