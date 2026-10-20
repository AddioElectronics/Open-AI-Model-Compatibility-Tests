# OpenAI Model Compatibility Tester `V0.1.1`

A Python CLI tool for testing API model compatibility, recording results, and querying previous test runs.

With Open AI not providing documentation on legacy model capabilities or execution restrictions, this tool was created to programmatically map and verify model constraints. Because behaviors like tool-calling schemas and reasoning limits shift from model to model and even minor versions, this tester builds a reliable baseline directly from the API.

## Requirements

* Python 3.10+
* An OpenAI API key
* The `openai` Python package

Install the dependency:

```bash
pip install openai
```

### Api Key
3 ways to set the API Key:
- Create `api_key.txt` with the key in plain text on the first line
- Pass the key using the `--apikey` argument (Overrides `api_key.txt`)
- Pass the key when prompted while in `--wizard` mode

### Imports

The test runner uses these Python modules:

* **Standard library:** `csv`, `json`, `os`, `re`, `sys`, `time`, `argparse`, `atexit`, `datetime`, `fnmatch`
* **External package:** `openai`

The results viewer uses:

* **Standard library:** `os`, `argparse`, `json`, `csv`, `textwrap`, `fnmatch`

---

## 1. Running Model Tests

```bash
python run_tests.py
```

### Arguments

| Argument                   | Value       | Description                                                                                      |
| -------------------------- | ----------- | ------------------------------------------------------------------------------------------------ |
| `-a`, `--apikey`           |             | Your OpenAI API key, or leave blank to use `api_key.txt`.                                        |
| `-i`, `--include`          | MODEL [...] | Explicitly include model names. (Supports * Wildcard)                                            |
| `-ex`, `--exclude`         | MODEL [...] | Explicitly exclude model names. (Supports * Wildcard)                                            |
| `-r`, `--regex`            | REGEX       | Include API-listed models matching a regex.                                                      |
| `-rx`, `--regexclude`      | REGEX       | Exclude models matching a regex.                                                                 |
| `-t`, `--tests`            | TEST [...]  | Select specific tests. Defaults to all tests.                                                    |
| `-w`, `--wizard`           |             | Interactively select models, tests, and keys.                                                    |
| `-f`, `--force`            |             | Skip the confirmation prompt.                                                                    |
| `-l`, `--log`              |             | Log standard output to a file.                                                                   |
| `-d`, `--delay`            | MS          | Delay between requests in milliseconds. If non 0, service tier is limited to `default` and `flex`. Max: 1,000 ms, Default: 250|
| `-s`, `--service-tier`     | TIER        | Choose a service tier: `default`, `auto`, `*flex`, `fast`, or `ultrafast`. If `--delay` is greater than 0, `fast` and `ultrafast` fall back to `default`.|
| `--max-retries`            | COUNT       | Max number of test retries using the `flex` tier before falling back to `default` or skipping. Default: 0|
| `--max-timeouts`           | COUNT       | Max number of consecutive `flex` tier timeouts before falling back to `default` or stopping execution. Default: 10|
| `--no-fallback`            |             | Disable fallback to `default` service tier if `flex` fails.                          |

### Examples

```bash
# Test default models
python run_tests.py

# Include models matching a regex
python run_tests.py -r "gpt-6-.*"

# Exclude models matching a regex
python run_tests.py -rx ".*preview.*"

# Test specific models
python run_tests.py -i gpt-6-luna gpt-4.1

# Exclude specific models
python run_tests.py -ex gpt-3.5-turbo

# Run selected tests
python run_tests.py -t reasoning:none tool_calls

# Skip confirmation
python run_tests.py -f

# Log standard output
python run_tests.py -l
```

---

## 2. Querying Results

Use the results viewer to inspect previously recorded tests.

```bash
python results.py
```

### Arguments

| Argument         | Value                      | Description                                                       |
| -----------------| -------------------------- | ----------------------------------------------------------------- |
| `-m`, `--models` | MODEL [...]                | Filter by model names. Supports `*` wildcards.                    |
| `-t`, `--tests`  | TEST [...]                 | Filter by test names.                                             |
| `-k`, `--keys`   | KEY [...]                  | Select result fields to display.                                  |
| `-v`, `--view`   | details*, summary, test    | Select how the results are displayed                              |
| `-w`, `--wizard` |                            | Interactively select models, tests, and keys.                     |
| `--all-keys`     |                            | Display every available result field.                             |
| `--show-invalid` |                            | Display tests that they them selves are invalid, in the results.  |

### Examples

```bash
# Display all results
python results.py

# Display a specific model
python results.py -m gpt-6-luna

# Match multiple models
python results.py -m "gpt-6-*"

# Filter by test
python results.py -t reasoning:none tool_calls

# Display selected fields
python results.py -k request_status error_message

# Display all fields
python results.py --all-keys

# Interactive selection
python results.py -p

# Display summary results
python results.py --view summary

# Display tests with models grouped into states
python results.py --view summary
```

---

## 3. Result Files

The tools generate and use the following files:

| File                               | Purpose                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------ |
| `model_compatibility_results.json` | Detailed test results, including requests, responses, errors, and usage. |
| `model_compatibility_results.csv`  | Detailed results in spreadsheet-friendly format.                         |
| `model_compatibility_summary.csv`  | Condensed compatibility status by model and test.                        |

Existing results are reused to avoid repeating completed tests, and wasting API tokens.

## 4. Adding Tests

The current way to add tests is to edit `tests/tests.py` and add an object definition to the `TESTS` array.

At minimum Test definitions must contain the required properties seen in the table below,
and any other properties will be built into the payload.


| Required Keys    | Types                                                              |
| ---------------- |------------------------------------------------------------------- |
| name             | str                                                                |
| reasoning_effort | None, 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'   |
| use_tools        | bool                                                               |
| max_tokens       | number                                                             |

**Example**:
```python
{
    "name": "reasoning:max",
    "reasoning_effort": "max",
    "use_tools": False,
    "max_tokens": 128,
}
```