# Evaluation Report: `pallets/click`

**Model:** gemini-2.5-flash | **PRs evaluated:** 5 | **Total time:** 130.6s

## Summary

| Metric | Value |
|--------|-------|
| Total human comments | 42 |
| Botable (fair comparison) | 36 |
| Non-botable (conversational/design) | 6 |
| True Positives | 0 |
| False Positives | 3 |
| False Negatives | 36 |
| **Precision** (botable only) | **0.0%** |
| **Recall** (botable only) | **0.0%** |
| **F1 Score** (botable only) | **0.0%** |

## Per-PR Breakdown

| PR# | Title | TP | FP | FN | Precision | Recall | Time |
|-----|-------|----|----|----|-----------|--------|------|
| #755 | Dynamic bash autocompletion | 0 | 1 | 12 | 0.0% | 0.0% | 31216ms |
| #806 | Fix overzealous completion when required options/a… | 0 | 0 | 5 | 0.0% | 0.0% | 29085ms |
| #869 | ZSH completion auto-documentation | 0 | 0 | 4 | 0.0% | 0.0% | 33086ms |
| #860 | Pass ctx to NoSuchOption exceptions | 0 | 2 | 0 | 0.0% | 0.0% | 10214ms |
| #830 | Wrap stdout/stderr to avoid "Not enough space" in … | 0 | 0 | 15 | 0.0% | 0.0% | 27032ms |

## Per-Severity Breakdown

| Severity | TP | FP |
|----------|----|----|
| SUGGESTION | 0 | 3 |

## Sample Matches

### True Positives (bot matched human)

_No true positives._

### False Positives (bot flagged, human didn't)

**click/_bashcomplete.py:109** [SUGGESTION]
- 🤖 Bot: The `get_user_autocompletions` function currently prioritizes `Choice` types over the `autocompletion` callback. This means if both are provided for a

**click/parser.py:324** [SUGGESTION]
- 🤖 Bot: Passing `self.ctx` to `NoSuchOption` provides the exception with more context, which can be used for more informative error messages or better error h

**click/parser.py:367** [SUGGESTION]
- 🤖 Bot: Consistently passing `self.ctx` to `NoSuchOption` improves the error path by providing more context for potential error handling or user feedback.

### False Negatives (human flagged, bot missed)

**click/_bashcomplete.py:107**
- 👤 Human: You can just use `yield` here.

**click/_bashcomplete.py:107**
- 👤 Human: Ok, is this is what you had in mind?

**click/_bashcomplete.py:107**
- 👤 Human: Ah, hmm. I'm trying to avoid instantiation of a list here. More comments will follow.

### Non-botable Comments (filtered from recall)

- [length] “Sounds good.”
- [length] “What do you think?”
- [length] “@untitaker ?”
- [length] “s/with a/with/”
- [casual] “Can you add a :param: docstring for this new kwarg?

Thanks”

## Performance

| Metric | Value |
|--------|-------|
| Avg time/PR | 26127ms |
| Min time/PR | 10214ms |
| Max time/PR | 33086ms |
| Total eval time | 130.6s |

## Configuration

| Setting | Value |
|---------|-------|
| Repository | `pallets/click` |
| PRs requested | 5 |
| PRs evaluated | 5 |
| Gemini model | `gemini-2.5-flash` |

