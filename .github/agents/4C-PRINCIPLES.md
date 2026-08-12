# 4C Principles for Documentation

The DOC PR COPILOT v2 agent enforces the 4C principles for all documentation. This ensures consistent, high-quality technical documentation across the repository.

## The 4C Framework

### 1. Clarity (Ясність)

**Definition:** Content is understandable on first reading.

**Guidelines:**
- Use simple, direct language
- Avoid ambiguous terms
- Define technical concepts when first introduced
- Use active voice instead of passive
- Break complex ideas into smaller parts

**Examples:**

❌ **Unclear:**
```
The system may potentially utilize various mechanisms for data processing.
```

✅ **Clear:**
```
The system processes data using three mechanisms: streaming, batch, and real-time.
```

---

### 2. Conciseness (Стислість)

**Definition:** No unnecessary words or redundant information.

**Guidelines:**
- Remove filler words and phrases
- Avoid repetition
- Get to the point quickly
- Use lists instead of long paragraphs
- Delete "obvious" information

**Examples:**

❌ **Verbose:**
```
In order to start the application, you will need to execute the following command 
in your terminal or command line interface: `geosync run`. This command will 
initiate the trading system and begin processing market data.
```

✅ **Concise:**
```
Start the application:
```bash
geosync run
```
This initiates the trading system and processes market data.
```

---

### 3. Correctness (Коректність)

**Definition:** Describes only factual behavior from code or PR changes.

**Guidelines:**
- Verify all statements against code
- Do not assume or speculate
- Update examples to match current behavior
- Remove outdated information
- Validate all code snippets

**Examples:**

❌ **Incorrect (assumes behavior):**
```
The API probably returns an error if the API key is invalid.
```

✅ **Correct (based on code):**
```
The API returns HTTP 401 with error code `INVALID_API_KEY` if authentication fails.
```

---

### 4. Consistency (Узгодженість)

**Definition:** Terms, style, and formatting aligned with existing documentation.

**Guidelines:**
- Use the same term for the same concept
- Follow established naming conventions
- Match existing heading hierarchy
- Use consistent code formatting
- Maintain uniform structure across sections

**Examples:**

❌ **Inconsistent:**
```
# File 1: Uses "trading strategy"
# File 2: Uses "trade strategy"
# File 3: Uses "strategy pattern"
```

✅ **Consistent:**
```
# All files: Use "trading strategy" for algorithms
# All files: Use "strategy pattern" for design pattern only
```

## Controlled Natural Language (CNL)

In addition to 4C principles, documentation follows CNL rules:

### Sentence Structure
- Short sentences (prefer under 20 words)
- One idea per sentence
- Simple subject-verb-object structure

### Word Choice
- Technical terms over colloquialisms
- Standard industry terminology
- No metaphors, jokes, or slang
- No marketing language in technical docs

### Format
- Use code blocks for all code
- Use lists for multiple items
- Use tables for comparisons
- Use headers for section organization

## Application in DOC PR COPILOT v2

The agent applies these principles during the REFLECT phase:

1. **Clarity Check:**
   - Can a senior engineer understand this on first reading?
   - Are all technical terms defined?
   - Is the explanation direct and unambiguous?

2. **Conciseness Check:**
   - Can any words be removed without losing meaning?
   - Are there redundant explanations?
   - Is the information density optimal?

3. **Correctness Check:**
   - Does this match the code diff?
   - Are all examples executable and correct?
   - Is any information speculative or assumed?

4. **Consistency Check:**
   - Do terms match existing documentation?
   - Does formatting follow repository style?
   - Is the structure aligned with similar docs?

## Enforcement

The agent will:
- Automatically rewrite content that violates 4C principles
- Flag severe violations in REVIEW_NOTES
- Prefer factual accuracy over style preferences
- Maintain consistency within and across files

## Examples

### Before 4C (Original Documentation)

```markdown
## Getting Started with GeoSync

So, you want to get started with GeoSync? Great! GeoSync is this really 
cool trading platform that's super powerful and flexible. It can do all sorts 
of amazing things with market data. Basically, it's like having a trading 
assistant that works 24/7 for you!

First, you'll probably want to install it. There are various different ways 
you might do this, depending on your system and preferences. You could use pip, 
or maybe conda, or possibly even build from source if you're feeling adventurous.
```

### After 4C (Agent-Revised Documentation)

```markdown
## Quick Start

Install GeoSync:

```bash
pip install geosync
```

Create a configuration file:

```yaml
# config.yaml
exchange: binance
api_key: your-key-here
```

Run the trading system:

```bash
geosync run --config config.yaml
```

See [Installation Guide](docs/installation.md) for detailed setup options.
```

## Common Violations and Fixes

| Violation | Example | Fix |
|-----------|---------|-----|
| Unclear pronoun | "It processes the data" | "The parser processes market data" |
| Redundancy | "This API endpoint returns back the results" | "This endpoint returns the results" |
| Speculation | "This should work in most cases" | "This works when X condition is met" |
| Inconsistent terms | Mix of "config" and "configuration" | Use "configuration" consistently |
| Passive voice | "The data is processed by the handler" | "The handler processes the data" |
| Filler words | "In order to start" | "To start" |
| Marketing language | "Amazing new feature!" | "New feature: [description]" |

## References

- [Plain Language Guidelines (plainlanguage.gov)](https://www.plainlanguage.gov/)
- [Google Developer Documentation Style Guide](https://developers.google.com/style)
- [Microsoft Writing Style Guide](https://docs.microsoft.com/style-guide/)
- [Write the Docs Best Practices](https://www.writethedocs.org/guide/)
