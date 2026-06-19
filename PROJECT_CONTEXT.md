# PROJECT_CONTEXT.md

## Project

AI Ticket Assistant API

## Goal

Create a portfolio-ready backend project that demonstrates Python backend development and AI automation concepts.

The application will allow users to create support tickets and request an AI-style analysis of each ticket.

The analysis should produce:
- category
- priority
- summary
- suggested reply

## Repository

GitHub repository:
https://github.com/Unequal1213/ai-ticket-assistant-api

## Target role

Junior Python Backend Developer / AI Automation Engineer

## Planned stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- Docker
- Pytest
- Ruff
- GitHub Actions

## Architecture direction

Use a clean and understandable structure:

- app/main.py
- app/api/
- app/models/
- app/schemas/
- app/services/
- app/database/

The AI analysis logic should live in app/services/ and should not be hardcoded inside API routes.

The first implementation should use a deterministic local analyzer so tests can run without external services or API keys.

A real LLM provider can be added later behind the same service interface.

## Current status

Repository has just been created.

Next step:
Create the initial FastAPI project structure with health endpoint, dependencies, requirements, Ruff, Pytest, Docker-ready structure, and basic CI-ready foundations.

## Important rules

- Do not commit .env.
- Do not hardcode secrets.
- Do not require a real AI API key in the MVP.
- Keep changes small and focused.
- Prefer clear code over clever abstractions.
