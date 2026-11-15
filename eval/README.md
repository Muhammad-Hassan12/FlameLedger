# Retrieval evaluation

`human_questions.jsonl` is intentionally empty. No independently human-authored or reviewed questions were supplied. Do not populate it with AI output and call it human gold.

Each completed row needs:

```json
{"id":"H01","query":"Write an independent research question","set":"human_independent","authorship":"human","reviewer":"actual reviewer","question_family":"independent-family-id","relevant_passage_ids":["actual passage ID"],"relevant_document_ids":["actual source ID"],"notes":"Identify an answer-bearing span and inspect related report versions"}
```

Use 15–25 independently written questions covering all lanes. Label all relevant passages/documents where practical. Avoid related report versions crossing question families. Keep the labels off any rank-tuning path. Passage Hit@5, first relevant MRR@10, true passage Recall@5 and unique-document Recall@10 are separate metrics.

`development_questions.jsonl`, when present, is agent-authored and unreviewed. It is useful for pipeline smoke tests and failure examples, and cannot support a claim of human relevance quality. Historical synthetic/teacher scores remain in the untouched uploaded run, separately labeled from new serving evaluations.
