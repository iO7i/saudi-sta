# Data and learning policy

## Stored contracts

Each record separates original/verbatim text, editable text, summary, semantic plan, tool arguments, provider/model provenance, signal origin, source revision, permissions, and review state. Audio links/times exist only when a managed recording was actually stored. Text-only records cannot claim acoustic evidence.

Defaults are conservative:

| Permission / signal | Default |
| --- | --- |
| Processing | granted for the local run |
| Retention | unknown |
| Third-party processing | denied |
| Training use | unknown |
| Public redistribution | denied |
| Provider output training terms | unknown |
| Native confidence | null/unknown |
| Calibrated correctness | null |

Labels can be `CANDIDATE`, `SILVER`, `GOLD`, or `REJECTED`. There is no automatic silver/gold promotion. A non-human reviewer cannot promote a label. A model self-score or language-ID probability is never treated as correctness.

## Training manifest

The local training-manifest endpoint exports record IDs, label state, and eligibility/exclusion reasons only. It excludes private audio, authored smoke/test data, withdrawn/deleted records, records without required rights, and provider outputs with unknown terms. It does not export a transcript dump as a training set and does not train anything.

## Review and deletion

The review view lets an actual human identity/type and promotion reason be recorded. Transcript edits mark derived outputs stale; a future repair request must carry source revision and real audio range, and must not overwrite later human text. Deleting a record removes the local record and its associated stored derivative. Any downloaded JSON/CSV export is outside application control and cannot be recalled.

## License boundaries

Application code and authored fixture text are separate from local model artifacts, user audio, provider outputs, and imported Qalam material. This project does not assume downloadable weights are open source or redistribution/training-safe. No Qalam code/assets are copied into this project.
