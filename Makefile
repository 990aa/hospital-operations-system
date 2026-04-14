mutation-test:
	mutmut run --paths-to-mutate backend/,models/ --runner "pytest tests/test_auth.py tests/test_validation.py"
	mutmut results
