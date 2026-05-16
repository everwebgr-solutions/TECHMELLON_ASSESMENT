.PHONY: install dev seed test loop ui lint clean

install:
	pip install -r requirements.txt

dev:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	uvicorn ui.server:app --host 0.0.0.0 --port 8001 --reload

seed:
	python -m api.seed

migrate:
	alembic upgrade head

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --cov=api --cov=refinement --cov-report=html

loop:
	python -m refinement.loop

setup-agent:
	python -m elevenlabs_client.setup

lint:
	python -m py_compile api/services/booking_service.py \
	                     api/services/flight_service.py \
	                     api/routes/webhooks.py \
	                     knowledge_base/kb_service.py
	@echo "Syntax OK"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f data/airline.db data/airline.db-shm data/airline.db-wal
