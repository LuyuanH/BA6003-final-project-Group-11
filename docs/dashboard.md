# Dashboard use

[Go to README](../README.md)

The dashboard replays detection results in historical time for evidence inspection and manual review.
See the [README](../README.md#setup) for installation, AI configuration, and start commands.

## Language and replay

New sessions use English by default.
You can select Chinese.
AI analysis uses the interface language at the start of the request.
The instructions below use the English interface labels.

Replay speeds are 900×, 3,600×, 14,400×, and 28,800×.
The default speed is 28,800×.
Replay moves forward only and includes the last detection cutoff.
Case inspection does not pause replay.
You cannot move replay to a selected time or move it backward.
Replay does not start again from the previous session position.

## Case inspection

The queue contains structure groups that wait for review or are under investigation.
The transaction graph and evidence table show the last evidence version available at the replay time.
This version contains all transaction members.
They do not include future evidence.
See [Project terms](architecture.md#project-terms) for the definitions of evidence sets, evidence versions, and structure groups.

## Manual review

1. Open a case from the queue.
2. Examine the transaction graph and evidence table.
3. Select **Complete review ✓** to open the review form.
4. Enter a comment.
5. Select a fraud type.
6. Select **Submit**.

A comment and fraud type are necessary.
The fraud types include eight patterns and **Non-fraud / False positive**.

When the application accepts a review, it removes the structure group from the queue in the active session.
New evidence does not automatically add a group with a completed review to the queue again.
The decision stays in the case details.
Select **Reopen review** to add the group to the queue again.

Review status is only for the active browser session.
AI reports do not complete manual reviews or change manual decisions.

## Transaction counts and amounts

- The processed transaction count includes source transactions before or at the replay time.
- The pending transaction count includes all available evidence from structure groups without a completed review.
  The count includes each transaction ID one time.
  It includes previous evidence versions, not only the last version in the case details.
- A transaction stays pending if it is also in a different structure group without a completed review.
- Transactions can be part of more than one pattern. Do not add the pattern counts to get a total.
- The dashboard shows transaction amounts independently for each currency.
