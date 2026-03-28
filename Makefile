# M-Cog Makefile
# Build and development commands

.PHONY: all clean compile install test run bootstrap help

# Default target
all: compile install

# Compile C modules
compile:
	@echo "Compiling C modules..."
	cd core && gcc -shared -fPIC -o safety_hardcode.so safety_hardcode.c
	cd core && gcc -shared -fPIC -o resource_scheduler.so resource_scheduler.c -lpthread
	@echo "C modules compiled successfully"

# Install Python dependencies
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Dependencies installed"

# Run bootstrap initialization
bootstrap:
	@echo "Running bootstrap initialization..."
	python core/bootstrapper.py

# Run tests
test:
	@echo "Running tests..."
	python -m pytest tests/ -v --cov=core --cov-report=term-missing

# Run linting
lint:
	@echo "Running linters..."
	flake8 core/ --max-line-length=120
	black --check core/
	mypy core/ --ignore-missing-imports

# Format code
format:
	@echo "Formatting code..."
	black core/

# Run the system
run:
	@echo "Starting M-Cog system..."
	python main.py --interactive

# Run with WebUI
run-web:
	@echo "Starting M-Cog with WebUI..."
	python main.py --webui

# Create backup
backup:
	@echo "Creating backup..."
	python scripts/backup.py

# Clean build artifacts
clean:
	@echo "Cleaning..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -f core/*.so
	rm -f runtime/*.so
	@echo "Clean complete"

# Show help
help:
	@echo "M-Cog Makefile Commands:"
	@echo "  make compile    - Compile C modules"
	@echo "  make install    - Install Python dependencies"
	@echo "  make bootstrap  - Initialize system with seed data"
	@echo "  make test       - Run test suite"
	@echo "  make lint       - Run code linters"
	@echo "  make format     - Format code with black"
	@echo "  make run        - Start interactive mode"
	@echo "  make run-web    - Start with WebUI"
	@echo "  make backup     - Create system backup"
	@echo "  make clean      - Remove build artifacts"
	@echo "  make help       - Show this help message"
