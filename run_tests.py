import csv
import json
import os
import re
import sys
import time
import argparse
import atexit
import fnmatch
from enum import StrEnum, auto
from datetime import datetime, timezone
from openai import OpenAI

from tests.tests import TESTS
from core.input import *

def parse_args():
    parser = argparse.ArgumentParser(
        description="Test model compatibility"
    )
    
    parser.add_argument(
        "-a", "--apikey",
        default=None,
        help="Your Open AI API key, or leave blank to use api_key.txt",
    )

    parser.add_argument(
        "-i", "--include",
        metavar="MODEL",
        nargs="+",      # Space-separated list -> returns a list
        default=None,
        help="Explicitly include model names. (Supports * Wilcard)",
    )

    parser.add_argument(
        "-ex", "--exclude",
        metavar="MODEL",
        nargs="+",      # Space-separated list -> returns a list
        default=None,
        help="Explicitly exclude model names. (Supports * Wilcard)",
    )
    
    parser.add_argument(
        "-r", "--regex",
        metavar="REGEX",
        default=None,
        help="Regex for selecting models.",
    )

    parser.add_argument(
        "-rx", "--regexclude",
        metavar="REGEX",
        default=None,
        help="Regex for excluding models.",
    )

    parser.add_argument(
        "-t", "--tests",
        metavar="TEST",
        nargs="+",      # Space-separated list
        default=set(),  # Default to empty set if omitted
        type=str,       # Process items as raw strings first
        help="Choose which tests to perform or omit for all.",
    )
    
    parser.add_argument(
        "-w", "--wizard",
        action="store_true",
        help="Interactively select models, tests, and keys.",
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    
    parser.add_argument(
        "-l", "--log",
        action="store_true",
        help="Log stdout to file.",
    )
    
    parser.add_argument(
        "-d", "--delay",
        default=None,
        type=int,
        help="Set the delay in milliseconds between requests. If greater than 0, service tier is limited to 'default' and 'flex'.\n"
            f"Default: {REQUEST_DELAY_MS}, Maximum: 1,000",
    )    
    
    parser.add_argument(
        "-s", "--service-tier",
        choices=("default", "auto", "flex", "fast", "ultrafast"),
        default=None,
        help="Choose a service tier to use. If --delay is greater than 0, 'fast' and 'ultrafast' will fall back to 'default'.\n"
             "Default: flex",
    )

    parser.add_argument(
        "--max-retries",
        default=None,
        type=int,
        help="Maximum amount of test retries using the 'flex' tier before falling back to 'defualt or skipping.\n"
            f"Default: {MAX_RETRIES}",
    )
    
    parser.add_argument(
        "--max-timeouts",
        default=None,
        type=int,
        help="Maximum amount of sequential 'flex' tier timeouts before falling back to 'default' or stopping execution.\n"
            f"Default: {MAX_TIMEOUTS}",
    )
    
    parser.add_argument(
        "--no-fallback",
        action="store_false",
        default=None,
        help="Disable fallback to 'default' service tier if Flex fails.",
    )

    args = parser.parse_args()
    
    # Post-processing fix: convert the parsed list of tests into a clean set
    if isinstance(args.tests, list):
        args.tests = set(item.strip() for item in args.tests if item.strip())

    return args

def prompt_args(args, api_key, tests):
    # Get API key if one wasn't provided.
    while not api_key:
        api_key = input(
            "Enter OpenAI API key: "
        ).strip() or None


    # Initialize API client.
    openClient(api_key)

    # Retrieve available models.
    available_models = pullAndFilterModels()

    # Retrieve available test names.
    available_tests = sorted(test["name"] for test in tests)

    # Select models to include.
    selected_models = prompt_selection(
        "models",
        available_models,
        wildcard=True,
        default=None,
        showOptions=True,
    ) if not args.include else args.include
    
    exclude_models = prompt_selection(
        "models to exclude",
        available_models,
        wildcard=True,
        default=None,
        showOptions=False,
    ) if not args.exclude else args.exclude
    

    # Default to all models if none were explicitly selected.
    if selected_models is None:
        selected_models = set(DEFAULT_MODELS)
    else:
        selected_models = set(selected_models)

    # Remove excluded models.
    selected_models -= exclude_models or set()

    # Select tests to run.
    selected_tests = prompt_selection(
        "tests",
        available_tests,
        default=None,
    ) if not args.tests else args.tests

    # Store selections on args.
    args.include = selected_models
    args.exclude = exclude_models
    args.tests = selected_tests
    
    args.delay = prompt_int(
        "delay (ms)",
        0,
        1000,
        REQUEST_DELAY_MS
    ) if args.delay is None else args.delay
    
    args.service_tier = (prompt_enum(
                            "service tiers (Default: flex)",
                            ("default", "auto", "flex", "fast", "ultrafast"),
                            "flex"
                        ) if args.service_tier is None else args.service_tier)
    
    if args.service_tier == 'flex':
        args.no_fallback = not prompt_bool("fallback to 'default' tier on flex timeout?", False) if args.no_fallback is None else args.no_fallback
        args.max_retries = prompt_int("Max flex retries", 0, None, MAX_RETRIES) if args.max_retries is None else args.max_retries
        args.max_timeouts = prompt_int("Max timeouts", 0, None, MAX_TIMEOUTS) if args.max_timeouts is None else args.max_timeouts
        

    return args, api_key


def sanitize_args(args):
    """
    Ensure basic argument values are within range, and resolve defaults when None.
    
    Arguments that rely on API data such as --includes are not handled.
    """    
    if args.delay:
        if args.delay < 0:
            raise ValueError("--delay cannot be negative")
        elif args.delay > 1000:
            args.delay = 1.0
        else:
            args.delay = args.delay / 1000.0
    else:
        args.delay = REQUEST_DELAY_MS / 1000.0
        
    if args.service_tier is None:
        args.service_tier = "flex"
    elif args.delay > 0 and args.service_tier in ('fast', 'ultrafast'):
        args.service_tier = 'default'
        
    if args.max_retries is None:
        args.max_retries = MAX_RETRIES
    elif args.max_retries < 0:
        raise ValueError("--max--retries cannot be negative")
        
    if args.max_timeouts is None:
        args.max_timeouts = MAX_TIMEOUTS
    elif args.max_timeouts < 0:
        raise ValueError("--max--timeouts cannot be negative")
        
    if args.no_fallback is None:
        args.no_fallback = False
        
# =========================================================
# Configuration
# =========================================================
RESULTS_BASE = "results/"
RESULTS_CSV = f"{RESULTS_BASE}model_compatibility_results.csv"
RESULTS_JSON = f"{RESULTS_BASE}model_compatibility_results.json"
SUMMARY_CSV = f"{RESULTS_BASE}model_compatibility_summary.csv"

REQUEST_DELAY_MS = 250      # Default
MAX_TIMEOUTS     = 10       # Maximum sequential timeouts before permanent fallback to "default" or app exit
MAX_RETRIES      = 0        # Maximum amount of retries using the 'flex' tier before falling back to 'defualt or skipping

# OpenAi client
CLIENT = None
PULLED_MODELS = None
API_KEY_FILE = "api_key.txt"

def tryReadApiKey():
    if not os.path.exists(API_KEY_FILE): return None
    try:        
        with open(
            API_KEY_FILE,
            "r",
            newline="",
            encoding="utf-8",
        ) as file:
            return file.readline()
    except:
        return None
    
def openClient(api_key):
    global CLIENT
    if CLIENT:        return    
    if not api_key:   raise KeyError("Api Key cannot be empty!")
    CLIENT = OpenAI(api_key=api_key)
    
# =========================================================
# Input
# =========================================================

def promptYesNo(message, force):
    if force: return True
    while True:
        try:
            accept = input(message + ' Y/N ').strip().lower()
        except EOFError:
            print("\nNo interactive input available. Use '--force' to disable prompts.")
            exit(1)

        if accept in ('y', 'yes'):
            return True
        elif accept in ('n', 'no'):
            return False
        else:
            print("Please enter Y or N.")
        
# =========================================================
# Logging
# =========================================================

LOG_FILE = None
def close_log_file():
    if LOG_FILE and not LOG_FILE.closed:
        LOG_FILE.close()

class DualStream:
    def __init__(self, terminal_stream, file_stream):
        self.terminal = terminal_stream
        self.file = file_stream

    def write(self, message):
        self.terminal.write(message)  # Send to standard console
        self.file.write(message)      # Send to log file
        self.file.flush()             # Instantly save to disk

    def flush(self):
        self.terminal.flush()
        self.file.flush()
        
def hijack_stdout():
    global LOG_FILE
    if LOG_FILE: return
    LOG_FILE = open(
        datetime.now().strftime(f"{RESULTS_BASE}log_%Y%m%d_%H%M%S.txt"),
        'w',
        newline="",
        encoding="utf-8-sig"
        )
    atexit.register(close_log_file)
    sys.stdout = DualStream(sys.stdout, LOG_FILE)
    sys.stderr = DualStream(sys.stderr, LOG_FILE)

# =========================================================
# Model discovery
# =========================================================

# Default patterns are a first pass used to filter initial models retrieved via the API.
# Command line arguments are the second pass used to precisely narrow down the model selection.

# Include all gpt and o# models
DEFAULT_INCLUDE_PATTERN = re.compile(r"^(gpt-|o\d)")

# Exclude non text-text models
DEFAULT_EXCLUDE_PATTERN = re.compile(
    r"realtime|transcribe|translate|audio|tts|search|"
    r"^gpt-image-|instruct"
)

# Canonical model names to test by default.
# Dated snapshots are intentionally excluded.
DEFAULT_MODELS = {
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5-chat-latest",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5-pro",
    "gpt-5-codex",
    "gpt-5.1",
    "gpt-5.1-chat-latest",
    "gpt-5.1-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
    "gpt-5.2",
    "gpt-5.2-chat-latest",
    "gpt-5.2-codex",
    "gpt-5.2-pro",
    "gpt-5.3-chat-latest",
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.4-pro",
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-6-astra",
    "gpt-6-luna",
    "gpt-6-sol",
    "gpt-6.1-sol",
    "o1",
    "o1-pro",
    "o3",
    "o3-mini",
    "o4-mini",
}

# Filters all non text-text models
def pullAndFilterModels():
    global CLIENT, PULLED_MODELS
    
    if not PULLED_MODELS:
        response = CLIENT.models.list()
        api_models = sorted([
            model.id for model in response.data
            if DEFAULT_INCLUDE_PATTERN.search(model.id) and not DEFAULT_EXCLUDE_PATTERN.search(model.id)
            ], key=str.lower)
        PULLED_MODELS = api_models
    return PULLED_MODELS

def select_models(available_model_ids, args):
    api_models = set(available_model_ids)
    selected = set()

    # Stage 1: Include API models matching the regex.
    if args.regex:
        include_regex = re.compile(args.regex, re.IGNORECASE)
        selected.update(
            model for model in api_models
            if include_regex.search(model)
        )

    # Stage 2: Use defaults if no inclusion filters were provided.
    if not args.regex and not args.include:
        selected.update(DEFAULT_MODELS)

    # Stage 3: Add explicitly included models.
    if args.include:
        valid_models = set(args.include) & api_models
        invalid_models = set(args.include) - api_models

        selected.update(valid_models)

        if invalid_models:
            print(
                "Invalid model IDs: "
                + ", ".join(sorted(invalid_models))
            )

    # Stage 4: Apply regex exclusions.
    if args.regexclude:
        exclude_regex = re.compile(args.regexclude, re.IGNORECASE)
        selected = {
            model for model in selected
            if not exclude_regex.search(model)
        }

    # Stage 5: Apply explicit exclusions.
    selected.difference_update(args.exclude or [])

    # Stage 6: Return sorted, deduplicated model IDs.
    return sorted(selected)


# =========================================================
# Tool definition
# =========================================================

# Fake tools. The script does not execute it.
FAKE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "test_tool",
            "description": (
                "A test function used to verify tool-calling support. "
                "Call this function with message set to OK."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The test message.",
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]


# =========================================================
# Payload construction
# =========================================================

def uses_max_completion_tokens(model_name):
    """
    Check if model used 'max_completion_tokens' over the deprecated 'max_tokens' in the API request.
    """    
    return (
        model_name.startswith("o1-")
        or model_name.startswith("o3-")
        or model_name.startswith("o4-")
        or model_name.startswith("gpt-5")
        or model_name.startswith("gpt-6")
    )


def build_payload(model, test, args):
    """
    Constructs a minimal Chat Completions payload from a test object. 
    """

    messages = [
        {
            "role": "system",
            "content": (
                "You are participating in an API compatibility test. "
                "Follow the user's instruction exactly."
            ),
        }
    ]

    if test["use_tools"]:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Call the test_tool function with message set to OK. "
                    "Do not provide a normal text response."
                ),
            }
        )
    else:
        messages.append(
            {
                "role": "user",
                "content": "Reply with OK.",
            }
        )

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    if uses_max_completion_tokens(model):
        payload["max_completion_tokens"] = test["max_tokens"]
    else:
        payload["max_tokens"] = test["max_tokens"]

    if test["reasoning_effort"] is not None:
        payload["reasoning_effort"] = test["reasoning_effort"]

    if test["use_tools"]:
        payload["tools"] = FAKE_TOOLS

        # Here we use "required" to make the test deterministic:
        # the model must call a tool if the request is accepted.
        payload["tool_choice"] = "required"
       
    payload["service_tier"] = args.service_tier
        
    # Add standard keys
    special_keys = ("name", "use_tools", "reasoning_effort", "max_tokens", "model", "stream")
    reserved_keys = ("model", "stream", "service_tier")
    for key, value in test.items():
        if key in special_keys:
            if key in reserved_keys:
                print(f"Reserved test key will be skipped ({key}: {value})")
            continue
        payload[key] = value

    return payload


