from scripts.eval_retrieval import metrics


def test_hit_and_true_recall_are_separate():
    result=metrics([{"id":"P1","source_id":"S1"}], ["P1","P2"], ["S1","S2"])
    assert result["passage_hit_at_5"] == 1
    assert result["passage_recall_at_5"] == .5
    assert result["unique_document_recall_at_10"] == .5


def test_document_recall_uses_canonical_source_ids_and_deduplicates():
    results=[{"id":f"P{i}","source_id":f"S{i//2}","paper_id":"Historical alias"} for i in range(20)]
    result=metrics(results,["P0"],["S0","S9"])
    assert result["unique_document_recall_at_10"] == 1


def test_baseline_encoder_must_match_its_own_offline_index(fixture_release,tmp_path):
    import pytest
    from scripts.common import json_write,jsonl_write,jsonl_read
    from scripts.eval_retrieval import evaluate
    base_model=tmp_path/"base-model";base_model.mkdir();json_write(base_model/"config.json",{})
    base_index=tmp_path/"base-index";base_index.mkdir()
    rows=jsonl_read(fixture_release/"evidence/passages.jsonl")
    jsonl_write(base_index/"passages.jsonl",rows)
    json_write(base_index/"manifest.json",{"model_fingerprint":"incorrect-checkpoint-digest"})
    questions=tmp_path/"questions.jsonl"
    jsonl_write(questions,[{"id":"Q-TEST","query":"Synthetic flame","set":"test_only","authorship":"agent","question_family":"test","relevant_passage_ids":["TEST-P1"]}])
    with pytest.raises(ValueError,match="Base model/index checkpoint identity"):
        evaluate(fixture_release,questions,tmp_path/"report.json",base_index,base_model)
