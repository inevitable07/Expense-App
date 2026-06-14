# AI Usage Log

This document summarizes the AI tools and prompts used during the development of this project, as well as specific corrections that were required to resolve incorrect AI outputs.

---

## 1. AI Tools Used
- **Antigravity**: A powerful agentic coding assistant developed by Google DeepMind.
- **Claude / Gemini models**: Employed inside the agent shell for planning, writing code, and diagnostics.

---

## 2. Key Prompts and Directives

Key instructions and prompts guiding the development process per module:
- **Resiliency & Validation**: *"Ensure all view validations fail gracefully rather than raising 500 errors. Verify form errors are rendered correctly in context."*
- **Import Pipelines**: *"Implement a robust multi-pass anomaly detector registry. Hold all rows in an intermediate review state. Do not automatically correct data."*
- **Database Optimizations**: *"Optimize the scanning engine for remote databases by caching redundant queries in-memory on the Django model instances and utilizing bulk inserts."*

---

## 3. Key Corrections and Refinements

During pair programming, the following 3 specific instances of incorrect first-run AI outputs were identified and resolved:

### Example 1: Traceability Reference mismatch in Duplicate Row Detector
- **Problem**: The initial implementation of `DuplicateRowDetector` flagged duplicate rows but incorrectly reported the relative row indexing, causing the test `test_pipeline_saves_batch_and_anomalies` to fail with:
  ```text
  AssertionError: 'row 3' != 'row 4'
  ```
- **How it was caught**: Running the Django unit test suite:
  ```powershell
  .venv\Scripts\python manage.py test
  ```
- **The Fix**: Re-indexed the duplicate row detection dictionary structure in `imports/detectors/duplicate_expense.py` to correctly record the first occurrence's index and link subsequent duplicate rows back to the exact original line reference.

### Example 2: Missing `Settlement` Model Import in `imports/tests.py`
- **Problem**: The AI generated integration test methods in `imports/tests.py` that queried the `Settlement` table to verify imported settlements, but forgot to import the `Settlement` class at the top of the file, resulting in:
  ```text
  NameError: name 'Settlement' is not defined
  ```
- **How it was caught**: Running the newly created test suite returned a compiler `NameError` traceback.
- **The Fix**: Added the explicit import statement:
  ```python
  from settlements.models import Settlement
  ```
  to the imports block in `imports/tests.py`.

### Example 3: Standalone Profiling Script Path Resolution Error
- **Problem**: The profiling script generated in the `scratch/` directory failed to execute because the Python runtime did not include the project workspace `e:\ExpenseApp` in its search paths when run from the app data folder. This raised:
  ```text
  ModuleNotFoundError: No module named 'shared_expenses'
  ```
- **How it was caught**: Attempting to execute the profiling command:
  ```powershell
  .venv\Scripts\python C:\Users\imaas\..._scan.py
  ```
- **The Fix**: Modified the script to insert the project root path into `sys.path` dynamically before setting up Django:
  ```python
  import sys
  sys.path.insert(0, 'e:\\ExpenseApp')
  import django
  ```
