# Sale-Fox Frontend

Sale-Fox is the React/Vite storefront.

## Requirements

- Node.js
- npm

## Install

From this repository's root directory, install the frontend dependencies:

```bash
npm ci
```

## Run locally

Start the development server:

```bash
npm run dev
```

Open **http://localhost:5173** in your browser. Keep the terminal running while you use the
frontend; press Ctrl+C to stop the server.

The frontend sends `/api` requests to `http://127.0.0.1:5050` through the Vite proxy configured in
`vite.config.js`. API-backed features require the separate API service to be available; this
frontend repository does not install or start it.

## Production build

Create a production build with:

```bash
npm run build
```

The generated files are written to `dist/`.

Checkout flows can submit real orders. Do not start a checkout unless you intend to place an order.