# =========================================================
# API execution
# =========================================================

def run_test(model, test, args, result=None):
    global CLIENT
    payload = build_payload(model, test, args) if not result else result["request_payload"]

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "test": test["name"],
        "reasoning_effort_requested": (
            test["reasoning_effort"]
            if test["reasoning_effort"] is not None
            else "omitted"
        ),
        "tool_calling_requested": test["use_tools"],
        "token_parameter": (
            "max_completion_tokens"
            if "max_completion_tokens" in payload
            else "max_tokens"
        ),
        "max_tokens_requested": test["max_tokens"],
        "request_payload": payload,
        "request_status": "unknown",
        "http_status": None,
        "finish_reason": None,
        "response_text": None,
        "tool_calls_returned": False,
        "tool_call_names": [],
        "tool_call_arguments": [],
        "usage": None,
        "response_dump": None,
        "latency_seconds": None,
        "error_type": None,
        "error_code": None,
        "error_message": None,
        "output_log": None,
    } if not result else result

    print(f"  {test['name']}: ", end="", flush=True)
    
    def write_log(message):
        result["output_log"] = message
        print(message)

    started = time.perf_counter()

    try:
        # We construct the payload ourselves to keep the JSON
        # fields explicit and reproducible.
        response = CLIENT.chat.completions.create(**payload)

        result["request_status"] = "success"
        result["http_status"] = 200

        choice = response.choices[0]
        message = choice.message

        result["finish_reason"] = choice.finish_reason
        result["response_text"] = message.content

        returned_calls = message.tool_calls or []

        result["tool_calls_returned"] = bool(returned_calls)

        result["tool_call_names"] = [
            call.function.name for call in returned_calls
        ]

        result["tool_call_arguments"] = [
            {
                "name": call.function.name,
                "arguments": call.function.arguments,
            }
            for call in returned_calls
        ]

        if response.usage is not None:
            result["usage"] = response.usage.model_dump()

        result["response_dump"] = response.model_dump()

        if test["use_tools"]:
            if returned_calls:
                write_log("SUCCESS — tool call returned")
            else:
                write_log(
                    "SUCCESS — no tool call returned "
                    f"(finish_reason={choice.finish_reason})"
                )
        else:
            write_log(
                f"SUCCESS — response={message.content!r}"
            )

    except Exception as exc:
        validity = get_result_validity(type(exc).__name__)
        result["request_status"] = "error"
        result["error_type"] = type(exc).__name__
        result["result_validity"] = validity
        result["error_message"] = str(exc)        
        result["http_status"] = getattr(exc, "status_code", None)
        result["error_code"] = getattr(exc, "code", None)

        body = getattr(exc, "body", None)
        if body is not None:
            result["error_body"] = body

        if validity == ResultValidity.VALID:
            write_log(
                f"ERROR — {type(exc).__name__}: "
                f"{str(exc)[:250]}"
            )
        else:
            write_log(
                f"TEST_{validity.upper()} — {type(exc).__name__}: "
                f"{str(exc)[:250]}"
            )

    finally:
        result["latency_seconds"] = round(
            time.perf_counter() - started, 3
        )

    return result

