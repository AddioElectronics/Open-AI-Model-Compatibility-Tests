MAX_TOKENS_REASONING = 64
MAX_TOKENS_TOOLCALL = 128


TESTS = [
    {
        "name": "reasoning:none",
        "reasoning_effort": "none",
        "use_tools": False,
        "max_tokens": MAX_TOKENS_REASONING,
    },
    {
        "name": "reasoning:minimal",
        "reasoning_effort": "minimal",
        "use_tools": False,
        "max_tokens": MAX_TOKENS_REASONING,
    },
    {
        # Tests whether model supports tool calling using their default reasoning
        "name": "tool_calls:null",
        "reasoning_effort": None,
        "use_tools": True,
        "max_tokens": MAX_TOKENS_TOOLCALL,
    },
    {
        "name": "tool_calls:none",
        "reasoning_effort": "none",
        "use_tools": True,
        "max_tokens": MAX_TOKENS_TOOLCALL,
    },
    {
        # Tests whether model supports tool calling on chat/completions with reasoning
        "name": "tool_calls:low",
        "reasoning_effort": "low",
        "use_tools": True,
        "max_tokens": MAX_TOKENS_TOOLCALL,
    },
]
