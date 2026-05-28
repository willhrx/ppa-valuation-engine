# PPA Valuation Tool - Development Rules

## Tech Stack
- Backend: Python (FastAPI for the API layer)
- Frontend: TypeScript + React (using Vite and shadcn/ui for high-density data styling)

## Architecture Guidelines
- Keep quantitative modeling and SDE simulations strictly in the backend.
- The backend must expose endpoints using Pydantic schemas.
- Do not modify or delete the core quantitative math scripts in `src/` without explicit permission.
- The frontend should fetch data asynchronously and render dense tables using TanStack Table.
- All frontend design scripts  should be contained to `frontend/` 

## Commands
- Backend Dev: `uvicorn main:app --reload`
- Frontend Dev: `npm run dev`