# Finite CUDA training deadline

Status: Active. User authorized Tuldok improvements needed for the ongoing
CUDA-training/CPU-inference sequence. One bounded slice extends only explicitly
managed CUDA execution from600 to1800seconds. Ordinary CPU remains600seconds;
captured CPU large-output profile remains2400seconds. One CUDA slot, memory
reservations, stopping/physical gates and optimizer budgets do not change.

Evidence: the5000-update control Run f8e6bd15f5ba4e6bbd5571071ecb2798 drained
after the600second execution deadline, last reported update4500. Retain that
failed attempt and close its Study before a fresh from-initialization run.

Write set: recipe admission, custody validation, affected contract tests/docs.
The custody owner supplies the shared CUDA bound to admission. No new receipt or
spec dialect, runtime installation or model arithmetic. Verify rejection above
the CUDA limit and unchanged CPU restriction, plus lifecycle cancellation/drain.
Deploy only after isolated verification and no live active Runs. Do not replay
any unknown mutation or overwrite completed migration gates.
