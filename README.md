# ai-ticket-assistant-api

## API

- `GET /health` - returns the service health status.
- `POST /tickets` - creates a ticket from a title and description.
- `GET /tickets` - returns tickets with pagination, filtering, and sorting.
- `GET /tickets/{ticket_id}` - returns one ticket by ID or `404` if it does not exist.
- `PATCH /tickets/{ticket_id}` - partially updates one ticket by ID.
- `DELETE /tickets/{ticket_id}` - deletes one ticket by ID.
- `POST /tickets/{ticket_id}/analyze` - applies deterministic local analysis to a ticket.

## Docker

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Start the API and PostgreSQL:

   ```bash
   docker compose up --build
   ```

The app runs on `http://localhost:8000`. Docker Compose waits for PostgreSQL to
be healthy, runs `alembic upgrade head`, and then starts Uvicorn.
