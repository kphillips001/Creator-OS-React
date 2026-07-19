# Creator_OS React Frontend

This directory contains the independent React foundation for the future
Creator_OS interface. It currently provides the desktop application shell and
placeholder routes only; no production feature or backend integration has been
migrated.

## Setup

Requires Node.js 20 or newer.

1. Copy `.env.example` to `.env` if local environment overrides are needed.
2. Install dependencies with `npm install`.

## Development

Run `npm run dev`, then open the local URL printed by Vite.

## Production build

Run `npm run build`. The static output is written to `dist/`.

## Validation

- `npm run lint`
- `npm run typecheck`
- `npm run build`

## Migration status

Iteration 2 establishes the React, TypeScript, Vite, routing, styling, and
application-shell foundation. Every product route is intentionally a migration
placeholder.

This frontend is independent from the production Streamlit application. It
does not import, replace, or modify Streamlit pages, Python services,
repositories, providers, or database code.
