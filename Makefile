.PHONY: test validate render preview

test:
	uv run pytest -q

validate:
	uv run profilegen validate

render:
	uv run profilegen render

preview:
	uv run profilegen render --offline --output /tmp/profile-preview.md
	@echo "Preview written to /tmp/profile-preview.md"