def is_flex_failure(test_result):
    return test_result["request_payload"]["service_tier"] == 'flex' and test_result.get("error_code", None) == "flex_unavailable" #and test_result["http_status"] in (408, 429)

def is_result_valid(test_result):
    validity = test_result.get("result_validity", None)
    if validity is None:
        validity = get_result_validity(test_result["error_type"])
        test_result["result_validity"] = validity
    return validity == ResultValidity.VALID

def is_result_invalid(test_result):
    validity = test_result.get("result_validity", None)
    if validity is None:
        validity = get_result_validity(test_result["error_type"])
        test_result["result_validity"] = validity
    return validity == ResultValidity.INVALID

def is_result_inconclusive(test_result):
    validity = test_result.get("result_validity", None)
    if validity is None:
        validity = get_result_validity(test_result["error_type"])
        test_result["result_validity"] = validity
    return validity == ResultValidity.INCONCLUSIVE

class ResultValidity(StrEnum):
    """
    Describes whether a test result can be used to evaluate compatibility.
    """

    INCONCLUSIVE = auto()
    """Test outcome is uncertain, e.g., connection failure, timeout, auth, etc.."""

    VALID = auto()
    """Test ran and produced an interpretable result, including API rejection
    of the tested configuration."""

    INVALID = auto()
    """Test target is invalid or unavailable, e.g., model not found."""


