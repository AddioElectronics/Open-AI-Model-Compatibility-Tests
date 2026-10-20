import os
import argparse
import json
import csv
import textwrap
import fnmatch

from core.input import *

RESULTS_JSON = "results/model_compatibility_results.json"
SUMMARY_CSV = "results/model_compatibility_summary.csv"

DEFAULT_KEYS = ["output_log"]
SEPARATOR = "─" * 100


def parse_args():
    parser = argparse.ArgumentParser(
        description="Query model test results"
    )

    parser.add_argument(
        "-m", "--models",
        metavar="MODEL",
        nargs="+",
        default=None,
        help="Filter by model names. Defaults to all models. (Supports * wildcard)",
    )

    parser.add_argument(
        "-t", "--tests",
        metavar="TEST",
        nargs="+",
        default=None,
        help="Filter by test names. Defaults to all tests.",
    )

    parser.add_argument(
        "-k", "--keys",
        metavar="KEY",
        nargs="+",
        default=DEFAULT_KEYS,
        help="JSON result keys to display. output_log is always included.",
    )

    parser.add_argument(
        "-v", "--view",
        choices=("details", "summary", "test"),
        default=None,
        help=(
            "Choose the results view: "
            "details*, summary, or test."
        ),
    )
    
    parser.add_argument(
        "-w", "--wizard",
        action="store_true",
        help="Interactively select models, tests, and keys.",
    )

    parser.add_argument(
        "--all-keys",
        action="store_true",
        help="Display every available result key.",
    )
    
    parser.add_argument(
        "--show-invalid",
        action="store_true",
        default=None,
        help="Display invalid tests in the results.",
    )

    args = parser.parse_args()

    if args.models:
        args.models = {item.strip() for item in args.models if item.strip()}

    if args.tests:
        args.tests = {item.strip() for item in args.tests if item.strip()}

    args.keys = {item.strip() for item in args.keys if item.strip()}

    return args

def prompt_args(args):
    results = open_results()

    available_models = sorted(results.keys(), key=str.lower)

    available_tests = sorted({
        test
        for model_results in results.values()
        if isinstance(model_results, dict)
        for test in model_results
    })

    available_keys = sorted({
        key
        for model_results in results.values()
        if isinstance(model_results, dict)
        for result in model_results.values()
        if isinstance(result, dict)
        for key in result
    })

    args.models = prompt_selection(
        "models",
        available_models,
        True
    ) if not args.models else args.models
    
    args.tests = prompt_selection(
        "tests",
        available_tests
    ) if not args.tests else args.tests
    
    args.view = prompt_enum(
        "view",
        ["details", "summary", "test"],
        "details"
    ) if not args.view else args.view
    
    if (not args.view or args.view == 'details'):
        
        args.all_keys = prompt_bool("Display all keys?", False ) if args.all_keys is None else args.all_keys
        
        if not args.all_keys:
            args.keys = prompt_selection(
                "keys",
                available_keys,
                False,
                {"output_log"}
            ) if not args.keys else args.keys
        
    args.show_invalid = prompt_bool("Show invalid tests in the results?", False ) if args.show_invalid is None else args.show_invalid

    return args

def match_options(patterns, options):
    return {
        option
        for option in options
        if any(fnmatch.fnmatchcase(option, pattern) for pattern in patterns)
    }

def open_results():
    if not os.path.exists(RESULTS_JSON):
        print(f"Results file not found: {RESULTS_JSON}")
        return {}

    try:
        with open(RESULTS_JSON, "r", encoding="utf-8-sig") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not load results: {exc}")
        return {}


def open_summary():
    if not os.path.exists(SUMMARY_CSV):
        print(f"Summary file not found: {SUMMARY_CSV}")
        return {}

    results = {}

    try:
        with open(
            SUMMARY_CSV,
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            reader = csv.DictReader(file)

            for row in reader:
                model = row.get("model")
                if not model:
                    continue

                results[model] = {
                    key: value
                    for key, value in row.items()
                    if key != "model"
                    and value not in (None, "")
                    and not key.endswith("_error")
                }

    except (OSError, csv.Error) as exc:
        print(f"Could not load summary: {exc}")

    return results


def format_value(value):
    """Format values for readable terminal output."""
    if value is None:
        return "None"

    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)

    return str(value)


def print_field(key, value, indent="    ", width=96):
    """Print a result field, wrapping long lines."""
    formatted = format_value(value)

    print(f"{indent}{key}:")

    for line in formatted.splitlines() or [""]:
        wrapped = textwrap.wrap(
            line,
            width=width - len(indent) - 4,
            replace_whitespace=False,
            drop_whitespace=False,
        )

        if not wrapped:
            print(f"{indent}    ")
        else:
            for wrapped_line in wrapped:
                print(f"{indent}    {wrapped_line}")


