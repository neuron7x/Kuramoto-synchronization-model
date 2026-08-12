# Module Contracts

Every module is called through the public request envelope and returns the public response envelope.

## Public surface

- module id
- operation
- input object
- output format
- language

## Hidden surface

- prompt wording
- intermediate notes
- adapter details
- implementation shortcuts

## Module list

- intent
- reflection
- introspection
- reverse_inference
- extrapolation
- artifact_builder
- safety

## Error policy

Modules return structured status and errors. Callers do not inspect private implementation state.