def get_result_validity(error_type: str | None) -> ResultValidity:
    if error_type is None:
        return ResultValidity.VALID

    # The test could not reliably establish compatibility.
    inconclusive_errors = {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "PermissionDeniedError",
        "AuthenticationError",
        "OAuthError",
        "SubjectTokenProviderError",
        "APIResponseValidationError",
        "APIStatusError",
        "ConflictError",
        "ContentFilterFinishReasonError",
        "LengthFinishReasonError",
    }

    if error_type in inconclusive_errors:
        return ResultValidity.INCONCLUSIVE

    # The target itself is invalid or unavailable.
    if error_type == "NotFoundError":
        return ResultValidity.INVALID

    # The API evaluated the request but rejected the configuration.
    # The error is a valid test outcome, not necessarily a compatibility success.
    if error_type in {
        "BadRequestError",
        "UnprocessableEntityError",
    }:
        return ResultValidity.VALID

    # Unknown errors require investigation.
    return ResultValidity.INCONCLUSIVE

# =========================================================
# CSV and JSON output
# =========================================================

CSV_FIELDS = [
    "timestamp_utc",
    "model",
    "test",
    "reasoning_effort_requested",
    "tool_calling_requested",
    "token_parameter",
    "max_tokens_requested",
    "request_status",
    "http_status",
    "finish_reason",
    "response_text",
    "tool_calls_returned",
    "tool_call_names",
    "tool_call_arguments",
    "usage",
    "latency_seconds",
    "error_type",
    "error_code",
    "error_message",
]


