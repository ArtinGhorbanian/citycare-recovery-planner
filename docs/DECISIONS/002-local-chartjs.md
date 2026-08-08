# ADR 002: Self-host Chart.js

- Status: Accepted
- Date: 2026-08-08

## Context

The dashboard uses Chart.js for resource and weekly-history visualizations. Loading it from a public CDN at runtime would create an availability, privacy, supply-chain, and content-security-policy dependency outside the repository.

Charts are useful but must not be the only representation of result values.

## Decision

Store the Chart.js 4.4.1 UMD bundle at `static/vendor/chart.umd.js` and its license text at `static/vendor/CHARTJS_LICENSE.md`. Serve both application scripts from the Flask origin and keep the browser content security policy at `script-src 'self'` and `connect-src 'self'`.

Load Chart.js independently of the main controller so application bootstrap does not depend on chart initialization. Keep adjacent accessible tables and show a notice if the chart library is unavailable.

## Consequences

Positive consequences:

- local demonstrations do not make a runtime request to a chart CDN;
- the exact browser bundle is reviewable with the repository state;
- content security policy does not need a third-party script origin; and
- values remain available without canvas rendering.

Trade-offs and limits:

- maintainers must track and review Chart.js updates manually or through an explicit vendoring process;
- the repository carries about 200 KiB of minified third-party code;
- license notices must remain with redistributed copies; and
- self-hosting does not establish the integrity of the workstation or original package-acquisition process.

## Alternatives considered

### Public CDN with subresource integrity

This can pin bytes but still depends on external availability and adds a third-party network origin. It was not selected for the self-contained local workflow.

### Custom SVG or CSS charts

This would remove the library but increase bespoke rendering and accessibility maintenance. It was not needed because Chart.js plus data tables meets the current prototype scope.

### Tables only

Tables remain the accessible fallback, but charts materially improve quick comparison for this dashboard. Both representations are retained.
