# Serotonin Stability Controller - Example Usage

This document demonstrates practical usage patterns for the Serotonin Stability Controller (5-HT Layer) agent in various development scenarios.

---

## Scenario 1: Sprint Overwhelm

### Context
Developer is facing an overwhelming sprint with multiple urgent tasks, experiencing high stress and considering working through the weekend.

### User Input
```
I have 8 PRs to review, 5 features to implement for the demo next week, 
3 production bugs that need fixing, and the PM just added 2 more "critical" 
items. I guess I'll just cancel my weekend plans and work straight through. 
No other choice.
```

### Agent Response

#### Serotonin Snapshot
* `serotonin_score:` 0.18
* `state:` severe overload, crash imminent
* `main_risk:` Cognitive overload leading to poor decisions and burnout

#### Stabilizing Moves (Next 30–90 minutes)
1. Stop and make a list: write down all 18 items in one place
2. Mark exactly 3 items as "this week" priority (demo-critical only)
3. Send email to PM: "I can do 3 items this week. Which 3?"
4. Schedule 15-minute break right now (walk outside, water)
5. Block 2-hour focus window for highest priority item
6. Set hard stop time: 6pm today, no exceptions

#### Medium-Horizon Guardrails (Next 7–30 days)
1. Max 5 active items per week (say NO to additions)
2. No weekend work unless pre-planned with recovery time
3. Daily 30-minute "triage meeting" with PM to prevent scope creep
4. End each day by identifying tomorrow's ONE priority
5. If PM adds items, ask "What should I drop?"

#### Language Reframe
* **Before:** "I guess I'll just cancel my weekend plans and work straight through. No other choice."
* **After:** "I have 18 pending items. I will identify the 3 highest-priority items for this week and negotiate the rest with my PM."

---

## Scenario 2: Post-Deployment Anxiety

### Context
Developer just deployed a major feature and is obsessively checking logs and metrics every 5 minutes, unable to focus on other work.

### User Input
```
The deployment went live 2 hours ago. Everything looks fine but I keep 
refreshing the dashboard. What if something breaks? What if users hate it? 
Maybe I should add more monitoring. Or rollback? I can't focus on anything else.
```

### Agent Response

#### Serotonin Snapshot
* `serotonin_score:` 0.42
* `state:` anxiety-driven hypervigilance, unproductive
* `main_risk:` Wasted cognitive bandwidth on low-probability monitoring

#### Stabilizing Moves (Next 30–90 minutes)
1. Set explicit monitoring schedule: check dashboard at 2pm, 5pm only
2. Define concrete rollback criteria (e.g., error rate >5%, latency >2s)
3. If criteria not met, feature stays deployed (no premature rollback)
4. Close monitoring tabs, set desktop alert for critical errors
5. Switch to different task: 30-minute code review or documentation
6. Acknowledge: deployment is done, monitoring is automated

