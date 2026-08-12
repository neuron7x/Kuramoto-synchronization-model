# Architecture

The system is a modular cognitive-methods workspace.

## Shared request

- method_id
- user_context
- objective
- constraints
- input_text
- output_mode
- language
- safety_level

## Shared response

- method_id
- status
- result
- artifacts
- validation
- next_action

## Pipeline

raw input -> finalizer -> reflection -> introspection -> reverse inference -> extrapolated thinking -> insight to artifact -> validation -> next iteration.

## Module contract

Each module must define: definition, input, process, output, validation, failure modes, example, schema, and test.
