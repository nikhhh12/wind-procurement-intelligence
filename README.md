# Wind Procurement Intelligence

A web application for exploring wind generation forecast performance against actual generation across selected delivery periods and forecast cutoffs.

## Live Application

- **Frontend:** https://wind-procurement-intelligence-gilt.vercel.app/
- **Backend health endpoint:** https://wind-procurement-api.onrender.com/api/health

## Features

- Compare actual wind generation with forecast data.
- Explore delivery months and forecast cutoffs.
- Evaluate forecast performance using MAE, RMSE, bias, and WAPE.
- Inspect settlement intervals and export analysis data where supported.
- Handle UK daylight-saving-time transitions in interval processing.

## Technology Stack

- **Frontend:** React, Vite, TypeScript (confirm against the current source)
- **Backend:** Python, FastAPI
- **Hosting:** Vercel for the frontend; Render for the backend
- **Data source:** Elexon generation and forecast data

## Repository Structure

The repository contains separate frontend and backend applications.

- `frontend/` — user interface, frontend dependencies, and Vercel routing configuration.
- `backend/` — API application, data processing, and backend dependencies.
- `frontend/vercel.json` — rewrites API requests to the deployed backend.
- `README.md` — setup, architecture, and usage documentation.

See the source tree for the complete file-by-file structure.

## Running Locally

### Backend

Create and activate a Python virtual environment, install the backend dependencies, and start the FastAPI application using the actual module and entry point configured in the repository.

### Frontend

Install the frontend dependencies and start the Vite development server using the scripts defined in `frontend/package.json`.

### Configuration

Configure any required environment variables according to the application's settings. Never commit credentials or secret values.

For local development, ensure API requests are routed to the local backend rather than unintentionally relying on the production service.

## Analysis Methodology

The application compares actual generation with forecast values aligned to the relevant delivery intervals. It reports complementary error metrics:

- **MAE:** mean absolute error.
- **RMSE:** root mean squared error.
- **Bias:** average signed forecast error, according to the implementation's sign convention.
- **WAPE:** weighted absolute percentage error, according to the implementation's denominator and zero-handling rules.

Consult the source code for the precise definitions, interval-alignment rules, and treatment of missing observations.

## Testing

Run the backend tests using the test command and working directory specified by the project configuration. Verify the test results before making claims about coverage or passing test counts.

## Deployment

The frontend is deployed on Vercel and the API is deployed on Render. The frontend's Vercel rewrite configuration forwards `/api` requests to the backend.

## Limitations

Results depend on the availability and quality of source data, correct forecast-vintage selection, and interval alignment. Validate the analysis against operational requirements before using it for live procurement decisions.
