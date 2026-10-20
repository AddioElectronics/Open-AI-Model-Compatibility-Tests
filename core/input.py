import fnmatch

__all__ = ["prompt_selection", "prompt_enum", "prompt_bool", "prompt_int", "prompt_float",]

def prompt_selection(label, options, wildcard=False, default=None, showOptions=True):
    
    if showOptions:
        print(f"\nAvailable {label}:")    
        for option in options:
            if option == default:
                print(f"  - *{option}*")
            else:
                print(f"  - {option}")

    wildcard_text = " (supports * wildcard)" if wildcard else ""

    while True:
        answer = input(
            f"\nEnter {label}, separated by commas"
            f"{wildcard_text} (Enter for all): "
        ).strip()

        if not answer:
            return default

        selected = {
            item.strip()
            for item in answer.split(",")
            if item.strip()
        }

        if wildcard:
            matched = {
                option
                for option in options
                if any(
                    fnmatch.fnmatchcase(option, pattern)
                    for pattern in selected
                )
            }

            invalid = {
                pattern
                for pattern in selected
                if not any(
                    fnmatch.fnmatchcase(option, pattern)
                    for option in options
                )
            }
            
        elif len(selected) == 1:
            test_name = next(iter(selected))
            if test_name not in options:
                print(f"Unknown {label}: {test_name}")
                continue
            return selected
            
        else:
            matched = selected & set(options)
            invalid = selected - set(options)

        if invalid:
            print(f"Unknown {label}: {', '.join(sorted(invalid))}")
            
        if len(matched) == 0:
            continue

        return matched

def prompt_enum(label, options=None, default=None):
    print(f"\nAvailable {label}:")
    for option in options:
        if option == default:
            print(f"  - *{option}")
        else:
            print(f"  - {option}")

    while True:
        answer = input(
            f"\nEnter {label} (Enter for default):"
        ).strip()

        if not answer:
            return default

        if options and answer not in options:
            print(f"Unknown {label}: {answer}")
        else:
            return answer
        
def prompt_bool(message, default=None):
    # Formulate a helpful default hint for the user prompt
    if default is True:
        default_str = " [Y/n]"
    elif default is False:
        default_str = " [y/N]"
    else:
        default_str = " [y/n]"

    # Maps common text answers to structural boolean values
    true_options = {"y", "yes", "true", "t", "1"}
    false_options = {"n", "no", "false", "f", "0"}

    while True:
        answer = input(f"{message}{default_str}: ").strip().lower()

        # Handle the default case when the user hits Enter without typing
        if not answer:
            if default is not None:
                return default
            print("Please enter an answer (y or n).")
            continue

        # Evaluate the answer against standard truth/falsity options
        if answer in true_options:
            return True
        elif answer in false_options:
            return False
        else:
            print(f"Unknown option: '{answer}'. Please enter yes/no, y/n, or true/false.")

def prompt_int(label, min_val=None, max_val=None, default=None):
    # 1. Build the dynamic boundary message fragment
    bounds = []
    if min_val is not None:
        bounds.append(f"min: {min_val}")
    if max_val is not None:
        bounds.append(f"max: {max_val}")
    
    bounds_str = f" ({', '.join(bounds)})" if bounds else ""
    default_str = f" [default: {default}]" if default is not None else ""

    while True:
        # 2. Display the prompt with min, max, and default options
        answer = input(f"Enter {label}{bounds_str}{default_str}: ").strip()

        # 3. Handle default case
        if not answer:
            if default is not None:
                return default
            print("A value is required.")
            continue

        # 4. Validate that the input is a number
        try:
            num = int(answer)
        except ValueError:
            print(f"Invalid input: '{answer}' is not a valid whole number.")
            continue

        # 5. Check min/max range boundaries
        if min_val is not None and num < min_val:
            print(f"Too low! Value must be at least {min_val}.")
        elif max_val is not None and num > max_val:
            print(f"Too high! Value must be at most {max_val}.")
        else:
            return num

def prompt_float(label, min_val=None, max_val=None, default=None):
    # 1. Build the dynamic boundary message fragment
    bounds = []
    if min_val is not None:
        bounds.append(f"min: {min_val}")
    if max_val is not None:
        bounds.append(f"max: {max_val}")
    
    bounds_str = f" ({', '.join(bounds)})" if bounds else ""
    default_str = f" [default: {default}]" if default is not None else ""

    while True:
        # 2. Display the prompt with min, max, and default options
        answer = input(f"Enter {label}{bounds_str}{default_str}: ").strip()

        # 3. Handle default case
        if not answer:
            if default is not None:
                return default
            print("A value is required.")
            continue

        # 4. Validate that the input is a number
        try:
            num = float(answer)
        except ValueError:
            print(f"Invalid input: '{answer}' is not a valid floating point number.")
            continue

        # 5. Check min/max range boundaries
        if min_val is not None and num < min_val:
            print(f"Too low! Value must be at least {min_val}.")
        elif max_val is not None and num > max_val:
            print(f"Too high! Value must be at most {max_val}.")
        else:
            return num
