# Legacy standalone Amazon scraper

This is the older Node.js Amazon scraper retained from the Sale-Fox workspace. The unified Flask
API does not launch or depend on it; use the backend repository root for the integrated scraper
and checkout API.

To run this legacy server separately, install its dependencies in this directory and use its
`npm start` script. Its Dockerfile, tunnel settings, and deployment manifests apply only to this
standalone Node.js server, not to the unified backend.