def view_detailed_results(args, models=None, tests=None, keys=None, all_keys=False):
    results = open_results()

    if not results:
        print("No detailed results to display.")
        return

    selected_models = (
        sorted(results, key=str.lower)
        if models is None
        else sorted(
            (model for model in results if model in models),
            key=str.lower,
        )
    )

    if models is not None:
        missing_models = models - results.keys()
        for model in sorted(missing_models, key=str.lower):
            print(f"Warning: model not found: {model}")

    displayed_count = 0

    for model in selected_models:
        model_results = results[model]

        if not isinstance(model_results, dict):
            continue

        selected_tests = (
            sorted(model_results)
            if tests is None
            else sorted(
                test_name
                for test_name in model_results
                if test_name in tests
            )
        )

        matching_tests = [
            (test_name, model_results[test_name])
            for test_name in selected_tests
            if isinstance(model_results[test_name], dict)
        ]

        if not matching_tests:
            continue

        print()
        print(SEPARATOR)
        print(f"  MODEL: {model}")
        print(SEPARATOR)

        for test_name, result in matching_tests:
            print(f"\n  ┌─ TEST: {test_name}")
            print("  │")
            
            if not args.show_invalid and result.get('result_validity') == 'invalid':
                continue

            if all_keys:
                selected_keys = list(result.keys())
            else:
                selected_keys = sorted(keys or DEFAULT_KEYS)

                # Always include output_log if it exists.
                if "output_log" in result and "output_log" not in selected_keys:
                    selected_keys.append("output_log")

            for key in selected_keys:
                if key not in result:
                    print(f"  │  {key}: <not available>")
                    continue

                value = format_value(result[key])
                lines = value.splitlines() or [""]

                print(f"  │  {key}:")
                for line in lines:
                    print(f"  │      {line}")

            print("  └" + "─" * 96)
            displayed_count += 1

    print()
    print(SEPARATOR)
    print(f"Displayed {displayed_count} test result(s).")
    print(SEPARATOR)


def view_summary(args, models=None, tests=None):
    results = open_summary()

    if not results:
        print("No summary results to display.")
        return

    selected_models = (
        sorted(results, key=str.lower)
        if models is None
        else sorted(
            (model for model in results if model in models),
            key=str.lower,
        )
    )

    for model in selected_models:
        print()
        print(SEPARATOR)
        print(f"  MODEL: {model}")
        print(SEPARATOR)

        model_results = results[model]

        for test_name, status in sorted(model_results.items()):
            if ((tests is not None and test_name not in tests) or
                (not args.show_invalid and status == 'TEST_INVALID')):
                continue

            print(f"  {test_name:<40} {status}")

    print()
    print(SEPARATOR)

def view_by_test(args, models=None, tests=None):
    results = open_summary()

    if not results:
        print("No summary results to display.")
        return

    # Select models.
    selected_models = (
        sorted(results, key=str.lower)
        if models is None
        else sorted(
            (model for model in results if model in models),
            key=str.lower,
        )
    )

    if not selected_models:
        print("No matching models found.")
        return

    # Group models by test and result status.
    test_results = {}

    for model in selected_models:
        for test_name, status in results[model].items():
            if tests is not None and test_name not in tests:
                continue

            test_results.setdefault(test_name, {}).setdefault(
                status, []
            ).append(model)

    if not test_results:
        print("No matching test results found.")
        return

    # Display results grouped by test.
    status_order = [
        "ACCEPTED",
        "ERROR",
        "TOOL_CALL",
        "NO_TOOL_CALL",
        "TEST_INCONCLUSIVE",
    ]
    
    if args.show_invalid:
        status_order.append('TEST_INVALID')

    for test_name in sorted(test_results, key=str.lower):
        print()
        print(SEPARATOR)
        print(f"  TEST: {test_name}")
        print(SEPARATOR)

        statuses = test_results[test_name]

        for status in status_order:
            matching_models = sorted(
                statuses.get(status, []),
                key=str.lower,
            )

            if matching_models:
                print(f"\n  {status.title().replace('_', ' ')}:")
                for model in matching_models:
                    print(f"    - {model}")

    print()
    print(SEPARATOR)

def main():
    args = parse_args()

    if args.wizard:
        args = prompt_args(args)
        
    models = args.models
    tests = args.tests
    
    if not args.view:
        args.view = "details"
        
    if args.view == "test":
        view_by_test(args, models=models, tests=tests)
    elif args.view == "summary":
        view_summary(args, models=models, tests=tests)
    else:
        view_detailed_results(args, models=models, tests=tests)


if __name__ == "__main__":
    main()
