#!/usr/bin/env bash
# Send the digest through the SMTP notifier to the mail catcher of the Compose stack, and
# check that both messages arrived (ADR-0045). The stack must be running.
#
# What this shows: delivery over plain SMTP on the private network of the stack. It does
# not exercise STARTTLS, TLS or authentication: Mailpit is not set up for them.
#
# The addresses are invented and Mailpit delivers nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

compose=(docker compose -f deploy/compose/compose.yaml)
mailpit="http://127.0.0.1:8025/api/v1/messages"

"${compose[@]}" exec -T \
    -e ARBITER_PLUGINS__NOTIFIER=smtp \
    -e ARBITER_NOTIFICATIONS__SENDER=arbiter@example.org \
    -e 'ARBITER_NOTIFICATIONS__RECIPIENTS=[{"address":"ada@example.org","locale":"it"},{"address":"grace@example.org"}]' \
    -e 'ARBITER_NOTIFICATIONS__SETTINGS={"host":"mailpit","port":1025,"security":"none"}' \
    arbiter arbiter digest run --send

for attempt in 1 2 3 4 5; do
    messages="$(curl --fail --silent --show-error "${mailpit}")"
    if grep -q 'Arbiter daily digest' <<<"${messages}" \
        && grep -q 'Digest giornaliero di Arbiter' <<<"${messages}" \
        && grep -q 'ada@example.org' <<<"${messages}" \
        && grep -q 'grace@example.org' <<<"${messages}"; then
        echo "Mailpit holds the digest in English and in Italian."
        "${compose[@]}" exec -T arbiter arbiter audit verify
        exit 0
    fi
    echo "Not there yet (attempt ${attempt})."
    sleep 1
done

echo "The digest did not reach Mailpit." >&2
exit 1
