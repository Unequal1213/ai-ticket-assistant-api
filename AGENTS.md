# AGENTS.md

## Project context

This is a portfolio backend project for a self-taught Junior Python Backend Developer / AI Automation Engineer.

Project name:
AI Ticket Assistant API

Main goal:
Build a production-style FastAPI backend that accepts support tickets and analyzes them with an AI-like service.

The project should demonstrate:
- backend API design
- database modeling
- clean project structure
- AI automation workflow
- testing
- Docker
- GitHub Actions CI

## Tech stack

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

## Development rules

- Do not rewrite the entire project unless explicitly requested.
- Make small, focused changes.
- Explain every changed file.
- Preserve a clean FastAPI project structure.
- Use type hints.
- Follow PEP8.
- Avoid quick hacks.
- Do not commit secrets.
- Do not hardcode API keys, passwords, tokens, or database URLs.
- Use environment variables for configuration.
- Keep business logic separate from API routes.
- Keep AI integration behind a service interface so it can be tested without real API calls.
- Prefer maintainable code over clever code.

## Initial MVP

Build a backend API for support tickets.

Core resources:
- Ticket

Ticket fields:
- id
- title
- description
- status
- category
- priority
- summary
- suggested_reply
- created_at
- updated_at

Initial endpoints:
- GET /health
- POST /tickets
- GET /tickets
- GET /tickets/{ticket_id}
- POST /tickets/{ticket_id}/analyze

AI analysis should initially be implemented as a deterministic local service or mock service.
Do not require a real OpenAI API key in the first version.

## Review guidelines

- Check for security issues.
- Check for hardcoded secrets.
- Check database session handling.
- Check API validation.
- Check test coverage.
- Check whether the code is understandable for a Junior Developer.
