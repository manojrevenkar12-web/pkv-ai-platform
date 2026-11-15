# Held-out run

The held-out world (`config/heldout.toml`: other customers, the premium letter in week 14 instead of 18, 30% English
emails, more paraphrased chat questions, more invoices billed above the threshold) was run once at commit 1b93072. Its
report is `reports/heldout.json`; it is not run again (`config/heldout.lock`).

## What held

| | Dev world | Held-out world |
|---|--:|--:|
| Routing accuracy, platform | 99.2% | 99.0% |
| Routing accuracy on answers to the premium letter | 98.2% | 98.5% |
| Days from the letter to the alarm | 0 | 0 |
| False alarms before the letter | 0 | 0 |
| Validation estimate minus production | +0.8 pts | −0.7 pts |
| Random-split estimate minus production | +2.1 pts | +1.2 pts |
| Wrong chat answers per 1,000 | 5.29 | 2.0 |
| Invoices settled without a person | 98.6% | 98.6% |
| All in per month, platform against the large model everywhere | €2,650 against €9,834 | €3,210 against €10,408 |

The monitor caught the earlier letter on its first day, and the split by time and customer stayed within a point of
production; a random split would again have promised more than production gave.

## What failed

The gate failed on one line: **model cost 0.75 of the large model everywhere** (the bar is 0.5).

The cause was the model choice for the invoice check. On the held-out holdout weeks the small and the large reader
were equally accurate (99.07% each), and the large one came out €0.20 cheaper per invoice all in (€0.058 against
€0.257), almost all of it money paid out wrongly and people's time, which a handful of invoices in two weeks can
swing. The platform took the large reader at 2.6 times the model cost per invoice on that point estimate alone: the
choice rule never asked whether the difference was more than luck.

Whether the large reader was the better choice on the held-out world is not known, and the held-out world is not run
again to find out. What is known is that the old rule would take a dearer model on any difference, however small or noisy.

Overpayment on the held-out invoices was also higher (€170 against €84 per 1,000), still inside the gate.

## What changed, measured on the dev world only

- `platform/select.py` now starts from the cheapest model that clears the gate and moves to a dearer one only if its
  saving per case all in is real at 90% in a paired bootstrap over the same holdout cases. Each trial records the mean
  saving and its lower bound; the design notes show them.
- The evaluation keeps each candidate's cost per case (model calls, people's time, money paid out wrongly) for the
  bootstrap.
- A test covers both a tie (stays with the cheaper model) and a clear saving (moves).

On the dev world the choice did not change (classifier, small, small) and every number in README.md stayed the same.
The held-out report is the original one and the gate in `config/gate.toml` is unchanged.

## Still open

The invoice reader's overpayment rose with more lines above the threshold. The next thing to try, on the dev world, is
a second read for every line above the threshold whose reason is present, since a misread reason pays out the higher
factor.
