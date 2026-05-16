.PHONY: install dev seed test loop ui ui-build start stop lint clean

install:
	pip install -r requirements.txt

dev:
	python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

ui-build:
	cd ui/frontend && npm run build

ui: ui-build
	python3 -m uvicorn ui.server:app --host 0.0.0.0 --port 8001 --reload

# Kill any uvicorn processes running on ports 8000 and 8001.
stop:
	@lsof -ti :8000 | xargs kill -9 2>/dev/null && echo "Stopped port 8000" || echo "Nothing on port 8000"
	@lsof -ti :8001 | xargs kill -9 2>/dev/null && echo "Stopped port 8001" || echo "Nothing on port 8001"

# Run API + observer UI together. Ctrl-C stops both.
start: ui-build
	@echo "→ API server   http://localhost:8000"
	@echo "→ Observer UI  http://localhost:8001"
	@python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &\
	 python3 -m uvicorn ui.server:app --host 0.0.0.0 --port 8001 --reload &\
	 wait

seed:
	python3 -m api.seed

migrate:
	python3 -m alembic upgrade head

test:
	python3 -m pytest tests/ -v --tb=short

test-cov:
	python3 -m pytest tests/ -v --cov=api --cov=refinement --cov-report=html

loop:
	python3 -m refinement.loop

setup-agent:
	python3 -m elevenlabs_client.setup

lint:
	python3 -m py_compile api/services/booking_service.py \
	                      api/services/flight_service.py \
	                      api/routes/webhooks.py \
	                      knowledge_base/kb_service.py
	@echo "Syntax OK"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f data/airline.db data/airline.db-shm data/airline.db-wal