def csv_safe(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    if value is None:
        return ""

    return value


def save_results(results):
    # Detailed CSV: one row per model/test combination.
    with open(
        RESULTS_CSV,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()

        for model, tests in results.items():
            for test_name, obj in tests.items():
                row = {
                    field: csv_safe(obj.get(field))
                    for field in CSV_FIELDS
                }

                # Ensure identifiers match the dictionary keys.
                row["model"] = model
                row["test"] = test_name

                writer.writerow(row)

    # JSON retains complete request payloads and response dumps.
    with open(
        RESULTS_JSON,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # Save the summary using the same nested structure.
    save_summary(results)


def save_summary(results):
    by_model = {}

    for model, tests in results.items():
        row = {"model": model}

        for test_name, result in tests.items():
            
            if result["result_validity"] != ResultValidity.VALID:
                status = f"TEST_{result["result_validity"].upper()}"
            
            elif result["request_status"] != "success":
                status = "ERROR"

            elif test_name.startswith("tool_calls"):
                status = (
                    "TOOL_CALL"
                    if result["tool_calls_returned"]
                    else "NO_TOOL_CALL"
                )

            else:
                status = "ACCEPTED"

            row[test_name] = status

            if result.get("error_message"):
                row[f"{test_name}_error"] = result["error_message"]

        by_model[model] = row

    # Build columns from TESTS so new tests are included automatically.
    fields = ["model"]

    for test in TESTS:
        test_name = test["name"]
        fields.append(test_name)
        fields.append(f"{test_name}_error")

    with open(
        SUMMARY_CSV,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for model in sorted(by_model, key=str.lower):
            writer.writerow(by_model[model])


def open_old_summary():
    if not os.path.exists(SUMMARY_CSV):
        return {}

    results = {}

    with open(
        SUMMARY_CSV,
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            model = row["model"]

            results[model] = {
                key: value
                for key, value in row.items()
                if key != "model"
                and value not in (None, "")
                and not key.endswith("_error")
            }

    return results

def open_old_results():
    if not os.path.exists(RESULTS_JSON):
        return {}

    with open(
        RESULTS_JSON,
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        return json.load(file)


# =========================================================
# Main
# =========================================================

def main():
    global CLIENT
    args = parse_args()
    
    if args.log:
        hijack_stdout()
    
    api_key = args.apikey
    if not api_key:
        api_key = tryReadApiKey()
    
    if args.wizard:
        prompt_args(args, api_key, TESTS)
    else:
        openClient(api_key)
        
    sanitize_args(args)
    
    try:

        # Retrieve the filtered models exposed by the API.
        model_ids = pullAndFilterModels()

        # Build the final test list.
        models = select_models(model_ids, args)
        
    except Exception as exc:
        sys.exit(
            f"Failed to list models: "
            f"{type(exc).__name__}: {exc}"
        )

    print(f"\nSelected {len(models)} models for testing:")
    if not models:
        print("\tError: No matching models found!")
        exit(1)
    
    for model in models:
        print(f"  - {model}")
        
    
    if not promptYesNo("Accept model list?", args.force):
        return

    total_tests = len(models) * len(TESTS)

    print(f"\nModels: {len(models)}")
    print(f"Tests per model: {len(TESTS)}")
    print(f"Total test requests: {total_tests}\n")
    
    # prev_summary = open_old_summary() or {}
    results = open_old_results() or {}
    tests: set = args.tests
    is_flex = args.service_tier == 'flex'
    max_timeouts = args.max_timeouts
    timeouts = 0 # Consecutive tests with flex timeouts (Does not include retries)

    for index, model in enumerate(models, start=1):
        print(f"\n[{index}/{len(models)}] {model}")
        
        # old_summary = prev_summary.get(model, {})
        model_obj = results.get(model, {})
        results[model] = model_obj

        def run_tests():
            nonlocal is_flex, timeouts
            
            for test in TESTS:
                test_name = test["name"]
                
                if not test_name:
                    raise ValueError(f"Test detected without a name: {test}")
                
                skip_test = tests and test_name not in tests
                prev_result = model_obj.get(test_name, None)
                
                # Skip tests that already have a saved valid result.
                if prev_result and not is_result_inconclusive(prev_result):
                    if not skip_test:
                        test_obj = model_obj[test_name]
                        print(f"  [Previous Result] {test_name}: {test_obj["output_log"]}\n", end="", flush=True)
                    continue
                
                if skip_test:
                    continue                    
                
                # Run test on 
                result = run_test(model, test, args)
                
                # Handle flex timeouts
                if is_flex and is_flex_failure(result):
                    timeouts += 1
                    
                    def retry():
                        nonlocal result
                        retries = 0
                        while retries < args.max_retries:
                            retries += 1
                            print(f"  Flex timeout {timeouts}/{args.max_timeouts}! Retrying ... {retries}/{args.max_retries}")  
                            result = run_test(model, test, args, result)
                            if not is_flex_failure(result):
                                return True
                        return False

                    # Fallbacks disabled, skip test
                    if args.no_fallback:                        
                        if timeouts > max_timeouts:
                            print(f"  Flex timeout! Max sequential timeouts of {timeouts} reached, exiting...\n")
                            exit(1)    
                        elif not retry():
                            print(f"  Flex timeout {timeouts}/{args.max_timeouts}! Skipping test...\n")                   

                    # Fallback and retry on standard tier
                    elif not retry():
                        print(f"  Flex timeout {timeouts}/{args.max_timeouts}! Retrying and falling back to standard tier...\n")

                        # Permanently fall back to default
                        if timeouts > max_timeouts:
                            print(f"  Max sequential timeouts of {timeouts} reached.\n")
                            print(f"  Permanently falling back to 'default' service_tier.\n")
                            
                            args.service_tier = "default"
                            is_flex = False
                        
                        # Re-run test on default tier
                        result["request_payload"]["service_tier"] = "default"
                        result = run_test(model, test, args, result)
                            
                else:
                    timeouts = 0
                
                # Update fail count for previously executed tests
                if prev_result:
                    if is_result_valid(result):
                        result.pop("result_fail_count", None)
                    else:
                        result["result_fail_count"] = result.get("result_fail_count", 0) + 1
                        
                
                model_obj[test_name] = result

                # Persist results after every request.
                save_results(results)

                time.sleep(args.delay)
                
        run_tests()


    print("\n" + "=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)

    for model in models:
        model_results = results.get(model, {})

        print(f"\n{model}")

        for test_name, result in model_results.items():
            if result["result_validity"] != ResultValidity.VALID:
                status = f"TEST_{result["result_validity"].upper()}"
            elif result["request_status"] != "success":
                status = "ERROR"
            elif test_name.startswith("tool_calls"):
                status = (
                    "TOOL CALL"
                    if result["tool_calls_returned"]
                    else "NO TOOL CALL"
                )
            else:
                status = "ACCEPTED"

            print(f"  {test_name:<32} {status}")


    print("\nFinished.")
    print(f"Detailed CSV: {os.path.abspath(RESULTS_CSV)}")
    print(f"Detailed JSON: {os.path.abspath(RESULTS_JSON)}")
    print(f"Summary CSV: {os.path.abspath(SUMMARY_CSV)}")

if __name__ == "__main__":
    main()
