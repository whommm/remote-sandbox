# Remote Sandbox Runner (whommm/remote-sandbox)

A cloud runner sandbox powered by GitHub Actions. Provides 4-core, 16GB RAM, high-speed network environment to execute heavy background tasks, scraping, conversions, and builds on demand.

## Triggers
Triggered via GitHub REST API `workflow_dispatch` with base64 script payload.
Outputs are automatically packaged into Artifacts.