#### Medium-Horizon Guardrails (Next 7–30 days)
1. Post-deployment: check metrics 3x first day, 2x second day, 1x thereafter
2. Define success metrics before deployment (don't invent new ones after)
3. Schedule post-mortem 48 hours after deployment (not immediately)
4. Trust automated alerting; disable manual refreshing habit

#### Language Reframe
* **Before:** "What if something breaks? What if users hate it? Maybe I should rollback?"
* **After:** "The deployment meets success criteria (error rate <5%, latency <2s). I will check metrics at scheduled times (2pm, 5pm) and respond to alerts if they occur."

---

## Scenario 3: Perfectionism Paralysis

### Context
Developer has been refactoring the same module for 3 days, unable to decide when it's "good enough" to commit.

### User Input
```
This refactor could be so much better. I could extract 3 more classes, 
add 10 more tests, improve the naming... But then I should probably 
refactor the related modules too for consistency. Maybe I should start over 
with a better design pattern?
```

### Agent Response

#### Serotonin Snapshot
* `serotonin_score:` 0.31
* `state:` perfectionism loop, diminishing returns
* `main_risk:` Infinite refactoring with no concrete value delivered

#### Stabilizing Moves (Next 30–90 minutes)
1. Define "done" right now: "code works, has basic tests, and is readable"
2. Commit current state with message "Refactor module X (incremental)"
3. Open PR with title "Refactor X - Part 1 of 3 (maybe)"
4. List future improvements in PR description as "Future work" section
5. Move to different task for rest of day

#### Medium-Horizon Guardrails (Next 7–30 days)
1. Time-box refactors: 4 hours max per module
2. "Good enough" = works + tested + reviewed (not perfect)
3. Ship small refactors, iterate later if needed
4. Ask: "Does this improvement unblock anything?" If no, defer it
5. Celebrate shipping > agonizing over perfection

#### Language Reframe
* **Before:** "This refactor could be so much better. Maybe I should start over with a better design pattern?"
* **After:** "This refactor improves readability and testability. It is good enough to ship. Future improvements can be made incrementally if needed."

---

## Scenario 4: Debugging Burnout

### Context
Developer has been debugging the same issue for 6 hours straight, getting increasingly frustrated and irrational.

### User Input
```
I've tried everything. EVERYTHING. This bug makes no sense. The logs don't 
help. Stack Overflow has nothing. I'm about to just delete this entire module 
and rewrite it. Or maybe I'm just not good enough to solve this.
```

### Agent Response

#### Serotonin Snapshot
* `serotonin_score:` 0.22
* `state:` cognitive fatigue, tunnel vision
* `main_risk:` Poor decisions due to exhaustion; negative self-attribution

#### Stabilizing Moves (Next 30–90 minutes)
1. STOP debugging immediately (close IDE, step away)
2. Take 30-minute break: walk, food, water (non-negotiable)
3. Write down what you've tried (externalize the search space)
4. Ask for help: post issue in team chat or forum with details
5. Work on different task for 2 hours (let brain reset)
6. Return to bug tomorrow with fresh perspective

#### Medium-Horizon Guardrails (Next 7–30 days)
1. Max 2 hours on any single bug before asking for help
2. Mandatory 15-minute break every 90 minutes when debugging
3. Recognize tunnel vision: if frustration >7/10, stop immediately
4. Keep "what I tried" log during debugging (prevents circular attempts)
5. "Not good enough" → "This bug is hard; I need a different approach"

#### Language Reframe
* **Before:** "I've tried everything. Or maybe I'm just not good enough to solve this."
* **After:** "I have been debugging for 6 hours and have exhausted my current approaches. I will take a break, document what I've tried, and ask for help from a colleague."

---

## Scenario 5: Feature Scope Creep

### Context
Developer is implementing a simple feature but keeps thinking of "nice to have" additions that expand scope.

### User Input
```
The user wants a simple export button. I've implemented CSV export. 
But now I'm thinking... what about Excel? And PDF? And what if they want 
to customize the columns? And email the export? And schedule automatic 
exports? This could be really powerful...
```

### Agent Response

#### Serotonin Snapshot
* `serotonin_score:` 0.48
* `state:` scope expansion, feature creep in progress
* `main_risk:` Simple feature becomes multi-week project, delays other work

#### Stabilizing Moves (Next 30–90 minutes)
1. Check original requirement: "export button" → CSV is sufficient
2. Commit and ship CSV export today (meets requirement)
3. Create separate tickets for Excel, PDF, customization (don't implement now)
4. Let product owner prioritize future enhancements
5. Celebrate: feature is DONE, not "almost done if I add 5 more things"

#### Medium-Horizon Guardrails (Next 7–30 days)
1. Implement exactly what was requested (not what could be nice)
2. Capture future ideas in backlog, don't implement immediately
3. Ask product owner: "Should I add X, or ship what we have?"
4. Remember: shipping simple feature > perfect feature that never ships
5. Review: "Would I accept this if someone else built it?" If yes, ship it.

#### Language Reframe
* **Before:** "This could be really powerful... [lists 5 additional features]"
* **After:** "The requirement is for CSV export. I have implemented that. Additional features (Excel, PDF, customization) can be added in future iterations if prioritized."

---

## Integration Patterns

### Pattern 1: Pre-Sprint Planning
Run user input through 5-HT controller before committing to sprint:
- Input: "Here's what I plan to do this sprint..."
- Output: Risk score, priority adjustments, scope constraints

### Pattern 2: Daily Standup Self-Check
Quick 5-HT check each morning:
- Input: Current task list + yesterday's completion + stress level
- Output: Tempo adjustment (slow down / keep steady / micro-step)

### Pattern 3: PR Description Review
Before opening PR, check language for stress signals:
- Input: Draft PR description
- Output: Language reframe suggestions (harsh → neutral)

### Pattern 4: Incident Response Cooldown
After resolving production incident:
- Input: Post-incident stress level + next actions
- Output: Recovery plan, guardrails to prevent burnout

### Pattern 5: Code Review Load Balancing
Before accepting review request:
- Input: Current review load + cognitive state
- Output: Accept/defer decision, delegation suggestions

---

## CLI Integration Example

> **Note**: This is an illustrative example. Production implementations should use proper JSON encoding, input validation, and error handling.

```bash
#!/bin/bash
# 5ht-check.sh - Quick serotonin stability check (EXAMPLE ONLY)

echo "Current tasks:"
cat tasks.txt

echo ""
echo "Stress level (1-10):"
read stress

echo ""
echo "Hours worked today:"
read hours

# Send to 5-HT agent (via API or LLM integration)
# NOTE: In production, properly encode JSON and validate inputs
curl -X POST https://api.agent.local/5ht/check \
  -d '{"tasks": "'$(cat tasks.txt)'", "stress": '$stress', "hours": '$hours'}' \
  | jq '.stabilizing_moves'
```

---

## Metrics Dashboard Integration

> **Note**: This is an illustrative example. Production implementations should include proper error handling, configuration management, and data validation.

Track 5-HT scores over time to identify patterns:

```python
import matplotlib.pyplot as plt
import pandas as pd

# Load 5-HT scores from logs
# NOTE: In production, add error handling for missing files and invalid data
df = pd.read_csv('5ht_scores.csv')
df['date'] = pd.to_datetime(df['date'])

# Plot stability trend
plt.figure(figsize=(12, 6))
plt.plot(df['date'], df['serotonin_score'], marker='o')
plt.axhline(y=0.5, color='orange', linestyle='--', label='Threshold')
plt.axhline(y=0.3, color='red', linestyle='--', label='Critical')
plt.xlabel('Date')
plt.ylabel('Serotonin Score')
plt.title('Cognitive Stability Trend')
plt.legend()
plt.grid(True, alpha=0.3)
plt.show()

# Identify crisis points
crisis_days = df[df['serotonin_score'] < 0.3]
print(f"Crisis days: {len(crisis_days)}")
print(crisis_days[['date', 'serotonin_score', 'main_risk']])
```

---

## Best Practices

### 1. Daily Check-ins
- Run 5-HT check at start of day
- Adjust plan based on stability score
- Track scores to identify patterns

### 2. Threshold-Based Interventions
- Score >0.6: Normal operation
- Score 0.4-0.6: Monitor closely, consider tempo adjustment
- Score 0.2-0.4: Implement stabilizing moves immediately
- Score <0.2: Emergency mode (stop, rest, delegate)

### 3. Team Integration
- Share 5-HT scores with manager (optional)
- Use for capacity planning (team-level stability)
- Normalize discussing cognitive load

### 4. Retrospective Analysis
- Review 5-HT scores during sprint retros
- Identify patterns: which tasks cause crashes?
- Adjust planning to prevent future overload

### 5. Automation
- Integrate with issue tracker to analyze task load
- Auto-calculate 5-HT score from calendar + commits
- Alert when score drops below threshold

---

## Anti-Patterns to Avoid

### ❌ Ignoring Low Scores
Don't treat 5-HT score as "just a number". Score <0.3 requires immediate action.

### ❌ Treating as Medical Advice
5-HT controller is NOT a replacement for mental health care. Seek professional help if needed.

### ❌ Gaming the System
Don't adjust inputs to get higher scores. The goal is honest assessment, not high scores.

### ❌ Using to Pressure Others
Don't use someone else's low 5-HT score to pressure them. Use it to support and adjust load.

### ❌ One-Time Check
5-HT monitoring is most effective with regular, consistent use. Single checks have limited value.

---

## Summary

The Serotonin Stability Controller (5-HT Layer) is a tool for:
- ✅ Identifying unsustainable work patterns
- ✅ Providing concrete, actionable interventions
- ✅ Preventing burnout through early detection
- ✅ Reframing harsh self-talk into neutral technical language
- ✅ Maintaining long-term productivity through stability

It is NOT:
- ❌ Medical or psychiatric advice
- ❌ A replacement for professional mental health care
- ❌ A diagnostic tool for mental health conditions

Use it as a cognitive hygiene tool for sustainable software development.
