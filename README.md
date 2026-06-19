# ai-ticket-assistant-api

## API

- `GET /health` - returns the service health status.
- `POST /tickets` - creates a ticket from a title and description.
- `GET /tickets` - returns all tickets.
- `GET /tickets/{ticket_id}` - returns one ticket by ID or `404` if it does not exist.
